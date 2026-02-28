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
import time

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
# 자동 백업(저장/삭제 시 실행)
# -----------------------------
def make_autobackup_zip(reason: str = "auto") -> None:
    """
    저장/삭제 직전에 호출:
    data/autobackup/yyyymmdd_HHMMSS_reason.zip 로 저장.
    최근 30개만 유지.
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

    # 최근 30개만 유지
    zips = sorted(AUTO_BK_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in zips[30:]:
        try:
            old.unlink()
        except Exception:
            pass

# -----------------------------
# 공휴일
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

st.sidebar.divider()
st.sidebar.caption("데이터 백업/복원")
col_b1, col_b2 = st.sidebar.columns(2)

def make_backup_zip() -> bytes:
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

with col_b1:
    st.download_button("ZIP 백업 다운로드", data=make_backup_zip(),
                       file_name=f"moms_menu_backup_{year:04d}{month:02d}.zip",
                       mime="application/zip", use_container_width=True)

with col_b2:
    up = st.file_uploader("ZIP 복원 업로드", type=["zip"], label_visibility="collapsed")
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
            st.sidebar.success("복원 완료! 즉시 반영됩니다.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"복원 실패: {e}")

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
moms_logo_b64 = b64_image(MOMS_LOGO_PATH)
kapma_logo_b64 = b64_image(KAPMA_LOGO_PATH)
bowl_b64 = b64_image(BOWL_PATH)

# -----------------------------
# 1) 메뉴 인덱스
# -----------------------------
st.subheader("1) 메뉴 인덱스 관리(가나다/사전순 자동정렬)")
cidx1, cidx2 = st.columns([2, 1])
with cidx1:
    new_item = st.text_input("새 메뉴 추가", placeholder="예) 소고기무국")
with cidx2:
    if st.button("인덱스에 추가", use_container_width=True):
        v = norm_menu(new_item)
        if v:
            idx_df = pd.concat([idx_df, pd.DataFrame({"name": [v]})], ignore_index=True)
            idx_df["name"] = idx_df["name"].astype(str).apply(norm_menu)
            idx_df = idx_df[idx_df["name"].str.len() > 0].drop_duplicates().sort_values("name").reset_index(drop=True)
            save_df(idx_df, MENU_INDEX_PATH)
            st.success("추가 및 저장 완료")
            st.rerun()
st.dataframe(idx_df, use_container_width=True, height=180)
st.divider()

# -----------------------------
# 공휴일 자동 반영
# -----------------------------
holiday_map = load_holidays_map_for_month(year, month)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)
del_df, holiday_auto_count = auto_apply_holiday_delivery_no(year, month, holiday_map, del_df, del_exists)
if holiday_auto_count > 0:
    save_df(del_df, DELIVERY_PATH)
    del_df = read_csv(DELIVERY_PATH)
    base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)

# -----------------------------
# 2) 월간 요약
# -----------------------------
st.subheader("2) 월간 요약(통계)")
days_in_month = calendar.monthrange(year, month)[1]
no_delivery_cnt = len([d for d, v in del_map.items() if v])
delivery_cnt = days_in_month - no_delivery_cnt
chg_cnt = len([d for d, v in chg_map.items() if v])

menus = []
for d in range(1, days_in_month + 1):
    if base_map.get(d): menus.append(base_map[d])
    if chg_map.get(d): menus.append(chg_map[d])

top_menu_df = pd.Series(menus, dtype="object").value_counts().head(10).reset_index()
top_menu_df.columns = ["메뉴", "횟수"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("총 일수", f"{days_in_month}일")
m2.metric("배달일수", f"{delivery_cnt}일")
m3.metric("배달불요", f"{no_delivery_cnt}일")
m4.metric("변경메뉴 있는 날", f"{chg_cnt}일")

if not top_menu_df.empty:
    st.markdown("**가장 자주 등장한 메뉴 TOP 10**")
    st.dataframe(top_menu_df, use_container_width=True, hide_index=True)
else:
    st.info("이번 달 메뉴 입력이 아직 없습니다.")
st.divider()

# -----------------------------
# 3) 달력(오늘 강조 + 색상)
# -----------------------------
st.subheader("3) 달력(1개월) — 날짜 클릭 → 입력/저장")

today = date.today()

STYLE = """
<style>
  .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;}
  .cal-head{font-weight:900;opacity:0.85;text-align:center;padding:6px 0;}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)
