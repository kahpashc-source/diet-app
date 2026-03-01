# app.py  (통째로 교체용)
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
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = APP_DIR / "assets"  # 여기에 로고/그림 넣어주세요
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)  -> Y:배달, N:배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name


GONGYANG_VERSE = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


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
        df = df[cols]
        return df
    except Exception:
        return pd.DataFrame(columns=cols)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
    df = df.copy()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _norm_date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_date_str(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _b64_image_tag(img_path: Path, height_px: int) -> str:
    if not img_path.exists():
        return ""
    data = img_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    ext = img_path.suffix.lower().lstrip(".")
    mime = "png" if ext == "png" else "jpeg" if ext in ("jpg", "jpeg") else "png"
    return f'<img src="data:image/{mime};base64,{b64}" style="height:{height_px}px; width:auto; object-fit:contain;" />'


def _clean_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return name


def _month_title(year: int, month: int) -> str:
    return f"{year}년 {month:02d}월"


def _dow_kr(idx: int) -> str:
    # calendar module: Monday=0
    return ["월", "화", "수", "목", "금", "토", "일"][idx]


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5  # Mon~Fri


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"])
chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
del_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"])
idx_df = _safe_read_csv(MENU_INDEX_PATH, ["name"])

# 메뉴 인덱스: 가나다 자동정렬
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
    return r.iloc[0] if len(r) else "Y"  # 기본은 배달(Y)


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
# 상단(초기화면) 디자인
# -----------------------------
# 파일명은 사용자가 지정한 형식(예: 동약협회 2026년 2월 식단변경 내역)
def output_filename(year: int, month: int) -> str:
    return _clean_filename(f"동약협회 {year}년 {month}월 식단변경 내역")


# 로고/그림 파일명(assets 폴더에 넣어주세요)
# - 협회 로고: kapma_logo.png (예시)
# - 맘스락 로고: moms_logo.png (예시)
# - 공양그릇: gongyang_bowl.png (예시)
KAPMA_LOGO = ASSETS_DIR / "kapma_logo.png"
MOMS_LOGO = ASSETS_DIR / "moms_logo.png"
BOWL_IMG = ASSETS_DIR / "gongyang_bowl.png"

kapma_tag = _b64_image_tag(KAPMA_LOGO, 64)
moms_tag = _b64_image_tag(MOMS_LOGO, 64)
bowl_tag = _b64_image_tag(BOWL_IMG, 72)

st.markdown(
    f"""
    <style>
      .hero {{
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(255,255,255,0.78));
        border: 1px solid rgba(0,0,0,0.08);
      }}
      .hero-top {{
        display:flex; align-items:center; justify-content:space-between; gap:12px;
        margin-bottom: 10px;
      }}
      .hero-mid {{
        display:flex; align-items:center; justify-content:center; gap:14px;
        margin: 6px 0 10px 0;
      }}
      .title {{
        font-size: 26px; font-weight: 800; line-height: 1.12; margin: 0;
      }}
      .subtitle {{
        font-size: 14px; opacity: 0.75; margin: 2px 0 0 0;
      }}
      .verse {{
        font-size: 18px; font-weight: 700; line-height: 1.45;
        white-space: pre-line;
        padding: 12px 14px;
        border-radius: 14px;
        background: rgba(255,255,255,0.80);
        border: 1px dashed rgba(0,0,0,0.12);
      }}
      .badge {{
        display:inline-block; padding: 4px 10px; border-radius: 999px;
        background: rgba(0,0,0,0.05);
        font-size: 12px;
      }}
      .calbtn button {{
        width: 100% !important;
        text-align: left !important;
        border-radius: 14px !important;
        padding: 10px 10px !important;
        min-height: 96px !important;
        white-space: pre-line !important;
        border: 1px solid rgba(0,0,0,0.12) !important;
      }}
      .cell-note {{
        font-size: 12px; opacity: 0.8;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container():
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="hero-top">
          <div style="display:flex; align-items:center; gap:10px;">
            <div>{moms_tag if moms_tag else '<span class="badge">MOMS 로고(assets/moms_logo.png)</span>'}</div>
            <div>
              <div class="title">맘스락 식단 변경 프로그램</div>
              <div class="subtitle">달력 클릭 → 변경/배달 입력 → 포스터(스크린샷/파일) → 업체 제출 문자</div>
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:10px;">
            <div>{kapma_tag if kapma_tag else '<span class="badge">동약협회 로고(assets/kapma_logo.png)</span>'}</div>
          </div>
        </div>

        <div class="hero-mid">
          <div>{bowl_tag if bowl_tag else '<span class="badge">공양그릇(assets/gongyang_bowl.png)</span>'}</div>
        </div>

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
colA, colB, colC = st.columns([1.2, 1.0, 1.8])
with colA:
    year = st.number_input("연도", min_value=2020, max_value=2100, value=today.year, step=1)
with colB:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with colC:
    st.markdown(f"### {_month_title(int(year), int(month))}")

year = int(year)
month = int(month)

# -----------------------------
# 메뉴 인덱스(가나다 순)
# -----------------------------
with st.expander("메뉴 인덱스 관리 (가나다 순 자동 정렬)", expanded=False):
    left, right = st.columns([1.1, 1.0])
    with left:
        new_menu = st.text_input("인덱스에 추가할 메뉴명", value="")
        if st.button("인덱스 추가"):
            add_index_menu(new_menu)
            st.success("추가했습니다.")
            st.rerun()
    with right:
        st.caption("현재 인덱스")
        if idx_df.empty:
            st.write("—")
        else:
            st.dataframe(idx_df, use_container_width=True, height=240)

index_options = ["(직접입력)"] + (idx_df["name"].tolist() if not idx_df.empty else [])

# -----------------------------
# 달력(월~금만 표시) + 날짜 클릭 입력(팝업)
# -----------------------------
cal = calendar.Calendar(firstweekday=0)  # Monday
month_days = [d for d in cal.itermonthdates(year, month)]
# 주 단위로 묶기
weeks = []
week = []
for d in month_days:
    if d.weekday() == 0 and week:
        weeks.append(week)
        week = []
    week.append(d)
if week:
    weeks.append(week)

st.markdown("## 1) 날짜 선택 (월~금)")

# 선택 날짜 상태 유지
if "selected_date" not in st.session_state:
    st.session_state.selected_date = None

def cell_text(d: date) -> str:
    if d.month != month:
        return ""
    if not _is_weekday(d):
        return ""
    base = get_base(d)
    chg = get_change(d)
    deliv = get_delivery_flag(d)
    lines = [f"{d.day:02d}({_dow_kr(d.weekday())})"]
    # 표시 우선순위: 배달불요 / 변경 / 기본
    if deliv == "N":
        lines.append("🟥 배달불요")
    if chg:
        lines.append(f"🟨 변경: {chg}")
    elif base:
        lines.append(f"⬜ 기본: {base}")
    return "\n".join(lines)

def open_editor(d: date):
    st.session_state.selected_date = _norm_date_str(d)

# 헤더(월~금)
hcols = st.columns(5)
for i in range(5):
    with hcols[i]:
        st.markdown(f"**{_dow_kr(i)}**")

# 달력 본문
for w in weeks:
    row = st.columns(5)
    # 월~금 칸만 그림
    for i in range(5):
        d = w[i]  # Monday..Friday
        label = cell_text(d)
        disabled = (d.month != month)
        key = f"cal_{d.isoformat()}"
        with row[i]:
            st.markdown('<div class="calbtn">', unsafe_allow_html=True)
            if st.button(label if label else " ", key=key, disabled=disabled):
                open_editor(d)
            st.markdown("</div>", unsafe_allow_html=True)

# 날짜 편집 팝업(가능하면 st.dialog)
selected = st.session_state.selected_date
selected_d = _parse_date_str(selected) if selected else None

def editor_body(d: date):
    st.markdown(f"### {d.strftime('%Y-%m-%d')} ({_dow_kr(d.weekday())})")

    cur_base = get_base(d)
    cur_chg = get_change(d)
    cur_del = get_delivery_flag(d)

    st.markdown("**배달 여부**")
    del_opt = st.radio("",
                      options=["Y(배달)", "N(배달불요)"],
                      index=0 if cur_del != "N" else 1,
                      horizontal=True)
    new_del = "N" if del_opt.startswith("N") else "Y"

    st.markdown("---")
    st.markdown("**기본 메뉴**")
    bcol1, bcol2 = st.columns([1.1, 1.0])
    with bcol1:
        base_pick = st.selectbox("인덱스 선택", options=index_options, key=f"base_pick_{d}")
    with bcol2:
        base_direct = st.text_input("직접 입력", value=cur_base, key=f"base_direct_{d}")

    new_base = base_direct
    if base_pick != "(직접입력)":
        new_base = base_pick

    st.markdown("**변경 메뉴**")
    ccol1, ccol2 = st.columns([1.1, 1.0])
    with ccol1:
        chg_pick = st.selectbox("인덱스 선택", options=index_options, key=f"chg_pick_{d}")
    with ccol2:
        chg_direct = st.text_input("직접 입력", value=cur_chg, key=f"chg_direct_{d}")

    new_chg = chg_direct
    if chg_pick != "(직접입력)":
        new_chg = chg_pick

    st.caption("※ 변경 메뉴를 입력하면 포스터/문자에서 '변경'으로 표시됩니다.")

    btn1, btn2, btn3 = st.columns([1.2, 1.0, 1.0])
    with btn1:
        if st.button("저장", key=f"save_{d}"):
            set_delivery(d, new_del)
            set_base(d, new_base)
            set_change(d, new_chg)
            st.session_state.selected_date = None
            st.success("저장 완료")
            st.rerun()
    with btn2:
        if st.button("변경메뉴만 비우기", key=f"clear_chg_{d}"):
            set_change(d, "")
            st.success("변경메뉴 삭제")
            st.session_state.selected_date = None
            st.rerun()
    with btn3:
        if st.button("닫기", key=f"close_{d}"):
            st.session_state.selected_date = None
            st.rerun()

try:
    # Streamlit 최신 버전이면 dialog 가능
    if selected_d:
        @st.dialog("날짜 입력/수정")
        def _dlg():
            editor_body(selected_d)
        _dlg()
except Exception:
    # fallback
    if selected_d:
        with st.expander("날짜 입력/수정", expanded=True):
            editor_body(selected_d)

st.divider()

# -----------------------------
# 포스터(달력형) HTML 생성 + 다운로드(HTML/PDF)
# -----------------------------
st.markdown("## 2) 포스터 : 스크린샷으로 찍기 좋도록 구성 (파일 출력 포함)")

poster_big = st.toggle("스크린샷 모드(큰 글씨/큰 칸)", value=True)
phone_text = "동약협회 010-7101-5871"  # 사용자가 원했던 협회 연락처 표기(정확도: 높음)

cell_h = 120 if poster_big else 96
font_title = 28 if poster_big else 24
font_cell = 14 if poster_big else 12

def poster_html(year: int, month: int) -> str:
    title = f"동약협회 {year}년 {month}월 도시락 변경/배달불요"
    # 월~금 표
    # 같은 weeks 사용하되, 월~금만 렌더
    # 로고/그릇은 base64로 포함
    kap = _b64_image_tag(KAPMA_LOGO, 56) or '<div style="font-size:12px;opacity:0.7;">(협회 로고)</div>'
    mom = _b64_image_tag(MOMS_LOGO, 56) or '<div style="font-size:12px;opacity:0.7;">(MOMS 로고)</div>'
    bowl = _b64_image_tag(BOWL_IMG, 64) or '<div style="font-size:12px;opacity:0.7;">(공양그릇)</div>'

    # 표 body 생성
    rows = []
    for w in weeks:
        tds = []
        for i in range(5):
            d = w[i]
            if d.month != month:
                tds.append(f'<td class="cell out"></td>')
                continue
            base = get_base(d)
            chg = get_change(d)
            deliv = get_delivery_flag(d)

            # 배경색: 배달불요(연한빨강) / 변경(연한노랑) / 기본(흰)
            bg = "#ffffff"
            if deliv == "N":
                bg = "#ffe9e9"
            if chg:
                bg = "#fff4cc"

            # 내용
            lines = [f'<div class="d">{d.day:02d}({_dow_kr(d.weekday())})</div>']
            if deliv == "N":
                lines.append('<div class="tag red">배달불요</div>')
            if chg:
                lines.append(f'<div class="tag yel">변경</div><div class="m">{chg}</div>')
            elif base:
                lines.append(f'<div class="tag gry">기본</div><div class="m">{base}</div>')

            tds.append(f'<td class="cell" style="background:{bg};">{"".join(lines)}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")

    html = f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; margin:0; }}
        .wrap {{ padding: 18px; width: 1120px; }}
        .top {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
        .mid {{ display:flex; align-items:center; justify-content:center; gap:14px; margin: 8px 0 10px 0; }}
        .title {{ font-size:{font_title}px; font-weight: 900; margin:0; line-height:1.15; }}
        .sub {{ font-size:13px; opacity:0.8; margin-top:6px; }}
        .verse {{ margin-top: 10px; padding: 10px 12px; border-radius: 12px; border:1px dashed rgba(0,0,0,0.18);
                 font-size: 16px; font-weight: 700; line-height:1.45; white-space: pre-line; }}
        table {{ border-collapse: separate; border-spacing: 10px; width:100%; }}
        th {{ text-align:left; font-size: 14px; opacity:0.85; }}
        .cell {{ height:{cell_h}px; vertical-align: top; padding: 10px 10px; border-radius: 14px; border: 1px solid rgba(0,0,0,0.12); }}
        .out {{ background: rgba(0,0,0,0.03); }}
        .d {{ font-weight: 900; font-size:{font_cell+2}px; margin-bottom:6px; }}
        .tag {{ display:inline-block; padding: 2px 8px; border-radius:999px; font-size:{font_cell-2}px; font-weight:800; margin-right:6px; }}
        .red {{ background:#ffcccc; }}
        .yel {{ background:#ffe08a; }}
        .gry {{ background:#eeeeee; }}
        .m {{ margin-top:6px; font-size:{font_cell}px; font-weight:800; line-height:1.25; }}
        .foot {{ margin-top: 8px; font-size: 12px; opacity:0.8; text-align:right; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="top">
          <div style="display:flex; align-items:center; gap:10px;">
            {mom}
            <div>
              <div class="title">{title}</div>
              <div class="sub">{phone_text}</div>
            </div>
          </div>
          <div>{kap}</div>
        </div>

        <div class="mid">{bowl}</div>

        <div class="verse">{GONGYANG_VERSE}</div>

        <div style="height:10px;"></div>

        <table>
          <thead>
            <tr>
              <th>월</th><th>화</th><th>수</th><th>목</th><th>금</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>

        <div class="foot">파일명: {output_filename(year, month)}</div>
      </div>
    </body>
    </html>
    """
    return html

html_str = poster_html(year, month)

# 미리보기
st.components.v1.html(html_str, height=760 if poster_big else 680, scrolling=True)

# 다운로드(HTML)
html_bytes = html_str.encode("utf-8")
st.download_button(
    "포스터 HTML 다운로드",
    data=html_bytes,
    file_name=f"{output_filename(year, month)}.html",
    mime="text/html",
)

# PDF 출력(외부 라이브러리 없이도 가능하게: reportlab 사용)
# - reportlab이 설치되어 있다면 A4 1페이지로 생성
pdf_ok = True
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
except Exception:
    pdf_ok = False

def make_pdf_from_html_like(year: int, month: int) -> bytes:
    """
    HTML을 그대로 렌더링하진 않고, '달력형 포스터'를 PDF로 1페이지 그립니다.
    (정확도: 높음 / 스타일은 HTML과 100% 동일하진 않지만, A4 1페이지 목적에 최적화)
    """
    buf = io.BytesIO()
    pagesize = landscape(A4)  # 가로 A4가 달력에 더 유리
    c = canvas.Canvas(buf, pagesize=pagesize)
    W, H = pagesize

    margin = 26
    x0, y0 = margin, margin
    # 헤더 영역
    title = f"동약협회 {year}년 {month}월 도시락 변경/배달불요"
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x0, H - margin - 18, title)
    c.setFont("Helvetica", 10)
    c.drawRightString(W - margin, H - margin - 16, phone_text)

    # 로고/그릇 (있으면)
    def draw_img(path: Path, x: float, y: float, h: float):
        if not path.exists():
            return
        try:
            img = ImageReader(str(path))
            iw, ih = img.getSize()
            w = h * (iw / ih)
            c.drawImage(img, x, y, width=w, height=h, mask="auto")
        except Exception:
            pass

    draw_img(MOMS_LOGO, x0, H - margin - 70, 36)
    draw_img(KAPMA_LOGO, W - margin - 160, H - margin - 70, 36)
    draw_img(BOWL_IMG, (W / 2) - 40, H - margin - 78, 44)

    # 공양게
    verse_y = H - margin - 92
    c.setFont("Helvetica-Bold", 11)
    lines = GONGYANG_VERSE.splitlines()
    yy = verse_y
    for line in lines:
        c.drawCentredString(W / 2, yy, line)
        yy -= 14

    # 달력 그리드
    grid_top = yy - 14
    grid_left = x0
    grid_right = W - margin
    grid_width = grid_right - grid_left
    col_w = grid_width / 5

    # 헤더 요일
    c.setFont("Helvetica-Bold", 11)
    for i, name in enumerate(["월", "화", "수", "목", "금"]):
        c.drawString(grid_left + col_w * i + 6, grid_top, name)

    # 셀
    cell_h_pdf = 66
    start_y = grid_top - 14
    c.setFont("Helvetica", 9)

    row_idx = 0
    for w in weeks:
        y = start_y - row_idx * (cell_h_pdf + 8)
        # 페이지 내에서 넘치면 중단(1페이지 유지)
        if y - cell_h_pdf < margin + 10:
            break

        for i in range(5):
            d = w[i]
            x = grid_left + col_w * i
            # 밖의 달
            if d.month != month:
                c.setStrokeColorRGB(0.85, 0.85, 0.85)
                c.setFillColorRGB(0.97, 0.97, 0.97)
            else:
                base = get_base(d)
                chg = get_change(d)
                deliv = get_delivery_flag(d)

                # 배경색
                if deliv == "N":
                    c.setFillColorRGB(1.0, 0.92, 0.92)  # 연한 빨강
                elif chg:
                    c.setFillColorRGB(1.0, 0.97, 0.80)  # 연한 노랑
                else:
                    c.setFillColorRGB(1, 1, 1)

                c.setStrokeColorRGB(0.75, 0.75, 0.75)

            c.roundRect(x + 2, y - cell_h_pdf, col_w - 6, cell_h_pdf, 10, stroke=1, fill=1)

            if d.month == month:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica-Bold", 10)
                c.drawString(x + 10, y - 16, f"{d.day:02d}({_dow_kr(d.weekday())})")
                c.setFont("Helvetica", 9)
                base = get_base(d)
                chg = get_change(d)
                deliv = get_delivery_flag(d)

                yy2 = y - 30
                if deliv == "N":
                    c.drawString(x + 10, yy2, "배달불요")
                    yy2 -= 12
                if chg:
                    c.drawString(x + 10, yy2, f"변경: {chg}")
                elif base:
                    c.drawString(x + 10, yy2, f"기본: {base}")

        row_idx += 1

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawRightString(W - margin, margin - 2, f"파일명: {output_filename(year, month)}")
    c.showPage()
    c.save()
    return buf.getvalue()

if pdf_ok:
    pdf_bytes = make_pdf_from_html_like(year, month)
    st.download_button(
        "포스터 PDF(A4 1페이지) 다운로드",
        data=pdf_bytes,
        file_name=f"{output_filename(year, month)}.pdf",
        mime="application/pdf",
    )
else:
    st.info("PDF 출력은 reportlab 설치가 필요합니다. (현재 환경에서 import 실패)")

st.divider()

# -----------------------------
# 업체 제출 문자(달력 형태 + 요약문)
# -----------------------------
st.markdown("## 3) 업체 제출 문자 (달력 형태)")

# 달력 형태 텍스트(월~금)
def vendor_calendar_text(year: int, month: int) -> str:
    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")
    lines.append("[달력형 요약(월~금)]")
    lines.append("월 | 화 | 수 | 목 | 금")
    lines.append("-" * 24)

    # 각 칸: DD + 상태(배/변/기)
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

# 리스트형 상세(업체가 더 좋아할 때도 있어서 같이 제공)
def vendor_detail_text(year: int, month: int) -> str:
    # 해당월 날짜들(월~금만)
    days = [d for d in month_days if d.month == month and _is_weekday(d)]
    nod = []
    chg = []
    for d in days:
        deliv = get_delivery_flag(d)
        c = get_change(d)
        b = get_base(d)
        if deliv == "N":
            nod.append(d)
        if c:
            # 기본이 있으면 "기본 → 변경" 형태
            if b:
                chg.append((d, b, c))
            else:
                chg.append((d, "", c))

    def dow(d: date) -> str:
        return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]

    out = []
    out.append("동약협회입니다.")
    out.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    if nod:
        out.append("🚫【배달불요】")
        for d in nod:
            out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : 배달불요")
    if chg:
        out.append("🔁【변경메뉴】")
        for d, b, c in chg:
            if b:
                out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : {b} → {c}")
            else:
                out.append(f"▶ {month:02d}/{d.day:02d}({dow(d)}) : (기본미기재) → {c}")
    out.append("감사합니다.")
    return "\n".join(out)

cal_text = vendor_calendar_text(year, month)
detail_text = vendor_detail_text(year, month)

left, right = st.columns([1.1, 1.1])
with left:
    st.markdown("**달력 형태(복사/붙여넣기)**")
    st.code(cal_text, language="text")
with right:
    st.markdown("**상세 목록(복사/붙여넣기)**")
    st.code(detail_text, language="text")

st.caption("※ ‘달력형’과 ‘상세 목록’ 중 업체가 선호하는 형식을 사용하시면 됩니다.")
