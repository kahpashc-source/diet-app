# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import html
import re

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
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)

# 포스터 하단 전화번호
ASSOC_PHONE = "010-7101-5871"

# (선택) 로고/이미지 파일 (repo에 있으면 자동 반영)
ASSET_CANDIDATES = {
    "moms": ["moms.png", "moms_logo.png", "momsrak.png", "momsrak_logo.png", "MOMS.png", "MOMS_logo.png"],
    "kapma": ["kapma.png", "kapma_logo.png", "dongyak.png", "dongyak_logo.png", "association_logo.png"],
    "bowl": ["gongyang_bowl.png", "bowl.png", "offering_bowl.png"],
}

GONGYANG_TITLE = "공양게"
GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


# -----------------------------
# 유틸
# -----------------------------
def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _weekday_kr(d: date) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]


def _month_title(year: int, month: int) -> str:
    return f"동약협회 {year}년 {month}월 식단변경 내역"


def _safe_read_csv(path: Path, expected_cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=expected_cols)

    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")

    for c in expected_cols:
        if c not in df.columns:
            df[c] = ""

    df = df[expected_cols].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["date"] = df["date"].dt.date
    return df


def _save_csv_atomic(df: pd.DataFrame, path: Path, cols: list[str]) -> None:
    df2 = df.copy()
    df2 = df2[cols].copy()
    tmp = path.with_suffix(".tmp")
    df2.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def _find_asset_base64(candidates: list[str]) -> str | None:
    for name in candidates:
        p = APP_DIR / name
        if p.exists() and p.is_file():
            b = p.read_bytes()
            return base64.b64encode(b).decode("utf-8")
    return None


def _upsert_value(path: Path, value_col: str, d: date, value: str) -> None:
    # 파일 로드
    if value_col == "base_menu":
        df = _safe_read_csv(path, ["date", "base_menu"])
    elif value_col == "change_menu":
        df = _safe_read_csv(path, ["date", "change_menu"])
    else:
        df = _safe_read_csv(path, ["date", "delivery"])

    # upsert
    if df.empty:
        df = pd.DataFrame({"date": [d], value_col: [value]})
    else:
        mask = df["date"] == d
        if mask.any():
            df.loc[mask, value_col] = value
        else:
            df = pd.concat([df, pd.DataFrame({"date": [d], value_col: [value]})], ignore_index=True)

    # date 정렬
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    # 저장
    _save_csv_atomic(df, path, ["date", value_col])


def _load_merged() -> pd.DataFrame:
    base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"]).rename(columns={"base_menu": "base"})
    chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"]).rename(columns={"change_menu": "change"})
    deliv_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"]).rename(columns={"delivery": "delivery"})

    df = pd.merge(base_df, chg_df, on="date", how="outer").merge(deliv_df, on="date", how="outer")
    if df.empty:
        df = pd.DataFrame(columns=["date", "base", "change", "delivery"])

    df["base"] = df["base"].fillna("")
    df["change"] = df["change"].fillna("")
    df["delivery"] = df["delivery"].fillna("Y").str.upper().replace({"": "Y"})
    df["delivery"] = df["delivery"].where(df["delivery"].isin(["Y", "N"]), "Y")
    return df


