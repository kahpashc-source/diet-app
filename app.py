# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import io
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

# 로컬 assets 폴더도 지원(없어도 됨)
ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N) -> Y:배달, N:배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# -----------------------------
# 이미지(GitHub raw URL 우선 → 없으면 로컬 assets)
# -----------------------------
# ✅ 아래 3개 URL은 "raw.githubusercontent.com/..." 형태여야 합니다.
# 부회장님 GitHub에 올려둔 파일의 "Raw" 링크를 그대로 붙여 넣으면 됩니다.
# (정확도: 매우 높음)
MOMS_LOGO_URL = ""       # 예: "https://raw.githubusercontent.com/<user>/<repo>/main/assets/moms_logo.png"
KAPMA_LOGO_URL = ""      # 예: "https://raw.githubusercontent.com/<user>/<repo>/main/assets/kapma_logo.png"
BOWL_IMG_URL = ""        # 예: "https://raw.githubusercontent.com/<user>/<repo>/main/assets/gongyang_bowl.png"

# 로컬 파일명(있으면 자동 사용)
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
    data = path.read_bytes()
    return _img_b64_tag_from_bytes(data, height_px)


def get_logo_tag(kind: str, height_px: int) -> str:
    # kind: moms/kapma/bowl
    if kind == "moms":
        data = _fetch_bytes(MOMS_LOGO_URL)
        tag = _img_b64_tag_from_bytes(data, height_px) if data else ""
        return tag or _img_b64_tag_from_local(MOMS_LOGO_LOCAL, height_px)
    if kind == "kapma":
        data = _fetch_bytes(KAPMA_LOGO_URL)
        tag = _img_b64_tag_from_bytes(data, height_px) if data else ""
        return tag or _img_b64_tag_from_local(KAPMA_LOGO_LOCAL, height_px)
    if kind == "bowl":
        data = _fetch_bytes(BOWL_IMG_URL)
        tag = _img_b64_tag_from_bytes(data, height_px) if data else ""
        return tag or _img_b64_tag_from_local(BOWL_IMG_LOCAL, height_px)
    return ""


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"])
chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
del_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"])
idx_df = _safe_read_csv(MENU_INDEX_PATH, ["name"])

# 메뉴 인덱스 가나다 정렬
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


# -----------------------------
# 상단(초기화면)
# -----------------------------
moms_tag = get_logo_tag("moms", 64) or '<span class="badge">MOMS 로고</span>'
kapma_tag = get_logo_tag("kapma", 64) or '<span class="badge">동약협회 로고</span>'
bowl_tag = get_logo_tag("bowl", 74) or '<span class="badge">공양그릇</span>'

