# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import html

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
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# ✅ 로고 자동 추출(업로드 UI 없음)
POSTER_SOURCE_PATH = DATA_DIR / "moms_poster_source.jpg"
EXTRACTED_LOGO_PATH = DATA_DIR / "moms_logo_extracted.png"

# 평일(월~금)만 출력
WEEKDAY_KR_WD = ["월", "화", "수", "목", "금"]
WEEKDAY_FULL = ["월", "화", "수", "목", "금", "토", "일"]


# -----------------------------
# CSV 유틸
# -----------------------------
def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
        df = df[df["date"].ne("NaT")]
    return df


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
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _delete_by_date(path: Path, columns: list[str], d: date) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    df = df[df["date"] != key].copy()
    df.to_csv(path, index=False, encoding="utf-8-sig")


# -----------------------------
# 메뉴 인덱스
# -----------------------------
def _read_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8-sig")
    if "name" not in df.columns:
        return []
    items = [x.strip() for x in df["name"].fillna("").tolist() if str(x).strip()]
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _write_menu_index(items: list[str]) -> None:
    pd.DataFrame({"name": items}).to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")


# -----------------------------
# 이미지(Data URI)
# -----------------------------
def _data_uri(path: Path) -> str | None:
    if path is None or (not path.exists()):
        return None
    b = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(b).decode("utf-8")


# -----------------------------
# ✅ 포스터 사진에서 M 로고 자동 추출
# -----------------------------
def _ensure_extracted_logo() -> None:
    if EXTRACTED_LOGO_PATH.exists():
        return
    if not POSTER_SOURCE_PATH.exists():
        return

    try:
        from PIL import Image, ImageOps

        img = Image.open(POSTER_SOURCE_PATH).convert("RGB")
        w, h = img.size

        # 좌측 상단 넓게 잡고(0~32%, 0~32%) 로고 bbox 자동 추정
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
            logo = crop.crop((x0, y0, x1, y1))
        else:
            logo = crop.crop((0, 0, int(crop.size[0] * 0.70), int(crop.size[1] * 0.70)))

        logo = logo.resize((420, int(420 * logo.size[1] / max(1, logo.size[0]))))
        logo.save(EXTRACTED_LOGO_PATH, format="PNG", optimize=True)

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
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["base"] = (r.get("base_menu") or "").strip()

    for _, r in change.iterrows():
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["change"] = (r.get("change_menu") or "").strip()

    for _, r in delivery.iterrows():
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        v = (r.get("delivery") or "Y").strip().upper()
        out[d]["delivery"] = "N" if v == "N" else "Y"

    return out


