# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import io
import zipfile
import base64

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

# 로고/이미지 파일 (없으면 텍스트로 대체)
MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_IMG_PATH = ASSETS_DIR / "gongyang_bowl.png"  # 그릇 그림

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
    df = df[columns].fillna("")
    return df


def _to_date_str(d: date) -> str:
    return d.isoformat()


def _b64_image_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    ext = path.suffix.lower().lstrip(".")
    mime = "png" if ext == "png" else ("jpeg" if ext in ["jpg", "jpeg"] else ext)
    return f"data:image/{mime};base64,{b64}"


def _normalize_menu_text(s: str) -> str:
    return (s or "").strip()


def _save_row(df: pd.DataFrame, key_date: str, col: str, value: str) -> pd.DataFrame:
    value = value.strip()
    mask = df["date"] == key_date
    if mask.any():
        df.loc[mask, col] = value
    else:
        new = pd.DataFrame([{"date": key_date, col: value}])
        df = pd.concat([df, new], ignore_index=True)
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
    if len(sub) == 0:
        return ""
    return str(sub.iloc[0].get(col, "") or "")


def _get_delivery(df: pd.DataFrame, key_date: str) -> str:
    sub = df[df["date"] == key_date]
    if len(sub) == 0:
        return ""
    return str(sub.iloc[0].get("delivery", "") or "")


def _month_title(year: int, month: int) -> str:
    return f"{year}년 {month:02d}월"


def _load_state():
    if "ym" not in st.session_state:
        today = date.today()
        st.session_state.ym = (today.year, today.month)
    if "people_count" not in st.session_state:
        st.session_state.people_count = "1"
    if "vendor_name" not in st.session_state:
        st.session_state.vendor_name = "맘스락(MOMS)"
    if "vendor_phone" not in st.session_state:
        st.session_state.vendor_phone = "010-0000-0000"
    if "kapma_phone" not in st.session_state:
        st.session_state.kapma_phone = "02-0000-0000"  # ✅ 여기만 부회장님 번호로 바꾸면 됨


# -----------------------------
# 데이터 로드
# -----------------------------
_load_state()

base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
menu_index_df = _read_csv(MENU_INDEX_PATH, ["name"])

# 메뉴 인덱스 자동 정렬
menu_index_df["name"] = menu_index_df["name"].fillna("").astype(str).str.strip()
menu_index_df = menu_index_df[menu_index_df["name"] != ""].drop_duplicates().sort_values("name")
menu_index_df.to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")
MENU_INDEX = menu_index_df["name"].tolist()

# -----------------------------
# CSS (포스터/출력물 공통)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 2.0rem; }

div.stButton > button{
  width: 100%;
  border-radius: 12px !important;
  padding: 8px 10px !important;
  font-weight: 800 !important;
}

/* 달력 상태 색 */
.bg-base { background: rgba(255,255,255,0.96); }
.bg-change { background: rgba(255, 245, 180, 0.60); }
.bg-nodelivery { background: rgba(255, 205, 205, 0.55); }
.bg-both { background: linear-gradient(135deg, rgba(255,245,180,0.60), rgba(255,205,205,0.55)); }

/* 포스터(스크린샷) */
.poster-wrap{ width:100%; display:flex; justify-content:center; }
.poster{
  width:100%;
  max-width: 980px;
  background:#fff;
  border-radius:18px;
  border: 1px solid rgba(0,0,0,0.10);
  padding:16px 16px 12px 16px;
}
.poster .toprow{ display:flex; align-items:center; justify-content:space-between; gap:12px; }
.poster .logoBox{
  width: 34%;
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 16px;
  padding: 10px;
  display:flex; align-items:center; justify-content:center;
  min-height: 92px;
}
.poster .midBox{
  width: 32%;
  display:flex; align-items:center; justify-content:center;
  min-height: 92px;
}
.poster .title{
  text-align:center;
  font-weight: 900;
  font-size: 34px;
  line-height: 1.10;
  margin-top: 12px;
  margin-bottom: 6px;
}
.poster .subtitle{
  text-align:center;
  font-weight: 800;
  font-size: 18px;
  opacity: 0.85;
  margin-bottom: 12px;
}

/* 달력형태(요일행 + 그리드) */
.poster .dow{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  margin-bottom: 8px;
}
.poster .dow .h{
  text-align:center;
  font-weight: 900;
  padding: 6px 0;
  border-radius: 12px;
  background: rgba(0,0,0,0.04);
  border: 1px solid rgba(0,0,0,0.08);
}

