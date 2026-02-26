# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import html
import re
import unicodedata
import io
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name (또는 menu 호환)

ASSOC_LOGO_ROOT = APP_DIR / "association_logo.png"
ASSOC_LOGO_DATA = DATA_DIR / "association_logo.png"

MOMS_LOGO_ROOT = APP_DIR / "moms_logo.png"
MOMS_LOGO_DATA = DATA_DIR / "moms_logo.png"
MOMS_BRAND_ROOT = APP_DIR / "moms_brand.png"
MOMS_BRAND_DATA = DATA_DIR / "moms_brand.png"

POSTER_SRC_ROOT = APP_DIR / "datamoms_poster_source.jpg"
POSTER_SRC_DATA = DATA_DIR / "moms_poster_source.jpg"
EXTRACTED_LOGO_PATH = DATA_DIR / "moms_logo_extracted.png"

WEEKDAY_KR_WD = ["월", "화", "수", "목", "금"]
WEEKDAY_FULL = ["월", "화", "수", "목", "금", "토", "일"]

ALL_DATA_FILES = [
    ("menu_index.csv", MENU_INDEX_PATH),
    ("base_menu.csv", BASE_MENU_PATH),
    ("change_menu.csv", CHANGE_MENU_PATH),
    ("delivery.csv", DELIVERY_PATH),
]

MAX_SERVER_BACKUPS_PER_LABEL = 30

# -----------------------------
# 안전 문자열 처리
# -----------------------------
def _safe_str(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()

def _safe_filename(s: str) -> str:
    s = _safe_str(s)
    if not s:
        return "식단표"
    s = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:120]

def _first_exists(*paths: Path) -> Path | None:
    for p in paths:
        try:
            if p.exists():
                return p
        except Exception:
            pass
    return None

# -----------------------------
# 가나다 정렬 키
# -----------------------------
def _ko_sort_key(s: str) -> tuple:
    x = _safe_str(s)
    if not x:
        return ("", "")
    x_norm = unicodedata.normalize("NFKD", x).casefold()
    return (x_norm, x.casefold())

def _unique_sorted(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        t = _safe_str(it)
        if not t:
            continue
        if t not in seen:
            out.append(t)
            seen.add(t)
    out.sort(key=_ko_sort_key)
    return out

# -----------------------------
# 원자적 CSV 저장 + 안전 읽기
# -----------------------------
def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)

def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        _atomic_write_csv(pd.DataFrame(columns=columns), path)
        return
    try:
        if path.stat().st_size == 0:
            _atomic_write_csv(pd.DataFrame(columns=columns), path)
    except Exception:
        pass

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, dtype=str, encoding="utf-8")

    df.columns = [re.sub(r"^\ufeff", "", _safe_str(c)).strip() for c in df.columns]

    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
        df = df[df["date"].ne("NaT")]
    return df

