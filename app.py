# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import re
import urllib.request
import pandas as pd
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 관리", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N) -> Y:배달, N:배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# -----------------------------
# GitHub Raw URL (선택)
# -----------------------------
# ✅ 여기에 "raw.githubusercontent.com/..." 형태로 넣으면 즉시 적용됩니다.
# 비어 있으면 assets 폴더(로컬) 파일을 사용합니다.
MOMS_LOGO_URL = ""   # 예: https://raw.githubusercontent.com/<user>/<repo>/main/assets/moms_logo.png
KAPMA_LOGO_URL = ""  # 예: https://raw.githubusercontent.com/<user>/<repo>/main/assets/kapma_logo.png
BOWL_IMG_URL = ""    # 예: https://raw.githubusercontent.com/<user>/<repo>/main/assets/gongyang_bowl.png

MOMS_LOGO_LOCAL = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_LOCAL = ASSETS_DIR / "kapma_logo.png"
BOWL_IMG_LOCAL = ASSETS_DIR / "gongyang_bowl.png"

GONGYANG_VERSE = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
몸을 지탱하는 약으로 알아 이 공양을 받습니다"""

ASSOC_LINE = "동약협회 (전화번호 010-7101-5871)"


# -----------------------------
# 유틸
# -----------------------------
def _safe_read_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _norm_date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_date_str(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _clean_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return name


def output_filename(year: int, month: int) -> str:
    return _clean_filename(f"동약협회 {year}년 {month}월 식단변경 내역")


def _dow_kr(idx: int) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][idx]


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


@st.cache_data(show_spinner=False)
def _fetch_bytes(url: str) -> bytes | None:
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def _img_b64_tag_from_bytes(data: bytes | None, height_px: int) -> str:
    if not data:
        return ""
    b64 = base64.b64encode(data).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64}" style="height:{height_px}px; width:auto; object-fit:contain;" />'


def _img_b64_tag_from_local(path: Path, height_px: int) -> str:
    if not path.exists():
        return ""
    return _img_b64_tag_from_bytes(path.read_bytes(), height_px)


def get_logo_tag(kind: str, height_px: int) -> str:
    if kind == "moms":
        data = _fetch_bytes(MOMS_LOGO_URL)
        return _img_b64_tag_from_bytes(data, height_px) if data else _img_b64_tag_from_local(MOMS_LOGO_LOCAL, height_px)
    if kind == "kapma":
        data = _fetch_bytes(KAPMA_LOGO_URL)
        return _img_b64_tag_from_bytes(data, height_px) if data else _img_b64_tag_from_local(KAPMA_LOGO_LOCAL, height_px)
    if kind == "bowl":
        data = _fetch_bytes(BOWL_IMG_URL)
        return _img_b64_tag_from_bytes(data, height_px) if data else _img_b64_tag_from_local(BOWL_IMG_LOCAL, height_px)
    return ""


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"])
chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
del_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"])
idx_df = _safe_read_csv(MENU_INDEX_PATH, ["name"])

if not idx_df.empty:
    idx_df["name"] = idx_df["name"].astype(str).str.strip()
    idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name")
    _save_csv(idx_df, MENU_INDEX_PATH)


def get_base(d: date) -> str:
    s = _norm_date_str(d)
    r = base_df.loc[base_df["date"] == s, "base_menu"]
    return r.iloc[0] if len(r) else ""


def get_change(d: date) -> str:
    s = _norm_date_str(d)
    r = chg_df.loc[chg_df["date"] == s, "change_menu"]
    return r.iloc[0] if len(r) else ""


def get_delivery_flag(d: date) -> str:
    s = _norm_date_str(d)
    r = del_df.loc[del_df["date"] == s, "delivery"]
    return r.iloc[0] if len(r) else "Y"


def set_base(d: date, menu: str) -> None:
    global base_df
    s = _norm_date_str(d)
    menu = (menu or "").strip()
    base_df = base_df.copy()
    base_df = base_df[base_df["date"] != s]
    if menu:
        base_df = pd.concat([base_df, pd.DataFrame([{"date": s, "base_menu": menu}])], ignore_index=True)
    _save_csv(base_df.sort_values("date"), BASE_MENU_PATH)


def set_change(d: date, menu: str) -> None:
    global chg_df
    s = _norm_date_str(d)
    menu = (menu or "").strip()
    chg_df = chg_df.copy()
    chg_df = chg_df[chg_df["date"] != s]
    if menu:
        chg_df = pd.concat([chg_df, pd.DataFrame([{"date": s, "change_menu": menu}])], ignore_index=True)
    _save_csv(chg_df.sort_values("date"), CHANGE_MENU_PATH)


def set_delivery(d: date, flag: str) -> None:
    global del_df
    s = _norm_date_str(d)
    flag = "N" if flag == "N" else "Y"
    del_df = del_df.copy()
    del_df = del_df[del_df["date"] != s]
    del_df = pd.concat([del_df, pd.DataFrame([{"date": s, "delivery": flag}])], ignore_index=True)
    _save_csv(del_df.sort_values("date"), DELIVERY_PATH)


def add_index_menu(name: str) -> None:
    global idx_df
    name = (name or "").strip()
    if not name:
        return
    idx_df = idx_df.copy()
    idx_df = pd.concat([idx_df, pd.DataFrame([{"name": name}])], ignore_index=True)
    idx_df["name"] = idx_df["name"].astype(str).str.strip()
    idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name")
    _save_csv(idx_df, MENU_INDEX_PATH)


index_options = ["(직접입력)"] + (idx_df["name"].tolist() if not idx_df.empty else [])


# -----------------------------
# CSS (초기화면/달력)
# -----------------------------
st.markdown(
    """
    <style>
      .hero{
        border-radius:18px;
        padding:20px 18px 16px 18px;
        background: #ffffff;
        border: 1px solid rgba(0,0,0,0.08);
      }
      .hero-top{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
      }
      .hero-title{
        font-size:30px;
        font-weight:900;
        line-height:1.12;
        margin:0;
      }
      .hero-sub{
        font-size:14px;
        opacity:0.75;
        margin-top:4px;
        font-weight:700;
      }
      .hero-mid{
        display:flex;
        justify-content:center;
        margin:10px 0 8px 0;
      }
      .verse{
        border-radius:16px;
        padding:16px 18px;
        background: #fffaf2;
        border: 2px solid rgba(177, 127, 69, 0.35);
        white-space: pre-line;
        font-size:18px;
        font-weight:900;
        line-height:1.55;
      }

      /* 달력 버튼 */
      .calbtn button{
        width:100% !important;
        text-align:left !important;
        border-radius:14px !important;
        padding:10px 10px !important;
        min-height:112px !important;
        white-space:pre-line !important;
        border: 1px solid rgba(0,0,0,0.14) !important;
      }

      /* 달력의 "불필요한 빈칸(네모박스)"은 버튼 자체를 만들지 않음 */
      .blank-cell{
        height:112px;
        border-radius:14px;
        background: transparent;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 1. 초기화면(디자인 개선)
# -----------------------------
moms_tag = get_logo_tag("moms", 52) or '<div style="font-size:12px;opacity:0.7;">MOMS 로고</div>'
kapma_tag = get_logo_tag("kapma", 52) or '<div style="font-size:12px;opacity:0.7;">동약협회 로고</div>'
bowl_tag = get_logo_tag("bowl", 54) or '<div style="font-size:12px;opacity:0.7;">공양그릇</div>'

st.markdown('<div class="hero">', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="hero-top">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="min-width:64px;">{moms_tag}</div>
        <div>
          <div class="hero-title">맘스락 식단 변경 관리</div>
          <div class="hero-sub">달력 클릭 → 저장 → 업체 제출용 A4 출력</div>
        </div>
      </div>
      <div style="min-width:64px; display:flex; justify-content:flex-end;">{kapma_tag}</div>
    </div>
    <div class="hero-mid">{bowl_tag}</div>
    <div class="verse">{GONGYANG_VERSE}</div>
    """,
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# -----------------------------
# 월 선택
# -----------------------------
today = date.today()
colA, colB, colC = st.columns([1.1, 1.0, 1.5])
with colA:
    year = st.number_input("연도", min_value=2020, max_value=2100, value=today.year, step=1)
with colB:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with colC:
    st.markdown(f"### {int(year)}년 {int(month):02d}월")

year = int(year)
month = int(month)

# -----------------------------
# 메뉴 인덱스(필요하면 사용)
# -----------------------------
with st.expander("메뉴 인덱스 (가나다 순)", expanded=False):
    l, r = st.columns([1.1, 1.0])
    with l:
        new_menu = st.text_input("인덱스에 추가할 메뉴명", value="")
        if st.button("인덱스 추가"):
            add_index_menu(new_menu)
            st.success("추가했습니다.")
            st.rerun()
    with r:
        if idx_df.empty:
            st.write("—")
        else:
            st.dataframe(idx_df, use_container_width=True, height=240)

st.divider()

# -----------------------------
# 2. 데이터 입력 달력
# - 기본메뉴가 먼저
# - 변경메뉴가 있으면 아래에 '확실히' 표시
# - 배달불요는 최상단 경고 + 칸 색상 변화
# - "요일 줄 밑의 불필요한 네모 박스" 제거: 월 외 날짜는 버튼 생성 자체를 하지 않음
# -----------------------------
st.markdown("## 날짜 입력 (월~금)")

cal = calendar.Calendar(firstweekday=0)
month_days = [d for d in cal.itermonthdates(year, month)]

weeks: list[list[date]] = []
wk: list[date] = []
for d in month_days:
    if d.weekday() == 0 and wk:
        weeks.append(wk)
        wk = []
    wk.append(d)
if wk:
    weeks.append(wk)

if "selected_date" not in st.session_state:
    st.session_state.selected_date = None


def open_editor(d: date):
    st.session_state.selected_date = _norm_date_str(d)


def cell_label(d: date) -> str:
    base = get_base(d)
    chg = get_change(d)
    deliv = get_delivery_flag(d)

    lines = [f"{d.day:02d}({_dow_kr(d.weekday())})"]

    # 배달불요는 가장 위에 (확실)
    if deliv == "N":
        lines.append("🟥 배달불요")

    # ✅ 기본 먼저
    if base:
        lines.append(f"⬜ 기본: {base}")

    # ✅ 변경은 아래 (확실히 구분)
    if chg:
        lines.append(f"🟨 변경: {chg}")

    return "\n".join(lines)


def cell_kind(d: date) -> str:
    # 배경색 선택용
    chg = get_change(d)
    deliv = get_delivery_flag(d)
    if deliv == "N":
        return "no_delivery"
    if chg:
        return "changed"
    return "normal"


# 요일 헤더
h = st.columns(5)
for i in range(5):
    with h[i]:
        st.markdown(f"**{_dow_kr(i)}**")

# 달력 본문
for w in weeks:
    row = st.columns(5)
    for i in range(5):
        d = w[i]  # Mon..Fri
        with row[i]:
            # 월 외 날짜/빈칸은 "버튼 생성 자체를 안 함" -> 불필요한 네모박스 제거
            if d.month != month:
                st.markdown('<div class="blank-cell"></div>', unsafe_allow_html=True)
                continue

            k = cell_kind(d)
            # 색감: 배달불요(연한빨강), 변경(연한노랑), 기본(흰)
            if k == "no_delivery":
                st.markdown(
                    "<style>.stButton > button{background: rgba(255,0,0,0.06) !important; border-color: rgba(255,0,0,0.35) !important;}</style>",
                    unsafe_allow_html=True,
                )
            elif k == "changed":
                st.markdown(
                    "<style>.stButton > button{background: rgba(255,170,0,0.10) !important; border-color: rgba(255,170,0,0.45) !important;}</style>",
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="calbtn">', unsafe_allow_html=True)
            if st.button(cell_label(d), key=f"cal_{d.isoformat()}"):
                open_editor(d)
            st.markdown("</div>", unsafe_allow_html=True)

# 날짜 편집(팝업)
selected = st.session_state.selected_date
selected_d = _parse_date_str(selected) if selected else None


def editor_body(d: date):
    st.markdown(f"### {d.strftime('%Y-%m-%d')} ({_dow_kr(d.weekday())})")
    cur_base = get_base(d)
    cur_chg = get_change(d)
    cur_del = get_delivery_flag(d)

    del_opt = st.radio(
        "배달 여부",
        options=["Y(배달)", "N(배달불요)"],
        index=0 if cur_del != "N" else 1,
        horizontal=True,
    )
    new_del = "N" if del_opt.startswith("N") else "Y"

    st.markdown("---")

    b1, b2 = st.columns([1.1, 1.0])
    with b1:
        base_pick = st.selectbox("기본메뉴 인덱스 선택", options=index_options, key=f"bp_{d}")
    with b2:
        base_direct = st.text_input("기본메뉴 직접 입력", value=cur_base, key=f"bd_{d}")
    new_base = base_pick if base_pick != "(직접입력)" else base_direct

    c1, c2 = st.columns([1.1, 1.0])
    with c1:
        chg_pick = st.selectbox("변경메뉴 인덱스 선택", options=index_options, key=f"cp_{d}")
    with c2:
        chg_direct = st.text_input("변경메뉴 직접 입력", value=cur_chg, key=f"cd_{d}")
    new_chg = chg_pick if chg_pick != "(직접입력)" else chg_direct

    colx, coly, colz = st.columns([1.2, 1.0, 1.0])
    with colx:
        if st.button("저장", key=f"save_{d}"):
            set_delivery(d, new_del)
            set_base(d, new_base)
            set_change(d, new_chg)
            st.session_state.selected_date = None
            st.rerun()
    with coly:
        if st.button("변경메뉴만 비우기", key=f"clr_{d}"):
            set_change(d, "")
            st.session_state.selected_date = None
            st.rerun()
    with colz:
        if st.button("닫기", key=f"close_{d}"):
            st.session_state.selected_date = None
            st.rerun()


try:
    if selected_d:
        @st.dialog("날짜 입력/수정")
        def _dlg():
            editor_body(selected_d)
        _dlg()
except Exception:
    if selected_d:
        with st.expander("날짜 입력/수정", expanded=True):
            editor_body(selected_d)

st.divider()

# -----------------------------
# 4. 업체 제출용 A4 출력만 제작 (불필요한 글씨 배제)
# - 제목 / 협회(전화) / 공양게 / 달력(메뉴표시) / 변경&배달불요 리스트
# - 안내문/불필요한 캡션/설명 제거
# -----------------------------
st.markdown("## 업체 제출용 A4 출력 (달력 + 리스트 1페이지)")

# A4 HTML
def vendor_a4_html(year: int, month: int) -> str:
    title = f"{output_filename(year, month)}"

    kap = get_logo_tag("kapma", 46) or ""
    mom = get_logo_tag("moms", 46) or ""
    bowl = get_logo_tag("bowl", 52) or ""

    # 달력(월~금) rows
    rows = []
    for w in weeks:
        tds = []
        for i in range(5):
            d = w[i]
            if d.month != month:
                tds.append('<td class="cell out"></td>')
                continue

            base = get_base(d)
            chg = get_change(d)
            deliv = get_delivery_flag(d)

            bg = "#ffffff"
            border = "rgba(0,0,0,0.14)"
            if deliv == "N":
                bg = "#ffe6e6"
                border = "rgba(255,0,0,0.35)"
            if chg:
                bg = "#fff2c2"
                border = "rgba(255,170,0,0.45)"

            blocks = [f'<div class="day">{d.day:02d}({_dow_kr(d.weekday())})</div>']

            # ✅ 배달불요 / 기본 / 변경 (구분 블록)
            if deliv == "N":
                blocks.append('<div class="block red"><span class="badge red">배달불요</span><div class="txt">배달하지 않음</div></div>')
            if base:
                blocks.append(f'<div class="block gry"><span class="badge gry">기본메뉴</span><div class="txt">{base}</div></div>')
            if chg:
                blocks.append(f'<div class="block yel"><span class="badge yel">변경메뉴</span><div class="txt">{chg}</div></div>')

            tds.append(f'<td class="cell" style="background:{bg}; border:1px solid {border};">{"".join(blocks)}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")

    # 리스트(배달불요/변경메뉴)
    days = [d for d in month_days if d.month == month and _is_weekday(d)]
    nod = []
    chg_list = []
    for d in days:
        if get_delivery_flag(d) == "N":
            nod.append(d)
        c = get_change(d)
        if c:
            chg_list.append((d, get_base(d), c))

    def dow(d: date) -> str:
        return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]

    nod_items = "".join([f"<li>{month:02d}/{d.day:02d}({dow(d)}) : 배달불요</li>" for d in nod]) if nod else "<li>해당 없음</li>"
    if chg_list:
        lis = []
        for d, b, c in chg_list:
            if b:
                lis.append(f"<li>{month:02d}/{d.day:02d}({dow(d)}) : {b} → {c}</li>")
            else:
                lis.append(f"<li>{month:02d}/{d.day:02d}({dow(d)}) : (기본미기재) → {c}</li>")
        chg_items = "".join(lis)
    else:
        chg_items = "<li>해당 없음</li>"

    html = f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8"/>
      <style>
        @page {{ size: A4 portrait; margin: 12mm; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; margin:0; color:#111; }}
        .top {{ display:flex; align-items:center; justify-content:space-between; gap:10px; }}
        .left {{ display:flex; align-items:center; gap:10px; }}
        .title {{ font-size: 18px; font-weight: 900; margin:0; line-height:1.15; }}
        .assoc {{ font-size: 12.5px; opacity:0.85; margin-top:4px; font-weight:800; }}
        .mid {{ display:flex; align-items:center; justify-content:center; margin:6px 0 6px 0; }}
        .verse {{
          margin-top: 6px; padding: 10px 12px; border-radius: 14px;
          background: #fffaf2; border: 2px solid rgba(177, 127, 69, 0.35);
          font-size: 13.5px; font-weight: 900; line-height:1.45; white-space: pre-line;
        }}

        table {{ border-collapse: separate; border-spacing: 4px; width:100%; margin-top:8px; }}
        th {{ text-align:left; font-size: 12px; opacity:0.85; padding: 0 0 2px 2px; }}
        .cell {{ height: 78px; vertical-align: top; padding: 8px 8px; border-radius: 12px; }}
        .out {{ background: rgba(0,0,0,0.03); border:1px solid rgba(0,0,0,0.08); }}

        .day {{ font-weight: 900; font-size: 12.5px; margin-bottom:5px; }}
        .block {{ margin-top:5px; padding: 6px 7px; border-radius: 11px; border: 1px solid rgba(0,0,0,0.10); }}
        .txt {{ margin-top: 4px; font-size: 11.2px; font-weight: 900; line-height:1.22; }}
        .badge {{ display:inline-block; padding: 1px 8px; border-radius:999px; font-size: 10.2px; font-weight: 900; }}

        .block.red {{ background: rgba(255,0,0,0.07); border-color: rgba(255,0,0,0.22); }}
        .badge.red {{ background:#ffcccc; }}
        .block.yel {{ background: rgba(255,170,0,0.12); border-color: rgba(255,170,0,0.28); }}
        .badge.yel {{ background:#ffe08a; }}
        .block.gry {{ background: rgba(0,0,0,0.035); border-color: rgba(0,0,0,0.12); }}
        .badge.gry {{ background:#eeeeee; }}

        .grid2 {{ display:grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
        .box {{ border: 1px solid rgba(0,0,0,0.12); border-radius: 12px; padding: 10px 10px; background: rgba(255,255,255,0.95); }}
        .box-title {{ font-weight: 900; margin-bottom: 6px; }}
        ul {{ margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.35; font-weight: 800; }}
      </style>
    </head>
    <body>
      <div class="top">
        <div class="left">
          <div>{mom}</div>
          <div>
            <div class="title">{title}</div>
            <div class="assoc">{ASSOC_LINE}</div>
          </div>
        </div>
        <div>{kap}</div>
      </div>

      <div class="mid">{bowl}</div>
      <div class="verse">{GONGYANG_VERSE}</div>

      <table>
        <thead><tr><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>

      <div class="grid2">
        <div class="box">
          <div class="box-title">🚫 배달불요</div>
          <ul>{nod_items}</ul>
        </div>
        <div class="box">
          <div class="box-title">🔁 변경메뉴</div>
          <ul>{chg_items}</ul>
        </div>
      </div>
    </body>
    </html>
    """
    return html


a4_html = vendor_a4_html(year, month)
st.components.v1.html(a4_html, height=860, scrolling=True)
st.download_button(
    "A4(HTML) 다운로드",
    data=a4_html.encode("utf-8"),
    file_name=f"{output_filename(year, month)}_업체제출용A4.html",
    mime="text/html",
)