components.html('<div class="cal-grid">' + "".join([f'<div class="cal-head">{d}</div>' for d in ["월","화","수","목","금","토","일"]]) + "</div>", height=34)

if "selected_day" not in st.session_state:
    st.session_state.selected_day = None
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = False

cal = calendar.Calendar(firstweekday=0)
weeks = cal.monthdayscalendar(year, month)

def cell_kind(day: int) -> str:
    if day <= 0: return "empty"
    if del_map.get(day, False): return "delivery"
    if chg_map.get(day): return "change"
    if base_map.get(day): return "base"
    return "none"

def cell_css(kind: str, is_today: bool) -> str:
    # 기본 색상
    if kind == "delivery":
        base = "background: rgba(255,0,0,0.10) !important; border:1px solid rgba(255,0,0,0.35) !important;"
    elif kind == "change":
        base = "background: rgba(255,180,0,0.12) !important; border:1px solid rgba(255,180,0,0.40) !important;"
    elif kind == "base":
        base = "background: rgba(0,0,0,0.03) !important; border:1px solid rgba(0,0,0,0.14) !important;"
    else:
        base = "background: rgba(255,255,255,0.92) !important; border:1px solid rgba(0,0,0,0.14) !important;"
    # ✅ 오늘 강조: 테두리 파란색 + 살짝 굵게
    if is_today:
        base += " box-shadow: 0 0 0 2px rgba(0,120,255,0.55) inset !important;"
    return base

def cell_label(day: int) -> str:
    if day <= 0: return ""
    lines = [f"{day:02d}"]
    if year == today.year and month == today.month and day == today.day:
        lines.append("📌 TODAY")
    if day in holiday_map:
        lines.append(f"🎌 {holiday_map[day]}")
    if del_map.get(day, False):
        lines.append("🚫 배달불요")
    if chg_map.get(day):
        lines.append(f"🔶 변경: {chg_map[day]}")
    if base_map.get(day):
        lines.append(f"▫ 기본: {base_map[day]}")
    return "\n".join(lines)

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
                st.markdown(f"<style>div[data-testid='stButton'][data-key='{key}'] button{{{cell_css(kind, is_today)}}}</style>", unsafe_allow_html=True)
                if st.button(cell_label(day), key=key, use_container_width=True):
                    st.session_state.selected_day = int(day)
                    st.session_state.confirm_delete = False  # 날짜 바뀌면 삭제확인 초기화