# -----------------------------
# 서버 내부 백업(참고용)
# -----------------------------
def _prune_backups_for_label(label: str, suffix: str) -> None:
    try:
        prefix = f"{label}_"
        files = sorted(
            [p for p in BACKUP_DIR.glob(f"{prefix}*{suffix}") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files[MAX_SERVER_BACKUPS_PER_LABEL:]:
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass

def _latest_backup_path(label: str, suffix: str) -> Path | None:
    try:
        prefix = f"{label}_"
        files = sorted(
            [p for p in BACKUP_DIR.glob(f"{prefix}*{suffix}") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files[0] if files else None
    except Exception:
        return None

def _backup_file_if_exists(path: Path, label: str) -> None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return

        cur_bytes = path.read_bytes()

        last = _latest_backup_path(label, path.suffix)
        if last is not None:
            try:
                if last.exists() and last.stat().st_size == len(cur_bytes):
                    if last.read_bytes() == cur_bytes:
                        return
            except Exception:
                pass

        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"{label}_{stamp}{path.suffix}"
        backup.write_bytes(cur_bytes)
        _prune_backups_for_label(label, path.suffix)
    except Exception:
        pass

def _mark_need_pc_backup(reason: str) -> None:
    st.session_state["needs_pc_backup"] = True
    st.session_state["needs_pc_backup_reason"] = reason
    st.session_state["needs_pc_backup_ts"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

def _upsert_by_date(path: Path, columns: list[str], d: date, value_col: str, value: str) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    if (df["date"] == key).any():
        df.loc[df["date"] == key, value_col] = value
    else:
        row = {c: "" for c in columns}
        row["date"] = key
        row[value_col] = value
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    _backup_file_if_exists(path, f"{path.stem}_backup")
    _atomic_write_csv(df, path)
    _mark_need_pc_backup(f"{path.name} 저장")

def _delete_by_date(path: Path, columns: list[str], d: date) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    df = df[df["date"] != key].copy()

    _backup_file_if_exists(path, f"{path.stem}_backup")
    _atomic_write_csv(df, path)
    _mark_need_pc_backup(f"{path.name} 삭제")

# -----------------------------
# ZIP 백업
# -----------------------------
def _build_data_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for arcname, p in ALL_DATA_FILES:
            if p.exists():
                z.write(p, arcname=arcname)
    return buf.getvalue()

def _restore_from_zip(zip_bytes: bytes) -> tuple[bool, str]:
    try:
        zbuf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(zbuf, "r") as z:
            names = z.namelist()
            wanted = {arcname: path for arcname, path in ALL_DATA_FILES}

            stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            for _, p in ALL_DATA_FILES:
                if p.exists():
                    _backup_file_if_exists(p, f"{p.stem}_before_zip_restore_{stamp}")

            restored = 0
            for n in names:
                fn = Path(n).name
                if fn in wanted:
                    dest = wanted[fn]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    restored += 1

        if restored == 0:
            return False, "ZIP 안에 복원 대상 CSV(menu_index/base_menu/change_menu/delivery)가 없습니다."
        _mark_need_pc_backup("ZIP 복원 후(새 상태) PC 백업 권장")
        return True, f"ZIP 복원 완료 ({restored}개 파일)"
    except Exception as e:
        return False, f"ZIP 복원 실패: {e}"

# -----------------------------
# 이미지(Data URI)
# -----------------------------
def _data_uri(path: Path | None) -> str | None:
    if path is None or (not path.exists()):
        return None
    b = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(b).decode("utf-8")

def _find_assoc_logo() -> Path | None:
    return _first_exists(ASSOC_LOGO_ROOT, ASSOC_LOGO_DATA)

def _find_moms_logo() -> tuple[str | None, bool]:
    brand = _first_exists(MOMS_BRAND_ROOT, MOMS_BRAND_DATA)
    if brand:
        return _data_uri(brand), True
    logo = _first_exists(MOMS_LOGO_ROOT, MOMS_LOGO_DATA)
    if logo:
        return _data_uri(logo), False
    extracted = _first_exists(EXTRACTED_LOGO_PATH)
    if extracted:
        return _data_uri(extracted), False
    return None, False

# -----------------------------
# 메뉴 인덱스
# -----------------------------
def _read_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    try:
        df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8")

    df.columns = [re.sub(r"^\ufeff", "", _safe_str(c)).strip() for c in df.columns]

    if "name" not in df.columns and "menu" in df.columns:
        df = df.rename(columns={"menu": "name"})

    if "name" not in df.columns:
        if len(df.columns) == 1:
            df = df.rename(columns={df.columns[0]: "name"})
        else:
            return []

    items = [_safe_str(x) for x in df["name"].fillna("").tolist()]
    return _unique_sorted(items)

def _write_menu_index(items: list[str]) -> None:
    items = _unique_sorted(items)
    _backup_file_if_exists(MENU_INDEX_PATH, "menu_index_backup")
    _atomic_write_csv(pd.DataFrame({"name": items}), MENU_INDEX_PATH)
    _mark_need_pc_backup("menu_index.csv 저장")

# -----------------------------
# (선택) 포스터 사진에서 M 로고 자동 추출
# -----------------------------
def _ensure_extracted_logo_if_needed() -> None:
    brand = _first_exists(MOMS_BRAND_ROOT, MOMS_BRAND_DATA)
    logo = _first_exists(MOMS_LOGO_ROOT, MOMS_LOGO_DATA)
    if brand or logo:
        return
    if EXTRACTED_LOGO_PATH.exists():
        return
    src = _first_exists(POSTER_SRC_ROOT, POSTER_SRC_DATA)
    if src is None:
        return
    try:
        from PIL import Image, ImageOps

        img = Image.open(src).convert("RGB")
        w, h = img.size
        crop = img.crop((0, 0, int(w * 0.32), int(h * 0.32)))
        crop = ImageOps.autocontrast(crop)

        gray = crop.convert("L")
        bw = gray.point(lambda p: 255 if p < 230 else 0, mode="1")
        bbox = bw.getbbox()

        if bbox:
            x0, y0, x1, y1 = bbox
            pad = 14
            x0 = max(0, x0 - pad)
            y0 = max(0, y0 - pad)
            x1 = min(crop.size[0], x1 + pad)
            y1 = min(crop.size[1], y1 + pad)
            logo_img = crop.crop((x0, y0, x1, y1))
        else:
            logo_img = crop.crop((0, 0, int(crop.size[0] * 0.70), int(crop.size[1] * 0.70)))

        logo_img = logo_img.resize((420, int(420 * logo_img.size[1] / max(1, logo_img.size[0]))))
        logo_img.save(EXTRACTED_LOGO_PATH, format="PNG", optimize=True)
    except Exception:
        return

# -----------------------------
# 달력/날짜 선택
# -----------------------------
def _weekday_calendar_picker(y: int, m: int, selected: date) -> date:
    cal = calendar.Calendar(firstweekday=0)
    weeks7 = cal.monthdayscalendar(y, m)

    rows5: list[list[int]] = []
    for wk in weeks7:
        wd = wk[:5]
        if all(d == 0 for d in wd):
            continue
        rows5.append(wd)

    st.markdown("**📅 날짜 선택(평일만)**")
    sel_day = selected.day if (selected.year == y and selected.month == m) else None

    hcols = st.columns(5)
    for i, w in enumerate(WEEKDAY_KR_WD):
        hcols[i].markdown(f"<div style='text-align:center;font-weight:900'>{w}</div>", unsafe_allow_html=True)

    for r, wk in enumerate(rows5):
        cols = st.columns(5)
        for c, day in enumerate(wk):
            if day == 0:
                cols[c].button(" ", key=f"blank_{y}_{m}_{r}_{c}", disabled=True, use_container_width=True)
                continue
            dt = date(y, m, day)
            label = f"{day:02d}" if sel_day != day else f"✅ {day:02d}"
            if cols[c].button(label, key=f"d_{y}_{m}_{day}", use_container_width=True):
                st.session_state["selected_date"] = dt
                st.session_state["show_quick_editor"] = True  # ✅ 날짜 클릭 즉시 입력창 열기
                st.rerun()

    return st.session_state.get("selected_date", selected)

# -----------------------------
# 달력 데이터 맵
# -----------------------------
def _get_day_record_map(y: int, m: int) -> dict[int, dict[str, str]]:
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    prefix = f"{y}-{m:02d}-"
    base = base[base["date"].str.startswith(prefix)].copy()
    change = change[change["date"].str.startswith(prefix)].copy()
    delivery = delivery[delivery["date"].str.startswith(prefix)].copy()

    out: dict[int, dict[str, str]] = {}
    for _, r in base.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) >= 2:
            try:
                d = int(ds[-2:])
                out.setdefault(d, {})
                out[d]["base"] = _safe_str(r.get("base_menu"))
            except Exception:
                pass

    for _, r in change.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) >= 2:
            try:
                d = int(ds[-2:])
                out.setdefault(d, {})
                out[d]["change"] = _safe_str(r.get("change_menu"))
            except Exception:
                pass

    for _, r in delivery.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) >= 2:
            try:
                d = int(ds[-2:])
                out.setdefault(d, {})
                v = _safe_str(r.get("delivery")).upper()
                out[d]["delivery"] = "N" if v == "N" else "Y"
            except Exception:
                pass

    return out

# -----------------------------
# 포스터 HTML (그대로)
# -----------------------------
def _build_weekday_poster_html(
    y: int,
    m: int,
    title1: str,
    title2: str,
    title3: str,
    right_label: str,
    moms_uri: str | None,
    moms_is_brand: bool,
    assoc_uri: str | None,
    contact_text: str,
) -> str:
    data_map = _get_day_record_map(y, m)

    cal = calendar.Calendar(firstweekday=0)
    weeks7 = cal.monthdayscalendar(y, m)
    rows5: list[list[int]] = []
    for wk in weeks7:
        wd = wk[:5]
        if all(d == 0 for d in wd):
            continue
        rows5.append(wd)

    row_count = len(rows5)
    cell_h = 122 if row_count <= 4 else 104

    if moms_uri and moms_is_brand:
        moms_box_html = f'<img src="{moms_uri}" class="moms-brand-banner" alt="MOMS"/>'
    else:
        logo_html = f'<img src="{moms_uri}" class="moms-logo-img" alt="M"/>' if moms_uri else '<div class="moms-logo-fallback">M</div>'
        moms_box_html = f"""
        <div class="brand-box">
          {logo_html}
          <div class="brand-text"><div class="moms">MOMS</div></div>
        </div>
        """

    assoc_html = f'<img src="{assoc_uri}" class="assoc-logo-img" alt="협회 로고"/>' if assoc_uri else ""

    css = f"""
    <style>
      @page {{ size: A4 landscape; margin: 6mm; }}
      html, body {{ height: 100%; }}
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
        color: #0f172a;
        background: #ffffff;
      }}
      .sheet {{ height: 100%; overflow: hidden; }}
      @media print {{
        * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        table, tr, td, th {{ page-break-inside: avoid !important; break-inside: avoid !important; }}
      }}
      .sheet {{ width: 100%; padding: 8px 10px; box-sizing: border-box; }}

      .header {{
        display:grid;
        grid-template-columns: 220px 1fr 320px;
        gap: 10px;
        align-items: center;
        margin-bottom: 8px;
      }}

      .brand-box {{
        height: 98px;
        border-radius: 20px;
        background: #ffffff;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:flex-start;
        gap: 14px;
        padding: 14px 16px;
        box-sizing: border-box;
      }}
      .moms-logo-img {{
        height: 64px;
        width: auto;
        object-fit: contain;
        border-radius: 14px;
      }}
      .moms-logo-fallback {{
        height: 64px; width: 64px;
        border-radius: 16px;
        display:flex; align-items:center; justify-content:center;
        font-weight: 1000; font-size: 44px;
        border: 2px solid rgba(15,23,42,0.18);
        background: rgba(0,0,0,0.03);
      }}
      .brand-text {{ line-height: 1.0; font-weight: 1000; letter-spacing: -0.3px; }}
      .brand-text .moms {{ font-size: 30px; }}

      .moms-brand-banner {{
        height: 98px;
        width: 100%;
        object-fit: contain;
        border-radius: 20px;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        background: #fff;
      }}

      .title {{
        text-align: center;
        line-height: 1.03;
      }}
      .title .t1 {{
        font-size: 34px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 0;
        background: linear-gradient(90deg, #0ea5e9, #22c55e);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }}
      .title .t2 {{
        font-size: 34px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 6px 0 0 0;
        background: linear-gradient(90deg, #8b5cf6, #ec4899);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }}
      .title .t3 {{
        font-size: 20px;
        font-weight: 900;
        letter-spacing: -0.6px;
        margin: 6px 0 0 0;
        color: rgba(15,23,42,0.70);
      }}

      .right-box {{
        height: 98px;
        border-radius: 20px;
        background: #ffffff;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        gap: 10px;
        padding: 12px 14px;
        box-sizing: border-box;
      }}
      .assoc-logo-img {{
        height: 66px;
        width: auto;
        object-fit: contain;
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
        transform: translateZ(0);
      }}
      .right-box .label {{ font-size: 28px; font-weight: 1000; letter-spacing: -0.3px; text-align:center; }}
      .contact {{
        margin-top: 6px;
        font-size: 15px;
        font-weight: 900;
        opacity: 0.90;
        text-align: center;
        white-space: nowrap;
        word-break: keep-all;
      }}

      table {{
        border-collapse: separate;
        border-spacing: 10px 10px;
        width: 100%;
        table-layout: fixed;
      }}
      th {{ font-size: 15px; font-weight: 1000; text-align:center; padding: 0; }}
      td {{
        height: {cell_h}px;
        vertical-align: top;
        background: #ffffff;
        border: 2.4px solid rgba(15,23,42,0.32);
        border-radius: 14px;
        box-shadow: 0 7px 12px rgba(15,23,42,0.06);
        padding: 10px 12px;
        box-sizing: border-box;
        overflow: hidden;
        position: relative;
      }}
      .empty {{ background: #ffffff; border: 2.4px dashed rgba(15,23,42,0.22); box-shadow: none; }}

      .has-change {{ border-color: rgba(184, 134, 11, 0.55); background: rgba(255, 250, 235, 0.96); }}
      .no-delivery {{ border-color: rgba(176,0,32,0.46); background: rgba(255, 240, 244, 0.96); }}
      .both {{ border-color: rgba(125, 60, 152, 0.56); background: rgba(248, 244, 255, 0.96); }}

      .corner {{
        position: absolute;
        top: 6px;
        right: 8px;
        width: 26px;
        height: 26px;
        border-radius: 999px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        font-weight: 1000;
        border: 1px solid rgba(15,23,42,0.25);
        box-shadow: 0 2px 4px rgba(15,23,42,0.10);
      }}
      .corner-change {{
        background: rgba(255, 230, 180, 0.95);
        color: rgba(120, 70, 0, 1.0);
      }}
      .corner-nodelivery {{
        background: rgba(255, 200, 210, 0.95);
        color: rgba(140, 0, 20, 1.0);
      }}
      .corner-both {{
        background: rgba(220, 210, 255, 0.95);
        color: rgba(70, 35, 120, 1.0);
      }}

      .cell-top {{ display:flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-right: 28px; }}
      .datechip {{ display:inline-flex; align-items:baseline; gap: 8px; font-weight: 1000; font-size: 16px; letter-spacing: -0.3px; }}
      .dow {{ font-size: 12.5px; font-weight: 900; opacity: 0.72; }}
      .badge-nodelivery {{
        font-size: 12px; font-weight: 1000; color: #b00020;
        background: rgba(255, 235, 238, 0.98);
        border: 1px solid rgba(176,0,32,0.34);
        padding: 4px 10px; border-radius: 999px; letter-spacing: -0.2px;
      }}

      .menu {{ font-size: 16px; line-height: 1.18; letter-spacing: -0.35px; word-break: keep-all; }}
      .base {{ font-weight: 1000; }}
      .change {{ margin-top: 10px; font-weight: 1000; color: #c40000; }}
      .change .label {{
        display:inline-block; font-size: 12px; font-weight: 1000;
        padding: 2px 10px; border-radius: 999px;
        background: rgba(196,0,0,0.10);
        border: 1px solid rgba(196,0,0,0.34);
        margin-right: 8px;
      }}
    </style>
    """

    thead = "<tr>" + "".join([f"<th>{w}</th>" for w in WEEKDAY_KR_WD]) + "</tr>"

    body_rows = []
    for wk in rows5:
        tds = []
        for day in wk:
            if day == 0:
                tds.append('<td class="empty"></td>')
                continue

            dt = date(y, m, day)
            dow = WEEKDAY_FULL[dt.weekday()]

            rec = data_map.get(day, {})
            base_v = html.escape(_safe_str(rec.get("base", "")))
            change_v = html.escape(_safe_str(rec.get("change", "")))
            delivery_v = _safe_str(rec.get("delivery", "Y")).upper()

            is_nodelivery = (delivery_v == "N")
            has_change = bool(change_v)

            cls = ""
            corner = ""
            if has_change and is_nodelivery:
                cls = "both"
                corner = '<div class="corner corner-both">✔</div>'
            elif has_change:
                cls = "has-change"
                corner = '<div class="corner corner-change">✔</div>'
            elif is_nodelivery:
                cls = "no-delivery"
                corner = '<div class="corner corner-nodelivery">✖</div>'

            badge = '<span class="badge-nodelivery">배달불요</span>' if is_nodelivery else ""
            base_line = f'<div class="menu base">{base_v}</div>' if base_v else '<div class="menu base">&nbsp;</div>'
            change_block = f'<div class="menu change"><span class="label">변경</span>{change_v}</div>' if change_v else ""

            tds.append(f"""
            <td class="{cls}">
              {corner}
              <div class="cell-top">
                <div class="datechip">{day:02d}<span class="dow">({dow})</span></div>
                {badge}
              </div>
              {base_line}
              {change_block}
            </td>
            """)
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    return f"""
    <!doctype html>
    <html lang="ko">
      <head><meta charset="utf-8"/>{css}</head>
      <body>
        <div class="sheet">
          <div class="header">
            <div>{moms_box_html}</div>

            <div class="title">
              <p class="t1">{html.escape(title1)}</p>
              <p class="t2">{html.escape(title2)}</p>
              <p class="t3">{html.escape(title3)}</p>
            </div>

            <div class="right-box">
              {assoc_html}
              <div>
                <div class="label">{html.escape(right_label)}</div>
                <div class="contact">{html.escape(contact_text)}</div>
              </div>
            </div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>{''.join(body_rows)}</tbody>
          </table>
        </div>
      </body>
    </html>
    """

# -----------------------------
# 시작 시
# -----------------------------
_ensure_extracted_logo_if_needed()

# -----------------------------
# 사이드바: PC 백업
# -----------------------------
if "needs_pc_backup" not in st.session_state:
    st.session_state["needs_pc_backup"] = False
    st.session_state["needs_pc_backup_reason"] = ""
    st.session_state["needs_pc_backup_ts"] = ""

if "zip_nonce" not in st.session_state:
    st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

with st.sidebar:
    st.markdown("## 💾 PC 백업(필수)")
    st.caption("Streamlit Cloud는 재시작 시 서버파일이 사라질 수 있어, **ZIP을 PC로 내려받아 보관**하는 방식이 안전합니다.")

    if st.session_state.get("needs_pc_backup", False):
        reason = st.session_state.get("needs_pc_backup_reason", "")
        ts = st.session_state.get("needs_pc_backup_ts", "")
        st.warning(f"방금 변경됨: {reason}\n\n➡️ **지금 ZIP 백업을 PC로 다운로드**하세요.\n\n(시간: {ts})")

    zip_bytes = _build_data_zip_bytes()
    zip_name = f"moms_data_backup_{st.session_state['zip_nonce']}.zip"
    st.download_button(
        "⬇️ 데이터 ZIP 백업 다운로드",
        data=zip_bytes,
        file_name=zip_name,
        mime="application/zip",
        use_container_width=True,
    )

    c_done1, c_done2 = st.columns(2)
    with c_done1:
        if st.button("✅ 다운로드 완료", use_container_width=True):
            st.session_state["needs_pc_backup"] = False
            st.session_state["needs_pc_backup_reason"] = ""
            st.session_state["needs_pc_backup_ts"] = ""
    with c_done2:
        if st.button("🔁 새 ZIP 갱신", use_container_width=True):
            st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

    st.divider()
    st.markdown("### ♻️ ZIP 업로드로 복원")
    confirm = st.checkbox("⚠️ 업로드한 ZIP으로 현재 데이터를 덮어쓰는 것을 이해했습니다.", value=False)
    up = st.file_uploader("ZIP 파일 선택", type=["zip"])
    if up is not None:
        if not confirm:
            st.error("복원 전 확인 체크가 필요합니다. (실수로 데이터 덮어쓰기 방지)")
        else:
            ok, msg = _restore_from_zip(up.read())
            if ok:
                st.success(msg)
                st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.caption(f"서버 저장 경로(참고): {DATA_DIR}")

# -----------------------------
# 메인 UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption(f"저장 경로: {DATA_DIR}")

colL, colR = st.columns([1.15, 1.0], vertical_alignment="top")

with colL:
    st.subheader("1) 메뉴 인덱스 관리 (가나다 순 자동 정렬)")
    idx_items = _read_menu_index()

    c1, c2 = st.columns([1, 1])
    with c1:
        new_item = st.text_input("메뉴 추가", placeholder="예: 소고기미역국")
        if st.button("➕ 인덱스에 추가", use_container_width=True):
            x = _safe_str(new_item)
            if x:
                idx_items.append(x)
                _write_menu_index(idx_items)
                st.success("저장 완료(가나다 정렬) — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with c2:
        del_item = st.selectbox("삭제할 메뉴 선택", ["(선택)"] + idx_items)
        if st.button("🗑️ 선택 메뉴 삭제", use_container_width=True):
            if del_item != "(선택)":
                idx_items = [x for x in idx_items if x != del_item]
                _write_menu_index(idx_items)
                st.success("삭제 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()

    st.divider()
    st.subheader("2) 월 선택")

    today = date.today()
    y = st.selectbox("연도", list(range(today.year - 2, today.year + 4)), index=2)
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = date(y, m, 1)
    if "show_quick_editor" not in st.session_state:
        st.session_state["show_quick_editor"] = False

    sd: date = st.session_state["selected_date"]
    if sd.year != y or sd.month != m:
        st.session_state["selected_date"] = date(y, m, 1)

    # ✅ 달력
    dsel = _weekday_calendar_picker(y, m, st.session_state["selected_date"])
    key = dsel.isoformat()

    # ✅ 날짜 클릭 시 달력 바로 아래에 입력 패널 자동 오픈
    if st.session_state.get("show_quick_editor", False):
        st.markdown("---")
        st.subheader("📝 빠른 입력(날짜 클릭 후 바로 입력)")

        base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
        change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
        deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

        cur_base = _safe_str(base_df.loc[base_df["date"] == key, "base_menu"].iloc[0]) if (base_df["date"] == key).any() else ""
        cur_change = _safe_str(change_df.loc[change_df["date"] == key, "change_menu"].iloc[0]) if (change_df["date"] == key).any() else ""
        cur_deliv = _safe_str(deliv_df.loc[deliv_df["date"] == key, "delivery"].iloc[0]).upper() if (deliv_df["date"] == key).any() else "Y"
        if cur_deliv not in ["Y", "N"]:
            cur_deliv = "Y"

        # 날짜가 바뀌면 해당 날짜 값으로 셋업
        if st.session_state.get("quick_key") != key:
            st.session_state["quick_key"] = key
            st.session_state["q_base_pick"] = "(직접입력)"
            st.session_state["q_base_text"] = cur_base
            st.session_state["q_change_pick"] = "(없음)"
            st.session_state["q_change_text"] = cur_change
            st.session_state["q_deliv_choice"] = "배달(Y)" if cur_deliv == "Y" else "배달불요(N)"

        st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_FULL[dsel.weekday()]})")

        # 기본메뉴
        st.markdown("**기본메뉴**")
        q_base_pick = st.selectbox("기본메뉴(인덱스)", ["(직접입력)"] + idx_items, key="q_base_pick")
        if q_base_pick != "(직접입력)":
            st.session_state["q_base_text"] = q_base_pick
        st.text_input("기본메뉴(입력)", key="q_base_text")

        # 변경메뉴
        st.markdown("**변경메뉴(있으면 입력)**")
        q_change_pick = st.selectbox("변경메뉴(인덱스)", ["(없음)"] + idx_items, key="q_change_pick")
        if q_change_pick != "(없음)":
            st.session_state["q_change_text"] = q_change_pick
        st.text_input("변경메뉴(입력)", key="q_change_text")

        # 배달
        st.markdown("**배달 여부**")
        st.radio("배달", ["배달(Y)", "배달불요(N)"], key="q_deliv_choice", horizontal=True)

        s1, s2, s3 = st.columns([1, 1, 1])
        with s1:
            if st.button("💾 저장(한번에)", use_container_width=True):
                # 기본
                v_base = _safe_str(st.session_state.get("q_base_text", ""))
                if v_base:
                    _upsert_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel, "base_menu", v_base)
                # 변경(빈값이면 저장 안함)
                v_ch = _safe_str(st.session_state.get("q_change_text", ""))
                if v_ch and v_ch != "(없음)":
                    _upsert_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel, "change_menu", v_ch)
                # 배달
                v_deliv = "Y" if st.session_state.get("q_deliv_choice", "배달(Y)").startswith("배달(Y)") else "N"
                _upsert_by_date(DELIVERY_PATH, ["date", "delivery"], dsel, "delivery", v_deliv)

                # ✅ 저장 후 입력칸 비우기(빠른 연속 입력)
                st.session_state["q_base_pick"] = "(직접입력)"
                st.session_state["q_base_text"] = ""
                st.session_state["q_change_pick"] = "(없음)"
                st.session_state["q_change_text"] = ""
                st.session_state["q_deliv_choice"] = "배달(Y)"
                st.success("저장 완료 — 다음 날짜를 클릭해 계속 입력하세요.")
                st.rerun()

        with s2:
            if st.button("🧹 입력창 닫기", use_container_width=True):
                st.session_state["show_quick_editor"] = False
                st.rerun()

        with s3:
            if st.button("🧾 현재값 다시 불러오기", use_container_width=True):
                st.session_state.pop("quick_key", None)
                st.rerun()

