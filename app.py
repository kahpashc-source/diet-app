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

# =========================================================
# 기본 설정 / 경로
# =========================================================
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)  -> Y means "배달불요"
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name
HOLIDAYS_PATH = DATA_DIR / "holidays.csv"           # date,name,auto_delivery_no(Y/N)

AUTO_BK_DIR = DATA_DIR / "autobackup"
AUTO_BK_DIR.mkdir(parents=True, exist_ok=True)

# 연락처
KAPMA_PHONE = "010-7101-5871"

# 로고/이미지
MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

DEFAULT_GONGYANG = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

KOR_DOW = ["월", "화", "수", "목", "금", "토", "일"]


# =========================================================
# 유틸
# =========================================================
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


def norm_text(x) -> str:
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
    v = norm_text(v)
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


def upsert_delivery_no(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    # delivery.csv의 delivery 컬럼: Y이면 "배달불요", N이면 "배달"
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
                base_map[d.day] = norm_text(r.get("base_menu", ""))

    if not chg_df.empty and {"date", "change_menu"}.issubset(chg_df.columns):
        for _, r in chg_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                chg_map[d.day] = norm_text(r.get("change_menu", ""))

    if not del_df.empty and {"date", "delivery"}.issubset(del_df.columns):
        for _, r in del_df.iterrows():
            d = parse_date(r.get("date"))
            if d and d.year == year and d.month == month:
                del_exists.add(d.day)
                del_map[d.day] = str(r.get("delivery", "N")).upper().startswith("Y")

    return base_map, chg_map, del_map, del_exists


def make_autobackup_zip(reason: str = "auto") -> None:
    """
    저장/삭제 직전에 호출:
    data/autobackup/yyyymmdd_HHMMSS_reason.zip 로 저장. (최근 30개 유지)
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = AUTO_BK_DIR / f"{ts}_{reason}.zip"

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH, HOLIDAYS_PATH]:
            if p.exists():
                zf.writestr(p.name, p.read_bytes())
        for p in [MOMS_LOGO_PATH, KAPMA_LOGO_PATH, BOWL_PATH]:
            if p.exists():
                zf.writestr(f"assets/{p.name}", p.read_bytes())

    zip_path.write_bytes(mem.getvalue())

    zips = sorted(AUTO_BK_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in zips[30:]:
        try:
            old.unlink()
        except Exception:
            pass


# =========================================================
# 공휴일(시드 + 월 로딩)
# =========================================================
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
                hm[d.day] = norm_text(r.get("name", "")) or "공휴일"
    return hm


def auto_apply_holiday_delivery_no(
    year: int, month: int, holiday_map: dict[int, str], del_df: pd.DataFrame, del_exists: set[int]
) -> tuple[pd.DataFrame, int]:
    """
    공휴일인데 delivery.csv에 기록이 없으면 자동으로 Y(배달불요) 저장.
    - 사용자가 이미 저장한 날(기록 존재)은 존중
    """
    changed = 0
    for day in holiday_map.keys():
        if day in del_exists:
            continue
        del_df = upsert_delivery_no(del_df, date(year, month, day), "Y")
        changed += 1
    return del_df, changed


# =========================================================
# 업체 전달 요약(요청 형식)
# =========================================================
def build_vendor_summary_text(
    year: int,
    month: int,
    base_map: dict[int, str],
    chg_map: dict[int, str],
    del_map: dict[int, bool],
) -> str:
    lines: list[str] = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")

    del_days = sorted([d for d, v in del_map.items() if v])
    if del_days:
        lines.append("🚫【배달불요】")
        for d in del_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            lines.append(f"▶ {month:02d}/{d:02d}({dow}) : 배달불요")

    chg_days = sorted([d for d, v in chg_map.items() if norm_text(v)])
    if chg_days:
        lines.append("🔁【변경메뉴】")
        for d in chg_days:
            dow = KOR_DOW[date(year, month, d).weekday()]
            before = norm_text(base_map.get(d, ""))
            after = norm_text(chg_map.get(d, ""))
            if before and after and before != after:
                lines.append(f"▶ {month:02d}/{d:02d}({dow}) : {before} → {after}")
            elif after:
                lines.append(f"▶ {month:02d}/{d:02d}({dow}) : {after}")

    if (not del_days) and (not chg_days):
        lines.append("※ 변경/배달불요 내역 없음")

    lines.append("감사합니다.")
    return "\n".join(lines)


# =========================================================
# 포스터/업체전달용 HTML 생성
# =========================================================
def make_calendar_table_html(
    year: int,
    month: int,
    base_map: dict[int, str],
    chg_map: dict[int, str],
    del_map: dict[int, bool],
    holiday_map: dict[int, str],
    a4: bool,
) -> str:
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    weeks = cal.monthdayscalendar(year, month)

    rows = []
    rows.append("<tr>" + "".join([f"<th>{d}</th>" for d in KOR_DOW]) + "</tr>")

    for w in weeks:
        tds = []
        for day in w:
            if day == 0:
                tds.append("<td class='empty'></td>")
            else:
                if del_map.get(day, False):
                    cls = "delivery"
                elif chg_map.get(day):
                    cls = "change"
                else:
                    cls = "normal"

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

    # A4에서는 셀 높이를 조금 줄여 1페이지 안정화
    cell_h = "21mm" if a4 else "110px"
    border_spacing = "7px" if a4 else "8px"

    return f"""
<table class="cal" style="border-spacing:{border_spacing};">
  {''.join(rows)}
</table>
<style>
  table.cal {{ width:100%; border-collapse:separate; table-layout:fixed; }}
  table.cal th {{ font-size:13px; font-weight:900; padding:6px 0; opacity:0.85; text-align:center; }}
  table.cal td {{ vertical-align:top; border:1px solid rgba(0,0,0,0.12); border-radius:14px; padding:7px 7px;
                 height:{cell_h}; overflow:hidden; }}
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
</style>
"""


def make_poster_html(
    year: int,
    month: int,
    people: int,
    gongyang: str,
    moms_logo_b64: str | None,
    kapma_logo_b64: str | None,
    bowl_b64: str | None,
    base_map: dict[int, str],
    chg_map: dict[int, str],
    del_map: dict[int, bool],
    holiday_map: dict[int, str],
    a4: bool,
    include_summary: bool,
    summary_text: str,
) -> str:
    moms_img = f"data:image/png;base64,{moms_logo_b64}" if moms_logo_b64 else ""
    kapma_img = f"data:image/png;base64,{kapma_logo_b64}" if kapma_logo_b64 else ""
    bowl_img = f"data:image/png;base64,{bowl_b64}" if bowl_b64 else ""

    cal_html = make_calendar_table_html(year, month, base_map, chg_map, del_map, holiday_map, a4=a4)

    page_w = "210mm" if a4 else "100%"
    page_h = "297mm" if a4 else "auto"
    pad = "10mm" if a4 else "14px"

    summary_html = ""
    if include_summary:
        summary_html = f"""
        <div class="summarybox">
          <pre class="summary">{safe_text(summary_text)}</pre>
        </div>
        """

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
  .page {{
    width:{page_w};
    height:{page_h};
    background:white;
    margin:0 auto;
    padding:{pad};
    box-sizing:border-box;
  }}

  .top {{
    display:flex; justify-content:space-between; align-items:center; gap:10px;
    margin-bottom:6mm;
  }}
  .brand {{
    display:flex; align-items:center; gap:10px;
    border:1px solid rgba(0,0,0,0.10);
    border-radius:14px;
    padding:8px 10px;
  }}
  .brand img {{ height:44px; width:auto; display:block; }}
  .brand .txt .b1 {{ font-weight:900; font-size:20px; }}
  .brand .txt .b2 {{ font-weight:800; font-size:14px; opacity:0.85; white-space:nowrap; }}

  .title {{
    text-align:center;
    margin:2mm 0 5mm 0;
    line-height:1.08;
  }}
  .title .t1 {{ font-size:34px; font-weight:900; }}
  .title .t2 {{ font-size:18px; font-weight:800; opacity:0.9; }}

  .mid {{
    display:flex; justify-content:center; align-items:center;
    margin:0 0 6mm 0;
  }}
  .midbox {{
    width:100%;
    border:1px solid rgba(0,0,0,0.10);
    border-radius:16px;
    padding:10px 12px;
    display:flex;
    gap:14px;
    align-items:center;
    justify-content:center;
  }}
  .midbox img {{ height:80px; width:auto; display:block; }}
  .gong {{
    white-space:pre-line;
    font-size:15px;
    font-weight:800;
    line-height:1.35;
  }}

  .summarybox {{
    margin-top:6mm;
    border:1px solid rgba(0,0,0,0.12);
    border-radius:14px;
    padding:10px 12px;
  }}
  pre.summary {{
    margin:0;
    white-space:pre-wrap;
    font-size:{'12.2px' if a4 else '12.5px'};
    line-height:1.35;
    font-weight:800;
  }}
</style>
</head>

<body>
  <div class="page">
    <div class="top">
      <div class="brand">
        {f'<img src="{moms_img}"/>' if moms_img else '<div style="width:44px;height:44px;border-radius:10px;background:rgba(0,0,0,0.05)"></div>'}
        <div class="txt">
          <div class="b1">MOMS</div>
          <div class="b2">도시락</div>
        </div>
      </div>

      <div class="brand">
        {f'<img src="{kapma_img}"/>' if kapma_img else '<div style="width:44px;height:44px;border-radius:10px;background:rgba(0,0,0,0.05)"></div>'}
        <div class="txt">
          <div class="b1">동약협회</div>
          <div class="b2">{safe_text(KAPMA_PHONE)}</div>
        </div>
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
  </div>
</body>
</html>
"""


# =========================================================
# 데이터 초기화
# =========================================================
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
if "name" not in idx_df.columns:
    idx_df["name"] = ""
idx_df["name"] = idx_df["name"].astype(str).apply(norm_text)
idx_df = idx_df[idx_df["name"].str.len() > 0].drop_duplicates().sort_values("name").reset_index(drop=True)

# =========================================================
# 사이드바(월 선택 / 백업)
# =========================================================
st.sidebar.header("월 선택")
today = date.today()
year = int(st.sidebar.number_input("연도", min_value=2020, max_value=2099, value=int(today.year), step=1))
month = int(st.sidebar.selectbox("월", list(range(1, 13)), index=int(today.month) - 1))
people = int(st.sidebar.number_input("인원", min_value=1, max_value=50, value=1, step=1))

st.sidebar.divider()
st.sidebar.caption("데이터 백업/복원")

def make_backup_zip_bytes() -> bytes:
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH, HOLIDAYS_PATH]:
            if p.exists():
                zf.writestr(p.name, p.read_bytes())
        for p in [MOMS_LOGO_PATH, KAPMA_LOGO_PATH, BOWL_PATH]:
            if p.exists():
                zf.writestr(f"assets/{p.name}", p.read_bytes())
    mem.seek(0)
    return mem.read()

