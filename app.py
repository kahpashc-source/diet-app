# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import pandas as pd
import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

# ✅ 중요: 저장 폴더를 "실행 위치"가 아니라 "app.py 위치"로 고정
# - 절전/재부팅 후 실행 위치가 달라도 data가 사라지는(새로 생성되는) 현상 방지
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name
GONGYANG_PATH = DATA_DIR / "gongyang.txt"           # text file

# ✅ 그릇 이미지 파일명 (프로젝트 폴더(app.py)와 같은 위치)
BOWL_IMAGE_PATH = APP_DIR / "gongyang_bowl.png"

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# -----------------------------
# 폰트 import (Noto Sans KR / 붓글씨)
# -----------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&family=Nanum+Brush+Script&display=swap');
      .wd-head{ text-align:center; font-weight:900; padding:6px 0; }
    </style>
    """,
    unsafe_allow_html=True
)

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
    return df[columns].copy()


def _save_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _to_datestr(d: date) -> str:
    return d.isoformat()


def _month_range(y: int, m: int) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


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
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    _save_csv(CHANGE_MENU_PATH, df)


def load_delivery() -> dict[str, str]:
    df = _load_csv(DELIVERY_PATH, ["date", "delivery"])
    df["date"] = df["date"].astype(str)
    df["delivery"] = df["delivery"].fillna("Y").astype(str)
    return dict(zip(df["date"], df["delivery"]))  # Y or N


def save_delivery(d: date, delivery: str) -> None:
    df = _load_csv(DELIVERY_PATH, ["date", "delivery"])
    ds = _to_datestr(d)
    delivery = "N" if str(delivery).upper().startswith("N") else "Y"
    df["date"] = df["date"].astype(str)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "delivery"] = delivery
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "delivery": delivery}])], ignore_index=True)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    _save_csv(DELIVERY_PATH, df)


def load_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    df = pd.read_csv(MENU_INDEX_PATH)
    if "name" not in df.columns:
        df = pd.DataFrame({"name": []})
    names = (
        df["name"].fillna("").astype(str).str.strip()
        .loc[lambda s: s != ""]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return names


def save_menu_index(names: list[str]) -> None:
    cleaned: list[str] = []
    for n in names:
        n2 = (n or "").strip()
        if n2 and n2 not in cleaned:
            cleaned.append(n2)
    _save_csv(MENU_INDEX_PATH, pd.DataFrame({"name": sorted(cleaned)}))


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
# 달력 (버튼 방식 / 새 창 열림 없음)
# - 달력 칸: 상태 네모(🟥/🟨/⬜) 1개만 표시
# - 내용: 이모티콘 없이 텍스트만
# -----------------------------
def render_calendar(y: int, m: int, base_map: dict[str, str], change_map: dict[str, str], deliv_map: dict[str, str]) -> date:
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    month_days = list(cal.itermonthdates(y, m))

    if "selected_date" not in st.session_state:
        st.session_state["selected_date"] = date(y, m, 1)

    selected: date = st.session_state["selected_date"]
    if selected.year != y or selected.month != m:
        selected = date(y, m, 1)
        st.session_state["selected_date"] = selected

    # 요일 헤더
    header = st.columns(7)
    for i, wd in enumerate(WEEKDAYS_KO):
        label = f"{wd}" if i != 6 else "일 ●"
        header[i].markdown(f"<div class='wd-head'>{label}</div>", unsafe_allow_html=True)

    # 7일씩 주 단위
    rows = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]
    for week in rows:
        cols = st.columns(7)
        for i, d in enumerate(week):
            in_month = (d.month == m)
            ds = _to_datestr(d)

            base = (base_map.get(ds, "") or "").strip()
            chg = (change_map.get(ds, "") or "").strip()
            delivery = deliv_map.get(ds, "Y")

            # 상태 네모(1개만)
            status_sq = ""
            if in_month and delivery == "N":
                status_sq = "🟥"
            elif in_month and chg:
                status_sq = "🟨"
            elif in_month and base:
                status_sq = "⬜"

            head = f"{d.day:02d}"
            if in_month and d == selected:
                head = f"⭐ {head}"
            if status_sq:
                head = f"{head} {status_sq}"

            lines = [head]
            if in_month and delivery == "N":
                lines.append("배달불요")
            if in_month and chg:
                lines.append(f"변경: {chg}")
            if in_month and base:
                lines.append(f"기본: {base}")

            label = "\n".join(lines)

            if not in_month:
                cols[i].button(label, key=f"day_{ds}", disabled=True, use_container_width=True)
            else:
                if cols[i].button(label, key=f"day_{ds}", use_container_width=True):
                    st.session_state["selected_date"] = d
                    selected = d

    return selected


# -----------------------------
# 문자 생성 (요청 형식)
# -----------------------------
def build_sms(y: int, m: int, base_map: dict[str, str], change_map: dict[str, str], deliv_map: dict[str, str]) -> str:
    start, end = _month_range(y, m)

    no_delivery = []
    changes = []

    d = start
    while d <= end:
        ds = _to_datestr(d)
        wd = WEEKDAYS_KO[d.weekday()]
        mmdd = f"{m:02d}/{d.day:02d}({wd})"

        delivery = deliv_map.get(ds, "Y")
        base = (base_map.get(ds, "") or "").strip()
        chg = (change_map.get(ds, "") or "").strip()

        if delivery == "N":
            no_delivery.append(f"▶ {mmdd} : 배달불요")
        if chg:
            if base:
                changes.append(f"▶ {mmdd} : {base} → {chg}")
            else:
                changes.append(f"▶ {mmdd} : {chg}")

        d = date.fromordinal(d.toordinal() + 1)

    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{y}년 {m:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("🚫【배달불요】")
    lines.extend(no_delivery if no_delivery else ["▶ 없음"])
    lines.append("🔁【변경메뉴】")
    lines.extend(changes if changes else ["▶ 없음"])
    lines.append("감사합니다.")
    return "\n".join(lines)


# -----------------------------
# 화면
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")

today = date.today()

# 사이드바
with st.sidebar:
    st.subheader("설정")
    year = st.number_input("연도", min_value=2024, max_value=2100, value=today.year, step=1)
    month = st.number_input("월", min_value=1, max_value=12, value=today.month, step=1)

    st.divider()
    st.subheader("💾 PC 저장 위치")
    st.caption(str(DATA_DIR))  # ✅ 어디에 저장되는지 항상 표시

    st.divider()
    st.subheader("🖋️ 글귀(공양게) 설정")
    gongyang_text = st.text_area("표시할 글귀 (줄바꿈 그대로)", value=load_gongyang_text(), height=160)

    font_choice = st.selectbox("서체 선택", ["Noto Sans KR (기본)", "붓글씨 (Nanum Brush Script)"], index=1)
    gongyang_font_size = st.slider("글자 크기", 18, 64, 42, 1)
    gongyang_align = st.selectbox("정렬", ["left", "center", "right"], index=0)

    if st.button("💾 글귀 저장", use_container_width=True):
        save_gongyang_text(gongyang_text)
        st.success("저장했습니다.")

# 폰트 패밀리
font_family = (
    "Noto Sans KR, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"
    if font_choice.startswith("Noto")
    else "'Nanum Brush Script', 'Apple SD Gothic Neo', 'Malgun Gothic', serif"
)

# 상단: 좌(그릇) / 우(글귀)
top_left, top_right = st.columns([1.0, 1.6], vertical_alignment="center")

with top_left:
    if BOWL_IMAGE_PATH.exists():
        st.image(str(BOWL_IMAGE_PATH), use_container_width=True)
    else:
        st.info("그릇 이미지 파일이 없습니다. 프로젝트 폴더에 'gongyang_bowl.png' 파일을 넣어 주세요.")

with top_right:
    st.markdown(
        f"""
        <div style="
            font-family: {font_family};
            font-size: {gongyang_font_size}px;
            line-height: 1.15;
            text-align: {gongyang_align};
            white-space: pre-line;
            padding-top: 6px;
        ">
        {gongyang_text}
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

