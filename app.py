# app.py (통체 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import io
import zipfile
import base64
import urllib.parse

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
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)  -> N = 배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_IMG_PATH = ASSETS_DIR / "gongyang_bowl.png"

KAPMA_PHONE_FIXED = "010-7101-5871"

# -----------------------------
# 유틸
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
    return df[columns].fillna("")

def _to_date_str(d: date) -> str:
    return d.isoformat()

def _b64_bytes(data: bytes, ext: str = "png") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    ext = ext.lower().lstrip(".")
    mime = "png" if ext == "png" else ("jpeg" if ext in ["jpg", "jpeg"] else ext)
    return f"data:image/{mime};base64,{b64}"

def _b64_image_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    ext = path.suffix.lower().lstrip(".") or "png"
    return _b64_bytes(path.read_bytes(), ext=ext)

def _normalize_menu_text(s: str) -> str:
    return (s or "").strip()

def _save_row(df: pd.DataFrame, key_date: str, col: str, value: str) -> pd.DataFrame:
    value = value.strip()
    mask = df["date"] == key_date
    if mask.any():
        df.loc[mask, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": key_date, col: value}])], ignore_index=True)
    return df

def _save_delivery(df: pd.DataFrame, key_date: str, yn: str) -> pd.DataFrame:
    yn = (yn or "").strip().upper()
    if yn not in ["Y", "N", ""]:
        yn = "Y"
    mask = df["date"] == key_date
    if mask.any():
        df.loc[mask, "delivery"] = yn
    else:
        df = pd.concat([df, pd.DataFrame([{"date": key_date, "delivery": yn}])], ignore_index=True)
    return df

def _get_value(df: pd.DataFrame, key_date: str, col: str) -> str:
    sub = df[df["date"] == key_date]
    return "" if len(sub) == 0 else str(sub.iloc[0].get(col, "") or "")

def _get_delivery(df: pd.DataFrame, key_date: str) -> str:
    sub = df[df["date"] == key_date]
    return "" if len(sub) == 0 else str(sub.iloc[0].get("delivery", "") or "")

def _month_title(year: int, month: int) -> str:
    return f"{year}년 {month:02d}월"

def _load_state():
    if "ym" not in st.session_state:
        today = date.today()
        st.session_state.ym = (today.year, today.month)
    if "people_count" not in st.session_state:
        st.session_state.people_count = "1"
    if "moms_logo_b64" not in st.session_state:
        st.session_state.moms_logo_b64 = None
    if "kapma_logo_b64" not in st.session_state:
        st.session_state.kapma_logo_b64 = None
    if "bowl_b64" not in st.session_state:
        st.session_state.bowl_b64 = None

_load_state()

# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
menu_index_df = _read_csv(MENU_INDEX_PATH, ["name"])

menu_index_df["name"] = menu_index_df["name"].fillna("").astype(str).str.strip()
menu_index_df = menu_index_df[menu_index_df["name"] != ""].drop_duplicates().sort_values("name")
menu_index_df.to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")
MENU_INDEX = menu_index_df["name"].tolist()

# -----------------------------
# CSS
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 2.0rem; }
div.stButton > button{ width: 100%; border-radius: 12px !important; font-weight: 800 !important; }
.bg-base { background: rgba(255,255,255,0.96); }
.bg-change { background: rgba(255, 245, 180, 0.62); }
.bg-nodelivery { background: rgba(255, 205, 205, 0.58); }
.bg-both { background: linear-gradient(135deg, rgba(255,245,180,0.62), rgba(255,205,205,0.58)); }
@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');
.poster-wrap{ width:100%; display:flex; justify-content:center; }
.poster{ width:100%; max-width: 980px; background:#fff; border-radius:18px; border: 1px solid rgba(0,0,0,0.10); padding:16px; }
.poster .title{ text-align:center; font-weight: 900; font-size: 36px; margin: 6px 0; }
.poster .subtitle{ text-align:center; font-weight: 800; font-size: 18px; opacity: 0.85; margin-bottom: 10px; }
.poster .midrow{ display:grid; grid-template-columns: 1fr 1.25fr 1fr; gap: 12px; margin-bottom: 12px; }
.poster .logoBox{ border: 1px solid rgba(0,0,0,0.10); border-radius: 16px; padding: 10px; min-height: 110px; display:flex; flex-direction: column; align-items:center; justify-content:center; }
.poster .logoImg{ max-height: 66px; max-width: 100%; object-fit: contain; }
.poster .logoText{ font-weight: 900; font-size: 18px; }
.poster .kapmaPhone{ font-weight: 900; font-size: 15px; opacity: 0.85; }
.poster .gongyangBox{ border: 1px dashed rgba(0,0,0,0.18); border-radius: 16px; padding: 10px; min-height: 110px; display:flex; align-items:center; justify-content:center; text-align:center; font-family: 'Nanum Brush Script', serif; font-size: 28px; }
.poster .dow{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 8px; }
.poster .dow .h{ text-align:center; font-weight: 900; padding: 6px 0; border-radius: 12px; background: rgba(0,0,0,0.04); border: 1px solid rgba(0,0,0,0.08); }
.poster .grid{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.poster .cell{ border: 1px solid rgba(0,0,0,0.10); border-radius: 14px; padding: 10px; min-height: 122px; }
.poster .cell .d{ font-weight: 900; font-size: 18px; margin-bottom: 6px; }
.poster .cell .t{ font-size: 12.8px; line-height: 1.25; margin: 2px 0; }
.poster .cell .t b{ opacity: 0.90; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단 UI
# -----------------------------
st.title("맘스락 식단 변경 프로그램")

top1, top2, top3 = st.columns([1.2, 1.0, 1.8], vertical_alignment="center")

with top1:
    y, m = st.session_state.ym
    month_options = []
    for yy in range(date.today().year - 1, date.today().year + 3):
        for mm in range(1, 13):
            month_options.append((yy, mm))
    idx = month_options.index((y, m)) if (y, m) in month_options else 0
    sel = st.selectbox("월 선택", options=month_options, index=idx, format_func=lambda x: f"{x[0]}-{x[1]:02d}", key="month_select")
    st.session_state.ym = sel

with top2:
    st.session_state.people_count = st.text_input("인원(예: 1인)", value=st.session_state.people_count)

with top3:
    st.caption("로고 업로드(선택)")
    c1, c2, c3 = st.columns(3)
    with c1:
        up = st.file_uploader("MOMS 로고", type=["png", "jpg", "jpeg"], key="up_moms")
        if up is not None:
            st.session_state.moms_logo_b64 = _b64_bytes(up.read(), ext=up.name.split(".")[-1])
    with c2:
        up = st.file_uploader("동약협회 로고", type=["png", "jpg", "jpeg"], key="up_kapma")
        if up is not None:
            st.session_state.kapma_logo_b64 = _b64_bytes(up.read(), ext=up.name.split(".")[-1])
    with c3:
        up = st.file_uploader("그릇 그림", type=["png", "jpg", "jpeg"], key="up_bowl")
        if up is not None:
            st.session_state.bowl_b64 = _b64_bytes(up.read(), ext=up.name.split(".")[-1])

st.divider()

# -----------------------------
# 백업/복원
# -----------------------------
b1, b2 = st.columns([1.0, 1.0])
with b1:
    if st.button("백업 ZIP 만들기"):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH]:
                if p.exists(): z.writestr(p.name, p.read_bytes())
        mem.seek(0)
        st.download_button("ZIP 다운로드", data=mem.getvalue(), file_name=f"moms_diet_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip", mime="application/zip")
with b2:
    up = st.file_uploader("백업 ZIP 복원", type=["zip"], key="up_zip")
    if up is not None:
        try:
            b = io.BytesIO(up.read())
            with zipfile.ZipFile(b, "r") as z:
                names = z.namelist()
                for fname in ["base_menu.csv", "change_menu.csv", "delivery.csv", "menu_index.csv"]:
                    if fname in names: (DATA_DIR / fname).write_bytes(z.read(fname))
            st.success("복원 완료")
            st.rerun()
        except Exception as e: st.error(f"복원 실패: {e}")

st.divider()

# -----------------------------
# 입력 다이얼로그
# -----------------------------
@st.dialog("식단 입력")
def edit_day_dialog(d: date):
    dstr = _to_date_str(d)
    cur_base = _get_value(base_df, dstr, "base_menu")
    cur_change = _get_value(change_df, dstr, "change_menu")
    cur_del = _get_delivery(delivery_df, dstr)

    st.subheader(d.strftime("%Y-%m-%d (%a)"))
    
    st.markdown("**기본 메뉴**")
    c1, c2 = st.columns([1, 2])
    with c1: b_pick = st.selectbox("인덱스", ["(선택 없음)"] + MENU_INDEX, index=0, key=f"b_pick_{dstr}")
    with c2: base_text = st.text_input("직접 입력", value=cur_base, key=f"b_txt_{dstr}")
    if b_pick != "(선택 없음)": base_text = b_pick

    st.markdown("**변경 메뉴**")
    c3, c4 = st.columns([1, 2])
    with c3: ch_pick = st.selectbox("인덱스", ["(선택 없음)"] + MENU_INDEX, index=0, key=f"c_pick_{dstr}")
    with c4: change_text = st.text_input("직접 입력", value=cur_change, key=f"c_txt_{dstr}")
    if ch_pick != "(선택 없음)": change_text = ch_pick

    st.markdown("**배달**")
    del_opt = st.radio("배달 여부", options=["배달", "배달불요"], index=0 if (cur_del or "Y") != "N" else 1, horizontal=True, key=f"del_{dstr}")
    yn = "Y" if del_opt == "배달" else "N"

    st.divider()
    if st.button("저장", use_container_width=True):
        b2 = _normalize_menu_text(base_text)
        c2 = _normalize_menu_text(change_text)
        
        # 다시 읽어서 저장(동시성 방지)
        _df_b = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
        _df_c = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
        _df_d = _read_csv(DELIVERY_PATH, ["date", "delivery"])

        _save_row(_df_b, dstr, "base_menu", b2).to_csv(BASE_MENU_PATH, index=False, encoding="utf-8-sig")
        _save_row(_df_c, dstr, "change_menu", c2).to_csv(CHANGE_MENU_PATH, index=False, encoding="utf-8-sig")
        _save_delivery(_df_d, dstr, yn).to_csv(DELIVERY_PATH, index=False, encoding="utf-8-sig")

        # 인덱스 자동 추가
        new_items = [x for x in [b2, c2] if x]
        if new_items:
            idx_df = _read_csv(MENU_INDEX_PATH, ["name"])
            for it in new_items: idx_df = pd.concat([idx_df, pd.DataFrame([{"name": it}])], ignore_index=True)
            idx_df["name"] = idx_df["name"].str.strip()
            idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name").to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")
        
        st.rerun()

# -----------------------------
# 달력 렌더링
# -----------------------------
y, m = st.session_state.ym
cal = calendar.Calendar(firstweekday=0)
days_mon_fri = [d for d in cal.itermonthdates(y, m) if d.month == m and d.weekday() < 5]
first_wd = date(y, m, 1).weekday()
pad_left = first_wd if first_wd < 5 else 0
cells = [None] * pad_left + days_mon_fri
while len(cells) % 5 != 0: cells.append(None)

def _cell_bg_and_lines(d: date):
    ds = _to_date_str(d)
    b = _get_value(base_df, ds, "base_menu").strip()
    c = _get_value(change_df, ds, "change_menu").strip()
    del_ = _get_delivery(delivery_df, ds).strip().upper()
    no_del = (del_ == "N")
    bg = "bg-both" if (c and no_del) else ("bg-change" if c else ("bg-nodelivery" if no_del else "bg-base"))
    lines = []
    if b: lines.append(("기본", b))
    if c: lines.append(("변경", c))
    if no_del: lines.append(("배달", "불요"))
    return bg, lines

st.subheader(_month_title(y, m))
wcols = st.columns(5)
for i, w in enumerate(["월", "화", "수", "목", "금"]):
    with wcols[i]: st.markdown(f"**{w}**")

rows = [cells[i:i+5] for i in range(0, len(cells), 5)]
for r in rows:
    cols = st.columns(5, gap="small")
    for i, d in enumerate(r):
        with cols[i]:
            if d:
                if st.button(f"{d.day}", key=f"day_{_to_date_str(d)}", use_container_width=True): edit_day_dialog(d)

st.divider()

# -----------------------------
# 포스터 & A4 생성
# -----------------------------
moms_b64 = st.session_state.moms_logo_b64 or _b64_image_if_exists(MOMS_LOGO_PATH)
kapma_b64 = st.session_state.kapma_logo_b64 or _b64_image_if_exists(KAPMA_LOGO_PATH)
bowl_b64 = st.session_state.bowl_b64 or _b64_image_if_exists(BOWL_IMG_PATH)
moms_logo_html = f'<img class="logoImg" src="{moms_b64}" />' if moms_b64 else '<div class="logoText">MOMS</div>'
kapma_logo_html = f'<img class="logoImg" src="{kapma_b64}" />' if kapma_b64 else '<div class="logoText">동약협회</div>'
kapma_box_text = f'<div class="logoText">동약협회</div><div class="kapmaPhone">{KAPMA_PHONE_FIXED}</div>'
gongyang_html = "이 음식이 어디에서 왔는가<br/>내 덕행으로는 받기가 부끄럽네<br/>마음의 온갖 탐욕을 떠나<br/>바른 생각으로 이 공양을 받습니다"
bowl_html = f'<img class="logoImg" src="{bowl_b64}" style="max-height:44px; margin-bottom:6px;" />' if bowl_b64 else ""

def poster_cell_html(d: date | None) -> str:
    if d is None: return '<div class="cell bg-base" style="opacity:.18;"></div>'
    bg, lines = _cell_bg_and_lines(d)
    line_html = "".join([f'<div class="t"><b>{lab}</b> {txt}</div>' for lab, txt in lines[:3]]) or '<div class="t" style="opacity:.35;">&nbsp;</div>'
    return f'<div class="cell {bg}"><div class="d">{d.day}</div>{line_html}</div>'

common_inner_html = f"""
    <div class="title">맘스락 {m:02d}월 식단(배달) 변경</div>
    <div class="subtitle">( 인원 : {st.session_state.people_count.strip() or "1"}인 )</div>
    <div class="midrow">
      <div class="logoBox">{moms_logo_html}<div class="logoText">MOMS</div></div>
      <div class="gongyangBox"><div>{bowl_html}{gongyang_html}</div></div>
      <div class="logoBox">{kapma_logo_html}{kapma_box_text}</div>
    </div>
    <div class="dow"><div class="h">월</div><div class="h">화</div><div class="h">수</div><div class="h">목</div><div class="h">금</div></div>
    <div class="grid">{''.join(poster_cell_html(d) for d in cells)}</div>
"""

st.subheader("포스터 미리보기")
components.html(f'<div class="poster-wrap"><div class="poster">{common_inner_html}</div></div>', height=900, scrolling=True)

# -----------------------------
# ✅ 신규 기능: 업체 전달용 문자 메시지 생성
# -----------------------------
st.divider()
st.subheader("📱 업체(맘스락) 전달용 문자 생성")

def generate_sms():
    sms_lines = []
    sms_lines.append(f"[맘스락] {m}월 식단 변경 및 배송 안내")
    sms_lines.append(f"안녕하세요, 동약협회입니다. {m}월 식단 변경 사항입니다.")
    sms_lines.append("")
    
    has_changes = False
    # 이번 달의 모든 평일 순회하며 변경/배송불요 체크
    for d in days_mon_fri:
        ds = _to_date_str(d)
        b = _get_value(base_df, ds, "base_menu").strip()
        c = _get_value(change_df, ds, "change_menu").strip()
        del_ = _get_delivery(delivery_df, ds).strip().upper()
        
        day_str = d.strftime("%m/%d(%a)")
        
        if c or del_ == "N":
            has_changes = True
            if del_ == "N":
                sms_lines.append(f"● {day_str}: 배송 불요 (취소)")
            elif c:
                sms_lines.append(f"● {day_str}: {b} → {c}")

    if not has_changes:
        sms_lines.append("변경 사항 없음 (기본 식단)")
    
    sms_lines.append("")
    sms_lines.append(f"총 인원: {st.session_state.people_count}")
    sms_lines.append("확인 부탁드립니다. 감사합니다.")
    
    return "\n".join(sms_lines)

sms_text = generate_sms()

c1, c2 = st.columns([2, 1])
with c1:
    st.text_area("문자 내용 (복사해서 사용하세요)", value=sms_text, height=300)
with c2:
    st.info("위 내용을 복사하여 맘스락 담당자에게 전송하세요.")
    # 모바일에서 바로 메시지 앱을 열 수 있는 링크 (선택 사항)
    encoded_sms = urllib.parse.quote(sms_text)
    st.markdown(f'''
        <a href="sms:?body={encoded_sms}" style="text-decoration:none;">
            <button style="width:100%; height:50px; border-radius:12px; background-color:#25D366; color:white; font-weight:bold; border:none; cursor:pointer;">
                📱 모바일에서 문자 보내기
            </button>
        </a>
    ''', unsafe_allow_html=True)

# -----------------------------
# A4 HTML 다운로드 (기존 유지)
# -----------------------------
st.divider()
st.subheader("업체 전달용 A4 출력")
# (A4 빌드 로직은 생략/기존과 동일하게 build_a4_html() 호출)