c_sb1, c_sb2 = st.sidebar.columns(2)
with c_sb1:
    st.download_button(
        "ZIP 백업",
        data=make_backup_zip_bytes(),
        file_name=f"moms_menu_backup_{year:04d}{month:02d}.zip",
        mime="application/zip",
        use_container_width=True,
    )
with c_sb2:
    up = st.file_uploader("ZIP 복원", type=["zip"], label_visibility="collapsed")
    if up is not None:
        try:
            data = up.read()
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                names = zf.namelist()
                for fname, path in [
                    ("base_menu.csv", BASE_MENU_PATH),
                    ("change_menu.csv", CHANGE_MENU_PATH),
                    ("delivery.csv", DELIVERY_PATH),
                    ("menu_index.csv", MENU_INDEX_PATH),
                    ("holidays.csv", HOLIDAYS_PATH),
                ]:
                    if fname in names:
                        path.write_bytes(zf.read(fname))
                for asset_name, path in [
                    ("assets/moms_logo.png", MOMS_LOGO_PATH),
                    ("assets/kapma_logo.png", KAPMA_LOGO_PATH),
                    ("assets/gongyang_bowl.png", BOWL_PATH),
                ]:
                    if asset_name in names:
                        path.write_bytes(zf.read(asset_name))
            st.sidebar.success("복원 완료!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"복원 실패: {e}")

# =========================================================
# 공휴일 자동 반영 + 월 데이터 맵
# =========================================================
holiday_map = load_holidays_map_for_month(year, month)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)
del_df, auto_cnt = auto_apply_holiday_delivery_no(year, month, holiday_map, del_df, del_exists)
if auto_cnt > 0:
    save_df(del_df, DELIVERY_PATH)
    del_df = read_csv(DELIVERY_PATH)
    base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)

