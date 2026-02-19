import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

BASE_CSV = DATA_DIR / "base_menu.csv"
CHANGE_CSV = DATA_DIR / "change_menu.csv"
DELIV_CSV = DATA_DIR / "delivery.csv"
MENU_CSV = DATA_DIR / "menu_index.csv"

BOWL_IMG_CANDIDATES = [Path("gongyang_bowl.png"), Path("images") / "gongyang_bowl.png"]

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

GONGYANG_TEXT_4LINES = [
    "이 음식이 어디에서 왔는가",
    "내 덕행으로는 받기가 부끄럽네",
    "마음의 온갖 탐욕을 떠나",
    "바른 생각으로 이 공양을 받습니다",
]


# -----------------------------
# utils
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


# -----------------------------
# load data
# -----------------------------
base_df = load_csv(BASE_CSV, ["date", "base_menu"])
change_df = load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = load_csv(DELIV_CSV, ["date", "delivery"])

menu_df = load_csv(MENU_CSV, ["menu"])
menu_list = sorted({m.strip() for m in menu_df["menu"].tolist() if m.strip()})


# -----------------------------
# state init
# -----------------------------
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

# 삭제 후 입력칸 비우기 플래그(위젯 key 직접 수정 금지)
st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)

# 메뉴 선택(선택 즉시 입력 반영)
st.session_state.setdefault("auto_fill_base", False)
st.session_state.setdefault("auto_fill_change", False)


# -----------------------------
# styles
# -----------------------------
st.markdown(
    """
<style>
.block-container { padding-top: 0.6rem; padding-bottom: 0.6rem; }
.main-title { font-size: 30px; font-weight: 900; margin: 0 0 10px 0; }

/* 헤더: 좌 그림, 우 글귀 4줄 */
.hero {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 18px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(0,0,0,0.03);
}
.hero-right {
  display: grid;
  grid-template-rows: repeat(4, 1fr);
  row-gap: 4px;
  height: 140px; /* 그릇 높이(대략)에 맞춰 정렬 */
}
.hero-line {
  font-family: "궁서", "바탕", "Batang", "Apple SD Gothic Neo", "Malgun Gothic", serif;
  font-size: 24px;
  line-height: 1.15;
}
@media (max-width: 860px){
  .hero { grid-template-columns: 1fr; }
  .hero-right { height: auto; }
  .hero-line { font-size: 22px; }
}

/* 달력 */
.week { text-align:center; font-weight: 800; padding: 4px 0; }
.cell {
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 12px;
  padding: 6px;
  min-height: 96px;
  background: rgba(255,255,255,0.68);
}
.smallbtn button {
  padding: 0.12rem 0.35rem !important;
  min-height: 30px !important;
  font-weight: 800 !important;
}
.lines { margin-top: 4px; font-size: 12px; line-height: 1.15; opacity: 0.9; }
.lines div { margin: 2px 0; }

/* 입력 섹션: 여백 줄여 동선 최소화 */
.section { padding: 8px 10px; border: 1px solid rgba(0,0,0,0.10); border-radius: 14px; background: rgba(0,0,0,0.02); }
.section h3 { margin: 4px 0 6px 0; }
</style>
""",
    unsafe_allow_html=True,
)

# bowl image
img_path = None
for p in BOWL_IMG_CANDIDATES:
    if p.exists():
        img_path = p
        break


# -----------------------------
# header
# -----------------------------
st.markdown('<div class="main-title">🍱 맘스락 식단 변경 프로그램</div>', unsafe_allow_html=True)

st.markdown('<div class="hero">', unsafe_allow_html=True)
if img_path:
    st.image(str(img_path), width=150)
else:
    st.caption("⚠️ gongyang_bowl.png 없음")

