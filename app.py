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

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N) -> N=배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_IMG_PATH = ASSETS_DIR / "gongyang_bowl.png"

KAPMA_PHONE = "010-7101-5871"  # ✅ 요청 반영

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


def _b64_bytes(data: bytes, ext: str) -> str:
    ext = (ext or "png").lower().lstrip(".")
    mime = "png" if ext == "png" else ("jpeg" if ext in ["jpg", "jpeg"] else ext)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def _b64_image_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    ext = path.suffix.lower().lstrip(".") or "png"
    return _b64_bytes(path.read_bytes(), ext)


def _normalize(s: str) -> str:
    return (s or "").strip()


def _save_row(df: pd.DataFrame, key_date: str, col: str, value: str) -> pd.DataFrame:
    value = _normalize(value)
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

    # 로고를 화면에서 업로드해도 즉시 반영 (없으면 assets fallback)
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
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
div.stButton > button { width:100%; border-radius: 12px !important; font-weight: 800 !important; }

@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');

.poster-wrap{ width:100%; display:flex; justify-content:center; }
.poster{
  width: 980px;
  background:#fff;
  padding: 14px 14px 16px 14px;
}
.topbar{
  display:grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: 12px;
  align-items:center;
  margin-bottom: 10px;
}
.logoBox{
  border: 2px solid rgba(0,0,0,0.20);
  border-radius: 18px;
  padding: 10px 12px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap: 10px;
  min-height: 72px;
}
.logoBox img{ max-height: 52px; max-width: 100%; object-fit:contain; }
.logoText{ font-weight: 900; font-size: 22px; }
.kapmaPhone{ font-weight: 900; font-size: 14px; opacity: .80; margin-top: 2px; }

.title{
  text-align:center;
  font-weight: 900;
  font-size: 34px;
  line-height: 1.10;
}

.dow{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin: 10px 0 8px 0;
}
.dow div{ text-align:center; font-weight: 900; }

.grid{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}

.cell{
  border: 2px solid rgba(0,0,0,0.25);
  border-radius: 14px;
  padding: 10px 10px 8px 10px;
  min-height: 98px;
  background: #fff;
  position: relative;
}
.cell.empty{
  border: 2px dashed rgba(0,0,0,0.25);
  background: rgba(255,255,255,0.60);
}
.cell.change{ background: rgba(255, 245, 180, 0.65); border-color: rgba(210,140,0,0.55); }
.cell.nodelivery{ background: rgba(255, 220, 220, 0.55); border-color: rgba(220,0,0,0.50); }

.dayrow{
  display:flex;
  align-items:flex-end;
  gap: 8px;
  margin-bottom: 4px;
}
.daynum{ font-weight: 900; font-size: 18px; }
.daywk{ font-weight: 900; font-size: 12px; opacity: .70; }