# =========================================================
# 스타일(초기 화면을 “덜 촌스럽게”)
# =========================================================
APP_STYLE = """
<style>
  .hero {
    border-radius: 18px;
    padding: 18px 18px;
    background: linear-gradient(135deg, rgba(255,245,230,0.75), rgba(235,245,255,0.75));
    border: 1px solid rgba(0,0,0,0.08);
    margin-bottom: 14px;
  }
  .hero-top {
    display:flex; justify-content:space-between; align-items:flex-end; gap:14px;
  }
  .hero-title {
    font-size: 40px; font-weight: 900; line-height: 1.06;
    margin:0;
  }
  .hero-sub {
    font-size: 15px; font-weight: 800; opacity: 0.78;
    margin-top: 6px;
  }
  .hero-right {
    text-align:right;
    white-space:nowrap;
  }
  .hero-right .k1 { font-size: 13px; opacity: 0.70; font-weight: 800; }
  .hero-right .k2 { font-size: 18px; font-weight: 900; }
  .pillrow { display:flex; gap:8px; flex-wrap:wrap; margin-top: 10px; }
  .pill { display:inline-block; padding:6px 10px; border-radius:999px;
          border:1px solid rgba(0,0,0,0.10); background: rgba(255,255,255,0.75);
          font-size:13px; font-weight:800; opacity:0.86; }
  .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;}
  .cal-head{font-weight:900;opacity:0.85;text-align:center;padding:6px 0;}
</style>
"""
st.markdown(APP_STYLE, unsafe_allow_html=True)

