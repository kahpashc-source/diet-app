# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, timedelta
import calendar
import io
import zipfile
import unicodedata
import base64

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

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N) -> Y만 저장(배달 필요)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# -----------------------------
# 유틸
# -----------------------------
def _today() -> date:
    return date.today()

def _iso(d: date) -> str:
    return d.isoformat()

def _parse_iso(s: str) -> date:
    return date.fromisoformat(s)

def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)

def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8-sig") -> None:
    _atomic_write_bytes(path, text.encode(encoding))

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns].astype(str).fillna("")

def _write_csv(path: Path, df: pd.DataFrame) -> None:
    _atomic_write_text(path, df.to_csv(index=False), encoding="utf-8-sig")

def _ensure_menu_index_sorted(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["name"] = df["name"].map(_nfc)
    df = df[df["name"] != ""]
    df = df.drop_duplicates(subset=["name"])
    df = df.sort_values("name", kind="mergesort").reset_index(drop=True)
    return df

def load_all():
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])
    idx = _read_csv(MENU_INDEX_PATH, ["name"])
    idx = _ensure_menu_index_sorted(idx)
    return base, change, delivery, idx

def upsert_by_date(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    df = df.copy()
    ds = _iso(d)
    value = _nfc(value)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, col: value}])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df

def delete_by_date_if_empty(df: pd.DataFrame, d: date, col: str) -> pd.DataFrame:
    df = df.copy()
    ds = _iso(d)
    hit = df[df["date"] == ds]
    if hit.empty:
        return df
    v = _nfc(hit.iloc[0][col])
    if v == "":
        df = df[df["date"] != ds].reset_index(drop=True)
    return df

def set_delivery(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    """
    delivery.csv는 '배달 필요(Y)'만 저장.
    체크 해제(배달불요)면 해당 날짜 레코드 삭제.
    """
    df = df.copy()
    ds = _iso(d)
    yn = "Y" if yn == "Y" else "N"
    if yn == "N":
        df = df[df["date"] != ds].reset_index(drop=True)
        return df
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "delivery"] = "Y"
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "delivery": "Y"}])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df

def get_value(df: pd.DataFrame, d: date, col: str) -> str:
    ds = _iso(d)
    hit = df[df["date"] == ds]
    if hit.empty:
        return ""
    return _nfc(hit.iloc[0][col])

def get_delivery_flag(df: pd.DataFrame, d: date) -> str:
    ds = _iso(d)
    return "Y" if not df[df["date"] == ds].empty else "N"

# -----------------------------
# ZIP 백업/복원 (DATA_DIR로 강제 덮어쓰기)
# -----------------------------
TARGET_FILES = {
    "base_menu.csv": BASE_MENU_PATH,
    "change_menu.csv": CHANGE_MENU_PATH,
    "delivery.csv": DELIVERY_PATH,
    "menu_index.csv": MENU_INDEX_PATH,
}

def make_backup_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, path in TARGET_FILES.items():
            if path.exists():
                zf.writestr(fname, path.read_bytes())
    return buf.getvalue()

def restore_from_zip(uploaded) -> tuple[bool, str]:
    if uploaded is None:
        return False, "ZIP 파일이 없습니다."
    raw = uploaded.getvalue()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as e:
        return False, f"ZIP 읽기 오류: {e}"

    found: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        name_only = Path(info.filename).name
        if name_only in TARGET_FILES:
            found[name_only] = info

    missing = sorted(list(set(TARGET_FILES.keys()) - set(found.keys())))
    if missing:
        return False, "ZIP 안에 필요한 파일이 없습니다: " + ", ".join(missing)

    for fname, info in found.items():
        _atomic_write_bytes(TARGET_FILES[fname], zf.read(info))

    return True, "복원 완료: data 폴더의 CSV를 강제로 교체했습니다."

