# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import re
import unicodedata
import io

import pandas as pd
import streamlit as st

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

# 경로 설정
BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
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
# 유틸리티
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
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols].fillna("")
    except Exception:
        return pd.DataFrame(columns=cols)


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
    return d.weekday() <= 4  # 월(0)~금(4)


def _img_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _month_weeks_mon_fri(year: int, month: int) -> list[list[date]]:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks = cal.monthdatescalendar(year, month)
    return [w[:5] for w in weeks]  # 월~금만


def _month_title(year: int, month: int) -> str:
    return f"{year}년 {month:02d}월"


def _safe_short(s: str, n: int = 12) -> str:
    s = _normalize_text(s)
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "…"


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
# 스타일(CSS)  (부회장님 코드 기반 + A4용)
# -----------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');

.block-container { padding-top: 1.2rem; padding-bottom: 1.5rem; }

.main-header{
  background: white; border-radius: 20px; padding: 22px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.05); border: 1px solid #f0f0f0;
  margin-bottom: 14px;
}

.gongyang-card{
  background: #fdfaf5; border-left: 5px solid #d4a373;
  padding: 18px; border-radius: 0 15px 15px 0;
  font-family: 'Noto Serif KR', serif;
}

.cal-head{
  text-align:center; font-weight:800; color:#d4a373;
  padding: 4px 0 10px 0;
}

.stButton>button{
  border-radius: 12px; border: 1px solid #eee;
  min-height: 120px;
  transition: all 0.25s; background: white;
  white-space: pre-line !important;
  text-align: left !important;
}
.stButton>button:hover{
  border-color: #d4a373;
  box-shadow: 0 5px 15px rgba(212, 163, 115, 0.20);
  transform: translateY(-2px);
}
.today-highlight{
  border: 2px solid #d4a373 !important;
  background: #fffcf9 !important;
}

.badge{
  display:inline-block;
  font-size:12px; font-weight:800;
  padding:2px 8px; border-radius:999px;
  margin-right:6px;
  background: rgba(212,163,115,0.18);
}

