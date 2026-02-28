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

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
DOSIRAK_PATH_JPG = ASSETS_DIR / "dosirak.jpg"
DOSIRAK_PATH_PNG = ASSETS_DIR / "dosirak.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

GONGYANG_TEXT = (
    "이 음식이 어디에서 왔는가\n"
    "내 덕행으로는 받기가 부끄럽네\n"
    "마음의 온갖 탐욕을 떠나\n"
    "몸을 지탱하는 약으로 알아\n"
    "이 공양을 받습니다"
)

WEEKDAYS_KO = ["월", "화", "수", "목", "금"]  # ✅ 토/일 제외

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


def _ensure_date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_value(df: pd.DataFrame, d: date, col: str) -> str:
    key = _ensure_date_str(d)
    row = df[df["date"] == key]
    if row.empty:
        return ""
    return str(row.iloc[0][col] or "").strip()


def _set_value(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    key = _ensure_date_str(d)
    value = _normalize_text(value)
    if (df["date"] == key).any():
        df.loc[df["date"] == key, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": key, col: value}])], ignore_index=True)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _set_delivery(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    key = _ensure_date_str(d)
    yn = "Y" if yn == "Y" else "N"
    if (df["date"] == key).any():
        df.loc[df["date"] == key, "delivery"] = yn
    else:
        df = pd.concat([df, pd.DataFrame([{"date": key, "delivery": yn}])], ignore_index=True)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _img_to_base64(path: Path) -> str | None:
    if not path.exists():
        return None
    b = path.read_bytes()
    return base64.b64encode(b).decode("utf-8")


def _pick_dosirak_path() -> Path | None:
    if DOSIRAK_PATH_JPG.exists():
        return DOSIRAK_PATH_JPG
    if DOSIRAK_PATH_PNG.exists():
        return DOSIRAK_PATH_PNG
    return None


def _is_weekday(d: date) -> bool:
    return d.weekday() <= 4  # 월(0)~금(4)


# -----------------------------
# 세션 상태 초기화(핵심)
# -----------------------------
def _init_state():
    if "base_df" not in st.session_state:
        st.session_state.base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    if "change_df" not in st.session_state:
        st.session_state.change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    if "delivery_df" not in st.session_state:
        st.session_state.delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
    if "menu_index_df" not in st.session_state:
        df = _read_csv(MENU_INDEX_PATH, ["name"])
        df["name"] = df["name"].map(_normalize_text)
        df = df[df["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
        st.session_state.menu_index_df = df

_init_state()

# 편의 참조
base_df: pd.DataFrame = st.session_state.base_df
change_df: pd.DataFrame = st.session_state.change_df
delivery_df: pd.DataFrame = st.session_state.delivery_df
menu_index_df: pd.DataFrame = st.session_state.menu_index_df

# -----------------------------
# 스타일(CSS)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 1.5rem; }

.hero {
  border-radius: 18px;
  padding: 18px 18px;
  background: linear-gradient(135deg, rgba(255,241,220,0.75), rgba(255,255,255,0.85));
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 6px 18px rgba(0,0,0,0.06);
  margin-bottom: 14px;
}
.hero-title { font-size: 30px; font-weight: 800; line-height: 1.1; margin: 0; }
.hero-sub { font-size: 14px; opacity: 0.75; margin-top: 6px; margin-bottom: 0; }

.gongyang-box{
  border-radius: 14px; padding: 12px 12px;
  background: rgba(255,255,255,0.70);
  border: 1px solid rgba(0,0,0,0.06);
}
.gongyang-title{ font-weight: 800; font-size: 14px; opacity: 0.80; margin-bottom: 6px; }
.gongyang-text{ font-size: 18px; line-height: 1.35; font-weight: 700; white-space: pre-line; }

.cal-header {
  font-weight: 800; font-size: 14px;
  text-align: center;
  padding: 6px 0 10px 0;
  opacity: 0.85;
}
.cal-btn > button{
  width: 100% !important;
  text-align: left !important;
  border-radius: 14px !important;
  padding: 10px 10px !important;
  min-height: 110px !important;
  border: 1px solid rgba(0,0,0,0.10) !important;
  background: rgba(255,255,255,0.85) !important;
  white-space: pre-line !important;
}
.today-outline{
  outline: 3px solid rgba(255, 170, 0, 0.65);
  outline-offset: -3px;
  border-radius: 14px;
}
.small-muted{ font-size: 12px; opacity: 0.70; }
hr{ margin: 12px 0; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단 메인 비주얼
# -----------------------------
logo_b64 = _img_to_base64(MOMS_LOGO_PATH)
bowl_b64 = _img_to_base64(BOWL_PATH)
dosirak_path = _pick_dosirak_path()

colA, colB = st.columns([1.35, 1.0], vertical_alignment="top")

with colA:
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([0.55, 0.8, 1.15], vertical_alignment="center")

    with c1:
        if logo_b64:
            st.image(MOMS_LOGO_PATH, use_container_width=True)
        else:
            st.markdown("**MOMS**\n\n(assets/moms_logo.png 추가 시 로고 표시)")

    with c2:
        if dosirak_path and dosirak_path.exists():
            st.image(dosirak_path, use_container_width=True)
        else:
            st.markdown("🍱 **도시락 이미지(선택)**\n\nassets/dosirak.jpg 또는 dosirak.png")

    with c3:
        if bowl_b64:
            st.image(BOWL_PATH, use_container_width=True)
        else:
            st.markdown("🥣 **공양 그릇 이미지(선택)**\n\nassets/gongyang_bowl.png")

    st.markdown(
        """
<p class="hero-title">맘스락 식단(배달) 변경</p>
<p class="hero-sub">월~금 입력에 최적화 (토/일은 표시하지 않습니다)</p>
""",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

with colB:
    st.markdown(
        f"""
<div class="gongyang-box">
  <div class="gongyang-title">공양게(供養偈)</div>
  <div class="gongyang-text">{GONGYANG_TEXT}</div>
  <div class="small-muted" style="text-align:right;margin-top:8px;">— 마음을 가다듬고 한 끼를 받습니다</div>
</div>
""",
        unsafe_allow_html=True,
    )

st.markdown("<hr/>", unsafe_allow_html=True)

# -----------------------------
# 상단 컨트롤(월 선택) - 1달만 표시
# -----------------------------
today = date.today()
years = list(range(today.year - 1, today.year + 3))
left, right = st.columns([1.1, 1.4], vertical_alignment="center")

with left:
    sel_year = st.selectbox("년도", years, index=years.index(today.year))
    sel_month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

with right:
    st.caption("✅ 달력은 **1달분만** 표시됩니다.  ✅ 토/일은 제외(월~금만)")

# -----------------------------
# 날짜 클릭 → 입력(대화상자)
# -----------------------------
def open_editor(d: date):
    if not _is_weekday(d):
        st.toast("토/일은 입력 대상에서 제외됩니다.")
        return

    base_now = _get_value(st.session_state.base_df, d, "base_menu")
    change_now = _get_value(st.session_state.change_df, d, "change_menu")
    delivery_now = _get_value(st.session_state.delivery_df, d, "delivery")
    delivery_now = delivery_now if delivery_now in ("Y", "N") else "N"

    @st.dialog(f"{d.strftime('%Y-%m-%d')} ({WEEKDAYS_KO[d.weekday()]}) 입력")
    def _dlg():
        idx_list = st.session_state.menu_index_df["name"].tolist()

        st.markdown("아래에서 **기본/변경/배달불요**를 입력 후 저장하세요.")
        st.divider()

        c1, c2 = st.columns([1.0, 1.0])

        with c1:
            st.markdown("**기본메뉴**")
            pick_base = st.selectbox("인덱스에서 선택(선택)", ["(직접입력)"] + idx_list, index=0, key=f"pb_{d}")
            base_text = st.text_input("기본메뉴(직접 입력)", value=base_now, key=f"bt_{d}")
            if pick_base != "(직접입력)":
                base_text = pick_base

        with c2:
            st.markdown("**변경메뉴**")
            pick_change = st.selectbox("인덱스에서 선택(선택)", ["(직접입력)"] + idx_list, index=0, key=f"pc_{d}")
            change_text = st.text_input("변경메뉴(직접 입력)", value=change_now, key=f"ct_{d}")
            if pick_change != "(직접입력)":
                change_text = pick_change

        st.divider()
        delivery_flag = st.toggle("🚫 배달불요(체크하면 배달불요)", value=(delivery_now == "Y"), key=f"dv_{d}")
        st.divider()

        cc1, cc2 = st.columns([1, 1], vertical_alignment="center")

        with cc1:
            if st.button("💾 저장", use_container_width=True):
                # 1) 세션 DF 갱신
                st.session_state.base_df = _set_value(st.session_state.base_df, d, "base_menu", base_text)
                st.session_state.change_df = _set_value(st.session_state.change_df, d, "change_menu", change_text)
                st.session_state.delivery_df = _set_delivery(st.session_state.delivery_df, d, "Y" if delivery_flag else "N")

                # 2) 파일 저장
                _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                # 3) 인덱스 자동 축적 + 가나다 정렬
                new_items = []
                for v in [base_text, change_text]:
                    v = _normalize_text(v)
                    if v:
                        new_items.append(v)

                if new_items:
                    idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame({"name": new_items})], ignore_index=True)
                    idx["name"] = idx["name"].map(_normalize_text)
                    idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                    st.session_state.menu_index_df = idx
                    _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)

                st.success("저장했습니다.")
                st.rerun()

        with cc2:
            if st.button("🧹 해당일 비우기", use_container_width=True):
                key = _ensure_date_str(d)
                st.session_state.base_df = st.session_state.base_df[st.session_state.base_df["date"] != key].reset_index(drop=True)
                st.session_state.change_df = st.session_state.change_df[st.session_state.change_df["date"] != key].reset_index(drop=True)
                st.session_state.delivery_df = st.session_state.delivery_df[st.session_state.delivery_df["date"] != key].reset_index(drop=True)

                _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                st.success("삭제했습니다.")
                st.rerun()

    _dlg()

# -----------------------------
# 달력(월~금만) + 요일 표시
# -----------------------------
st.subheader(f"{sel_year}년 {sel_month:02d}월 (월~금)")

hcols = st.columns(5)
for i, wd in enumerate(WEEKDAYS_KO):
    hcols[i].markdown(f'<div class="cal-header">{wd}</div>', unsafe_allow_html=True)

cal = calendar.Calendar(firstweekday=0)  # Monday
weeks = cal.monthdatescalendar(sel_year, sel_month)

for week in weeks:
    day_list = week[:5]  # ✅ 월~금
    cols = st.columns(5)

    for i, d in enumerate(day_list):
        with cols[i]:
            if d.month != sel_month:
                st.button(" ", disabled=True, key=f"blank_{sel_year}_{sel_month}_{week[0]}_{i}")
                continue

            base_v = _get_value(st.session_state.base_df, d, "base_menu")
            change_v = _get_value(st.session_state.change_df, d, "change_menu")
            deliv_v = _get_value(st.session_state.delivery_df, d, "delivery")
            deliv_v = deliv_v if deliv_v in ("Y", "N") else "N"

            badges = []
            lines = []

            if deliv_v == "Y":
                badges.append("🚫배달불요")
                lines.append("배달: 불요")
            if change_v:
                badges.append("🔁변경")
                lines.append(f"변경: {change_v}")
            if base_v:
                badges.append("🍚기본")
                lines.append(f"기본: {base_v}")

            top = f"{d.day:02d}"
            if badges:
                top += "  " + " · ".join(badges)

            text = top
            if lines:
                text += "\n" + "\n".join(lines[:3])

            wrap_class = "today-outline" if d == today else ""
            st.markdown(f'<div class="{wrap_class}">', unsafe_allow_html=True)
            clicked = st.button(text, key=f"day_{d}", help="클릭하면 입력창이 뜹니다.")
            st.markdown("</div>", unsafe_allow_html=True)

            if clicked:
                open_editor(d)

st.divider()

# -----------------------------
# 인덱스 관리(가나다 자동정렬)
# -----------------------------
st.markdown("### 메뉴 인덱스(가나다 순)")
cL, cR = st.columns([1.2, 1.0], vertical_alignment="top")

with cL:
    new_item = st.text_input("인덱스에 메뉴 추가", placeholder="예) 소고기미역국, 제육볶음 ...")
    if st.button("➕ 인덱스에 추가"):
        v = _normalize_text(new_item)
        if v:
            idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame([{"name": v}])], ignore_index=True)
            idx["name"] = idx["name"].map(_normalize_text)
            idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
            st.session_state.menu_index_df = idx
            _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)
            st.success("추가했습니다.")
            st.rerun()
        else:
            st.warning("메뉴명을 입력해 주세요.")

with cR:
    st.dataframe(st.session_state.menu_index_df, use_container_width=True, height=260)