# -----------------------------
# 이미지(base64 data uri)
# -----------------------------
def file_to_data_uri(uploaded) -> str:
    if uploaded is None:
        return ""
    b = uploaded.getvalue()
    mime = uploaded.type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(b).decode('utf-8')}"

# -----------------------------
# 세션 상태
# -----------------------------
if "ym" not in st.session_state:
    t = _today()
    st.session_state.ym = (t.year, t.month)

if "last_clicked" not in st.session_state:
    st.session_state.last_clicked = None  # iso date string

# -----------------------------
# 상단
# -----------------------------
st.title("맘스락 식단 변경 프로그램")
base_df, change_df, delivery_df, idx_df = load_all()

# -----------------------------
# 사이드바
# -----------------------------
with st.sidebar:
    st.header("1) 메뉴 인덱스 관리")
    st.caption("가나다 순 자동 정렬")

    new_name = st.text_input("메뉴 추가", placeholder="예: 소고기무국")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("추가", use_container_width=True):
            n = _nfc(new_name)
            if n:
                idx_df2 = pd.concat([idx_df, pd.DataFrame([{"name": n}])], ignore_index=True)
                idx_df2 = _ensure_menu_index_sorted(idx_df2)
                _write_csv(MENU_INDEX_PATH, idx_df2)
                st.rerun()
    with c2:
        if st.button("전체 정렬 저장", use_container_width=True):
            idx_df2 = _ensure_menu_index_sorted(idx_df)
            _write_csv(MENU_INDEX_PATH, idx_df2)
            st.rerun()

    if not idx_df.empty:
        del_target = st.selectbox("삭제할 메뉴", ["(선택)"] + idx_df["name"].tolist())
        if st.button("선택 삭제", use_container_width=True):
            if del_target != "(선택)":
                idx_df2 = idx_df[idx_df["name"] != del_target].reset_index(drop=True)
                _write_csv(MENU_INDEX_PATH, idx_df2)
                st.rerun()

    st.divider()
    st.header("2) 백업/복원(ZIP)")
    st.download_button(
        "📦 데이터 ZIP 다운로드",
        data=make_backup_zip_bytes(),
        file_name="diet_data_backup.zip",
        mime="application/zip",
        use_container_width=True,
    )
    up = st.file_uploader("ZIP 업로드(복원)", type=["zip"])
    if st.button("ZIP에서 복원(강제 덮어쓰기)", type="primary", use_container_width=True):
        ok, msg = restore_from_zip(up)
        st.success(msg) if ok else st.error(msg)
        st.rerun()

    st.divider()
    st.header("3) 포스터 로고")
    st.caption("포스터 상단 좌/우 로고를 업로드하면 그림에 반영됩니다.")
    moms_logo_up = st.file_uploader("왼쪽(MOMS) 로고 업로드", type=["png", "jpg", "jpeg", "webp"], key="momslogo")
    kapma_logo_up = st.file_uploader("오른쪽(동약협회) 로고 업로드", type=["png", "jpg", "jpeg", "webp"], key="kapmalogo")

moms_logo_uri = file_to_data_uri(st.session_state.get("momslogo"))
kapma_logo_uri = file_to_data_uri(st.session_state.get("kapmalogo"))

# -----------------------------
# 월 선택
# -----------------------------
st.subheader("월 선택")
y, m = st.session_state.ym
years = list(range(2024, 2036))
months = list(range(1, 13))

cY, cM, cNow = st.columns([1, 1, 1])
with cY:
    y = st.selectbox("년도", years, index=years.index(y) if y in years else 0)
with cM:
    m = st.selectbox("월", months, index=months.index(m) if m in months else 0)
with cNow:
    if st.button("이번 달", use_container_width=True):
        t = _today()
        st.session_state.ym = (t.year, t.month)
        st.rerun()
st.session_state.ym = (y, m)

