# app.py  (통째로 교체)
# 요구사항 반영:
# 1) 대제목: "🍱 맘스락 식단 변경 프로그램"
# 2) 그 아래: 좌측(그릇 그림, 과하지 않게), 우측(글귀, 붓글씨 느낌)
#    - 네트워크 차단 시에도 “망가지지 않게” 폴백 폰트(궁서/바탕) 적용
# 3) 달력: 불필요한 여백 최소화 + 날짜칸 안에 기본/변경/배달불요 내용 표시
#    - 날짜 버튼 크기/여백 축소, 셀 높이 축소, 글자수 자동 줄임
# 4) 삭제 에러 방지 유지(플래그 + rerun)
# 5) 메뉴설정(인덱스) 사이드바 유지 + 본문에서 선택하여 입력칸 채우기
# 6) 문자 출력 포맷: 사용자가 준 예시 그대로

import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

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

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

GONGYANG_TEXT = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


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


def _short(s: str, n: int) -> str:
    s = _norm(s)
    if not s:
        return ""
    return s if len(s) <= n else (s[: n - 1] + "…")


# -----------------------------
# 데이터 로드
# -----------------------------
base_df = _load_csv(BASE_CSV, ["date", "base_menu"])
change_df = _load_csv(CHANGE_CSV, ["date", "change_menu"])
deliv_df = _load_csv(DELIV_CSV, ["date", "delivery"])
menu_df = _load_csv(MENU_CSV, ["menu"])
menu_list = sorted({m.strip() for m in menu_df["menu"].tolist() if m.strip()})


# -----------------------------
# 상태 초기화
# -----------------------------
today = date.today()
st.session_state.setdefault("year", today.year)
st.session_state.setdefault("month", today.month)
st.session_state.setdefault("selected_day", today.day)

# 삭제 후 입력칸 비우기(위젯 key 직접 수정 금지 → 플래그)
st.session_state.setdefault("clear_base_input", False)
st.session_state.setdefault("clear_change_input", False)

# 메뉴 선택 → 입력칸 채움(위젯 생성 전 적용)
st.session_state.setdefault("set_base_value", None)
st.session_state.setdefault("set_change_value", None)


# -----------------------------
# 스타일: 여백 최소화 + 달력 셀 압축 + 붓글씨 느낌
# -----------------------------
# (네트워크 차단 시에도 폴백 폰트로 "망가지지 않게" 구성)
CALLI_FONT = "Nanum Pen Script"  # 가능하면 사용, 안되면 폴백