# -----------------------------
# 스타일
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.poster-wrap { max-width: 980px; margin: 0 auto; }
hr { margin: 1.2rem 0 1rem 0; }
.small { font-size: 12px; opacity: .75; }
.card {
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 14px;
  padding: 14px;
  background: #fff;
}
.cal-grid {
  display:grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
.daybtn > button{
  width: 100% !important;
  text-align: left !important;
  border-radius: 14px !important;
  padding: 10px 10px !important;
  min-height: 92px !important;
  white-space: pre-line !important;
  border: 1px solid rgba(0,0,0,0.12) !important;
  background: rgba(255,255,255,0.95) !important;
}
.daybtn.off > button{
  background: rgba(255, 80, 80, 0.12) !important;
  border-color: rgba(255, 80, 80, 0.22) !important;
}
.daybtn.chg > button{
  background: rgba(255, 210, 80, 0.18) !important;
  border-color: rgba(255, 170, 0, 0.26) !important;
}
.badge { font-size: 12px; font-weight: 800; }
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 상단: 월 선택
# -----------------------------
today = date.today()
years = list(range(today.year - 1, today.year + 3))

c0, c1, c2 = st.columns([1, 1, 2])
with c0:
    sel_year = st.selectbox("년도", years, index=years.index(today.year) if today.year in years else 0)
with c1:
    sel_month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with c2:
    st.caption("입력(달력 클릭) → 포스터 미리보기 → PNG/HTML 다운로드")

title_for_file = _month_title(int(sel_year), int(sel_month))

# 데이터 로드
df = _load_merged()


# -----------------------------
# 입력용 달력 (월~금) + 날짜 클릭하면 입력창
# -----------------------------
def _get_day_state(d: date) -> tuple[str, str, str]:
    row = df[df["date"] == d]
    if row.empty:
        return "", "", "Y"  # 기본: 배달(Y)
    base = _norm(row.iloc[0]["base"])
    chg = _norm(row.iloc[0]["change"])
    delivery = _norm(row.iloc[0]["delivery"]) or "Y"
    delivery = delivery if delivery in ("Y", "N") else "Y"
    return base, chg, delivery


def _render_day_label(d: date, base: str, chg: str, delivery: str) -> tuple[str, str]:
    wd = _weekday_kr(d)
    top = f"{d.day}({wd})"
    lines = [top]

    if delivery == "N":
        lines.append("🚫 배달불요")
    elif chg:
        # 기본이 있으면 → 표시
        if base:
            lines.append(f"🔁 {base} → {chg}")
        else:
            lines.append(f"🔁 {chg}")
    elif base:
        lines.append(base)

    css_class = "daybtn"
    if delivery == "N":
        css_class += " off"
    elif chg:
        css_class += " chg"
    return "\n".join(lines), css_class


@st.dialog("날짜 입력", width="large")
def edit_date_dialog(d: date):
    base, chg, delivery = _get_day_state(d)

    st.markdown(f"### {d.isoformat()} ({_weekday_kr(d)})")
    st.caption("저장하면 창이 닫히고, 달력/포스터에 바로 반영됩니다.")

    base_in = st.text_input("기본메뉴", value=base, placeholder="예: 소고기무국")
    chg_in = st.text_input("변경메뉴(없으면 비워두기)", value=chg, placeholder="예: 제육볶음")
    delivery_ok = st.checkbox("배달함", value=(delivery == "Y"))
    # 내부 저장은 Y/N
    delivery_val = "Y" if delivery_ok else "N"

    cA, cB, cC = st.columns([1, 1, 2])
    with cA:
        if st.button("💾 저장", use_container_width=True, type="primary"):
            _upsert_value(BASE_MENU_PATH, "base_menu", d, _norm(base_in))
            _upsert_value(CHANGE_MENU_PATH, "change_menu", d, _norm(chg_in))
            _upsert_value(DELIVERY_PATH, "delivery", d, delivery_val)
            st.rerun()
    with cB:
        if st.button("닫기", use_container_width=True):
            st.rerun()
    with cC:
        st.caption("※ 배달불요는 ‘배달함’ 체크를 해제하면 됩니다.")


def input_calendar(year: int, month: int):
    st.subheader("1) 입력(월~금 달력) — 날짜를 클릭해서 입력/수정")
    st.caption("토/일은 표시하지 않습니다.")

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    weeks = cal.monthdatescalendar(year, month)

    # 요일 헤더
    hcols = st.columns(5)
    for i, name in enumerate(["월", "화", "수", "목", "금"]):
        with hcols[i]:
            st.markdown(f"<div class='small'><b>{name}</b></div>", unsafe_allow_html=True)

    st.markdown("<div class='cal-grid'>", unsafe_allow_html=True)

    # 각 주별로 월~금만 5칸 고정으로 출력 (다른 달 날짜는 빈칸)
    for w in weeks:
        mf = [d for d in w if d.weekday() <= 4]  # Mon-Fri (항상 5개)
        for d in mf:
            if d.month != month:
                # 빈칸
                st.markdown("<div class='card' style='opacity:.25; min-height:92px;'></div>", unsafe_allow_html=True)
                continue

            base, chg, delivery = _get_day_state(d)
            label, css_class = _render_day_label(d, base, chg, delivery)

            st.markdown(f"<div class='{css_class}'>", unsafe_allow_html=True)
            if st.button(label, key=f"day_{d.isoformat()}"):
                edit_date_dialog(d)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------
# 포스터 HTML 생성 (월~금 달력)
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    moms_b64 = _find_asset_base64(ASSET_CANDIDATES["moms"])
    kapma_b64 = _find_asset_base64(ASSET_CANDIDATES["kapma"])
    bowl_b64 = _find_asset_base64(ASSET_CANDIDATES["bowl"])

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    mdf = df[(df["date"] >= first_day) & (df["date"] <= last_day)].copy()

    base_map = {r["date"]: _norm(r["base"]) for _, r in mdf.iterrows()}
    chg_map = {r["date"]: _norm(r["change"]) for _, r in mdf.iterrows()}
    del_map = {r["date"]: _norm(r["delivery"]) for _, r in mdf.iterrows()}

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)
    weeks_mf = [[d for d in w if d.weekday() <= 4] for w in weeks]

    def img_tag(b64: str | None, height_px: int) -> str:
        if not b64:
            return ""
        return f"<img src='data:image/png;base64,{b64}' style='height:{height_px}px; width:auto; display:block;'/>"

    moms_img = img_tag(moms_b64, 34)
    kapma_img = img_tag(kapma_b64, 34)
    bowl_img = img_tag(bowl_b64, 52)

    gongyang_html = "<br/>".join(html.escape(line) for line in GONGYANG_TEXT.splitlines())
    month_title = _month_title(year, month)

    def cell_html(d: date) -> str:
        if d.month != month:
            return '<td class="cell empty"></td>'

        b = base_map.get(d, "")
        c = chg_map.get(d, "")
        dy = del_map.get(d, "Y")
        dy = dy if dy in ("Y", "N") else "Y"

        is_delivery_off = (dy == "N")
        has_change = (c != "")

        menu_line = ""
        if has_change:
            if b:
                menu_line = f"{html.escape(b)} <span class='arrow'>→</span> <b>{html.escape(c)}</b>"
            else:
                menu_line = f"<b>{html.escape(c)}</b>"
        else:
            menu_line = html.escape(b) if b else ""

        badge = ""
        cls = "cell"
        if is_delivery_off:
            cls += " off"
            badge = "<span class='badge off'>배달불요</span>"
        elif has_change:
            cls += " chg"
            badge = "<span class='badge chg'>변경</span>"
        else:
            cls += " base"

        wd = _weekday_kr(d)
        return f"""
<td class="{cls}">
  <div class="d-top">
    <div class="d-num">{d.day}<span class="d-wd">({wd})</span></div>
    <div class="d-badge">{badge}</div>
  </div>
  <div class="d-menu">{menu_line}</div>
</td>
"""

    poster = f"""
<div id="poster" class="poster">
  <div class="head">
    <div class="brand left">
      <div class="logo">{moms_img}</div>
      <div class="brand-txt">MOMS</div>
    </div>

    <div class="center">
      <div class="gong-title">{html.escape(GONGYANG_TITLE)}</div>
      <div class="gong-text">{gongyang_html}</div>
      <div class="bowl">{bowl_img}</div>
    </div>

    <div class="brand right">
      <div class="logo">{kapma_img}</div>
      <div class="brand-txt">동약협회</div>
    </div>
  </div>

  <div class="main-title">{html.escape(month_title)}</div>

  <table class="cal">
    <thead>
      <tr>
        <th>월</th><th>화</th><th>수</th><th>목</th><th>금</th>
      </tr>
    </thead>
    <tbody>
      {''.join('<tr>' + ''.join(cell_html(d) for d in week) + '</tr>' for week in weeks_mf)}
    </tbody>
  </table>

  <div class="foot">
    <div class="mini">동약협회 {ASSOC_PHONE}</div>
  </div>
</div>

<style>
  .poster {{
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", system-ui, -apple-system, sans-serif;
    background: #fff;
    padding: 18px;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 14px;
  }}
  .head {{ display:flex; align-items:stretch; gap: 12px; }}
  .brand {{
    width: 190px;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 12px;
    padding: 10px 12px;
    display:flex; flex-direction:column; justify-content:center; align-items:center;
    background: #fff;
  }}
  .brand .brand-txt {{
    margin-top: 6px;
    font-weight: 800;
    letter-spacing: .5px;
    opacity: .9;
  }}
  .center {{
    flex: 1;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 12px;
    padding: 10px 14px;
    display:flex; flex-direction:column; align-items:center; justify-content:center; gap: 6px;
  }}
  .gong-title {{ font-weight: 900; font-size: 18px; letter-spacing: .2px; }}
  .gong-text {{ font-size: 14px; line-height: 1.35; text-align: center; opacity: .92; }}
  .bowl {{ margin-top: 2px; }}
  .main-title {{
    margin-top: 14px; font-size: 20px; font-weight: 900; text-align:center; letter-spacing: .2px;
  }}
  .cal {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 8px;
    margin-top: 10px;
  }}
  .cal thead th {{
    text-align:center;
    font-weight: 900;
    padding: 10px 6px;
    border-radius: 10px;
    background: rgba(0,0,0,0.04);
  }}
  .cell {{
    vertical-align: top;
    border-radius: 12px;
    padding: 10px 10px 12px 10px;
    min-height: 92px;
    border: 1px solid rgba(0,0,0,0.10);
    background: #fff;
  }}
  .cell.empty {{ border: none; background: transparent; }}
  .cell.base {{ background: rgba(0,0,0,0.01); }}
  .cell.chg {{
    background: rgba(255, 210, 80, 0.20);
    border-color: rgba(255, 170, 0, 0.35);
  }}
  .cell.off {{
    background: rgba(255, 80, 80, 0.16);
    border-color: rgba(255, 80, 80, 0.30);
  }}
  .d-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap: 6px; margin-bottom: 6px; }}
  .d-num {{ font-weight: 900; font-size: 16px; }}
  .d-wd {{ font-weight: 700; font-size: 12px; opacity: .75; margin-left: 4px; }}
  .d-badge .badge {{
    display:inline-block; font-size: 12px; padding: 3px 8px; border-radius: 999px; font-weight: 800;
    border: 1px solid rgba(0,0,0,0.10); background: rgba(255,255,255,0.7);
  }}
  .badge.chg {{ border-color: rgba(255, 170, 0, 0.45); }}
  .badge.off {{ border-color: rgba(255, 80, 80, 0.45); }}
  .d-menu {{ font-size: 13px; line-height: 1.3; word-break: keep-all; }}
  .arrow {{ opacity: .75; font-weight: 900; margin: 0 2px; }}
  .foot {{ margin-top: 10px; display:flex; justify-content:flex-end; }}
  .mini {{ font-size: 12px; opacity: .8; font-weight: 800; }}
</style>
"""
    return poster


