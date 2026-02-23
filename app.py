# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date
import calendar
import base64
import html

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
BG_IMAGE_PATH = DATA_DIR / "poster_bg.jpg"          # 출력 배경(선택)

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
# 배경 이미지 처리
# -----------------------------
def _save_bg_image(uploaded_file) -> None:
    # 업로드 파일을 jpg로 저장(원본 확장자 무관하게 bytes 그대로 저장)
    if uploaded_file is None:
        return
    BG_IMAGE_PATH.write_bytes(uploaded_file.getvalue())


def _bg_data_uri() -> str | None:
    if not BG_IMAGE_PATH.exists():
        return None
    b = BG_IMAGE_PATH.read_bytes()
    # 단순하게 jpg로 가정(대부분 문제 없음). png여도 브라우저가 대체로 렌더링함.
    return "data:image/jpeg;base64," + base64.b64encode(b).decode("utf-8")


# -----------------------------
# 달력 데이터
# -----------------------------
def _get_day_record_map(y: int, m: int) -> dict[int, dict[str, str]]:
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])

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


# -----------------------------
# 맘스락 느낌 “포스터형(달력 1장)” HTML
# -----------------------------
def _build_moms_poster_html(
    y: int,
    m: int,
    title_main: str,
    title_sub: str,
    bg_uri: str | None,
    show_footer: bool,
    footer_left: str,
    footer_mid: str,
    footer_right: str,
) -> str:
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    weeks = cal.monthdayscalendar(y, m)
    data_map = _get_day_record_map(y, m)

    # 배경
    bg_css = ""
    if bg_uri:
        bg_css = f"""
        body {{
          background-image: url("{bg_uri}");
          background-size: cover;
          background-position: center center;
          background-repeat: no-repeat;
        }}
        """
    else:
        # 기본 배경(이미지 없을 때)
        bg_css = """
        body {
          background: radial-gradient(1200px 600px at 30% 10%, rgba(255,255,255,0.9), rgba(255,255,255,0.35)),
                      linear-gradient(135deg, rgba(170,220,255,0.65), rgba(255,200,230,0.55));
        }
        """

    # 셀 높이: 1페이지(가로 A4) 안정 맞춤
    # 5주=조금 크게, 6주=조금 작게 자동
    row_count = len(weeks)
    cell_h = 102 if row_count == 5 else 92

    css = f"""
    <style>
      @page {{ size: A4 landscape; margin: 7mm; }}
      html, body {{ height: 100%; }}
      {bg_css}

      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
        color: #0f172a;
      }}

      .sheet {{
        width: 100%;
        border-radius: 18px;
        padding: 10px 12px 10px 12px;
        box-sizing: border-box;
        background: rgba(255,255,255,0.18);
        backdrop-filter: blur(2px);
      }}

      /* 헤더: 맘스락 느낌의 큰 타이틀 */
      .header {{
        display:flex;
        align-items:flex-start;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 8px;
      }}

      .brand {{
        width: 140px;
        min-width: 140px;
        height: 88px;
        border-radius: 16px;
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(15,23,42,0.12);
        box-shadow: 0 6px 16px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        font-weight: 900;
        letter-spacing: -0.2px;
        line-height: 1.05;
        text-align:center;
      }}
      .brand small {{
        display:block;
        font-weight: 800;
        font-size: 11px;
        opacity: 0.75;
        margin-top: 4px;
      }}

      .titles {{
        flex: 1;
        display:flex;
        flex-direction: column;
        align-items: center;
        justify-content:center;
        padding-top: 2px;
      }}
      .titles .main {{
        font-size: 44px;
        font-weight: 1000;
        letter-spacing: -1.2px;
        color: rgba(15,23,42,0.92);
        text-shadow: 0 2px 0 rgba(255,255,255,0.65), 0 6px 18px rgba(15,23,42,0.15);
        margin: 0;
      }}
      .titles .sub {{
        font-size: 40px;
        font-weight: 1000;
        letter-spacing: -1.2px;
        color: rgba(15,23,42,0.92);
        text-shadow: 0 2px 0 rgba(255,255,255,0.65), 0 6px 18px rgba(15,23,42,0.15);
        margin: 2px 0 0 0;
      }}

      .qr {{
        width: 110px;
        min-width: 110px;
        height: 110px;
        border-radius: 16px;
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(15,23,42,0.12);
        box-shadow: 0 6px 16px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        color: rgba(15,23,42,0.55);
        font-weight: 900;
        font-size: 12px;
        text-align:center;
        line-height: 1.1;
      }}

      /* 달력 */
      table {{
        border-collapse: separate;
        border-spacing: 10px 10px;   /* 맘스락처럼 ‘카드가 떠 있는’ 느낌 */
        width: 100%;
        table-layout: fixed;
      }}
      th {{
        font-size: 14px;
        font-weight: 1000;
        text-align:center;
        color: rgba(15,23,42,0.90);
        text-shadow: 0 1px 0 rgba(255,255,255,0.6);
        padding: 2px 0 0 0;
      }}

      td {{
        height: {cell_h}px;
        vertical-align: top;
        background: rgba(255,255,255,0.82);
        border: 1px solid rgba(15,23,42,0.18);
        border-radius: 14px;
        box-shadow: 0 10px 18px rgba(15,23,42,0.12);
        padding: 8px 10px;
        box-sizing: border-box;
        overflow: hidden;
      }}

      .empty {{
        background: rgba(255,255,255,0.35);
        border: 1px dashed rgba(15,23,42,0.12);
        box-shadow: none;
      }}

      .cell-top {{
        display:flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
      }}
      .datechip {{
        display:inline-flex;
        align-items:center;
        gap: 6px;
        font-weight: 1000;
        font-size: 14px;
        letter-spacing: -0.2px;
      }}
      .dow {{
        font-size: 12px;
        font-weight: 900;
        opacity: 0.70;
      }}

      .badge-nodelivery {{
        font-size: 12px;
        font-weight: 1000;
        color: #b00020;
        background: rgba(255, 235, 238, 0.95);
        border: 1px solid rgba(176,0,32,0.25);
        padding: 3px 9px;
        border-radius: 999px;
        letter-spacing: -0.2px;
      }}

      .menu {{
        font-size: 14px;
        line-height: 1.18;
        letter-spacing: -0.25px;
        word-break: keep-all;
      }}
      .base {{
        font-weight: 1000;
        color: rgba(15,23,42,0.92);
      }}

      /* 변경메뉴: 붉은색 + 굵게 */
      .change {{
        margin-top: 7px;
        font-weight: 1000;
        color: #c40000;
      }}
      .change .label {{
        display:inline-block;
        font-size: 12px;
        font-weight: 1000;
        padding: 2px 10px;
        border-radius: 999px;
        background: rgba(196,0,0,0.09);
        border: 1px solid rgba(196,0,0,0.25);
        margin-right: 8px;
      }}

      /* 하단 정보박스(선택) */
      .footer {{
        margin-top: 10px;
        display:grid;
        grid-template-columns: 1.1fr 1.4fr 1.1fr;
        gap: 10px;
      }}
      .fbox {{
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(15,23,42,0.14);
        border-radius: 16px;
        box-shadow: 0 8px 16px rgba(15,23,42,0.10);
        padding: 10px 12px;
        min-height: 68px;
        font-size: 12px;
        line-height: 1.25;
        color: rgba(15,23,42,0.80);
        white-space: pre-wrap;
      }}
    </style>
    """

    thead = "<tr>" + "".join([f"<th>{w}</th>" for w in WEEKDAY_KR]) + "</tr>"

    rows = []
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

            dow = WEEKDAY_KR[i]
            badge = f'<span class="badge-nodelivery">배달불요</span>' if is_nodelivery else ""

            base_line = f'<div class="menu base">{base}</div>' if base else '<div class="menu base">&nbsp;</div>'

            change_block = ""
            if change:
                change_block = f"""
                <div class="menu change"><span class="label">변경메뉴</span>{change}</div>
                """

            cell = f"""
            <td>
              <div class="cell-top">
                <div class="datechip">{day:02d}<span class="dow">({dow})</span></div>
                {badge}
              </div>
              {base_line}
              {change_block}
            </td>
            """
            tds.append(cell)

        rows.append("<tr>" + "".join(tds) + "</tr>")

    footer_html = ""
    if show_footer:
        footer_html = f"""
        <div class="footer">
          <div class="fbox">{html.escape(footer_left)}</div>
          <div class="fbox">{html.escape(footer_mid)}</div>
          <div class="fbox">{html.escape(footer_right)}</div>
        </div>
        """

    return f"""
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8"/>
        {css}
      </head>
      <body>
        <div class="sheet">
          <div class="header">
            <div class="brand">
              MOMS<br/>STYLE
              <small>포스터 출력용</small>
            </div>

            <div class="titles">
              <h1 class="main">{html.escape(title_main)}</h1>
              <h2 class="sub">{html.escape(title_sub)}</h2>
            </div>

            <div class="qr">QR<br/>영역(선택)</div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>

          {footer_html}
        </div>
      </body>
    </html>
    """


# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption("맘스락 포스터 느낌(달력 카드형)으로 출력용 1장 HTML을 생성합니다. 변경메뉴는 붉은색 굵게 표시됩니다.")

colL, colR = st.columns([1.05, 1.0], vertical_alignment="top")

with colL:
    st.subheader("0) 포스터 배경(선택)")
    up = st.file_uploader("맘스락 포스터처럼 배경 사진을 넣고 싶으면 업로드", type=["jpg", "jpeg", "png", "webp"])
    c0a, c0b = st.columns([1, 1])
    with c0a:
        if st.button("🖼️ 배경 저장", use_container_width=True):
            if up is None:
                st.warning("업로드한 파일이 없습니다.")
            else:
                _save_bg_image(up)
                st.success("배경 저장 완료")
    with c0b:
        if st.button("🧹 배경 삭제", use_container_width=True):
            if BG_IMAGE_PATH.exists():
                BG_IMAGE_PATH.unlink()
            st.success("배경 삭제 완료")

    st.divider()

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

    days = [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]
    labels = [f"{d.strftime('%m/%d')}({WEEKDAY_KR[d.weekday()]})" for d in days]
    pick = st.selectbox("날짜 선택", list(range(len(days))), format_func=lambda i: labels[i])
    dsel = days[pick]
    key = dsel.isoformat()

    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    cur_base = base_df.loc[base_df["date"] == key, "base_menu"].iloc[0] if (base_df["date"] == key).any() else ""
    cur_change = change_df.loc[change_df["date"] == key, "change_menu"].iloc[0] if (change_df["date"] == key).any() else ""
    cur_deliv = deliv_df.loc[deliv_df["date"] == key, "delivery"].iloc[0] if (deliv_df["date"] == key).any() else "Y"
    if cur_deliv not in ["Y", "N"]:
        cur_deliv = "Y"

    st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_KR[dsel.weekday()]})")

    st.markdown("**기본메뉴**")
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

    st.markdown("**변경메뉴(있으면 입력)**")
    change_pick = st.selectbox("변경메뉴(인덱스)", ["(없음)"] + idx_items, index=0)
    default_change = "" if cur_change.strip() == "" else cur_change
    change_text = st.text_input("변경메뉴(직접입력)", value=default_change if change_pick == "(없음)" else change_pick)
    if change_pick != "(없음)":
        change_text = change_pick

    c3, c4 = st.columns([1, 1])
    with c3:
        if st.button("💾 변경메뉴 저장", use_container_width=True):
            _upsert_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel, "change_menu", (change_text or "").strip())
            st.success("변경메뉴 저장 완료")
    with c4:
        if st.button("🧹 변경메뉴 삭제(해당일)", use_container_width=True):
            _delete_by_date(CHANGE_MENU_PATH, ["date", "change_menu"], dsel)
            st.success("변경메뉴 삭제 완료")

    st.markdown("**배달 여부**")
    deliv_choice = st.radio("배달", ["배달(Y)", "배달불요(N)"], index=0 if cur_deliv == "Y" else 1, horizontal=True)
    if st.button("💾 배달여부 저장", use_container_width=True):
        _upsert_by_date(DELIVERY_PATH, ["date", "delivery"], dsel, "delivery", "Y" if deliv_choice.startswith("배달(Y)") else "N")
        st.success("배달여부 저장 완료")