with colR:
    st.subheader("4) 포스터(출력용 1장) 미리보기")

    right_label = st.text_input("우측 상단 표기", value="동약협회")
    headcount = st.number_input("인원수", min_value=1, max_value=999, value=1, step=1)
    contact = st.text_input("연락처", value="010-7101-5871")

    title1 = f"맘스락 {m:02d}월"
    title2 = "식단(배달) 변경"
    title3 = f"(인원:{int(headcount)}인)"
    contact_text = f"연락처: {contact}"

    moms_uri, moms_is_brand = _find_moms_logo()
    assoc_uri = _data_uri(_find_assoc_logo())

    poster_html = _build_weekday_poster_html(
        y=y,
        m=m,
        title1=title1,
        title2=title2,
        title3=title3,
        right_label=_safe_str(right_label) or "동약협회",
        moms_uri=moms_uri,
        moms_is_brand=moms_is_brand,
        assoc_uri=assoc_uri,
        contact_text=contact_text,
    )

    components.html(poster_html, height=780, scrolling=True)

    st.divider()
    st.subheader("5) 업체 전달용 파일 만들기")

    dl_name = _safe_filename(f"{title1}_{title2}_{title3}_{right_label}") + ".html"
    st.download_button(
        label=f"⬇️ HTML 다운로드 ({dl_name})",
        data=poster_html.encode("utf-8"),
        file_name=dl_name,
        mime="text/html",
        use_container_width=True,
    )# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import html
