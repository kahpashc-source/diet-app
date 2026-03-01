# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import re
import pandas as pd
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 관리", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N) -> Y:배달, N:배달불요
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# ✅ GitHub 저장소에 이미 있는 파일명 그대로 사용(루트 기준)
# (정확도: 매우 높음) — 스샷에 보이는 파일 리스트와 동일
MOMS_LOGO = APP_DIR / "moms_logo.png"
ASSOC_LOGO = APP_DIR / "association_logo.png"
BOWL_IMG = APP_DIR / "gongyang_bowl.png"

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


def _img_b64_tag(path: Path, height_px: int) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    # png로 가정(현재 파일이 png)
    return f'<img src="data:image/png;base64,{b64}" style="height:{height_px}px; width:auto; object-fit:contain;" />'


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"])
chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
del_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"])
idx_df = _safe_read_csv(MENU_INDEX_PATH, ["name"])

# 인덱스 가나다 정렬
if not idx_df.empty:
    idx_df["name"] = idx_df["name"].astype(str).str.strip()
    idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name")
    _save_csv(idx_df, MENU_INDEX_PATH)

index_options = ["(직접입력)"] + (idx_df["name"].tolist() if not idx_df.empty else [])


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
# UI: 상단(간단히)
# -----------------------------
st.markdown(
    """
    <style>
      .calbtn button{
        width:100% !important;
        text-align:left !important;
        border-radius:14px !important;
        padding:10px 10px !important;
        min-height:112px !important;
        white-space:pre-line !important;
        border: 1px solid rgba(0,0,0,0.14) !important;
      }
      .blank-cell{ height:112px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# 월 선택
today = date.today()
colA, colB, colC = st.columns([1.1, 1.0, 1.6])
with colA:
    year = st.number_input("연도", min_value=2020, max_value=2100, value=today.year, step=1)
with colB:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with colC:
    st.markdown(f"### {int(year)}년 {int(month):02d}월")

year = int(year)
month = int(month)

# 메뉴 인덱스(필요시만)
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
# 달력(월~금) + 날짜 클릭 입력
# - 표시 규칙: 기본메뉴 먼저, 변경메뉴는 아래(강조), 배달불요는 최상단 경고
# - 월 외 날짜는 버튼을 만들지 않아 “불필요한 네모박스”가 생기지 않게 처리
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
    if deliv == "N":
        lines.append("🟥 배달불요")
    if base:
        lines.append(f"⬜ 기본: {base}")
    if chg:
        lines.append(f"🟨 변경: {chg}")
    return "\n".join(lines)


def cell_kind(d: date) -> str:
    if get_delivery_flag(d) == "N":
        return "no_delivery"
    if get_change(d):
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
            if d.month != month:
                st.markdown('<div class="blank-cell"></div>', unsafe_allow_html=True)
                continue

            k = cell_kind(d)
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
# 포스터: 업로드한 형식(가장 마음에 든 스타일)로 고정
# - 좌/우 로고 박스, 중앙 제목(2줄)
# - 월~금 달력 박스
# - 변경: 노란 테두리 + 빨간 글씨 + '변경' 배지
# - 배달불요: 붉은 테두리 + '배달불요' 배지
# - 월 외 빈칸: 점선 박스
# -----------------------------
st.markdown("## 포스터 미리보기 (업로드한 형식 고정)")

def poster_html(year: int, month: int) -> str:
    moms = _img_b64_tag(MOMS_LOGO, 56) or "<div style='font-weight:900;'>MOMS</div>"
    assoc = _img_b64_tag(ASSOC_LOGO, 56) or "<div style='font-weight:900;'>동약협회</div>"

    title = f"맘스락 {month:02d}월<br/>식단 변경"

    # 달력 셀 생성(월~금)
    # 바깥달: 점선 빈칸
    cells_html = []
    for w in weeks:
        for i in range(5):
            d = w[i]
            if d.month != month:
                cells_html.append("<div class='cell empty'></div>")
                continue

            base = get_base(d)
            chg = get_change(d)
            deliv = get_delivery_flag(d)

            cls = "cell"
            badge = ""
            sub = ""

            # 배달불요 우선
            if deliv == "N":
                cls += " no"
                badge = "<span class='pill pill-no'>배달불요</span>"

            # 변경이 있으면 변경 스타일로(배달불요와 동시일 때도 변경은 표시만 추가)
            if chg:
                cls += " chg"
                sub = f"<div class='chgline'><span class='pill pill-chg'>변경</span><span class='chgtext'>{chg}</span></div>"

            dayline = f"<div class='dayline'><span class='daynum'>{d.day:02d}</span><span class='dow'>({_dow_kr(d.weekday())})</span>{badge}</div>"
            base_line = f"<div class='base'>{base}</div>" if base else "<div class='base muted'></div>"

            cells_html.append(
                f"""
                <div class="{cls}">
                  {dayline}
                  {base_line}
                  {sub}
                </div>
                """
            )

    html = f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8"/>
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
          margin:0; background:#ffffff;
        }}
        .wrap {{
          width: 1080px;
          padding: 18px 18px 10px 18px;
        }}
        .top {{
          display:flex; align-items:center; justify-content:space-between;
          margin-bottom: 10px;
        }}
        .logoBox {{
          width: 290px;
          height: 92px;
          border: 2px solid rgba(0,0,0,0.22);
          border-radius: 18px;
          display:flex; align-items:center; justify-content:center;
          background:#fff;
        }}
        .title {{
          text-align:center;
          font-weight: 900;
          font-size: 34px;
          line-height: 1.05;
        }}

        .dowrow {{
          display:grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 14px;
          margin: 10px 4px 6px 4px;
          font-weight: 900;
          opacity: 0.9;
        }}
        .dowrow div {{ text-align:center; }}

        .grid {{
          display:grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 14px;
          margin-top: 2px;
        }}

        .cell {{
          border: 2px solid rgba(0,0,0,0.22);
          border-radius: 14px;
          min-height: 92px;
          padding: 10px 10px 8px 10px;
          background:#fff;
        }}
        .cell.empty {{
          border: 2px dashed rgba(0,0,0,0.22);
          background: #fff;
        }}

        .cell.chg {{
          border-color: rgba(245, 166, 35, 0.85);
          background: rgba(255, 243, 210, 0.55);
        }}
        .cell.no {{
          border-color: rgba(255, 60, 60, 0.65);
          background: rgba(255, 235, 235, 0.55);
        }}

        .dayline {{
          display:flex; align-items:center; gap:8px;
          margin-bottom: 6px;
        }}
        .daynum {{ font-weight: 900; }}
        .dow {{ opacity: 0.75; font-weight: 800; }}
        .pill {{
          display:inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 900;
        }}
        .pill-chg {{ background:#ffe3a1; border:1px solid rgba(245,166,35,0.6); }}
        .pill-no {{ background:#ffd0d0; border:1px solid rgba(255,60,60,0.55); }}

        .base {{
          font-size: 18px;
          font-weight: 900;
          line-height: 1.15;
          margin-top: 2px;
        }}

        .chgline {{
          margin-top: 8px;
          display:flex; align-items:center; gap:8px;
        }}
        .chgtext {{
          font-size: 18px;
          font-weight: 900;
          color: #d10000;
          line-height: 1.15;
        }}
        .muted {{ opacity: 0.0; }} /* 빈칸 높이 유지용 */
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="top">
          <div class="logoBox">{moms}</div>
          <div class="title">{title}</div>
          <div class="logoBox">{assoc}</div>
        </div>

        <div class="dowrow">
          <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
        </div>

        <div class="grid">
          {''.join(cells_html)}
        </div>
      </div>
    </body>
    </html>
    """
    return html

poster = poster_html(year, month)
st.components.v1.html(poster, height=760, scrolling=True)

# A4 출력용(필요한 것만)
st.markdown("## 업체 제출용 A4 출력 (달력 + 리스트 1페이지)")

def vendor_a4_html(year: int, month: int) -> str:
    moms = _img_b64_tag(MOMS_LOGO, 46) or ""
    assoc = _img_b64_tag(ASSOC_LOGO, 46) or ""
    bowl = _img_b64_tag(BOWL_IMG, 52) or ""

    title = output_filename(year, month)

    # 리스트(배달불요/변경)
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

    # 달력은 포스터와 동일한 스타일로 축약(월~금)
    cells = []
    for w in weeks:
        for i in range(5):
            d = w[i]
            if d.month != month:
                cells.append("<div class='cell empty'></div>")
                continue

            base = get_base(d)
            chg = get_change(d)
            deliv = get_delivery_flag(d)

            cls = "cell"
            badge = ""
            sub = ""
            if deliv == "N":
                cls += " no"
                badge = "<span class='pill pill-no'>배달불요</span>"
            if chg:
                cls += " chg"
                sub = f"<div class='chgline'><span class='pill pill-chg'>변경</span><span class='chgtext'>{chg}</span></div>"

            dayline = f"<div class='dayline'><span class='daynum'>{d.day:02d}</span><span class='dow'>({_dow_kr(d.weekday())})</span>{badge}</div>"
            base_line = f"<div class='base'>{base}</div>" if base else "<div class='base muted'></div>"
            cells.append(f"<div class='{cls}'>{dayline}{base_line}{sub}</div>")

    html = f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8"/>
      <style>
        @page {{ size: A4 landscape; margin: 10mm; }}
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
          margin:0; color:#111;
        }}
        .top {{
          display:flex; align-items:center; justify-content:space-between;
          margin-bottom: 6px;
        }}
        .left {{ display:flex; align-items:center; gap:10px; }}
        .title {{ font-size: 18px; font-weight: 900; line-height:1.15; }}
        .assocline {{ font-size: 12px; font-weight: 800; opacity:0.85; margin-top:4px; }}
        .mid {{ display:flex; justify-content:center; margin: 4px 0 6px 0; }}
        .verse {{
          border-radius: 12px;
          padding: 10px 12px;
          background: #fffaf2;
          border: 2px solid rgba(177, 127, 69, 0.35);
          white-space: pre-line;
          font-size: 13px;
          font-weight: 900;
          line-height: 1.45;
        }}

        .dowrow {{
          display:grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 10px;
          margin: 8px 2px 4px 2px;
          font-weight: 900;
          opacity: 0.9;
        }}
        .dowrow div {{ text-align:center; font-size: 12px; }}

        .grid {{
          display:grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 10px;
        }}
        .cell {{
          border: 2px solid rgba(0,0,0,0.22);
          border-radius: 12px;
          min-height: 74px;
          padding: 8px 8px 6px 8px;
          background:#fff;
        }}
        .cell.empty {{
          border: 2px dashed rgba(0,0,0,0.22);
        }}
        .cell.chg {{
          border-color: rgba(245, 166, 35, 0.85);
          background: rgba(255, 243, 210, 0.55);
        }}
        .cell.no {{
          border-color: rgba(255, 60, 60, 0.65);
          background: rgba(255, 235, 235, 0.55);
        }}

        .dayline {{ display:flex; align-items:center; gap:7px; margin-bottom: 5px; }}
        .daynum {{ font-weight: 900; font-size: 12px; }}
        .dow {{ opacity: 0.75; font-weight: 800; font-size: 12px; }}
        .pill {{
          display:inline-block;
          padding: 2px 7px;
          border-radius: 999px;
          font-size: 10.5px;
          font-weight: 900;
        }}
        .pill-chg {{ background:#ffe3a1; border:1px solid rgba(245,166,35,0.6); }}
        .pill-no {{ background:#ffd0d0; border:1px solid rgba(255,60,60,0.55); }}

        .base {{ font-size: 13px; font-weight: 900; line-height: 1.15; }}
        .chgline {{ margin-top: 7px; display:flex; align-items:center; gap:7px; }}
        .chgtext {{ font-size: 13px; font-weight: 900; color:#d10000; line-height:1.15; }}
        .muted {{ opacity:0.0; }}

        .grid2 {{
          display:grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          margin-top: 10px;
        }}
        .box {{
          border: 1px solid rgba(0,0,0,0.12);
          border-radius: 12px;
          padding: 10px 10px;
          background:#fff;
        }}
        .box-title {{ font-weight: 900; margin-bottom: 6px; }}
        ul {{ margin:0; padding-left: 18px; font-size: 12px; font-weight: 800; line-height:1.35; }}
      </style>
    </head>
    <body>
      <div class="top">
        <div class="left">
          <div>{moms}</div>
          <div>
            <div class="title">{title}</div>
            <div class="assocline">{ASSOC_LINE}</div>
          </div>
        </div>
        <div>{assoc}</div>
      </div>

      <div class="mid">{bowl}</div>
      <div class="verse">{GONGYANG_VERSE}</div>

      <div class="dowrow">
        <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
      </div>
      <div class="grid">{''.join(cells)}</div>

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
st.components.v1.html(a4_html, height=820, scrolling=True)
st.download_button(
    "업체 제출용 A4(HTML) 다운로드",
    data=a4_html.encode("utf-8"),
    file_name=f"{output_filename(year, month)}_업체제출용A4.html",
    mime="text/html",
)
