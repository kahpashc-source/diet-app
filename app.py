# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import html
import io

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="맘스락 식단 변경 프로그램", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


# -----------------------------
# CSV 유틸
# -----------------------------
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
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
        df = df[df["date"].ne("NaT")]
    return df


def _upsert_by_date(path: Path, columns: list[str], d: date, value_col: str, value: str) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    if (df["date"] == key).any():
        df.loc[df["date"] == key, value_col] = value
    else:
        row = {c: "" for c in columns}
        row["date"] = key
        row[value_col] = value
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _delete_by_date(path: Path, columns: list[str], d: date) -> None:
    df = _read_csv(path, columns)
    key = d.isoformat()
    df = df[df["date"] != key].copy()
    df.to_csv(path, index=False, encoding="utf-8-sig")


# -----------------------------
# 메뉴 인덱스
# -----------------------------
def _read_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8-sig")
    if "name" not in df.columns:
        return []
    items = [x.strip() for x in df["name"].fillna("").tolist() if str(x).strip()]
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _write_menu_index(items: list[str]) -> None:
    pd.DataFrame({"name": items}).to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")


# -----------------------------
# 달력 데이터 만들기
# -----------------------------
def _get_day_record_map(y: int, m: int) -> dict[int, dict[str, str]]:
    """
    반환: {일자(int): {"base":..., "change":..., "delivery": "Y/N"}}
    (정확도: 매우 높음 — CSV 기반 단순 매핑)
    """
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    # 해당 월만 필터
    prefix = f"{y}-{m:02d}-"
    base = base[base["date"].str.startswith(prefix)].copy()
    change = change[change["date"].str.startswith(prefix)].copy()
    delivery = delivery[delivery["date"].str.startswith(prefix)].copy()

    out: dict[int, dict[str, str]] = {}
    for _, r in base.iterrows():
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["base"] = (r.get("base_menu") or "").strip()

    for _, r in change.iterrows():
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        out[d]["change"] = (r.get("change_menu") or "").strip()

    for _, r in delivery.iterrows():
        try:
            d = int(str(r["date"])[-2:])
        except Exception:
            continue
        out.setdefault(d, {})
        v = (r.get("delivery") or "Y").strip().upper()
        out[d]["delivery"] = "N" if v == "N" else "Y"

    return out


