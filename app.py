# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
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
def _safe_read_csv(path: Path, expected_cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=expected_cols)
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        # 인코딩 문제 대비
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    for c in expected_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[expected_cols].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    df["date"] = df["date"].dt.date
    return df


def _find_asset_base64(candidates: list[str]) -> str | None:
    for name in candidates:
        p = APP_DIR / name
        if p.exists() and p.is_file():
            b = p.read_bytes()
            return base64.b64encode(b).decode("utf-8")
    return None


def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _weekday_kr(d: date) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]


def _month_title(year: int, month: int) -> str:
    return f"동약협회 {year}년 {month}월 식단변경 내역"


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _safe_read_csv(BASE_MENU_PATH, ["date", "base_menu"]).rename(columns={"base_menu": "base"})
chg_df = _safe_read_csv(CHANGE_MENU_PATH, ["date", "change_menu"]).rename(columns={"change_menu": "change"})
deliv_df = _safe_read_csv(DELIVERY_PATH, ["date", "delivery"]).rename(columns={"delivery": "delivery"})

# 합치기
df = (
    pd.merge(base_df, chg_df, on="date", how="outer")
    .merge(deliv_df, on="date", how="outer")
)

if df.empty:
    df = pd.DataFrame(columns=["date", "base", "change", "delivery"])

df["base"] = df["base"].fillna("")
df["change"] = df["change"].fillna("")
df["delivery"] = df["delivery"].fillna("N").str.upper().replace({"": "N"})
df["delivery"] = df["delivery"].where(df["delivery"].isin(["Y", "N"]), "N")

