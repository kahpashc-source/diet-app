# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import html
import io
import zipfile
import re
import unicodedata

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

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"
DELIVERY_PATH = DATA_DIR / "delivery.csv"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"
HOLIDAYS_PATH = DATA_DIR / "holidays.csv"

AUTO_BK_DIR = DATA_DIR / "autobackup"
AUTO_BK_DIR.mkdir(parents=True, exist_ok=True)

KAPMA_PHONE = "010-7101-5871"

MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

DEFAULT_GONGYANG = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

KOR_DOW = ["월", "화", "수", "목", "금", "토", "일"]

# -----------------------------
# 유틸
# -----------------------------
def ensure_csv(path: Path, cols: list[str]) -> None:
    if not path.exists():
        pd.DataFrame(columns=cols).to_csv(path, index=False, encoding="utf-8-sig")

def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False, na_filter=False)
    except Exception:
        return pd.read_csv(path, dtype=str, encoding="utf-8", keep_default_na=False, na_filter=False)

def save_df(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")

def norm_menu(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return "" if s.lower() == "nan" else s

def parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None

def safe_text(s: str) -> str:
    return html.escape(s or "")

def b64_image(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")

def upsert_date_value(df: pd.DataFrame, date_col: str, value_col: str, d: date, v: str) -> pd.DataFrame:
    dstr = d.isoformat()
    v = norm_menu(v)
    if df.empty:
        return pd.DataFrame({date_col: [dstr], value_col: [v]})
    df = df.copy()
    if date_col not in df.columns:
        df[date_col] = ""
    if value_col not in df.columns:
        df[value_col] = ""
    mask = df[date_col].astype(str) == dstr
    if mask.any():
        df.loc[mask, value_col] = v
    else:
        df = pd.concat([df, pd.DataFrame({date_col: [dstr], value_col: [v]})], ignore_index=True)
    return df

def upsert_delivery(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    dstr = d.isoformat()
    yn = "Y" if (yn or "").upper().startswith("Y") else "N"
    if df.empty:
        return pd.DataFrame({"date": [dstr], "delivery": [yn]})
    df = df.copy()
    if "date" not in df.columns:
        df["date"] = ""
    if "delivery" not in df.columns:
        df["delivery"] = "N"
    mask = df["date"].astype(str) == dstr
    if mask.any():
        df.loc[mask, "delivery"] = yn
    else:
        df = pd.concat([df, pd.DataFrame({"date": [dstr], "delivery": [yn]})], ignore_index=True)
    return df

def build_day_maps(year: int, month: int, base_df: pd.DataFrame, chg_df: pd.DataFrame, del_df: pd.DataFrame):
    base_map: dict[int, str] = {}
    chg_map: dict[int, str] = {}
    del_map: dict[int, bool] = {}
    del_exists: set[int] = set()

    if not base_df.empty and {"date", "base_menu"}.issubset(base_df.columns):
        for _, r in base_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                base_map[d.day] = norm_menu(r.get("base_menu", ""))

    if not chg_df.empty and {"date", "change_menu"}.issubset(chg_df.columns):
        for _, r in chg_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                chg_map[d.day] = norm_menu(r.get("change_menu", ""))

    if not del_df.empty and {"date", "delivery"}.issubset(del_df.columns):
        for _, r in del_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                del_exists.add(d.day)
                del_map[d.day] = str(r.get("delivery", "N")).upper().startswith("Y")

    return base_map, chg_map, del_map, del_exists

# -----------------------------
# 공휴일(기본 시드)
# -----------------------------
def ensure_holidays_seed() -> None:
    ensure_csv(HOLIDAYS_PATH, ["date", "name", "auto_delivery_no"])
    df = read_csv(HOLIDAYS_PATH)
    if not df.empty and "date" in df.columns and df["date"].astype(str).str.len().gt(0).any():
        return

    seed_2026 = [
        ("2026-01-01", "신정", "Y"),
        ("2026-02-16", "설날 연휴", "Y"),
        ("2026-02-17", "설날", "Y"),
        ("2026-02-18", "설날 연휴", "Y"),
        ("2026-03-01", "삼일절", "Y"),
        ("2026-03-02", "삼일절 대체공휴일", "Y"),
        ("2026-05-05", "어린이날", "Y"),
        ("2026-05-24", "부처님오신날", "Y"),
        ("2026-05-25", "부처님오신날 대체공휴일", "Y"),
        ("2026-06-06", "현충일", "Y"),
        ("2026-08-15", "광복절", "Y"),
        ("2026-08-17", "광복절 대체공휴일", "Y"),
        ("2026-09-24", "추석 연휴", "Y"),
        ("2026-09-25", "추석", "Y"),
        ("2026-09-26", "추석 연휴", "Y"),
        ("2026-10-03", "개천절", "Y"),
        ("2026-10-05", "개천절 대체공휴일", "Y"),
        ("2026-10-09", "한글날", "Y"),
        ("2026-12-25", "성탄절", "Y"),
    ]
    save_df(pd.DataFrame(seed_2026, columns=["date", "name", "auto_delivery_no"]), HOLIDAYS_PATH)

def load_holidays_map_for_month(year: int, month: int) -> dict[int, str]:
    df = read_csv(HOLIDAYS_PATH)
    if df.empty or "date" not in df.columns:
        return {}
    if "name" not in df.columns:
        df["name"] = ""
    if "auto_delivery_no" not in df.columns:
        df["auto_delivery_no"] = "Y"

    hm: dict[int, str] = {}
    for _, r in df.iterrows():
        d = parse_date(r.get("date"))
        if not d:
            continue
        if d.year == year and d.month == month:
            auto = str(r.get("auto_delivery_no", "Y")).upper().startswith("Y")
            if auto:
                hm[d.day] = norm_menu(r.get("name", "")) or "공휴일"
    return hm

def auto_apply_holiday_delivery_no(year: int, month: int, holiday_map: dict[int, str], del_df: pd.DataFrame, del_exists: set[int]):
    changed = 0
    for day in holiday_map.keys():
        if day in del_exists:
            continue
        del_df = upsert_delivery(del_df, date(year, month, day), "Y")
        changed += 1
    return del_df, changed

# -----------------------------
# 요약문(업체용) 생성
# -----------------------------
def build_vendor_summary_text(year: int, month: int, base_map: dict[int, str], chg_map: dict[int, str], del_map: dict[int, bool]) -> str:
    lines: list[str] = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")

    # 배달불요
    del_days = sorted([d for d, v in del_map.items() if v])
    if del_days:
        lines.append("🚫【배달불요】")
        for d in del_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            lines.append(f"▶ {month:02d}/{d:02d}({dow}) : 배달불요")

    # 변경메뉴(기본→변경 형식)
    chg_days = sorted([d for d, v in chg_map.items() if norm_menu(v)])
    if chg_days:
        lines.append("🔁【변경메뉴】")
        for d in chg_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            before = norm_menu(base_map.get(d, ""))
            after = norm_menu(chg_map.get(d, ""))
            if before and after and before != after:
                lines.append(f"▶ {month:02d}/{d:02d}({dow}) : {before} → {after}")
            elif after:
                # 기본이 없거나 동일하면 변경만 표시
                lines.append(f"▶ {month:02d}/{d:02d}({dow}) : {after}")

    if (not del_days) and (not chg_days):
        lines.append("※ 변경/배달불요 내역 없음")

    lines.append("감사합니다.")
    return "\n".join(lines)

# -----------------------------
# 데이터 초기화
# -----------------------------
ensure_csv(BASE_MENU_PATH, ["date", "base_menu"])
ensure_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
ensure_csv(DELIVERY_PATH, ["date", "delivery"])
ensure_csv(MENU_INDEX_PATH, ["name"])
ensure_holidays_seed()

base_df = read_csv(BASE_MENU_PATH)
chg_df = read_csv(CHANGE_MENU_PATH)
del_df = read_csv(DELIVERY_PATH)
idx_df = read_csv(MENU_INDEX_PATH)
if idx_df.empty:
    idx_df = pd.DataFrame(columns=["name"])
idx_df["name"] = idx_df.get("name", "").astype(str).apply(norm_menu)
idx_df = idx_df[idx_df["name"].str.len() > 0].drop_duplicates().sort_values("name").reset_index(drop=True)

# -----------------------------
# 사이드바
# -----------------------------
st.sidebar.header("월 선택")
t = date.today()
year = int(st.sidebar.number_input("연도", min_value=2020, max_value=2099, value=int(t.year), step=1))
month = int(st.sidebar.selectbox("월", list(range(1, 13)), index=int(t.month) - 1))
people = int(st.sidebar.number_input("인원", min_value=1, max_value=50, value=1, step=1))

# -----------------------------
# 헤더
# -----------------------------
components.html(f"""
<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin:4px 0 10px 0;">
  <div style="line-height:1.08;">
    <div style="font-size:38px;font-weight:900;">맘스락 {month:02d}월</div>
    <div style="font-size:38px;font-weight:900;">식단(배달) 변경</div>
    <div style="font-size:22px;font-weight:700;opacity:0.88;">( 인원 : {people}인 )</div>
  </div>
  <div style="text-align:right;line-height:1.2;white-space:nowrap;">
    <div style="font-size:14px;opacity:0.75;">동약협회</div>
    <div style="font-size:18px;font-weight:800;">{KAPMA_PHONE}</div>
  </div>
</div>
""", height=110)

# -----------------------------
# 로고/그림
# -----------------------------
with st.expander("로고/그림 설정(필요시)", expanded=False):
    c1, c2, c3 = st.columns(3)
    moms_up = c1.file_uploader("MOMS 로고 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="moms_up")
    kapma_up = c2.file_uploader("동약협회 로고 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="kapma_up")
    bowl_up = c3.file_uploader("그릇 그림 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="bowl_up")
    if moms_up is not None:
        MOMS_LOGO_PATH.write_bytes(moms_up.read()); st.success("MOMS 로고 저장됨")
    if kapma_up is not None:
        KAPMA_LOGO_PATH.write_bytes(kapma_up.read()); st.success("동약협회 로고 저장됨")
    if bowl_up is not None:
        BOWL_PATH.write_bytes(bowl_up.read()); st.success("그릇 그림 저장됨")

gongyang = st.text_area("공양게(포스터/출력에 사용)", value=DEFAULT_GONGYANG, height=110)

# -----------------------------
# 공휴일 + 맵
# -----------------------------
holiday_map = load_holidays_map_for_month(year, month)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)
del_df, holiday_auto_count = auto_apply_holiday_delivery_no(year, month, holiday_map, del_df, del_exists)
if holiday_auto_count > 0:
    save_df(del_df, DELIVERY_PATH)
    del_df = read_csv(DELIVERY_PATH)
    base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)

# -----------------------------
# 4) 포스터(스크린샷용) 미리보기 / 파일 출력(A4 1페이지 최적화)
# -----------------------------
st.subheader('4) "포스터(스크린샷용) 미리보기 / 파일 출력(A4 1페이지 최적화)"')

moms_logo_b64 = b64_image(MOMS_LOGO_PATH)
kapma_logo_b64 = b64_image(KAPMA_LOGO_PATH)
bowl_b64 = b64_image(BOWL_PATH)

def make_calendar_table_html(year: int, month: int) -> str:
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    rows = []
    rows.append("<tr>" + "".join([f"<th>{d}</th>" for d in KOR_DOW]) + "</tr>")
    for w in weeks:
        tds = []
        for day in w:
            if day == 0:
                tds.append("<td class='empty'></td>")
            else:
                if del_map.get(day, False): cls = "delivery"
                elif chg_map.get(day): cls = "change"
                else: cls = "normal"
                lines = [f"<div class='d'>{day:02d}</div>"]
                if day in holiday_map:
                    lines.append(f"<div class='tag tag-hol'>🎌 {safe_text(holiday_map[day])}</div>")
                if del_map.get(day, False):
                    lines.append("<div class='tag tag-del'>🚫 배달불요</div>")
                if chg_map.get(day):
                    lines.append(f"<div class='tag tag-chg'>🔁 {safe_text(chg_map[day])}</div>")
                if base_map.get(day):
                    lines.append(f"<div class='tag tag-base'>▫ {safe_text(base_map[day])}</div>")
                tds.append(f"<td class='{cls}'>" + "".join(lines) + "</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return "<table class='cal'>" + "".join(rows) + "</table>"

def make_poster_html(a4: bool = False, include_summary: bool = False) -> str:
    moms_img = f"data:image/png;base64,{moms_logo_b64}" if moms_logo_b64 else ""
    kapma_img = f"data:image/png;base64,{kapma_logo_b64}" if kapma_logo_b64 else ""
    bowl_img = f"data:image/png;base64,{bowl_b64}" if bowl_b64 else ""

    cal_html = make_calendar_table_html(year, month)
    page_w = "210mm" if a4 else "100%"
    page_h = "297mm" if a4 else "auto"
    pad = "10mm" if a4 else "14px"

    summary_text = build_vendor_summary_text(year, month, base_map, chg_map, del_map) if include_summary else ""
    summary_html = f"""
    <div class="summarybox">
      <div class="summarytitle">업체 전달용 요약</div>
      <pre class="summary">{safe_text(summary_text)}</pre>
    </div>
    """ if include_summary else ""

    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{
    margin:0; padding:0; background:#f7f7f7;
    font-family: "Apple SD Gothic Neo","Malgun Gothic","맑은 고딕","Noto Sans KR",sans-serif;
  }}
  .page {{ width:{page_w}; height:{page_h}; background:white; margin:0 auto; padding:{pad}; box-sizing:border-box; }}

  .top {{ display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:6mm; }}
  .brand {{ display:flex; align-items:center; gap:10px; border:1px solid rgba(0,0,0,0.10); border-radius:14px; padding:8px 10px; }}
  .brand img {{ height:44px; width:auto; display:block; }}
  .brand .txt .b1 {{ font-weight:900; font-size:20px; }}
  .brand .txt .b2 {{ font-weight:800; font-size:14px; opacity:0.85; white-space:nowrap; }}

  .title {{ text-align:center; margin:2mm 0 5mm 0; line-height:1.08; }}
  .title .t1 {{ font-size:34px; font-weight:900; }}
  .title .t2 {{ font-size:18px; font-weight:800; opacity:0.9; }}

  .mid {{ display:flex; justify-content:center; align-items:center; margin:0 0 6mm 0; }}
  .midbox {{ width:100%; border:1px solid rgba(0,0,0,0.10); border-radius:16px; padding:10px 12px;
             display:flex; gap:14px; align-items:center; justify-content:center; }}
  .midbox img {{ height:80px; width:auto; display:block; }}
  .gong {{ white-space:pre-line; font-size:15px; font-weight:800; line-height:1.35; }}

  table.cal {{ width:100%; border-collapse:separate; border-spacing:7px; table-layout:fixed; }}
  table.cal th {{ font-size:13px; font-weight:900; padding:6px 0; opacity:0.85; text-align:center; }}
  table.cal td {{ vertical-align:top; border:1px solid rgba(0,0,0,0.12); border-radius:14px; padding:7px 7px;
                 height:{'22mm' if a4 else '110px'}; overflow:hidden; }}
  td.empty {{ border:none; background:transparent; }}
  td.normal {{ background:white; }}
  td.change {{ background:rgba(255,180,0,0.10); border-color:rgba(255,180,0,0.35); }}
  td.delivery {{ background:rgba(255,0,0,0.08); border-color:rgba(255,0,0,0.35); }}
  .d {{ font-weight:900; font-size:15px; margin-bottom:3px; }}
  .tag {{ font-size:11px; font-weight:800; line-height:1.25; margin-top:2px; word-break:break-word; }}
  .tag-hol {{ color:#0b4d7a; }}
  .tag-del {{ color:#b00020; }}
  .tag-chg {{ color:#7a4a00; }}
  .tag-base {{ color:#333; opacity:0.9; }}

  .summarybox {{
    margin-top:6mm;
    border:1px solid rgba(0,0,0,0.12);
    border-radius:14px;
    padding:10px 12px;
  }}
  .summarytitle {{
    font-weight:900;
    font-size:14px;
    margin-bottom:6px;
    opacity:0.9;
  }}
  pre.summary {{
    margin:0;
    white-space:pre-wrap;
    font-size:12.5px;
    line-height:1.35;
    font-weight:700;
  }}

  .foot {{ margin-top:4mm; font-size:12px; opacity:0.75; display:flex; justify-content:space-between; }}
</style>
</head>
<body>
  <div class="page">
    <div class="top">
      <div class="brand">
        {f'<img src="{moms_img}"/>' if moms_img else '<div style="width:44px;height:44px;border-radius:10px;background:rgba(0,0,0,0.05)"></div>'}
        <div class="txt"><div class="b1">MOMS</div><div class="b2">도시락</div></div>
      </div>
      <div class="brand">
        {f'<img src="{kapma_img}"/>' if kapma_img else '<div style="width:44px;height:44px;border-radius:10px;background:rgba(0,0,0,0.05)"></div>'}
        <div class="txt"><div class="b1">동약협회</div><div class="b2">{safe_text(KAPMA_PHONE)}</div></div>
      </div>
    </div>

    <div class="title">
      <div class="t1">맘스락 {month:02d}월 식단(배달) 변경</div>
      <div class="t2">( 인원 : {people}인 )</div>
    </div>

    <div class="mid">
      <div class="midbox">
        {f'<img src="{bowl_img}"/>' if bowl_img else ''}
        <div class="gong">{safe_text(gongyang)}</div>
      </div>
    </div>

    {cal_html}

    {summary_html}

    <div class="foot">
      <div>※ 공휴일 🎌 / 변경·배달불요는 색으로 강조</div>
      <div>{year:04d}-{month:02d}</div>
    </div>
  </div>
</body>
</html>
"""

# 미리보기(요약 없이)
poster_html = make_poster_html(a4=False, include_summary=False)
components.html(poster_html, height=920, scrolling=True)

# -----------------------------
# 5) 업체전달용 파일 출력(요약 포함 A4)
# -----------------------------
st.subheader('5) "업체전달용 파일 출력"(A4 1페이지, 요약 삽입)')

vendor_html = make_poster_html(a4=True, include_summary=True)

# 파일명: 업체가 알아보기 쉽게
download_name = f"동약협회 {year}년 {month}월 식단 변경 내역.html"

st.download_button(
    "업체전달용 HTML 다운로드(A4 1페이지 + 요약 포함)",
    data=vendor_html.encode("utf-8-sig"),
    file_name=download_name,
    mime="text/html; charset=utf-8",
    use_container_width=True,
)

# 참고: 요약 텍스트도 화면에서 확인/복사 가능
with st.expander("업체 전달용 요약(복사용)", expanded=False):
    st.text_area("요약", value=build_vendor_summary_text(year, month, base_map, chg_map, del_map), height=220)
