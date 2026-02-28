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

# ✅ 로고/그림은 "매번 업로드"가 아니라 assets 폴더에 "고정 내장"
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
    df = df[columns].copy().fillna("")
    return df


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _norm_menu_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _korean_sort_key(s: str) -> str:
    return (s or "").strip().lower()


def _ym_title_multiline(year: int, month: int) -> str:
    return f"맘스락 {month:02d}월\n식단 변경"


def _ym_title_singleline(year: int, month: int) -> str:
    return f"맘스락 {month:02d}월 식단 변경"


def _img_to_data_uri(path: Path) -> str:
    """
    로컬 이미지를 data URI로 변환.
    - png/jpg/jpeg/webp/svg 지원
    - 파일이 없거나 읽기 실패 시 "" 반환
    """
    try:
        if not path.exists():
            return ""
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = path.suffix.lower().lstrip(".")
        if ext in ("jpg", "jpeg"):
            mime = "jpeg"
        elif ext in ("png", "webp"):
            mime = ext
        elif ext == "svg":
            mime = "svg+xml"
        else:
            # 알 수 없는 확장자면 png로 가정(대부분 png)
            mime = "png"
        return f"data:image/{mime};base64,{b64}"
    except Exception:
        return ""


# =========================================================
# 데이터 로드/저장
# =========================================================
def load_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])  # Y/N
    idx_df = _read_csv(MENU_INDEX_PATH, ["name"])

    for df in (base_df, change_df, delivery_df):
        df["date"] = df["date"].astype(str).str.strip()

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
    return df.fillna("")


def upsert_delivery(delivery_df: pd.DataFrame, day: date, is_no_delivery: bool) -> pd.DataFrame:
    sday = day.isoformat()
    val = "N" if is_no_delivery else "Y"
    if sday in delivery_df["date"].values:
        delivery_df.loc[delivery_df["date"] == sday, "delivery"] = val
    else:
        delivery_df = pd.concat([delivery_df, pd.DataFrame([{"date": sday, "delivery": val}])], ignore_index=True)
    return delivery_df.fillna("")


def add_menu_index(idx_df: pd.DataFrame, name: str) -> pd.DataFrame:
    name = _norm_menu_name(name)
    if not name or (name in idx_df["name"].values):
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
        for p in (BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH):
            if p.exists():
                z.writestr(p.name, p.read_bytes())
    return buf.getvalue()


def restore_from_zip_bytes(zbytes: bytes) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(zbytes), "r") as z:
            needed = {"base_menu.csv", "change_menu.csv", "delivery.csv", "menu_index.csv"}
            names = set(z.namelist())
            missing = needed - names
            if missing:
                return False, f"ZIP 안에 다음 파일이 없습니다: {', '.join(sorted(missing))}"

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
# 포스터/출력(중요: A4 최적화)
# =========================================================
def render_header_html(title_text: str, *, a4_mode: bool) -> str:
    moms_uri = _img_to_data_uri(MOMS_LOGO_PATH)
    kapma_uri = _img_to_data_uri(KAPMA_LOGO_PATH)

    # ✅ 로고가 안 나올 때도 "박스"와 텍스트는 유지
    moms_img = (
        f'<img src="{moms_uri}" style="height:{18 if a4_mode else 40}mm;max-height:{18 if a4_mode else 40}mm;">'
        if moms_uri else
        f'<div style="height:{18 if a4_mode else 40}mm;"></div>'
    )
    kapma_img = (
        f'<img src="{kapma_uri}" style="height:{18 if a4_mode else 40}mm;max-height:{18 if a4_mode else 40}mm;">'
        if kapma_uri else
        f'<div style="height:{18 if a4_mode else 40}mm;"></div>'
    )

    safe_title = (title_text or "").replace("\n", "<br>")

    # A4에서는 mm 기반으로 고정 폭을 쓰는 것이 “출력 정렬”에 가장 안정적
    box_pad = "4mm 4.5mm" if a4_mode else "10px 12px"
    box_w = "48mm" if a4_mode else "220px"
    title_fs = "18pt" if a4_mode else "34px"
    title_lh = "1.05"

    return f"""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:{'4mm' if a4_mode else '10px'};">
      <div style="width:{box_w};display:flex;align-items:center;gap:{'3mm' if a4_mode else '10px'};
                  border:1px solid rgba(0,0,0,0.18);border-radius:12px;padding:{box_pad};background:#fff;box-sizing:border-box;">
        {moms_img}
        <div style="font-weight:900;font-size:{'14pt' if a4_mode else '22px'};letter-spacing:0.3px;">MOMS</div>
      </div>

      <div style="flex:1;text-align:center;font-weight:900;font-size:{title_fs};line-height:{title_lh};">
        {safe_title}
      </div>

      <div style="width:{box_w};text-align:center;
                  border:1px solid rgba(0,0,0,0.18);border-radius:12px;padding:{box_pad};background:#fff;box-sizing:border-box;">
        <div>{kapma_img}</div>
        <div style="font-weight:900;font-size:{'14pt' if a4_mode else '22px'};margin-top:{'2mm' if a4_mode else '6px'};">동약협회</div>
        <div style="font-size:{'10.5pt' if a4_mode else '14px'};opacity:0.85;margin-top:{'1mm' if a4_mode else '2px'};">{PHONE_TEXT}</div>
      </div>
    </div>
    """