.poster .grid{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}
.poster .cell{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 10px;
  min-height: 122px;
}
.poster .cell .d{ font-weight: 900; font-size: 18px; margin-bottom: 6px; }
.poster .cell .t{ font-size: 12.8px; line-height: 1.25; margin: 2px 0; }
.poster .cell .t b{ opacity: 0.90; }

@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');
.poster .gongyang{
  margin-top: 12px;
  border-top: 1px dashed rgba(0,0,0,0.18);
  padding-top: 12px;
  text-align:center;
  font-family: 'Nanum Brush Script', '궁서', 'Gungsuh', serif;
  font-size: 28px;
  line-height: 1.25;
}

/* A4 출력용(인쇄) */
@page { size: A4; margin: 12mm; }
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
    sel = st.selectbox(
        "월 선택",
        options=month_options,
        index=idx,
        format_func=lambda x: f"{x[0]}-{x[1]:02d}",
        key="month_select",
    )
    st.session_state.ym = sel

with top2:
    st.session_state.people_count = st.text_input("인원(예: 1인)", value=st.session_state.people_count)

with top3:
    c1, c2, c3 = st.columns([1.1, 1.1, 1.1])
    with c1:
        st.session_state.vendor_name = st.text_input("업체명", value=st.session_state.vendor_name)
    with c2:
        st.session_state.vendor_phone = st.text_input("업체 전화", value=st.session_state.vendor_phone)
    with c3:
        st.session_state.kapma_phone = st.text_input("동약협회 전화", value=st.session_state.kapma_phone)

st.caption("로고/이미지 파일: assets/moms_logo.png, assets/kapma_logo.png, assets/gongyang_bowl.png")
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
                if p.exists():
                    z.writestr(p.name, p.read_bytes())
        mem.seek(0)
        st.download_button(
            "ZIP 다운로드",
            data=mem.getvalue(),
            file_name=f"moms_diet_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
        )
with b2:
    up = st.file_uploader("백업 ZIP 복원", type=["zip"])
    if up is not None:
        try:
            b = io.BytesIO(up.read())
            with zipfile.ZipFile(b, "r") as z:
                names = z.namelist()
                for fname in ["base_menu.csv", "change_menu.csv", "delivery.csv", "menu_index.csv"]:
                    if fname in names:
                        (DATA_DIR / fname).write_bytes(z.read(fname))
            st.success("복원 완료")
            st.rerun()
        except Exception as e:
            st.error(f"복원 실패: {e}")

st.divider()

# -----------------------------
# 입력 다이얼로그
# -----------------------------
@st.dialog("식단 입력")
def edit_day_dialog(d: date):
    dstr = _to_date_str(d)

    _base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    _change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    _delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
    _menu_index_df = _read_csv(MENU_INDEX_PATH, ["name"])

    cur_base = _get_value(_base_df, dstr, "base_menu")
    cur_change = _get_value(_change_df, dstr, "change_menu")
    cur_del = _get_delivery(_delivery_df, dstr)

    _menu_index_df["name"] = _menu_index_df["name"].fillna("").astype(str).str.strip()
    _menu_index_df = _menu_index_df[_menu_index_df["name"] != ""].drop_duplicates().sort_values("name")
    menu_list = _menu_index_df["name"].tolist()

    st.subheader(d.strftime("%Y-%m-%d (%a)"))

    st.markdown("**기본 메뉴**")
    c1, c2 = st.columns([1, 2])
    with c1:
        b_pick = st.selectbox("인덱스", ["(선택 없음)"] + menu_list, index=0, key=f"b_pick_{dstr}")
    with c2:
        base_text = st.text_input("직접 입력", value=cur_base, key=f"b_txt_{dstr}")
    if b_pick != "(선택 없음)":
        base_text = b_pick

    st.markdown("**변경 메뉴**")
    c3, c4 = st.columns([1, 2])
    with c3:
        ch_pick = st.selectbox("인덱스", ["(선택 없음)"] + menu_list, index=0, key=f"c_pick_{dstr}")
    with c4:
        change_text = st.text_input("직접 입력", value=cur_change, key=f"c_txt_{dstr}")
    if ch_pick != "(선택 없음)":
        change_text = ch_pick

    st.markdown("**배달**")
    del_opt = st.radio(
        "배달 여부",
        options=["배달", "배달불요"],
        index=0 if (cur_del or "Y") != "N" else 1,
        horizontal=True,
        key=f"del_{dstr}",
    )
    yn = "Y" if del_opt == "배달" else "N"

    st.divider()
    s1, s2 = st.columns([1, 1])
    with s1:
        if st.button("저장", use_container_width=True):
            base_text2 = _normalize_menu_text(base_text)
            change_text2 = _normalize_menu_text(change_text)

            base_df2 = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
            change_df2 = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
            delivery_df2 = _read_csv(DELIVERY_PATH, ["date", "delivery"])

            base_df2 = _save_row(base_df2, dstr, "base_menu", base_text2)
            change_df2 = _save_row(change_df2, dstr, "change_menu", change_text2)
            delivery_df2 = _save_delivery(delivery_df2, dstr, yn)

            base_df2.to_csv(BASE_MENU_PATH, index=False, encoding="utf-8-sig")
            change_df2.to_csv(CHANGE_MENU_PATH, index=False, encoding="utf-8-sig")
            delivery_df2.to_csv(DELIVERY_PATH, index=False, encoding="utf-8-sig")

            # 인덱스 누적
            new_items = [x for x in [base_text2, change_text2] if x]
            if new_items:
                idx_df = _read_csv(MENU_INDEX_PATH, ["name"])
                for it in new_items:
                    idx_df = pd.concat([idx_df, pd.DataFrame([{"name": it}])], ignore_index=True)
                idx_df["name"] = idx_df["name"].fillna("").astype(str).str.strip()
                idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name")
                idx_df.to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")

            st.rerun()
    with s2:
        if st.button("닫기", use_container_width=True):
            st.rerun()