st.markdown(
    """
    <style>
      .hero{
        border-radius:18px; padding:18px;
        background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(255,255,255,0.78));
        border:1px solid rgba(0,0,0,0.08);
      }
      .hero-top{ display:flex; align-items:center; justify-content:space-between; gap:12px; }
      .title{ font-size:28px; font-weight:900; margin:0; line-height:1.15; }
      .subtitle{ font-size:14px; opacity:0.78; margin-top:4px; }
      .verse{
        margin-top:10px; padding:12px 14px; border-radius:14px;
        background: rgba(255,255,255,0.82);
        border: 1px dashed rgba(0,0,0,0.18);
        white-space: pre-line;
        font-size:18px; font-weight:800; line-height:1.45;
      }
      .badge{
        display:inline-block; padding:4px 10px; border-radius:999px;
        background: rgba(0,0,0,0.06); font-size:12px;
      }
      .calbtn button{
        width:100% !important; text-align:left !important;
        border-radius:14px !important; padding:10px 10px !important;
        min-height:96px !important; white-space:pre-line !important;
        border:1px solid rgba(0,0,0,0.12) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="hero">', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="hero-top">
      <div style="display:flex; align-items:center; gap:10px;">
        <div>{moms_tag}</div>
        <div>
          <div class="title">맘스락 식단 변경 관리</div>
          <div class="subtitle">달력 클릭 → 저장 → 포스터(A4/스크린샷) → 업체 제출용 A4</div>
        </div>
      </div>
      <div>{kapma_tag}</div>
    </div>
    <div style="display:flex; justify-content:center; margin-top:8px;">{bowl_tag}</div>
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
c1, c2, c3 = st.columns([1.2, 1.0, 1.8])
with c1:
    year = st.number_input("연도", min_value=2020, max_value=2100, value=today.year, step=1)
with c2:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with c3:
    st.markdown(f"### {year}년 {month:02d}월")

year = int(year)
month = int(month)

# -----------------------------
# 메뉴 인덱스
# -----------------------------
with st.expander("메뉴 인덱스 관리 (가나다 순 자동 정렬)", expanded=False):
    l, r = st.columns([1.1, 1.0])
    with l:
        new_menu = st.text_input("인덱스에 추가할 메뉴명", value="")
        if st.button("인덱스 추가"):
            add_index_menu(new_menu)
            st.success("추가했습니다.")
            st.rerun()
    with r:
        st.caption("현재 인덱스")
        if idx_df.empty:
            st.write("—")
        else:
            st.dataframe(idx_df, use_container_width=True, height=240)

index_options = ["(직접입력)"] + (idx_df["name"].tolist() if not idx_df.empty else [])

# -----------------------------
# 달력(월~금) + 날짜 클릭 입력
# -----------------------------
cal = calendar.Calendar(firstweekday=0)  # Monday
month_days = [d for d in cal.itermonthdates(year, month)]

# 주 단위 분리
weeks: list[list[date]] = []
wk: list[date] = []
for d in month_days:
    if d.weekday() == 0 and wk:
        weeks.append(wk)
        wk = []
    wk.append(d)
if wk:
    weeks.append(wk)

st.markdown("## 1) 날짜 선택 (월~금)")

if "selected_date" not in st.session_state:
    st.session_state.selected_date = None


def open_editor(d: date):
    st.session_state.selected_date = _norm_date_str(d)


def cell_text(d: date) -> str:
    if d.month != month or not _is_weekday(d):
        return ""
    base = get_base(d)
    chg = get_change(d)
    deliv = get_delivery_flag(d)

    lines = [f"{d.day:02d}({_dow_kr(d.weekday())})"]

    # ✅ 박스 안에서 “확실히 구분” (배달불요/변경/기본을 각각 줄로)
    if deliv == "N":
        lines.append("🟥 배달불요")
    if chg:
        lines.append(f"🟨 변경: {chg}")
    if base:
        lines.append(f"⬜ 기본: {base}")

    return "\n".join(lines)


# 요일 헤더
hcols = st.columns(5)
for i in range(5):
    with hcols[i]:
        st.markdown(f"**{_dow_kr(i)}**")

# 달력 버튼
for w in weeks:
    row = st.columns(5)
    for i in range(5):
        d = w[i]  # Mon..Fri
        disabled = (d.month != month)
        label = cell_text(d) if not disabled else ""
        with row[i]:
            st.markdown('<div class="calbtn">', unsafe_allow_html=True)
            if st.button(label if label else " ", key=f"cal_{d.isoformat()}", disabled=disabled):
                open_editor(d)
            st.markdown("</div>", unsafe_allow_html=True)

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

    c1_, c2_ = st.columns([1.1, 1.0])
    with c1_:
        chg_pick = st.selectbox("변경메뉴 인덱스 선택", options=index_options, key=f"cp_{d}")
    with c2_:
        chg_direct = st.text_input("변경메뉴 직접 입력", value=cur_chg, key=f"cd_{d}")
    new_chg = chg_pick if chg_pick != "(직접입력)" else chg_direct

    colx, coly, colz = st.columns([1.2, 1.0, 1.0])
    with colx:
        if st.button("저장", key=f"save_{d}"):
            set_delivery(d, new_del)
            set_base(d, new_base)
            set_change(d, new_chg)
            st.session_state.selected_date = None
            st.success("저장 완료")
            st.rerun()
    with coly:
        if st.button("변경메뉴만 비우기", key=f"clr_{d}"):
            set_change(d, "")
            st.session_state.selected_date = None
            st.success("변경메뉴 삭제")
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
# 2) 포스터 (스크린샷 + A4 출력)
# -----------------------------
st.markdown("## 2) 포스터 : 스크린샷/출력(A4) 최적화")

poster_big = st.toggle("스크린샷 모드(큰 글씨/큰 칸)", value=True)

# ✅ 핵심: 요일 밑 '빈칸' 제거
# - border-spacing을 너무 크게 주면 헤더 아래가 '한 줄 빈칸'처럼 보입니다.
# - 여기서는 spacing을 작게(4px)로 줄이고, 헤더와 tbody 간격을 없앴습니다. (정확도: 매우 높음)
cell_h = 124 if poster_big else 98
font_title = 28 if poster_big else 24
font_cell = 14 if poster_big else 12

def poster_html(year: int, month: int) -> str:
    title = f"동약협회 {year}년 {month:02d}월 도시락 변경/배달불요"

    kap = get_logo_tag("kapma", 56) or '<span style="font-size:12px;opacity:0.7;">(협회 로고)</span>'
    mom = get_logo_tag("moms", 56) or '<span style="font-size:12px;opacity:0.7;">(MOMS 로고)</span>'
    bowl = get_logo_tag("bowl", 62) or '<span style="font-size:12px;opacity:0.7;">(공양그릇)</span>'

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

            # ✅ 칸 색상 변화 + 테두리 강조
            # - 배달불요: 붉은 배경 + 붉은 테두리
            # - 변경: 노란 배경 + 노란 테두리
            # - 기본만: 흰 배경 + 기본 테두리
            bg = "#ffffff"
            border = "rgba(0,0,0,0.14)"
            if deliv == "N":
                bg = "#ffe6e6"
                border = "rgba(255,0,0,0.35)"
            if chg:
                bg = "#fff2c2"
                border = "rgba(255,170,0,0.45)"

            # ✅ 박스 안에서 확실한 구분: 배달/변경/기본을 각각 badge + block 으로 표시
            blocks = [f'<div class="day">{d.day:02d}({_dow_kr(d.weekday())})</div>']

            if deliv == "N":
                blocks.append('<div class="block red"><span class="badge red">배달불요</span><div class="txt">배달하지 않음</div></div>')

            if chg:
                blocks.append(f'<div class="block yel"><span class="badge yel">변경메뉴</span><div class="txt">{chg}</div></div>')

            if base:
                blocks.append(f'<div class="block gry"><span class="badge gry">기본메뉴</span><div class="txt">{base}</div></div>')

            tds.append(f'<td class="cell" style="background:{bg}; border:1px solid {border};">{"".join(blocks)}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")

    html = f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; margin:0; }}
        .wrap {{ padding: 16px; width: 1120px; }}
        .top {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
        .left {{ display:flex; align-items:center; gap:10px; }}
        .title {{ font-size:{font_title}px; font-weight: 900; margin:0; line-height:1.15; }}
        .sub {{ font-size:13px; opacity:0.85; margin-top:6px; }}
        .mid {{ display:flex; align-items:center; justify-content:center; gap:14px; margin: 6px 0 8px 0; }}
        .verse {{ margin-top: 6px; padding: 10px 12px; border-radius: 12px; border:1px dashed rgba(0,0,0,0.18);
                 font-size: 16px; font-weight: 800; line-height:1.45; white-space: pre-line; }}

        /* ✅ 요일 밑 빈칸처럼 보이는 현상 방지 */
        table {{ border-collapse: separate; border-spacing: 4px; width:100%; margin-top:8px; }}
        thead tr {{ margin:0; padding:0; }}
        th {{ text-align:left; font-size: 14px; opacity:0.85; padding: 0 0 2px 2px; }}

        .cell {{
          height:{cell_h}px;
          vertical-align: top;
          padding: 10px 10px;
          border-radius: 14px;
        }}
        .out {{ background: rgba(0,0,0,0.03); border:1px solid rgba(0,0,0,0.08); }}

        .day {{ font-weight: 900; font-size:{font_cell+2}px; margin-bottom:6px; }}

        .block {{
          margin-top:6px;
          padding: 7px 8px;
          border-radius: 12px;
          border: 1px solid rgba(0,0,0,0.10);
        }}
        .block .txt {{ margin-top: 4px; font-size:{font_cell}px; font-weight: 900; line-height:1.22; }}

        .badge {{
          display:inline-block; padding: 2px 9px; border-radius:999px;
          font-size:{font_cell-2}px; font-weight: 900;
        }}

        .block.red {{ background: rgba(255,0,0,0.07); border-color: rgba(255,0,0,0.22); }}
        .badge.red {{ background:#ffcccc; }}

        .block.yel {{ background: rgba(255,170,0,0.12); border-color: rgba(255,170,0,0.28); }}
        .badge.yel {{ background:#ffe08a; }}

        .block.gry {{ background: rgba(0,0,0,0.035); border-color: rgba(0,0,0,0.12); }}
        .badge.gry {{ background:#eeeeee; }}

        .foot {{ margin-top: 8px; font-size: 12px; opacity:0.8; text-align:right; }}
        .a4 {{ font-size: 11px; opacity:0.75; margin-top:6px; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="top">
          <div class="left">
            {mom}
            <div>
              <div class="title">{title}</div>
              <div class="sub">{ASSOC_LINE}</div>
            </div>
          </div>
          <div>{kap}</div>
        </div>

        <div class="mid">{bowl}</div>
        <div class="verse">{GONGYANG_VERSE}</div>

        <table>
          <thead>
            <tr><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>

        <div class="foot">파일명: {output_filename(year, month)}</div>
        <div class="a4">A4 출력: HTML 다운로드 → Ctrl+P → PDF 저장</div>
      </div>
    </body>
    </html>
    """
    return html

poster = poster_html(year, month)

# 미리보기
st.components.v1.html(poster, height=780 if poster_big else 700, scrolling=True)

# 다운로드(HTML)
st.download_button(
    "포스터 HTML 다운로드(A4 인쇄용)",
    data=poster.encode("utf-8"),
    file_name=f"{output_filename(year, month)}_포스터.html",
    mime="text/html",
)

st.caption("※ 한글 깨짐 방지: 다운로드한 HTML을 열고 Ctrl+P → ‘PDF로 저장’(또는 Microsoft Print to PDF)로 A4 1페이지 저장")

st.divider()

# -----------------------------
# 3) 업체 제출 문자 (A4 포함)
# -----------------------------
st.markdown("## 3) 업체 제출 문자 (달력형 + A4 출력)")

def vendor_calendar_text(year: int, month: int) -> str:
    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")
    lines.append("[달력형 요약(월~금)]")
    lines.append("월 | 화 | 수 | 목 | 금")
    lines.append("-" * 24)

    for w in weeks:
        row = []
        for i in range(5):
            d = w[i]
            if d.month != month:
                row.append("   ")
                continue
            base = get_base(d)
            chg = get_change(d)
            deliv = get_delivery_flag(d)

            tag = "기"
            if deliv == "N":
                tag = "배"
            if chg:
                tag = "변"
            row.append(f"{d.day:02d}{tag}")
        lines.append(" | ".join(row))

    lines.append("")
    lines.append("표기: 배=배달불요, 변=변경, 기=기본")
    return "\n".join(lines)

def vendor_detail_text(year: int, month: int) -> str:
    days = [d for d in month_days if d.month == month and _is_weekday(d)]
    nod = []
    chg_list = []
    for d in days:
        deliv = get_delivery_flag(d)
        c = get_change(d)
        b = get_base(d)
        if deliv == "N":
            nod.append(d)
        if c:
            chg_list.append((d, b, c))

    def dow(d: date) -> str:
        return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]

    out = []
    out.append("동약협회입니다.")
    out.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    if nod:
        out.append("🚫【배달불요】")
        for d in nod:
            out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : 배달불요")
    if chg_list:
        out.append("🔁【변경메뉴】")
        for d, b, c in chg_list:
            if b:
                out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : {b} → {c}")
            else:
                out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : (기본미기재) → {c}")
    out.append("감사합니다.")
    return "\n".join(out)

