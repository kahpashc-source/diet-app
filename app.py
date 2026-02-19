# app.py  (통째로 교체)
# (1) 삭제 에러 방지: 삭제 콜백에서 위젯 key 직접 수정 금지 → clear 플래그 + rerun
# (2) 그릇그림: 아주 작게(오른쪽 위)
# (3) 달력 날짜칸 안에 기본/변경/배달 상태를 직접 표시
# (4) 문자 출력 포맷: 부회장님 예시 그대로
# (5) 메뉴 설정(인덱스): 사이드바에서 관리 + 선택하여 입력칸에 채우기

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

GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


# -----------------------------
# utils
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


def _mmdd_weekday(d: date) -> str:
    return f"{d.strftime('%m/%d')}({WEEKDAY_NAMES[d.weekday()]})"


def _norm(s: str) -> str:
    return (s or "").strip()


def _short(s: str, n: int = 10) -> str:
    s = _norm(s)
    if not s:
        return ""
    return s if len(s) <= n else (s[: n - 1] + "…")


# -----------------------------
# load data
# -----------------------------
base_df = _load_csv(BASE_CSV, ["date", "base_menu"])
change_df = _load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = _load_csv(DELIV_CSV, ["date", "delivery"])
menu_df = _load_csv(MENU_CSV, ["menu"])
menu_list = sorted({m.strip() for m in menu_df["menu"].tolist() if m.strip()})


# -----------------------------
# session state init
# -----------------------------
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

# 삭제 후 입력칸 비우기 플래그
st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)

# 메뉴 선택으로 입력칸 채우기 플래그(위젯 생성 전 적용)
st.session_state.setdefault("set_base_value", None)
st.session_state.setdefault("set_change_value", None)


# -----------------------------
# styles
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 0.8rem; }

.header-wrap{
  display:flex; align-items:flex-start; justify-content:space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(0,0,0,0.03);
}
.header-title{
  font-size: 26px;
  font-weight: 800;
  margin: 0 0 6px 0;
}
.header-sub{
  white-space: pre-line;
  font-size: 20px;
  line-height: 1.45;
  margin: 0;
  font-family: "궁서", "바탕", "Batang", "Apple SD Gothic Neo", "Malgun Gothic", serif;
}
.header-img img{
  width: 80px !important;
  max-width: 80px !important;
  height: auto !important;
  opacity: 0.95;
}

.cal-cell{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 12px;
  padding: 8px 8px 10px 8px;
  min-height: 108px;
  background: rgba(255,255,255,0.6);
}
.cal-lines{
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.2;
  opacity: 0.85;
}
.cal-lines div{ margin: 2px 0; }
.dim { opacity: 0.45; }

.sidebar-box{
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255,255,255,0.6);
}
.sidebar-title{
  font-size: 16px;
  font-weight: 900;
  margin-bottom: 6px;
}
</style>
""",
    unsafe_allow_html=True,
)

# bowl image path
img_path = None
for p in BOWL_IMG_CANDIDATES:
    if p.exists():
        img_path = p
        break


# -----------------------------
# header: small bowl on right
# -----------------------------
st.markdown('<div class="header-wrap">', unsafe_allow_html=True)
st.markdown(
    f"""
<div>
  <div class="header-title">🍱 식단변경프로그램</div>
  <div class="header-sub">{GONGYANG_TEXT}</div>