import re
import unicodedata
import io
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name (또는 menu 호환)

ASSOC_LOGO_ROOT = APP_DIR / "association_logo.png"
ASSOC_LOGO_DATA = DATA_DIR / "association_logo.png"

MOMS_LOGO_ROOT = APP_DIR / "moms_logo.png"
MOMS_LOGO_DATA = DATA_DIR / "moms_logo.png"
MOMS_BRAND_ROOT = APP_DIR / "moms_brand.png"
MOMS_BRAND_DATA = DATA_DIR / "moms_brand.png"

POSTER_SRC_ROOT = APP_DIR / "datamoms_poster_source.jpg"
POSTER_SRC_DATA = DATA_DIR / "moms_poster_source.jpg"
EXTRACTED_LOGO_PATH = DATA_DIR / "moms_logo_extracted.png"

WEEKDAY_KR_WD = ["월", "화", "수", "목", "금"]
WEEKDAY_FULL = ["월", "화", "수", "목", "금", "토", "일"]

ALL_DATA_FILES = [
    ("menu_index.csv", MENU_INDEX_PATH),
    ("base_menu.csv", BASE_MENU_PATH),
    ("change_menu.csv", CHANGE_MENU_PATH),
    ("delivery.csv", DELIVERY_PATH),
]

MAX_SERVER_BACKUPS_PER_LABEL = 30