.small-muted{ font-size:12px; opacity:0.70; }
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# 상단 레이아웃 (로고 & 이미지 & 공양게)
# -----------------------------
def render_header():
    header_col1, header_col2 = st.columns([1.25, 1], gap="large")

    with header_col1:
        st.markdown('<div class="main-header">', unsafe_allow_html=True)

        v_col1, v_col2 = st.columns([0.7, 2.3], vertical_alignment="center")
        with v_col1:
            if MOMS_LOGO_PATH.exists():
                st.image(str(MOMS_LOGO_PATH), use_container_width=True)
            else:
                st.subheader("🍱 맘스락")

        with v_col2:
            st.markdown("<h2 style='margin:0; color:#443322;'>식단 관리 시스템</h2>", unsafe_allow_html=True)
            st.caption("평일(월~금) 중심 | 날짜 클릭 → 바로 입력")

        if DOSIRAK_PATH.exists():
            st.image(str(DOSIRAK_PATH), use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with header_col2:
        st.markdown(
            f"""
<div class="gongyang-card">
  <div style="font-size:0.9rem; color:#888; margin-bottom:10px;">供養偈 (공양게)</div>
  <div style="font-size:1.22rem; font-weight:700; color:#554433; line-height:1.6; white-space:pre-line;">
  {GONGYANG_TEXT}
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

render_header()
st.divider()


# -----------------------------
# 포스터/출력용 HTML 생성
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    title = _month_title(year, month)

    moms_b64 = _img_b64(MOMS_LOGO_PATH)
    bowl_b64 = _img_b64(BOWL_PATH)

    weeks = _month_weeks_mon_fri(year, month)

    # 표 셀(월~금) 내용 구성
    def cell_text(d: date) -> str:
        if d.month != month:
            return ""
        base = _get_value(st.session_state.base_df, d, "base_menu")
        change = _get_value(st.session_state.change_df, d, "change_menu")
        no_deliv = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

        lines = [f"<div class='daynum'>{d.day}</div>"]
        if no_deliv:
            lines.append("<div class='tag nd'>🚫 배달불요</div>")
        if change:
            lines.append(f"<div class='tag ch'>🔁 {change}</div>")
        if base:
            lines.append(f"<div class='tag bs'>🍚 {base}</div>")
        return "".join(lines)

    rows_html = ""
    for w in weeks:
        tds = ""
        for d in w:
            tds += f"<td>{cell_text(d)}</td>"
        rows_html += f"<tr>{tds}</tr>"

    moms_img = f"<img class='logo' src='data:image/png;base64,{moms_b64}' />" if moms_b64 else "<div class='logo ph'>MOMS</div>"
    bowl_img = f"<img class='bowl' src='data:image/png;base64,{bowl_b64}' />" if bowl_b64 else "<div class='bowl ph'>🥣</div>"

    html = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title} 포스터</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", Arial, sans-serif; }}
  .wrap {{ width: 100%; }}
  .top {{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom: 8px;
  }}
  .logo {{ height: 52px; object-fit: contain; }}
  .bowl {{ height: 56px; object-fit: contain; }}
  .title {{
    text-align:center;
    font-size: 22px;
    font-weight: 900;
    margin: 0;
    line-height: 1.15;
    flex: 1;
  }}
  .subtitle {{
    text-align:center;
    font-size: 12px;
    opacity: 0.75;
    margin-top: 2px;
  }}
  .mid {{
    display:flex; gap: 10px; align-items:stretch;
    margin: 8px 0 10px 0;
  }}
  .gongyang {{
    flex: 1;
    border-left: 5px solid #d4a373;
    background: #fdfaf5;
    border-radius: 10px;
    padding: 10px 12px;
    white-space: pre-line;
    font-size: 15px;
    line-height: 1.45;
    font-weight: 700;
    color: #554433;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid rgba(0,0,0,0.10);
    vertical-align: top;
    padding: 6px 6px;
  }}
  th {{
    text-align:center;
    background: rgba(212,163,115,0.13);
    color: #6b4e2e;
    font-weight: 900;
    padding: 7px 0;
    font-size: 13px;
  }}
  td {{
    height: 90px;  /* A4 1페이지 맞춤 핵심 */
  }}
  .daynum {{ font-weight: 900; margin-bottom: 4px; }}
  .tag {{ font-size: 12px; margin: 2px 0; line-height: 1.25; }}
  .nd {{ color: #9b1c1c; font-weight: 900; }}
  .ch {{ font-weight: 800; }}
  .bs {{ opacity: 0.90; }}

  .ph {{
    width: 70px; height: 52px; display:flex; align-items:center; justify-content:center;
    border: 1px dashed rgba(0,0,0,0.2); border-radius: 10px; font-weight: 900;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    {moms_img}
    <div style="flex:1;">
      <div class="title">{title} 식단(배달) 변경</div>
      <div class="subtitle">월~금 / 토·일 제외</div>
    </div>
    {bowl_img}
  </div>

  <div class="mid">
    <div class="gongyang">{GONGYANG_TEXT}</div>
  </div>

  <table>
    <thead>
      <tr>
        <th>월</th><th>화</th><th>수</th><th>목</th><th>금</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>
</body>
</html>
"""
    return html


def build_vendor_text(year: int, month: int) -> str:
    # 월~금만, 변경/배달불요만 뽑아 “문자 보내기” 최적화
    weeks = _month_weeks_mon_fri(year, month)
    items_no = []
    items_ch = []

    for w in weeks:
        for d in w:
            if d.month != month:
                continue
            no_deliv = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"
            change = _get_value(st.session_state.change_df, d, "change_menu")
            if no_deliv:
                items_no.append((d, "배달불요"))
            if change:
                items_ch.append((d, change))

    title = _month_title(year, month)
    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")

    if items_no:
        lines.append("🚫【배달불요】")
        for d, _ in items_no:
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
# 메인 탭(달력/포스터/업체전달)
# -----------------------------
tabs = st.tabs(["① 달력 입력", "② 포스터(스크린샷/출력)", "③ 업체 전달용 출력"])

curr = date.today()

# -----------------------------
# ① 달력 입력
# -----------------------------
with tabs[0]:
    c1, c2 = st.columns([1, 3])
    with c1:
        sel_year = st.selectbox("연도", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1)
        sel_month = st.selectbox("월", list(range(1, 13)), index=curr.month - 1)

    with c2:
        st.markdown(
            "<span class='badge'>✅ 1달만</span><span class='badge'>✅ 월~금만</span><span class='badge'>✅ 요일 표시</span>",
            unsafe_allow_html=True,
        )

    # 요일 헤더
    hcols = st.columns(5)
    for i, day_name in enumerate(WEEKDAYS_KO):
        hcols[i].markdown(f"<div class='cal-head'>{day_name}</div>", unsafe_allow_html=True)

    weeks = _month_weeks_mon_fri(sel_year, sel_month)

    def open_editor(target_date: date):
        if not _is_weekday(target_date):
            return

        base = _get_value(st.session_state.base_df, target_date, "base_menu")
        change = _get_value(st.session_state.change_df, target_date, "change_menu")
        is_no_deliv = _get_value(st.session_state.delivery_df, target_date, "delivery") == "Y"

        @st.dialog(f"{target_date.strftime('%m월 %d일')} ({WEEKDAYS_KO[target_date.weekday()]}) 식단 편집")
        def edit_dialog():
            idx_list = ["(직접입력)"] + st.session_state.menu_index_df["name"].tolist()

            b_val = st.selectbox("기본 메뉴 선택", idx_list, key=f"sel_b_{target_date}")
            b_text = st.text_input(
                "기본 메뉴(직접 입력)",
                value=base if b_val == "(직접입력)" else b_val,
                key=f"txt_b_{target_date}",
            )

            st.divider()

            c_val = st.selectbox("변경 메뉴 선택", idx_list, key=f"sel_c_{target_date}")
            c_text = st.text_input(
                "변경 메뉴(직접 입력)",
                value=change if c_val == "(직접입력)" else c_val,
                key=f"txt_c_{target_date}",
            )

            st.divider()

            no_del = st.toggle("🚫 배달 불요", value=is_no_deliv, key=f"tog_nd_{target_date}")

            st.divider()

            colx, coly = st.columns([1, 1])
            with colx:
                if st.button("저장", use_container_width=True, type="primary", key=f"save_{target_date}"):
                    st.session_state.base_df = _set_value(st.session_state.base_df, target_date, "base_menu", b_text)
                    st.session_state.change_df = _set_value(st.session_state.change_df, target_date, "change_menu", c_text)
                    st.session_state.delivery_df = _set_value(
                        st.session_state.delivery_df, target_date, "delivery", "Y" if no_del else "N"
                    )

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)

                    # 인덱스 업데이트(가나다 정렬)
                    new_items = [_normalize_text(b_text), _normalize_text(c_text)]
                    new_items = [x for x in new_items if x]
                    if new_items:
                        new_idx = pd.concat(
                            [st.session_state.menu_index_df, pd.DataFrame({"name": new_items})],
                            ignore_index=True,
                        )
                        new_idx["name"] = new_idx["name"].map(_normalize_text)
                        new_idx = new_idx[new_idx["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
                        st.session_state.menu_index_df = new_idx
                        _write_csv(st.session_state.menu_index_df, MENU_INDEX_PATH)

                    st.rerun()

            with coly:
                if st.button("해당일 비우기", use_container_width=True, key=f"clear_{target_date}"):
                    k = _key(target_date)
                    st.session_state.base_df = st.session_state.base_df[st.session_state.base_df["date"] != k].reset_index(drop=True)
                    st.session_state.change_df = st.session_state.change_df[st.session_state.change_df["date"] != k].reset_index(drop=True)
                    st.session_state.delivery_df = st.session_state.delivery_df[st.session_state.delivery_df["date"] != k].reset_index(drop=True)

                    _write_csv(st.session_state.base_df, BASE_MENU_PATH)
                    _write_csv(st.session_state.change_df, CHANGE_MENU_PATH)
                    _write_csv(st.session_state.delivery_df, DELIVERY_PATH)
                    st.rerun()

        edit_dialog()

    # 달력 그리드
    for week in weeks:
        cols = st.columns(5)
        for i in range(5):
            d = week[i]
            with cols[i]:
                if d.month != sel_month:
                    st.write("")
                    continue

                base = _get_value(st.session_state.base_df, d, "base_menu")
                change = _get_value(st.session_state.change_df, d, "change_menu")
                is_no_deliv = _get_value(st.session_state.delivery_df, d, "delivery") == "Y"

                cls = "today-highlight" if d == curr else ""
                label = f"**{d.day}**\n"
                if is_no_deliv:
                    label += "🚫 배달불요\n"
                if change:
                    label += f"🔁 {_safe_short(change, 14)}\n"
                elif base:
                    label += f"🍚 {_safe_short(base, 14)}\n"

                if st.button(label, key=f"btn_{d}", use_container_width=True):
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
# ② 포스터(스크린샷/출력)
# -----------------------------
with tabs[1]:
    c1, c2 = st.columns([1, 3])
    with c1:
        p_year = st.selectbox("연도(포스터)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="p_year")
        p_month = st.selectbox("월(포스터)", list(range(1, 13)), index=curr.month - 1, key="p_month")
    with c2:
        st.caption("포스터는 A4 1페이지 인쇄를 목표로 HTML로 구성합니다. (브라우저 인쇄 Ctrl+P → ‘한 페이지에 맞춤’)")

    poster_html = build_poster_html(p_year, p_month)

    st.markdown("#### 포스터 미리보기")
    st.components.v1.html(poster_html, height=850, scrolling=True)

    st.download_button(
        "⬇️ 포스터 HTML 다운로드(A4 1페이지 인쇄용)",
        data=poster_html.encode("utf-8"),
        file_name=f"포스터_{p_year}-{p_month:02d}.html",
        mime="text/html",
        use_container_width=True,
    )


# -----------------------------
# ③ 업체 전달용 출력(문자/복사)
# -----------------------------
with tabs[2]:
    c1, c2 = st.columns([1, 3])
    with c1:
        o_year = st.selectbox("연도(출력)", [curr.year - 1, curr.year, curr.year + 1, curr.year + 2], index=1, key="o_year")
        o_month = st.selectbox("월(출력)", list(range(1, 13)), index=curr.month - 1, key="o_month")
    with c2:
        st.caption("월~금 기준으로 ‘배달불요/변경메뉴’만 추려서 문자로 보내기 좋게 출력합니다.")

    txt = build_vendor_text(o_year, o_month)

    st.text_area("업체 전달용 문구(복사해서 문자로 보내기)", value=txt, height=350)

    st.download_button(
        "⬇️ 텍스트 파일 다운로드",
        data=txt.encode("utf-8"),
        file_name=f"업체전달_{o_year}-{o_month:02d}.txt",
        mime="text/plain",
        use_container_width=True,
    )
