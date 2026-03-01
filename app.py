# app.py (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import io
import re

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

# 파일 경로 정의
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

# 이미지 경로 (부회장님께서 assets 폴더에 넣어주실 파일명들입니다)
KAPMA_LOGO = ASSETS_DIR / "kapma_logo.png"   # 동약협회 로고
MOMS_LOGO = ASSETS_DIR / "moms_logo.png"     # 맘스락 로고
BOWL_IMG = ASSETS_DIR / "gongyang_bowl.png"  # 공양그릇 그림

GONGYANG_VERSE = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
몸을 지탱하는 약으로 알아 이 공양을 받습니다"""

# -----------------------------
# 2. 데이터 처리 유틸리티
# -----------------------------
def _safe_read_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
        for c in cols:
            if c not in df.columns: df[c] = ""
        return df[cols]
    except:
        return pd.DataFrame(columns=cols)

def _save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")

def _b64_image_tag(img_path: Path, height_px: int) -> str:
    if not img_path.exists(): return ""
    b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64}" style="height:{height_px}px; width:auto;">'

def _dow_kr(idx: int) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][idx]

# -----------------------------
# 3. 데이터 로드 및 세션 상태
# -----------------------------
if "base_df" not in st.session_state:
    st.session_state.base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"])
if "chg_df" not in st.session_state:
    st.session_state.chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
if "del_df" not in st.session_state:
    st.session_state.del_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"])
if "idx_df" not in st.session_state:
    st.session_state.idx_df = _safe_read_csv(MENU_INDEX_PATH, ["name"])

# -----------------------------
# 4. 스타일 및 헤더 (디자인 중심)
# -----------------------------
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@700&display=swap');
    .hero-box {{
        background: white; border-radius: 20px; padding: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #eee;
        margin-bottom: 20px; text-align: center;
    }}
    .main-title {{ font-size: 32px; font-weight: 800; color: #3e2723; margin: 10px 0; }}
    .verse-box {{
        font-family: 'Noto Serif KR', serif; font-size: 19px; line-height: 1.6;
        color: #4e342e; background: #fdfaf5; padding: 20px;
        border-radius: 15px; border-left: 5px solid #d4a373;
        display: inline-block; text-align: left; margin-top: 15px;
    }}
    .cal-btn button {{
        height: 100px !important; border-radius: 12px !important;
        background: #ffffff !important; border: 1px solid #eee !important;
        transition: 0.2s;
    }}
    .cal-btn button:hover {{ border-color: #d4a373 !important; background: #fffcf9 !important; }}
</style>
""", unsafe_allow_html=True)

