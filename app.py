# app.py (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import html
import io
import zipfile
import re
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# =========================================================
# 기본 설정 / 경로
# =========================================================
st.set_page_config(page_title="맘스락 식단 관리 시스템", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"
HOLIDAYS_PATH = DATA_DIR / "holidays.csv"

AUTO_BK_DIR = DATA_DIR / "autobackup"
AUTO_BK_DIR.mkdir(parents=True, exist_ok=True)

KAPMA_PHONE = "010-7101-5871"

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

DEFAULT_GONGYANG = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

KOR_DOW = ["월", "화", "수", "목", "금", "토", "일"]

# =========================================================
# 유틸리티 함수
# =========================================================
def ensure_csv(path: Path, cols: list[str]) -> None:
    if not path.exists():
        pd.DataFrame(columns=cols).to_csv(path, index=False, encoding="utf-8-sig")

def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False, na_filter=False)
    except Exception:
        return pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=False, na_filter=False)

def save_df(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")

def norm_text(x) -> str:
    if x is None: return ""
    try:
        if pd.isna(x): return ""
    except: pass
    s = str(x).strip()
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return "" if s.lower() == "nan" else s

def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except:
        return None

def safe_text(s: str) -> str:
    return html.escape(s or "")

def b64_image(path: Path) -> str | None:
    if not path.exists(): return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")

def upsert_date_value(df: pd.DataFrame, date_col: str, value_col: str, d: date, v: str) -> pd.DataFrame:
    dstr = d.isoformat()
    v = norm_text(v)
    df = df.copy()
    if df.empty or date_col not in df.columns:
        return pd.DataFrame({date_col: [dstr], value_col: [v]})
    mask = df[date_col].astype(str) == dstr
    if mask.any():
        df.loc[mask, value_col] = v
    else:
        df = pd.concat([df, pd.DataFrame({date_col: [dstr], value_col: [v]})], ignore_index=True)
    return df

def upsert_delivery_no(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    dstr = d.isoformat()
    yn = "Y" if (yn or "").upper().startswith("Y") else "N"
    df = df.copy()
    if df.empty or "date" not in df.columns:
        return pd.DataFrame({"date": [dstr], "delivery": [yn]})
    mask = df["date"].astype(str) == dstr
    if mask.any():
        df.loc[mask, "delivery"] = yn
    else:
        df = pd.concat([df, pd.DataFrame({"date": [dstr], "delivery": [yn]})], ignore_index=True)
    return df

def delete_date_rows(df: pd.DataFrame, d: date, date_col: str = "date") -> pd.DataFrame:
    if df.empty or date_col not in df.columns: return df
    return df[df[date_col].astype(str) != d.isoformat()]

def build_day_maps(year: int, month: int, base_df: pd.DataFrame, chg_df: pd.DataFrame, del_df: pd.DataFrame):
    base_map, chg_map, del_map = {}, {}, {}
    del_exists = set()

    for df, col, target_map in [(base_df, "base_menu", base_map), (chg_df, "change_menu", chg_map)]:
        if not df.empty and {"date", col}.issubset(df.columns):
            for _, r in df.iterrows():
                d = parse_date(r.get("date"))
                if d and d.year == year and d.month == month:
                    target_map[d.day] = norm_text(r.get(col, ""))

    if not del_df.empty and {"date", "delivery"}.issubset(del_df.columns):
        for _, r in del_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                del_exists.add(d.day)
                del_map[d.day] = str(r.get("delivery", "N")).upper().startswith("Y")

    return base_map, chg_map, del_map, del_exists

def make_autobackup_zip(reason: str = "auto") -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = AUTO_BK_DIR / f"{ts}_{reason}.zip"
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH, HOLIDAYS_PATH]:
            if p.exists(): zf.writestr(p.name, p.read_bytes())
    zip_path.write_bytes(mem.getvalue())

# =========================================================
# 공휴일 로직
# =========================================================
def ensure_holidays_seed():
    ensure_csv(HOLIDAYS_PATH, ["date", "name", "auto_delivery_no"])
    df = read_csv(HOLIDAYS_PATH)
    if not df.empty: return
    seed = [("2026-01-01", "신정", "Y"), ("2026-02-16", "설날연휴", "Y"), ("2026-02-17", "설날", "Y"), 
            ("2026-02-18", "설날연휴", "Y"), ("2026-03-01", "삼일절", "Y"), ("2026-05-05", "어린이날", "Y"), 
            ("2026-06-06", "현충일", "Y"), ("2026-08-15", "광복절", "Y"), ("2026-10-03", "개천절", "Y"), ("2026-12-25", "성탄절", "Y")]
    save_df(pd.DataFrame(seed, columns=["date", "name", "auto_delivery_no"]), HOLIDAYS_PATH)

def load_holidays_map_for_month(year, month):
    df = read_csv(HOLIDAYS_PATH)
    hm = {}
    if df.empty: return hm
    for _, r in df.iterrows():
        d = parse_date(r.get("date"))
        if d and d.year == year and d.month == month:
            if str(r.get("auto_delivery_no", "Y")).upper().startswith("Y"):
                hm[d.day] = norm_text(r.get("name", "")) or "공휴일"
    return hm

# =========================================================
# 요약 및 리포트
# =========================================================
def build_vendor_summary_text(year, month, base_map, chg_map, del_map) -> str:
    lines = ["동약협회입니다.", f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.", ""]
    
    del_days = sorted([d for d, v in del_map.items() if v])
    if del_days:
        lines.append("🚫【배달불요】")
        for d in del_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            lines.append(f"▶ {month:02d}/{d:02d}({dow}) : 배달불요")
        lines.append("")

    chg_days = sorted([d for d, v in chg_map.items() if v])
    if chg_days:
        lines.append("🔁【변경메뉴】")
        for d in chg_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            before = base_map.get(d, "기본없음")
            after = chg_map[d]
            lines.append(f"▶ {month:02d}/{d:02d}({dow}) : {before} → {after}")
        lines.append("")

    lines.append("감사합니다.")
    return "\n".join(lines)

# =========================================================
# HTML 생성 (포스터/출력)
# =========================================================
def make_calendar_table_html(year, month, base_map, chg_map, del_map, holiday_map, a4=False):
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    rows = ["<tr>" + "".join([f"<th>{d}</th>" for d in KOR_DOW]) + "</tr>"]

    for w in weeks:
        tds = []
        for day in w:
            if day == 0: tds.append("<td class='empty'></td>")
            else:
                cls = "delivery" if del_map.get(day) else ("change" if chg_map.get(day) else "normal")
                lines = [f"<div class='d'>{day:02d}</div>"]
                if day in holiday_map: lines.append(f"<div class='tag tag-hol'>🎌 {holiday_map[day]}</div>")
                if del_map.get(day): lines.append("<div class='tag tag-del'>🚫 배달불요</div>")
                if chg_map.get(day): lines.append(f"<div class='tag tag-chg'>🔁 {chg_map[day]}</div>")
                elif base_map.get(day): lines.append(f"<div class='tag tag-base'>▫ {base_map[day]}</div>")
                tds.append(f"<td class='{cls}'>" + "".join(lines) + "</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")

    cell_h = "21mm" if a4 else "110px"
    return f'<table class="cal">{"".join(rows)}</table><style>table.cal{{width:100%;border-collapse:separate;border-spacing:5px;table-layout:fixed;}}table.cal th{{padding:5px;font-size:12px;opacity:0.7;}}table.cal td{{vertical-align:top;border:1px solid #eee;border-radius:10px;padding:8px;height:{cell_h};}}.empty{{border:none !important;}}.normal{{background:#fff;}}.change{{background:#fff9e6;border-color:#ffe0b3 !important;}}.delivery{{background:#fff0f0;border-color:#ffcccc !important;}}.d{{font-weight:900;font-size:14px;}}.tag{{font-size:11px;font-weight:700;margin-top:2px;}}.tag-hol{{color:#d32f2f;}}.tag-del{{color:#c62828;}}.tag-chg{{color:#ef6c00;}}.tag-base{{color:#555;}}</style>'

def make_poster_html(year, month, people, gongyang, moms_b64, kapma_b64, bowl_b64, base_map, chg_map, del_map, holiday_map, a4=False, summary=""):
    cal_html = make_calendar_table_html(year, month, base_map, chg_map, del_map, holiday_map, a4)
    summary_html = f'<div class="sum-box"><pre>{safe_text(summary)}</pre></div>' if summary else ""
    
    return f"""
    <div class="page" style="width:{'210mm' if a4 else '100%'}; padding:{'10mm' if a4 else '20px'}; background:white; font-family:sans-serif;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <div style="display:flex; align-items:center; gap:10px;">
                {f'<img src="data:image/png;base64,{moms_b64}" style="height:40px;">' if moms_b64 else ''}
                <b style="font-size:20px;">MOMS 도시락</b>
            </div>
            <div style="text-align:right;">
                <b style="font-size:18px;">동약협회</b><br><small>{KAPMA_PHONE}</small>
            </div>
        </div>
        <h1 style="text-align:center; margin:20px 0;">{month}월 식단 변경 안내 ({people}인)</h1>
        <div style="border:1px solid #eee; border-radius:15px; padding:15px; display:flex; align-items:center; gap:20px; margin-bottom:20px;">
            {f'<img src="data:image/png;base64,{bowl_b64}" style="height:60px;">' if bowl_b64 else ''}
            <div style="white-space:pre-line; font-weight:700; color:#444;">{safe_text(gongyang)}</div>
        </div>
        {cal_html}
        {summary_html}
    </div>
    <style>pre{{white-space:pre-wrap; font-size:13px; line-height:1.5; font-weight:700;}}.sum-box{{margin-top:20px; border:1px solid #ddd; border-radius:10px; padding:15px;}}</style>
    """

# =========================================================
# 앱 실행 메인 로직
# =========================================================
ensure_csv(BASE_MENU_PATH, ["date", "base_menu"])
ensure_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
ensure_csv(DELIVERY_PATH, ["date", "delivery"])
ensure_csv(MENU_INDEX_PATH, ["name"])
ensure_holidays_seed()

# 사이드바
st.sidebar.title("📅 식단 관리")
today = date.today()
year = st.sidebar.number_input("연도", 2020, 2099, today.year)
month = st.sidebar.selectbox("월", list(range(1, 13)), index=today.month-1)
people = st.sidebar.number_input("인원", 1, 100, 1)

# 데이터 로드
base_df = read_csv(BASE_MENU_PATH)
chg_df = read_csv(CHANGE_MENU_PATH)
del_df = read_csv(DELIVERY_PATH)
idx_df = read_csv(MENU_INDEX_PATH)
holiday_map = load_holidays_map_for_month(year, month)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)

# 메인 헤더
st.markdown(f"### 🍱 {year}년 {month}월 식단 변경")
st.caption("달력의 날짜 버튼을 클릭하여 메뉴를 수정하세요.")

# 달력 그리드 출력
cols = st.columns(7)
for i, d in enumerate(KOR_DOW): cols[i].centered_text = cols[i].markdown(f"<div style='text-align:center; font-weight:bold;'>{d}</div>", unsafe_allow_html=True)

cal_obj = calendar.Calendar(firstweekday=0)
for week in cal_obj.monthdayscalendar(year, month):
    cols = st.columns(7)
    for i, day in enumerate(week):
        if day == 0: 
            cols[i].write("")
            continue
        
        is_today = (year == today.year and month == today.month and day == today.day)
        btn_label = f"{day:02d}"
        if is_today: btn_label += "\n📌 TODAY"
        if del_map.get(day): btn_label += "\n🚫불요"
        elif chg_map.get(day): btn_label += f"\n🔁{chg_map[day][:5]}.."
        
        # 날짜별 버튼 색상 적용 (오늘 날짜 강조 포함)
        btn_type = "primary" if is_today else "secondary"
        if cols[i].button(btn_label, key=f"btn_{day}", use_container_width=True, type=btn_type):
            st.session_state.sel_day = day
            st.rerun()

# 입력 다이얼로그
if "sel_day" in st.session_state and st.session_state.sel_day:
    sd = st.session_state.sel_day
    d_obj = date(year, month, sd)
    
    @st.dialog(f"{d_obj.isoformat()} ({KOR_DOW[d_obj.weekday()]}) 식단 수정")
    def edit_menu():
        idx_list = ["(직접입력)"] + sorted(idx_df["name"].tolist())
        
        c1, c2 = st.columns(2)
        b_sel = c1.selectbox("기본 메뉴 인덱스", idx_list)
        b_txt = c1.text_input("기본 메뉴 직접입력", value=base_map.get(sd, ""))
        
        c_sel = c2.selectbox("변경 메뉴 인덱스", idx_list)
        c_txt = c2.text_input("변경 메뉴 직접입력", value=chg_map.get(sd, ""))
        
        is_del = st.checkbox("🚫 배달 불요", value=del_map.get(sd, False))
        
        st.divider()
        col_b1, col_b2, col_b3 = st.columns(3)
        if col_b1.button("✅ 저장", use_container_width=True):
            make_autobackup_zip("save")
            final_b = b_sel if b_sel != "(직접입력)" else b_txt
            final_c = c_sel if c_sel != "(직접입력)" else c_txt
            save_df(upsert_date_value(read_csv(BASE_MENU_PATH), "date", "base_menu", d_obj, final_b), BASE_MENU_PATH)
            save_df(upsert_date_value(read_csv(CHANGE_MENU_PATH), "date", "change_menu", d_obj, final_c), CHANGE_MENU_PATH)
            save_df(upsert_delivery_no(read_csv(DELIVERY_PATH), d_obj, "Y" if is_del else "N"), DELIVERY_PATH)
            st.session_state.sel_day = None
            st.rerun()
            
        if col_b2.button("🗑️ 삭제", use_container_width=True, color="red"):
            st.session_state.confirm_del = sd
            
        if col_b3.button("닫기", use_container_width=True):
            st.session_state.sel_day = None
            st.rerun()

        if "confirm_del" in st.session_state and st.session_state.confirm_del == sd:
            st.error("정말 삭제하시겠습니까?")
            if st.button("⚠️ 삭제 확정", use_container_width=True):
                save_df(delete_date_rows(read_csv(BASE_MENU_PATH), d_obj), BASE_MENU_PATH)
                save_df(delete_date_rows(read_csv(CHANGE_MENU_PATH), d_obj), CHANGE_MENU_PATH)
                save_df(delete_date_rows(read_csv(DELIVERY_PATH), d_obj), DELIVERY_PATH)
                st.session_state.sel_day = None
                del st.session_state.confirm_del
                st.rerun()

    edit_menu()

# ---------------------------------------------------------
# 하단 출력물 영역
# ---------------------------------------------------------
st.divider()
tab1, tab2 = st.tabs(["📄 포스터/요약 확인", "📊 메뉴 통계"])

with tab1:
    v_sum = build_vendor_summary_text(year, month, base_map, chg_map, del_map)
    m_b64 = b64_image(MOMS_LOGO_PATH)
    k_b64 = b64_image(KAPMA_LOGO_PATH)
    b_b64 = b64_image(BOWL_PATH)
    
    poster_html = make_poster_html(year, month, people, DEFAULT_GONGYANG, m_b64, k_b64, b_b64, base_map, chg_map, del_map, holiday_map, False, v_sum)
    components.html(poster_html, height=800, scrolling=True)
    
    st.download_button("📥 A4 출력용 HTML 다운로드", 
                       data=make_poster_html(year, month, people, DEFAULT_GONGYANG, m_b64, k_b64, b_b64, base_map, chg_