def _cell_border_bg(has_change: bool, no_delivery: bool) -> str:
    if no_delivery:
        return "border:1.2pt solid rgba(220,50,70,0.70); background: rgba(220,50,70,0.06);"
    if has_change:
        return "border:1.2pt solid rgba(245,170,35,0.75); background: rgba(245,170,35,0.06);"
    return "border:1.0pt solid rgba(0,0,0,0.22); background: rgba(255,255,255,0.98);"


def build_calendar_body_html(
    year: int,
    month: int,
    base_df: pd.DataFrame,
    change_df: pd.DataFrame,
    delivery_df: pd.DataFrame,
    *,
    a4_mode: bool,
) -> str:
    """
    ✅ 핵심: A4 출력에서 '달력 부분이 가장 중요'하므로
    - mm 기반 폭/높이
    - 5열 x (최대 6주) 구조가 A4 1페이지 안에 안정적으로 들어가게 최적화
    - 글씨/줄바꿈/칸높이/여백을 A4 기준으로 고정
    """
    base_map = dict(zip(base_df["date"], base_df["base_menu"]))
    change_map = dict(zip(change_df["date"], change_df["change_menu"]))
    delivery_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))  # Y/N

    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)

    dow_labels = ["월", "화", "수", "목", "금"]  # 주말 제외

    # 출력 안정성을 위해: A4는 폭을 mm로 "고정" (여백 제외 실사용 폭 약 190mm)
    # 5열 + gap(2mm*4=8mm) -> 칸폭 약 36.4mm
    if a4_mode:
        wrap_w = "190mm"
        gap = "2mm"
        cell_min_h = "26mm"  # 6주일 때도 1페이지 내 유지
        day_fs = "10pt"
        menu_fs = "9.2pt"
        badge_fs = "8.5pt"
        pad = "2.2mm 2.4mm"
    else:
        wrap_w = "760px"
        gap = "10px"
        cell_min_h = "86px"
        day_fs = "14px"
        menu_fs = "14px"
        badge_fs = "12px"
        pad = "10px 10px"

    css = f"""
    <style>
      .cal-wrap {{
        width: {wrap_w};
        margin: 0 auto;
        box-sizing: border-box;
      }}
      .dow-row {{
        display:grid;
        grid-template-columns: repeat(5, 1fr);
        gap: {gap};
        margin: {('2.2mm 0 2mm 0' if a4_mode else '8px 0 8px 0')};
      }}
      .dow {{
        text-align:center;
        font-weight:900;
        font-size: {('10pt' if a4_mode else '14px')};
      }}
      .grid {{
        display:grid;
        grid-template-columns: repeat(5, 1fr);
        gap: {gap};
      }}
      .cell {{
        border-radius: 8px;
        padding: {pad};
        min-height: {cell_min_h};
        box-sizing: border-box;
        overflow: hidden;
      }}
      .dline {{
        display:flex;
        align-items:baseline;
        justify-content:flex-start;
        gap: {('1.5mm' if a4_mode else '6px')};
      }}
      .daynum {{
        font-weight:900;
        font-size: {day_fs};
        line-height: 1.05;
      }}
      .dowmini {{
        font-size: {('8.7pt' if a4_mode else '12px')};
        opacity: 0.7;
      }}
      .menu {{
        margin-top: {('1.8mm' if a4_mode else '8px')};
        font-weight: 800;
        font-size: {menu_fs};
        line-height: 1.20;
        white-space: normal;
        word-break: keep-all;
      }}
      .menu .chg {{
        color: rgba(200,0,0,0.95);
        font-weight: 900;
      }}
      .badges {{
        margin-top: {('1.8mm' if a4_mode else '6px')};
        display:flex;
        gap: {('1.5mm' if a4_mode else '6px')};
        flex-wrap: wrap;
      }}
      .badge {{
        display:inline-block;
        padding: {('0.6mm 2.0mm' if a4_mode else '2px 8px')};
        border-radius: 999px;
        font-size: {badge_fs};
        font-weight: 900;
        line-height: 1.1;
      }}
      .badge-change {{
        background: rgba(245,170,35,0.18);
        color: rgba(170,95,0,1);
        border:1px solid rgba(245,170,35,0.40);
      }}
      .badge-nodeli {{
        background: rgba(220,50,70,0.14);
        color: rgba(180,20,40,1);
        border:1px solid rgba(220,50,70,0.35);
      }}
      .empty {{
        border:1pt dashed rgba(0,0,0,0.18);
        background: rgba(255,255,255,0.70);
      }}
      /* 출력 시 칸이 쪼개지지 않도록 */
      .cell {{ break-inside: avoid; page-break-inside: avoid; }}
    </style>
    """

    # 요일 헤더
    dow_html = "".join([f'<div class="dow">{x}</div>' for x in dow_labels])

    # 본문
    body_cells = []
    for week in weeks:
        for d in week[:5]:
            in_month = (d.month == month)
            sday = d.isoformat()

            base = (base_map.get(sday, "") or "").strip()
            chg = (change_map.get(sday, "") or "").strip()
            deli = (delivery_map.get(sday, "") or "Y").strip().upper()

            no_delivery = (deli == "N")
            has_change = bool(chg)

            if not in_month and (not base) and (not chg) and (not deli):
                body_cells.append('<div class="cell empty"></div>')
                continue

            style = _cell_border_bg(has_change=has_change, no_delivery=no_delivery)

            # 메뉴 HTML
            if has_change and chg:
                if base:
                    menu_html = f'{base}<br><span class="chg">{chg}</span>'
                else:
                    menu_html = f'<span class="chg">{chg}</span>'
            else:
                menu_html = base.replace("\n", "<br>") if base else ""

            badges = []
            if no_delivery:
                badges.append('<span class="badge badge-nodeli">배달불요</span>')
            if has_change:
                badges.append('<span class="badge badge-change">변경</span>')
            badges_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""

            dow_mini = ["월", "화", "수", "목", "금"][d.weekday()]
            body_cells.append(
                f"""
                <div class="cell" style="{style}">
                  <div class="dline">
                    <div class="daynum">{d.day:02d}</div>
                    <div class="dowmini">({dow_mini})</div>
                  </div>
                  <div class="menu">{menu_html}</div>
                  {badges_html}
                </div>
                """
            )

    return f'{css}<div class="cal-wrap"><div class="dow-row">{dow_html}</div><div class="grid">{"".join(body_cells)}</div></div>'


