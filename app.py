# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import io
import zipfile
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# ✅ 로고/그릇그림 내장(매번 업로드 X)
ASSETS_DIR = APP_DIR / "assets"
MOMS_LOGO_PATH = ASSETS_DIR / "moms_logo.png"
KAPMA_LOGO_PATH = ASSETS_DIR / "kapma_logo.png"
GONGYANG_BOWL_PATH = ASSETS_DIR / "gongyang_bowl.png"

PHONE_TEXT = "010-7101-5871"

GONGYANG_VERSE = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


# =========================================================
# 유틸
# =========================================================
def _ensure_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        pd.DataFrame(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    _ensure_csv(path, columns)
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns].copy()
    df = df.fillna("")
    return df


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _img_to_data_uri(path: Path) -> str:
    """로컬 이미지를 data URI로 변환 (없으면 빈 문자열)."""
    try:
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = path.suffix.lower().lstrip(".")
        mime = "png" if ext == "png" else ext
        return f"data:image/{mime};base64,{b64}"
    except Exception:
        return ""


def _norm_menu_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _korean_sort_key(s: str) -> str:
    # 단순 정렬(가나다 포함) – 대부분 케이스에서 충분
    return (s or "").strip().lower()


def _ym_to_title(year: int, month: int) -> str:
    return f"맘스락 {month:02d}월\n식단 변경"


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _fmt_mmdd(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}"


# =========================================================
# 데이터 로드/저장
# =========================================================
def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])  # Y/N
    idx_df = _read_csv(MENU_INDEX_PATH, ["name"])

    # 날짜 정리
    for df, col in [(base_df, "date"), (change_df, "date"), (delivery_df, "date")]:
        df[col] = df[col].astype(str).str.strip()

    idx_df["name"] = idx_df["name"].astype(str).apply(_norm_menu_name)
    idx_df = idx_df[idx_df["name"] != ""].drop_duplicates().copy()
    idx_df = idx_df.sort_values("name", key=lambda s: s.map(_korean_sort_key)).reset_index(drop=True)
    _write_csv(MENU_INDEX_PATH, idx_df)

    return base_df, change_df, delivery_df, idx_df


def upsert_menu(df: pd.DataFrame, day: date, col: str, value: str) -> pd.DataFrame:
    sday = day.isoformat()
    value = _norm_menu_name(value)
    if sday in df["date"].values:
        df.loc[df["date"] == sday, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": sday, col: value}])], ignore_index=True)
    df = df.fillna("")
    return df


def upsert_delivery(delivery_df: pd.DataFrame, day: date, is_no_delivery: bool) -> pd.DataFrame:
    sday = day.isoformat()
    val = "N" if is_no_delivery else "Y"
    if sday in delivery_df["date"].values:
        delivery_df.loc[delivery_df["date"] == sday, "delivery"] = val
    else:
        delivery_df = pd.concat([delivery_df, pd.DataFrame([{"date": sday, "delivery": val}])], ignore_index=True)
    delivery_df = delivery_df.fillna("")
    return delivery_df


def add_menu_index(idx_df: pd.DataFrame, name: str) -> pd.DataFrame:
    name = _norm_menu_name(name)
    if not name:
        return idx_df
    if name in idx_df["name"].values:
        return idx_df
    idx_df = pd.concat([idx_df, pd.DataFrame([{"name": name}])], ignore_index=True)
    idx_df = idx_df.drop_duplicates().copy()
    idx_df = idx_df.sort_values("name", key=lambda s: s.map(_korean_sort_key)).reset_index(drop=True)
    _write_csv(MENU_INDEX_PATH, idx_df)
    return idx_df


# =========================================================
# 백업/복원(ZIP)
# =========================================================
def build_backup_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH]:
            if p.exists():
                z.writestr(p.name, p.read_bytes())
    return buf.getvalue()


def restore_from_zip_bytes(zbytes: bytes) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(zbytes), "r") as z:
            names = set(z.namelist())
            needed = {"base_menu.csv", "change_menu.csv", "delivery.csv", "menu_index.csv"}
            missing = needed - names
            if missing:
                return False, f"ZIP 안에 다음 파일이 없습니다: {', '.join(sorted(missing))}"

            # 덮어쓰기 복원
            (DATA_DIR).mkdir(parents=True, exist_ok=True)
            for fn, dst in [
                ("base_menu.csv", BASE_MENU_PATH),
                ("change_menu.csv", CHANGE_MENU_PATH),
                ("delivery.csv", DELIVERY_PATH),
                ("menu_index.csv", MENU_INDEX_PATH),
            ]:
                dst.write_bytes(z.read(fn))
        return True, "복원이 완료되었습니다."
    except Exception as e:
        return False, f"복원 중 오류: {e}"


