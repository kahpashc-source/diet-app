# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import re
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="맘스락 식단 관리 시스템",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ✅ GitHub 스샷 기준: 파일이 루트(diet-app/)에 존재
MOMS_LOGO_PATH = APP_DIR / "moms_logo.png"
ASSOC_LOGO_PATH = APP_DIR / "association_logo.png"
BOWL_PATH = APP_DIR / "gongyang_bowl.png"
DOSIRAK_PATH = APP_DIR / "datamoms_poster_source.jpg"  # 도시락 이미지(jpg)

# 데이터 파일
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

GONGYANG_TEXT = (
    "이 음식이 어디에서 왔는가\n"
    "내 덕행으로는 받기가 부끄럽네\n"
    "마음의 온갖 탐욕을 떠나\n"
    "몸을 지탱하는 약으로 알아\n"
    "이 공양을 받습니다"
)
WEEKDAYS_KO = ["월", "화", "수", "목", "금"]

# -----------------------------
# 유틸
# -----------------------------
def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s

def _read_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].fillna("")

def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

def _key(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def _get_value(df: pd.DataFrame, d: date, col: str) -> str:
    k = _key(d)
    if df.empty:
        return ""
    row = df[df["date"] == k]
    return str(row.iloc[0][col]).strip() if not row.empty else ""

def _set_value(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    k = _key(d)
    value = _normalize_text(value)

    if "date" not in df.columns:
        df["date"] = ""
    if col not in df.columns:
        df[col] = ""

    if (df["date"] == k).any():
        df.loc[df["date"] == k, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": k, col: value}])], ignore_index=True)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)

def _month_weeks_mon_fri(year: int, month: int) -> list[list[date]]:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    return [w[:5] for w in weeks]

def _safe_short(s: str, n: int = 16) -> str:
    s = _normalize_text(s)
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "…"

def _img_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")

def _download_basename(year: int, month: int) -> str:
    # ✅ 요청한 파일명 규칙
    return f"동약협회 {year}년 {month:02d}월 식단변경 내역"

def _is_no_delivery(d: date) -> bool:
    return _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

# -----------------------------
# 세션 초기화 (오류 방지: 컬럼 강제 생성)
# -----------------------------
if "base_df" not in st.session_state:
    st.session_state.base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
if "change_df" not in st.session_state:
    st.session_state.change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
if "delivery_df" not in st.session_state:
    st.session_state.delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
if "menu_index_df" not in st.session_state:
    idx = _read_csv(MENU_INDEX_PATH, ["name"])
    idx["name"] = idx["name"].map(_normalize_text)
    idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
    st.session_state.menu_index_df = idx

# -----------------------------
# CSS (오늘 오전 UI 느낌 유지)
# -----------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');

.block-container { padding-top: 1.2rem; }
.header-card{
  background:#fff; border-radius:20px; padding:18px 18px;
  box-shadow:0 10px 30px rgba(0,0,0,0.05);
  border:1px solid #f0f0f0; margin-bottom: 16px;
}
.gongyang-card{
  background:#fdfaf5; border-left:5px solid #d4a373;
  padding:18px; border-radius:0 15px 15px 0;
  font-family:'Noto Serif KR', serif;
}
.cal-head{ text-align:center; font-weight:900; color:#d4a373; padding: 4px 0 10px 0; }
.stButton>button{
  border-radius:12px; border:1px solid #eee; min-height:120px;
  transition: all 0.25s; background:white;
  text-align:left !important; white-space: pre-line !important;
}
.stButton>button:hover{
  border-color:#d4a373; box-shadow:0 5px 15px rgba(212, 163, 115, 0.2);
  transform: translateY(-2px);
}
.small-muted{ font-size:12px; opacity:0.70; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단: 공양게(제목 + 글귀) + (루트 이미지 사용)
# -----------------------------
h1, h2 = st.columns([1.25, 1], gap="large")

with h1:
    st.markdown('<div class="header-card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([0.9, 1.4, 0.9], vertical_alignment="center")

    with c1:
        if MOMS_LOGO_PATH.exists():
            st.image(str(MOMS_LOGO_PATH), use_container_width=True)
        else:
            st.write("moms_logo.png 없음")

    with c2:
        st.markdown("<h2 style='margin:0; color:#443322;'>맘스락 식단 관리</h2>", unsafe_allow_html=True)
        st.caption("평일(월~금) 중심 | 날짜 클릭 → 바로 입력")
        if DOSIRAK_PATH.exists():
            st.image(str(DOSIRAK_PATH), use_container_width=True)
        else:
            st.write("datamoms_poster_source.jpg 없음")

    with c3:
        if ASSOC_LOGO_PATH.exists():
            st.image(str(ASSOC_LOGO_PATH), use_container_width=True)
        else:
            st.write("association_logo.png 없음")

    st.markdown("</div>", unsafe_allow_html=True)

with h2:
    st.markdown(
        f"""
<div class="gongyang-card">
  <div style="font-size:1.05rem;font-weight:900;color:#6b4e2e;margin-bottom:10px;">공양게</div>
  <div style="font-size:1.18rem;font-weight:700;color:#554433;line-height:1.6;white-space:pre-line;">
  {GONGYANG_TEXT}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

st.divider()

# -----------------------------
# 포스터 HTML 생성(A4 1페이지)
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    moms = _img_b64(MOMS_LOGO_PATH)
    assoc = _img_b64(ASSOC_LOGO_PATH)
    bowl = _img_b64(BOWL_PATH)

    moms_img = f"<img class='logo' src='data:image/png;base64,{moms}' />" if moms else "<div class='logo ph'>MOMS</div>"
    assoc_img = f"<img class='logo' src='data:image/png;base64,{assoc}' />" if assoc else "<div class='logo ph'>동약협회</div>"
    bowl_img = f"<img class='bowl' src='data:image/png;base64,{bowl}' />" if bowl else "<div class='bowl ph'>🥣</div>"

    weeks = _month_weeks_mon_fri(year, month)

    def cell_html(d: date) -> str:
        if d.month != month:
            return ""
        base = _get_value(st.session_state.base_df, d, "base_menu")
        change = _get_value(st.session_state.change_df, d, "change_menu")
        no_del = _is_no_delivery(d)

        out = [f"<div class='daynum'>{d.day}</div>"]
        if no_del:
            out.append("<div class='nd'>🚫 배달불요</div>")
        if change:
            out.append(f"<div class='ch'>🔁 {change}</div>")
        if base:
            out.append(f"<div class='bs'>🍚 {base}</div>")
        return "".join(out)

    rows = ""
    for w in weeks:
        rows += "<tr>" + "".join([f"<td>{cell_html(d)}</td>" for d in w]) + "</tr>"

    title = _download_basename(year, month)

    return f"""
<!doctype html><html lang="ko"><head><meta charset="utf-8"/>
<style>
@page {{ size:A4; margin:10mm; }}
body {{ font-family: "Malgun Gothic", Arial, sans-serif; }}

.top {{
  display:grid; grid-template-columns: 1fr 1.8fr 1fr;
  gap:10px; align-items:center; margin-bottom: 6px;
}}
.logo {{ height:46px; object-fit:contain; }}

.mid {{
  border:1px solid rgba(0,0,0,0.12);
  border-radius:12px;
  padding:8px 10px;
  background:#fdfaf5;
  display:flex; gap:10px; align-items:center;
}}
.bowl {{ height:52px; object-fit:contain; }}
.gong {{
  white-space:pre-line;
  font-weight:900;
  font-size:14px;
  line-height:1.45;
  color:#4a3627;
}}

.h1 {{ text-align:center; font-weight:900; font-size:20px; margin:6px 0 6px 0; }}

table{{ width:100%; border-collapse:collapse; table-layout:fixed; }}
th,td{{ border:1px solid rgba(0,0,0,0.12); vertical-align:top; padding:6px; }}
th{{ text-align:center; background:rgba(212,163,115,0.14); font-weight:900; color:#6b4e2e; }}
td{{ height:92px; }}

.daynum{{ font-weight:900; margin-bottom:4px; }}
.nd{{ color:#9b1c1c; font-weight:900; }}
.ch{{ font-weight:900; }}
.bs{{ opacity:0.85; }}

.ph{{ border:1px dashed rgba(0,0,0,0.25); border-radius:10px; height:46px;
     display:flex; align-items:center; justify-content:center; font-weight:900; }}
</style></head>
<body>
  <div class="top">
    <div style="display:flex;justify-content:flex-start;">{moms_img}</div>
    <div class="mid">{bowl_img}<div class="gong">{GONGYANG_TEXT}</div></div>
    <div style="display:flex;justify-content:flex-end;">{assoc_img}</div>
  </div>

  <div class="h1">{title}</div>

  <table>
    <thead><tr><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body></html>
"""

# -----------------------------
# 업체 전달용 텍스트
# -----------------------------
def build_vendor_text(year: int, month: int) -> str:
    weeks = _month_weeks_mon_fri(year, month)
    no_list, ch_list = [], []

    for w in weeks:
        for d in w:
            if d.month != month:
                continue
            if _is_no_delivery(d):
                no_list.append(d)
            ch = _get_value(st.session_state.change_df, d, "change_menu")
            if ch:
                ch_list.append((d, ch))

    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")

    if no_list:
        lines.append("🚫【배달불요】")
        for d in no_list:
            lines.append(f"▶ {d.strftime('%m/%d')}({WEEKDAYS_KO[d.weekday()]}) : 배달불요")
        lines.append("")

    if ch_list:
        lines.append("🔁【변경메뉴】")
        for d, menu in ch_list:
            lines.append(f"▶ {d.strftime('%m/%d')}({WEEKDAYS_KO[d.weekday()]}) : {menu}")

    if not no_list and not ch_list:
        lines.append("금월 변경/배달불요 내역이 없습니다.")
    return "\n".join(lines)

# -----------------------------
# 탭 (달력 / 포스터 / 출력)
# -----------------------------
tabs = st.tabs(["① 달력 입력", "② 포스터(스크린샷/출력)", "③ 업체 전달용 출력"])
curr = date.today()

# ① 달력 입력
with tabs[0]:
    c1, c2 = st.columns([1, 4])
    with c1:
        sel_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1)
        sel_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1)

    # 요일 헤더
    hcols = st.columns(5)
    for i, day_name in enumerate(WEEKDAYS_KO):
        hcols[i].markdown(f"<div class='cal-head'>{day_name}</div>", unsafe_allow_html=True)

    weeks = _month_weeks_mon_fri(sel_year, sel_month)

    def open_editor(target_date: date):
        base = _get_value(st.session_state.base_df, target_date, "base_menu")
        change = _get_value(st.session_state.change_df, target_date, "change_menu")
        is_no = _is_no_delivery(target_date)

        @st.dialog(f"{target_date.strftime('%m월 %d일')} 식단 편집")
        def edit_dialog():
            idx_list = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()

            b_val = st.selectbox("기본 메뉴 선택", idx_list, key=f"sel_b_{target_date}")
            b_text = st.text_input("기본 메뉴(직접 입력)", value=base if b_val == "(직접입력)" else b_val, key=f"txt_b_{target_date}")

            st.divider()

            c_val = st.selectbox("변경 메뉴 선택", idx_list, key=f"sel_c_{target_date}")
            c_text = st.text_input("변경 메뉴(직접 입력)", value=change if c_val == "(직접입력)" else c_val, key=f"txt_c_{target_date}")

            no_del = st.toggle("🚫 배달 불요", value=is_no, key=f"nd_{target_date}")

            if st.button("저장하기", use_container_width=True, type="primary", key=f"save_{target_date}"):
                st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_text)
                st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_text)
                st.session_state.delivery_df = _set_value(st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N")

                _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                # 인덱스 업데이트(가나다 정렬)
                new_items = [_normalize_text(b_text), _normalize_text(c_text)]
                new_items = [x for x in new_items if x]
                if new_items:
                    new_idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame({"name": new_items})], ignore_index=True)
                    new_idx["name"] = new_idx["name"].map(_normalize_text)
                    st.session_state.menu_index_df = new_idx[new_idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                    _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)

                st.rerun()

        edit_dialog()

    for week in weeks:
        cols = st.columns(5)
        for i in range(5):
            d = week[i]
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue

                base = _get_value(st.session_state.base_df, d, "base_menu")
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no = _is_no_delivery(d)

                label = f"**{d.day}**\n"
                if is_no:
                    label += "🚫 배달불요\n"
                if change:
                    label += f"🔁 {_safe_short(change, 16)}\n"
                elif base:
                    label += f"🍚 {_safe_short(base, 16)}\n"

                if st.button(label, key=f"btn_{d}", use_container_width=True):
                    open_editor(d)

# ② 포스터
with tabs[1]:
    p1, p2 = st.columns([1, 4])
    with p1:
        p_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="p_year")
        p_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1, key="p_month")
    with p2:
        st.caption("A4 1페이지 인쇄용 HTML입니다. (Ctrl+P → 한 페이지에 맞춤 권장)")

    poster_html = build_poster_html(p_year, p_month)
    base_name = _download_basename(p_year, p_month)

    st.markdown("#### 포스터 미리보기")
    components.html(poster_html, height=860, scrolling=True)

    st.download_button(
        "⬇️ 포스터 HTML 다운로드",
        data=poster_html.encode("utf-8"),
        file_name=f"{base_name}.html",
        mime="text/html",
        use_container_width=True,
    )

# ③ 업체 전달용 출력
with tabs[2]:
    o1, o2 = st.columns([1, 4])
    with o1:
        o_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="o_year")
        o_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1, key="o_month")
    with o2:
        st.caption("월~금 기준으로 ‘배달불요/변경메뉴’만 문자용으로 출력합니다.")

    txt = build_vendor_text(o_year, o_month)
    base_name = _download_basename(o_year, o_month)

    st.text_area("업체 전달용 문구(복사)", value=txt, height=360)

    st.download_button(
        "⬇️ 텍스트 파일 다운로드",
        data=txt.encode("utf-8"),
        file_name=f"{base_name}.txt",
        mime="text/plain",
        use_container_width=True,
    )