# -----------------------------
# PNG 캡처/다운로드 + A4 HTML 다운로드
# -----------------------------
def poster_png_downloader(poster_html: str, filename_base: str):
    js = f"""
<div id="capture-wrap" style="background:#fff; padding: 8px;">
  {poster_html}
</div>

<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
  const sendValue = (v) => {{
    const msg = {{
      isStreamlitMessage: true,
      type: "streamlit:setComponentValue",
      value: v
    }};
    window.parent.postMessage(msg, "*");
  }};

  async function makePng() {{
    const node = document.getElementById("capture-wrap");
    const canvas = await html2canvas(node, {{
      backgroundColor: "#FFFFFF",
      scale: 2,
      useCORS: true
    }});
    const dataUrl = canvas.toDataURL("image/png");
    sendValue(dataUrl);
  }}
</script>

<div style="margin-top:10px; display:flex; gap:10px; align-items:center;">
  <button onclick="makePng()"
    style="padding:10px 14px; border-radius:10px; border:1px solid rgba(0,0,0,0.15); background:#fff; cursor:pointer; font-weight:800;">
    🖼️ 포스터 PNG 만들기
  </button>
  <span style="opacity:.65; font-size:12px;">버튼을 누르면 잠시 후 아래에 ‘PNG 다운로드’가 나타납니다.</span>
</div>
"""
    data_url = components.html(js, height=980, scrolling=True, key=f"poster_capture_{filename_base}")

    if isinstance(data_url, str) and data_url.startswith("data:image/png;base64,"):
        b64 = data_url.split(",", 1)[1]
        png_bytes = base64.b64decode(b64)
        st.download_button(
            "⬇️ PNG 다운로드",
            data=png_bytes,
            file_name=f"{filename_base}.png",
            mime="image/png",
            use_container_width=True,
        )
    else:
        st.info("위의 🖼️ 버튼을 눌러 PNG를 생성하면, 아래에 다운로드 버튼이 나타납니다.")