# -----------------------------
# 날짜 입력 UI + 저장 시 자동 백업 + 삭제 확인
# -----------------------------
sel = st.session_state.selected_day
if sel is not None:
    dsel = date(year, month, sel)
    is_holiday = sel in holiday_map

    st.markdown("---")
    st.markdown(f"### 📌 선택한 날짜: {dsel.strftime('%Y-%m-%d')}" + (f"  (🎌 {holiday_map[sel]})" if is_holiday else ""))

    index_options = idx_df["name"].tolist() if (not idx_df.empty and "name" in idx_df.columns) else []
    left, right = st.columns([2, 1], gap="large")

    with left:
        cA, cB = st.columns(2, gap="medium")
        with cA:
            base_pick = st.selectbox("기본메뉴(인덱스 선택)", ["(선택안함)"] + index_options, index=0, key=f"base_pick_{dsel}")
            base_text = st.text_input("기본메뉴(직접 입력)", value=base_map.get(sel, ""), key=f"base_text_{dsel}")
        with cB:
            chg_pick = st.selectbox("변경메뉴(인덱스 선택)", ["(선택안함)"] + index_options, index=0, key=f"chg_pick_{dsel}")
            chg_text = st.text_input("변경메뉴(직접 입력)", value=chg_map.get(sel, ""), key=f"chg_text_{dsel}")

        default_del = del_map.get(sel, False) if (sel in del_exists) else (True if is_holiday else False)
        delivery_no = st.checkbox("🚫 배달불요(체크하면 배달불요)", value=default_del, key=f"del_{dsel}")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("저장", use_container_width=True):
                # ✅ 저장 직전 자동 백업
                make_autobackup_zip("save")

                base_v = base_text if base_pick == "(선택안함)" else base_pick
                chg_v = chg_text if chg_pick == "(선택안함)" else chg_pick

                base_df = upsert_date_value(base_df, "date", "base_menu", dsel, base_v)
                chg_df = upsert_date_value(chg_df, "date", "change_menu", dsel, chg_v)
                del_df = upsert_delivery(del_df, dsel, "Y" if delivery_no else "N")

                save_df(base_df, BASE_MENU_PATH)
                save_df(chg_df, CHANGE_MENU_PATH)
                save_df(del_df, DELIVERY_PATH)

                st.session_state.selected_day = None
                st.session_state.confirm_delete = False
                st.success("저장 완료 (자동 백업 생성됨)")
                st.rerun()

        with b2:
            if st.button("선택 취소", use_container_width=True):
                st.session_state.selected_day = None
                st.session_state.confirm_delete = False
                st.rerun()

        with b3:
            # ✅ 삭제 2단계 확인
            if not st.session_state.confirm_delete:
                if st.button("해당일 내용 삭제", use_container_width=True):
                    st.session_state.confirm_delete = True
                    st.warning("정말 삭제하시겠습니까? 아래에서 ‘삭제 확정’을 눌러주세요.")
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
                        st.success("삭제 완료 (자동 백업 생성됨)")
                        st.rerun()
                with cdel2:
                    if st.button("취소", use_container_width=True):
                        st.session_state.confirm_delete = False
                        st.info("삭제를 취소했습니다.")

    with right:
        st.markdown("#### 빠른 확인")
        st.write("기본:", base_map.get(sel, ""))
        st.write("변경:", chg_map.get(sel, ""))
        st.write("배달불요:", "예" if delivery_no else "아니오")
        if is_holiday:
            st.info(f"🎌 공휴일/기념일: {holiday_map[sel]}")
        st.caption("저장/삭제 시 자동 백업은 data/autobackup/에 남습니다.")

st.divider()

# -----------------------------
# 포스터 + A4 HTML 다운로드(깨짐 방지)
# -----------------------------
st.subheader("4) 포스터(스크린샷용) 미리보기 / 5) 업체 전달용 파일 출력(A4 1페이지 최적화)")

# 최신 데이터 재로딩
base_df = read_csv(BASE_MENU_PATH)
chg_df = read_csv(CHANGE_MENU_PATH)
del_df = read_csv(DELIVERY_PATH)
base_map, chg_map, del_map, del_exists = build_day_maps(year, month, base_df, chg_df, del_df)
holiday_map = load_holidays_map_for_month(year, month)

moms_logo_b64 = b64_image(MOMS_LOGO_PATH)
kapma_logo_b64 = b64_image(KAPMA_LOGO_PATH)
bowl_b64 = b64_image(BOWL_PATH)