st.markdown('<div class="hero-right">', unsafe_allow_html=True)
for ln in GONGYANG_TEXT_4LINES:
    st.markdown(f'<div class="hero-line">{ln}</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
st.divider()


# -----------------------------
# sidebar: year/month + menu index
# -----------------------------
with st.sidebar:
    st.title("📅 설정")
    y = st.number_input("연도", 2020, 2100, int(st.session_state["year"]), 1, key="year_input")
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1, key="month_select")
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.divider()
    st.subheader("🍽️ 메뉴 설정(인덱스)")
    st.caption("메뉴 추가/수정/삭제 후 본문에서 선택해 입력칸에 바로 넣습니다.")
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

    if menu_list:
        old = st.selectbox("✏️ 수정할 메뉴", options=menu_list, key="menu_edit_select")
        edited = st.text_input("새 이름", value=old, key="menu_edit_input")
        if st.button("수정 저장", use_container_width=True, key="menu_edit_btn"):
            nv = norm(edited)
            if not nv:
                st.warning("빈 값으로 바꿀 수 없습니다.")
            elif nv != old and nv in menu_list:
                st.warning("같은 이름이 이미 있습니다.")
            else:
                menu_list = [nv if x == old else x for x in menu_list]
                menu_list = sorted({x.strip() for x in menu_list if x.strip()})
                save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
                st.success("수정 완료")
                st.rerun()

        dlt = st.selectbox("🗑️ 삭제할 메뉴", options=menu_list, key="menu_del_select")
        if st.button("삭제", use_container_width=True, key="menu_del_btn"):
            menu_list = [x for x in menu_list if x != dlt]
            save_csv(pd.DataFrame({"menu": menu_list}), MENU_CSV)
            st.success("삭제 완료")
            st.rerun()


# -----------------------------
# calendar (cells show content)
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])

cal = calendar.Calendar(firstweekday=0)
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

hdr = st.columns(7)
for i, wd in enumerate(WEEKDAY_NAMES):
    hdr[i].markdown(f'<div class="week">{wd}</div>', unsafe_allow_html=True)