# =========================================================
# 상단 히어로(초기 화면)
# =========================================================
hero_html = f"""
<div class="hero">
  <div class="hero-top">
    <div>
      <div class="hero-title">맘스락 {month:02d}월 식단(배달) 변경</div>
      <div class="hero-sub">달력에서 날짜를 클릭하면 바로 입력할 수 있습니다.</div>
      <div class="pillrow">
        <span class="pill">오늘: {today.strftime('%Y-%m-%d')}({KOR_DOW[today.weekday()]})</span>
        <span class="pill">인원: {people}인</span>
        <span class="pill">자동백업: 저장/삭제 시 생성</span>
      </div>
    </div>
    <div class="hero-right">
      <div class="k1">동약협회</div>
      <div class="k2">{KAPMA_PHONE}</div>
    </div>
  </div>
</div>
"""
components.html(hero_html, height=150)

# 퀵 액션(스크롤)
qa1, qa2, qa3, qa4 = st.columns(4)
with qa1:
    if st.button("📅 달력으로", use_container_width=True):
        components.html(
            "<script>const el=document.getElementById('sec_calendar'); if(el){el.scrollIntoView({behavior:'smooth'});}</script>",
            height=0,
        )
with qa2:
    if st.button("🖼️ 포스터 미리보기", use_container_width=True):
        components.html(
            "<script>const el=document.getElementById('sec_poster'); if(el){el.scrollIntoView({behavior:'smooth'});}</script>",
            height=0,
        )