# 상단 배너 출력
with st.container():
    st.markdown('<div class="hero-box">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        st.markdown(_b64_image_tag(MOMS_LOGO, 70), unsafe_allow_html=True)
        st.caption("MOM'S RAK")
    with c2:
        st.markdown('<div class="main-title">맘스락 식단 변경 관리</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="verse-box">{GONGYANG_VERSE.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
    with c3:
        st.markdown(_b64_image_tag(KAPMA_LOGO, 70), unsafe_allow_html=True)
        st.caption("동약협회")
    
    st.write("")
    st.markdown(_b64_image_tag(BOWL_IMG, 80), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# 5. 메인 달력 로직 (월~금 집중)
# -----------------------------
today = date.today()
col_ctrl1, col_ctrl2 = st.columns([1, 4])
with col_ctrl1:
    year = st.selectbox("연도", [today.year, today.year+1], index=0)
    month = st.selectbox("월", list(range(1, 13)), index=today.month-1)

st.markdown("### 🗓️ 주간 식단 설정 (토/일 제외)")

# 요일 헤더
h_cols = st.columns(5)
for i, dname in enumerate(["월", "화", "수", "목", "금"]):
    h_cols[i].markdown(f"<div style='text-align:center; font-weight:bold; color:#d4a373;'>{dname}</div>", unsafe_allow_html=True)

# 달력 생성
cal_obj = calendar.Calendar(firstweekday=0)
weeks = cal_obj.monthdatescalendar(year, month)

for week in weeks:
    cols = st.columns(5)
    for i in range(5): # 월(0)~금(4)
        d = week[i]
        if d.month != month:
            cols[i].write("")
            continue
        
        # 데이터 매칭
        d_str = d.strftime("%Y-%m-%d")
        base = st.session_state.base_df[st.session_state.base_df["date"] == d_str]
        chg = st.session_state.chg_df[st.session_state.chg_df["date"] == d_str]
        dlv = st.session_state.del_df[st.session_state.del_df["date"] == d_str]
        
        base_val = base["base_menu"].values[0] if not base.empty else ""
        chg_val = chg["change_menu"].values[0] if not chg.empty else ""
        is_no_deliv = dlv["delivery"].values[0] == "N" if not dlv.empty else False
        
        # 버튼 텍스트 구성
        btn_label = f"**{d.day}일**\n"
        if is_no_deliv: btn_label += "🚫 배달불요\n"
        if chg_val: btn_label += f"🔁 {chg_val[:10]}\n"
        elif base_val: btn_label += f"🍚 {base_val[:10]}\n"

        with cols[i]:
            st.markdown('<div class="cal-btn">', unsafe_allow_html=True)
            if st.button(btn_label, key=f"btn_{d_str}", use_container_width=True):
                @st.dialog(f"{d.month}월 {d.day}일 식단 수정")
                def edit_dialog(target_date=d, t_str=d_str):
                    st.markdown(f"**날짜: {target_date} ({_dow_kr(target_date.weekday())})**")
                    
                    # 인덱스 불러오기
                    idx_list = ["(직접입력)"] + st.session_state.idx_df["name"].tolist()
                    
                    new_base = st.text_input("기본 메뉴", value=base_val)
                    st.caption("또는 인덱스에서 선택:")
                    base_sel = st.selectbox("기본 메뉴 선택", idx_list, key="bsel")
                    
                    st.divider()
                    
                    new_chg = st.text_input("변경 메뉴 (필요 시)", value=chg_val)
                    st.caption("또는 인덱스에서 선택:")
                    chg_sel = st.selectbox("변경 메뉴 선택", idx_list, key="csel")
                    
                    no_deliv = st.toggle("배달 불요 (도시락 안 받음)", value=is_no_deliv)

                    if st.button("저장하기", use_container_width=True, type="primary"):
                        # 데이터 업데이트 로직
                        final_base = base_sel if base_sel != "(직접입력)" else new_base
                        final_chg = chg_sel if chg_sel != "(직접입력)" else new_chg
                        
                        # 세션 및 파일 저장 (함수 생략, 실제 적용 시 위 정의된 set_base 등 활용)
                        # 여기서는 간단히 세션 직접 수정 후 저장
                        def update_df(df_name, col, val):
                            df = st.session_state[df_name].copy()
                            df = df[df["date"] != t_str]
                            if val:
                                df = pd.concat([df, pd.DataFrame([{"date": t_str, col: val}])], ignore_index=True)
                            st.session_state[df_name] = df.sort_values("date")

                        update_df("base_df", "base_menu", final_base)
                        update_df("chg_df", "change_menu", final_chg)
                        update_df("del_df", "delivery", "N" if no_deliv else "Y")
                        
                        _save_csv(st.session_state.base_df, BASE_MENU_PATH)
                        _save_csv(st.session_state.chg_df, CHANGE_MENU_PATH)
                        _save_csv(st.session_state.del_df, DELIVERY_PATH)
                        
                        # 인덱스 추가
                        if final_base and final_base not in st.session_state.idx_df["name"].values:
                             new_idx = pd.concat([st.session_state.idx_df, pd.DataFrame([{"name": final_base}])]).drop_duplicates().sort_values("name")
                             st.session_state.idx_df = new_idx
                             _save_csv(new_idx, MENU_INDEX_PATH)

                        st.rerun()
                edit_dialog()
            st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# 6. 하단 정보 (전달용 문구)
# -----------------------------
st.divider()
st.subheader("💬 업체 제출용 요약")
if st.button("이번 달 변경 내역 텍스트 생성"):
    summary = []
    summary.append(f"동약협회 {month}월 식단 변경 내역입니다.\n")
    # 상세 로직 구현...
    st.code("\n".join(summary))

st.info("포스터 출력은 상단 달력 설정 후 브라우저 인쇄 기능을 활용해 주세요.")