# -----------------------------
# 안전 문자열 처리
# -----------------------------
def _safe_str(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x).strip()

def _safe_filename(s: str) -> str:
    s = _safe_str(s)
    if not s:
        return "식단표"
    s = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:120]

def _first_exists(*paths: Path) -> Path | None:
    for p in paths:
        try:
            if p.exists():
                return p
        except Exception:
            pass
    return None

# -----------------------------
# 가나다 정렬 키
# -----------------------------
def _ko_sort_key(s: str) -> tuple:
    x = _safe_str(s)
    if not x:
        return ("", "")
    x_norm = unicodedata.normalize("NFKD", x).casefold()
    return (x_norm, x.casefold())

def _unique_sorted(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        t = _safe_str(it)
        if not t:
            continue
        if t not in seen:
            out.append(t)
            seen.add(t)
    out.sort(key=_ko_sort_key)
    return out

# -----------------------------
# 원자적 CSV 저장 + 안전 읽기
# -----------------------------
def _atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)

def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        _atomic_write_csv(pd.DataFrame(columns=columns), path)
        return
    try:
        if path.stat().st_size == 0:
            _atomic_write_csv(pd.DataFrame(columns=columns), path)
    except Exception:
        pass

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, dtype=str, encoding="utf-8")

    df.columns = [re.sub(r"^\ufeff", "", _safe_str(c)).strip() for c in df.columns]

    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
        df = df[df["date"].ne("NaT")]
    return df