st.markdown(
    f"""
<link href="https://fonts.googleapis.com/css2?family={CALLI_FONT.replace(' ', '+')}&display=swap" rel="stylesheet">
<style>
/* 전체 여백 줄이기 */
.block-container {{
  padding-top: 0.6rem !important;
  padding-bottom: 0.6rem !important;
}}
div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMarkdownContainer"]) {{
  margin-bottom: 0.2rem;
}}

/* 대제목 */
.main-title {{
  font-size: 30px;
  font-weight: 900;
  margin: 0 0 8px 0;
}}

/* 헤더(그림+글귀) */
.hero {{
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 14px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(0,0,0,0.03);
  margin-bottom: 10px;
}}
.hero-img img {{
  width: 135px !important;
  max-width: 135px !important;
  height: auto !important;
  opacity: 0.96;
}}
.gongyang {{
  font-family: "{CALLI_FONT}", "궁서", "바탕", "Batang", "Apple SD Gothic Neo", "Malgun Gothic", serif;
  font-size: 26px;
  line-height: 1.35;
  white-space: pre-line;
  margin: 0;
}}
@media (max-width: 860px){{
  .hero{{ grid-template-columns: 1fr; }}
  .hero-img img{{ width: 120px !important; max-width:120px !important; }}
  .gongyang{{ font-size: 24px; }}
}}

/* 달력 헤더(요일) */
.week-hdr {{
  text-align:center;
  font-weight: 800;
  padding: 4px 0;
}}

/* 달력 셀: 여백/높이 최소화 */
.cal-cell {{
  border: 1px solid rgba(0,0,0,0.10);
  border-radius: 12px;
  padding: 6px 6px 8px 6px;
  min-height: 96px;            /* ✅ 불필요한 높이 줄임 */
  background: rgba(255,255,255,0.62);
}}
.cal-daybtn button {{
  padding: 0.15rem 0.35rem !important; /* ✅ 버튼 여백 축소 */
  min-height: 32px !important;
  font-weight: 800 !important;
}}
.cal-lines {{
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.15;
  opacity: 0.88;
}}
.cal-lines div {{ margin: 2px 0; }}
.dim {{ opacity: 0.40; }}

/* 본문 입력 섹션 간격 압축 */
.section-title {{
  font-size: 18px;
  font-weight: 900;
  margin: 6px 0 6px 0;
}}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# 그릇 이미지 찾기
# -----------------------------
img_path = None
for p in BOWL_IMG_CANDIDATES:
    if p.exists():
        img_path = p
        break


# -----------------------------
# 상단: 대제목 + (좌 그림/우 글귀)
# -----------------------------
st.markdown('<div class="main-title">🍱 맘스락 식단 변경 프로그램</div>', unsafe_allow_html=True)

st.markdown('<div class="hero">', unsafe_allow_html=True)
st.markdown('<div class="hero-img">', unsafe_allow_html=True)
if img_path:
    st.image(str(img_path))
else:
    st.caption("⚠️ gongyang_bowl.png 없음 (루트 또는 images/ 폴더에 업로드)")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(f'<div class="gongyang">{GONGYANG_TEXT}</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.divider()


# -----------------------------
# 사이드바: 연/월 + 메뉴설정(인덱스)
# -----------------------------
with st.sidebar:
    st.title("📅 설정")
    y = st.number_input("연도", min_value=2020, max_value=2100, value=int(st.session_state["year"]), step=1)
    m = st.selectbox("월", list(range(1, 13)), index=int(st.session_state["month"]) - 1)
    st.session_state["year"] = int(y)
    st.session_state["month"] = int(m)

    st.markdown("### 🍽️ 메뉴 설정(인덱스)")
    st.caption("메뉴 목록을 관리하면 본문에서 선택해 입력칸에 넣을 수 있습니다.")

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


# -----------------------------
# 달력(셀 안에 내용 표시) — 동선 최소화
# -----------------------------
year = int(st.session_state["year"])
month = int(st.session_state["month"])

cal = calendar.Calendar(firstweekday=0)
month_days = [d for d in cal.itermonthdates(year, month) if d.month == month]

# 요일 헤더
hdr = st.columns(7)
for i, wd in enumerate(WEEKDAY_NAMES):
    hdr[i].markdown(f'<div class="week-hdr">{wd}</div>', unsafe_allow_html=True)

# 달력 본문 (날짜칸에 내용 표시)
# - 변경메뉴/기본메뉴는 짧게 줄여서 최대 2줄 표시
# - 배달불요면 1줄로 강하게 표시
for week_start in range(0, len(month_days), 7):
    row = month_days[week_start: week_start + 7]
    cols = st.columns(7)

    for i, d in enumerate(row):
        d_str = _fmt_date(d)
        base_v = _norm(_get_value(base_df, d_str, "base_menu"))
        chg_v = _norm(_get_value(change_df, d_str, "change_menu"))
        delv = _norm(_get_value(deliv_df, d_str, "delivery"))

        with cols[i]:
            st.markdown('<div class="cal-cell">', unsafe_allow_html=True)

            # 날짜 버튼(작게)
            st.markdown('<div class="cal-daybtn">', unsafe_allow_html=True)
            if st.button(f"{d.day}", key=f"daybtn_{d_str}", use_container_width=True):
                st.session_state["selected_day"] = d.day
            st.markdown("</div>", unsafe_allow_html=True)

            lines = []
            if delv == "SKIP":
                lines.append("🚫 배달불요")
            else:
                if chg_v:
                    lines.append(f"🔁 {_short(chg_v, 12)}")
                if base_v:
                    lines.append(f"🍱 {_short(base_v, 12)}")

            if not lines:
                lines.append('<span class="dim"> </span>')

            st.markdown(
                '<div class="cal-lines">' + "".join([f"<div>{x}</div>" for x in lines]) + "</div>",
                unsafe_allow_html=True
            )
            st.markdown("</div>", unsafe_allow_html=True)

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

st.subheader(f"선택한 날짜: {selected_str} ({WEEKDAY_NAMES[selected_date.weekday()]})")

base_text_key = f"base_text_{selected_str}"
change_text_key = f"change_text_{selected_str}"
delivery_key = f"delivery_{selected_str}"


# -----------------------------
# ✅ 위젯 생성 전에만 상태 적용(삭제/메뉴선택 반영)
# -----------------------------
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


# -----------------------------
# 콜백
# -----------------------------
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
    days = [d.date() for d in pd.date_range(date(year_, month_, 1), date(year_, month_, last_), freq="D")]

    skip_lines = []
    change_lines = []

    for d in days:
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
# 입력/저장/삭제 + 문자 출력(동선 최소화)
# -----------------------------
left, right = st.columns([1.12, 1])

with left:
    st.markdown('<div class="section-title">기본메뉴</div>', unsafe_allow_html=True)
    if menu_list:
        pick = st.selectbox("메뉴 선택(기본)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_base_{selected_str}")
        if pick != "(선택 안함)":
            st.button("선택 메뉴 넣기", use_container_width=True, on_click=apply_base_from_menu, args=(pick,))
    st.text_input("기본메뉴 입력", key=base_text_key)
    a, b = st.columns(2)
    a.button("저장", use_container_width=True, on_click=save_base)
    b.button("삭제", use_container_width=True, on_click=delete_base)

    st.markdown('<div class="section-title">변경메뉴</div>', unsafe_allow_html=True)
    if menu_list:
        pick2 = st.selectbox("메뉴 선택(변경)", ["(선택 안함)"] + menu_list, index=0, key=f"pick_change_{selected_str}")
        if pick2 != "(선택 안함)":
            st.button("선택 메뉴 넣기", use_container_width=True, on_click=apply_change_from_menu, args=(pick2,))
    st.text_input("변경메뉴 입력", key=change_text_key)
    c, d = st.columns(2)
    c.button("저장", use_container_width=True, on_click=save_change)
    d.button("삭제", use_container_width=True, on_click=delete_change)

    st.markdown('<div class="section-title">배달 상태</div>', unsafe_allow_html=True)
    st.radio("배달/배달불요", ["배달", "배달 불요"], horizontal=True, key=delivery_key)
    e, f = st.columns(2)
    e.button("저장", use_container_width=True, on_click=save_delivery)
    f.button("초기화", use_container_width=True, on_click=clear_delivery)

with right:
    st.markdown('<div class="section-title">📩 월간 문자 출력</div>', unsafe_allow_html=True)
    st.text_area("복사해서 문자로 보내기", value=build_month_sms(year, month), height=420)