for week_start in range(0, len(month_days), 7):
    row = month_days[week_start : week_start + 7]
    cols = st.columns(7)

    for i, d in enumerate(row):
        d_str = fmt_date(d)
        base_v = norm(get_value(base_df, d_str, "base_menu"))
        chg_v = norm(get_value(change_df, d_str, "change_menu"))
        delv = norm(get_value(deliv_df, d_str, "delivery"))

        with cols[i]:
            st.markdown('<div class="cell">', unsafe_allow_html=True)
            st.markdown('<div class="smallbtn">', unsafe_allow_html=True)
            if st.button(f"{d.day}", key=f"daybtn_{d_str}", use_container_width=True):
                st.session_state["selected_day"] = d.day
            st.markdown("</div>", unsafe_allow_html=True)

            lines = []
            if delv == "SKIP":
                lines.append("🚫 배달불요")
            else:
                if chg_v:
                    lines.append(f"🔁 {short(chg_v, 12)}")
                if base_v:
                    lines.append(f"🍱 {short(base_v, 12)}")
            if not lines:
                lines = [""]

            st.markdown('<div class="lines">' + "".join(f"<div>{x}</div>" for x in lines) + "</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

st.divider()


# -----------------------------
# selected date + editor
# -----------------------------
selected_day = int(st.session_state["selected_day"])
last_day = calendar.monthrange(year, month)[1]
if selected_day > last_day:
    selected_day = last_day
    st.session_state["selected_day"] = selected_day

selected_date = date(year, month, selected_day)
selected_str = fmt_date(selected_date)

base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"

# ✅ 위젯 생성 전: 삭제 플래그 반영
if st.session_state.get("clear_base_input"):
    st.session_state[base_text_key] = ""
    st.session_state["clear_base_input"] = False
if st.session_state.get("clear_change_input"):
    st.session_state[change_text_key] = ""
    st.session_state["clear_change_input"] = False

# 초기값(키 없을 때만)
if base_text_key not in st.session_state:
    st.session_state[base_text_key] = get_value(base_df, selected_str, "base_menu")
if change_text_key not in st.session_state:
    st.session_state[change_text_key] = get_value(change_df, selected_str, "change_menu")
if delivery_key not in st.session_state:
    st.session_state[delivery_key] = ("배달 불요" if get_value(deliv_df, selected_str, "delivery") == "SKIP" else "배달")


# callbacks
def save_base():
    global base_df
    val = norm(st.session_state.get(base_text_key, ""))
    base_df = upsert(base_df, selected_str, "base_menu", val)
    save_csv(base_df, BASE_CSV)
    st.toast("기본메뉴 저장", icon="✅")


def delete_base():
    global base_df
    base_df = delete_row(base_df, selected_str)
    save_csv(base_df, BASE_CSV)
    st.session_state["clear_base_input"] = True
    st.rerun()


def save_change():
    global change_df
    val = norm(st.session_state.get(change_text_key, ""))
    change_df = upsert(change_df, selected_str, "change_menu", val)
    save_csv(change_df, CHANGE_CSV)
    st.toast("변경메뉴 저장", icon="✅")


def delete_change():
    global change_df
    change_df = delete_row(change_df, selected_str)
    save_csv(change_df, CHANGE_CSV)
    st.session_state["clear_change_input"] = True
    st.rerun()


def save_delivery():
    global deliv_df
    choice = st.session_state.get(delivery_key, "배달")
    val = "SKIP" if choice == "배달 불요" else "DELIVER"
    deliv_df = upsert(deliv_df, selected_str, "delivery", val)
    save_csv(deliv_df, DELIV_CSV)
    st.toast("배달 상태 저장", icon="✅")


def clear_delivery():
    global deliv_df
    deliv_df = delete_row(deliv_df, selected_str)
    save_csv(deliv_df, DELIV_CSV)
    st.session_state[delivery_key] = "배달"
    st.toast("배달 초기화", icon="🧹")
    st.rerun()


def on_pick_base():
    # ✅ 선택 즉시 입력 반영 (버튼 없음 → 동선 최소화)
    pick = st.session_state.get(f"pick_base_{selected_str}", "(선택 안함)")
    if pick != "(선택 안함)":
        st.session_state[base_text_key] = pick


def on_pick_change():
    pick = st.session_state.get(f"pick_change_{selected_str}", "(선택 안함)")
    if pick != "(선택 안함)":
        st.session_state[change_text_key] = pick


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

    out = []
    out.append("동약협회입니다.")
    out.append(f"{year_}년 {month_:02d}월 도시락 변경/배달불요 내역입니다.")
    out.append("🚫【배달불요】")
    if skip_lines:
        out.extend(skip_lines)
    out.append("🔁【변경메뉴】")
    if change_lines:
        out.extend(change_lines)
    out.append("감사합니다.")
    return "\n".join(out)


st.subheader(f"선택한 날짜: {selected_str} ({WEEKDAY_NAMES[selected_date.weekday()]})")

left, right = st.columns([1.15, 1])

with left:
    st.markdown('<div class="section">', unsafe_allow_html=True)

    st.markdown("### 기본메뉴")
    if menu_list:
        st.selectbox(
            "메뉴 인덱스에서 선택(기본)",
            ["(선택 안함)"] + menu_list,
            index=0,
            key=f"pick_base_{selected_str}",
            on_change=on_pick_base,
        )
    st.text_input("기본메뉴 입력", key=base_text_key)
    a, b = st.columns(2)
    a.button("저장", use_container_width=True, on_click=save_base, key=f"btn_save_base_{selected_str}")
    b.button("삭제", use_container_width=True, on_click=delete_base, key=f"btn_del_base_{selected_str}")

    st.markdown("### 변경메뉴")
    if menu_list:
        st.selectbox(
            "메뉴 인덱스에서 선택(변경)",
            ["(선택 안함)"] + menu_list,
            index=0,
            key=f"pick_change_{selected_str}",
            on_change=on_pick_change,
        )
    st.text_input("변경메뉴 입력", key=change_text_key)
    c, d = st.columns(2)
    c.button("저장", use_container_width=True, on_click=save_change, key=f"btn_save_change_{selected_str}")
    d.button("삭제", use_container_width=True, on_click=delete_change, key=f"btn_del_change_{selected_str}")

    st.markdown("### 배달 상태")
    st.radio("배달/배달불요", ["배달", "배달 불요"], horizontal=True, key=delivery_key)
    e, f = st.columns(2)
    e.button("저장", use_container_width=True, on_click=save_delivery, key=f"btn_save_deliv_{selected_str}")
    f.button("초기화", use_container_width=True, on_click=clear_delivery, key=f"btn_clear_deliv_{selected_str}")

    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("### 📩 월간 문자 출력")
    st.text_area("복사해서 문자로 보내기", value=build_month_sms(year, month), height=420, key=f"sms_{year}_{month}")