# =========================================================
# 포스터 HTML 생성
# =========================================================
def render_poster_header_html(title_text: str) -> str:
    moms_uri = _img_to_data_uri(MOMS_LOGO_PATH)
    kapma_uri = _img_to_data_uri(KAPMA_LOGO_PATH)

    moms_img = f'<img src="{moms_uri}" style="height:40px;vertical-align:middle;">' if moms_uri else '<div style="height:40px;"></div>'
    kapma_img = f'<img src="{kapma_uri}" style="height:40px;vertical-align:middle;">' if kapma_uri else '<div style="height:40px;"></div>'

    # title_text: 줄바꿈 \n 허용
    safe_title = (title_text or "").replace("\n", "<br>")

    return f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin:6px 0 10px 0;">
      <div style="width:220px;display:flex;align-items:center;gap:10px;
                  border:1px solid rgba(0,0,0,0.18);border-radius:14px;padding:10px 12px;background:#fff;">
        {moms_img}
        <div style="font-weight:800;font-size:22px;letter-spacing:0.5px;">MOMS</div>
      </div>

      <div style="flex:1;text-align:center;font-weight:900;font-size:34px;line-height:1.05;">
        {safe_title}
      </div>

      <div style="width:220px;text-align:center;
                  border:1px solid rgba(0,0,0,0.18);border-radius:14px;padding:10px 12px;background:#fff;">
        <div>{kapma_img}</div>
        <div style="font-weight:900;font-size:22px;margin-top:6px;">동약협회</div>
        <div style="font-size:14px;opacity:0.80;margin-top:2px;">{PHONE_TEXT}</div>
      </div>
    </div>
    """


def _cell_style(has_change: bool, no_delivery: bool) -> str:
    # ✅ 요청: 변경/배달불요를 색으로 구분(스크린샷/인쇄용)
    if no_delivery:
        return "border:2px solid rgba(220,50,70,0.65); background: rgba(220,50,70,0.07);"
    if has_change:
        return "border:2px solid rgba(245,170,35,0.65); background: rgba(245,170,35,0.07);"
    return "border:2px solid rgba(0,0,0,0.18); background: rgba(255,255,255,0.95);"


def render_poster_body_html(
    year: int,
    month: int,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    delivery_df: pd.DataFrame,
) -> str:
    # 데이터 맵
    base_map = dict(zip(base_df["date"], base_df["base_menu"]))
    change_map = dict(zip(change_df["date"], change_df["change_menu"]))
    delivery_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))  # Y/N

    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)

    dow_labels = ["월", "화", "수", "목", "금"]  # ✅ 주말 제외 표시

    css = """
    <style>
      .poster-wrap { width: 760px; margin: 0 auto; }
      .dow-row { display:grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 8px 0 8px 0; }
      .dow { text-align:center; font-weight:800; font-size:14px; }
      .grid { display:grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
      .cell { border-radius: 12px; padding: 10px 10px; min-height: 86px; box-sizing: border-box; }
      .dline { display:flex; align-items:baseline; justify-content:flex-start; gap:6px; }
      .daynum { font-weight:900; font-size:16px; }
      .dowmini { font-size:12px; opacity:0.65; }
      .menu { margin-top: 8px; font-weight:800; font-size:14px; line-height:1.25; white-space:pre-line; }
      .badge { display:inline-block; margin-top: 6px; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:900; }
      .badge-change { background: rgba(245,170,35,0.18); color: rgba(170,95,0,1); border:1px solid rgba(245,170,35,0.35); }
      .badge-nodeli { background: rgba(220,50,70,0.14); color: rgba(180,20,40,1); border:1px solid rgba(220,50,70,0.30); }
      .muted { opacity:0.35; }
      .empty { border:2px dashed rgba(0,0,0,0.16); background: rgba(255,255,255,0.6); }
    </style>
    """

    rows = []
    # 요일 헤더
    dow_html = "".join([f'<div class="dow">{x}</div>' for x in dow_labels])
    rows.append(f'<div class="dow-row">{dow_html}</div>')

    # 본문 그리드(주말 칸은 표시하지 않고, 월~금만)
    body_cells = []
    for week in weeks:
        # week: 7 days (Mon..Sun)
        for d in week[:5]:  # 월~금
            in_month = (d.month == month)
            sday = d.isoformat()
            base = (base_map.get(sday, "") or "").strip()
            chg = (change_map.get(sday, "") or "").strip()
            deli = (delivery_map.get(sday, "") or "").strip().upper()

            no_delivery = (deli == "N")
            has_change = bool(chg)

            # 표시 메뉴: 변경 있으면 "기본 + 변경" 형태(스크린샷처럼 변경만 강조)
            menu_lines = []
            if base:
                menu_lines.append(base)
            if has_change:
                # 변경은 별도 줄
                menu_lines.append(f"{chg}")
            menu_text = "\n".join([x for x in menu_lines if x])

            style = _cell_style(has_change=has_change, no_delivery=no_delivery)

            extra_class = ""
            if not in_month:
                extra_class = " muted"
            if not in_month and not base and not chg and not deli:
                # 완전 빈칸 느낌
                body_cells.append(f'<div class="cell empty"></div>')
                continue

            badges = ""
            if no_delivery:
                badges += '<div class="badge badge-nodeli">배달불요</div>'
            if has_change:
                badges += '<div class="badge badge-change">변경</div>'

            # 요일 미니표시(월~금만)
            dow_mini = ["월", "화", "수", "목", "금"][d.weekday()]

            # 변경은 빨간 글씨 강조(요청: 변경메뉴 강조)
            if has_change and chg:
                # 마지막 줄(변경)을 강조
                # base 줄이 있으면 그대로 두고, 변경 줄만 span
                if base:
                    menu_html = f'{base}<br><span style="color:rgba(200,0,0,0.95);font-weight:900;">{chg}</span>'
                else:
                    menu_html = f'<span style="color:rgba(200,0,0,0.95);font-weight:900;">{chg}</span>'
            else:
                menu_html = (menu_text or "").replace("\n", "<br>")

            body_cells.append(
                f"""
                <div class="cell{extra_class}" style="{style}">
                  <div class="dline">
                    <div class="daynum">{d.day:02d}</div>
                    <div class="dowmini">({dow_mini})</div>
                  </div>
                  <div class="menu">{menu_html}</div>
                  {badges}
                </div>
                """
            )

    rows.append(f'<div class="grid">{"".join(body_cells)}</div>')

    return f'{css}<div class="poster-wrap">{"".join(rows)}</div>'


def render_poster_full_html(title_text: str, body_html: str) -> str:
    return f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#fff;">
      <div style="width:780px;margin:0 auto;padding:10px 10px 16px 10px;">
        {render_poster_header_html(title_text)}
        {body_html}
      </div>
    </body>
    </html>
    """


# =========================================================
# 업체 전달용 출력 HTML (A4 최적화 + 공양게/그릇: 출력에만 반영)
# =========================================================
def render_vendor_print_html(poster_body_html: str, print_title: str) -> str:
    bowl_uri = _img_to_data_uri(GONGYANG_BOWL_PATH)
    bowl_img = f'<img src="{bowl_uri}" style="height:72px;">' if bowl_uri else ""

    gongyang_block = f"""
    <div style="display:flex;align-items:flex-start;gap:14px;margin:10px 0 14px 0;">
      <div style="width:90px;flex:0 0 90px;">{bowl_img}</div>
      <div style="flex:1;">
        <div style="font-weight:900;font-size:18px;margin-bottom:6px;">공양게</div>
        <div style="white-space:pre-line;font-size:14px;line-height:1.55;opacity:0.92;">
          {GONGYANG_VERSE}
        </div>
      </div>
    </div>
    """

    css = """
    <style>
      @page { size: A4; margin: 12mm; }
      body { font-family: -apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif; }
      .sheet { width: 100%; }
      .hint { font-size: 12px; opacity: 0.72; margin: 0 0 10px 0; }
      /* 인쇄 시 버튼 등 제거 */
      button, input, textarea, select { display:none !important; }
    </style>
    """

    header_html = render_poster_header_html(print_title)  # ✅ 출력물에도 로고/전화 포함

    # print_title 줄바꿈 제거(인쇄에서 보기 좋게)
    pt = (print_title or "").replace("\n", " ").strip()

    return f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <div class="sheet">
        {header_html}
        {gongyang_block}
        <div class="hint">※ 본 문서는 A4 출력에 맞춰 작성되었습니다. (브라우저 인쇄: ‘여백 기본’, ‘배율 맞춤’ 권장)</div>
        {poster_body_html}
      </div>
    </body></html>
    """


# =========================================================
# UI: 메뉴 인덱스 관리
# =========================================================
def ui_menu_index(idx_df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("### 0) 메뉴 인덱스 관리 (가나다 순 자동 정렬)")

    c1, c2 = st.columns([2, 1])
    with c1:
        new_name = st.text_input("메뉴 추가(새 메뉴 이름 입력)", value="", placeholder="예: 제육볶음")
    with c2:
        add_btn = st.button("인덱스에 추가", use_container_width=True)

    if add_btn:
        before = len(idx_df)
        idx_df = add_menu_index(idx_df, new_name)
        after = len(idx_df)
        if after > before:
            st.success("메뉴 인덱스에 추가되었습니다.")
        else:
            st.info("추가할 내용이 없거나 이미 존재합니다.")

    if len(idx_df) > 0:
        with st.expander("현재 메뉴 인덱스 보기"):
            st.dataframe(idx_df, use_container_width=True, hide_index=True)

    return idx_df


# =========================================================
# UI: 날짜 클릭 입력(다이얼로그)
# =========================================================
@st.dialog("식단 입력", width="large")
def dialog_edit_day(
    day: date,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    delivery_df: pd.DataFrame,
    idx_df: pd.DataFrame,
):
    sday = day.isoformat()

    base_map = dict(zip(base_df["date"], base_df["base_menu"]))
    change_map = dict(zip(change_df["date"], change_df["change_menu"]))
    delivery_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))

    cur_base = (base_map.get(sday, "") or "").strip()
    cur_change = (change_map.get(sday, "") or "").strip()
    cur_deli = (delivery_map.get(sday, "Y") or "Y").strip().upper()
    cur_no_delivery = (cur_deli == "N")

    st.markdown(f"**선택 날짜:** {day.strftime('%Y-%m-%d')} ({['월','화','수','목','금','토','일'][day.weekday()]})")
    st.markdown("---")

    # ✅ 기본메뉴: 인덱스 선택 + 직접입력
    st.markdown("#### 기본메뉴")
    base_col1, base_col2 = st.columns([1, 2])
    with base_col1:
        base_pick = st.selectbox(
            "인덱스에서 선택",
            options=["(선택 안 함)"] + (idx_df["name"].tolist() if len(idx_df) else []),
            index=0,
        )
        use_pick_base = st.checkbox("선택한 인덱스로 채우기", value=False)
    with base_col2:
        base_text = st.text_input("기본메뉴(직접 입력/수정)", value=cur_base, placeholder="예: 김치콩나물국")

    if use_pick_base and base_pick != "(선택 안 함)":
        base_text = base_pick

    st.markdown("#### 변경메뉴")
    chg_col1, chg_col2 = st.columns([1, 2])
    with chg_col1:
        chg_pick = st.selectbox(
            "인덱스에서 선택(변경)",
            options=["(선택 안 함)"] + (idx_df["name"].tolist() if len(idx_df) else []),
            index=0,
            key="chg_pick",
        )
        use_pick_chg = st.checkbox("선택한 인덱스로 채우기(변경)", value=False)
    with chg_col2:
        chg_text = st.text_input("변경메뉴(직접 입력/수정)", value=cur_change, placeholder="예: 제육볶음")

    if use_pick_chg and chg_pick != "(선택 안 함)":
        chg_text = chg_pick

    st.markdown("#### 배달")
    no_delivery = st.checkbox("배달불요", value=cur_no_delivery)

    st.markdown("---")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        save_btn = st.button("저장", type="primary", use_container_width=True)
    with c2:
        clear_change_btn = st.button("변경메뉴 지우기", use_container_width=True)
    with c3:
        st.caption("저장하면 창이 닫히고 달력에 반영됩니다.")

    if clear_change_btn:
        chg_text = ""

    if save_btn:
        # 반영 + 저장
        new_base_df = upsert_menu(base_df.copy(), day, "base_menu", base_text)
        new_change_df = upsert_menu(change_df.copy(), day, "change_menu", chg_text)
        new_delivery_df = upsert_delivery(delivery_df.copy(), day, is_no_delivery=no_delivery)

        _write_csv(BASE_MENU_PATH, new_base_df)
        _write_csv(CHANGE_MENU_PATH, new_change_df)
        _write_csv(DELIVERY_PATH, new_delivery_df)

        # 인덱스에도 자동 추가(사용자가 입력한 메뉴는 편의상 인덱스에 반영)
        # (원치 않으면 아래 2줄 주석처리 가능)
        if _norm_menu_name(base_text):
            add_menu_index(idx_df, base_text)
        if _norm_menu_name(chg_text):
            add_menu_index(idx_df, chg_text)

        st.success("저장했습니다.")
        st.rerun()


# =========================================================
# UI: 달력(클릭형)
# =========================================================
def ui_calendar(
    year: int,
    month: int,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    delivery_df: pd.DataFrame,
    idx_df: pd.DataFrame,
) -> None:
    st.markdown("### 1) 월 선택 / 날짜 클릭 입력")

    # 월 선택(주말 제외 표시는 포스터/달력에서 처리)
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        y = st.number_input("연도", value=year, min_value=2000, max_value=2100, step=1)
    with col2:
        m = st.number_input("월", value=month, min_value=1, max_value=12, step=1)
    with col3:
        st.caption("날짜를 클릭하면 바로 입력창이 뜹니다.")

    year = int(y)
    month = int(m)

    # 데이터 맵
    base_map = dict(zip(base_df["date"], base_df["base_menu"]))
    change_map = dict(zip(change_df["date"], change_df["change_menu"]))
    deli_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))

    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)
    dow_labels = ["월", "화", "수", "목", "금"]

    st.markdown("#### 달력 (월~금)")
    st.write("")

    # 요일 헤더
    hdr = st.columns(5)
    for i, lab in enumerate(dow_labels):
        hdr[i].markdown(f"<div style='text-align:center;font-weight:900;'>{lab}</div>", unsafe_allow_html=True)

    # 버튼 스타일(셀)
    st.markdown(
        """
        <style>
        div[data-testid="column"] > div:has(button.cal-btn) button {
            width: 100% !important;
            text-align: left !important;
            border-radius: 12px !important;
            padding: 10px 10px !important;
            min-height: 98px !important;
            white-space: pre-line !important;
            border: 2px solid rgba(0,0,0,0.18) !important;
            background: rgba(255,255,255,0.95) !important;
            font-weight: 800 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for week in weeks:
        cols = st.columns(5)
        for i, d in enumerate(week[:5]):  # 월~금
            sday = d.isoformat()
            in_month = (d.month == month)

            base = (base_map.get(sday, "") or "").strip()
            chg = (change_map.get(sday, "") or "").strip()
            deli = (deli_map.get(sday, "Y") or "Y").strip().upper()

            no_delivery = (deli == "N")
            has_change = bool(chg)

            # 버튼 라벨
            lines = [f"{d.day:02d} ({dow_labels[i]})"]
            if no_delivery:
                lines.append("배달불요")
            if base:
                lines.append(base)
            if has_change:
                lines.append(f"변경: {chg}")

            label = "\n".join(lines) if in_month else ""

            # 색상 느낌(버튼 자체는 CSS 한계가 있어, 이모지 대신 텍스트로 구분)
            # - 요청대로 산만한 이모지는 사용하지 않음
            # - in_month가 아니면 빈칸
            with cols[i]:
                if in_month:
                    btn_key = f"cal_{sday}"
                    clicked = st.button(label, key=btn_key, use_container_width=True, type="secondary")
                    # 버튼에 class를 먹이기 위한 트릭(최소 침습)
                    st.markdown("<script></script>", unsafe_allow_html=True)
                    # 버튼 클릭 시 다이얼로그
                    if clicked:
                        dialog_edit_day(d, base_df, change_df, delivery_df, idx_df)
                else:
                    st.markdown(
                        "<div style='height:98px;border:2px dashed rgba(0,0,0,0.16);border-radius:12px;'></div>",
                        unsafe_allow_html=True,
                    )


# =========================================================
# UI: 포스터 미리보기 + 업체전달용 출력(포스터 밑)
# =========================================================
def ui_poster_and_exports(
    year: int,
    month: int,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    delivery_df: pd.DataFrame,
) -> None:
    st.markdown("### 2) 포스터(출력용 1장) 미리보기")

    title_text = _ym_to_title(year, month)
    poster_body_html = render_poster_body_html(year, month, base_df, change_df, delivery_df)
    poster_full_html = render_poster_full_html(title_text, poster_body_html)

    # 화면 포스터(스크린샷 용도)
    components.html(poster_full_html, height=720, scrolling=True)

    # 포스터 HTML 다운로드(요청하신 “스크린샷으로 업체 문자”에 맞춰 헤더 로고/전화 포함)
    file_title = title_text.replace("\n", " ")
    st.download_button(
        "포스터 HTML 다운로드(스크린샷/보관용)",
        data=poster_full_html.encode("utf-8"),
        file_name=f"{file_title}.html",
        mime="text/html",
        use_container_width=True,
    )

    # ✅ 업체 전달용 출력(포스터 밑에 배치)
    st.markdown("---")
    st.subheader("업체 전달용 파일 출력")

    cA, cB = st.columns([1, 2])
    with cA:
        st.caption("담당자가 문자/카톡으로 받은 뒤 A4로 바로 출력하기 좋은 파일입니다.")
    with cB:
        st.caption("※ 이 출력파일에만 그릇그림/공양게가 포함됩니다. (포스터 화면에는 미표시)")

    vendor_html = render_vendor_print_html(poster_body_html=poster_body_html, print_title=title_text)

    st.download_button(
        "업체 전달용 HTML 다운로드(A4 출력용)",
        data=vendor_html.encode("utf-8"),
        file_name=f"{file_title}_업체전달_A4.html",
        mime="text/html",
        use_container_width=True,
    )

    with st.expander("출력 안내(담당자용)"):
        st.markdown(
            """
- PC에서 파일을 열고 **Ctrl+P(인쇄)** → 대상: 프린터 또는 “PDF로 저장”
- 권장: **용지 A4 / 여백 기본 / 배율 ‘맞춤’**
- 컬러가 부담되면 프린터 설정에서 흑백 인쇄로 출력 가능
            """.strip()
        )


# =========================================================
# UI: 백업/복원
# =========================================================
def ui_backup_restore() -> None:
    st.markdown("### 3) 데이터 백업/복원 (ZIP)")

    col1, col2 = st.columns([1, 1])
    with col1:
        zbytes = build_backup_zip_bytes()
        st.download_button(
            "데이터 백업 ZIP 다운로드",
            data=zbytes,
            file_name="moms_diet_backup.zip",
            mime="application/zip",
            use_container_width=True,
        )
    with col2:
        up = st.file_uploader("백업 ZIP 업로드(복원)", type=["zip"])
        if up is not None:
            ok, msg = restore_from_zip_bytes(up.read())
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# =========================================================
# 메인
# =========================================================
def main() -> None:
    st.title("맘스락 식단 변경 프로그램")

    # assets 안내(조용히)
    if not ASSETS_DIR.exists():
        st.warning("assets 폴더가 없습니다. app.py 옆에 assets/ 를 만들고 로고/그림 파일을 넣어주세요.")
    else:
        missing = []
        for p in [MOMS_LOGO_PATH, KAPMA_LOGO_PATH]:
            if not p.exists():
                missing.append(p.name)
        if missing:
            st.warning(f"로고 파일이 없습니다: {', '.join(missing)}  (assets/ 폴더에 넣으면 자동 표시됩니다)")

    base_df, change_df, delivery_df, idx_df = load_all()

    # 기본 월: 오늘 기준
    today = date.today()
    default_year = today.year
    default_month = today.month

    # 0) 메뉴 인덱스
    idx_df = ui_menu_index(idx_df)

    st.markdown("---")

    # 1) 달력(클릭 입력)
    ui_calendar(default_year, default_month, base_df, change_df, delivery_df, idx_df)

    # 사용자가 월/연도를 바꿨을 수 있으니, session_state에서 마지막 입력값을 잡는 대신
    # 포스터는 “현재 화면의 월/연도”와 일치하도록 다시 묻는 UI를 간단히 둠(최소 변경)
    st.markdown("---")
    st.markdown("### 2) 포스터 월 선택(미리보기/출력용)")
    c1, c2 = st.columns([1, 1])
    with c1:
        py = st.number_input("포스터 연도", value=default_year, min_value=2000, max_value=2100, step=1, key="poster_year")
    with c2:
        pm = st.number_input("포스터 월", value=default_month, min_value=1, max_value=12, step=1, key="poster_month")

    # 최신 데이터 재로드(다이얼로그 저장 후 반영)
    base_df, change_df, delivery_df, _ = load_all()

    ui_poster_and_exports(int(py), int(pm), base_df, change_df, delivery_df)

    st.markdown("---")
    ui_backup_restore()


if __name__ == "__main__":
    main()