# 데이터 로드
base_map = load_base_menu()
change_map = load_change_menu()
deliv_map = load_delivery()
menu_index = load_menu_index()

# 레이아웃
left, right = st.columns([1.35, 1.0], vertical_alignment="top")

with left:
    st.markdown("### 📅 달력 (🟥배달불요 / 🟨변경 / ⬜기본)")
    selected_date = render_calendar(int(year), int(month), base_map, change_map, deliv_map)

with right:
    st.markdown("### 🧾 선택 날짜 편집")
    st.write(f"선택: **{selected_date.strftime('%Y-%m-%d')} ({WEEKDAYS_KO[selected_date.weekday()]})**")

    ds = _to_datestr(selected_date)
    current_base = base_map.get(ds, "")
    current_change = change_map.get(ds, "")
    current_deliv = deliv_map.get(ds, "Y")

    # 배달 여부
    delivery_choice = st.radio("배달", options=["배달", "배달불요"], index=0 if current_deliv == "Y" else 1, horizontal=True)

    # 기본메뉴: 인덱스 선택 + 직접입력
    st.markdown("**기본메뉴**")
    colb1, colb2 = st.columns([1, 1])
    with colb1:
        base_pick = st.selectbox("인덱스에서 선택(기본)", options=["(선택 없음)"] + menu_index, key="base_pick")
    with colb2:
        base_input = st.text_input("또는 직접 입력(기본)", value=current_base, key="base_input")
    if base_pick != "(선택 없음)":
        base_input = base_pick

    # 변경메뉴: 인덱스 선택 + 직접입력
    st.markdown("**변경메뉴**")
    colc1, colc2 = st.columns([1, 1])
    with colc1:
        change_pick = st.selectbox("인덱스에서 선택(변경)", options=["(선택 없음)"] + menu_index, key="change_pick")
    with colc2:
        change_input = st.text_input("또는 직접 입력(변경)", value=current_change, key="change_input")
    if change_pick != "(선택 없음)":
        change_input = change_pick

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
        new_name = st.text_input("메뉴 추가", placeholder="예: 순두부찌개", key="idx_new")
        if st.button("➕ 인덱스에 추가", use_container_width=True, key="idx_add"):
            nn = (new_name or "").strip()
            if nn:
                save_menu_index(menu_index + [nn])
                st.success("추가했습니다.")
                st.rerun()
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with colm2:
        sel = st.selectbox("기존 메뉴", options=["(선택)"] + menu_index, key="idx_sel")
        rename = st.text_input("이름 변경", placeholder="새 이름", key="idx_rename")

        if st.button("✏️ 이름 변경", use_container_width=True, key="idx_rename_btn"):
            if sel == "(선택)":
                st.warning("먼저 메뉴를 선택해 주세요.")
            else:
                rn = (rename or "").strip()
                if not rn:
                    st.warning("새 이름을 입력해 주세요.")
                else:
                    save_menu_index([rn if x == sel else x for x in menu_index])
                    st.success("변경했습니다.")
                    st.rerun()

        if st.button("🗑️ 삭제", use_container_width=True, key="idx_del_btn"):
            if sel == "(선택)":
                st.warning("먼저 메뉴를 선택해 주세요.")
            else:
                save_menu_index([x for x in menu_index if x != sel])
                st.success("삭제했습니다.")
                st.rerun()

    st.divider()

    st.markdown("### 📩 월 문자 생성 (요청 형식)")
    sms_text = build_sms(int(year), int(month), base_map, change_map, deliv_map)
    st.text_area("복사해서 문자로 보내세요", value=sms_text, height=320)

st.caption("달력 상태표시: 🟥배달불요 / 🟨변경 / ⬜기본 | 데이터: data/ 폴더")
