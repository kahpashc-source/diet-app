# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import re
import unicodedata

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="맘스락 식단 관리 시스템",
    layout="wide",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
ASSETS_DIR = APP_DIR / "assets"
for d in [DATA_DIR, ASSETS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 데이터 경로
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

# 이미지 경로
MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"      # ✅ 있으면 사용
DOSIRAK_PATH = ASSETS_DIR / "dosirak.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

GONGYANG_TEXT = (
    "이 음식이 어디에서 왔는가\n"
    "내 덕행으로는 받기가 부끄럽네\n"
    "마음의 온갖 탐욕을 떠나\n"
    "몸을 지탱하는 약으로 알아\n"
    "이 공양을 받습니다"
)

# ✅ 토/일 제외
WEEKDAYS_KO = ["월", "화", "수", "목", "금"]


# -----------------------------
# 유틸
# -----------------------------
def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _read_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame(columns=cols)

    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].fillna("")


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _key(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_value(df: pd.DataFrame, d: date, col: str) -> str:
    k = _key(d)
    row = df[df["date"] == k]
    return str(row.iloc[0][col]).strip() if not row.empty else ""


def _set_value(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    k = _key(d)
    value = _normalize_text(value)

    if "date" not in df.columns:
        df["date"] = ""

    if (df["date"] == k).any():
        df.loc[df["date"] == k, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": k, col: value}])], ignore_index=True)

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _is_weekday(d: date) -> bool:
    return d.weekday() <= 4


def _img_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _safe_short(s: str, n: int = 14) -> str:
    s = _normalize_text(s)
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "…"


def _month_weeks_mon_fri(year: int, month: int) -> list[list[date]]:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    return [w[:5] for w in weeks]  # 월~금


def _month_title(year: int, month: int) -> str:
    return f"{year}년 {month:02d}월"


# -----------------------------
# 세션 상태 초기화
# -----------------------------
if "base_df" not in st.session_state:
    st.session_state.base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
if "change_df" not in st.session_state:
    st.session_state.change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
if "delivery_df" not in st.session_state:
    st.session_state.delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
if "menu_index_df" not in st.session_state:
    idx = _read_csv(MENU_INDEX_PATH, ["name"])
    idx["name"] = idx["name"].map(_normalize_text)
    idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
    st.session_state.menu_index_df = idx


# -----------------------------
# CSS (상단 “꽉 찬” 배너 + 달력 버튼)
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 0.8rem; padding-bottom: 1.2rem; }

/* 상단 배너: 좌-중-우 꽉 채우기 */
.hero{
  border-radius: 20px;
  padding: 14px 16px;
  background: linear-gradient(135deg, rgba(255,245,232,0.85), rgba(255,255,255,0.90));
  border: 1px solid rgba(0,0,0,0.06);
  box-shadow: 0 10px 26px rgba(0,0,0,0.06);
  margin-bottom: 12px;
}
.hero-grid{
  display: grid;
  grid-template-columns: 1.1fr 1.3fr 1.1fr;
  gap: 14px;
  align-items: center;
}
.brand{
  display:flex;
  align-items:center;
  gap: 12px;
}
.brand img{
  height: 44px;
  width: auto;
  object-fit: contain;
}
.brand-title{
  margin: 0;
  font-size: 26px;
  font-weight: 900;
  line-height: 1.05;
  color: #3f2f22;
}
.brand-sub{
  margin: 4px 0 0 0;
  font-size: 12px;
  opacity: 0.75;
}
.center-img{
  width: 100%;
  height: 92px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.06);
  background: rgba(255,255,255,0.7);
  display:flex;
  align-items:center;
  justify-content:center;
}
.center-img img{
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.gongyang{
  border-radius: 16px;
  padding: 12px 12px;
  background: rgba(255,255,255,0.75);
  border: 1px solid rgba(0,0,0,0.06);
}
.gongyang-head{
  font-size: 12px;
  font-weight: 900;
  opacity: 0.7;
  margin-bottom: 6px;
}
.gongyang-text{
  font-size: 15px;
  font-weight: 800;
  line-height: 1.45;
  white-space: pre-line;
  color: #4a3627;
}

/* 달력 */
.cal-head{
  text-align:center;
  font-weight: 900;
  color: #b07a42;
  padding: 4px 0 10px 0;
}
.stButton>button{
  border-radius: 14px !important;
  border: 1px solid rgba(0,0,0,0.10) !important;
  min-height: 116px !important;
  background: rgba(255,255,255,0.92) !important;
  text-align: left !important;
  white-space: pre-line !important;
}
.stButton>button:hover{
  border-color: rgba(176,122,66,0.85) !important;
  box-shadow: 0 6px 18px rgba(176,122,66,0.15) !important;
  transform: translateY(-1px);
}
.today-highlight{
  outline: 3px solid rgba(176,122,66,0.55);
  outline-offset: -3px;
}

/* 탭 여백 */
.stTabs [data-baseweb="tab-list"]{ gap: 6px; }
.small-muted{ font-size: 12px; opacity: 0.72; }
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# 상단 배너 렌더링
# -----------------------------
moms_b64 = _img_b64(MOMS_LOGO_PATH)
kapma_b64 = _img_b64(KAPMA_LOGO_PATH)
dosirak_b64 = _img_b64(DOSIRAK_PATH)

brand_logo_html = f"<img src='data:image/png;base64,{moms_b64}'/>" if moms_b64 else "<div style='font-weight:900;'>MOMS</div>"
kapma_logo_html = f"<img src='data:image/png;base64,{kapma_b64}' style='height:34px;'/>" if kapma_b64 else ""

center_img_html = (
    f"<img src='data:image/png;base64,{dosirak_b64}'/>"
    if dosirak_b64
    else "<div style='font-weight:900;opacity:0.7;'>assets/dosirak.png</div>"
)

st.markdown(
    f"""
<div class="hero">
  <div class="hero-grid">
    <div class="brand">
      {brand_logo_html}
      <div>
        <p class="brand-title">식단 관리 시스템</p>
        <p class="brand-sub">월~금만 표시 · 날짜 클릭 → 바로 입력 {kapma_logo_html}</p>
      </div>
    </div>

    <div class="center-img">
      {center_img_html}
    </div>

    <div class="gongyang">
      <div class="gongyang-head">供養偈 (공양게)</div>
      <div class="gongyang-text">{GONGYANG_TEXT}</div>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 포스터/출력용 HTML 생성
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    """
    ✅ 요구사항: "두 로고 사이 가운데에 그릇그림 + 공양게"
    - 좌: MOMS 로고
    - 중: 공양그릇 + 공양게
    - 우: KAPMA 로고(있으면)
    - 아래: 월~금 달력
    """
    title = _month_title(year, month)

    moms = _img_b64(MOMS_LOGO_PATH)
    kapma = _img_b64(KAPMA_LOGO_PATH)
    bowl = _img_b64(BOWL_PATH)

    moms_img = f"<img class='logo' src='data:image/png;base64,{moms}' />" if moms else "<div class='logo ph'>MOMS</div>"
    kapma_img = f"<img class='logo' src='data:image/png;base64,{kapma}' />" if kapma else "<div class='logo ph'>협회</div>"
    bowl_img = f"<img class='bowl' src='data:image/png;base64,{bowl}' />" if bowl else "<div class='bowl ph'>🥣</div>"

    weeks = _month_weeks_mon_fri(year, month)

    def cell_html(d: date) -> str:
        if d.month != month:
            return ""
        base = _get_value(st.session_state.base_df, d, "base_menu")
        change = _get_value(st.session_state.change_df, d, "change_menu")
        no_del = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

        lines = [f"<div class='daynum'>{d.day}</div>"]
        if no_del:
            lines.append("<div class='tag nd'>🚫 배달불요</div>")
        if change:
            lines.append(f"<div class='tag ch'>🔁 {change}</div>")
        if base:
            lines.append(f"<div class='tag bs'>🍚 {base}</div>")
        return "".join(lines)

    body_rows = ""
    for w in weeks:
        tds = "".join([f"<td>{cell_html(d)}</td>" for d in w])
        body_rows += f"<tr>{tds}</tr>"

    html = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>{title} 포스터</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif; }}
  .top {{
    display:grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    align-items:center;
    gap: 10px;
    margin-bottom: 8px;
  }}
  .logo {{ height: 46px; object-fit: contain; }}
  .mid {{
    border: 1px solid rgba(0,0,0,0.10);
    border-radius: 14px;
    background: #fdfaf5;
    padding: 8px 10px;
    display:flex;
    align-items:center;
    gap: 10px;
  }}
  .bowl {{ height: 52px; object-fit: contain; }}
  .gong {{
    white-space: pre-line;
    font-size: 14px;
    font-weight: 800;
    line-height: 1.45;
    color: #4a3627;
  }}
  .title {{
    text-align:center;
    font-size: 20px;
    font-weight: 900;
    margin: 6px 0 2px 0;
    color:#3f2f22;
  }}
  .sub {{
    text-align:center;
    font-size: 12px;
    opacity: 0.75;
    margin: 0 0 8px 0;
  }}

  table {{ width:100%; border-collapse: collapse; table-layout: fixed; }}
  th, td {{ border: 1px solid rgba(0,0,0,0.10); vertical-align: top; padding: 6px; }}
  th {{
    background: rgba(176,122,66,0.14);
    color:#6b4e2e;
    font-weight: 900;
    text-align:center;
    padding: 7px 0;
    font-size: 13px;
  }}
  td {{ height: 92px; }} /* ✅ A4 1페이지 고정 핵심 */
  .daynum {{ font-weight: 900; margin-bottom: 4px; }}
  .tag {{ font-size: 12px; margin: 2px 0; line-height: 1.25; }}
  .nd {{ color:#9b1c1c; font-weight: 900; }}
  .ch {{ font-weight: 900; }}
  .bs {{ opacity: 0.88; }}

  .ph {{
    height: 46px;
    display:flex; align-items:center; justify-content:center;
    border: 1px dashed rgba(0,0,0,0.25);
    border-radius: 12px; font-weight: 900;
  }}
</style>
</head>
<body>
  <div class="top">
    <div style="display:flex;justify-content:flex-start;">{moms_img}</div>
    <div class="mid">
      {bowl_img}
      <div class="gong">{GONGYANG_TEXT}</div>
    </div>
    <div style="display:flex;justify-content:flex-end;">{kapma_img}</div>
  </div>

  <div class="title">{title} 식단(배달) 변경</div>
  <div class="sub">월~금 / 토·일 제외</div>

  <table>
    <thead>
      <tr><th>월</th><th>화</th><th>수</th><th>목</th><th>금</th></tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>
</body>
</html>
"""
    return html


def build_vendor_text(year: int, month: int) -> str:
    weeks = _month_weeks_mon_fri(year, month)
    items_no, items_ch = [], []

    for w in weeks:
        for d in w:
            if d.month != month:
                continue
            no_del = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"
            change = _get_value(st.session_state.change_df, d, "change_menu")
            if no_del:
                items_no.append(d)
            if change:
                items_ch.append((d, change))

    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")

    if items_no:
        lines.append("🚫【배달불요】")
        for d in items_no:
            lines.append(f"▶ {d.strftime('%m/%d')}({WEEKDAYS_KO[d.weekday()]}) : 배달불요")
        lines.append("")

    if items_ch:
        lines.append("🔁【변경메뉴】")
        for d, menu in items_ch:
            lines.append(f"▶ {d.strftime('%m/%d')}({WEEKDAYS_KO[d.weekday()]}) : {menu}")

    if not items_no and not items_ch:
        lines.append("금월 변경/배달불요 내역이 없습니다.")

    return "\n".join(lines)


# -----------------------------
# 탭 구성 (포스터/출력 복구)
# -----------------------------
tabs = st.tabs(["① 달력 입력", "② 포스터(스크린샷/인쇄)", "③ 업체 전달용 출력(다운로드)"])

curr = date.today()


# -----------------------------
# ① 달력 입력
# -----------------------------
with tabs[0]:
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        sel_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1)
        sel_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1)

    with c2:
        st.caption("✅ 1달만 표시 / ✅ 월~금만 / ✅ 요일 표시 / 날짜 클릭 → 입력창")

    # 요일 헤더
    hcols = st.columns(5)
    for i, day_name in enumerate(WEEKDAYS_KO):
        hcols[i].markdown(f"<div class='cal-head'>{day_name}</div>", unsafe_allow_html=True)

    weeks = _month_weeks_mon_fri(sel_year, sel_month)

    def open_editor(target_date: date):
        base = _get_value(st.session_state.base_df, target_date, "base_menu")
        change = _get_value(st.session_state.change_df, target_date, "change_menu")
        is_no = _get_value(st.session_state.delivery_df, target_date, "delivery") == "Y"

        @st.dialog(f"{target_date.strftime('%m월 %d일')} ({WEEKDAYS_KO[target_date.weekday()]}) 입력")
        def _dlg():
            idx_list = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()

            b_sel = st.selectbox("기본 메뉴(인덱스)", idx_list, key=f"bsel_{target_date}")
            b_txt = st.text_input(
                "기본 메뉴(직접 입력)",
                value=base if b_sel == "(직접입력)" else b_sel,
                key=f"btxt_{target_date}",
            )

            st.divider()

            c_sel = st.selectbox("변경 메뉴(인덱스)", idx_list, key=f"csel_{target_date}")
            c_txt = st.text_input(
                "변경 메뉴(직접 입력)",
                value=change if c_sel == "(직접입력)" else c_sel,
                key=f"ctxt_{target_date}",
            )

            st.divider()

            no_del = st.toggle("🚫 배달불요", value=is_no, key=f"nd_{target_date}")

            st.divider()

            a, b = st.columns([1, 1])
            with a:
                if st.button("저장", type="primary", use_container_width=True, key=f"save_{target_date}"):
                    st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_txt)
                    st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_txt)
                    st.session_state.delivery_df = _set_value(
                        st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N"
                    )

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                    # 인덱스 축적(가나다)
                    new_items = [_normalize_text(b_txt), _normalize_text(c_txt)]
                    new_items = [x for x in new_items if x]
                    if new_items:
                        idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame({"name": new_items})], ignore_index=True)
                        idx["name"] = idx["name"].map(_normalize_text)
                        idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                        st.session_state.menu_index_df = idx
                        _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)

                    st.rerun()

            with b:
                if st.button("해당일 비우기", use_container_width=True, key=f"clr_{target_date}"):
                    k = _key(target_date)
                    st.session_state.base_df = st.session_state.base_df[st.session_state.base_df["date"] != k].reset_index(drop=True)
                    st.session_state.change_df = st.session_state.change_df[st.session_state.change_df["date"] != k].reset_index(drop=True)
                    st.session_state.delivery_df = st.session_state.delivery_df[st.session_state.delivery_df["date"] != k].reset_index(drop=True)

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)
                    st.rerun()

        _dlg()

    # 달력 출력
    for week in weeks:
        cols = st.columns(5)
        for i, d in enumerate(week):
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue

                base = _get_value(st.session_state.base_df, d, "base_menu")
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

                label = f"**{d.day}**\n"
                if is_no:
                    label += "🚫 배달불요\n"
                if change:
                    label += f"🔁 {_safe_short(change, 16)}\n"
                elif base:
                    label += f"🍚 {_safe_short(base, 16)}\n"

                wrap_start = "<div class='today-highlight'>" if d == curr else "<div>"
                st.markdown(wrap_start, unsafe_allow_html=True)
                clicked = st.button(label, key=f"btn_{d}", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

                if clicked and _is_weekday(d):
                    open_editor(d)

    st.divider()
    st.markdown("### 메뉴 인덱스(가나다 순)")
    ix1, ix2 = st.columns([1.2, 1.0])
    with ix1:
        add_item = st.text_input("메뉴 추가", placeholder="예) 소고기무국")
        if st.button("➕ 인덱스 추가"):
            v = _normalize_text(add_item)
            if v:
                idx = pd.concat([st.session_state.menu_index_df, pd.DataFrame([{"name": v}])], ignore_index=True)
                idx["name"] = idx["name"].map(_normalize_text)
                idx = idx[idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                st.session_state.menu_index_df = idx
                _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)
                st.rerun()
            else:
                st.warning("메뉴명을 입력해 주세요.")
    with ix2:
        st.dataframe(st.session_state.menu_index_df, use_container_width=True, height=260)


# -----------------------------
# ② 포스터(스크린샷/인쇄)  ✅ 복구
# -----------------------------
with tabs[1]:
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        p_year = st.selectbox("연도(포스터)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="p_year")
        p_month = st.selectbox("월(포스터)", list(range(1, 13)), index=curr.month - 1, key="p_month")
    with c2:
        st.caption("A4 1페이지 인쇄용 HTML입니다. (브라우저 Ctrl+P → '한 페이지에 맞춤' 권장)")

    poster_html = build_poster_html(p_year, p_month)

    st.markdown("#### 포스터 미리보기")
    components.html(poster_html, height=860, scrolling=True)

    st.download_button(
        "⬇️ 포스터 HTML 다운로드(A4 1페이지 인쇄용)",
        data=poster_html.encode("utf-8"),
        file_name=f"포스터_{p_year}-{p_month:02d}.html",
        mime="text/html",
        use_container_width=True,
    )


# -----------------------------
# ③ 업체 전달용 출력(다운로드) ✅ 복구
# -----------------------------
with tabs[2]:
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        o_year = st.selectbox("연도(출력)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="o_year")
        o_month = st.selectbox("월(출력)", list(range(1, 13)), index=curr.month - 1, key="o_month")
    with c2:
        st.caption("월~금 기준으로 ‘배달불요/변경메뉴’만 추려서 문자로 보내기 좋게 출력합니다.")

    txt = build_vendor_text(o_year, o_month)
    st.text_area("업체 전달용 문구(복사해서 문자로 보내기)", value=txt, height=360)

    st.download_button(
        "⬇️ 텍스트 파일 다운로드",
        data=txt.encode("utf-8"),
        file_name=f"업체전달_{o_year}-{o_month:02d}.txt",
        mime="text/plain",
        use_container_width=True,
    )
