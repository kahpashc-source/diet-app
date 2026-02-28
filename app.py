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
# CSS (시각화 강화)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 2.2rem; }

.cal-cell{
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 14px;
  padding: 10px;
  min-height: 138px;
  background: rgba(255,255,255,0.90);
}
.badge{
  display:inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  border: 1px solid rgba(0,0,0,0.10);
  background: rgba(255,255,255,0.65);
}
.bg-base { background: rgba(255,255,255,0.92); }
.bg-change { background: rgba(255, 245, 180, 0.55); }
.bg-nodelivery { background: rgba(255, 205, 205, 0.50); }
.bg-both { background: linear-gradient(135deg, rgba(255,245,180,0.55), rgba(255,205,205,0.50)); }

.itemline{
  font-size: 13px;
  line-height: 1.25;
  margin: 2px 0;
  opacity: 0.95;
}
.itemlabel{
  font-weight: 900;
  margin-right: 6px;
  opacity: 0.85;
}

div.stButton > button{
  width: 100%;
  border-radius: 12px !important;
  padding: 8px 10px !important;
  font-weight: 800 !important;
}

.poster-wrap{ width:100%; display:flex; justify-content:center; }
.poster{
  width:100%; max-width:900px;
  background:#fff;
  border-radius:18px;
  border: 1px solid rgba(0,0,0,0.10);
  padding:18px 18px 14px 18px;
}
.poster .toprow{ display:flex; align-items:center; justify-content:space-between; gap:14px; }
.poster .logoBox{
  width: 33%;
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 16px;
  padding: 10px;
  display:flex; align-items:center; justify-content:center;
  min-height: 92px;
}
.poster .midBox{
  width: 34%;
  display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  gap: 10px;
}
.poster .title{
  text-align:center;
  font-weight: 900;
  font-size: 34px;
  line-height: 1.08;
  margin-top: 12px;
  margin-bottom: 6px;
}
.poster .subtitle{
  text-align:center;
  font-weight: 800;
  font-size: 18px;
  opacity: 0.85;
  margin-bottom: 14px;
}
.poster .calendar-grid{
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
.poster .cell{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 10px;
  min-height: 120px;
  background: rgba(255,255,255,0.95);
}
.poster .cell .d{ font-weight: 900; font-size: 18px; margin-bottom: 6px; }
.poster .cell .t{ font-size: 12.8px; line-height: 1.25; margin: 2px 0; }

@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');
.poster .gongyang{
  margin-top: 14px;
  border-top: 1px dashed rgba(0,0,0,0.18);
  padding-top: 12px;
  text-align:center;
  font-family: 'Nanum Brush Script', '궁서', 'Gungsuh', serif;
  font-size: 28px;
  line-height: 1.25;
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단
# -----------------------------
st.title("맘스락 식단 변경 프로그램")

top1, top2, top3, top4 = st.columns([1.1, 1.1, 1.0, 1.2], vertical_alignment="center")

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
    st.caption("데이터")
    c1, c2 = st.columns(2)
    with c1:
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
    with c2:
        up = st.file_uploader("백업 ZIP 복원", type=["zip"], label_visibility="collapsed")
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

with top4:
    st.caption("로고/이미지")
    st.write("assets 폴더에 아래 파일을 두면 자동 반영됩니다.")
    st.code("assets/moms_logo.png\nassets/kapma_logo.png\nassets/gongyang_bowl.png", language="text")

st.divider()

# -----------------------------
# 날짜 편집 다이얼로그 (✅ nonlocal 제거: CSV 재로딩/저장 방식)
# -----------------------------
@st.dialog("식단 입력")
def edit_day_dialog(d: date):
    dstr = _to_date_str(d)

    # 매번 최신 상태로 읽어오기(동시성/캐시 문제도 줄임)
    _base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    _change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    _delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
    _menu_index_df = _read_csv(MENU_INDEX_PATH, ["name"])

    cur_base = _get_value(_base_df, dstr, "base_menu")
    cur_change = _get_value(_change_df, dstr, "change_menu")
    cur_del = _get_delivery(_delivery_df, dstr)

    # 인덱스(정렬)
    _menu_index_df["name"] = _menu_index_df["name"].fillna("").astype(str).str.strip()
    _menu_index_df = _menu_index_df[_menu_index_df["name"] != ""].drop_duplicates().sort_values("name")
    menu_list = _menu_index_df["name"].tolist()

    st.subheader(d.strftime("%Y-%m-%d (%a)"))

    st.markdown("**기본 메뉴**")
    bcols = st.columns([1.0, 2.0])
    with bcols[0]:
        b_pick = st.selectbox("인덱스 선택", options=["(선택 없음)"] + menu_list, index=0, key=f"b_pick_{dstr}")
    with bcols[1]:
        base_text = st.text_input("직접 입력", value=cur_base, key=f"b_txt_{dstr}")
    if b_pick != "(선택 없음)":
        base_text = b_pick

    st.markdown("**변경 메뉴**")
    ccols = st.columns([1.0, 2.0])
    with ccols[0]:
        c_pick = st.selectbox("인덱스 선택", options=["(선택 없음)"] + menu_list, index=0, key=f"c_pick_{dstr}")
    with ccols[1]:
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
    save_cols = st.columns([1, 1, 2])

    with save_cols[0]:
        if st.button("저장", use_container_width=True):
            base_text2 = _normalize_menu_text(base_text)
            change_text2 = _normalize_menu_text(change_text)

            # 저장: CSV 재로딩 -> 수정 -> 저장
            base_df2 = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
            change_df2 = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
            delivery_df2 = _read_csv(DELIVERY_PATH, ["date", "delivery"])

            base_df2 = _save_row(base_df2, dstr, "base_menu", base_text2)
            change_df2 = _save_row(change_df2, dstr, "change_menu", change_text2)
            delivery_df2 = _save_delivery(delivery_df2, dstr, yn)

            base_df2.to_csv(BASE_MENU_PATH, index=False, encoding="utf-8-sig")
            change_df2.to_csv(CHANGE_MENU_PATH, index=False, encoding="utf-8-sig")
            delivery_df2.to_csv(DELIVERY_PATH, index=False, encoding="utf-8-sig")

            # 인덱스 누적 저장(가나다 정렬)
            new_items = [x for x in [base_text2, change_text2] if x]
            if new_items:
                idx_df = _read_csv(MENU_INDEX_PATH, ["name"])
                for it in new_items:
                    idx_df = pd.concat([idx_df, pd.DataFrame([{"name": it}])], ignore_index=True)
                idx_df["name"] = idx_df["name"].fillna("").astype(str).str.strip()
                idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().sort_values("name")
                idx_df.to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")

            st.rerun()

    with save_cols[1]:
        if st.button("닫기", use_container_width=True):
            st.rerun()


# -----------------------------
# 달력 렌더 (월~금만)
# -----------------------------
y, m = st.session_state.ym
cal = calendar.Calendar(firstweekday=0)
month_days = list(cal.itermonthdates(y, m))

weeks = []
week = []
for d in month_days:
    if d.weekday() < 5:
        week.append(d)
    if d.weekday() == 6:
        if week:
            weeks.append(week)
        week = []
if week:
    weeks.append(week)

weekday_names = ["월", "화", "수", "목", "금"]

st.subheader(_month_title(y, m))

# 요일 헤더(불필요한 빈줄 없음)
wcols = st.columns(5)
for i, w in enumerate(weekday_names):
    with wcols[i]:
        st.markdown(f"**{w}**")

def cell_status(d: date):
    dstr = _to_date_str(d)
    if d.month != m:
        return "out", "", "", "", False

    b = _get_value(base_df, dstr, "base_menu").strip()
    c = _get_value(change_df, dstr, "change_menu").strip()
    del_ = _get_delivery(delivery_df, dstr).strip().upper()
    no_delivery = (del_ == "N")

    if c and no_delivery:
        bg = "bg-both"
        badge = "변경+배달불요"
    elif c:
        bg = "bg-change"
        badge = "변경"
    elif no_delivery:
        bg = "bg-nodelivery"
        badge = "배달불요"
    else:
        bg = "bg-base"
        badge = "기본"

    return bg, badge, b, c, no_delivery

for w in weeks:
    cols = st.columns(5, gap="small")
    day_map = {d.weekday(): d for d in w}
    for wd in range(5):
        with cols[wd]:
            d = day_map.get(wd, None)
            if d is None or d.month != m:
                st.markdown('<div class="cal-cell bg-base" style="opacity:0.25;"></div>', unsafe_allow_html=True)
                continue

            bg, badge, b, c, no_delivery = cell_status(d)
            dstr = _to_date_str(d)

            if st.button(f"{d.day}", key=f"daybtn_{dstr}", use_container_width=True):
                edit_day_dialog(d)

            lines = []
            if b:
                lines.append(("기본", b))
            if c:
                lines.append(("변경", c))
            if no_delivery:
                lines.append(("배달", "불요"))

            html_lines = ""
            for lab, txt in lines[:3]:
                html_lines += f'<div class="itemline"><span class="itemlabel">{lab}</span>{txt}</div>'

            st.markdown(
                f"""
<div class="cal-cell {bg}">
  <div class="dayline">
    <span class="badge">{badge}</span>
  </div>
  {html_lines if html_lines else '<div class="itemline" style="opacity:0.40;">&nbsp;</div>'}
</div>
""",
                unsafe_allow_html=True,
            )

st.divider()

# -----------------------------
# 업체 전달용 문자(복사용) - 설명문구 없음
# -----------------------------
def build_vendor_text(year: int, month: int) -> str:
    cal2 = calendar.Calendar(firstweekday=0)
    days = [d for d in cal2.itermonthdates(year, month) if d.month == month and d.weekday() < 5]

    changes = []
    nod = []
    for d in days:
        ds = _to_date_str(d)
        c = _get_value(change_df, ds, "change_menu").strip()
        del_ = _get_delivery(delivery_df, ds).strip().upper()
        if c:
            changes.append((d, c))
        if del_ == "N":
            nod.append(d)

    title = f"동약협회입니다.\n{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.\n"
    parts = [title]

    if nod:
        parts.append("🚫【배달불요】")
        for d in nod:
            parts.append(f"▶ {d.month:02d}/{d.day:02d}({['월','화','수','목','금','토','일'][d.weekday()]}) : 배달불요")
        parts.append("")

    if changes:
        parts.append("🟨【변경메뉴】")
        for d, c in changes:
            parts.append(f"▶ {d.month:02d}/{d.day:02d}({['월','화','수','목','금','토','일'][d.weekday()]}) : {c}")
        parts.append("")

    return "\n".join(parts).strip()

left, right = st.columns([1.2, 1.0], gap="large")

with left:
    st.subheader("업체 전달용 문자(복사)")
    txt = build_vendor_text(y, m)
    st.text_area("", value=txt, height=220, label_visibility="collapsed")

with right:
    st.subheader("포스터(스크린샷용) 미리보기")

    moms_b64 = _b64_image_if_exists(MOMS_LOGO_PATH)
    kapma_b64 = _b64_image_if_exists(KAPMA_LOGO_PATH)
    bowl_b64 = _b64_image_if_exists(BOWL_IMG_PATH)

    cal3 = calendar.Calendar(firstweekday=0)
    days = [d for d in cal3.itermonthdates(y, m) if d.month == m and d.weekday() < 5]
    first_wd = date(y, m, 1).weekday()
    pad_left = first_wd if first_wd < 5 else 0
    poster_cells = [None] * pad_left + days
    while len(poster_cells) % 5 != 0:
        poster_cells.append(None)

    def poster_cell_html(d: date | None) -> str:
        if d is None:
            return '<div class="cell" style="opacity:0.18;"></div>'
        ds = _to_date_str(d)
        b = _get_value(base_df, ds, "base_menu").strip()
        c = _get_value(change_df, ds, "change_menu").strip()
        del_ = _get_delivery(delivery_df, ds).strip().upper()
        no_delivery = (del_ == "N")

        if c and no_delivery:
            bg = "background: linear-gradient(135deg, rgba(255,245,180,0.55), rgba(255,205,205,0.50));"
        elif c:
            bg = "background: rgba(255,245,180,0.55);"
        elif no_delivery:
            bg = "background: rgba(255,205,205,0.50);"
        else:
            bg = "background: rgba(255,255,255,0.95);"

        lines = []
        if b:
            lines.append(f'<div class="t"><b>기본</b> {b}</div>')
        if c:
            lines.append(f'<div class="t"><b>변경</b> {c}</div>')
        if no_delivery:
            lines.append(f'<div class="t"><b>배달</b> 불요</div>')

        return f"""
<div class="cell" style="{bg}">
  <div class="d">{d.day}</div>
  {''.join(lines) if lines else '<div class="t" style="opacity:0.35;">&nbsp;</div>'}
</div>
"""

    gongyang_text = (
        "이 음식이 어디에서 왔는가\n"
        "내 덕행으로는 받기가 부끄럽네\n"
        "마음의 온갖 탐욕을 떠나\n"
        "바른 생각으로 이 공양을 받습니다"
    ).replace("\n", "<br/>")

    moms_html = f'<img src="{moms_b64}" style="max-height:68px;max-width:100%;object-fit:contain;" />' if moms_b64 else '<div style="font-weight:900;font-size:18px;">MOMS</div>'
    kapma_html = f'<img src="{kapma_b64}" style="max-height:68px;max-width:100%;object-fit:contain;" />' if kapma_b64 else '<div style="font-weight:900;font-size:18px;">동약협회</div>'
    bowl_html = f'<img src="{bowl_b64}" style="max-height:88px;max-width:100%;object-fit:contain;" />' if bowl_b64 else ""

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

    <div class="calendar-grid">
      {''.join([poster_cell_html(d) for d in poster_cells])}
    </div>

    <div class="gongyang">{gongyang_text}</div>
  </div>
</div>
"""

    components.html(poster_html, height=980, scrolling=True)

st.divider()

# -----------------------------
# A4 1페이지 HTML 출력 (안내문구 없음)
# -----------------------------
def build_a4_html(year: int, month: int) -> str:
    moms_b64 = _b64_image_if_exists(MOMS_LOGO_PATH)
    kapma_b64 = _b64_image_if_exists(KAPMA_LOGO_PATH)
    bowl_b64 = _b64_image_if_exists(BOWL_IMG_PATH)

    moms_html = f'<img src="{moms_b64}" style="height:20mm;max-width:100%;object-fit:contain;" />' if moms_b64 else '<div style="font-weight:900;font-size:18px;">MOMS</div>'
    kapma_html = f'<img src="{kapma_b64}" style="height:20mm;max-width:100%;object-fit:contain;" />' if kapma_b64 else '<div style="font-weight:900;font-size:18px;">동약협회</div>'
    bowl_html = f'<img src="{bowl_b64}" style="height:26mm;max-width:100%;object-fit:contain;" />' if bowl_b64 else ""

    gongyang_text = (
        "이 음식이 어디에서 왔는가\n"
        "내 덕행으로는 받기가 부끄럽네\n"
        "마음의 온갖 탐욕을 떠나\n"
        "바른 생각으로 이 공양을 받습니다"
    ).replace("\n", "<br/>")

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
        ds = _to_date_str(d)
        b = _get_value(base_df, ds, "base_menu").strip()
        c = _get_value(change_df, ds, "change_menu").strip()
        del_ = _get_delivery(delivery_df, ds).strip().upper()
        no_delivery = (del_ == "N")

        cls = "base"
        if c and no_delivery:
            cls = "both"
        elif c:
            cls = "chg"
        elif no_delivery:
            cls = "nod"

        lines = []
        if b:
            lines.append(f"<div><b>기본</b> {b}</div>")
        if c:
            lines.append(f"<div><b>변경</b> {c}</div>")
        if no_delivery:
            lines.append(f"<div><b>배달</b> 불요</div>")

        return f"""
<div class="c {cls}">
  <div class="d">{d.day}</div>
  {''.join(lines) if lines else '<div style="opacity:.35;">&nbsp;</div>'}
</div>
"""

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>맘스락_{year}_{month:02d}_A4</title>
<style>
@page {{ size: A4; margin: 12mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; margin:0; }}
@import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');

.wrap {{ width: 100%; }}
.header {{ display:flex; align-items:center; justify-content:space-between; gap: 8mm; }}
.logo {{
  width: 38%;
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 6mm;
  display:flex; align-items:center; justify-content:center;
  min-height: 30mm;
}}
.mid {{ width: 24%; display:flex; align-items:center; justify-content:center; }}
.title {{
  text-align:center; font-weight: 900;
  font-size: 20pt; line-height: 1.08;
  margin: 6mm 0 2mm 0;
}}
.sub {{
  text-align:center; font-weight: 800;
  font-size: 12pt; opacity: .85;
  margin: 0 0 5mm 0;
}}
.grid {{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 4mm; }}
.c {{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 12px;
  padding: 3.5mm;
  min-height: 28mm;
  background: rgba(255,255,255,0.96);
}}
.c .d {{ font-weight: 900; font-size: 12pt; margin-bottom: 2mm; }}
.c div {{ font-size: 9.2pt; line-height: 1.22; margin: 0.8mm 0; }}
.c.chg {{ background: rgba(255,245,180,0.55); }}
.c.nod {{ background: rgba(255,205,205,0.50); }}
.c.both {{ background: linear-gradient(135deg, rgba(255,245,180,0.55), rgba(255,205,205,0.50)); }}
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
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="logo">{moms_html}</div>
    <div class="mid">{bowl_html}</div>
    <div class="logo">{kapma_html}</div>
  </div>

  <div class="title">맘스락 {month:02d}월<br/>식단(배달) 변경</div>
  <div class="sub">( 인원 : {st.session_state.people_count.strip() or "1"}인 )</div>

  <div class="grid">
    {''.join([cell(d) for d in cells])}
  </div>

  <div class="gong">{gongyang_text}</div>
</div>
</body>
</html>
"""
    return html_doc


a4_html = build_a4_html(y, m)

dcols = st.columns([1.3, 1.7])
with dcols[0]:
    st.subheader("업체 전달용 파일 출력")
    st.download_button(
        "A4 HTML 다운로드",
        data=a4_html.encode("utf-8"),
        file_name=f"맘스락_{y}_{m:02d}_A4_1page.html",
        mime="text/html",
        use_container_width=True,
    )
with dcols[1]:
    st.subheader("A4 미리보기(인쇄 → PDF)")
    components.html(a4_html, height=680, scrolling=True)