# -----------------------------
# 상단 UI
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.poster-wrap { max-width: 980px; margin: 0 auto; }
.mini-note { font-size: 12px; opacity: 0.7; }
hr { margin: 1.2rem 0 1rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

today = date.today()
years = list(range(today.year - 1, today.year + 2))
cols = st.columns([1, 1, 2, 2])
with cols[0]:
    sel_year = st.selectbox("년도", years, index=years.index(today.year) if today.year in years else 0)
with cols[1]:
    sel_month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with cols[2]:
    st.caption("※ 이 화면은 **포스터 미리보기 + PNG/HTML 다운로드**만 제공합니다.")
with cols[3]:
    st.caption("데이터 파일: data/base_menu.csv, data/change_menu.csv, data/delivery.csv")

title_for_file = _month_title(int(sel_year), int(sel_month))


# -----------------------------
# 포스터 HTML 생성 (월~금 달력)
# -----------------------------
def build_poster_html(year: int, month: int) -> str:
    moms_b64 = _find_asset_base64(ASSET_CANDIDATES["moms"])
    kapma_b64 = _find_asset_base64(ASSET_CANDIDATES["kapma"])
    bowl_b64 = _find_asset_base64(ASSET_CANDIDATES["bowl"])

    # 해당 월 데이터만
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    month_df = df[(df["date"] >= first_day) & (df["date"] <= last_day)].copy()
    # dict로 빠르게 조회
    base_map = {r["date"]: _norm(r["base"]) for _, r in month_df.iterrows()}
    chg_map = {r["date"]: _norm(r["change"]) for _, r in month_df.iterrows()}
    del_map = {r["date"]: _norm(r["delivery"]) for _, r in month_df.iterrows()}

    # 월~금만 (0~4). 달력은 주 단위로 구성하되 토/일은 아예 표시하지 않음.
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    weeks = cal.monthdatescalendar(year, month)  # 각 주는 7일
    # 주별로 월~금만 뽑기
    weeks_mf = []
    for w in weeks:
        mf = [d for d in w if d.weekday() <= 4]  # Mon-Fri
        weeks_mf.append(mf)

    def cell_html(d: date) -> str:
        # 다른 달 날짜는 빈칸 처리
        if d.month != month:
            return '<td class="cell empty"></td>'

        b = base_map.get(d, "")
        c = chg_map.get(d, "")
        dy = del_map.get(d, "N")

        # 상태
        is_delivery_off = (dy == "N")  # N이면 배달불요(기존 대화 기준)
        has_change = (c != "")

        # 표시 텍스트
        menu_line = ""
        if has_change:
            # 기본이 있으면 "기본 → 변경", 아니면 변경만
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

    # 로고 IMG
    def img_tag(b64: str | None, height_px: int) -> str:
        if not b64:
            return ""
        return f"<img src='data:image/png;base64,{b64}' style='height:{height_px}px; width:auto; display:block;'/>"

    moms_img = img_tag(moms_b64, 34)
    kapma_img = img_tag(kapma_b64, 34)
    bowl_img = img_tag(bowl_b64, 52)

    # 공양게(붓글씨 느낌 폰트는 환경차가 있어, 웹폰트 없이도 최대한 분위기만)
    gongyang_html = "<br/>".join(html.escape(line) for line in GONGYANG_TEXT.splitlines())

    month_title = _month_title(year, month)

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
    <div class="mini">※ 표시: 배달불요 / 변경 / 기본</div>
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
  .head {{
    display:flex; align-items:stretch; gap: 12px;
  }}
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
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    gap: 6px;
  }}
  .gong-title {{
    font-weight: 900;
    font-size: 18px;
    letter-spacing: .2px;
  }}
  .gong-text {{
    font-size: 14px;
    line-height: 1.35;
    text-align: center;
    white-space: normal;
    opacity: .92;
  }}
  .bowl {{
    margin-top: 2px;
  }}
  .main-title {{
    margin-top: 14px;
    font-size: 20px;
    font-weight: 900;
    text-align:center;
    letter-spacing: .2px;
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
  .cell.empty {{
    border: none;
    background: transparent;
  }}
  .cell.base {{
    background: rgba(0,0,0,0.01);
  }}
  .cell.chg {{
    background: rgba(255, 210, 80, 0.20);
    border-color: rgba(255, 170, 0, 0.35);
  }}
  .cell.off {{
    background: rgba(255, 80, 80, 0.16);
    border-color: rgba(255, 80, 80, 0.30);
  }}
  .d-top {{
    display:flex; justify-content:space-between; align-items:flex-start; gap: 6px;
    margin-bottom: 6px;
  }}
  .d-num {{
    font-weight: 900;
    font-size: 16px;
  }}
  .d-wd {{
    font-weight: 700;
    font-size: 12px;
    opacity: .75;
    margin-left: 4px;
  }}
  .d-badge .badge {{
    display:inline-block;
    font-size: 12px;
    padding: 3px 8px;
    border-radius: 999px;
    font-weight: 800;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(255,255,255,0.7);
  }}
  .badge.chg {{
    border-color: rgba(255, 170, 0, 0.45);
  }}
  .badge.off {{
    border-color: rgba(255, 80, 80, 0.45);
  }}
  .d-menu {{
    font-size: 13px;
    line-height: 1.3;
    white-space: normal;
    word-break: keep-all;
  }}
  .arrow {{
    opacity: .75;
    font-weight: 900;
    margin: 0 2px;
  }}
  .foot {{
    margin-top: 6px;
    display:flex; justify-content:flex-end;
  }}
  .mini {{
    font-size: 12px;
    opacity: .7;
  }}
</style>
"""
    return poster


# -----------------------------
# PNG 캡처/다운로드 컴포넌트
# -----------------------------
def poster_png_downloader(poster_html: str, filename_base: str):
    """
    poster_html: 캡처할 포스터 전체 HTML
    filename_base: 예) '동약협회 2026년 2월 식단변경 내역'
    """
    # components.html ↔ Streamlit 값 전달 (postMessage)
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
# 화면: 포스터 미리보기 + 다운로드
# -----------------------------
st.markdown("---")
poster_html = build_poster_html(int(sel_year), int(sel_month))

st.subheader("포스터(달력형) 미리보기")
components.html(f"<div class='poster-wrap'>{poster_html}</div>", height=980, scrolling=True)

st.markdown("---")
st.subheader("보내기용 파일 만들기")

c1, c2 = st.columns([1, 1])
with c1:
    st.markdown("**1) PNG(사진) 만들기 & 다운로드**")
    st.caption("휴대폰 문자/카톡으로 보내기 가장 쉬운 방식입니다.")
    poster_png_downloader(poster_html, title_for_file)

with c2:
    st.markdown("**2) A4 인쇄용 HTML 다운로드**")
    st.caption("HTML을 열고 ‘인쇄 → PDF 저장’하면 A4 1페이지로 정리하기 좋습니다.")
    download_a4_html(poster_html, title_for_file)

st.markdown("---")
st.caption("파일명 규칙: " + title_for_file)