def render_poster_html(year: int, month: int, base_df: pd.DataFrame, change_df: pd.DataFrame, delivery_df: pd.DataFrame) -> tuple[str, str]:
    """
    반환:
    - full_html: 화면(스크린샷)용 포스터 전체 HTML
    - body_html: 달력 본문만(업체 출력용에서 재사용)
    """
    title = _ym_title_multiline(year, month)
    body_html = build_calendar_body_html(year, month, base_df, change_df, delivery_df, a4_mode=False)

    full_html = f"""
    <html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#fff;">
      <div style="width:800px;margin:0 auto;padding:10px 10px 16px 10px;box-sizing:border-box;">
        {render_header_html(title, a4_mode=False)}
        <div style="height:10px;"></div>
        {body_html}
      </div>
    </body></html>
    """
    return full_html, body_html


def render_vendor_a4_html(year: int, month: int, base_df: pd.DataFrame, change_df: pd.DataFrame, delivery_df: pd.DataFrame) -> str:
    """
    ✅ 업체 전달용: A4 1페이지 출력 최적화
    - 달력이 가장 크게/중심
    - 상단: MOMS/동약협회/전화 (반드시 표시)
    - 공양게/그릇그림: '업체 파일 출력'에만 포함(요청사항)
    """
    title_multi = _ym_title_multiline(year, month)
    title_single = _ym_title_singleline(year, month)

    # A4 모드 달력(핵심)
    a4_calendar_html = build_calendar_body_html(year, month, base_df, change_df, delivery_df, a4_mode=True)

    bowl_uri = _img_to_data_uri(GONGYANG_BOWL_PATH)
    bowl_img = f'<img src="{bowl_uri}" style="height:18mm;max-height:18mm;">' if bowl_uri else ""

    gongyang_block = f"""
    <div style="display:flex;align-items:flex-start;gap:4mm;margin:3mm 0 3mm 0;">
      <div style="width:22mm;flex:0 0 22mm;">{bowl_img}</div>
      <div style="flex:1;">
        <div style="font-weight:900;font-size:11pt;margin-bottom:1mm;">공양게</div>
        <div style="white-space:pre-line;font-size:9.5pt;line-height:1.35;opacity:0.92;">
{GONGYANG_VERSE}
        </div>
      </div>
    </div>
    """

    # ✅ A4 인쇄 CSS: "정렬/배치"를 mm로 고정해야 프린터에서 틀어짐이 거의 없습니다.
    css = """
    <style>
      @page { size: A4; margin: 10mm; }
      html, body { margin:0; padding:0; background:#fff; }
      body { font-family: -apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",Arial,sans-serif; }
      .sheet { width: 190mm; margin: 0 auto; box-sizing: border-box; }
      .title-line { text-align:center; font-weight:900; font-size: 16pt; margin: 2mm 0 1mm 0; }
      .note { font-size: 9pt; opacity:0.72; margin: 0 0 2mm 0; text-align:center; }
      /* 인쇄 시 쪼개짐 방지 */
      .sheet, .sheet * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    </style>
    """

    return f"""
    <html><head><meta charset="utf-8">{css}</head>
    <body>
      <div class="sheet">
        {render_header_html(title_multi, a4_mode=True)}
        <div class="title-line">{title_single}</div>
        {gongyang_block}
        <div class="note">※ A4 1페이지 출력 최적화 (권장: 여백 ‘기본’, 배율 ‘맞춤’)</div>
        {a4_calendar_html}
      </div>
    </body></html>
    """


