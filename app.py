# app.py
# (정확도: 매우 높음) 삭제 버튼 오류(StreamlitAPIException) 방지:
# - 삭제 콜백에서 위젯 key 값을 직접 수정하지 않고(clear 플래그만 세팅)
# - 다음 rerun에서(위젯 생성 전에) 입력칸을 비우는 방식으로 통일

import calendar
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="식단 변경 프로그램", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BASE_CSV = DATA_DIR / "base_menu.csv"      # columns: date, base_menu
CHANGE_CSV = DATA_DIR / "change_menu.csv"  # columns: date, change_menu
DELIV_CSV = DATA_DIR / "delivery.csv"      # columns: date, delivery  (DELIVER / SKIP)

# ✅ 그릇 그림 파일(저장소/폴더 위치)
# - 같은 폴더에 두면: gongyang_bowl.png
# - images 폴더에 두면: images/gongyang_bowl.png
BOWL_IMG_CANDIDATES = [
    Path("gongyang_bowl.png"),
    Path("images") / "gongyang_bowl.png",
]


# -----------------------------
# 유틸
# -----------------------------
def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        return df[columns]
    return pd.DataFrame(columns=columns)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
    df = df.copy()
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _get_value(df: pd.DataFrame, d: str, col: str) -> str:
    hit = df.loc[df["date"] == d, col]
    return "" if hit.empty else str(hit.iloc[0])


def _upsert(df: pd.DataFrame, d: str, col: str, value: str) -> pd.DataFrame:
    df = df.copy()
    if (df["date"] == d).any():
        df.loc[df["date"] == d, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": d, col: value}])], ignore_index=True)
    return df


def _delete(df: pd.DataFrame, d: str) -> pd.DataFrame:
    df = df.copy()
    return df.loc[df["date"] != d].reset_index(drop=True)


def _fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# -----------------------------
# (복원) 공양게 글귀
# -----------------------------
GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

# ✅ 붓글씨 느낌: "Google Fonts"로 대체 (외부 폰트)
# - 네트워크가 막힌 환경이면 기본 글꼴로 표시됩니다.
CALLIGRAPHY_FONT = "Nanum Pen Script"


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _load_csv(BASE_CSV, ["date", "base_menu"])
change_df = _load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = _load_csv(DELIV_CSV, ["date", "delivery"])  # DELIVER / SKIP


# -----------------------------
# 상태 초기화
# -----------------------------
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

# 삭제 후 입력칸 비우기 플래그
st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)


# -----------------------------
# 상단 UI(그릇 그림 + 글귀)
# -----------------------------
st.markdown(
    f"""
<link href="https://fonts.googleapis.com/css2?family={CALLIGRAPHY_FONT.replace(' ', '+')}&display=swap" rel="stylesheet">
<style>
.block-container {{ padding-top: 1.2rem; }}
.gongyang-wrap {{
  display:flex; gap:28px; align-items:center;
  padding:18px 18px; border-radius:16px;
  background: rgba(0,0,0,0.03);
}}
.gongyang-text {{
  font-family: "{CALLIGRAPHY_FONT}", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  font-size: 26px; line-height: 1.35;
  white-space: pre-line;
}}
.small-hint {{ font-size:12px; opacity:0.6; }}
</style>
""",
    unsafe_allow_html=True,
)

img_path = None
for p in BOWL_IMG_CANDIDATES:
    if p.exists():
        img_path = p
        break

top_left, top_right = st.columns([1, 2.2], vertical_alignment="center")
with top_left:
    if img_path:
        st.image(str(img_path), use_container_width=True)
    else:
        st.caption("⚠️ 그릇 그림 파일을 찾지 못했습니다: gongyang_bowl.png")
        st.caption("저장소 루트 또는 images/ 폴더에 올려주세요.")
with top_right:
    st.markdown(f'<div class="gongyang-wrap"><div class="gongyang-text">{GONGYANG_TEXT}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="small-hint">※ 글씨가 붓글씨로 안 보이면: 인터넷 차단 환경일 수 있어 기본 글꼴로 표시됩니다.</div>', unsafe_allow_html=True)

st.divider()