# -----------------------------
# 달력 데이터(월~금)
# -----------------------------
y, m = st.session_state.ym
cal = calendar.Calendar(firstweekday=0)  # 월 시작
days_mon_fri = [d for d in cal.itermonthdates(y, m) if d.month == m and d.weekday() < 5]

# 포스터 그리드(월 시작 위치 맞춤)
first_wd = date(y, m, 1).weekday()  # 월=0
pad_left = first_wd if first_wd < 5 else 0
poster_cells = [None] * pad_left + days_mon_fri
while len(poster_cells) % 5 != 0:
    poster_cells.append(None)

def _cell_bg_and_lines(d: date):
    ds = _to_date_str(d)
    b = _get_value(base_df, ds, "base_menu").strip()
    c = _get_value(change_df, ds, "change_menu").strip()
    del_ = _get_delivery(delivery_df, ds).strip().upper()
    no_delivery = (del_ == "N")

    if c and no_delivery:
        bg = "bg-both"
    elif c:
        bg = "bg-change"
    elif no_delivery:
        bg = "bg-nodelivery"
    else:
        bg = "bg-base"

    lines = []
    if b:
        lines.append(("기본", b))
    if c:
        lines.append(("변경", c))
    if no_delivery:
        lines.append(("배달", "불요"))
    return bg, lines

# -----------------------------
# 입력용 달력(클릭)
# -----------------------------
st.subheader(_month_title(y, m))
wcols = st.columns(5)
for i, w in enumerate(["월", "화", "수", "목", "금"]):
    with wcols[i]:
        st.markdown(f"**{w}**")

# 주 단위 표시를 위해: 월~금만 구성하여 5칸씩 렌더
rows = [poster_cells[i:i+5] for i in range(0, len(poster_cells), 5)]
for r in rows:
    cols = st.columns(5, gap="small")
    for i, d in enumerate(r):
        with cols[i]:
            if d is None:
                st.markdown('<div class="poster cell" style="opacity:.18; min-height:68px;"></div>', unsafe_allow_html=True)
                continue
            key = _to_date_str(d)
            if st.button(f"{d.day}", key=f"day_{key}", use_container_width=True):
                edit_day_dialog(d)

st.divider()

# -----------------------------
# 포스터(스크린샷용): 달력 형태 + 공양게(화면용)
# -----------------------------
moms_b64 = _b64_image_if_exists(MOMS_LOGO_PATH)
kapma_b64 = _b64_image_if_exists(KAPMA_LOGO_PATH)
bowl_b64 = _b64_image_if_exists(BOWL_IMG_PATH)