# =========================================================
# UI: 메뉴 인덱스
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
# UI: 날짜 입력 다이얼로그
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
        st.caption("저장하면 창이 닫히고 달력/포스터에 반영됩니다.")

    if clear_change_btn:
        chg_text = ""

    if save_btn:
        new_base_df = upsert_menu(base_df.copy(), day, "base_menu", base_text)
        new_change_df = upsert_menu(change_df.copy(), day, "change_menu", chg_text)
        new_delivery_df = upsert_delivery(delivery_df.copy(), day, is_no_delivery=no_delivery)

        _write_csv(BASE_MENU_PATH, new_base_df)
        _write_csv(CHANGE_MENU_PATH, new_change_df)
        _write_csv(DELIVERY_PATH, new_delivery_df)

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

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        y = st.number_input("연도", value=year, min_value=2000, max_value=2100, step=1)
    with col2:
        m = st.number_input("월", value=month, min_value=1, max_value=12, step=1)
    with col3:
        st.caption("날짜를 클릭하면 바로 입력창이 뜹니다.")

    year = int(y)
    month = int(m)

    base_map = dict(zip(base_df["date"], base_df["base_menu"]))
    change_map = dict(zip(change_df["date"], change_df["change_menu"]))
    deli_map = dict(zip(delivery_df["date"], delivery_df["delivery"]))

    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)
    dow_labels = ["월", "화", "수", "목", "금"]

    st.markdown("#### 달력 (월~금)")
    hdr = st.columns(5)
    for i, lab in enumerate(dow_labels):
        hdr[i].markdown(f"<div style='text-align:center;font-weight:900;'>{lab}</div>", unsafe_allow_html=True)

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
        for i, d in enumerate(week[:5]):
            in_month = (d.month == month)
            if not in_month:
                with cols[i]:
                    st.markdown(
                        "<div style='height:98px;border:2px dashed rgba(0,0,0,0.16);border-radius:12px;'></div>",
                        unsafe_allow_html=True,
                    )
                continue

            sday = d.isoformat()
            base = (base_map.get(sday, "") or "").strip()
            chg = (change_map.get(sday, "") or "").strip()
            deli = (deli_map.get(sday, "Y") or "Y").strip().upper()

            no_delivery = (deli == "N")
            has_change = bool(chg)

            lines = [f"{d.day:02d} ({dow_labels[i]})"]
            if no_delivery:
                lines.append("배달불요")
            if base:
                lines.append(base)
            if has_change:
                lines.append(f"변경: {chg}")

            label = "\n".join(lines)

            with cols[i]:
                clicked = st.button(label, key=f"cal_{sday}", use_container_width=True, type="secondary")
                if clicked:
                    dialog_edit_day(d, base_df, change_df, delivery_df, idx_df)


