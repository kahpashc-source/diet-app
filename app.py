# app.py  (통째로 교체)
# - 그릇 그림: 너무 크지 않도록 160px 기본 + 화면 반응형
# - 메뉴 설정(인덱스): 사이드바 상단에 크게 고정 표시
# - 삭제 에러 방지 / 문자 출력 포맷 / 메뉴 인덱스 기능 유지

import calendar
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="식단 변경 프로그램", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BASE_CSV = DATA_DIR / "base_menu.csv"
CHANGE_CSV = DATA_DIR / "change_menu.csv"
DELIV_CSV = DATA_DIR / "delivery.csv"
MENU_CSV = DATA_DIR / "menu_index.csv"

BOWL_IMG_CANDIDATES = [
    Path("gongyang_bowl.png"),
    Path("images") / "gongyang_bowl.png",
]


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        return df[columns]
    return pd.DataFrame(columns=columns)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
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
    return df.loc[df["date"] != d].reset_index(drop=True)


def _fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _mmdd_weekday(d: date, weekday_names: list[str]) -> str:
    return f"{d.strftime('%m/%d')}({weekday_names[d.weekday()]})"


def _normalize_menu_text(s: str) -> str:
    return (s or "").strip()


GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


# 데이터 로드
base_df = _load_csv(BASE_CSV, ["date", "base_menu"])
change_df = _load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = _load_csv(DELIV_CSV, ["date", "delivery"])
menu_df = _load_csv(MENU_CSV, ["menu"])
menu_list = sorted({m.strip() for m in menu_df["menu"].tolist() if m.strip()})


# 상태 초기화
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)

st.session_state.setdefault("set_base_value", None)
st.session_state.setdefault("set_change_value", None)


# 스타일 (그림 크기/레이아웃 개선 + 사이드바 섹션 강조)
st.markdown(
    """
<style>
.block-container { padding-top: 0.9rem; }

.hero-card{
  background: rgba(0,0,0,0.03);
  border-radius: 18px;
  padding: 14px 16px;
}
.hero-grid{
  display: grid;
  grid-template-columns: 180px 1fr; /* ✅ 이미지 영역을 더 작게 */
  gap: 18px;
  align-items: center;
}
.hero-title{
  font-size: 18px;
  font-weight: 800;
  margin: 0 0 8px 0;
}
.hero-text{
  font-size: 22px;
  line-height: 1.45;
  white-space: pre-line;
  margin: 0;
  font-family: "궁서", "바탕", "Batang", "Apple SD Gothic Neo", "Malgun Gothic", serif;
}
@media (max-width: 860px){
  .hero-grid{ grid-template-columns: 1fr; }
}

/* ✅ 이미지 자체가 너무 커 보이지 않게 */
.bowl-img img{
  max-width: 160px !important;
  width: 160px !important;
  height: auto !important;
}

/* ✅ 사이드바 메뉴설정이 눈에 띄게 */
.sidebar-box{
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 14px;
  padding: 12px 12px;
  background: rgba(255,255,255,0.6);
}
.sidebar-title{
  font-size: 16px;
  font-weight: 800;
  margin-bottom: 6px;
}
.small-note{ font-size: 12px; opacity: 0.7; }
</style>
""",
    unsafe_allow_html=True,
)

# 그릇 이미지 찾기
img_path = None
for p in BOWL_IMG_CANDIDATES:
    if p.exists():
        img_path = p
        break


# -----------------------------
# 상단(그릇 + 공양게) : 이미지 작게
# -----------------------------
st.markdown('<div class="hero-card"><div class="hero-grid">', unsafe_allow_html=True)

st.markdown('<div class="bowl-img">', unsafe_allow_html=True)
if img_path:
    st.image(str(img_path))  # CSS가 크기 제한