def _build_calendar_html(y: int, m: int, org_name: str = "동약협회") -> str:
    """
    월간 달력 '1장 포스터' HTML 생성.
    - 각 날짜 칸: 기본메뉴 / (있으면) 변경메뉴 / (배달불요면) 배달불요 라벨
    - 출력 친화: A4 가로 인쇄 권장
    (정확도: 매우 높음 — 렌더링은 브라우저 인쇄 기능 활용)
    """
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작(0=월)
    weeks = cal.monthdayscalendar(y, m)      # 각 주: [월..일], 해당월 아니면 0

    data_map = _get_day_record_map(y, m)

    title = f"{org_name}  |  {y}년 {m:02d}월 도시락 식단표"
    subtitle = "※ 각 날짜 칸에 기본메뉴/변경메뉴/배달불요가 기재되어 출력(종이) 전달용으로 사용합니다."

    css = """
    <style>
      @page { size: A4 landscape; margin: 10mm; }
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo",
                     "Noto Sans KR", Arial, sans-serif;
        color: #111;
      }
      .wrap { width: 100%; }
      .head {
        display:flex; align-items:flex-end; justify-content:space-between;
        margin-bottom: 10px;
      }
      .title { font-size: 22px; font-weight: 900; }
      .meta { font-size: 11px; color:#666; text-align:right; }
      .subtitle { font-size: 12px; color:#444; margin: 2px 0 10px 0; }
      table { border-collapse: collapse; width: 100%; table-layout: fixed; }
      th, td { border: 1px solid #999; }
      th {
        background: #f2f2f2;
        font-size: 12px;
        padding: 6px 4px;
        text-align: center;
        font-weight: 800;
      }
      td {
        height: 110px;
        vertical-align: top;
        padding: 6px 6px;
      }
      .cell-top {
        display:flex; justify-content:space-between; align-items:center;
        margin-bottom: 4px;
      }
      .daynum { font-size: 13px; font-weight: 900; }
      .badge {
        font-size: 11px; font-weight: 900;
        padding: 2px 6px; border-radius: 10px;
        border: 1px solid rgba(0,0,0,0.25);
      }
      .badge-nodelivery { background: #ffe8e8; }
      .menu { font-size: 12px; line-height: 1.25; margin-top: 3px; }
      .base { font-weight: 800; }
      .change { margin-top: 4px; }
      .change .label {
        display:inline-block;
        font-size: 11px; font-weight: 900;
        padding: 1px 6px; border-radius: 8px;
        background: #fff4cc;
        border: 1px solid rgba(0,0,0,0.2);
        margin-right: 6px;
      }
      .empty { background: #fafafa; }
      .weekend-sat { background: #fbfbff; }
      .weekend-sun { background: #fffafb; }
      .foot {
        margin-top: 8px;
        font-size: 11px;
        color: #666;
        display:flex;
        justify-content: space-between;
      }
      .print-tip {
        font-size: 11px; color:#555;
      }
    </style>
    """

    # 요일 헤더 (월~일)
    thead = "<tr>" + "".join([f"<th>{w}</th>" for w in WEEKDAY_KR]) + "</tr>"

    # 각 셀 생성
    rows_html = []
    for wk in weeks:
        tds = []
        for i, day in enumerate(wk):  # i: 0..6 (월..일)
            if day == 0:
                tds.append('<td class="empty"></td>')
                continue

            rec = data_map.get(day, {})
            base = html.escape(rec.get("base", "").strip())
            change = html.escape(rec.get("change", "").strip())
            delivery = (rec.get("delivery", "Y") or "Y").strip().upper()
            is_nodelivery = (delivery == "N")

            # 주말 배경 약하게
            weekend_class = ""
            if i == 5:
                weekend_class = "weekend-sat"
            elif i == 6:
                weekend_class = "weekend-sun"

            badge = ""
            if is_nodelivery:
                badge = '<span class="badge badge-nodelivery">배달불요</span>'

            base_line = f'<div class="menu base">{base}</div>' if base else '<div class="menu base">&nbsp;</div>'

            change_block = ""
            if change:
                change_block = f"""
                <div class="menu change">
                  <span class="label">변경</span>{change}
                </div>
                """

            cell_html = f"""
            <td class="{weekend_class}">
              <div class="cell-top">
                <span class="daynum">{day}</span>
                {badge}
              </div>
              {base_line}
              {change_block}
            </td>
            """
            tds.append(cell_html)

        rows_html.append("<tr>" + "".join(tds) + "</tr>")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_doc = f"""
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8"/>
        {css}
      </head>
      <body>
        <div class="wrap">
          <div class="head">
            <div>
              <div class="title">{title}</div>
              <div class="subtitle">{subtitle}</div>
            </div>
            <div class="meta">
              생성: {now}<br/>
              <span class="print-tip">권장: Ctrl+P → 가로/여백 좁게/한 페이지 맞춤</span>
            </div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>
              {''.join(rows_html)}
            </tbody>
          </table>

          <div class="foot">
            <div>표기: <b>변경</b>은 변경메뉴가 있는 날만 표시 / <b>배달불요</b>는 배달 N인 날만 표시</div>
            <div></div>
          </div>
        </div>
      </body>
    </html>
    """
    return html_doc


# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption("월별 달력(출력용 1장) 안에 기본메뉴/변경메뉴/배달불요가 모두 기재되도록 구성합니다.")

colL, colR = st.columns([1.05, 1.0], vertical_alignment="top")