with colR:
    st.subheader("3) 포스터(출력용 1장) 미리보기")

    org = st.text_input("상단 표기(단체/회사명)", value="동약협회")
    title_main = st.text_input("큰 제목(1줄)", value="맘스락")
    title_sub = st.text_input("큰 제목(2줄)", value=f"{m}월식단  {org}")

    st.markdown("**하단 안내 박스(선택)**")
    show_footer = st.checkbox("하단 박스 표시", value=False)
    footer_left = st.text_area("하단 왼쪽", value="원산지/비고 등", height=80)
    footer_mid = st.text_area("하단 가운데", value="회사명/담당자/연락처/식사시간 등", height=80)
    footer_right = st.text_area("하단 오른쪽", value="이용방법/유의사항 등", height=80)

    bg_uri = _bg_data_uri()
    poster_html = _build_moms_poster_html(
        y=y,
        m=m,
        title_main=(title_main or "맘스락").strip(),
        title_sub=(title_sub or f"{m}월식단").strip(),
        bg_uri=bg_uri,
        show_footer=show_footer,
        footer_left=footer_left or "",
        footer_mid=footer_mid or "",
        footer_right=footer_right or "",
    )

    components.html(poster_html, height=780, scrolling=True)

    st.divider()
    st.subheader("4) 업체 전달용 파일 만들기")
    st.download_button(
        label="⬇️ HTML 다운로드(열고 Ctrl+P → PDF 저장/바로 출력)",
        data=poster_html.encode("utf-8"),
        file_name=f"{y}-{m:02d}_식단표_포스터형.html",
        mime="text/html",
        use_container_width=True,
    )

    st.info("인쇄 권장: 가로 / 여백 좁게 / 한 페이지에 맞춤 (이 설정이면 ‘달력 1장’으로 안정적으로 출력됩니다.)")
