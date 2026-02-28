# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import re
import unicodedata

import pandas as pd
import streamlit as st

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
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ✅ GitHub 스샷 기준: 이미지 파일은 루트에 존재(있어도/없어도 됨)
# (상단엔 공양게 글만 두므로 이미지 사용 안 함)
# MOMS_LOGO_PATH = APP_DIR / "moms_logo.png"
# ASSOC_LOGO_PATH = APP_DIR / "association_logo.png"
# BOWL_PATH = APP_DIR / "gongyang_bowl.png"
# DOSIRAK_PATH = APP_DIR / "datamoms_poster_source.jpg"

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


def _is_no_delivery(d: date) -> bool:
    return _get_value(st.session_state.delivery_df, d, "delivery") == "Y"


def _download_basename(year: int, month: int) -> str:
    return f"동약협회 {year}년 {month:02d}월 식단변경 내역"


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
# 스타일 (간단/안정)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 1.2rem; }

.gongyang-wrap{
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255,255,255,0.92);
  border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 8px 22px rgba(0,0,0,0.06);
  margin-bottom: 12px;
}
.gongyang-head{ font-weight:900; font-size: 14px; opacity: 0.75; margin-bottom: 6px; }
.gongyang-text{ font-weight:900; font-size: 18px; line-height: 1.45; white-space: pre-line; }

.cal-head{ text-align:center; font-weight:900; opacity:0.75; padding: 4px 0 10px 0; }
.stButton>button{
  border-radius: 14px !important;
  border: 1px solid rgba(0,0,0,0.12) !important;
  min-height: 110px !important;
  text-align:left !important;
  white-space: pre-line !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단: 공양게(제목 + 글귀)
# -----------------------------
st.markdown(
    f"""
<div class="gongyang-wrap">
  <div class="gongyang-head">공양게</div>
  <div class="gongyang-text">{GONGYANG_TEXT}</div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 탭: 달력 입력 / 업체전달 출력
# -----------------------------
tabs = st.tabs(["① 달력 입력", "② 업체 전달용 출력(TXT)"])
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
        idx_list = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()

        @st.dialog(f"{target_date.strftime('%m월 %d일')} ({WEEKDAYS_KO[target_date.weekday()]}) 입력")
        def _dlg():
            # 기본
            b_sel = st.selectbox("기본 메뉴(인덱스)", idx_list, key=f"bsel_{target_date}")
            b_txt = st.text_input(
                "기본 메뉴(직접 입력)",
                value=base if b_sel == "(직접입력)" else b_sel,
                key=f"btxt_{target_date}",
            )

            st.divider()

            # 변경
            c_sel = st.selectbox("변경 메뉴(인덱스)", idx_list, key=f"csel_{target_date}")
            c_txt = st.text_input(
                "변경 메뉴(직접 입력)",
                value=change if c_sel == "(직접입력)" else c_sel,
                key=f"ctxt_{target_date}",
            )

            st.divider()

            no_del = st.toggle("🚫 배달 불요", value=is_no, key=f"nd_{target_date}")

            if st.button("저장", type="primary", use_container_width=True, key=f"save_{target_date}"):
                st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_txt)
                st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_txt)
                st.session_state.delivery_df = _set_value(
                    st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N"
                )

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

        _dlg()

    for week in weeks:
        cols = st.columns(5)
        for i, d in enumerate(week):
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue

                # 달력 칸 내용: “변경/배달불요”만 보이게(식단표 목적 제거)
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no = _is_no_delivery(d)

                label = f"**{d.day}**\n"
                if is_no:
                    label += "🚫 배달불요\n"
                if change:
                    label += f"🔁 {change}\n"

                if st.button(label, key=f"btn_{d}", use_container_width=True):
                    open_editor(d)

# ② 업체 전달용 출력(TXT)
with tabs[1]:
    o1, o2 = st.columns([1, 4])
    with o1:
        o_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="o_year")
        o_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1, key="o_month")
    with o2:
        st.caption("월~금 기준으로 ‘배달불요/변경메뉴’만 문자로 보내기 좋게 출력합니다.")

    # 출력 텍스트 생성
    weeks = _month_weeks_mon_fri(o_year, o_month)
    no_list, ch_list = [], []
    for w in weeks:
        for d in w:
            if d.month != o_month:
                continue
            if _is_no_delivery(d):
                no_list.append(d)
            ch = _get_value(st.session_state.change_df, d, "change_menu")
            if ch:
                ch_list.append((d, ch))

    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{o_year}년 {o_month:02d}월 도시락 변경/배달불요 내역입니다.")
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

    txt = "\n".join(lines)
    base_name = _download_basename(o_year, o_month)

    st.text_area("업체 전달용 문구(복사)", value=txt, height=360)

    st.download_button(
        "⬇️ 텍스트 파일 다운로드",
        data=txt.encode("utf-8"),
        file_name=f"{base_name}.txt",
        mime="text/plain",
        use_container_width=True,
    )
