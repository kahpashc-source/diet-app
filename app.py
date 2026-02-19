# app.py
# (정확도: 매우 높음) Streamlit 위젯 key(session_state) 충돌/삭제 시 에러를 막기 위해
# "삭제 버튼 콜백에서는 key 값을 직접 수정하지 않고, 플래그를 세운 뒤 rerun"
# → 다음 rerun에서 "위젯 생성 전에" 값을 비우는 방식으로 통일했습니다.

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


# -----------------------------
# 유틸
# -----------------------------
def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        # 컬럼 누락 방어
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


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _load_csv(BASE_CSV, ["date", "base_menu"])
change_df = _load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = _load_csv(DELIV_CSV, ["date", "delivery"])  # DELIVER / SKIP

# delivery 기본값: 비어 있으면 DELIVER로 간주
# (정확도: 높음) 사용자 편의상 화면 표시에서는 빈값도 "배달"로 봅니다.


# -----------------------------
# 상태 초기화
# -----------------------------
today = date.today()
if "year" not in st.session_state:
    st.session_state["year"] = today.year
if "month" not in st.session_state:
    st.session_state["month"] = today.month
if "selected_day" not in st.session_state:
    st.session_state["selected_day"] = today.day

# 입력칸 비우기 플래그(삭제/저장 후 정리용)
st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)


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
# 달력 그리기
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])

cal = calendar.Calendar(firstweekday=0)  # Monday=0
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

st.title("🍱 식단 변경 프로그램")

# 요일 헤더
weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
cols = st.columns(7)
for i in range(7):
    cols[i].markdown(f"**{weekday_names[i]}**")

# 날짜 버튼(주 단위 7개씩)
for week_start in range(0, len(month_days), 7):
    row_days = month_days[week_start:week_start + 7]
    row_cols = st.columns(7)

    for i, d in enumerate(row_days):
        d_str = _fmt_date(d)
        base_val = _get_value(base_df, d_str, "base_menu")
        change_val = _get_value(change_df, d_str, "change_menu")
        deliv_val = _get_value(deliv_df, d_str, "delivery")
        is_skip = (deliv_val == "SKIP")
        # 표시용 라벨
        label = f"{d.day}"
        if is_skip:
            label += " 🚫"
        elif change_val.strip():
            label += " ✳️"
        elif base_val.strip():
            label += " ✅"

        # 이번 달이 아니면 비활성(여기서는 month_days에 이번 달만 포함되어 있어 생략 가능)
        key = f"daybtn_{d_str}"
        if row_cols[i].button(label, key=key, use_container_width=True):
            st.session_state["selected_day"] = d.day


# -----------------------------
# 선택한 날짜
# -----------------------------
selected_day = int(st.session_state["selected_day"])
# 월의 마지막 일 넘어가는 경우 보정
last_day = calendar.monthrange(year, month)[1]
if selected_day > last_day:
    selected_day = last_day
    st.session_state["selected_day"] = selected_day

selected_date = date(year, month, selected_day)
selected_str = _fmt_date(selected_date)

st.divider()
st.subheader(f"선택한 날짜: {selected_str} ({weekday_names[selected_date.weekday()]})")


# -----------------------------
# 입력 위젯 key (날짜별로 고정)
# -----------------------------
base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"


# -----------------------------
# ✅ 핵심: 위젯 생성 전에만 session_state 값을 세팅(삭제 시 에러 방지)
# -----------------------------
if st.session_state.get("clear_base_input", False):
    st.session_state[base_text_key] = ""
    st.session_state["clear_base_input"] = False

if st.session_state.get("clear_change_input", False):
    st.session_state[change_text_key] = ""
    st.session_state["clear_change_input"] = False


# -----------------------------
# 현재값 가져오기 (초기값 주입)
# -----------------------------
cur_base = _get_value(base_df, selected_str, "base_menu")
cur_change = _get_value(change_df, selected_str, "change_menu")
cur_deliv = _get_value(deliv_df, selected_str, "delivery")  # DELIVER / SKIP / ""

# 텍스트 입력 초기값: key가 없을 때만 넣기 (이미 있으면 사용자가 편집 중일 수 있음)
if base_text_key not in st.session_state:
    st.session_state[base_text_key] = cur_base
if change_text_key not in st.session_state:
    st.session_state[change_text_key] = cur_change

# 배달 상태 초기값
if delivery_key not in st.session_state:
    st.session_state[delivery_key] = ("배달 불요" if cur_deliv == "SKIP" else "배달")


# -----------------------------
# 액션 콜백
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

    # ❗여기서 st.session_state[base_text_key] = "" 직접 세팅 금지(에러 원인)
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
# 화면: 입력/저장/삭제
# -----------------------------
left, right = st.columns([1.2, 1])

with left:
    st.markdown("### 기본메뉴")
    st.text_input("기본메뉴 입력", key=base_text_key, placeholder="예: 생고기김치찌개")
    c1, c2 = st.columns(2)
    c1.button("기본메뉴 저장", use_container_width=True, on_click=save_base)
    c2.button("기본메뉴 삭제", use_container_width=True, on_click=delete_base)

    st.markdown("### 변경메뉴")
    st.text_input("변경메뉴 입력", key=change_text_key, placeholder="예: (변경) 순두부찌개")
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
    # 화면 표시용 상태
    disp_base = _get_value(base_df, selected_str, "base_menu")
    disp_change = _get_value(change_df, selected_str, "change_menu")
    disp_deliv = _get_value(deliv_df, selected_str, "delivery")
    disp_deliv_txt = "배달 불요" if disp_deliv == "SKIP" else "배달"

    st.write(f"- 기본메뉴: **{disp_base or '(없음)'}**")
    st.write(f"- 변경메뉴: **{disp_change or '(없음)'}**")
    st.write(f"- 배달: **{disp_deliv_txt}**")

    st.divider()
    st.markdown("### 이번 달 전체 현황")
    # 월간 표
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)
    all_dates = pd.date_range(month_start, month_end, freq="D").strftime("%Y-%m-%d").tolist()

    rows = []
    for d_str in all_dates:
        d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
        rows.append(
            {
                "date": d_str,
                "weekday": weekday_names[d_obj.weekday()],
                "base_menu": _get_value(base_df, d_str, "base_menu"),
                "change_menu": _get_value(change_df, d_str, "change_menu"),
                "delivery": "배달 불요" if _get_value(deliv_df, d_str, "delivery") == "SKIP" else "배달",
            }
        )
    month_table = pd.DataFrame(rows)

    # 보기 좋게: 주말 옅게 표시 대신 필터만 제공
    show_weekend = st.checkbox("주말 포함", value=False)
    if not show_weekend:
        month_table = month_table[~month_table["weekday"].isin(["토", "일"])].reset_index(drop=True)

    st.dataframe(month_table, use_container_width=True, hide_index=True)
