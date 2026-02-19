import calendar
import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

# -----------------------------
# Paths
# -----------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BASE_CSV = DATA_DIR / "base_menu.csv"
CHANGE_CSV = DATA_DIR / "change_menu.csv"
DELIV_CSV = DATA_DIR / "delivery.csv"
MENU_CSV = DATA_DIR / "menu_index.csv"

BOWL_IMG_CANDIDATES = [
    Path("gongyang_bowl.png"),
    Path("images") / "gongyang_bowl.png",
    Path("static") / "gongyang_bowl.png",
]

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

GONGYANG_TEXT_4LINES = [
    "이 음식이 어디에서 왔는가",
    "내 덕행으로는 받기가 부끄럽네",
    "마음의 온갖 탐욕을 떠나",
    "바른 생각으로 이 공양을 받습니다",
]

# -----------------------------
# Utils
# -----------------------------
def load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        return df[columns]
    return pd.DataFrame(columns=columns)

def save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")

def get_value(df: pd.DataFrame, d: str, col: str) -> str:
    hit = df.loc[df["date"] == d, col]
    return "" if hit.empty else str(hit.iloc[0])

def upsert(df: pd.DataFrame, d: str, col: str, value: str) -> pd.DataFrame:
    df = df.copy()
    if (df["date"] == d).any():
        df.loc[df["date"] == d, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": d, col: value}])], ignore_index=True)
    return df

def delete_row(df: pd.DataFrame, d: str) -> pd.DataFrame:
    return df.loc[df["date"] != d].reset_index(drop=True)

def fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def mmdd_weekday(d: date) -> str:
    return f"{d.strftime('%m/%d')}({WEEKDAY_NAMES[d.weekday()]})"

def norm(s: str) -> str:
    return (s or "").strip()

def short(s: str, n: int = 12) -> str:
    s = norm(s)
    if not s:
        return ""
    return s if len(s) <= n else (s[: n - 1] + "…")

def find_bowl_image():
    for p in BOWL_IMG_CANDIDATES:
        if p.exists():
            return p
    return None

# -----------------------------
# Holiday helpers
# -----------------------------
def fixed_kr_holidays(year: int) -> dict[str, str]:
    # 고정 공휴일(양력)만 보장(정확도 매우 높음)
    return {
        f"{year}-01-01": "신정",
        f"{year}-03-01": "삼일절",
        f"{year}-05-05": "어린이날",
        f"{year}-06-06": "현충일",
        f"{year}-08-15": "광복절",
        f"{year}-10-03": "개천절",
        f"{year}-10-09": "한글날",
        f"{year}-12-25": "성탄절",
    }

def try_holidays_lib(year: int) -> dict[str, str]:
    # holidays 패키지가 있으면 더 정확(대체공휴일/음력 일부 포함 가능)
    try:
        import holidays  # type: ignore
        kr = holidays.KR(years=[year])
        return {d.strftime("%Y-%m-%d"): str(name) for d, name in kr.items()}
    except Exception:
        return {}

def build_holiday_map(year: int) -> dict[str, str]:
    lib = try_holidays_lib(year)
    return lib if lib else fixed_kr_holidays(year)

# -----------------------------
# Load data
# -----------------------------
base_df = load_csv(BASE_CSV, ["date", "base_menu"])
change_df = load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = load_csv(DELIV_CSV, ["date", "delivery"])
menu_df = load_csv(MENU_CSV, ["menu"])
menu_list = sorted({m.strip() for m in menu_df["menu"].tolist() if m.strip()})

# -----------------------------
# State init
# -----------------------------
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)

# -----------------------------
# Styles
# -----------------------------
st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap" rel="stylesheet">
<style>
.block-container { padding-top: 0.5rem; padding-bottom: 0.6rem; }

.titlebar{
  margin: 0.2rem 0 0.6rem 0;
  padding: 0.6rem 0.8rem;
  border-radius: 16px;
  background: rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.06);
}
.titlebar h1{
  margin: 0;
  text-align: center;
  font-weight: 900;
  font-size: 44px;
  letter-spacing: -1px;
}

.hero-box{
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(0,0,0,0.02);
  border: 1px solid rgba(0,0,0,0.06);
  height: 220px;
}
.gongyang-area{
  margin-top: 18px;        /* ✅ 글귀가 너무 위로 붙지 않게 */
  margin-left: 10px;       /* ✅ 조금 좌측으로 */
}
.gongyang-line{
  font-family: "Nanum Brush Script","궁서","바탕","Batang","Apple SD Gothic Neo","Malgun Gothic",serif;
  font-size: 36px;         /* ✅ 조금 크게 */
  font-weight: 800;        /* ✅ 굵게 */
  line-height: 1.08;
}