# -----------------------------
# 달력(입력용)
# - 기본: 흰색
# - 변경: 노랑 계열 + "변경" 뱃지
# - 배달불요: 핑크 계열 + "배달불요" 뱃지
# -----------------------------
st.caption("※ 날짜 클릭 → 입력창(저장 시 달력으로 복귀)")

def cell_label_input(d: date) -> str:
    base = get_value(base_df, d, "base_menu")
    change = get_value(change_df, d, "change_menu")
    delivery = get_delivery_flag(delivery_df, d)

    # 버튼 텍스트는 간결하게(칸 안 잘림 방지)
    parts = [f"{d.day:02d}"]
    if delivery != "Y":
        parts.append("배달불요")
    if change:
        parts.append(f"변경:{change}")
    else:
        if base:
            parts.append(base)
    return "\n".join(parts)

def open_editor(d: date):
    st.session_state.last_clicked = _iso(d)

weekdays = ["월", "화", "수", "목", "금", "토", "일"]
hcols = st.columns(7)
for i, w in enumerate(weekdays):
    hcols[i].markdown(f"**{w}**")

cal = calendar.Calendar(firstweekday=0)
month_days = list(cal.itermonthdates(y, m))
if len(month_days) < 42:
    last = month_days[-1]
    month_days = month_days + [last + timedelta(days=i) for i in range(1, 42 - len(month_days) + 1)]
else:
    month_days = month_days[:42]

# ✅ 버튼별 클래스 적용을 위해 HTML+JS로 스타일 주입 (Streamlit 버튼 자체는 클래스 부여가 어려움)
# - workaround: 각 버튼 key를 이용해 data-testid 요소를 찾아 근처 button에 스타일을 적용
def inject_calendar_style(keys_changed: set[str], keys_nodlv: set[str]):
    # JS에서 Streamlit이 만든 버튼들을 찾아 스타일을 덧씌웁니다.
    js = f"""
    <script>
    const changed = new Set({list(keys_changed)});
    const nodlv = new Set({list(keys_nodlv)});

    function apply() {{
      const all = window.parent.document.querySelectorAll('button[kind="secondary"]');
      all.forEach(btn => {{
        const k = btn.getAttribute("data-testid") || "";
      }});
      // Streamlit은 버튼에 key를 직접 안 박습니다.
      // 따라서, 라벨 텍스트의 '변경:' / '배달불요'로 2차 판별해 적용합니다(안정적).
      const buttons = window.parent.document.querySelectorAll('button');
      buttons.forEach(b => {{
        const t = (b.innerText || "").trim();
        if (!t) return;
        if (t.includes("배달불요")) {{
          b.style.background = "rgba(255, 235, 238, 1)";
          b.style.border = "2px solid rgba(216, 65, 90, 0.65)";
          b.style.borderRadius = "14px";
        }}
        if (t.includes("변경:") || t.includes("변경:") || t.includes("변경:")) {{
          b.style.background = "rgba(255, 248, 225, 1)";
          b.style.border = "2px solid rgba(222, 150, 35, 0.70)";
          b.style.borderRadius = "14px";
        }}
      }});
    }}
    setTimeout(apply, 50);
    setTimeout(apply, 250);
    </script>
    """
    components.html(js, height=0)

keys_changed, keys_nodlv = set(), set()

for row in range(6):
    cols = st.columns(7)
    for col in range(7):
        d = month_days[row * 7 + col]
        in_month = (d.month == m)
        disabled = not in_month
        label = cell_label_input(d) if in_month else " "

        # key 기록(포스터는 별도라 달력은 텍스트 기반 스타일링 사용)
        if in_month:
            if get_value(change_df, d, "change_menu"):
                keys_changed.add(f"daybtn-{y}-{m}-{row}-{col}")
            if get_delivery_flag(delivery_df, d) != "Y":
                keys_nodlv.add(f"daybtn-{y}-{m}-{row}-{col}")

        if cols[col].button(label, key=f"daybtn-{y}-{m}-{row}-{col}", disabled=disabled, use_container_width=True):
            if in_month:
                open_editor(d)

