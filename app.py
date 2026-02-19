# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import pandas as pd
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name
GONGYANG_PATH = DATA_DIR / "gongyang.txt"           # text file

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# -----------------------------
# 유틸
# -----------------------------
def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        pd.DataFrame({c: [] for c in columns}).to_csv(path, index=False, encoding="utf-8-sig")


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    df = pd.read_csv(path)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].copy()
    return df


def _save_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _to_datestr(d: date) -> str:
    return d.isoformat()


def _parse_datestr(s: str) -> date | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None


def _month_range(y: int, m: int) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _is_weekend(d: date) -> bool:
    # Monday=0 ... Sunday=6
    return d.weekday() >= 5


def _is_sunday(d: date) -> bool:
    return d.weekday() == 6


# -----------------------------
# 데이터 로드/저장
# -----------------------------
def load_base_menu() -> dict[str, str]:
    df = _load_csv(BASE_MENU_PATH, ["date", "base_menu"])
    df["date"] = df["date"].astype(str)
    df["base_menu"] = df["base_menu"].fillna("").astype(str)
    return dict(zip(df["date"], df["base_menu"]))


def save_base_menu(d: date, menu: str) -> None:
    df = _load_csv(BASE_MENU_PATH, ["date", "base_menu"])
    ds = _to_datestr(d)
    menu = (menu or "").strip()
    df["date"] = df["date"].astype(str)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "base_menu"] = menu
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "base_menu": menu}])], ignore_index=True)
    # 정리
    df["base_menu"] = df["base_menu"].fillna("").astype(str)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    _save_csv(BASE_MENU_PATH, df)


def load_change_menu() -> dict[str, str]:
    df = _load_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    df["date"] = df["date"].astype(str)
    df["change_menu"] = df["change_menu"].fillna("").astype(str)
    return dict(zip(df["date"], df["change_menu"]))


def save_change_menu(d: date, menu: str) -> None:
    df = _load_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    ds = _to_datestr(d)
    menu = (menu or "").strip()
    df["date"] = df["date"].astype(str)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "change_menu"] = menu
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "change_menu": menu}])], ignore_index=True)
    df["change_menu"] = df["change_menu"].fillna("").astype(str)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    _save_csv(CHANGE_MENU_PATH, df)


def load_delivery() -> dict[str, str]:
    df = _load_csv(DELIVERY_PATH, ["date", "delivery"])
    df["date"] = df["date"].astype(str)
    df["delivery"] = df["delivery"].fillna("Y").astype(str)
    # delivery: Y(배달), N(배달불요)
    return dict(zip(df["date"], df["delivery"]))


def save_delivery(d: date, delivery: str) -> None:
    df = _load_csv(DELIVERY_PATH, ["date", "delivery"])
    ds = _to_datestr(d)
    delivery = "N" if str(delivery).upper().startswith("N") else "Y"
    df["date"] = df["date"].astype(str)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "delivery"] = delivery
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "delivery": delivery}])], ignore_index=True)
    df["delivery"] = df["delivery"].fillna("Y").astype(str)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    _save_csv(DELIVERY_PATH, df)


def load_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    df = pd.read_csv(MENU_INDEX_PATH)
    if "name" not in df.columns:
        df = pd.DataFrame({"name": []})
    df["name"] = df["name"].fillna("").astype(str).str.strip()
    names = sorted([x for x in df["name"].tolist() if x])
    # 중복 제거
    uniq = []
    for n in names:
        if n not in uniq:
            uniq.append(n)
    return uniq


def save_menu_index(names: list[str]) -> None:
    cleaned = []
    for n in names:
        n2 = (n or "").strip()
        if n2 and n2 not in cleaned:
            cleaned.append(n2)
    df = pd.DataFrame({"name": sorted(cleaned)})
    _save_csv(MENU_INDEX_PATH, df)


def load_gongyang_text() -> str:
    if GONGYANG_PATH.exists():
        return GONGYANG_PATH.read_text(encoding="utf-8")
    default = (
        "이 음식이 어디에서 왔는가\n"
        "내 덕행으로는 받기가 부끄럽네\n"
        "그 공덕을 헤아려서 이 공양을 받습니다\n"
        "마음의 탐욕을 여의고 몸을 바르게 하여\n"
        "도를 이루고자 이 공양을 받습니다"
    )
    GONGYANG_PATH.write_text(default, encoding="utf-8")
    return default


def save_gongyang_text(text: str) -> None:
    GONGYANG_PATH.write_text(text or "", encoding="utf-8")