.cal-btn > button{
  width: 100% !important;
  text-align: left !important;
  border-radius: 12px !important;
  padding: 10px 10px !important;
  min-height: 106px !important;
  border: 1px solid rgba(0,0,0,0.12) !important;
  background: rgba(255,255,255,0.70) !important;
  white-space: pre-line !important; /* ✅ 줄바꿈 표시 */
}
.cal-btn.holiday > button{
  background: rgba(255,230,230,0.55) !important;
  border-color: rgba(220,0,0,0.25) !important;
}

.wd{
  text-align:center;
  font-weight:800;
  padding: 2px 0;
}
.wd.sun{ color: #d11; }

@media (max-width: 860px){
  .titlebar h1{ font-size: 34px; }
  .hero-box{ height: auto; }
  .gongyang-line{ font-size: 32px; }
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.title("설정")
    y = st.number_input("연도", 2020, 2100, int(st.session_state["year"]), 1, key="year_input")
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1, key="month_select")
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.divider()
    st.subheader("데이터 백업/복원")
    st.caption("Cloud 재시작 시 초기화될 수 있어, 백업 ZIP으로 복원합니다.")

    if st.button("백업 ZIP 만들기", use_container_width=True, key="mk_backup_btn"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in [BASE_CSV, CHANGE_CSV, DELIV_CSV, MENU_CSV]:
                if p.exists():
                    z.write(p, arcname=f"data/{p.name}")
        st.session_state["backup_bytes"] = buf.getvalue()

    if st.session_state.get("backup_bytes"):
        st.download_button(
            "⬇️ 백업 ZIP 다운로드",
            data=st.session_state["backup_bytes"],
            file_name="momsrak_backup.zip",
            mime="application/zip",
            use_container_width=True,
            key="dl_backup_btn",
        )

    up = st.file_uploader("복원 ZIP 업로드", type=["zip"], key="restore_zip")
    if up is not None:
        try:
            zdata = io.BytesIO(up.read())
            with zipfile.ZipFile(zdata, "r") as z:
                for name in z.namelist():
                    if name.startswith("data/") and name.endswith(".csv"):
                        out_path = DATA_DIR / Path(name).name
                        out_path.write_bytes(z.read(name))
            st.success("복원 완료! 즉시 반영합니다.")
            st.rerun()
        except Exception as e:
            st.error(f"복원 실패: {e}")

    st.divider()
    st.subheader("메뉴 인덱스")
    st.write(f"현재 메뉴 수: **{len(menu_list)}**")

    new_menu = st.text_input("➕ 메뉴 추가", value="", placeholder="예: 뚝불고기", key="menu_add_input")
    if st.button("추가", use_container_width=True, key="menu_add_btn"):
        nm = norm(new_menu)
        if not nm:
            st.warning("빈 값은 추가할 수 없습니다.")
        elif nm in menu_list:
            st.warning("이미 존재하는 메뉴입니다.")
        else:
            menu_list = sorted(set(menu_list + [nm]))
            save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
            st.success("추가 완료")
            st.rerun()

# -----------------------------
# Title (잘 보이도록 별도 타이틀바)
# -----------------------------
st.markdown(
    """
<div class="titlebar">
  <h1>🍱 맘스락 식단 변경 프로그램</h1>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# Header: bowl + text (상단 높이 일치)
# -----------------------------
bowl = find_bowl_image()
hc1, hc2 = st.columns([1, 3], vertical_alignment="top")

with hc1:
    st.markdown('<div class="hero-box">', unsafe_allow_html=True)
    if bowl:
        st.image(str(bowl), width=170)
    else:
        st.warning("그릇 그림 파일 없음 (gongyang_bowl.png)")
    st.markdown("</div>", unsafe_allow_html=True)

with hc2:
    st.markdown('<div class="hero-box">', unsafe_allow_html=True)
    st.markdown('<div class="gongyang-area">', unsafe_allow_html=True)
    for ln in GONGYANG_TEXT_4LINES:
        st.markdown(f"<div class='gongyang-line'>{ln}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# -----------------------------
# Calendar (1개월만 표시: monthdayscalendar 사용 / 셀 클릭=날짜 선택)
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])
holiday_map = build_holiday_map(year)

cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
weeks = cal.monthdayscalendar(year, month)  # ✅ 1개월만(다른달은 0으로 공백)

# weekday header
hdr = st.columns(7)
for i, wd in enumerate(WEEKDAY_NAMES):
    cls = "wd sun" if wd == "일" else "wd"
    hdr[i].markdown(f"<div class='{cls}'>{wd}</div>", unsafe_allow_html=True)

def is_sunday_daynum(daynum: int) -> bool:
    if daynum == 0:
        return False
    d = date(year, month, daynum)
    return d.weekday() == 6

def holiday_name(daynum: int) -> str:
    if daynum == 0:
        return ""
    return holiday_map.get(f"{year}-{month:02d}-{daynum:02d}", "")

for w in weeks:
    cols = st.columns(7)
    for i, daynum in enumerate(w):
        with cols[i]:
            if daynum == 0:
                # 공백(다른 달 날짜는 표시하지 않음)
                st.markdown(
                    "<div style='height:106px;border:1px dashed rgba(0,0,0,0.08);border-radius:12px;opacity:0.35;'></div>",
                    unsafe_allow_html=True,
                )
                continue

            d = date(year, month, daynum)
            d_str = fmt_date(d)

            base_v = norm(get_value(base_df, d_str, "base_menu"))
            chg_v = norm(get_value(change_df, d_str, "change_menu"))
            delv = norm(get_value(deliv_df, d_str, "delivery"))

            # 표시 순서: 기본 → 변경 → 배달불요
            lines = []
            if base_v:
                lines.append(f"🍱 {short(base_v, 12)}")
            if chg_v:
                lines.append(f"🔁 {short(chg_v, 12)}")
            if delv == "SKIP":
                lines.append("🚫 배달불요")

            hname = holiday_name(daynum)
            is_holiday = bool(hname) or (d.weekday() == 6)
            head = f"{daynum}"
            if is_holiday:
                # 빨간색 표현은 버튼 라벨에서 제한이 있어 🔴로 명확히 표시
                # (배경은 CSS로 붉게 처리)
                if hname:
                    head = f"🔴 {daynum}  🎌 {hname}"
                else:
                    head = f"🔴 {daynum}  (일)"

            label = head
            if lines:
                label += "\n" + "\n".join(lines)

            btn_class = "cal-btn holiday" if is_holiday else "cal-btn"
            st.markdown(f"<div class='{btn_class}'>", unsafe_allow_html=True)
            if st.button(label, key=f"daycell_{d_str}", use_container_width=True):
                st.session_state["selected_day"] = daynum
            st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# -----------------------------
# Selected date + editor
# -----------------------------
selected_day = int(st.session_state["selected_day"])
last_day = calendar.monthrange(year, month)[1]
if selected_day > last_day:
    selected_day = last_day
    st.session_state["selected_day"] = selected_day

selected_date = date(year, month, selected_day)
selected_str = fmt_date(selected_date)

base_key = f"base_{selected_str}"
chg_key = f"chg_{selected_str}"
delv_key = f"delv_{selected_str}"

# 삭제 후 초기화
if st.session_state.get("clear_base_input"):
    st.session_state[base_key] = ""
    st.session_state["clear_base_input"] = False
if st.session_state.get("clear_change_input"):
    st.session_state[chg_key] = ""
    st.session_state["clear_change_input"] = False

# 최초 로딩
if base_key not in st.session_state:
    st.session_state[base_key] = get_value(base_df, selected_str, "base_menu")
if chg_key not in st.session_state:
    st.session_state[chg_key] = get_value(change_df, selected_str, "change_menu")
if delv_key not in st.session_state:
    st.session_state[delv_key] = ("배달 불요" if get_value(deliv_df, selected_str, "delivery") == "SKIP" else "배달")

def save_base():
    global base_df
    base_df = upsert(base_df, selected_str, "base_menu", norm(st.session_state.get(base_key, "")))
    save_csv(base_df, BASE_CSV)
    st.toast("기본메뉴 저장", icon="✅")
    st.rerun()

def delete_base():
    global base_df
    base_df = delete_row(base_df, selected_str)
    save_csv(base_df, BASE_CSV)
    st.session_state["clear_base_input"] = True
    st.rerun()

def save_change():
    global change_df
    change_df = upsert(change_df, selected_str, "change_menu", norm(st.session_state.get(chg_key, "")))
    save_csv(change_df, CHANGE_CSV)
    st.toast("변경메뉴 저장", icon="✅")
    st.rerun()

def delete_change():
    global change_df
    change_df = delete_row(change_df, selected_str)
    save_csv(change_df, CHANGE_CSV)
    st.session_state["clear_change_input"] = True
    st.rerun()

def save_delivery():
    global deliv_df
    choice = st.session_state.get(delv_key, "배달")
    val = "SKIP" if choice == "배달 불요" else "DELIVER"
    deliv_df = upsert(deliv_df, selected_str, "delivery", val)
    save_csv(deliv_df, DELIV_CSV)
    st.toast("배달 상태 저장", icon="✅")
    st.rerun()

def clear_delivery():
    global deliv_df
    deliv_df = delete_row(deliv_df, selected_str)
    save_csv(deliv_df, DELIV_CSV)
    st.session_state[delv_key] = "배달"
    st.toast("배달 초기화", icon="🧹")
    st.rerun()

def on_pick_base():
    pick = st.session_state.get(f"pick_base_{selected_str}", "(선택 안함)")
    if pick != "(선택 안함)":
        st.session_state[base_key] = pick

def on_pick_change():
    pick = st.session_state.get(f"pick_chg_{selected_str}", "(선택 안함)")
    if pick != "(선택 안함)":
        st.session_state[chg_key] = pick

def build_month_sms(year_: int, month_: int) -> str:
    last_ = calendar.monthrange(year_, month_)[1]
    days = [d.date() for d in pd.date_range(date(year_, month_, 1), date(year_, month_, last_), freq="D")]

    skip_lines, change_lines = [], []
    for d in days:
        d_str = fmt_date(d)
        deliv_val = norm(get_value(deliv_df, d_str, "delivery"))
        base_v = norm(get_value(base_df, d_str, "base_menu"))
        chg_v = norm(get_value(change_df, d_str, "change_menu"))

        if deliv_val == "SKIP":
            skip_lines.append(f"▶ {mmdd_weekday(d)} : 배달불요")
            continue
        if chg_v:
            left = base_v if base_v else "-"
            change_lines.append(f"▶ {mmdd_weekday(d)} : {left} → {chg_v}")

    out = [
        "동약협회입니다.",
        f"{year_}년 {month_:02d}월 도시락 변경/배달불요 내역입니다.",
        "🚫【배달불요】",
        *skip_lines,
        "🔁【변경메뉴】",
        *change_lines,
        "감사합니다.",
    ]
    return "\n".join(out)

st.subheader(f"선택한 날짜: {selected_str} ({WEEKDAY_NAMES[selected_date.weekday()]})")

left, right = st.columns([1.15, 1])

with left:
    st.markdown("### 기본메뉴")
    if menu_list:
        st.selectbox(
            "인덱스 선택(기본) → 즉시 입력",
            ["(선택 안함)"] + menu_list,
            index=0,
            key=f"pick_base_{selected_str}",
            on_change=on_pick_base,
        )
    st.text_input("기본메뉴 입력", key=base_key)
    b1, b2 = st.columns(2)
    b1.button("저장", use_container_width=True, on_click=save_base, key=f"btn_save_base_{selected_str}")
    b2.button("삭제", use_container_width=True, on_click=delete_base, key=f"btn_del_base_{selected_str}")

    st.markdown("### 변경메뉴")
    if menu_list:
        st.selectbox(
            "인덱스 선택(변경) → 즉시 입력",
            ["(선택 안함)"] + menu_list,
            index=0,
            key=f"pick_chg_{selected_str}",
            on_change=on_pick_change,
        )
    st.text_input("변경메뉴 입력", key=chg_key)
    c1, c2 = st.columns(2)
    c1.button("저장", use_container_width=True, on_click=save_change, key=f"btn_save_chg_{selected_str}")
    c2.button("삭제", use_container_width=True, on_click=delete_change, key=f"btn_del_chg_{selected_str}")

    st.markdown("### 배달 상태")
    st.radio("배달/배달불요", ["배달", "배달 불요"], horizontal=True, key=delv_key)
    d1, d2 = st.columns(2)
    d1.button("저장", use_container_width=True, on_click=save_delivery, key=f"btn_save_delv_{selected_str}")
    d2.button("초기화", use_container_width=True, on_click=clear_delivery, key=f"btn_clear_delv_{selected_str}")

with right:
    st.markdown("### 📩 월간 문자 출력")
    st.text_area(
        "복사해서 문자로 보내기",
        value=build_month_sms(year, month),
        height=420,
        key=f"sms_{year}_{month}",
    )
