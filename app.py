import calendar
import io
import zipfile
from datetime import date, datetime
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

def short(s: str, n: int = 10) -> str:
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
    """고정 공휴일(양력) + 대체공휴일은 여기서 완벽 반영 어렵지만 기본은 제공.
       정확도: 고정 공휴일 매우 높음
    """
    items = {
        f"{year}-01-01": "신정",
        f"{year}-03-01": "삼일절",
        f"{year}-05-05": "어린이날",
        f"{year}-06-06": "현충일",
        f"{year}-08-15": "광복절",
        f"{year}-10-03": "개천절",
        f"{year}-10-09": "한글날",
        f"{year}-12-25": "성탄절",
    }
    return items

def try_holidays_lib(year: int) -> dict[str, str]:
    """가능하면 holidays 패키지(KR) 사용. 없으면 빈 dict."""
    try:
        import holidays  # type: ignore
        kr = holidays.KR(years=[year])
        out = {}
        for d, name in kr.items():
            out[d.strftime("%Y-%m-%d")] = str(name)
        return out
    except Exception:
        return {}

def build_holiday_map(year: int) -> dict[str, str]:
    """우선순위: holidays 라이브러리 > 고정 공휴일"""
    lib = try_holidays_lib(year)
    if lib:
        return lib
    return fixed_kr_holidays(year)


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
# Styles  (요청하신 CSS 라인들은 사용하지 않음)
# -----------------------------
st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap" rel="stylesheet">
<style>
.block-container { padding-top: 0.6rem; padding-bottom: 0.6rem; }
.hero-box{
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.06);
}
.gongyang-line{
  font-family: "Nanum Brush Script","궁서","바탕","Batang","Apple SD Gothic Neo","Malgun Gothic",serif;
  font-size: 30px;
  line-height: 1.05;
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.title("📅 설정")
    y = st.number_input("연도", 2020, 2100, int(st.session_state["year"]), 1, key="year_input")
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1, key="month_select")
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.divider()
    st.subheader("💾 데이터 백업/복원")
    st.caption("Cloud 재시작으로 초기화될 수 있어, 백업 ZIP으로 복원 가능하게 합니다.")

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
    st.subheader("🍽️ 메뉴 인덱스")
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
# Header (상단 높이/상단선 일치: top 정렬)
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")

bowl = find_bowl_image()
hc1, hc2 = st.columns([1, 3], vertical_alignment="top")

with hc1:
    st.markdown('<div class="hero-box" style="padding-top:12px;">', unsafe_allow_html=True)
    if bowl:
        st.image(str(bowl), width=150)
    else:
        st.warning("그릇 그림 파일 없음 (gongyang_bowl.png)")
    st.markdown("</div>", unsafe_allow_html=True)

with hc2:
    st.markdown('<div class="hero-box" style="padding-top:12px;">', unsafe_allow_html=True)
    for ln in GONGYANG_TEXT_4LINES:
        st.markdown(f"<div class='gongyang-line'>{ln}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# -----------------------------
# Calendar (휴일/명절 빨간색 표시)
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])
holiday_map = build_holiday_map(year)  # { "YYYY-MM-DD": "휴일명" }

cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
weeks = cal.monthdatescalendar(year, month)

# 요일 헤더: 일요일은 빨강
hdr = st.columns(7)
for i, wd in enumerate(WEEKDAY_NAMES):
    if wd == "일":
        hdr[i].markdown("<div style='text-align:center;font-weight:800;color:#d11;'>일</div>", unsafe_allow_html=True)
    else:
        hdr[i].markdown(f"<div style='text-align:center;font-weight:800;'>{wd}</div>", unsafe_allow_html=True)

def is_sunday(d: date) -> bool:
    return d.weekday() == 6

def is_holiday(d: date) -> bool:
    return fmt_date(d) in holiday_map

def holiday_name(d: date) -> str:
    return holiday_map.get(fmt_date(d), "")

for w in weeks:
    cols = st.columns(7)
    for i, d in enumerate(w):
        d_str = fmt_date(d)
        is_current_month = (d.month == month)

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

        # 휴일 표시(빨간색)
        hname = holiday_name(d)
        holiday_flag = is_holiday(d) or is_sunday(d)
        date_color = "#d11" if holiday_flag else "#111"
        bg = "rgba(255,230,230,0.55)" if holiday_flag else "rgba(255,255,255,0.70)"
        opacity = "0.35" if not is_current_month else "1.0"

        with cols[i]:
            st.markdown(
                f"<div style='border:1px solid rgba(0,0,0,0.12);border-radius:12px;padding:6px;"
                f"min-height:100px;background:{bg};opacity:{opacity};'>",
                unsafe_allow_html=True,
            )

            if is_current_month:
                # 날짜 버튼은 그대로 두되, 날짜 텍스트는 위에 빨간색으로 별도 표기
                st.markdown(
                    f"<div style='font-weight:900;color:{date_color};margin-bottom:2px;'>{d.day}</div>",
                    unsafe_allow_html=True,
                )
                if st.button("선택", key=f"pick_{d_str}", use_container_width=True):
                    st.session_state["selected_day"] = d.day
            else:
                st.markdown(
                    f"<div style='font-weight:900;color:{date_color};margin-bottom:2px;'>{d.day}</div>",
                    unsafe_allow_html=True,
                )

            if hname:
                st.markdown(f"<div style='color:#d11;font-size:12px;font-weight:800;'>🎌 {hname}</div>", unsafe_allow_html=True)
            elif is_sunday(d):
                st.markdown("<div style='color:#d11;font-size:12px;font-weight:800;'>일요일</div>", unsafe_allow_html=True)

            if lines:
                st.markdown(
                    "<div style='margin-top:4px;font-size:12px;line-height:1.15;opacity:0.92;'>"
                    + "".join(f"<div style='margin:2px 0'>{x}</div>" for x in lines)
                    + "</div>",
                    unsafe_allow_html=True,
                )

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

if st.session_state.get("clear_base_input"):
    st.session_state[base_key] = ""
    st.session_state["clear_base_input"] = False
if st.session_state.get("clear_change_input"):
    st.session_state[chg_key] = ""
    st.session_state["clear_change_input"] = False

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