with qa3:
    if st.button("📄 업체전달용 출력", use_container_width=True):
        components.html(
            "<script>const el=document.getElementById('sec_vendor'); if(el){el.scrollIntoView({behavior:'smooth'});}</script>",
            height=0,
        )
with qa4:
    if st.button("📋 문자 복사", use_container_width=True):
        components.html(
            "<script>const el=document.getElementById('sec_message'); if(el){el.scrollIntoView({behavior:'smooth'});}</script>",
            height=0,
        )

# =========================================================
# 로고/공양게 설정
# =========================================================
with st.expander("로고/그림 설정(필요시)", expanded=False):
    c1, c2, c3 = st.columns(3)
    moms_up = c1.file_uploader("MOMS 로고 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="moms_up")
    kapma_up = c2.file_uploader("동약협회 로고 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="kapma_up")
    bowl_up = c3.file_uploader("그릇 그림 업로드 (png/jpg)", type=["png", "jpg", "jpeg"], key="bowl_up")
    if moms_up is not None:
        MOMS_LOGO_PATH.write_bytes(moms_up.read())
        st.success("MOMS 로고 저장됨")
    if kapma_up is not None:
        KAPMA_LOGO_PATH.write_bytes(kapma_up.read())
        st.success("동약협회 로고 저장됨")
    if bowl_up is not None:
        BOWL_PATH.write_bytes(bowl_up.read())
        st.success("그릇 그림 저장됨")

gongyang = st.text_area("공양게(포스터/출력에 사용)", value=DEFAULT_GONGYANG, height=110)

moms_logo_b64 = b64_image(MOMS_LOGO_PATH)
kapma_logo_b64 = b64_image(KAPMA_LOGO_PATH)
bowl_b64 = b64_image(BOWL_PATH)

# =========================================================
# 1) 메뉴 인덱스 관리(간단)
# =========================================================
with st.expander("메뉴 인덱스(가나다/사전순 자동정렬)", expanded=False):
    cidx1, cidx2 = st.columns([2, 1])
    with cidx1:
        new_item = st.text_input("새 메뉴 추가", placeholder="예) 소고기무국")
    with cidx2:
        if st.button("인덱스에 추가", use_container_width=True):
            v = norm_text(new_item)
            if v:
                idx_df2 = pd.concat([idx_df, pd.DataFrame({"name": [v]})], ignore_index=True)
                idx_df2["name"] = idx_df2["name"].astype(str).apply(norm_text)
                idx_df2 = idx_df2[idx_df2["name"].str.len() > 0].drop_duplicates().sort_values("name").reset_index(drop=True)
                idx_df = idx_df2
                save_df(idx_df, MENU_INDEX_PATH)
                st.success("저장 완료")
                st.rerun()
    st.dataframe(idx_df, use_container_width=True, height=200)

# =========================================================
# 3) 달력(1개월) — 날짜 클릭 → 입력/저장
# =========================================================
st.markdown("<div id='sec_calendar'></div>", unsafe_allow_html=True)
st.subheader("3) 달력(1개월) — 날짜 클릭 → 입력/저장")

components.html('<div class="cal-grid">' + "".join([f'<div class="cal-head">{d}</div>' for d in KOR_DOW]) + "</div>", height=34)

if "selected_day" not in st.session_state:
    st.session_state.selected_day = None
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False

cal = calendar.Calendar(firstweekday=0)
weeks = cal.monthdayscalendar(year, month)

def cell_kind(day: int) -> str:
    if day <= 0:
        return "empty"
    if del_map.get(day, False):
        return "delivery"
    if chg_map.get(day):
        return "change"
    if base_map.get(day):
        return "base"
    return "none"

def cell_css(kind: str, is_today: bool) -> str:
    if kind == "delivery":
        base = "background: rgba(255,0,0,0.10) !important; border:1px solid rgba(255,0,0,0.35) !important;"
    elif kind == "change":
        base = "background: rgba(255,180,0,0.12) !important; border:1px solid rgba(255,180,0,0.40) !important;"
    elif kind == "base":
        base = "background: rgba(0,0,0,0.03) !important; border:1px solid rgba(0,0,0,0.14) !important;"
    else:
        base = "background: rgba(255,255,255,0.92) !important; border:1px solid rgba(0,0,0,0.14) !important;"
    if is_today:
        base += " box-shadow: 0 0 0 2px rgba(0,120,255,0.55) inset !important;"
    return base

def cell_label(day: int) -> str:
    if day <= 0:
        return ""
    lines = [f"{day:02d}"]
    if year == today.year and month == today.month and day == today.day:
        lines.append("📌 TODAY")
    if day in holiday_map:
        lines.append(f"🎌 {holiday_map[day]}")
    if del_map.get(day, False):
        lines.append("🚫 배달불요")
    if chg_map.get(day):
        lines.append(f"🔁 변경: {chg_map[day]}")
    if base_map.get(day):
        lines.append(f"▫ 기본: {base_map[day]}")
    return "\n".join(lines)

# 달력 렌더
for w in weeks:
    cols = st.columns(7, gap="small")
    for i, day in enumerate(w):
        with cols[i]:
            if day == 0:
                st.markdown("<div style='height:112px;border-radius:14px;background:rgba(0,0,0,0.02);'></div>", unsafe_allow_html=True)
            else:
                kind = cell_kind(day)
                is_today = (year == today.year and month == today.month and day == today.day)
                key = f"day_{year}_{month}_{day}"
                st.markdown(
                    f"<style>div[data-testid='stButton'][data-key='{key}'] button{{{cell_css(kind, is_today)}}}</style>",
                    unsafe_allow_html=True
                )
                if st.button(cell_label(day), key=key, use_container_width=True):
                    st.session_state.selected_day = int(day)
                    st.session_state.confirm_delete = False
                    # 클릭 즉시 입력 영역으로 스크롤
                    components.html(
                        "<script>setTimeout(()=>{const el=document.getElementById('input_anchor'); if(el){el.scrollIntoView({behavior:'smooth',block:'start'});} }, 60);</script>",
                        height=0
                    )

st.markdown("<div id='input_anchor'></div>", unsafe_allow_html=True)

# 입력 패널
sel = st.session_state.selected_day
if sel is not None:
    dsel = date(year, month, sel)
    dow = KOR_DOW[dsel.weekday()]
    is_holiday = sel in holiday_map

    st.markdown("---")
    st.markdown(f"### 📌 선택한 날짜: {dsel.strftime('%Y-%m-%d')}({dow})" + (f"  (🎌 {holiday_map[sel]})" if is_holiday else ""))

    # 버튼을 위로 올려 동선 최소화
    b1, b2, b3 = st.columns(3)

    # 인덱스 옵션
    index_options = idx_df["name"].tolist() if (not idx_df.empty and "name" in idx_df.columns) else []

    # 기본값(배달불요)
    default_del = del_map.get(sel, False) if (sel in del_exists) else (True if is_holiday else False)

    cA, cB = st.columns(2, gap="medium")
    with cA:
        base_pick = st.selectbox("기본메뉴(인덱스 선택)", ["(선택안함)"] + index_options, index=0, key=f"base_pick_{dsel}")
        base_text = st.text_input("기본메뉴(직접 입력)", value=base_map.get(sel, ""), key=f"base_text_{dsel}")
    with cB:
        chg_pick = st.selectbox("변경메뉴(인덱스 선택)", ["(선택안함)"] + index_options, index=0, key=f"chg_pick_{dsel}")
        chg_text = st.text_input("변경메뉴(직접 입력)", value=chg_map.get(sel, ""), key=f"chg_text_{dsel}")

    delivery_no = st.checkbox("🚫 배달불요(체크하면 배달불요)", value=default_del, key=f"del_{dsel}")

    with b1:
        if st.button("저장", use_container_width=True):
            make_autobackup_zip("save")

            base_v = base_text if base_pick == "(선택안함)" else base_pick
            chg_v = chg_text if chg_pick == "(선택안함)" else chg_pick

            base_df = upsert_date_value(base_df, "date", "base_menu", dsel, base_v)
            chg_df = upsert_date_value(chg_df, "date", "change_menu", dsel, chg_v)
            del_df = upsert_delivery_no(del_df, dsel, "Y" if delivery_no else "N")

            save_df(base_df, BASE_MENU_PATH)
            save_df(chg_df, CHANGE_MENU_PATH)
            save_df(del_df, DELIVERY_PATH)

            st.session_state.selected_day = None
            st.session_state.confirm_delete = False
            st.success("저장 완료")
            st.rerun()

    with b2:
        if st.button("선택 취소", use_container_width=True):
            st.session_state.selected_day = None
            st.session_state.confirm_delete = False
            st.rerun()

    with b3:
        if not st.session_state.confirm_delete:
            if st.button("해당일 내용 삭제", use_container_width=True):
                st.session_state.confirm_delete = True
                st.warning("정말 삭제하시겠습니까? 아래 ‘삭제 확정’을 눌러주세요.")
        else:
            cdel1, cdel2 = st.columns(2)
            with cdel1:
                if st.button("🗑️ 삭제 확정", use_container_width=True):
                    make_autobackup_zip("delete")

                    dstr = dsel.isoformat()
                    if not base_df.empty and "date" in base_df.columns:
                        base_df = base_df[base_df["date"].astype(str) != dstr]
                    if not chg_df.empty and "date" in chg_df.columns:
                        chg_df = chg_df[chg_df["date"].astype(str) != dstr]
                    if not del_df.empty and "date" in del_df.columns:
                        del_df = del_df[del_df["date"].astype(str) != dstr]

                    save_df(base_df, BASE_MENU_PATH)
                    save_df(chg_df, CHANGE_MENU_PATH)
                    save_df(del_df, DELIVERY_PATH)

                    st.session_state.selected_day = None
                    st.session_state.confirm_delete = False
                    st.success("삭제 완료")
                    st.rerun()
            with cdel2:
                if st.button("취소", use_container_width=True):
                    st.session_state.confirm_delete = False
                    st.info("삭제를 취소했습니다.")

st.divider()

# =========================================================
# 4) 포스터(스크린샷용) 미리보기 / 파일 출력(A4 1페이지 최적화)
# =========================================================
st.markdown("<div id='sec_poster'></div>", unsafe_allow_html=True)
st.subheader('4) "포스터(스크린샷용) 미리보기 / 파일 출력(A4 1페이지 최적화)"')

# 최신 데이터 재로딩(안전)
base_df = read_csv(BASE_MENU_PATH)
chg_df = read_csv(CHANGE_MENU_PATH)
del_df = read_csv(DELIVERY_PATH)
holiday_map = load_holidays_map_for_month(year, month)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)

poster_html = make_poster_html(
    year=year,
    month=month,
    people=people,
    gongyang=gongyang,
    moms_logo_b64=moms_logo_b64,
    kapma_logo_b64=kapma_logo_b64,
    bowl_b64=bowl_b64,
    base_map=base_map,
    chg_map=chg_map,
    del_map=del_map,
    holiday_map=holiday_map,
    a4=False,
    include_summary=False,
    summary_text="",
)
components.html(poster_html, height=920, scrolling=True)

# 포스터 A4(요약 없음) 다운로드(원하시는 경우만 쓰도록 유지)
poster_a4_html = make_poster_html(
    year=year,
    month=month,
    people=people,
    gongyang=gongyang,
    moms_logo_b64=moms_logo_b64,
    kapma_logo_b64=kapma_logo_b64,
    bowl_b64=bowl_b64,
    base_map=base_map,
    chg_map=chg_map,
    del_map=del_map,
    holiday_map=holiday_map,
    a4=True,
    include_summary=False,
    summary_text="",
)
st.download_button(
    "포스터 A4 HTML 다운로드",
    data=poster_a4_html.encode("utf-8-sig"),
    file_name=f"포스터_{year}년_{month}월_A4.html",
    mime="text/html; charset=utf-8",
    use_container_width=True,
)

st.divider()

# =========================================================
# 5) 업체전달용 파일 출력(요약 포함 A4)
# =========================================================
st.markdown("<div id='sec_vendor'></div>", unsafe_allow_html=True)
st.subheader('5) "업체전달용 파일 출력"(A4 1페이지, 요약 삽입)')

vendor_summary = build_vendor_summary_text(year, month, base_map, chg_map, del_map)

vendor_html = make_poster_html(
    year=year,
    month=month,
    people=people,
    gongyang=gongyang,
    moms_logo_b64=moms_logo_b64,
    kapma_logo_b64=kapma_logo_b64,
    bowl_b64=bowl_b64,
    base_map=base_map,
    chg_map=chg_map,
    del_map=del_map,
    holiday_map=holiday_map,
    a4=True,
    include_summary=True,
    summary_text=vendor_summary,
)

download_name = f"동약협회 {year}년 {month}월 식단 변경 내역.html"

st.download_button(
    "업체전달용 HTML 다운로드(A4 1페이지 + 요약 포함)",
    data=vendor_html.encode("utf-8-sig"),
    file_name=download_name,
    mime="text/html; charset=utf-8",
    use_container_width=True,
)

with st.expander("업체 전달용 요약(화면에서 확인/복사)", expanded=False):
    st.text_area("요약", value=vendor_summary, height=240)

st.divider()

# =========================================================
# 문자(클립보드 복사 버튼)
# =========================================================
st.markdown("<div id='sec_message'></div>", unsafe_allow_html=True)
st.subheader("업체 문자 전송용(복사해서 전송)")

msg = vendor_summary  # 요약과 동일 포맷

cmsg1, cmsg2 = st.columns([3, 1])
with cmsg1:
    st.text_area("복사용", value=msg, height=220, key="msg_area")

with cmsg2:
    copy_js = f"""
    <script>
    async function copyText() {{
      try {{
        await navigator.clipboard.writeText({msg!r});
        const el = document.getElementById("copy_status");
        if (el) el.innerText = "✅ 복사 완료";
      }} catch (e) {{
        const el = document.getElementById("copy_status");
        if (el) el.innerText = "⚠️ 복사 실패(브라우저 제한)\\n텍스트 영역에서 직접 복사하세요.";
      }}
    }}
    </script>
    <button onclick="copyText()" style="
      width:100%;
      padding:10px 12px;
      border-radius:12px;
      border:1px solid rgba(0,0,0,0.18);
      background:white;
      font-weight:900;
      cursor:pointer;
    ">클립보드 복사</button>
    <div id="copy_status" style="margin-top:10px;font-size:13px;opacity:0.85;white-space:pre-line;"></div>
    """
    components.html(copy_js, height=110)

# =========================================================
# (선택) 휴무일 관리
# =========================================================
with st.expander("공휴일/휴무일 관리(holidays.csv)", expanded=False):
    st.caption("형식: date(YYYY-MM-DD), name, auto_delivery_no(Y/N)")
    hdf = read_csv(HOLIDAYS_PATH)
    st.dataframe(hdf, use_container_width=True, height=240)