# 달력 색상 적용(텍스트 기반)
inject_calendar_style(keys_changed, keys_nodlv)

# -----------------------------
# 날짜 편집 Dialog
# -----------------------------
clicked_iso = st.session_state.last_clicked
if clicked_iso:
    clicked_date = _parse_iso(clicked_iso)

    @st.dialog("식단 입력(저장 후 달력으로 복귀)")
    def edit_dialog(d: date):
        base_df2, change_df2, delivery_df2, idx_df2 = load_all()

        st.write(f"📅 선택 날짜: **{d.year}-{d.month:02d}-{d.day:02d}**")

        current_base = get_value(base_df2, d, "base_menu")
        current_change = get_value(change_df2, d, "change_menu")
        current_delivery = get_delivery_flag(delivery_df2, d)

        delivery_ok = st.checkbox("배달 필요(체크 해제 시 배달불요)", value=(current_delivery == "Y"))

        st.divider()

        idx_list = idx_df2["name"].tolist() if not idx_df2.empty else []
        base_choices = ["(직접입력)"] + idx_list
        change_choices = ["(없음)"] + idx_list + ["(직접입력)"]

        st.markdown("**기본 메뉴**")
        base_mode = st.selectbox("기본 선택", base_choices, index=0, key="base_mode")
        base_text = st.text_input("기본(직접 입력)", value=current_base, key="base_text")
        if base_mode != "(직접입력)":
            base_text = base_mode

        st.markdown("**변경 메뉴**")
        change_mode = st.selectbox("변경 선택", change_choices, index=0, key="change_mode")
        change_text = st.text_input("변경(직접 입력)", value=current_change, key="change_text")
        if change_mode == "(없음)":
            change_text = ""
        elif change_mode != "(직접입력)":
            change_text = change_mode

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 저장", type="primary", use_container_width=True):
                base_df3 = upsert_by_date(base_df2, d, "base_menu", base_text)
                base_df3 = delete_by_date_if_empty(base_df3, d, "base_menu")

                change_df3 = upsert_by_date(change_df2, d, "change_menu", change_text)
                change_df3 = delete_by_date_if_empty(change_df3, d, "change_menu")

                delivery_df3 = set_delivery(delivery_df2, d, "Y" if delivery_ok else "N")

                _write_csv(BASE_MENU_PATH, base_df3)
                _write_csv(CHANGE_MENU_PATH, change_df3)
                _write_csv(DELIVERY_PATH, delivery_df3)

                st.session_state.last_clicked = None
                st.rerun()
        with c2:
            if st.button("닫기(저장 안함)", use_container_width=True):
                st.session_state.last_clicked = None
                st.rerun()

    edit_dialog(clicked_date)

# -----------------------------
# 포스터(1장) - 예시처럼 월~금만 / 색상 구분 / 로고 포함 / PNG 저장
# -----------------------------
st.divider()
st.header("포스터(출력용 1장) 미리보기 / PNG 저장")

def esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def build_weeks_mon_fri(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    days = list(cal.itermonthdates(year, month))
    weeks = [days[i:i+7] for i in range(0, len(days), 7)]
    rows = []
    for w in weeks:
        wk = w[:5]  # 월~금
        if not any(d.month == month for d in wk):
            continue
        rows.append(wk)
    return rows

wd_kr = ["월", "화", "수", "목", "금", "토", "일"]
rows = build_weeks_mon_fri(y, m)

poster_filename = f"맘스락_{y}_{m:02d}_식단변경.png"
title_html = f"맘스락 {m:02d}월<br/>식단 변경"

left_logo_html = (
    f'<img class="logo-img" src="{moms_logo_uri}" />'
    if moms_logo_uri else '<div class="logo-text"><b>MOMS</b></div>'
)
right_logo_html = (
    f'<img class="logo-img" src="{kapma_logo_uri}" />'
    if kapma_logo_uri else '<div class="logo-text"><b>동약협회</b></div>'
)

cells_html = ""
for wk in rows:
    cells_html += '<div class="row">'
    for d in wk:
        if d.month != m:
            cells_html += '<div class="cell empty"></div>'
            continue

        base = esc(get_value(base_df, d, "base_menu"))
        change = esc(get_value(change_df, d, "change_menu"))
        delivery = get_delivery_flag(delivery_df, d)

        cls = "cell"
        badges = []
        if delivery != "Y":
            cls += " nodlv"
            badges.append('<span class="badge nodlv">배달불요</span>')
        if change:
            cls += " changed"
            badges.append('<span class="badge changed">변경</span>')

        wd = wd_kr[d.weekday()]
        # 메뉴 표시: 기본은 검정 / 변경은 빨강 굵게
        menu_main = base
        change_block = f'<div class="change">{change}</div>' if change else ""

        cells_html += f"""
        <div class="{cls}">
          <div class="top">
            <div class="day">{d.day:02d} <span class="wd">({wd})</span></div>
            <div class="badges">{''.join(badges)}</div>
          </div>
          <div class="menu">{menu_main}</div>
          {change_block}
        </div>
        """
    cells_html += "</div>"

poster_html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{
    margin:0; padding:0; background:#ffffff;
    font-family: "Noto Sans KR","Malgun Gothic",system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  }}
  .wrap {{
    width: 980px;
    padding: 18px 18px 14px 18px;
    box-sizing: border-box;
    background: #fff;
  }}
  .btnbar {{
    display:flex; gap:10px; align-items:center;
    margin: 0 0 12px 0;
  }}
  button {{
    border: 0; border-radius: 12px;
    padding: 10px 14px;
    font-weight: 900;
    cursor: pointer;
    background:#111; color:#fff;
  }}
  #downloadLink {{
    display:none;
    font-weight: 900;
    text-decoration: none;
    padding: 10px 14px;
    border-radius: 12px;
    background: #1f7a1f;
    color:#fff;
  }}
  .hint {{
    font-size: 12px;
    color: rgba(0,0,0,0.55);
  }}

  .header {{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom: 10px;
  }}
  .logo-box {{
    width: 250px; height: 86px;
    border: 1.5px solid rgba(0,0,0,0.15);
    border-radius: 18px;
    display:flex; align-items:center; justify-content:center;
    overflow:hidden;
    background:#fff;
  }}
  .logo-img {{ max-width: 92%; max-height: 92%; object-fit: contain; }}
  .logo-text {{ font-size: 30px; color:#111; }}
  .title {{
    flex: 1;
    text-align:center;
    font-weight: 950;
    font-size: 40px;
    line-height: 1.05;
    color:#111;
  }}

  .dow {{
    display:grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin: 12px 0 8px 0;
  }}
  .dow div {{
    text-align:center;
    font-weight: 900;
    color:#111;
  }}

  .grid {{
    display:flex;
    flex-direction:column;
    gap: 12px;
  }}
  .row {{
    display:grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
  }}
  .cell {{
    border: 1.8px solid rgba(0,0,0,0.24);
    border-radius: 18px;
    padding: 12px 12px 10px 12px;
    min-height: 108px;
    box-sizing: border-box;
    background:#fff;
  }}
  .cell.empty {{
    border: 2px dashed rgba(0,0,0,0.18);
    background: #fff;
  }}
  .cell.nodlv {{
    background: #fff1f3;
    border-color: rgba(216, 65, 90, 0.65);
  }}
  .cell.changed {{
    background: #fff7e8;
    border-color: rgba(222, 150, 35, 0.72);
  }}
  .top {{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    margin-bottom: 8px;
    gap: 8px;
  }}
  .day {{
    font-weight: 950;
    color:#111;
    font-size: 16px;
  }}
  .wd {{
    font-weight: 800;
    color: rgba(0,0,0,0.55);
    font-size: 12px;
  }}
  .badges {{
    display:flex;
    gap:6px;
    flex-wrap:wrap;
    justify-content:flex-end;
  }}
  .badge {{
    font-size: 12px;
    font-weight: 950;
    padding: 3px 10px;
    border-radius: 999px;
    border: 1.6px solid rgba(0,0,0,0.18);
    background: #fff;
    color:#111;
    white-space:nowrap;
  }}
  .badge.nodlv {{
    border-color: rgba(216, 65, 90, 0.65);
    color: rgb(190, 30, 60);
    background: rgba(216, 65, 90, 0.06);
  }}
  .badge.changed {{
    border-color: rgba(222, 150, 35, 0.72);
    color: rgb(175, 85, 0);
    background: rgba(222, 150, 35, 0.10);
  }}
  .menu {{
    font-size: 18px;
    font-weight: 800;
    color:#111;
    line-height: 1.18;
    word-break: keep-all;
  }}
  .change {{
    margin-top: 8px;
    font-size: 18px;
    font-weight: 950;
    color: rgb(200, 30, 45);
    line-height: 1.18;
    word-break: keep-all;
  }}
  .footer {{
    margin-top: 10px;
    font-size: 12px;
    color: rgba(0,0,0,0.55);
    text-align:right;
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="btnbar">
      <button id="btnCapture">PNG로 저장</button>
      <a id="downloadLink" download="{poster_filename}">다운로드</a>
      <span class="hint">※ 버튼 클릭 → PNG 다운로드 → 카톡/문자에 첨부</span>
    </div>

    <div id="poster">
      <div class="header">
        <div class="logo-box">{left_logo_html}</div>
        <div class="title">{title_html}</div>
        <div class="logo-box">{right_logo_html}</div>
      </div>

      <div class="dow">
        <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
      </div>

      <div class="grid">
        {cells_html}
      </div>

      <div class="footer">{y}-{m:02d} / moms diet poster</div>
    </div>
  </div>

<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
  const btn = document.getElementById("btnCapture");
  const link = document.getElementById("downloadLink");

  btn.addEventListener("click", async () => {{
    link.style.display = "none";
    const target = document.getElementById("poster");

    const canvas = await html2canvas(target, {{
      backgroundColor: "#ffffff",
      scale: 2
    }});

    canvas.toBlob((blob) => {{
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.style.display = "inline-block";
      link.textContent = "다운로드";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }}, "image/png");
  }});
</script>
</body>
</html>
"""

components.html(poster_html, height=980, scrolling=True)

# -----------------------------
# 하단: 업체 전달용 텍스트(옵션)
# -----------------------------
st.divider()
st.subheader("업체 전달용 요약(월간 텍스트)")
last_day = date(y, m, calendar.monthrange(y, m)[1])
all_days = [date(y, m, d) for d in range(1, last_day.day + 1)]

lines: list[str] = []
lines.append("동약협회입니다.")
lines.append(f"{y}년 {m:02d}월 도시락 변경/배달불요 내역입니다.")

no_delivery = [d for d in all_days if get_delivery_flag(delivery_df, d) != "Y"]
if no_delivery:
    lines.append("")
    lines.append("【배달불요】")
    for d in no_delivery:
        wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
        lines.append(f"▶ {m:02d}/{d.day:02d}({wd}) : 배달불요")

changed = [d for d in all_days if get_value(change_df, d, "change_menu") != ""]
if changed:
    lines.append("")
    lines.append("【변경메뉴】")
    for d in changed:
        wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
        cm = get_value(change_df, d, "change_menu")
        lines.append(f"▶ {m:02d}/{d.day:02d}({wd}) : {cm}")

st.text_area("복사해서 문자/카톡에 붙여넣기", "\n".join(lines), height=220)
