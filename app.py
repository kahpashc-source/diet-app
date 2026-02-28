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