# -----------------------------
# ✅ 평일(월~금) 달력(주차 구조 유지) 포스터 HTML
# -----------------------------
def _build_weekday_poster_html(
    y: int,
    m: int,
    title_top: str,
    title_bottom: str,
    right_label: str,
    logo_uri: str | None,
) -> str:
    data_map = _get_day_record_map(y, m)

    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    weeks7 = cal.monthdayscalendar(y, m)     # 각 주: [월..일], 해당월 아니면 0

    # ✅ 주차 구조 그대로 두고 월~금만 사용
    rows5: list[list[int]] = []
    for wk in weeks7:
        wd = wk[:5]  # 월~금
        # 주 전체가 0(즉, 월~금이 전부 비어있으면) 스킵
        if all(d == 0 for d in wd):
            continue
        rows5.append(wd)

    # 1장 출력 안정: 행 수에 따라 셀 높이 자동 조정
    row_count = len(rows5)
    cell_h = 126 if row_count <= 4 else 112

    if logo_uri:
        logo_html = f'<img src="{logo_uri}" class="logo-img" alt="logo"/>'
    else:
        logo_html = """
        <div class="logo-fallback"><div class="mf">M</div></div>
        """

    css = f"""
    <style>
      @page {{ size: A4 landscape; margin: 7mm; }}
      html, body {{ height: 100%; }}
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
        color: #0f172a;
        background: #ffffff;
      }}

      @media print {{
        * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      }}

      .sheet {{
        width: 100%;
        border-radius: 18px;
        padding: 10px 12px 10px 12px;
        box-sizing: border-box;
      }}

      .header {{
        display:grid;
        grid-template-columns: 200px 1fr 200px;
        gap: 10px;
        align-items: center;
        margin-bottom: 10px;
      }}

      .brand {{
        height: 104px;
        border-radius: 18px;
        background: #ffffff;
        border: 2.5px solid rgba(15,23,42,0.32);
        box-shadow: 0 6px 14px rgba(15,23,42,0.08);
        display:flex;
        align-items:center;
        justify-content:center;
        gap: 10px;
        padding: 10px 12px;
        box-sizing: border-box;
      }}
      .logo-img {{
        height: 74px;
        width: auto;
        object-fit: contain;
      }}
      .logo-fallback {{
        height: 74px; width: 74px;
        border-radius: 20px;
        background: linear-gradient(180deg, rgba(255,120,160,0.55), rgba(255,180,90,0.55));
        border: 2px solid rgba(15,23,42,0.22);
        display:flex; align-items:center; justify-content:center;
      }}
      .logo-fallback .mf {{
        font-size: 54px;
        font-weight: 1000;
        color: rgba(15,23,42,0.86);
        line-height: 1;
      }}

      .brand-text {{
        line-height: 1.0;
        font-weight: 1000;
        letter-spacing: -0.3px;
        color: rgba(15,23,42,0.92);
      }}
      .brand-text .moms {{ font-size: 30px; }}
      .brand-text .style {{
        font-size: 13px;
        font-weight: 900;
        opacity: 0.70;
        margin-top: 6px;
      }}

      .title {{
        text-align: center;
        line-height: 1.0;
      }}
      .title .t1 {{
        font-size: 38px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 0;
      }}
      .title .t2 {{
        font-size: 38px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        margin: 6px 0 0 0;
      }}

      .rightbox {{
        height: 104px;
        border-radius: 18px;
        background: #ffffff;
        border: 2.5px solid rgba(15,23,42,0.32);
        box-shadow: 0 6px 14px rgba(15,23,42,0.08);
        display:flex;
        align-items:center;
        justify-content:center;
        padding: 10px 12px;
        box-sizing: border-box;
      }}
      .rightbox .label {{
        font-size: 30px;
        font-weight: 1000;
        letter-spacing: -0.3px;
        color: rgba(15,23,42,0.92);
      }}

      table {{
        border-collapse: separate;
        border-spacing: 10px 10px;
        width: 100%;
        table-layout: fixed;
      }}
      th {{
        font-size: 15px;
        font-weight: 1000;
        text-align:center;
        padding: 2px 0 0 0;
        color: rgba(15,23,42,0.92);
      }}
      td {{
        height: {cell_h}px;
        vertical-align: top;
        background: #ffffff;
        border: 2.5px solid rgba(15,23,42,0.30);
        border-radius: 14px;
        box-shadow: 0 8px 14px rgba(15,23,42,0.07);
        padding: 10px 12px;
        box-sizing: border-box;
        overflow: hidden;
      }}
      .empty {{
        background: #ffffff;
        border: 2.5px dashed rgba(15,23,42,0.20);
        box-shadow: none;
      }}

      .has-change {{
        border-color: rgba(196,0,0,0.45);
        background: rgba(255, 246, 246, 0.92);
      }}
      .no-delivery {{
        border-color: rgba(176,0,32,0.38);
        background: rgba(255, 240, 244, 0.92);
      }}
      .both {{
        border-color: rgba(125, 60, 152, 0.45);
        background: rgba(248, 244, 255, 0.92);
      }}

      .cell-top {{
        display:flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }}
      .datechip {{
        display:inline-flex;
        align-items:baseline;
        gap: 8px;
        font-weight: 1000;
        font-size: 16px;
        letter-spacing: -0.3px;
      }}
      .dow {{
        font-size: 12.5px;
        font-weight: 900;
        opacity: 0.72;
      }}

      .badge-nodelivery {{
        font-size: 12px;
        font-weight: 1000;
        color: #b00020;
        background: rgba(255, 235, 238, 0.98);
        border: 1px solid rgba(176,0,32,0.34);
        padding: 4px 10px;
        border-radius: 999px;
        letter-spacing: -0.2px;
      }}

      .menu {{
        font-size: 16px;
        line-height: 1.18;
        letter-spacing: -0.35px;
        word-break: keep-all;
      }}
      .base {{
        font-weight: 1000;
        color: rgba(15,23,42,0.93);
      }}

      .change {{
        margin-top: 10px;
        font-weight: 1000;
        color: #c40000;
      }}
      .change .label {{
        display:inline-block;
        font-size: 12px;
        font-weight: 1000;
        padding: 2px 10px;
        border-radius: 999px;
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
        for col, day in enumerate(wk):  # col: 0..4
            if day == 0:
                tds.append('<td class="empty"></td>')
                continue

            # 실제 요일 계산(월~금만 들어오지만 안전하게)
            dt = date(y, m, day)
            dow = WEEKDAY_FULL[dt.weekday()]

            rec = data_map.get(day, {})
            base = html.escape(rec.get("base", "").strip())
            change = html.escape(rec.get("change", "").strip())
            delivery = (rec.get("delivery", "Y") or "Y").strip().upper()

            is_nodelivery = (delivery == "N")
            has_change = bool(change)

            cls = ""
            if has_change and is_nodelivery:
                cls = "both"
            elif has_change:
                cls = "has-change"
            elif is_nodelivery:
                cls = "no-delivery"

            badge = f'<span class="badge-nodelivery">배달불요</span>' if is_nodelivery else ""
            base_line = f'<div class="menu base">{base}</div>' if base else '<div class="menu base">&nbsp;</div>'
            change_block = f'<div class="menu change"><span class="label">변경</span>{change}</div>' if change else ""

            tds.append(f"""
            <td class="{cls}">
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
      <head>
        <meta charset="utf-8"/>
        {css}
      </head>
      <body>
        <div class="sheet">
          <div class="header">
            <div class="brand">
              {logo_html}
              <div class="brand-text">
                <div class="moms">MOMS</div>
                <div class="style">Style</div>
              </div>
            </div>

            <div class="title">
              <p class="t1">{html.escape(title_top)}</p>
              <p class="t2">{html.escape(title_bottom)}</p>
            </div>

            <div class="rightbox">
              <div class="label">{html.escape(right_label)}</div>
            </div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>
              {''.join(body_rows)}
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """


# -----------------------------
# 앱 시작 시 로고 자동 추출 시도
# -----------------------------
_ensure_extracted_logo()


# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption("평일(월~금)만 크게 출력(1장) + 주차 구조 유지(3월도 정상) + 인쇄 선명도 강화")

colL, colR = st.columns([1.05, 1.0], vertical_alignment="top")

with colL:
    st.subheader("1) 메뉴 인덱스 관리")
    idx_items = _read_menu_index()

    c1, c2 = st.columns([1, 1])
    with c1:
        new_item = st.text_input("메뉴 추가", placeholder="예: 소고기미역국")
        if st.button("➕ 인덱스에 추가", use_container_width=True):
            x = (new_item or "").strip()
            if x:
                if x not in idx_items:
                    idx_items.append(x)
                    _write_menu_index(idx_items)
                st.success("저장 완료")
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with c2:
        del_item = st.selectbox("삭제할 메뉴 선택", ["(선택)"] + idx_items)
        if st.button("🗑️ 선택 메뉴 삭제", use_container_width=True):
            if del_item != "(선택)":
                idx_items = [x for x in idx_items if x != del_item]
                _write_menu_index(idx_items)
                st.success("삭제 완료")

    st.divider()

    st.subheader("2) 월 선택 & 날짜별 입력")
    today = date.today()
    y = st.selectbox("연도", list(range(today.year - 2, today.year + 4)), index=2)
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    days = [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    labels = [f"{d.strftime('%m/%d')}({WEEKDAY_FULL[d.weekday()]})" for d in days]
    pick = st.selectbox("날짜 선택", list(range(len(days))), format_func=lambda i: labels[i])
    dsel = days[pick]
    key = dsel.isoformat()

    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    cur_base = base_df.loc[base_df["date"] == key, "base_menu"].iloc[0] if (base_df["date"] == key).any() else ""
    cur_change = change_df.loc[change_df["date"] == key, "change_menu"].iloc[0] if (change_df["date"] == key).any() else ""
    cur_deliv = deliv_df.loc[deliv_df["date"] == key, "delivery"].iloc[0] if (deliv_df["date"] == key).any() else "Y"
    if cur_deliv not in ["Y", "N"]:
        cur_deliv = "Y"

    st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_FULL[dsel.weekday()]})")

    st.markdown("**기본메뉴**")
    base_pick = st.selectbox("기본메뉴(인덱스)", ["(직접입력)"] + idx_items, index=0)
    base_text = st.text_input("기본메뉴(직접입력)", value=cur_base if base_pick == "(직접입력)" else base_pick)
    if base_pick != "(직접입력)":
        base_text = base_pick

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 기본메뉴 저장", use_container_width=True):
            _upsert_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel, "base_menu", (base_text or "").strip())
            st.success("기본메뉴 저장 완료")
    with b2:
        if st.button("🧹 기본메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel)
            st.success("기본메뉴 삭제 완료")

    st.markdown("**변경메뉴(있으면 입력)**")
    change_pick = st.selectbox("변경메뉴(인덱스)", ["(없음)"] + idx_items, index=0)
    default_change = "" if cur_change.strip() == "" else cur_change
    change_text = st.text_input("변경메뉴(직접입력)", value=default_change if change_pick == "(없음)" else change_pick)
    if change_pick != "(없음)":
        change_text = change_pick

    c3, c4 = st.columns([1, 1])
    with c3:
        if st.button("💾 변경메뉴 저장", use_container_width=True):
            _upsert_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel, "change_menu", (change_text or "").strip())
            st.success("변경메뉴 저장 완료")
    with c4:
        if st.button("🧹 변경메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel)
            st.success("변경메뉴 삭제 완료")

    st.markdown("**배달 여부**")
    deliv_choice = st.radio("배달", ["배달(Y)", "배달불요(N)"], index=0 if cur_deliv == "Y" else 1, horizontal=True)
    if st.button("💾 배달여부 저장", use_container_width=True):
        _upsert_by_date(DELIVERY_PATH, ["date", "delivery"], dsel, "delivery", "Y" if deliv_choice.startswith("배달(Y)") else "N")
        st.success("배달여부 저장 완료")

with colR:
    st.subheader("3) 포스터(출력용 1장) 미리보기")

    right_label = st.text_input("우측 상단 표기", value="동약협회")

    # ✅ 제목 2줄 고정
    title_top = f"맘스락 {m:02d}월"
    title_bottom = "식단 변경"

    logo_uri = _data_uri(EXTRACTED_LOGO_PATH)

    poster_html = _build_weekday_poster_html(
        y=y,
        m=m,
        title_top=title_top,
        title_bottom=title_bottom,
        right_label=(right_label or "동약협회").strip(),
        logo_uri=logo_uri,
    )

    components.html(poster_html, height=780, scrolling=True)

    st.divider()
    st.subheader("4) 업체 전달용 파일 만들기")
    st.download_button(
        label="⬇️ HTML 다운로드(열고 Ctrl+P → PDF 저장/바로 출력)",
        data=poster_html.encode("utf-8"),
        file_name=f"{y}-{m:02d}_식단표_평일포스터.html",
        mime="text/html",
        use_container_width=True,
    )