moms_html = f'<img src="{moms_b64}" style="max-height:70px;max-width:100%;object-fit:contain;" />' if moms_b64 else '<div style="font-weight:900;font-size:18px;">MOMS</div>'
kapma_html = f'<img src="{kapma_b64}" style="max-height:70px;max-width:100%;object-fit:contain;" />' if kapma_b64 else '<div style="font-weight:900;font-size:18px;">동약협회</div>'
bowl_html = f'<img src="{bowl_b64}" style="max-height:92px;max-width:100%;object-fit:contain;" />' if bowl_b64 else ""

gongyang_html = (
    "이 음식이 어디에서 왔는가<br/>"
    "내 덕행으로는 받기가 부끄럽네<br/>"
    "마음의 온갖 탐욕을 떠나<br/>"
    "바른 생각으로 이 공양을 받습니다"
)

def poster_cell_html(d: date | None) -> str:
    if d is None:
        return '<div class="cell bg-base" style="opacity:.18;"></div>'
    bg, lines = _cell_bg_and_lines(d)
    line_html = ""
    for lab, txt in lines[:3]:
        line_html += f'<div class="t"><b>{lab}</b> {txt}</div>'
    if not line_html:
        line_html = '<div class="t" style="opacity:.35;">&nbsp;</div>'
    return f"""
<div class="cell {bg}">
  <div class="d">{d.day}</div>
  {line_html}
</div>
"""

poster_html = f"""
<div class="poster-wrap">
  <div class="poster">
    <div class="toprow">
      <div class="logoBox">{moms_html}</div>
      <div class="midBox">{bowl_html}</div>
      <div class="logoBox">{kapma_html}</div>
    </div>

    <div class="title">맘스락 {m:02d}월<br/>식단(배달) 변경</div>
    <div class="subtitle">( 인원 : {st.session_state.people_count.strip() or "1"}인 )</div>

    <div class="dow">
      <div class="h">월</div><div class="h">화</div><div class="h">수</div><div class="h">목</div><div class="h">금</div>
    </div>

    <div class="grid">
      {''.join(poster_cell_html(d) for d in poster_cells)}
    </div>

    <div class="gongyang">{gongyang_html}</div>
  </div>
</div>
"""

st.subheader("포스터(스크린샷용) 미리보기")
components.html(poster_html, height=980, scrolling=True)

st.divider()

# -----------------------------
# A4 출력용 포스터(업체 전달용) : 제목+로고+그릇+달력+공양게+연락처까지 1페이지
# -----------------------------
def build_a4_poster_html(year: int, month: int) -> str:
    moms_b64 = _b64_image_if_exists(MOMS_LOGO_PATH)
    kapma_b64 = _b64_image_if_exists(KAPMA_LOGO_PATH)
    bowl_b64 = _b64_image_if_exists(BOWL_IMG_PATH)

    moms_html = f'<img src="{moms_b64}" style="height:20mm;max-width:100%;object-fit:contain;" />' if moms_b64 else '<div style="font-weight:900;font-size:16pt;">MOMS</div>'
    kapma_html = f'<img src="{kapma_b64}" style="height:20mm;max-width:100%;object-fit:contain;" />' if kapma_b64 else '<div style="font-weight:900;font-size:16pt;">동약협회</div>'
    bowl_html = f'<img src="{bowl_b64}" style="height:26mm;max-width:100%;object-fit:contain;" />' if bowl_b64 else ""

    # 월~금 셀(패딩 포함)
    calx = calendar.Calendar(firstweekday=0)
    days = [d for d in calx.itermonthdates(year, month) if d.month == month and d.weekday() < 5]
    first_wd = date(year, month, 1).weekday()
    pad_left = first_wd if first_wd < 5 else 0
    cells = [None] * pad_left + days
    while len(cells) % 5 != 0:
        cells.append(None)

    def cell(d: date | None) -> str:
        if d is None:
            return '<div class="c empty"></div>'
        bg, lines = _cell_bg_and_lines(d)
        # bg 클래스 -> A4용 클래스 매핑
        cls = "base"
        if bg == "bg-change":
            cls = "chg"
        elif bg == "bg-nodelivery":
            cls = "nod"
        elif bg == "bg-both":
            cls = "both"

        line_html = ""
        for lab, txt in lines[:3]:
            line_html += f"<div><b>{lab}</b> {txt}</div>"
        if not line_html:
            line_html = '<div style="opacity:.35;">&nbsp;</div>'

        return f"""
<div class="c {cls}">
  <div class="d">{d.day}</div>
  {line_html}
</div>
"""

    gong = (
        "이 음식이 어디에서 왔는가<br/>"
        "내 덕행으로는 받기가 부끄럽네<br/>"
        "마음의 온갖 탐욕을 떠나<br/>"
        "바른 생각으로 이 공양을 받습니다"
    )

    vendor_line = f"업체: {st.session_state.vendor_name} / {st.session_state.vendor_phone}"
    kapma_line = f"동약협회: {st.session_state.kapma_phone}"

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>맘스락_{year}_{month:02d}_A4</title>
<style>
@page {{ size: A4; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: "Malgun Gothic","Apple SD Gothic Neo",sans-serif; }}