else:
    st.warning("그릇 그림 파일이 없습니다. (gongyang_bowl.png 또는 images/gongyang_bowl.png 업로드 필요)")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f"""
<div>
  <div class="hero-title">공양게</div>
  <div class="hero-text">{GONGYANG_TEXT}</div>
  <div class="small-note">※ 그림은 작은 고정 크기로 표시됩니다.</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("</div></div>", unsafe_allow_html=True)
st.divider()


# -----------------------------
# ✅ 사이드바: 연/월 + 메뉴 설정(인덱스) — "반드시 보이게" 상단 고정
# -----------------------------
with st.sidebar:
    st.title("📅 설정")

    y = st.number_input("연도", min_value=2020, max_value=2100, value=int(st.session_state["year"]), step=1)
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1)
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.markdown("<div class='sidebar-box'>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-title'>🍽️ 메뉴 설정(인덱스)</div>", unsafe_allow_html=True)
    st.caption("메뉴를 관리하고(추가/수정/삭제) 아래 입력칸에 선택해서 넣습니다.")

    menu_search = st.text_input("메뉴 검색", value="", placeholder="예: 김치찌개")
    filtered = [x for x in menu_list if menu_search.strip() in x] if menu_search.strip() else menu_list
    st.write(f"현재 메뉴 수: **{len(menu_list)}**")

    # 추가
    st.markdown("**➕ 추가**")
    new_menu = st.text_input("추가할 메뉴", key="menu_add_text", placeholder="예: 뚝불고기")
    if st.button("추가", use_container_width=True, key="menu_add_btn"):
        nm = _normalize_menu_text(new_menu)
        if nm:
            if nm in menu_list:
                st.warning("이미 존재하는 메뉴입니다.")
            else:
                menu_list.append(nm)
                menu_list = sorted({x.strip() for x in menu_list if x.strip()})
                _save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
                st.success("추가 완료")
                st.rerun()
        else:
            st.warning("빈 값은 추가할 수 없습니다.")

    st.markdown("---")

    # 수정
    st.markdown("**✏️ 수정**")
    if menu_list:
        old = st.selectbox("수정할 메뉴", options=filtered if filtered else menu_list, key="menu_edit_select")
        edited = st.text_input("새 이름", key="menu_edit_text", value=old)
        if st.button("수정 저장", use_container_width=True, key="menu_edit_btn"):
            newv = _normalize_menu_text(edited)
            if not newv:
                st.warning("빈 값으로 바꿀 수 없습니다.")
            elif newv != old and newv in menu_list:
                st.warning("같은 이름의 메뉴가 이미 있습니다.")
            else:
                menu_list = [newv if x == old else x for x in menu_list]
                menu_list = sorted({x.strip() for x in menu_list if x.strip()})
                _save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
                st.success("수정 완료")
                st.rerun()
    else:
        st.info("메뉴가 없습니다. 먼저 추가하세요.")

    st.markdown("---")

    # 삭제
    st.markdown("**🗑️ 삭제**")
    if menu_list:
        dlt = st.selectbox("삭제할 메뉴", options=filtered if filtered else menu_list, key="menu_del_select")
        if st.button("삭제", use_container_width=True, key="menu_del_btn"):
            menu_list = [x for x in menu_list if x != dlt]
            _save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
            st.success("삭제 완료")
            st.rerun()
    else:
        st.info("삭제할 메뉴가 없습니다.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    st.caption("데이터 파일")
    st.write(f"- {BASE_CSV.as_posix()}")
    st.write(f"- {CHANGE_CSV.as_posix()}")
    st.write(f"- {DELIV_CSV.as_posix()}")
    st.write(f"- {MENU_CSV.as_posix()}")


# -----------------------------
# 달력
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])
weekday_names = ["월", "화", "수", "목", "금", "토", "일"]

st.title("🍱 식단 변경 프로그램")

cal = calendar.Calendar(firstweekday=0)
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

hdr = st.columns(7)
for i, wd in enumerate(weekday_names):
    hdr[i].markdown(f"**{wd}**")

for week_start in range(0, len(month_days), 7):
    row = month_days[week_start:week_start + 7]
    cols = st.columns(7)
    for i, d in enumerate(row):
        d_str = _fmt_date(d)
        base_v = _get_value(base_df, d_str, "base_menu").strip()
        chg_v = _get_value(change_df, d_str, "change_menu").strip()
        delv = _get_value(deliv_df, d_str, "delivery").strip()

        label = f"{d.day}"
        if delv == "SKIP":
            label += " 🚫"
        elif chg_v:
            label += " ✳️"
        elif base_v:
            label += " ✅"

        if cols[i].button(label, key=f"daybtn_{d_str}", use_container_width=True):
            st.session_state["selected_day"] = d.day

st.divider()


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
st.subheader(f"선택한 날짜: {selected_str} ({weekday_names[selected_date.weekday()]})")


# 위젯 key
base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"

# ✅ 위젯 생성 전 상태 조정(삭제/선택 반영)
if st.session_state.get("clear_base_input", False):
    st.session_state[base_text_key] = ""
    st.session_state["clear_base_input"] = False
if st.session_state.get("clear_change_input", False):
    st.session_state[change_text_key] = ""
    st.session_state["clear_change_input"] = False

if st.session_state.get("set_base_value") is not None:
    st.session_state[base_text_key] = st.session_state["set_base_value"]
    st.session_state["set_base_value"] = None
if st.session_state.get("set_change_value") is not None:
    st.session_state[change_text_key] = st.session_state["set_change_value"]
    st.session_state["set_change_value"] = None

# 초기값(키 없을 때만)
cur_base = _get_value(base_df, selected_str, "base_menu")
cur_change = _get_value(change_df, selected_str, "change_menu")
cur_deliv = _get_value(deliv_df, selected_str, "delivery")

if base_text_key not in st.session_state:
    st.session_state[base_text_key] = cur_base
if change_text_key not in st.session_state:
    st.session_state[change_text_key] = cur_change
if delivery_key not in st.session_state:
    st.session_state[delivery_key] = ("배달 불요" if cur_deliv == "SKIP" else "배달")


# 콜백
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
    st.toast("배달 상태 초기화", icon="🧹")
    st.rerun()


def apply_base_from_menu(choice: str):
    st.session_state["set_base_value"] = choice
    st.rerun()


def apply_change_from_menu(choice: str):
    st.session_state["set_change_value"] = choice
    st.rerun()


def build_month_sms(year_: int, month_: int) -> str:
    last_ = calendar.monthrange(year_, month_)[1]
    start = date(year_, month_, 1)
    end = date(year_, month_, last_)
    all_days = [d.date() for d in pd.date_range(start, end, freq="D")]

    skip_lines = []
    change_lines = []

    for d in all_days:
        d_str = _fmt_date(d)
        deliv_val = _get_value(deliv_df, d_str, "delivery").strip()
        base_v = _get_value(base_df, d_str, "base_menu").strip()
        chg_v = _get_value(change_df, d_str, "change_menu").strip()

        if deliv_val == "SKIP":
            skip_lines.append(f"▶ {_mmdd_weekday(d, weekday_names)} : 배달불요")
            continue

        if chg_v:
            left = base_v if base_v else "-"
            change_lines.append(f"▶ {_mmdd_weekday(d, weekday_names)} : {left} → {chg_v}")

    lines = [
        "동약협회입니다.",
        f"{year_}년 {month_:02d}월 도시락 변경/배달불요 내역입니다.",
        "🚫【배달불요】",
        *skip_lines,
        "🔁【변경메뉴】",
        *change_lines,
        "감사합니다.",
    ]
    return "\n".join(lines)


# 화면
left, right = st.columns([1.2, 1])

with left:
    st.markdown("### 기본메뉴")
    if menu_list:
        pick = st.selectbox("메뉴 선택(기본메뉴)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_base_{selected_str}")
        if pick != "(선택 안함)":
            st.button("선택한 메뉴를 기본메뉴 입력칸에 넣기", use_container_width=True, on_click=apply_base_from_menu, args=(pick,))
    st.text_input("기본메뉴 입력", key=base_text_key)
    c1, c2 = st.columns(2)
    c1.button("기본메뉴 저장", use_container_width=True, on_click=save_base)
    c2.button("기본메뉴 삭제", use_container_width=True, on_click=delete_base)

    st.markdown("### 변경메뉴")
    if menu_list:
        pick2 = st.selectbox("메뉴 선택(변경메뉴)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_change_{selected_str}")
        if pick2 != "(선택 안함)":
            st.button("선택한 메뉴를 변경메뉴 입력칸에 넣기", use_container_width=True, on_click=apply_change_from_menu, args=(pick2,))
    st.text_input("변경메뉴 입력", key=change_text_key)
    c3, c4 = st.columns(2)
    c3.button("변경메뉴 저장", use_container_width=True, on_click=save_change)
    c4.button("변경메뉴 삭제", use_container_width=True, on_click=delete_change)

    st.markdown("### 배달 상태")
    st.radio("배달/배달불요", ["배달", "배달 불요"], horizontal=True, key=delivery_key)
    c5, c6 = st.columns(2)
    c5.button("배달 상태 저장", use_container_width=True, on_click=save_delivery)
    c6.button("배달 상태 초기화", use_container_width=True, on_click=clear_delivery)

with right:
    st.markdown("### 📩 월간 문자 출력")
    st.text_area("복사해서 문자로 보내기", value=build_month_sms(year, month), height=380)