def download_a4_html(poster_html: str, filename_base: str):
    a4_shell = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(filename_base)}</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{ margin:0; background:#fff; }}
</style>
</head>
<body>
{poster_html}
</body>
</html>"""
    st.download_button(
        "⬇️ A4 인쇄용 HTML 다운로드",
        data=a4_shell.encode("utf-8"),
        file_name=f"{filename_base}.html",
        mime="text/html",
        use_container_width=True,
    )


# -----------------------------
# 화면 구성
# -----------------------------
input_calendar(int(sel_year), int(sel_month))

st.markdown("---")
st.subheader("2) 포스터(달력형) 미리보기")
poster_html = build_poster_html(int(sel_year), int(sel_month))
components.html(f"<div class='poster-wrap'>{poster_html}</div>", height=980, scrolling=True)

st.markdown("---")
st.subheader("3) 보내기용 파일 만들기")

c1, c2 = st.columns([1, 1])
with c1:
    st.markdown("**PNG(사진) 다운로드**")
    st.caption("휴대폰 문자/카톡으로 보내기 가장 쉬운 방식입니다.")
    poster_png_downloader(poster_html, title_for_file)

with c2:
    st.markdown("**A4 인쇄용 HTML 다운로드**")
    st.caption("HTML을 열고 ‘인쇄 → PDF 저장’하면 A4 1페이지로 정리하기 좋습니다.")
    download_a4_html(poster_html, title_for_file)

st.caption(f"파일명: {title_for_file} / 전화번호 표기: 동약협회 {ASSOC_PHONE}")