def vendor_a4_html(year: int, month: int) -> str:
    title = f"{output_filename(year, month)} (업체 제출용)"

    kap = get_logo_tag("kapma", 48) or '<span style="font-size:12px;opacity:0.7;">(협회 로고)</span>'
    mom = get_logo_tag("moms", 48) or '<span style="font-size:12px;opacity:0.7;">(MOMS 로고)</span>'
    bowl = get_logo_tag("bowl", 54) or '<span style="font-size:12px;opacity:0.7;">(공양그릇)</span>'

    # 달력 rows (포스터와 동일한 “구분 블록” 스타일)
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
            if deliv == "N":
                blocks.append('<div class="block red"><span class="badge red">배달불요</span><div class="txt">배달하지 않음</div></div>')
            if chg:
                blocks.append(f'<div class="block yel"><span class="badge yel">변경메뉴</span><div class="txt">{chg}</div></div>')
            if base:
                blocks.append(f'<div class="block gry"><span class="badge gry">기본메뉴</span><div class="txt">{base}</div></div>')

            tds.append(f'<td class="cell" style="background:{bg}; border:1px solid {border};">{"".join(blocks)}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")

    # 리스트(변경/배달불요)
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
    chg_items = ""
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
          margin-top: 6px; padding: 8px 10px; border-radius: 12px; border:1px dashed rgba(0,0,0,0.18);
          font-size: 13.5px; font-weight: 800; line-height:1.45; white-space: pre-line;
        }}

        table {{ border-collapse: separate; border-spacing: 4px; width:100%; margin-top:8px; }}
        th {{ text-align:left; font-size: 12px; opacity:0.85; padding: 0 0 2px 2px; }}
        .cell {{ height: 74px; vertical-align: top; padding: 8px 8px; border-radius: 12px; }}
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
        .box {{ border: 1px solid rgba(0,0,0,0.12); border-radius: 12px; padding: 10px 10px; background: rgba(255,255,255,0.9); }}
        .box-title {{ font-weight: 900; margin-bottom: 6px; }}
        ul {{ margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.35; font-weight: 800; }}
        .foot {{ margin-top: 8px; font-size: 11px; opacity: 0.75; text-align:right; }}
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

      <div class="foot">인쇄: Ctrl+P → PDF로 저장</div>
    </body>
    </html>
    """
    return html

# 복사용
cal_text = vendor_calendar_text(year, month)
detail_text = vendor_detail_text(year, month)
l, r = st.columns([1.05, 1.05])
with l:
    st.markdown("**달력 형태(복사/붙여넣기)**")
    st.code(cal_text, language="text")
with r:
    st.markdown("**상세 목록(복사/붙여넣기)**")
    st.code(detail_text, language="text")

st.markdown("### 업체 제출용 A4 출력(달력 + 리스트 1페이지)")
a4_html = vendor_a4_html(year, month)
st.components.v1.html(a4_html, height=820, scrolling=True)
st.download_button(
    "업체 제출용 A4(HTML) 다운로드",
    data=a4_html.encode("utf-8"),
    file_name=f"{output_filename(year, month)}_업체제출용A4.html",
    mime="text/html",
)
st.caption("※ HTML 열기 → Ctrl+P → ‘PDF로 저장’(또는 Microsoft Print to PDF)로 A4 1페이지 저장")