.badge{
  position:absolute;
  right: 10px;
  top: 10px;
  padding: 3px 9px;
  border-radius: 999px;
  font-weight: 900;
  font-size: 12px;
  border: 1px solid rgba(0,0,0,0.18);
  background: rgba(255,255,255,0.78);
}
.badge.red{ color: #c50000; border-color: rgba(197,0,0,0.35); }
.badge.orange{ color: #b85c00; border-color: rgba(184,92,0,0.35); }

.baseText{
  font-weight: 900;
  font-size: 14px;
  margin-top: 6px;
}
.changeText{
  font-weight: 900;
  font-size: 14px;
  margin-top: 6px;
  color: #c50000;
}

.gongyangBox{
  border: 1px dashed rgba(0,0,0,0.25);
  border-radius: 16px;
  padding: 10px 12px;
  font-family: 'Nanum Brush Script','궁서','Gungsuh',serif;
  font-size: 22px;
  line-height: 1.18;
  text-align:center;
}

@page { size: A4; margin: 12mm; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단 UI
# -----------------------------
st.title("맘스락 식단 변경 프로그램")

c1, c2 = st.columns([1.0, 1.8], vertical_alignment="center")
with c1:
    y, m = st.session_state.ym
    month_options = [(yy, mm) for yy in range(date.today().year - 1, date.today().year + 3) for mm in range(1, 13)]
    idx = month_options.index((y, m)) if (y, m) in month_options else 0
    st.session_state.ym = st.selectbox(
        "월 선택",
        options=month_options,
        index=idx,
        format_func=lambda x: f"{x[0]}-{x[1]:02d}",
    )

with c2:
    st.caption("로고 업로드(선택) — 업로드하면 포스터/A4에 즉시 반영됩니다. (없으면 assets 폴더 파일 사용)")
    u1, u2, u3 = st.columns(3)
    with u1:
        up = st.file_uploader("MOMS 로고", type=["png", "jpg", "jpeg"], key="up_moms")
        if up is not None:
            st.session_state.moms_logo_b64 = _b64_bytes(up.read(), up.name.split(".")[-1])
    with u2:
        up = st.file_uploader("동약협회 로고", type=["png", "jpg", "jpeg"], key="up_kapma")
        if up is not None:
            st.session_state.kapma_logo_b64 = _b64_bytes(up.read(), up.name.split(".")[-1])
    with u3:
        up = st.file_uploader("그릇 그림(출력용)", type=["png", "jpg", "jpeg"], key="up_bowl")
        if up is not None:
            st.session_state.bowl_b64 = _b64_bytes(up.read(), up.name.split(".")[-1])

st.divider()

# -----------------------------
# 백업/복원
# -----------------------------
b1, b2 = st.columns(2)
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
    up = st.file_uploader("백업 ZIP 복원", type=["zip"], key="up_zip")
    if up is not None:
        try:
            b = io.BytesIO(up.read())
            with zipfile.ZipFile(b, "r") as z:
                for fname in ["base_menu.csv", "change_menu.csv", "delivery.csv", "menu_index.csv"]:
                    if fname in z.namelist():
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
    a, b = st.columns([1, 2])
    with a:
        b_pick = st.selectbox("인덱스", ["(선택 없음)"] + menu_list, index=0, key=f"b_pick_{dstr}")
    with b:
        base_text = st.text_input("직접 입력", value=cur_base, key=f"b_txt_{dstr}")
    if b_pick != "(선택 없음)":
        base_text = b_pick

    st.markdown("**변경 메뉴**")
    c, d2 = st.columns([1, 2])
    with c:
        c_pick = st.selectbox("인덱스", ["(선택 없음)"] + menu_list, index=0, key=f"c_pick_{dstr}")
    with d2:
        change_text = st.text_input("직접 입력", value=cur_change, key=f"c_txt_{dstr}")
    if c_pick != "(선택 없음)":
        change_text = c_pick

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
    s1, s2 = st.columns(2)
    with s1:
        if st.button("저장", use_container_width=True):
            base_text2 = _normalize(base_text)
            change_text2 = _normalize(change_text)

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
# 달력(월~금) 셀 구성
# -----------------------------
y, m = st.session_state.ym
cal = calendar.Calendar(firstweekday=0)

days_mon_fri = [d for d in cal.itermonthdates(y, m) if d.month == m and d.weekday() < 5]
first_wd = date(y, m, 1).weekday()  # 월=0
pad_left = first_wd if first_wd < 5 else 0

cells = [None] * pad_left + days_mon_fri
while len(cells) % 5 != 0:
    cells.append(None)

WK = ["월", "화", "수", "목", "금", "토", "일"]

def _status(d: date):
    ds = _to_date_str(d)
    base = _get_value(base_df, ds, "base_menu").strip()
    chg = _get_value(change_df, ds, "change_menu").strip()
    delv = _get_delivery(delivery_df, ds).strip().upper()
    nodel = (delv == "N")
    return base, chg, nodel

# -----------------------------
# 입력용 달력(버튼)
# -----------------------------
st.subheader(_month_title(y, m))
wcols = st.columns(5)
for i, w in enumerate(["월", "화", "수", "목", "금"]):
    with wcols[i]:
        st.markdown(f"**{w}**")

rows = [cells[i:i+5] for i in range(0, len(cells), 5)]
for r in rows:
    cols = st.columns(5, gap="small")
    for i, d in enumerate(r):
        with cols[i]:
            if d is None:
                st.write("")
                continue
            if st.button(f"{d.day:02d}", key=f"day_{_to_date_str(d)}", use_container_width=True):
                edit_day_dialog(d)

st.divider()

# -----------------------------
# 로고 (업로드 우선 -> assets fallback)
# -----------------------------
moms_b64 = st.session_state.moms_logo_b64 or _b64_image_if_exists(MOMS_LOGO_PATH)
kapma_b64 = st.session_state.kapma_logo_b64 or _b64_image_if_exists(KAPMA_LOGO_PATH)
bowl_b64 = st.session_state.bowl_b64 or _b64_image_if_exists(BOWL_IMG_PATH)

def _img_or_text(b64: str | None, text: str) -> str:
    if b64:
        return f'<img src="{b64}" />'
    return f'<div class="logoText">{text}</div>'

# -----------------------------
# ✅ 포스터(스크린샷용): 업로드하신 이미지 스타일(달력형태) + 동약협회 전화번호
# -----------------------------
def poster_calendar_html() -> str:
    def cell_html(d: date | None) -> str:
        if d is None:
            return '<div class="cell empty"></div>'

        base, chg, nodel = _status(d)
        cls = "cell"
        badges = ""
        if nodel:
            cls += " nodelivery"
            badges += '<span class="badge red">배달불요</span>'
        if chg:
            cls += " change"
            badges += '<span class="badge orange" style="right:10px; top:40px;">변경</span>' if nodel else '<span class="badge orange">변경</span>'

        base_line = f'<div class="baseText">{base}</div>' if base else ""
        chg_line = f'<div class="changeText">{chg}</div>' if chg else ""

        return f"""
<div class="{cls}">
  {badges}
  <div class="dayrow">
    <div class="daynum">{d.day:02d}</div>
    <div class="daywk">({WK[d.weekday()]})</div>
  </div>
  {base_line}
  {chg_line}
</div>
"""

    # 제목을 스크린샷처럼 2줄
    title = f"맘스락 {m:02d}월<br/>식단 변경"

    return f"""
<div class="poster-wrap">
  <div class="poster">
    <div class="topbar">
      <div class="logoBox">
        {_img_or_text(moms_b64, "MOMS")}
        <div class="logoText">MOMS</div>
      </div>

      <div class="title">{title}</div>

      <div class="logoBox" style="flex-direction:row; justify-content:center;">
        {_img_or_text(kapma_b64, "동약협회")}
        <div style="display:flex; flex-direction:column; align-items:flex-start;">
          <div class="logoText">동약협회</div>
          <div class="kapmaPhone">{KAPMA_PHONE}</div>
        </div>
      </div>
    </div>

    <div class="dow">
      <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
    </div>

    <div class="grid">
      {''.join(cell_html(d) for d in cells)}
    </div>
  </div>
</div>
"""

st.subheader("포스터(스크린샷용) 미리보기")
components.html(poster_calendar_html(), height=880, scrolling=True)

st.divider()

# -----------------------------
# ✅ A4 출력 파일: 공양게/그릇그림 포함(요청)
#   - 출력 파일은 포스터와 달리 “공양게”를 포함한 포스터형 1페이지
# -----------------------------
def a4_html_with_gongyang() -> str:
    title = f"맘스락 {m:02d}월 식단 변경"

    gong = (
        "이 음식이 어디에서 왔는가<br/>"
        "내 덕행으로는 받기가 부끄럽네<br/>"
        "마음의 온갖 탐욕을 떠나<br/>"
        "바른 생각으로 이 공양을 받습니다"
    )
    bowl = f'<img src="{bowl_b64}" style="max-height:38px; margin-bottom:6px; object-fit:contain;" />' if bowl_b64 else ""

    def cell_html(d: date | None) -> str:
        if d is None:
            return '<div class="cell empty"></div>'

        base, chg, nodel = _status(d)
        cls = "cell"
        badges = ""
        if nodel:
            cls += " nodelivery"
            badges += '<span class="badge red">배달불요</span>'
        if chg:
            cls += " change"
            badges += '<span class="badge orange" style="right:10px; top:40px;">변경</span>' if nodel else '<span class="badge orange">변경</span>'

        base_line = f'<div class="baseText">{base}</div>' if base else ""
        chg_line = f'<div class="changeText">{chg}</div>' if chg else ""

        return f"""
<div class="{cls}">
  {badges}
  <div class="dayrow">
    <div class="daynum">{d.day:02d}</div>
    <div class="daywk">({WK[d.weekday()]})</div>
  </div>
  {base_line}
  {chg_line}
</div>
"""

    # A4에서는 “제목 → (로고/공양게/로고) → 달력” 구성
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
/* 위 streamlit CSS를 A4에도 동일하게 적용(필요한 부분만) */
@page {{ size:A4; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: "Malgun Gothic","Apple SD Gothic Neo",sans-serif; }}

@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');

.topbar{{ display:grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 10px; align-items:center; margin-bottom: 8px; }}
.logoBox{{ border:2px solid rgba(0,0,0,0.20); border-radius:18px; padding: 8px 10px; display:flex; align-items:center; justify-content:center; gap:10px; min-height: 58px; }}
.logoBox img{{ max-height: 42px; max-width: 100%; object-fit:contain; }}
.logoText{{ font-weight:900; font-size: 16px; }}
.kapmaPhone{{ font-weight:900; font-size: 12px; opacity:.8; margin-top:2px; }}

.title{{ text-align:center; font-weight:900; font-size: 22px; line-height:1.10; }}

.midrow{{ display:grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 10px; align-items: stretch; margin-bottom: 8px; }}
.gongyangBox{{ border: 1px dashed rgba(0,0,0,0.25); border-radius:16px; padding: 8px 10px; font-family:'Nanum Brush Script','궁서','Gungsuh',serif; font-size: 18px; line-height:1.15; text-align:center; display:flex; align-items:center; justify-content:center; }}

.dow{{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 6px 0; }}
.dow div{{ text-align:center; font-weight:900; }}

.grid{{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }}

.cell{{ border:2px solid rgba(0,0,0,0.25); border-radius:14px; padding: 8px 8px 6px 8px; min-height: 84px; background:#fff; position:relative; }}
.cell.empty{{ border:2px dashed rgba(0,0,0,0.25); background: rgba(255,255,255,0.60); }}
.cell.change{{ background: rgba(255,245,180,0.65); border-color: rgba(210,140,0,0.55); }}
.cell.nodelivery{{ background: rgba(255,220,220,0.55); border-color: rgba(220,0,0,0.50); }}

.dayrow{{ display:flex; align-items:flex-end; gap: 6px; margin-bottom: 2px; }}
.daynum{{ font-weight:900; font-size: 14px; }}
.daywk{{ font-weight:900; font-size: 10px; opacity:.70; }}

.badge{{ position:absolute; right:8px; top:8px; padding: 2px 8px; border-radius:999px; font-weight:900; font-size: 10px; border:1px solid rgba(0,0,0,0.18); background: rgba(255,255,255,0.78); }}
.badge.red{{ color:#c50000; border-color: rgba(197,0,0,0.35); }}
.badge.orange{{ color:#b85c00; border-color: rgba(184,92,0,0.35); }}

.baseText{{ font-weight:900; font-size: 12px; margin-top: 4px; }}
.changeText{{ font-weight:900; font-size: 12px; margin-top: 4px; color:#c50000; }}
</style>
</head>
<body>
  <div class="title">{title}</div>

  <div class="midrow">
    <div class="logoBox">
      {_img_or_text(moms_b64, "MOMS")}
      <div class="logoText">MOMS</div>
    </div>

    <div class="gongyangBox">
      <div>{bowl}{gong}</div>
    </div>

    <div class="logoBox">
      {_img_or_text(kapma_b64, "동약협회")}
      <div style="display:flex; flex-direction:column; align-items:flex-start;">
        <div class="logoText">동약협회</div>
        <div class="kapmaPhone">{KAPMA_PHONE}</div>
      </div>
    </div>
  </div>

  <div class="dow"><div>월</div><div>화</div><div>수</div><div>목</div><div>금</div></div>
  <div class="grid">{''.join(cell_html(d) for d in cells)}</div>
</body>
</html>
"""

a4_html = a4_html_with_gongyang()

st.subheader("출력파일(A4 1페이지) — 공양게/그릇그림 포함")
d1, d2 = st.columns([1.0, 1.6])
with d1:
    st.download_button(
        "A4 HTML 다운로드",
        data=a4_html.encode("utf-8"),
        file_name=f"맘스락_{y}_{m:02d}_A4_출력.html",
        mime="text/html",
        use_container_width=True,
    )
with d2:
    components.html(a4_html, height=720, scrolling=True)