# -----------------------------
# 사이드바: 연/월 선택
# -----------------------------
with st.sidebar:
    st.title("📅 설정")
    y = st.number_input("연도", min_value=2020, max_value=2100, value=int(st.session_state["year"]), step=1)
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1)
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.divider()
    st.caption("데이터 파일")
    st.write(f"- {BASE_CSV.as_posix()}")
    st.write(f"- {CHANGE_CSV.as_posix()}")
    st.write(f"- {DELIV_CSV.as_posix()}")


# -----------------------------
# 달력
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])

cal = calendar.Calendar(firstweekday=0)  # 월요일 시작(0)
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

st.title("🍱 식단 변경 프로그램")

weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
hdr = st.columns(7)
for i in range(7):
    hdr[i].markdown(f"**{weekday_names[i]}**")

for week_start in range(0, len(month_days), 7):
    row_days = month_days[week_start:week_start + 7]
    row_cols = st.columns(7)
    for i, d in enumerate(row_days):
        d_str = _fmt_date(d)
        base_val = _get_value(base_df, d_str, "base_menu")
        change_val = _get_value(change_df, d_str, "change_menu")
        deliv_val = _get_value(deliv_df, d_str, "delivery")
        is_skip = (deliv_val == "SKIP")

        label = f"{d.day}"
        if is_skip:
            label += " 🚫"
        elif change_val.strip():
            label += " ✳️"
        elif base_val.strip():
            label += " ✅"

        if row_cols[i].button(label, key=f"daybtn_{d_str}", use_container_width=True):
            st.session_state["selected_day"] = d.day


# -----------------------------
# 선택 날짜
# -----------------------------
selected_day = int(st.session_state["selected_day"])
last_day = calendar.monthrange(year, month)[1]
if selected_day > last_day:
    selected_day = last_day
    st.session_state["selected_day"] = selected_day

selected_date = date(year, month, selected_day)
selected_str = _fmt_date(selected_date)

st.divider()
st.subheader(f"선택한 날짜: {selected_str} ({weekday_names[selected_date.weekday()]})")


# -----------------------------
# 위젯 key
# -----------------------------
base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"


# -----------------------------
# ✅ 핵심: 위젯 생성 전에만 session_state 값을 세팅(삭제 에러 방지)
# -----------------------------
if st.session_state.get("clear_base_input", False):
    st.session_state[base_text_key] = ""
    st.session_state["clear_base_input"] = False

if st.session_state.get("clear_change_input", False):
    st.session_state[change_text_key] = ""
    st.session_state["clear_change_input"] = False


# -----------------------------
# 초기값 주입(키 없을 때만)
# -----------------------------
cur_base = _get_value(base_df, selected_str, "base_menu")
cur_change = _get_value(change_df, selected_str, "change_menu")
cur_deliv = _get_value(deliv_df, selected_str, "delivery")

if base_text_key not in st.session_state:
    st.session_state[base_text_key] = cur_base
if change_text_key not in st.session_state:
    st.session_state[change_text_key] = cur_change
if delivery_key not in st.session_state:
    st.session_state[delivery_key] = ("배달 불요" if cur_deliv == "SKIP" else "배달")


# -----------------------------
# 콜백
# -----------------------------
def save_base():
    global base_df
    val = (st.session_state.get(base_text_key, "") or "").strip()
    base_df = _upsert(base_df, selected_str, "base_menu", val)
    _save_csv(base_df, BASE_CSV)
    st.toast("기본메뉴 저장 완료", icon="✅")


def delete_base():
    global base_df
    base_df = _delete(base_df, selected_str)
    _save_csv(base_df, BASE_CSV)
    st.session_state["clear_base_input"] = True
    st.rerun()


def save_change():
    global change_df
    val = (st.session_state.get(change_text_key, "") or "").strip()
    change_df = _upsert(change_df, selected_str, "change_menu", val)
    _save_csv(change_df, CHANGE_CSV)
    st.toast("변경메뉴 저장 완료", icon="✅")


def delete_change():
    global change_df
    change_df = _delete(change_df, selected_str)
    _save_csv(change_df, CHANGE_CSV)
    st.session_state["clear_change_input"] = True
    st.rerun()