</div>
""",
    unsafe_allow_html=True,
)
st.markdown('<div class="header-img">', unsafe_allow_html=True)
if img_path:
    st.image(str(img_path))
else:
    st.caption("⚠️ gongyang_bowl.png 없음")
st.markdown("</div></div>", unsafe_allow_html=True)

st.divider()


# -----------------------------
# sidebar: year/month + menu index
# -----------------------------
with st.sidebar:
    st.title("📅 설정")
    y = st.number_input("연도", min_value=2020, max_value=2100, value=int(st.session_state["year"]), step=1)
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1)
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.markdown("<div class='sidebar-box'>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-title'>🍽️ 메뉴 설정(인덱스)</div>", unsafe_allow_html=True)
    st.caption("메뉴 목록을 관리(추가/수정/삭제)하면 본문에서 선택해 입력칸에 넣을 수 있습니다.")

    menu_search = st.text_input("메뉴 검색", value="", placeholder="예: 김치찌개")
    filtered = [x for x in menu_list if menu_search.strip() in x] if menu_search.strip() else menu_list
    st.write(f"현재 메뉴 수: **{len(menu_list)}**")

    st.markdown("**➕ 추가**")
    new_menu = st.text_input("추가할 메뉴", key="menu_add_text", placeholder="예: 뚝불고기")
    if st.button("추가", use_container_width=True, key="menu_add_btn"):
        nm = _norm(new_menu)
        if not nm:
            st.warning("빈 값은 추가할 수 없습니다.")
        elif nm in menu_list:
            st.warning("이미 존재하는 메뉴입니다.")
        else:
            menu_list = sorted(set(menu_list + [nm]))
            _save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
            st.success("추가 완료")
            st.rerun()

    st.markdown("---")
    st.markdown("**✏️ 수정**")
    if menu_list:
        old = st.selectbox("수정할 메뉴", options=(filtered if filtered else menu_list), key="menu_edit_select")
        edited = st.text_input("새 이름", key="menu_edit_text", value=old)
        if st.button("수정 저장", use_container_width=True, key="menu_edit_btn"):
            newv = _norm(edited)
            if not newv:
                st.warning("빈 값으로 바꿀 수 없습니다.")
            elif newv != old and newv in menu_list:
                st.warning("같은 이름이 이미 있습니다.")
            else:
                menu_list = [newv if x == old else x for x in menu_list]
                menu_list = sorted({x.strip() for x in menu_list if x.strip()})
                _save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
                st.success("수정 완료")
                st.rerun()
    else:
        st.info("메뉴가 없습니다. 먼저 추가하세요.")

    st.markdown("---")
    st.markdown("**🗑️ 삭제**")
    if menu_list:
        dlt = st.selectbox("삭제할 메뉴", options=(filtered if filtered else menu_list), key="menu_del_select")
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
# calendar (with content in cells)
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])

cal = calendar.Calendar(firstweekday=0)
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

# weekday header
hdr = st.columns(7)
for i, wd in enumerate(WEEKDAY_NAMES):
    hdr[i].markdown(f"**{wd}**")

for week_start in range(0, len(month_days), 7):
    row = month_days[week_start: week_start + 7]
    cols = st.columns(7)

    for i, d in enumerate(row):
        d_str = _fmt_date(d)
        base_v = _norm(_get_value(base_df, d_str, "base_menu"))
        chg_v = _norm(_get_value(change_df, d_str, "change_menu"))
        delv = _norm(_get_value(deliv_df, d_str, "delivery"))

        # cell box
        with cols[i]:
            st.markdown('<div class="cal-cell">', unsafe_allow_html=True)

            # day select button
            if st.button(f"{d.day}", key=f"daybtn_{d_str}", use_container_width=True):
                st.session_state["selected_day"] = d.day

            # lines inside the cell
            lines = []

            if delv == "SKIP":
                lines.append("🚫 배달불요")
            else:
                # 변경이 있으면 먼저 보여주고
                if chg_v:
                    lines.append(f"🔁 {_short(chg_v, 11)}")
                if base_v:
                    lines.append(f"🍱 {_short(base_v, 11)}")

            if not lines:
                lines.append('<span class="dim"> </span>')

            st.markdown('<div class="cal-lines">' + "".join([f"<div>{x}</div>" for x in lines]) + "</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

st.divider()


# -----------------------------
# selected date section
# -----------------------------
selected_day = int(st.session_state["selected_day"])
last_day = calendar.monthrange(year, month)[1]
if selected_day > last_day:
    selected_day = last_day
    st.session_state["selected_day"] = selected_day

selected_date = date(year, month, selected_day)
selected_str = _fmt_date(selected_date)

st.subheader(f"선택한 날짜: {selected_str} ({WEEKDAY_NAMES[selected_date.weekday()]})")

base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"

# ✅ apply flags BEFORE widgets
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

# init values only when key missing
cur_base = _get_value(base_df, selected_str, "base_menu")
cur_change = _get_value(change_df, selected_str, "change_menu")
cur_deliv = _get_value(deliv_df, selected_str, "delivery")

if base_text_key not in st.session_state:
    st.session_state[base_text_key] = cur_base
if change_text_key not in st.session_state:
    st.session_state[change_text_key] = cur_change
if delivery_key not in st.session_state:
    st.session_state[delivery_key] = ("배달 불요" if cur_deliv == "SKIP" else "배달")


# callbacks
def save_base():
    global base_df
    val = _norm(st.session_state.get(base_text_key, ""))
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
    val = _norm(st.session_state.get(change_text_key, ""))
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
        deliv_val = _norm(_get_value(deliv_df, d_str, "delivery"))
        base_v = _norm(_get_value(base_df, d_str, "base_menu"))
        chg_v = _norm(_get_value(change_df, d_str, "change_menu"))

        if deliv_val == "SKIP":
            skip_lines.append(f"▶ {_mmdd_weekday(d)} : 배달불요")
            continue

        if chg_v:
            left = base_v if base_v else "-"
            change_lines.append(f"▶ {_mmdd_weekday(d)} : {left} → {chg_v}")

    lines = []
    lines.append("동약협회입니다.")
    lines.append(f"{year_}년 {month_:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("🚫【배달불요】")
    if skip_lines:
        lines.extend(skip_lines)
    lines.append("🔁【변경메뉴】")
    if change_lines:
        lines.extend(change_lines)
    lines.append("감사합니다.")
    return "\n".join(lines)


# -----------------------------
# editor + sms
# -----------------------------
left, right = st.columns([1.15, 1])

with left:
    st.markdown("### 기본메뉴")
    if menu_list:
        pick = st.selectbox("메뉴 선택(기본)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_base_{selected_str}")
        if pick != "(선택 안함)":
            st.button("선택한 메뉴를 기본메뉴 입력칸에 넣기", use_container_width=True, on_click=apply_base_from_menu, args=(pick,))
    st.text_input("기본메뉴 입력", key=base_text_key)
    a, b = st.columns(2)
    a.button("기본메뉴 저장", use_container_width=True, on_click=save_base)
    b.button("기본메뉴 삭제", use_container_width=True, on_click=delete_base)

    st.markdown("### 변경메뉴")
    if menu_list:
        pick2 = st.selectbox("메뉴 선택(변경)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_change_{selected_str}")
        if pick2 != "(선택 안함)":
            st.button("선택한 메뉴를 변경메뉴 입력칸에 넣기", use_container_width=True, on_click=apply_change_from_menu, args=(pick2,))
    st.text_input("변경메뉴 입력", key=change_text_key)
    c, d = st.columns(2)
    c.button("변경메뉴 저장", use_container_width=True, on_click=save_change)
    d.button("변경메뉴 삭제", use_container_width=True, on_click=delete_change)

    st.markdown("### 배달 상태")
    st.radio("배달/배달불요", ["배달", "배달 불요"], horizontal=True, key=delivery_key)
    e, f = st.columns(2)
    e.button("배달 상태 저장", use_container_width=True, on_click=save_delivery)
    f.button("배달 상태 초기화", use_container_width=True, on_click=clear_delivery)

with right:
    st.markdown("### 📩 월간 문자 출력")
    st.text_area("복사해서 문자로 보내기", value=build_month_sms(year, month), height=420)