# =========================================================
# UI: 포스터 미리보기 + 업체전달용 출력(A4 최적화)
# =========================================================
def ui_poster_and_exports(year: int, month: int, base_df: pd.DataFrame, change_df: pd.DataFrame, delivery_df: pd.DataFrame) -> None:
    st.markdown("### 2) 포스터(스크린샷용) 미리보기")

    poster_full_html, _poster_body_html = render_poster_html(year, month, base_df, change_df, delivery_df)
    components.html(poster_full_html, height=740, scrolling=True)

    file_title = _ym_title_singleline(year, month)

    st.download_button(
        "포스터 HTML 다운로드(스크린샷/보관용)",
        data=poster_full_html.encode("utf-8"),
        file_name=f"{file_title}.html",
        mime="text/html",
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader("업체 전달용 파일 출력 (A4 1페이지 최적화)")

    vendor_a4_html = render_vendor_a4_html(year, month, base_df, change_df, delivery_df)

    st.download_button(
        "업체 전달용 HTML 다운로드(A4 출력용)",
        data=vendor_a4_html.encode("utf-8"),
        file_name=f"{file_title}_업체전달_A4.html",
        mime="text/html",
        use_container_width=True,
    )

    with st.expander("담당자 출력 안내(그대로 복사해 문자/카톡에 넣어도 됨)"):
        st.markdown(
            """
1) 다운로드한 **업체전달_A4.html** 파일을 PC에서 엽니다.  
2) **Ctrl+P(인쇄)** → 용지 **A4**  
3) 권장 설정: **여백 ‘기본’ / 배율 ‘맞춤’** (또는 ‘한 페이지에 맞춤’)  
4) 프린터가 없으면 ‘PDF로 저장’으로 저장 후 출력 가능
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

    # ✅ 로고가 안 보일 때 원인 99%: 파일명/경로/확장자 불일치
    # (사용자는 업로드 하지 않도록 했으니, 여기서 "존재 여부"를 확실히 보여드립니다.)
    with st.expander("로고/그림 파일 상태(문제 해결용)"):
        st.write(f"APP_DIR: {APP_DIR}")
        st.write(f"ASSETS_DIR: {ASSETS_DIR}")
        st.write(f"- moms_logo.png: {'✅ 있음' if MOMS_LOGO_PATH.exists() else '❌ 없음'}  ({MOMS_LOGO_PATH})")
        st.write(f"- kapma_logo.png: {'✅ 있음' if KAPMA_LOGO_PATH.exists() else '❌ 없음'}  ({KAPMA_LOGO_PATH})")
        st.write(f"- gongyang_bowl.png: {'✅ 있음' if GONGYANG_BOWL_PATH.exists() else '❌ 없음'}  ({GONGYANG_BOWL_PATH})")
        st.caption("※ 파일명이 정확히 위와 같아야 자동 반영됩니다. (대/소문자 포함)")

    base_df, change_df, delivery_df, idx_df = load_all()

    today = date.today()
    default_year = today.year
    default_month = today.month

    # 0) 인덱스
    idx_df = ui_menu_index(idx_df)

    st.markdown("---")

    # 1) 달력(입력)
    ui_calendar(default_year, default_month, base_df, change_df, delivery_df, idx_df)

    st.markdown("---")
    st.markdown("### 2) 포스터/업체전달 출력 월 선택")

    c1, c2 = st.columns([1, 1])
    with c1:
        py = st.number_input("연도", value=default_year, min_value=2000, max_value=2100, step=1, key="poster_year")
    with c2:
        pm = st.number_input("월", value=default_month, min_value=1, max_value=12, step=1, key="poster_month")

    # 최신 반영 위해 재로드
    base_df, change_df, delivery_df, _ = load_all()

    ui_poster_and_exports(int(py), int(pm), base_df, change_df, delivery_df)

    st.markdown("---")
    ui_backup_restore()


if __name__ == "__main__":
    main()
