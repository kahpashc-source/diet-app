from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import re
import unicodedata
import io

import pandas as pd
import streamlit as st

# -----------------------------
# 1. 기본 설정 및 경로
# -----------------------------
st.set_page_config(
    page_title="맘스락 식단 관리 시스템",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
ASSETS_DIR = APP_DIR / "assets"
for d in [DATA_DIR, ASSETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 파일 경로
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
DOSIRAK_PATH = ASSETS_DIR / "dosirak.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

GONGYANG_TEXT = (
    "이 음식이 어디에서 왔는가\n"
    "내 덕행으로는 받기가 부끄럽네\n"
    "마음의 온갖 탐욕을 떠나\n"
    "몸을 지탱하는 약으로 알아\n"
    "이 공양을 받습니다"
)

WEEKDAYS_KO = ["월", "화", "수", "목", "금"]

# -----------------------------
# 2. 유틸리티 함수
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
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols].fillna("")
    except:
        return pd.DataFrame(columns=cols)

def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

def _get_value(df: pd.DataFrame, d: date, col: str) -> str:
    k = d.strftime("%Y-%m-%d")
    row = df[df["date"] == k]
    return str(row.iloc[0][col]).strip() if not row.empty else ""

def _set_value(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    k = d.strftime("%Y-%m-%d")
    value = _normalize_text(value)
    if (df["date"] == k).any():
        df.loc[df["date"] == k, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": k, col: value}])], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.sort_values("date").reset_index(drop=True)

def _img_to_b64(path: Path) -> str | None:
    if not path.exists(): return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")

# -----------------------------
# 3. 세션 상태 및 스타일(CSS)
# -----------------------------
if "base_df" not in st.session_state:
    st.session_state.base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
if "change_df" not in st.session_state:
    st.session_state.change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
if "delivery_df" not in st.session_state:
    st.session_state.delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
if "menu_index_df" not in st.session_state:
    st.session_state.menu_index_df = _read_csv(MENU_INDEX_PATH, ["name"])

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');
.block-container { padding-top: 1.5rem; }

/* 초기 타이틀 배너 구역 */
.hero-container {
    background: linear-gradient(to right, #ffffff, #fdfaf5);
    border-radius: 25px;
    padding: 30px;
    border: 1px solid #efebe9;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
    margin-bottom: 25px;
}

.moms-title {
    font-family: 'Noto Serif KR', serif;
    font-size: 2.5rem;
    font-weight: 700;
    color: #3e2723;
    margin: 0;
}

.gongyang-card {
    background: white;
    border-left: 5px solid #d4a373;
    padding: 20px;
    border-radius: 5px 15px 15px 5px;
    box-shadow: 3px 3px 10px rgba(0,0,0,0.02);
}

.gongyang-text {
    font-family: 'Noto Serif KR', serif;
    font-size: 1.15rem;
    line-height: 1.6;
    color: #4e342e;
    white-space: pre-line;
    font-weight: 700;
}

/* 달력 스타일 */
.cal-head { text-align:center; font-weight:800; color:#d4a373; padding-bottom: 10px; }
.stButton>button {
    border-radius: 15px; border: 1px solid #f0f0f0; min-height: 110px;
    background: white; transition: 0.3s; text-align: left !important;
}
.stButton>button:hover { border-color: #d4a373; transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
.today-highlight { border: 2.5px solid #d4a373 !important; background: #fffcf9 !important; }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# 4. 초기 타이틀 화면 구성 (Header)
# -----------------------------
def render_initial_screen():
    st.markdown('<div class="hero-container">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.2, 1, 1.3], gap="medium")
    
    with c1:
        # 맘스로고와 타이틀
        sub_c1, sub_c2 = st.columns([0.4, 1])
        with sub_c1:
            if MOMS_LOGO_PATH.exists(): st.image(str(MOMS_LOGO_PATH), width=80)
            else: st.title("🍱")
        with sub_c2:
            st.markdown('<p class="moms-title">맘스락</p>', unsafe_allow_html=True)
            st.caption("MOM'S RAK | 정성을 담은 공양 식단")
        
        st.write("")
        # 도시락 그림
        if DOSIRAK_PATH.exists():
            st.image(str(DOSIRAK_PATH), use_container_width=True)
        else:
            st.info("assets/dosirak.png 이미지를 넣어주세요.")

    with c2:
        # 공양 그릇 이미지
        st.write("")
        if BOWL_PATH.exists():
            st.image(str(BOWL_PATH), use_container_width=True)
        else:
            st.markdown("<div style='text-align:center; padding:40px; border:1px dashed #ccc; border-radius:20px;'>🥣 공양그릇 이미지 영역</div>", unsafe_allow_html=True)

    with c3:
        # 공양게 카드
        st.markdown(f"""
        <div class="gongyang-card">
            <p style="color:#d4a373; font-weight:bold; margin-bottom:10px;">供養偈</p>
            <div class="gongyang-text">{GONGYANG_TEXT}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

render_initial_screen()

# -----------------------------
# 5. 메인 기능 영역 (달력 입력)
# -----------------------------
tab1, tab2, tab3 = st.tabs(["🗓️ 식단 입력", "📜 포스터 출력", "💬 업체 전달"])

with tab1:
    # 달력 컨트롤
    curr = date.today()
    col_sel1, col_sel2 = st.columns([1, 4])
    with col_sel1:
        sel_year = st.selectbox("연도", [curr.year, curr.year+1], index=0)
        sel_month = st.selectbox("월", list(range(1, 13)), index=curr.month-1)
    with col_sel2:
        st.markdown("<div style='margin-top:35px; color:gray;'>* 토/일요일은 표시되지 않으며 평일 식단만 관리합니다.</div>", unsafe_allow_html=True)

    # 요일 표시 (월~금)
    hcols = st.columns(5)
    for i, wd in enumerate(WEEKDAYS_KO):
        hcols[i].markdown(f'<div class="cal-head">{wd}</div>', unsafe_allow_html=True)

    # 달력 생성 로직
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(sel_year, sel_month)

    for week in weeks:
        cols = st.columns(5)
        for i in range(5):  # 월~금만 슬라이싱
            d = week[i]
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue
                
                # 데이터 확인
                base = _get_value(st.session_state.base_df, d, "base_menu")
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no_deliv = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"
                
                # 버튼 라벨 구성
                btn_label = f"**{d.day}**\n"
                if is_no_deliv: btn_label += "🚫 배달불요\n"
                if change: btn_label += f"🔁 {change[:10]}\n"
                elif base: btn_label += f"🍚 {base[:10]}\n"
                
                # 오늘 날짜 강조용 래퍼
                if d == curr: st.markdown('<div class="today-highlight">', unsafe_allow_html=True)
                if st.button(btn_label, key=f"btn_{d}", use_container_width=True):
                    # 입력 다이얼로그
                    @st.dialog(f"{d.strftime('%m/%d')} 식단 수정")
                    def edit_dlg(target_date):
                        idx = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()
                        b_sel = st.selectbox("기본 메뉴 인덱스", idx)
                        b_txt = st.text_input("기본 메뉴", value=base if b_sel=="(직접입력)" else b_sel)
                        
                        st.divider()
                        
                        c_sel = st.selectbox("변경 메뉴 인덱스", idx)
                        c_txt = st.text_input("변경 메뉴", value=change if c_sel=="(직접입력)" else c_sel)
                        
                        no_del = st.toggle("배달 불요", value=is_no_deliv)
                        
                        if st.button("저장하기", use_container_width=True, type="primary"):
                            st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_txt)
                            st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_txt)
                            st.session_state.delivery_df = _set_value(st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N")
                            
                            _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                            _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                            _write_csv(st.session_state.delivery_df, DELIVERY_PATH)
                            
                            # 인덱스 업데이트
                            new_names = [n for n in [b_txt, c_txt] if n]
                            if new_names:
                                new_df = pd.concat([st.session_state.menu_index_df, pd.DataFrame({"name": new_names})])
                                st.session_state.menu_index_df = new_df.drop_duplicates().sort_values("name")
                                _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)
                            st.rerun()
                    edit_dlg(d)
                if d == curr: st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.info("포스터 출력 화면은 브라우저 인쇄(Ctrl+P) 기능을 활용해 주세요.")
    # 포스터 HTML 생성 로직 (생략 - 기존 로직 유지 가능)

with tab3:
    st.subheader("업체 전달용 텍스트")
    # 전달 문구 생성 로직 (생략 - 기존 로직 유지 가능)
