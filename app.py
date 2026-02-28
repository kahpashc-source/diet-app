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
    page_title="맘스락 식단 변경 프로그램",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
ASSETS_DIR = APP_DIR / "assets"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# 데이터 파일
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

# (예전 기능용) 로고/이미지 파일은 있어도 되고 없어도 됩니다.
MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

GONGYANG_TEXT = (
    "이 음식이 어디에서 왔는가\n"
    "내 덕행으로는 받기가 부끄럽네\n"
    "마음의 온갖 탐욕을 떠나\n"
    "몸을 지탱하는 약으로 알아\n"
    "이 공양을 받습니다"
)

# ✅ 월~금만
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
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _key(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_value(df: pd.DataFrame, d: date, col: str) -> str:
    k = _key(d)
    row = df[df["date"] == k]
    return str(row.iloc[0][col]).strip() if not row.empty else ""


def _set_value(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    k = _key(d)
    value = _normalize_text(value)

    if "date" not in df.columns:
        df["date"] = ""

    if (df["date"] == k).any():
        df.loc[df["date"] == k, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": k, col: value}])], ignore_index=True)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)


def _is_weekday(d: date) -> bool:
    return d.weekday() <= 4


def _safe_short(s: str, n: int = 16) -> str:
    s = _normalize_text(s)
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "…"


def _month_weeks_mon_fri(year: int, month: int) -> list[list[date]]:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    return [w[:5] for w in weeks]  # 월~금


def _img_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


# -----------------------------
# 세션 초기화
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
# CSS (달력/표시만: 예전처럼 단순 안정)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 0.9rem; padding-bottom: 1.2rem; }

.gongyang-wrap{
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255,255,255,0.92);
  border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 8px 22px rgba(0,0,0,0.06);
  margin-bottom: 12px;
}
.gongyang-head{ font-weight:900; font-size: 13px; opacity: 0.7; margin-bottom: 6px; }
.gongyang-text{ font-weight:900; font-size: 18px; line-height: 1.45; white-space: pre-line; }

.cal-head{ text-align:center; font-weight:900; opacity:0.75; padding: 4px 0 10px 0; }
.stButton>button{
  border-radius: 14px !important;
  border: 1px solid rgba(0,0,0,0.12) !important;
  min-height: 110px !important;
  text-align:left !important;
  white-space: pre-line !important;
}
.today-outline{ outline: 3px solid rgba(255, 170, 0, 0.55); outline-offset:-3px; border-radius: 14px; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# ✅ 상단: 공양게 + 글귀만
# -----------------------------
st.markdown(
    f"""
<div class="gongyang-wrap">
  <div class="gongyang-head">供養偈 (공양게)</div>
  <div class="gongyang-text">{GONGYANG_TEXT}</div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# ✅ 예전 기능 복구: 탭 (달력 입력 / 포스터 / 업체전달)
# -----------------------------
tabs = st.tabs(["① 달력 입력", "② 포스터(HTML)", "③ 업체 전달용 출력(TXT)"])
curr = date.today()


# -----------------------------
# 포스터(HTML) 생성
# - 예전 요구: A4 1페이지 + 로고/그릇/공양게 + 월~금 달력
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    moms = _img_b64(MOMS_LOGO_PATH)
    kapma = _img_b64(KAPMA_LOGO_PATH)
    bowl = _img_b64(BOWL_PATH)

    moms_img = f"<img class='logo' src='data:image/png;base64,{moms}' />" if moms else "<div class='logo ph'>MOMS</div>"
    kapma_img = f"<img class='logo' src='data:image/png;base64,{kapma}' />" if kapma else "<div class='logo ph'>협회</div>"
    bowl_img = f"<img class='bowl' src='data:image/png;base64,{bowl}' />" if bowl else "<div class='bowl ph'>🥣</div>"

    weeks = _month_weeks_mon_fri(year, month)

    def cell_html(d: date) -> str:
        if d.month != month:
            return ""
        base = _get_value(st.session_state.base_df, d, "base_menu")
        change = _get_value(st.session_state.change_df, d, "change_menu")
        no_del = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

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

    title = f"{year}년 {month:02d}월 식단(배달) 변경"

    return f"""
<!doctype html><html lang="ko"><head><meta charset="utf-8"/>
<style>
@page {{ size:A4; margin:10mm; }}
body {{ font-family: "Malgun Gothic", Arial, sans-serif; }}

.top {{
  display:grid; grid-template-columns: 1fr 1.6fr 1fr;
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
th{{ text-align:center; background:rgba(0,0,0,0.05); font-weight:900; }}
td{{ height:92px; }} /* ✅ A4 1페이지 고정 */

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
    <div style="display:flex;justify-content:flex-end;">{kapma_img}</div>
  </div>

  <div class="h1">{title}</div>

  <table>
    <thead><tr><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body></html>
"""


def build_vendor_text(year: int, month: int) -> str:
    weeks = _month_weeks_mon_fri(year, month)
    no_list, ch_list = [], []
    for w in weeks:
        for d in w:
            if d.month != month:
                continue
            if _get_value(st.session_state.delivery_df, d, "delivery") == "Y":
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
# ① 달력 입력
# -----------------------------
with tabs[0]:
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        sel_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1)
        sel_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1)
    with c2:
        st.caption("✅ 1달만 / ✅ 월~금만 / ✅ 요일 표시 / 날짜 클릭 → 입력")

    # 요일 헤더
    hcols = st.columns(5)
    for i, day_name in enumerate(WEEKDAYS_KO):
        hcols[i].markdown(f"<div class='cal-head'>{day_name}</div>", unsafe_allow_html=True)

    weeks = _month_weeks_mon_fri(sel_year, sel_month)

    def open_editor(target_date: date):
        base = _get_value(st.session_state.base_df, target_date, "base_menu")
        change = _get_value(st.session_state.change_df, target_date, "change_menu")
        is_no = _get_value(st.session_state.delivery_df, target_date, "delivery") == "Y"
        idx_list = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()

        @st.dialog(f"{target_date.strftime('%m월 %d일')} ({WEEKDAYS_KO[target_date.weekday()]}) 입력")
        def _dlg():
            b_sel = st.selectbox("기본 메뉴(인덱스)", idx_list, key=f"bsel_{target_date}")
            b_txt = st.text_input("기본 메뉴(직접 입력)", value=base if b_sel == "(직접입력)" else b_sel, key=f"btxt_{target_date}")

            st.divider()

            c_sel = st.selectbox("변경 메뉴(인덱스)", idx_list, key=f"csel_{target_date}")
            c_txt = st.text_input("변경 메뉴(직접 입력)", value=change if c_sel == "(직접입력)" else c_sel, key=f"ctxt_{target_date}")

            st.divider()

            no_del = st.toggle("🚫 배달불요", value=is_no, key=f"nd_{target_date}")
            st.divider()

            colA, colB = st.columns([1, 1])
            with colA:
                if st.button("저장", type="primary", use_container_width=True, key=f"save_{target_date}"):
                    st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_txt)
                    st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_txt)
                    st.session_state.delivery_df = _set_value(st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N")

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                    # 인덱스 축적(가나다)
                    new_items = [_normalize_text(b_txt), _normalize_text(c_txt)]
                    new_items = [x for x in new_items if x]
                    if new_items:
                        idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame({"name": new_items})], ignore_index=True)
                        idx["name"] = idx["name"].map(_normalize_text)
                        idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                        st.session_state.menu_index_df = idx
                        _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)

                    st.rerun()

            with colB:
                if st.button("해당일 비우기", use_container_width=True, key=f"clr_{target_date}"):
                    k = _key(target_date)
                    st.session_state.base_df = st.session_state.base_df[st.session_state.base_df["date"] != k].reset_index(drop=True)
                    st.session_state.change_df = st.session_state.change_df[st.session_state.change_df["date"] != k].reset_index(drop=True)
                    st.session_state.delivery_df = st.session_state.delivery_df[st.session_state.delivery_df["date"] != k].reset_index(drop=True)

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)
                    st.rerun()

        _dlg()

    # 달력 출력
    for week in weeks:
        cols = st.columns(5)
        for i, d in enumerate(week):
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue

                base = _get_value(st.session_state.base_df, d, "base_menu")
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

                label = f"**{d.day}**\n"
                if is_no:
                    label += "🚫 배달불요\n"
                if change:
                    label += f"🔁 {_safe_short(change)}\n"
                elif base:
                    label += f"🍚 {_safe_short(base)}\n"

                wrap = "today-outline" if d == curr else ""
                st.markdown(f"<div class='{wrap}'>", unsafe_allow_html=True)
                clicked = st.button(label, key=f"btn_{d}", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

                if clicked and _is_weekday(d):
                    open_editor(d)


# -----------------------------
# ② 포스터(HTML) + 다운로드
# -----------------------------
with tabs[1]:
    p_year = st.selectbox("연도(포스터)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="p_year")
    p_month = st.selectbox("월(포스터)", list(range(1, 13)), index=curr.month - 1, key="p_month")

    poster_html = build_poster_html(p_year, p_month)

    st.markdown("#### 포스터 미리보기")
    components.html(poster_html, height=860, scrolling=True)

    st.download_button(
        "⬇️ 포스터 HTML 다운로드(A4 1페이지 인쇄용)",
        data=poster_html.encode("utf-8"),
        file_name=f"포스터_{p_year}-{p_month:02d}.html",
        mime="text/html",
        use_container_width=True,
    )


# -----------------------------
# ③ 업체 전달용 출력(TXT) + 다운로드
# -----------------------------
with tabs[2]:
    o_year = st.selectbox("연도(출력)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="o_year")
    o_month = st.selectbox("월(출력)", list(range(1, 13)), index=curr.month - 1, key="o_month")

    txt = build_vendor_text(o_year, o_month)

    st.text_area("업체 전달용 문구(복사)", value=txt, height=360)

    st.download_button(
        "⬇️ 텍스트 파일 다운로드",
        data=txt.encode("utf-8"),
        file_name=f"업체전달_{o_year}-{o_month:02d}.txt",
        mime="text/plain",
        use_container_width=True,
    )