def make_calendar_table_html(year: int, month: int) -> str:
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    rows = []
    rows.append("<tr>" + "".join([f"<th>{d}</th>" for d in ["월","화","수","목","금","토","일"]]) + "</tr>")
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
                    lines.append(f"<div class='tag tag-chg'>🔶 {safe_text(chg_map[day])}</div>")
                if base_map.get(day):
                    lines.append(f"<div class='tag tag-base'>▫ {safe_text(base_map[day])}</div>")
                tds.append(f"<td class='{cls}'>" + "".join(lines) + "</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return "<table class='cal'>" + "".join(rows) + "</table>"

def make_poster_html(a4: bool = False) -> str:
    moms_img = f"data:image/png;base64,{moms_logo_b64}" if moms_logo_b64 else ""
    kapma_img = f"data:image/png;base64,{kapma_logo_b64}" if kapma_logo_b64 else ""
    bowl_img = f"data:image/png;base64,{bowl_b64}" if bowl_b64 else ""
    cal_html = make_calendar_table_html(year, month)

    page_w = "210mm" if a4 else "100%"
    page_h = "297mm" if a4 else "auto"
    pad = "10mm" if a4 else "14px"

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
  .midbox img {{ height:86px; width:auto; display:block; }}
  .gong {{ white-space:pre-line; font-size:16px; font-weight:800; line-height:1.35; }}
  table.cal {{ width:100%; border-collapse:separate; border-spacing:8px; table-layout:fixed; }}
  table.cal th {{ font-size:14px; font-weight:900; padding:6px 0; opacity:0.85; text-align:center; }}
  table.cal td {{ vertical-align:top; border:1px solid rgba(0,0,0,0.12); border-radius:14px; padding:8px 8px;
                 height:{'26mm' if a4 else '110px'}; overflow:hidden; }}
  td.empty {{ border:none; background:transparent; }}
  td.normal {{ background:white; }}
  td.change {{ background:rgba(255,180,0,0.10); border-color:rgba(255,180,0,0.35); }}
  td.delivery {{ background:rgba(255,0,0,0.08); border-color:rgba(255,0,0,0.35); }}
  .d {{ font-weight:900; font-size:16px; margin-bottom:4px; }}
  .tag {{ font-size:12px; font-weight:800; line-height:1.25; margin-top:2px; word-break:break-word; }}
  .tag-hol {{ color:#0b4d7a; }}
  .tag-del {{ color:#b00020; }}
  .tag-chg {{ color:#7a4a00; }}
  .tag-base {{ color:#333; opacity:0.9; }}
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

    <div class="foot">
      <div>※ 공휴일 🎌 / 변경·배달불요는 색으로 강조</div>
      <div>{year:04d}-{month:02d}</div>
    </div>
  </div>
</body>
</html>
"""

poster_html = make_poster_html(a4=False)
components.html(poster_html, height=920, scrolling=True)

a4_html = make_poster_html(a4=True)
st.download_button(
    "업체 전달용 HTML 다운로드(A4 1페이지 최적화)",
    data=a4_html.encode("utf-8-sig"),
    file_name=f"맘스락_{year:04d}{month:02d}_식단변경_A4.html",
    mime="text/html; charset=utf-8",
    use_container_width=True,
)

st.divider()

# -----------------------------
# 6) 업체 문자 전송용 텍스트 + 복사 버튼
# -----------------------------
st.subheader("6) 업체 문자 전송용 텍스트(복사해서 전송)")

def build_message_text(year: int, month: int) -> str:
    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")

    del_days = sorted([d for d, v in del_map.items() if v])
    if del_days:
        lines.append("🚫【배달불요】")
        for d in del_days:
            lines.append(f"▶ {month:02d}/{d:02d} : 배달불요")

    chg_days = sorted([d for d, v in chg_map.items() if v])
    if chg_days:
        lines.append("🔶【변경메뉴】")
        for d in chg_days:
            lines.append(f"▶ {month:02d}/{d:02d} : {chg_map[d]}")

    if not del_days and not chg_days:
        lines.append("※ 변경/배달불요 내역 없음")

    lines.append(f"문의: {KAPMA_PHONE}")
    return "\n".join(lines)

msg = build_message_text(year, month)

cmsg1, cmsg2 = st.columns([3, 1])
with cmsg1:
    st.text_area("복사용", value=msg, height=220, key="msg_area")

with cmsg2:
    # ✅ JS로 클립보드 복사 (대부분 브라우저에서 동작)
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
      font-weight:800;
      cursor:pointer;
    ">클립보드 복사</button>
    <div id="copy_status" style="margin-top:10px;font-size:13px;opacity:0.85;white-space:pre-line;"></div>
    """
    components.html(copy_js, height=110)