@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');

.header {{
  display:flex; align-items:center; justify-content:space-between; gap: 8mm;
}}
.logo {{
  width: 38%;
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 6mm;
  display:flex; align-items:center; justify-content:center;
  min-height: 30mm;
}}
.mid {{
  width: 24%;
  display:flex; align-items:center; justify-content:center;
}}

.title {{
  text-align:center; font-weight: 900;
  font-size: 20pt; line-height: 1.10;
  margin: 6mm 0 2mm 0;
}}
.sub {{
  text-align:center; font-weight: 800;
  font-size: 12pt; opacity: .85;
  margin: 0 0 4mm 0;
}}

.dow {{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 3mm;
  margin-bottom: 3mm;
}}
.dow div {{
  text-align:center;
  font-weight: 900;
  padding: 2.2mm 0;
  border-radius: 10px;
  background: rgba(0,0,0,0.04);
  border: 1px solid rgba(0,0,0,0.08);
}}

.grid {{
  display:grid; grid-template-columns: repeat(5, 1fr); gap: 3mm;
}}
.c {{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 12px;
  padding: 3.5mm;
  min-height: 28mm;
  background: rgba(255,255,255,0.96);
}}
.c .d {{
  font-weight: 900;
  font-size: 12pt;
  margin-bottom: 2mm;
}}
.c div {{
  font-size: 9.2pt;
  line-height: 1.22;
  margin: 0.8mm 0;
}}
.c.chg {{ background: rgba(255,245,180,0.60); }}
.c.nod {{ background: rgba(255,205,205,0.55); }}
.c.both {{ background: linear-gradient(135deg, rgba(255,245,180,0.60), rgba(255,205,205,0.55)); }}
.c.empty {{ opacity: .18; }}

.gong {{
  margin-top: 6mm;
  border-top: 1px dashed rgba(0,0,0,0.18);
  padding-top: 4mm;
  text-align:center;
  font-family: 'Nanum Brush Script','궁서','Gungsuh',serif;
  font-size: 18pt;
  line-height: 1.25;
}}

.footer {{
  margin-top: 4mm;
  border-top: 1px solid rgba(0,0,0,0.10);
  padding-top: 3mm;
  display:flex;
  justify-content:space-between;
  gap: 8mm;
  font-size: 10.5pt;
  font-weight: 800;
}}
.footer .muted {{ opacity: .85; font-weight: 800; }}
</style>
</head>
<body>
  <div class="header">
    <div class="logo">{moms_html}</div>
    <div class="mid">{bowl_html}</div>
    <div class="logo">{kapma_html}</div>
  </div>

  <div class="title">맘스락 {month:02d}월<br/>식단(배달) 변경</div>
  <div class="sub">( 인원 : {st.session_state.people_count.strip() or "1"}인 )</div>

  <div class="dow">
    <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
  </div>

  <div class="grid">
    {''.join(cell(d) for d in cells)}
  </div>

  <div class="gong">{gong}</div>

  <div class="footer">
    <div class="muted">{vendor_line}</div>
    <div class="muted">{kapma_line}</div>
  </div>
</body>
</html>
"""
    return html_doc

a4_html = build_a4_poster_html(y, m)

st.subheader("업체 전달용 A4 출력(1페이지 포스터)")
c1, c2 = st.columns([1.0, 1.4])
with c1:
    st.download_button(
        "A4 포스터 HTML 다운로드",
        data=a4_html.encode("utf-8"),
        file_name=f"맘스락_{y}_{m:02d}_A4_포스터.html",
        mime="text/html",
        use_container_width=True,
    )
with c2:
    components.html(a4_html, height=720, scrolling=True)