def save_delivery():
    global deliv_df
    choice = st.session_state.get(delivery_key, "배달")
    val = "SKIP" if choice == "배달 불요" else "DELIVER"
    deliv_df = _upsert(deliv_df, selected_str, "delivery", val)
    _save_csv(deliv_df, DELIV_CSV)
    st.toast("배달 상태 저장 완료", icon="✅")


def clear_delivery():
    global deliv_df
    deliv_df = _delete(deliv_df, selected_str)
    _save_csv(deliv_df, DELIV_CSV)
    st.session_state[delivery_key] = "배달"
    st.toast("배달 상태 초기화(기본=배달)", icon="🧹")
    st.rerun()


# -----------------------------
# (복원) 문자 출력(SMS) 생성
# -----------------------------
def build_month_sms(year_: int, month_: int) -> str:
    """월 전체(평일 기준) 기본/변경/배달불요를 모아 문자로 출력 (간단 버전)"""
    last_ = calendar.monthrange(year_, month_)[1]
    start = date(year_, month_, 1)
    end = date(year_, month_, last_)
    all_days = pd.date_range(start, end, freq="D").strftime("%Y-%m-%d").tolist()

    lines = [f"[{year_}년 {month_:02d}월 도시락]"]
    for d_str in all_days:
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        wd = weekday_names[d_obj.weekday()]
        if wd in ("토", "일"):
            continue

        base_v = _get_value(base_df, d_str, "base_menu").strip()
        chg_v = _get_value(change_df, d_str, "change_menu").strip()
        deliv_v = _get_value(deliv_df, d_str, "delivery")
        if deliv_v == "SKIP":
            lines.append(f"{d_str[5:]}({wd}) 배달불요")
            continue

        if chg_v:
            lines.append(f"{d_str[5:]}({wd}) (기본){base_v or '-'} → (변경){chg_v}")
        else:
            lines.append(f"{d_str[5:]}({wd}) {base_v or '-'}")

    return "\n".join(lines)


# -----------------------------
# 화면: 입력/저장/삭제 + 문자 출력
# -----------------------------
left, right = st.columns([1.2, 1])

with left:
    st.markdown("### 기본메뉴")
    st.text_input("기본메뉴 입력", key=base_text_key, placeholder="예: 생고기김치찌개")
    c1, c2 = st.columns(2)
    c1.button("기본메뉴 저장", use_container_width=True, on_click=save_base)
    c2.button("기본메뉴 삭제", use_container_width=True, on_click=delete_base)

    st.markdown("### 변경메뉴")
    st.text_input("변경메뉴 입력", key=change_text_key, placeholder="예: 순두부찌개")
    c3, c4 = st.columns(2)
    c3.button("변경메뉴 저장", use_container_width=True, on_click=save_change)
    c4.button("변경메뉴 삭제", use_container_width=True, on_click=delete_change)

    st.markdown("### 배달 상태")
    st.radio("배달/배달불요", options=["배달", "배달 불요"], horizontal=True, key=delivery_key)
    c5, c6 = st.columns(2)
    c5.button("배달 상태 저장", use_container_width=True, on_click=save_delivery)
    c6.button("배달 상태 초기화", use_container_width=True, on_click=clear_delivery)

with right:
    st.markdown("### 요약(선택일)")
    disp_base = _get_value(base_df, selected_str, "base_menu")
    disp_change = _get_value(change_df, selected_str, "change_menu")
    disp_deliv = _get_value(deliv_df, selected_str, "delivery")
    disp_deliv_txt = "배달 불요" if disp_deliv == "SKIP" else "배달"

    st.write(f"- 기본메뉴: **{disp_base or '(없음)'}**")
    st.write(f"- 변경메뉴: **{disp_change or '(없음)'}**")
    st.write(f"- 배달: **{disp_deliv_txt}**")

    st.divider()
    st.markdown("### 📩 월간 문자 출력")
    sms = build_month_sms(year, month)
    st.text_area("복사해서 문자로 보내기", value=sms, height=320)

    st.caption("※ 포맷을 예전과 동일하게 맞추려면, 예전 문자 예시(캡처/텍스트) 1개만 주시면 그대로 재현해 드립니다.")
