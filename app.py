import os
import calendar
from datetime import date
import pandas as pd
import streamlit as st

# =========================
# 기본 설정
# =========================
st.set_page_config(page_title="맘스락 식단 관리", layout="wide")

DATA_DIR = "data"
BASE_MENU_FILE = os.path.join(DATA_DIR, "base_menu.csv")
CHANGE_MENU_FILE = os.path.join(DATA_DIR, "change_menu.csv")
DELIVERY_FILE = os.path.join(DATA_DIR, "delivery.csv")
MENU_INDEX_FILE = os.path.join(DATA_DIR, "menu_index.csv")

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

GONGYANG_GE = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽다
마음의 탐욕을 버리고
이 음식을 약으로 삼아
도업을 이루고자 한다"""

SMS_HEADER_LINE1 = "동약협회입니다."
SMS_FOOTER = "감사합니다."


# =========================
# 파일/데이터 유틸
# =========================
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_csv(path: str, columns: list[str]) -> pd.DataFrame:
    ensure_data_dir()
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        return pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns]


def _write_csv(path: str, df: pd.DataFrame):
    ensure_data_dir()
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _norm_date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def load_menu_index() -> list[str]:
    df = _read_csv(MENU_INDEX_FILE, ["menu"])
    items = [str(x).strip() for x in df["menu"].fillna("").tolist() if str(x).strip()]
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def save_menu_index(items: list[str]):
    items = [str(x).strip() for x in items if str(x).strip()]
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    _write_csv(MENU_INDEX_FILE, pd.DataFrame({"menu": out}))


def add_to_menu_index_if_new(menu: str):
    menu = (menu or "").strip()
    if not menu:
        return
    items = load_menu_index()
    if menu not in items:
        items.append(menu)
        save_menu_index(items)


def get_value_by_date(path: str, value_col: str, d: date) -> str:
    df = _read_csv(path, ["date", value_col])
    ds = _norm_date_str(d)
    row = df[df["date"] == ds]
    if row.empty:
        return ""
    v = str(row.iloc[-1][value_col])
    return "" if v == "nan" else v


def set_value_by_date(path: str, value_col: str, d: date, value: str):
    df = _read_csv(path, ["date", value_col])
    ds = _norm_date_str(d)
    value = (value or "").strip()
    df = df[df["date"] != ds]
    df = pd.concat([df, pd.DataFrame([{"date": ds, value_col: value}])], ignore_index=True)
    df = df.sort_values("date")
    _write_csv(path, df)


def delete_by_date(path: str, value_col: str, d: date):
    df = _read_csv(path, ["date", value_col])
    ds = _norm_date_str(d)
    df = df[df["date"] != ds]
    df = df.sort_values("date")
    _write_csv(path, df)


def get_delivery_flag(d: date) -> str:
    v = get_value_by_date(DELIVERY_FILE, "delivery", d).strip()
    if v not in ["배달", "배달불요"]:
        return ""
    return v


def set_delivery_flag(d: date, flag: str):
    flag = (flag or "").strip()
    if flag not in ["배달", "배달불요", ""]:
        flag = ""
    set_value_by_date(DELIVERY_FILE, "delivery", d, flag)


# =========================
# UI/포맷 헬퍼
# =========================
def date_title_ko(d: date) -> str:
    wd = WEEKDAY_KO[d.weekday()]
    return f"{d.strftime('%Y-%m-%d')} ({wd})"


def find_bowl_image_path() -> str | None:
    candidates = [
        "gongyang_bowl.png",
        os.path.join("assets", "gongyang_bowl.png"),
        os.path.join("images", "gongyang_bowl.png"),
        os.path.join("static", "gongyang_bowl.png"),
        "/mnt/data/gongyang_bowl.png",  # 개발 환경용
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def render_month_calendar(year: int, month: int, selected: date) -> date:
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    month_days = list(cal.itermonthdates(year, month))
    weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]

    st.markdown("### 📅 날짜 선택")
    cols = st.columns(7)
    for i, name in enumerate(WEEKDAY_KO):
        cols[i].markdown(f"**{name}**")

    new_selected = selected

    for w in weeks:
        cols = st.columns(7)
        for i, d in enumerate(w):
            in_month = (d.month == month)
            label = str(d.day)

            if not in_month:
                cols[i].markdown(
                    f"<div style='opacity:0.25;padding:10px 0;text-align:center;'>{label}</div>",
                    unsafe_allow_html=True
                )
                continue

            delivery = get_delivery_flag(d)
            badge = " 🚫" if delivery == "배달불요" else (" 🚚" if delivery == "배달" else "")

            is_selected = (d == selected)
            if cols[i].button(
                f"{label}{badge}",
                key=f"daybtn_{year}_{month}_{d.day}",
                use_container_width=True,
                type="primary" if is_selected else "secondary",
            ):
                new_selected = d

    return new_selected


def month_prefix(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-"


def _fmt_mmdd_wd(ds: str) -> str:
    y, m, d = map(int, ds.split("-"))
    wd = WEEKDAY_KO[date(y, m, d).weekday()]
    return f"{m:02d}/{d:02d}({wd})"


def build_momsrak_sms(year: int, month: int) -> str:
    mp = month_prefix(year, month)

    base_df = _read_csv(BASE_MENU_FILE, ["date", "base_menu"])
    chg_df = _read_csv(CHANGE_MENU_FILE, ["date", "change_menu"])
    del_df = _read_csv(DELIVERY_FILE, ["date", "delivery"])

    base_m = base_df[base_df["date"].str.startswith(mp, na=False)].copy()
    chg_m = chg_df[chg_df["date"].str.startswith(mp, na=False)].copy()
    del_m = del_df[del_df["date"].str.startswith(mp, na=False)].copy()

    merged = pd.merge(base_m, chg_m, on="date", how="outer")
    merged = pd.merge(merged, del_m, on="date", how="outer")
    merged = merged.fillna("").sort_values("date")

    delivery_off = []
    changes = []

    for _, r in merged.iterrows():
        ds = str(r.get("date", "")).strip()
        if not ds:
            continue

        delivery = str(r.get("delivery", "")).strip()
        base = str(r.get("base_menu", "")).strip()
        chg = str(r.get("change_menu", "")).strip()

        if delivery == "배달불요":
            delivery_off.append(ds)
            continue

        if base and chg:
            changes.append((ds, base, chg))

    lines = []
    lines.append(SMS_HEADER_LINE1)
    lines.append(f"{year}년 {month:02d}월 도시락 변경/배달불요 내역입니다.")

    if delivery_off:
        lines.append("🚫【배달불요】")
        for ds in delivery_off:
            lines.append(f"▶ {_fmt_mmdd_wd(ds)} : 배달불요")

    if changes:
        lines.append("🔁【변경메뉴】")
        for ds, base, chg in changes:
            lines.append(f"▶ {_fmt_mmdd_wd(ds)} : {base} → {chg}")

    lines.append(SMS_FOOTER)
    return "\n".join(lines)


def style_monthly_table(df: pd.DataFrame):
    # 컬럼명 통일
    view = df.copy()
    view.columns = ["날짜", "기본메뉴", "변경메뉴", "배달"]

    def cell_style(value, col):
        v = str(value).strip()
        if col == "배달":
            if v == "배달불요":
                return "background-color: rgba(255, 99, 132, 0.20); font-weight: 700;"
            if v == "배달":
                return "background-color: rgba(54, 162, 235, 0.18); font-weight: 700;"
            return ""
        if col == "변경메뉴":
            if v:
                return "background-color: rgba(255, 206, 86, 0.22);"
            return ""
        if col == "기본메뉴":
            if v:
                return "background-color: rgba(153, 102, 255, 0.14);"
            return ""
        return ""

    def apply_styles(dataframe):
        styles = pd.DataFrame("", index=dataframe.index, columns=dataframe.columns)
        for c in dataframe.columns:
            styles[c] = dataframe[c].apply(lambda x: cell_style(x, c))
        return styles

    return view.style.apply(apply_styles, axis=None)


# =========================
# 스타일 (붓글씨 폰트 + UI)
# =========================
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Nanum+Brush+Script&display=swap');

      .gong-title {
        font-size: 18px;
        font-weight: 800;
        margin-bottom: 6px;
      }
      .gong-text {
        font-family: 'Nanum Brush Script', cursive;
        font-size: 34px;
        line-height: 1.35;
        white-space: pre-line;
        letter-spacing: 0.2px;
        opacity: 0.95;
      }
      .hero-wrap {
        padding: 14px 14px;
        border-radius: 18px;
        background: rgba(0,0,0,0.03);
      }
      .date-chip {
        text-align:center;
        font-size:18px;
        opacity:0.9;
        padding: 8px 10px;
        border-radius: 12px;
        background: rgba(0,0,0,0.03);
        margin-bottom: 10px;
        font-weight: 800;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# 화면
# =========================
st.title("🍱 맘스락 식단 관리")

# 상단: 그림 + 공양게(붓글씨)
bowl_path = find_bowl_image_path()
left, right = st.columns([1, 3], vertical_alignment="center")

with left:
    if bowl_path:
        st.image(bowl_path, use_container_width=True)
    else:
        st.markdown(
            "<div style='font-size:84px; text-align:center; opacity:0.9;'>🍚</div>",
            unsafe_allow_html=True
        )

with right:
    st.markdown("<div class='hero-wrap'>", unsafe_allow_html=True)
    st.markdown("<div class='gong-title'>공양게</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='gong-text'>{GONGYANG_GE}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# 사이드바: 월 선택 + 메뉴 인덱스 관리
with st.sidebar:
    st.header("📆 월 선택")
    today = date.today()
    year = st.number_input("연도", min_value=2020, max_value=2100, value=today.year, step=1)
    month = st.number_input("월", min_value=1, max_value=12, value=today.month, step=1)

    st.divider()
    st.header("📚 메뉴 인덱스")

    with st.expander("메뉴 인덱스 관리", expanded=True):
        items = load_menu_index()
        st.caption(f"현재 등록: {len(items)}개")

        st.subheader("새 메뉴 추가 (단건)")
        new_one = st.text_input("단건 입력", value="", key="index_new_one")
        if st.button("단건 추가", use_container_width=True):
            if new_one.strip():
                add_to_menu_index_if_new(new_one)
                st.success("추가했습니다.")
                st.rerun()
            else:
                st.warning("비어 있습니다.")

        st.subheader("새 메뉴 대량 추가 (여러 줄)")
        st.caption("한 줄에 1개씩 입력(붙여넣기 가능). 수십/수백 개도 한 번에 등록됩니다.")
        bulk = st.text_area("대량 입력", height=180, key="index_bulk")
        if st.button("대량 추가", use_container_width=True):
            lines = [x.strip() for x in (bulk or "").splitlines()]
            lines = [x for x in lines if x]
            if not lines:
                st.warning("입력된 내용이 없습니다.")
            else:
                for x in lines:
                    add_to_menu_index_if_new(x)
                st.success(f"{len(lines)}개 처리했습니다(중복은 자동 제외).")
                st.rerun()

        st.subheader("삭제")
        items = load_menu_index()
        if items:
            del_item = st.selectbox("삭제할 메뉴 선택", items, key="index_del_item")
            if st.button("선택 메뉴 삭제", use_container_width=True):
                items2 = [x for x in items if x != del_item]
                save_menu_index(items2)
                st.success("삭제했습니다.")
                st.rerun()
        else:
            st.info("메뉴 인덱스가 비어 있습니다.")

# 선택 날짜 초기값
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = date(int(year), int(month), 1)

# 월이 바뀌면 선택 날짜 보정
try:
    sd = st.session_state["selected_date"]
    if sd.year != int(year) or sd.month != int(month):
        st.session_state["selected_date"] = date(int(year), int(month), 1)
except Exception:
    st.session_state["selected_date"] = date(int(year), int(month), 1)

# =========================
# ✅ 동선 개선: 달력(좌) + 입력(우) 2열 배치
# =========================
col_cal, col_form = st.columns([1.1, 1.4], gap="large")

with col_cal:
    selected_date = render_month_calendar(int(year), int(month), st.session_state["selected_date"])
    st.session_state["selected_date"] = selected_date

with col_form:
    st.markdown(f"<div class='date-chip'>{date_title_ko(selected_date)}</div>", unsafe_allow_html=True)

    # 현재 값 로드
    base_current = get_value_by_date(BASE_MENU_FILE, "base_menu", selected_date)
    change_current = get_value_by_date(CHANGE_MENU_FILE, "change_menu", selected_date)
    delivery_current = get_delivery_flag(selected_date)
    menu_index_list = load_menu_index()

    tabs = st.tabs(["기본메뉴", "변경메뉴", "배달", "출력 문자"])

    # ---- 기본메뉴 탭
    with tabs[0]:
        base_select_key = f"base_select_{_norm_date_str(selected_date)}"
        base_text_key = f"base_text_{_norm_date_str(selected_date)}"

        if base_text_key not in st.session_state:
            st.session_state[base_text_key] = base_current or ""

        base_choice = st.selectbox(
            "메뉴 인덱스에서 선택",
            ["(직접입력)"] + menu_index_list,
            index=0,
            key=base_select_key
        )
        if base_choice != "(직접입력)":
            st.session_state[base_text_key] = base_choice

        base_menu = st.text_input("기본메뉴 입력", key=base_text_key)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("기본메뉴 저장", use_container_width=True):
                v = (base_menu or "").strip()
                if not v:
                    st.warning("기본메뉴가 비어 있습니다.")
                else:
                    set_value_by_date(BASE_MENU_FILE, "base_menu", selected_date, v)
                    add_to_menu_index_if_new(v)
                    st.success("기본메뉴 저장 완료")
                    st.rerun()
        with c2:
            if st.button("기본메뉴 삭제", use_container_width=True):
                delete_by_date(BASE_MENU_FILE, "base_menu", selected_date)
                st.session_state[base_text_key] = ""
                st.success("기본메뉴 삭제 완료")
                st.rerun()

    # ---- 변경메뉴 탭
    with tabs[1]:
        chg_select_key = f"chg_select_{_norm_date_str(selected_date)}"
        chg_text_key = f"chg_text_{_norm_date_str(selected_date)}"

        if chg_text_key not in st.session_state:
            st.session_state[chg_text_key] = change_current or ""

        chg_choice = st.selectbox(
            "메뉴 인덱스에서 선택",
            ["(직접입력)"] + menu_index_list,
            index=0,
            key=chg_select_key
        )
        if chg_choice != "(직접입력)":
            st.session_state[chg_text_key] = chg_choice

        change_menu = st.text_input("변경메뉴 입력", key=chg_text_key)

        c3, c4 = st.columns(2)
        with c3:
            if st.button("변경메뉴 저장", use_container_width=True):
                v = (change_menu or "").strip()
                if not v:
                    st.warning("변경메뉴가 비어 있습니다.")
                else:
                    set_value_by_date(CHANGE_MENU_FILE, "change_menu", selected_date, v)
                    add_to_menu_index_if_new(v)
                    st.success("변경메뉴 저장 완료")
                    st.rerun()
        with c4:
            if st.button("변경메뉴 삭제", use_container_width=True):
                delete_by_date(CHANGE_MENU_FILE, "change_menu", selected_date)
                st.session_state[chg_text_key] = ""
                st.success("변경메뉴 삭제 완료")
                st.rerun()

    # ---- 배달 탭
    with tabs[2]:
        delivery_choice = st.radio(
            "배달 상태",
            options=["(미설정)", "배달", "배달불요"],
            index=0 if delivery_current == "" else (1 if delivery_current == "배달" else 2),
            horizontal=True,
            key=f"delivery_{_norm_date_str(selected_date)}",
        )

        c5, c6 = st.columns(2)
        with c5:
            if st.button("배달 저장", use_container_width=True):
                flag = "" if delivery_choice == "(미설정)" else delivery_choice
                set_delivery_flag(selected_date, flag)
                st.success("배달 상태 저장 완료")
                st.rerun()
        with c6:
            if st.button("배달 삭제", use_container_width=True):
                delete_by_date(DELIVERY_FILE, "delivery", selected_date)
                st.success("배달 상태 삭제 완료")
                st.rerun()

    # ---- 출력 문자 탭
    with tabs[3]:
        sms_text = build_momsrak_sms(int(year), int(month))
        st.text_area("복사해서 맘스락에 보낼 문자", value=sms_text, height=320)

st.divider()

# =========================
# 월별 입력 현황 (색상 시각화)
# =========================
st.subheader("월별 입력 현황")

mp = month_prefix(int(year), int(month))
base_df = _read_csv(BASE_MENU_FILE, ["date", "base_menu"])
chg_df = _read_csv(CHANGE_MENU_FILE, ["date", "change_menu"])
del_df = _read_csv(DELIVERY_FILE, ["date", "delivery"])

base_m = base_df[base_df["date"].str.startswith(mp, na=False)].copy()
chg_m = chg_df[chg_df["date"].str.startswith(mp, na=False)].copy()
del_m = del_df[del_df["date"].str.startswith(mp, na=False)].copy()

merged = pd.merge(base_m, chg_m, on="date", how="outer")
merged = pd.merge(merged, del_m, on="date", how="outer")
merged = merged.fillna("").sort_values("date")

if merged.empty:
    st.info("이번 달 입력 데이터가 없습니다.")
else:
    st.dataframe(style_monthly_table(merged), use_container_width=True)

st.caption("data 폴더에 자동 저장: base_menu.csv / change_menu.csv / delivery.csv / menu_index.csv")