# -----------------------------
# 캘린더 UI
# -----------------------------
def render_calendar(y: int, m: int, base_map: dict[str, str], change_map: dict[str, str], deliv_map: dict[str, str]) -> date:
    cal = calendar.Calendar(firstweekday=0)  # Monday start
    month_days = list(cal.itermonthdates(y, m))

    # 7열 표 형태로 그리기
    st.markdown("### 📅 달력")
    header = st.columns(7)
    for i, wd in enumerate(WEEKDAYS_KO):
        # 일요일 강조만 살짝(색은 최소)
        if i == 6:
            header[i].markdown(f"<div style='text-align:center;font-weight:800;'>일</div>", unsafe_allow_html=True)
        else:
            header[i].markdown(f"<div style='text-align:center;font-weight:800;'>{wd}</div>", unsafe_allow_html=True)

    # 날짜 버튼
    selected = st.session_state.get("selected_date")
    if not selected:
        selected = date(y, m, 1)
        st.session_state["selected_date"] = selected

    rows = [month_days[i:i+7] for i in range(0, len(month_days), 7)]
    for week in rows:
        cols = st.columns(7)
        for i, d in enumerate(week):
            in_month = (d.month == m)
            ds = _to_datestr(d)

            base = base_map.get(ds, "")
            change = change_map.get(ds, "")
            delivery = deliv_map.get(ds, "Y")

            # 표시 텍스트
            line1 = f"{d.day:02d}"
            if not in_month:
                # 다른 달은 흐리게
                label = f"{line1}\n"
            else:
                label = f"{line1}\n"

            if in_month:
                if delivery == "N":
                    label += "배달불요\n"
                if change.strip():
                    label += f"변경: {change}\n"
                elif base.strip():
                    label += f"{base}\n"

            # 버튼 스타일: 최소한만
            btn_kwargs = dict(use_container_width=True)
            if not in_month:
                cols[i].button(label, key=f"day_{ds}", disabled=True, **btn_kwargs)
            else:
                clicked = cols[i].button(label, key=f"day_{ds}", **btn_kwargs)
                if clicked:
                    st.session_state["selected_date"] = d
                    selected = d
    return selected


# -----------------------------
# 문자 생성
# -----------------------------
def build_sms(y: int, m: int, base_map: dict[str, str], change_map: dict[str, str], deliv_map: dict[str, str]) -> str:
    start, end = _month_range(y, m)

    lines = []
    lines.append(f"[{y}년 {m:02d}월 도시락 주문/변경]")
    d = start
    while d <= end:
        ds = _to_datestr(d)
        # 주말은 보통 제외(필요시 바꿀 수 있음)
        if not _is_weekend(d):
            delivery = deliv_map.get(ds, "Y")
            base = base_map.get(ds, "").strip()
            change = change_map.get(ds, "").strip()

            day_part = f"{m:02d}/{d.day:02d}({WEEKDAYS_KO[d.weekday()]})"

            if delivery == "N":
                lines.append(f"{day_part}: 배달불요")
            else:
                if change:
                    # 기본도 같이 표시하고 싶으면 base를 붙임
                    if base:
                        lines.append(f"{day_part}: {base} → {change}")
                    else:
                        lines.append(f"{day_part}: 변경 {change}")
                else:
                    if base:
                        lines.append(f"{day_part}: {base}")
        d = date.fromordinal(d.toordinal() + 1)

    return "\n".join(lines)


# -----------------------------
# 화면 구성
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")

# 사이드바: 년/월 선택
today = date.today()
with st.sidebar:
    st.subheader("설정")
    year = st.number_input("연도", min_value=2024, max_value=2100, value=today.year, step=1)
    month = st.number_input("월", min_value=1, max_value=12, value=today.month, step=1)

    st.divider()
    st.subheader("🖋️ 글귀(공양게) 설정")
    gongyang_text = st.text_area(
        "표시할 글귀 (줄바꿈 그대로)",
        value=load_gongyang_text(),
        height=160
    )
    colg1, colg2 = st.columns([1, 1])
    with colg1:
        gongyang_font_size = st.slider("글자 크기", 24, 60, 42, 1)
    with colg2:
        gongyang_align = st.selectbox("정렬", ["center", "left", "right"], index=0)

    if st.button("💾 글귀 저장", use_container_width=True):
        save_gongyang_text(gongyang_text)
        st.success("저장했습니다.")

