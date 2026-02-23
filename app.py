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

# ✅ 중요: 저장 폴더를 "실행 위치"가 아니라 "app.py 위치"로 고정
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# (선택) 공양게 이미지/텍스트
GONGYANG_IMG = APP_DIR / "gongyang_bowl.png"

GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

# -----------------------------
# UI: 여백(상단) 축소 + 약간 정리 (요청 2)
# -----------------------------
st.markdown(
    """
    <style>
      /* 상단 여백 줄이기 */
      .block-container { padding-top: 1.0rem !important; padding-bottom: 1.5rem !important; }

      /* 제목 아래 여백 줄이기 */
      h1 { margin-bottom: 0.4rem !important; }

      /* 달력 버튼: 새창 링크 방지(버튼만 사용) + 높이 고정 */
      div[data-testid="column"] button {
        width: 100% !important;
        text-align: left !important;
        white-space: pre-line !important;
        min-height: 86px !important;
        border-radius: 12px !important;
      }

      /* 사이드바 라벨/텍스트 약간 정돈 */
      section[data-testid="stSidebar"] { padding-top: 0.5rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# 데이터 유틸
# -----------------------------
def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, dtype=str, encoding="utf-8")
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].fillna("")
    return df

def _upsert(df: pd.DataFrame, key_col: str, key_val: str, value_col: str, value_val: str) -> pd.DataFrame:
    df = df.copy()
    mask = df[key_col].astype(str) == str(key_val)
    if mask.any():
        df.loc[mask, value_col] = value_val
    else:
        df = pd.concat([df, pd.DataFrame([{key_col: key_val, value_col: value_val}])], ignore_index=True)
    df = df.sort_values(key_col).reset_index(drop=True)
    return df

def _delete_key(df: pd.DataFrame, key_col: str, key_val: str) -> pd.DataFrame:
    df = df.copy()
    df = df[df[key_col].astype(str) != str(key_val)].reset_index(drop=True)
    return df

def _save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")

def _d2s(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def _s2d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _month_days(year: int, month: int):
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
    return cal.monthdatescalendar(year, month)

def _fmt_mmdd(d: date) -> str:
    return d.strftime("%m/%d")

def _weekday_kr(d: date) -> str:
    w = ["월","화","수","목","금","토","일"]
    return w[d.weekday()]

# -----------------------------
# 로드
# -----------------------------
base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])
idx_df = _read_csv(MENU_INDEX_PATH, ["name"])

# 인덱스 리스트
menu_index = [x for x in idx_df["name"].tolist() if str(x).strip() != ""]
menu_index_sorted = sorted(set(menu_index))

# 빠른 조회 dict
base_map = dict(zip(base_df["date"], base_df["base_menu"]))
change_map = dict(zip(change_df["date"], change_df["change_menu"]))
delivery_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))

# -----------------------------
# 사이드바
# -----------------------------
st.sidebar.title("설정")

today = date.today()
year = st.sidebar.number_input("연도", min_value=2020, max_value=2100, value=int(st.session_state.get("year", today.year)), step=1)
month = st.sidebar.number_input("월", min_value=1, max_value=12, value=int(st.session_state.get("month", today.month)), step=1)

st.session_state["year"] = int(year)
st.session_state["month"] = int(month)

st.sidebar.divider()

# ✅ 요청 1: “PC 저장 위치” → “서버 저장 위치(Cloud)”로 정리
st.sidebar.subheader("💾 서버 저장 위치(Cloud)")
st.sidebar.caption("아래 경로는 사용자의 PC가 아니라, Streamlit 서버 내부 저장 경로입니다.")
with st.sidebar.expander("저장 경로 보기", expanded=False):
    st.code(str(DATA_DIR), language="text")

st.sidebar.divider()

with st.sidebar.expander("📚 메뉴 인덱스 관리", expanded=False):
    new_item = st.text_input("추가할 메뉴명", value="", placeholder="예: 소고기무국")
    c1, c2 = st.columns(2)
    if c1.button("➕ 추가", use_container_width=True):
        v = (new_item or "").strip()
        if v:
            idx_df2 = idx_df.copy()
            if v not in idx_df2["name"].tolist():
                idx_df2 = pd.concat([idx_df2, pd.DataFrame([{"name": v}])], ignore_index=True)
                idx_df2["name"] = idx_df2["name"].astype(str)
                idx_df2 = idx_df2[idx_df2["name"].str.strip() != ""]
                idx_df2 = idx_df2.sort_values("name").reset_index(drop=True)
                _save_csv(idx_df2, MENU_INDEX_PATH)
                st.success("추가 완료")
                st.rerun()
        else:
            st.warning("메뉴명을 입력하세요.")
    if c2.button("🧹 공백정리", use_container_width=True):
        idx_df2 = idx_df.copy()
        idx_df2["name"] = idx_df2["name"].astype(str).str.strip()
        idx_df2 = idx_df2[idx_df2["name"] != ""].drop_duplicates().sort_values("name").reset_index(drop=True)
        _save_csv(idx_df2, MENU_INDEX_PATH)
        st.success("정리 완료")
        st.rerun()

    if menu_index_sorted:
        del_target = st.selectbox("삭제할 항목 선택", options=["(선택)"] + menu_index_sorted, index=0)
        if st.button("🗑️ 선택 항목 삭제", use_container_width=True):
            if del_target != "(선택)":
                idx_df2 = idx_df.copy()
                idx_df2 = idx_df2[idx_df2["name"].astype(str) != del_target].reset_index(drop=True)
                _save_csv(idx_df2, MENU_INDEX_PATH)
                st.success("삭제 완료")
                st.rerun()

# -----------------------------
# 메인 헤더
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")

# 공양게 영역 (있으면 표시)
c_left, c_right = st.columns([1.15, 1.0], vertical_alignment="center")
with c_left:
    if GONGYANG_IMG.exists():
        st.image(str(GONGYANG_IMG), use_container_width=True)
    else:
        st.caption("(gongyang_bowl.png 파일이 없으면 그림은 표시되지 않습니다.)")
with c_right:
    # 붓글씨 폰트는 사용자 PC/브라우저 환경에 따라 달라서,
    # 가능한 범위에서 가독성 좋게 표시
    st.markdown(
        f"""
        <div style="font-size:24px; line-height:1.45; font-weight:700;">
          {GONGYANG_TEXT.replace("\n","<br>")}
        </div>
        """,
        unsafe_allow_html=True
    )

st.divider()

# -----------------------------
# 달력 + 선택일 상태
# -----------------------------
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = _d2s(date(int(year), int(month), 1))

sel_date = _s2d(st.session_state["selected_date"])

weeks = _month_days(int(year), int(month))
weekdays = ["일", "월", "화", "수", "목", "금", "토"]

# 요일 헤더
hdr = st.columns(7)
for i, w in enumerate(weekdays):
    hdr[i].markdown(f"**{w}**")

def _cell_text(d: date) -> str:
    s = _d2s(d)
    lines = [f"{d.day:02d}({ _weekday_kr(d) })"]

    # 표시 규칙(간단하게): 배달불요 > 변경 > 기본(기본메뉴 있으면)
    if delivery_map.get(s, "") == "N":
        lines.append("🚫 배달불요")
    elif (change_map.get(s, "") or "").strip():
        lines.append("🔁 변경")
    elif (base_map.get(s, "") or "").strip():
        lines.append("• 기본")

    # 너무 길어지지 않게 메뉴명은 아래에 1줄만 (선택)
    cm = (change_map.get(s, "") or "").strip()
    bm = (base_map.get(s, "") or "").strip()
    show_menu = cm if cm else bm
    if show_menu:
        if len(show_menu) > 14:
            show_menu = show_menu[:14] + "…"
        lines.append(show_menu)

    return "\n".join(lines)

# 달력 본문
for week in weeks:
    cols = st.columns(7)
    for i, d in enumerate(week):
        in_month = (d.month == int(month))
        label = _cell_text(d) if in_month else ""
        key = f"cal_{d.isoformat()}"

        # 다른 달은 비활성 느낌으로 버튼 대신 빈칸
        if not in_month:
            cols[i].markdown("<div style='height:86px'></div>", unsafe_allow_html=True)
            continue

        # 선택일은 강조(버튼 라벨 앞에 ●)
        display_label = label
        if d == sel_date:
            display_label = "● " + label

        if cols[i].button(display_label, key=key):
            st.session_state["selected_date"] = _d2s(d)
            st.rerun()

st.divider()

# -----------------------------
# 선택일 편집
# -----------------------------
sel_s = st.session_state["selected_date"]
sel_d = _s2d(sel_s)

st.subheader(f"📌 선택 날짜: {sel_d.strftime('%Y-%m-%d')} ({_weekday_kr(sel_d)})")

# 현재 값
cur_base = (base_map.get(sel_s, "") or "").strip()
cur_change = (change_map.get(sel_s, "") or "").strip()
cur_delivery = (delivery_map.get(sel_s, "Y") or "Y").strip()

# 입력 UI
colA, colB, colC = st.columns([1.2, 1.2, 0.8], vertical_alignment="top")

with colA:
    st.markdown("**기본메뉴**")
    base_pick = st.selectbox(
        "인덱스에서 선택",
        options=["(직접입력)"] + menu_index_sorted,
        index=0,
        key="base_pick"
    )
    base_text = st.text_input("기본메뉴 직접 입력", value=cur_base, key="base_text")
    if base_pick != "(직접입력)":
        base_text = base_pick
        st.session_state["base_text"] = base_text

with colB:
    st.markdown("**변경메뉴**")
    change_pick = st.selectbox(
        "인덱스에서 선택",
        options=["(없음)"] + menu_index_sorted,
        index=0,
        key="change_pick"
    )
    change_text = st.text_input("변경메뉴 직접 입력", value=cur_change, key="change_text")
    if change_pick != "(없음)":
        change_text = change_pick
        st.session_state["change_text"] = change_text

with colC:
    st.markdown("**배달**")
    delivery_no = st.checkbox("배달 불요(🚫)", value=(cur_delivery == "N"), key="delivery_no")

btn1, btn2, btn3 = st.columns(3)

if btn1.button("💾 기본메뉴 저장", use_container_width=True):
    v = (st.session_state.get("base_text", "") or "").strip()
    base_df2 = base_df.copy()
    if v:
        base_df2 = _upsert(base_df2, "date", sel_s, "base_menu", v)
    else:
        base_df2 = _delete_key(base_df2, "date", sel_s)
    _save_csv(base_df2, BASE_MENU_PATH)
    st.success("기본메뉴 저장 완료")
    st.rerun()

if btn2.button("💾 변경메뉴 저장", use_container_width=True):
    v = (st.session_state.get("change_text", "") or "").strip()
    change_df2 = change_df.copy()
    if v:
        change_df2 = _upsert(change_df2, "date", sel_s, "change_menu", v)
    else:
        change_df2 = _delete_key(change_df2, "date", sel_s)
    _save_csv(change_df2, CHANGE_MENU_PATH)
    st.success("변경메뉴 저장 완료")
    st.rerun()

if btn3.button("💾 배달(불요) 저장", use_container_width=True):
    delivery_df2 = delivery_df.copy()
    v = "N" if st.session_state.get("delivery_no", False) else "Y"
    delivery_df2 = _upsert(delivery_df2, "date", sel_s, "delivery", v)
    _save_csv(delivery_df2, DELIVERY_PATH)
    st.success("배달 상태 저장 완료")
    st.rerun()

st.divider()

# -----------------------------
# 월별 문자 생성
# -----------------------------
st.subheader("📨 월별 안내문(복사해서 문자 전송)")

def _collect_month(year: int, month: int):
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return first, last

m_first, m_last = _collect_month(int(year), int(month))

# 해당 월 날짜만 모으기
def _in_month(s: str) -> bool:
    try:
        d = _s2d(s)
        return (d.year == int(year) and d.month == int(month))
    except Exception:
        return False

# 배달불요 목록
no_delivery_days = []
for s, v in delivery_map.items():
    if _in_month(s) and v == "N":
        no_delivery_days.append(_s2d(s))
no_delivery_days.sort()

# 변경메뉴 목록 (변경메뉴가 있는 날)
changed_days = []
for s, v in change_map.items():
    if _in_month(s) and str(v).strip():
        changed_days.append((_s2d(s), str(v).strip()))
changed_days.sort(key=lambda x: x[0])

# 안내문 포맷
lines = []
lines.append("동약협회입니다.")
lines.append(f"{int(year)}년 {int(month):02d}월 도시락 변경/배달불요 내역입니다.")

if no_delivery_days:
    lines.append("🚫【배달불요】")
    for d in no_delivery_days:
        lines.append(f"▶ {d.strftime('%m/%d')}({ _weekday_kr(d) }) : 배달불요")
else:
    lines.append("🚫【배달불요】")
    lines.append("▶ 없음")

if changed_days:
    lines.append("🔁【변경메뉴】")
    for d, cm in changed_days:
        bm = (base_map.get(_d2s(d), "") or "").strip()
        if bm:
            lines.append(f"▶ {d.strftime('%m/%d')}({ _weekday_kr(d) }) : {bm} → {cm}")
        else:
            lines.append(f"▶ {d.strftime('%m/%d')}({ _weekday_kr(d) }) : (기본미등록) → {cm}")
else:
    lines.append("🔁【변경메뉴】")
    lines.append("▶ 없음")

msg = "\n".join(lines)
st.text_area("복사용 متن", value=msg, height=260)

st.caption("※ 저장 후 달력 표시/문자 내역이 즉시 반영됩니다.")