# -----------------------------
# 서버 내부 백업(참고용) - 폭증 방지 기능 포함
# -----------------------------
def _prune_backups_for_label(label: str, suffix: str) -> None:
    try:
        prefix = f"{label}_"
        files = sorted(
            [p for p in BACKUP_DIR.glob(f"{prefix}*{suffix}") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files[MAX_SERVER_BACKUPS_PER_LABEL:]:
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass

def _latest_backup_path(label: str, suffix: str) -> Path | None:
    try:
        prefix = f"{label}_"
        files = sorted(
            [p for p in BACKUP_DIR.glob(f"{prefix}*{suffix}") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files[0] if files else None
    except Exception:
        return None

def _backup_file_if_exists(path: Path, label: str) -> None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return

        cur_bytes = path.read_bytes()

        last = _latest_backup_path(label, path.suffix)
        if last is not None:
            try:
                if last.exists() and last.stat().st_size == len(cur_bytes):
                    if last.read_bytes() == cur_bytes:
                        return
            except Exception:
                pass

        stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"{label}_{stamp}{path.suffix}"
        backup.write_bytes(cur_bytes)
        _prune_backups_for_label(label, path.suffix)
    except Exception:
        pass

def _mark_need_pc_backup(reason: str) -> None:
    st.session_state["needs_pc_backup"] = True
    st.session_state["needs_pc_backup_reason"] = reason
    st.session_state["needs_pc_backup_ts"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

def _upsert_by_date(path: Path, columns: list[str], d: date, value_col: str, value: str) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    if (df["date"] == key).any():
        df.loc[df["date"] == key, value_col] = value
    else:
        row = {c: "" for c in columns}
        row["date"] = key
        row[value_col] = value
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    _backup_file_if_exists(path, f"{path.stem}_backup")
    _atomic_write_csv(df, path)
    _mark_need_pc_backup(f"{path.name} 저장")

def _delete_by_date(path: Path, columns: list[str], d: date) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    df = df[df["date"] != key].copy()

    _backup_file_if_exists(path, f"{path.stem}_backup")
    _atomic_write_csv(df, path)
    _mark_need_pc_backup(f"{path.name} 삭제")

# -----------------------------
# ZIP 백업(PC 다운로드) / ZIP 복원(업로드)
# -----------------------------
def _build_data_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for arcname, p in ALL_DATA_FILES:
            if p.exists():
                z.write(p, arcname=arcname)
    return buf.getvalue()

def _restore_from_zip(zip_bytes: bytes) -> tuple[bool, str]:
    try:
        zbuf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(zbuf, "r") as z:
            names = z.namelist()
            wanted = {arcname: path for arcname, path in ALL_DATA_FILES}

            stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            for _, p in ALL_DATA_FILES:
                if p.exists():
                    _backup_file_if_exists(p, f"{p.stem}_before_zip_restore_{stamp}")

            restored = 0
            for n in names:
                fn = Path(n).name
                if fn in wanted:
                    dest = wanted[fn]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    restored += 1

        if restored == 0:
            return False, "ZIP 안에 복원 대상 CSV(menu_index/base_menu/change_menu/delivery)가 없습니다."
        _mark_need_pc_backup("ZIP 복원 후(새 상태) PC 백업 권장")
        return True, f"ZIP 복원 완료 ({restored}개 파일)"
    except Exception as e:
        return False, f"ZIP 복원 실패: {e}"

# -----------------------------
# 이미지(Data URI)
# -----------------------------
def _data_uri(path: Path | None) -> str | None:
    if path is None or (not path.exists()):
        return None
    b = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(b).decode("utf-8")

def _find_assoc_logo() -> Path | None:
    return _first_exists(ASSOC_LOGO_ROOT, ASSOC_LOGO_DATA)

def _find_moms_logo() -> tuple[str | None, bool]:
    brand = _first_exists(MOMS_BRAND_ROOT, MOMS_BRAND_DATA)
    if brand:
        return _data_uri(brand), True
    logo = _first_exists(MOMS_LOGO_ROOT, MOMS_LOGO_DATA)
    if logo:
        return _data_uri(logo), False
    extracted = _first_exists(EXTRACTED_LOGO_PATH)
    if extracted:
        return _data_uri(extracted), False
    return None, False

# -----------------------------
# 메뉴 인덱스
# -----------------------------
def _read_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    try:
        df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8")

    df.columns = [re.sub(r"^\ufeff", "", _safe_str(c)).strip() for c in df.columns]

    if "name" not in df.columns and "menu" in df.columns:
        df = df.rename(columns={"menu": "name"})

    if "name" not in df.columns:
        if len(df.columns) == 1:
            df = df.rename(columns={df.columns[0]: "name"})
        else:
            return []

    items = [_safe_str(x) for x in df["name"].fillna("").tolist()]
    items = _unique_sorted(items)
    return items

def _write_menu_index(items: list[str]) -> None:
    items = _unique_sorted(items)
    _backup_file_if_exists(MENU_INDEX_PATH, "menu_index_backup")
    _atomic_write_csv(pd.DataFrame({"name": items}), MENU_INDEX_PATH)
    _mark_need_pc_backup("menu_index.csv 저장")

# -----------------------------
# (선택) 포스터 사진에서 M 로고 자동 추출
# -----------------------------
def _ensure_extracted_logo_if_needed() -> None:
    brand = _first_exists(MOMS_BRAND_ROOT, MOMS_BRAND_DATA)
    logo = _first_exists(MOMS_LOGO_ROOT, MOMS_LOGO_DATA)
    if brand or logo:
        return
    if EXTRACTED_LOGO_PATH.exists():
        return
    src = _first_exists(POSTER_SRC_ROOT, POSTER_SRC_DATA)
    if src is None:
        return
    try:
        from PIL import Image, ImageOps

        img = Image.open(src).convert("RGB")
        w, h = img.size
        crop = img.crop((0, 0, int(w * 0.32), int(h * 0.32)))
        crop = ImageOps.autocontrast(crop)

        gray = crop.convert("L")
        bw = gray.point(lambda p: 255 if p < 230 else 0, mode="1")
        bbox = bw.getbbox()

        if bbox:
            x0, y0, x1, y1 = bbox
            pad = 14
            x0 = max(0, x0 - pad)
            y0 = max(0, y0 - pad)
            x1 = min(crop.size[0], x1 + pad)
            y1 = min(crop.size[1], y1 + pad)
            logo_img = crop.crop((x0, y0, x1, y1))
        else:
            logo_img = crop.crop((0, 0, int(crop.size[0] * 0.70), int(crop.size[1] * 0.70)))

        logo_img = logo_img.resize((420, int(420 * logo_img.size[1] / max(1, logo_img.size[0]))))
        logo_img.save(EXTRACTED_LOGO_PATH, format="PNG", optimize=True)
    except Exception:
        return

# -----------------------------
# 달력 데이터
# -----------------------------
def _get_day_record_map(y: int, m: int) -> dict[int, dict[str, str]]:
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    prefix = f"{y}-{m:02d}-"
    base = base[base["date"].str.startswith(prefix)].copy()
    change = change[change["date"].str.startswith(prefix)].copy()
    delivery = delivery[delivery["date"].str.startswith(prefix)].copy()

    out: dict[int, dict[str, str]] = {}

    for _, r in base.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) < 2:
            continue
        try:
            d = int(ds[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["base"] = _safe_str(r.get("base_menu"))

    for _, r in change.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) < 2:
            continue
        try:
            d = int(ds[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["change"] = _safe_str(r.get("change_menu"))

    for _, r in delivery.iterrows():
        ds = _safe_str(r.get("date"))
        if len(ds) < 2:
            continue
        try:
            d = int(ds[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        v = _safe_str(r.get("delivery")).upper()
        out[d]["delivery"] = "N" if v == "N" else "Y"

    return out

# -----------------------------
# 날짜 선택 UI: 월~금 달력 버튼
# -----------------------------
def _weekday_calendar_picker(y: int, m: int, selected: date) -> date:
    cal = calendar.Calendar(firstweekday=0)
    weeks7 = cal.monthdayscalendar(y, m)

    rows5: list[list[int]] = []
    for wk in weeks7:
        wd = wk[:5]
        if all(d == 0 for d in wd):
            continue
        rows5.append(wd)

    st.markdown("**📅 날짜 선택(평일만)**")
    sel_day = selected.day if (selected.year == y and selected.month == m) else None

    hcols = st.columns(5)
    for i, w in enumerate(WEEKDAY_KR_WD):
        hcols[i].markdown(f"<div style='text-align:center;font-weight:900'>{w}</div>", unsafe_allow_html=True)

    for r, wk in enumerate(rows5):
        cols = st.columns(5)
        for c, day in enumerate(wk):
            if day == 0:
                cols[c].button(" ", key=f"blank_{y}_{m}_{r}_{c}", disabled=True, use_container_width=True)
                continue
            dt = date(y, m, day)
            label = f"{day:02d}"
            if sel_day == day:
                label = f"✅ {label}"

            # ✅ 한 번 클릭하면 즉시 ✅ 표시
            if cols[c].button(label, key=f"d_{y}_{m}_{day}", use_container_width=True):
                st.session_state["selected_date"] = dt
                st.rerun()

    return st.session_state.get("selected_date", selected)

# -----------------------------
# 포스터 HTML
# -----------------------------
def _build_weekday_poster_html(
    y: int,
    m: int,
    title1: str,
    title2: str,
    title3: str,
    right_label: str,
    moms_uri: str | None,
    moms_is_brand: bool,
    assoc_uri: str | None,
    contact_text: str,
) -> str:
    data_map = _get_day_record_map(y, m)

    cal = calendar.Calendar(firstweekday=0)
    weeks7 = cal.monthdayscalendar(y, m)
    rows5: list[list[int]] = []
    for wk in weeks7:
        wd = wk[:5]
        if all(d == 0 for d in wd):
            continue
        rows5.append(wd)

    row_count = len(rows5)
    cell_h = 122 if row_count <= 4 else 104

    if moms_uri and moms_is_brand:
        moms_box_html = f'<img src="{moms_uri}" class="moms-brand-banner" alt="MOMS"/>'
    else:
        logo_html = f'<img src="{moms_uri}" class="moms-logo-img" alt="M"/>' if moms_uri else '<div class="moms-logo-fallback">M</div>'
        moms_box_html = f"""
        <div class="brand-box">
          {logo_html}
          <div class="brand-text"><div class="moms">MOMS</div></div>
        </div>
        """

    assoc_html = f'<img src="{assoc_uri}" class="assoc-logo-img" alt="협회 로고"/>' if assoc_uri else ""

    css = f"""
    <style>
      @page {{ size: A4 landscape; margin: 6mm; }}
      html, body {{ height: 100%; }}
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
        color: #0f172a;
        background: #ffffff;
      }}
      .sheet {{ height: 100%; overflow: hidden; }}
      @media print {{
        * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        table, tr, td, th {{ page-break-inside: avoid !important; break-inside: avoid !important; }}
      }}
      .sheet {{ width: 100%; padding: 8px 10px; box-sizing: border-box; }}

      .header {{
        display:grid;
        grid-template-columns: 220px 1fr 320px;
        gap: 10px;
        align-items: center;
        margin-bottom: 8px;
      }}

      .brand-box {{
        height: 98px;
        border-radius: 20px;
        background: #ffffff;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:flex-start;
        gap: 14px;
        padding: 14px 16px;
        box-sizing: border-box;
      }}
      .moms-logo-img {{
        height: 64px;
        width: auto;
        object-fit: contain;
        border-radius: 14px;
      }}
      .moms-logo-fallback {{
        height: 64px; width: 64px;
        border-radius: 16px;
        display:flex; align-items:center; justify-content:center;
        font-weight: 1000; font-size: 44px;
        border: 2px solid rgba(15,23,42,0.18);
        background: rgba(0,0,0,0.03);
      }}
      .brand-text {{ line-height: 1.0; font-weight: 1000; letter-spacing: -0.3px; }}
      .brand-text .moms {{ font-size: 30px; }}

      .moms-brand-banner {{
        height: 98px;
        width: 100%;
        object-fit: contain;
        border-radius: 20px;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        background: #fff;
      }}

      .title {{
        text-align: center;
        line-height: 1.03;
      }}
      .title .t1 {{
        font-size: 34px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 0;
        background: linear-gradient(90deg, #0ea5e9, #22c55e);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }}
      .title .t2 {{
        font-size: 34px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 6px 0 0 0;
        background: linear-gradient(90deg, #8b5cf6, #ec4899);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
      }}
      .title .t3 {{
        font-size: 20px;
        font-weight: 900;
        letter-spacing: -0.6px;
        margin: 6px 0 0 0;
        color: rgba(15,23,42,0.70);
      }}

      .right-box {{
        height: 98px;
        border-radius: 20px;
        background: #ffffff;
        border: 2px solid rgba(15,23,42,0.28);
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        gap: 10px;
        padding: 12px 14px;
        box-sizing: border-box;
      }}
      .assoc-logo-img {{
        height: 66px;
        width: auto;
        object-fit: contain;
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
        transform: translateZ(0);
      }}
      .right-box .label {{ font-size: 28px; font-weight: 1000; letter-spacing: -0.3px; text-align:center; }}
      .contact {{
        margin-top: 6px;
        font-size: 15px;
        font-weight: 900;
        opacity: 0.90;
        text-align: center;
        white-space: nowrap;
        word-break: keep-all;
      }}

      table {{
        border-collapse: separate;
        border-spacing: 10px 10px;
        width: 100%;
        table-layout: fixed;
      }}
      th {{ font-size: 15px; font-weight: 1000; text-align:center; padding: 0; }}
      td {{
        height: {cell_h}px;
        vertical-align: top;
        background: #ffffff;
        border: 2.4px solid rgba(15,23,42,0.32);
        border-radius: 14px;
        box-shadow: 0 7px 12px rgba(15,23,42,0.06);
        padding: 10px 12px;
        box-sizing: border-box;
        overflow: hidden;
        position: relative;
      }}
      .empty {{ background: #ffffff; border: 2.4px dashed rgba(15,23,42,0.22); box-shadow: none; }}

      .has-change {{ border-color: rgba(184, 134, 11, 0.55); background: rgba(255, 250, 235, 0.96); }}
      .no-delivery {{ border-color: rgba(176,0,32,0.46); background: rgba(255, 240, 244, 0.96); }}
      .both {{ border-color: rgba(125, 60, 152, 0.56); background: rgba(248, 244, 255, 0.96); }}

      .corner {{
        position: absolute;
        top: 6px;
        right: 8px;
        width: 26px;
        height: 26px;
        border-radius: 999px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        font-weight: 1000;
        border: 1px solid rgba(15,23,42,0.25);
        box-shadow: 0 2px 4px rgba(15,23,42,0.10);
      }}
      .corner-change {{
        background: rgba(255, 230, 180, 0.95);
        color: rgba(120, 70, 0, 1.0);
      }}
      .corner-nodelivery {{
        background: rgba(255, 200, 210, 0.95);
        color: rgba(140, 0, 20, 1.0);
      }}
      .corner-both {{
        background: rgba(220, 210, 255, 0.95);
        color: rgba(70, 35, 120, 1.0);
      }}

      .cell-top {{ display:flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding-right: 28px; }}
      .datechip {{ display:inline-flex; align-items:baseline; gap: 8px; font-weight: 1000; font-size: 16px; letter-spacing: -0.3px; }}
      .dow {{ font-size: 12.5px; font-weight: 900; opacity: 0.72; }}
      .badge-nodelivery {{
        font-size: 12px; font-weight: 1000; color: #b00020;
        background: rgba(255, 235, 238, 0.98);
        border: 1px solid rgba(176,0,32,0.34);
        padding: 4px 10px; border-radius: 999px; letter-spacing: -0.2px;
      }}

      .menu {{ font-size: 16px; line-height: 1.18; letter-spacing: -0.35px; word-break: keep-all; }}
      .base {{ font-weight: 1000; }}
      .change {{ margin-top: 10px; font-weight: 1000; color: #c40000; }}
      .change .label {{
        display:inline-block; font-size: 12px; font-weight: 1000;
        padding: 2px 10px; border-radius: 999px;
        background: rgba(196,0,0,0.10);
        border: 1px solid rgba(196,0,0,0.34);
        margin-right: 8px;
      }}
    </style>
    """

    thead = "<tr>" + "".join([f"<th>{w}</th>" for w in WEEKDAY_KR_WD]) + "</tr>"

    body_rows = []
    for wk in rows5:
        tds = []
        for day in wk:
            if day == 0:
                tds.append('<td class="empty"></td>')
                continue

            dt = date(y, m, day)
            dow = WEEKDAY_FULL[dt.weekday()]

            rec = data_map.get(day, {})
            base_v = html.escape(_safe_str(rec.get("base", "")))
            change_v = html.escape(_safe_str(rec.get("change", "")))
            delivery_v = _safe_str(rec.get("delivery", "Y")).upper()

            is_nodelivery = (delivery_v == "N")
            has_change = bool(change_v)

            cls = ""
            corner = ""
            if has_change and is_nodelivery:
                cls = "both"
                corner = '<div class="corner corner-both">✔</div>'
            elif has_change:
                cls = "has-change"
                corner = '<div class="corner corner-change">✔</div>'
            elif is_nodelivery:
                cls = "no-delivery"
                corner = '<div class="corner corner-nodelivery">✖</div>'

            badge = '<span class="badge-nodelivery">배달불요</span>' if is_nodelivery else ""
            base_line = f'<div class="menu base">{base_v}</div>' if base_v else '<div class="menu base">&nbsp;</div>'
            change_block = f'<div class="menu change"><span class="label">변경</span>{change_v}</div>' if change_v else ""

            tds.append(f"""
            <td class="{cls}">
              {corner}
              <div class="cell-top">
                <div class="datechip">{day:02d}<span class="dow">({dow})</span></div>
                {badge}
              </div>
              {base_line}
              {change_block}
            </td>
            """)
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    return f"""
    <!doctype html>
    <html lang="ko">
      <head><meta charset="utf-8"/>{css}</head>
      <body>
        <div class="sheet">
          <div class="header">
            <div>{moms_box_html}</div>

            <div class="title">
              <p class="t1">{html.escape(title1)}</p>
              <p class="t2">{html.escape(title2)}</p>
              <p class="t3">{html.escape(title3)}</p>
            </div>

            <div class="right-box">
              {assoc_html}
              <div>
                <div class="label">{html.escape(right_label)}</div>
                <div class="contact">{html.escape(contact_text)}</div>
              </div>
            </div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>{''.join(body_rows)}</tbody>
          </table>
        </div>
      </body>
    </html>
    """

# -----------------------------
# 시작 시: 정식 로고 없을 때만 추출 시도
# -----------------------------
_ensure_extracted_logo_if_needed()

# -----------------------------
# 사이드바: PC 백업(다운로드/업로드)
# -----------------------------
if "needs_pc_backup" not in st.session_state:
    st.session_state["needs_pc_backup"] = False
    st.session_state["needs_pc_backup_reason"] = ""
    st.session_state["needs_pc_backup_ts"] = ""

if "zip_nonce" not in st.session_state:
    st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

with st.sidebar:
    st.markdown("## 💾 PC 백업(필수)")
    st.caption("Streamlit Cloud는 재시작 시 서버파일이 사라질 수 있어, **ZIP을 PC로 내려받아 보관**하는 방식이 안전합니다.")

    if st.session_state.get("needs_pc_backup", False):
        reason = st.session_state.get("needs_pc_backup_reason", "")
        ts = st.session_state.get("needs_pc_backup_ts", "")
        st.warning(f"방금 변경됨: {reason}\n\n➡️ **지금 ZIP 백업을 PC로 다운로드**하세요.\n\n(시간: {ts})")

    zip_bytes = _build_data_zip_bytes()
    zip_name = f"moms_data_backup_{st.session_state['zip_nonce']}.zip"
    st.download_button(
        "⬇️ 데이터 ZIP 백업 다운로드",
        data=zip_bytes,
        file_name=zip_name,
        mime="application/zip",
        use_container_width=True,
    )

    c_done1, c_done2 = st.columns(2)
    with c_done1:
        if st.button("✅ 다운로드 완료", use_container_width=True):
            st.session_state["needs_pc_backup"] = False
            st.session_state["needs_pc_backup_reason"] = ""
            st.session_state["needs_pc_backup_ts"] = ""
    with c_done2:
        if st.button("🔁 새 ZIP 갱신", use_container_width=True):
            st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

    st.divider()
    st.markdown("### ♻️ ZIP 업로드로 복원")
    confirm = st.checkbox("⚠️ 업로드한 ZIP으로 현재 데이터를 덮어쓰는 것을 이해했습니다.", value=False)
    up = st.file_uploader("ZIP 파일 선택", type=["zip"])
    if up is not None:
        if not confirm:
            st.error("복원 전 확인 체크가 필요합니다. (실수로 데이터 덮어쓰기 방지)")
        else:
            ok, msg = _restore_from_zip(up.read())
            if ok:
                st.success(msg)
                st.session_state["zip_nonce"] = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.caption(f"서버 저장 경로(참고): {DATA_DIR}")

# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption(f"저장 경로: {DATA_DIR}")

colL, colR = st.columns([1.15, 1.0], vertical_alignment="top")

with colL:
    st.subheader("1) 메뉴 인덱스 관리 (가나다 순 자동 정렬)")
    idx_items = _read_menu_index()

    c1, c2 = st.columns([1, 1])
    with c1:
        new_item = st.text_input("메뉴 추가", placeholder="예: 소고기미역국")
        if st.button("➕ 인덱스에 추가", use_container_width=True):
            x = _safe_str(new_item)
            if x:
                idx_items.append(x)
                _write_menu_index(idx_items)
                st.success("저장 완료(가나다 정렬) — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with c2:
        del_item = st.selectbox("삭제할 메뉴 선택", ["(선택)"] + idx_items)
        if st.button("🗑️ 선택 메뉴 삭제", use_container_width=True):
            if del_item != "(선택)":
                idx_items = [x for x in idx_items if x != del_item]
                _write_menu_index(idx_items)
                st.success("삭제 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()

    st.divider()
    st.subheader("2) 월 선택")

    today = date.today()
    y = st.selectbox("연도", list(range(today.year - 2, today.year + 4)), index=2)
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = date(y, m, 1)

    sd: date = st.session_state["selected_date"]
    if sd.year != y or sd.month != m:
        st.session_state["selected_date"] = date(y, m, 1)

    dsel = _weekday_calendar_picker(y, m, st.session_state["selected_date"])
    key = dsel.isoformat()

    st.divider()
    st.subheader("3) 선택 날짜 입력")

    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    cur_base = _safe_str(base_df.loc[base_df["date"] == key, "base_menu"].iloc[0]) if (base_df["date"] == key).any() else ""
    cur_change = _safe_str(change_df.loc[change_df["date"] == key, "change_menu"].iloc[0]) if (change_df["date"] == key).any() else ""
    cur_deliv = _safe_str(deliv_df.loc[deliv_df["date"] == key, "delivery"].iloc[0]).upper() if (deliv_df["date"] == key).any() else "Y"
    if cur_deliv not in ["Y", "N"]:
        cur_deliv = "Y"

    # ✅ 저장 후 초기화는 "다음 rerun 시작 시(=위젯 생성 전)"에만 처리
    if st.session_state.get("active_date_key") != key:
        st.session_state["active_date_key"] = key
        # 날짜가 바뀌면 해당 날짜 저장값으로 보여주기
        st.session_state["base_pick"] = "(직접입력)"
        st.session_state["base_text"] = cur_base
        st.session_state["change_pick"] = "(없음)"
        st.session_state["change_text"] = cur_change

        st.session_state["clear_base_after_save"] = False
        st.session_state["clear_change_after_save"] = False

    if st.session_state.get("clear_base_after_save", False):
        st.session_state["base_pick"] = "(직접입력)"
        st.session_state["base_text"] = ""
        st.session_state["clear_base_after_save"] = False

    if st.session_state.get("clear_change_after_save", False):
        st.session_state["change_pick"] = "(없음)"
        st.session_state["change_text"] = ""
        st.session_state["clear_change_after_save"] = False

    st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_FULL[dsel.weekday()]})")

    # ---- 기본메뉴 ----
    st.markdown("**기본메뉴**")
    # ✅ selectbox 자체에서 타이핑하면 자동 검색됨(별도 검색창 없음)
    base_pick = st.selectbox(
        "기본메뉴(인덱스)",
        ["(직접입력)"] + idx_items,
        key="base_pick",
    )
    if base_pick != "(직접입력)":
        st.session_state["base_text"] = base_pick

    st.text_input("기본메뉴(입력란)", key="base_text")

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 기본메뉴 저장", use_container_width=True):
            v = _safe_str(st.session_state.get("base_text", ""))
            if not v:
                st.warning("기본메뉴가 비어 있습니다.")
            else:
                _upsert_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel, "base_menu", v)
                # ✅ 다음 rerun에서 입력/선택창 비우기
                st.session_state["clear_base_after_save"] = True
                st.success("기본메뉴 저장 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()
    with b2:
        if st.button("🧹 기본메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel)
            st.session_state["clear_base_after_save"] = True
            st.success("기본메뉴 삭제 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
            st.rerun()

    # ---- 변경메뉴 ----
    st.markdown("**변경메뉴(있으면 입력)**")
    change_pick = st.selectbox(
        "변경메뉴(인덱스)",
        ["(없음)"] + idx_items,
        key="change_pick",
    )
    if change_pick != "(없음)":
        st.session_state["change_text"] = change_pick

    st.text_input("변경메뉴(입력란)", key="change_text")

    c3, c4 = st.columns([1, 1])
    with c3:
        if st.button("💾 변경메뉴 저장", use_container_width=True):
            v = _safe_str(st.session_state.get("change_text", ""))
            if not v or v == "(없음)":
                st.warning("변경메뉴가 비어 있습니다. (없음)으로 두려면 삭제를 사용하세요.")
            else:
                _upsert_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel, "change_menu", v)
                st.session_state["clear_change_after_save"] = True
                st.success("변경메뉴 저장 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
                st.rerun()
    with c4:
        if st.button("🧹 변경메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel)
            st.session_state["clear_change_after_save"] = True
            st.success("변경메뉴 삭제 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
            st.rerun()

    # ---- 배달 여부 ----
    st.markdown("**배달 여부**")
    deliv_choice = st.radio(
        "배달",
        ["배달(Y)", "배달불요(N)"],
        index=0 if cur_deliv == "Y" else 1,
        horizontal=True
    )
    if st.button("💾 배달여부 저장", use_container_width=True):
        _upsert_by_date(
            DELIVERY_PATH,
            ["date", "delivery"],
            dsel,
            "delivery",
            "Y" if deliv_choice.startswith("배달(Y)") else "N",
        )
        st.success("배달여부 저장 완료 — 좌측에서 ZIP 백업을 다운로드하세요.")
        st.rerun()

with colR:
    st.subheader("4) 포스터(출력용 1장) 미리보기")

    right_label = st.text_input("우측 상단 표기", value="동약협회")
    headcount = st.number_input("인원수", min_value=1, max_value=999, value=1, step=1)
    contact = st.text_input("연락처", value="010-7101-5871")

    title1 = f"맘스락 {m:02d}월"
    title2 = "식단(배달) 변경"
    title3 = f"(인원:{int(headcount)}인)"
    contact_text = f"연락처: {contact}"

    moms_uri, moms_is_brand = _find_moms_logo()
    assoc_uri = _data_uri(_find_assoc_logo())

    poster_html = _build_weekday_poster_html(
        y=y,
        m=m,
        title1=title1,
        title2=title2,
        title3=title3,
        right_label=_safe_str(right_label) or "동약협회",
        moms_uri=moms_uri,
        moms_is_brand=moms_is_brand,
        assoc_uri=assoc_uri,
        contact_text=contact_text,
    )

    components.html(poster_html, height=780, scrolling=True)

    st.divider()
    st.subheader("5) 업체 전달용 파일 만들기")

    dl_name = _safe_filename(f"{title1}_{title2}_{title3}_{right_label}") + ".html"
    st.download_button(
        label=f"⬇️ HTML 다운로드 ({dl_name})",
        data=poster_html.encode("utf-8"),
        file_name=dl_name,
        mime="text/html",
        use_container_width=True,
    )