with colL:
    st.subheader("1) 메뉴 인덱스 관리")
    idx_items = _read_menu_index()

    c1, c2 = st.columns([1, 1])
    with c1:
        new_item = st.text_input("메뉴 추가", placeholder="예: 소고기미역국")
        if st.button("➕ 인덱스에 추가", use_container_width=True):
            x = (new_item or "").strip()
            if x:
                if x not in idx_items:
                    idx_items.append(x)
                    _write_menu_index(idx_items)
                st.success("저장 완료")
            else:
                st.warning("메뉴명을 입력해 주세요.")

    with c2:
        del_item = st.selectbox("삭제할 메뉴 선택", ["(선택)"] + idx_items)
        if st.button("🗑️ 선택 메뉴 삭제", use_container_width=True):
            if del_item != "(선택)":
                idx_items = [x for x in idx_items if x != del_item]
                _write_menu_index(idx_items)
                st.success("삭제 완료")

    st.divider()

    st.subheader("2) 월 선택 & 날짜별 입력")
    today = date.today()
    y = st.selectbox("연도", list(range(today.year - 2, today.year + 4)), index=2)
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    # 날짜 선택
    days = [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    labels = [f"{d.strftime('%m/%d')}({WEEKDAY_KR[d.weekday()]})" for d in days]
    pick = st.selectbox("날짜 선택", list(range(len(days))), format_func=lambda i: labels[i])
    dsel = days[pick]
    key = dsel.isoformat()

    # 현재 값 로드
    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    cur_base = base_df.loc[base_df["date"] == key, "base_menu"].iloc[0] if (base_df["date"] == key).any() else ""
    cur_change = change_df.loc[change_df["date"] == key, "change_menu"].iloc[0] if (change_df["date"] == key).any() else ""
    cur_deliv = deliv_df.loc[deliv_df["date"] == key, "delivery"].iloc[0] if (deliv_df["date"] == key).any() else "Y"
    if cur_deliv not in ["Y", "N"]:
        cur_deliv = "Y"

    st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_KR[dsel.weekday()]})")

    # 기본 메뉴
    st.markdown("**기본메뉴 입력(인덱스에서 선택/직접 입력 가능)**")
    base_pick = st.selectbox("기본메뉴(인덱스)", ["(직접입력)"] + idx_items, index=0)
    base_text = st.text_input("기본메뉴(직접입력)", value=cur_base if base_pick == "(직접입력)" else base_pick)
    if base_pick != "(직접입력)":
        base_text = base_pick

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 기본메뉴 저장", use_container_width=True):
            _upsert_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel, "base_menu", (base_text or "").strip())
            st.success("기본메뉴 저장 완료")
    with b2:
        if st.button("🧹 기본메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(BASE_MENU_PATH, ["date", "base_menu"], dsel)
            st.success("기본메뉴 삭제 완료")

    # 변경 메뉴
    st.markdown("**변경메뉴 입력(없으면 비워둬도 됨)**")
    change_pick = st.selectbox("변경메뉴(인덱스)", ["(없음)"] + idx_items, index=0)
    default_change = "" if cur_change.strip() == "" else cur_change
    change_text = st.text_input("변경메뉴(직접입력)", value=default_change if change_pick == "(없음)" else change_pick)
    if change_pick != "(없음)":
        change_text = change_pick

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("💾 변경메뉴 저장", use_container_width=True):
            v = (change_text or "").strip()
            _upsert_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel, "change_menu", v)
            st.success("변경메뉴 저장 완료")
    with c2:
        if st.button("🧹 변경메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel)
            st.success("변경메뉴 삭제 완료")

    # 배달 여부
    st.markdown("**배달 여부**")
    deliv_choice = st.radio("배달", ["배달(Y)", "배달불요(N)"], index=0 if cur_deliv == "Y" else 1, horizontal=True)
    if st.button("💾 배달여부 저장", use_container_width=True):
        _upsert_by_date(DELIVERY_PATH, ["date", "delivery"], dsel, "delivery", "Y" if deliv_choice.startswith("배달(Y)") else "N")
        st.success("배달여부 저장 완료")

with colR:
    st.subheader("3) 월간 달력(출력용 1장) 미리보기")
    org = st.text_input("상단 제목에 넣을 단체명", value="동약협회")
    poster_html = _build_calendar_html(y, m, org_name=(org or "동약협회").strip())

    # 미리보기(높이는 넉넉히)
    components.html(poster_html, height=760, scrolling=True)

    st.divider()
    st.subheader("4) 업체/식당 전달용 파일 만들기")

    st.download_button(
        label="⬇️ HTML 다운로드(권장: 열고 Ctrl+P → PDF로 저장/바로 인쇄)",
        data=poster_html.encode("utf-8"),
        file_name=f"{y}-{m:02d}_식단표_달력1장.html",
        mime="text/html",
        use_container_width=True,
    )

    st.info(
        "사용 방법(정확도: 매우 높음)\n"
        "1) 위 HTML 다운로드\n"
        "2) 파일을 더블클릭으로 열기(크롬/엣지)\n"
        "3) Ctrl+P(인쇄)\n"
        "   - 방향: 가로\n"
        "   - 여백: 좁게\n"
        "   - 배율: 한 페이지에 맞춤\n"
        "4) 프린터로 출력하거나 ‘PDF로 저장’ 후 업체에 전송"
    )