# 본문: 글귀 표시 (요구사항 미반영 방지: 여기서 바로 반영)
st.markdown(
    f"""
    <div style="
        font-family: 'Nanum Brush Script','Apple SD Gothic Neo','Malgun Gothic',serif;
        font-size: {gongyang_font_size}px;
        line-height: 1.15;
        text-align: {gongyang_align};
        white-space: pre-line;
        margin-top: 6px;
        margin-bottom: 18px;
    ">
    {gongyang_text}
    </div>
    """,
    unsafe_allow_html=True
)

# 데이터 로드
base_map = load_base_menu()
change_map = load_change_menu()
deliv_map = load_delivery()
menu_index = load_menu_index()

# 레이아웃
left, right = st.columns([1.35, 1.0], vertical_alignment="top")

with left:
    selected_date = render_calendar(int(year), int(month), base_map, change_map, deliv_map)

with right:
    st.markdown("### 🧾 선택 날짜 편집")
    st.write(f"선택: **{selected_date.strftime('%Y-%m-%d')} ({WEEKDAYS_KO[selected_date.weekday()]})**")

    ds = _to_datestr(selected_date)
    current_base = base_map.get(ds, "")
    current_change = change_map.get(ds, "")
    current_deliv = deliv_map.get(ds, "Y")

    # 배달 여부
    delivery_choice = st.radio(
        "배달",
        options=["배달", "배달불요"],
        index=0 if current_deliv == "Y" else 1,
        horizontal=True
    )

    # 기본메뉴 입력(직접 입력)
    base_input = st.text_input("기본메뉴", value=current_base)

    # 변경메뉴: 인덱스 선택 + 직접입력
    st.markdown("**변경메뉴**")
    colc1, colc2 = st.columns([1, 1])
    with colc1:
        pick = st.selectbox("인덱스에서 선택", options=["(선택 없음)"] + menu_index)
    with colc2:
        change_input = st.text_input("또는 직접 입력", value=current_change)

    if pick != "(선택 없음)":
        change_input = pick

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💾 기본메뉴 저장", use_container_width=True):
            save_base_menu(selected_date, base_input)
            st.success("기본메뉴 저장 완료")
            st.rerun()
    with b2:
        if st.button("💾 변경메뉴 저장", use_container_width=True):
            save_change_menu(selected_date, change_input)
            st.success("변경메뉴 저장 완료")
            st.rerun()
    with b3:
        if st.button("💾 배달 저장", use_container_width=True):
            save_delivery(selected_date, "N" if delivery_choice == "배달불요" else "Y")
            st.success("배달 상태 저장 완료")
            st.rerun()

    st.divider()

    st.markdown("### 📚 메뉴 인덱스 관리 (삭제 포함)")
    colm1, colm2 = st.columns([1.2, 1.0])

    with colm1:
        new_name = st.text_input("메뉴 추가", placeholder="예: 순두부찌개")
        if st.button("➕ 인덱스에 추가", use_container_width=True):
            nn = (new_name or "").strip()
            if nn:
                menu_index2 = menu_index + [nn]
                save_menu_index(menu_index2)
                st.success("추가했습니다.")
                st.rerun()
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with colm2:
        sel = st.selectbox("기존 메뉴", options=["(선택)"] + menu_index)
        rename = st.text_input("이름 변경", placeholder="새 이름")
        if st.button("✏️ 이름 변경", use_container_width=True):
            if sel == "(선택)":
                st.warning("먼저 메뉴를 선택해 주세요.")
            else:
                rn = (rename or "").strip()
                if not rn:
                    st.warning("새 이름을 입력해 주세요.")
                else:
                    menu_index2 = [rn if x == sel else x for x in menu_index]
                    save_menu_index(menu_index2)
                    st.success("변경했습니다.")
                    st.rerun()

        if st.button("🗑️ 삭제", use_container_width=True):
            if sel == "(선택)":
                st.warning("먼저 메뉴를 선택해 주세요.")
            else:
                menu_index2 = [x for x in menu_index if x != sel]
                save_menu_index(menu_index2)
                st.success("삭제했습니다.")
                st.rerun()

    st.divider()

    st.markdown("### 📩 월 문자 생성")
    sms_text = build_sms(int(year), int(month), base_map, change_map, deliv_map)
    st.text_area("복사해서 문자로 보내세요", value=sms_text, height=260)

st.caption("데이터 저장 위치: data/ (base_menu.csv, change_menu.csv, delivery.csv, menu_index.csv, gongyang.txt)")
