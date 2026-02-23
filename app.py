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

BG_IMAGE_PATH = DATA_DIR / "poster_bg.jpg"          # 포스터 배경(선택)
LOGO_IMAGE_PATH = DATA_DIR / "moms_logo.png"        # M 로고(선택)

# 평일(월~금)만 출력
WEEKDAY_KR_WD = ["월", "화", "수", "목", "금"]
WEEKDAY_FULL = ["월", "화", "수", "목", "금", "토", "일"]


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
# 업로드 이미지 저장/로드
# -----------------------------
def _save_bytes(path: Path, uploaded_file) -> None:
    if uploaded_file is None:
        return
    path.write_bytes(uploaded_file.getvalue())


def _data_uri(path: Path) -> str | None:
    if path is None or (not path.exists()):
        return None
    b = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(b).decode("utf-8")


def _find_logo_path() -> Path | None:
    # data 폴더의 moms_logo.* 중 첫 번째 사용
    for p in sorted(DATA_DIR.glob("moms_logo.*")):
        return p
    # 기본 경로도 확인
    return LOGO_IMAGE_PATH if LOGO_IMAGE_PATH.exists() else None


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
# 평일(월~금) 포스터 HTML
# -----------------------------
def _build_weekday_poster_html(
    y: int,
    m: int,
    title: str,
    right_label: str,
    bg_uri: str | None,
    logo_uri: str | None,
) -> str:
    data_map = _get_day_record_map(y, m)

    # 월의 모든 평일을 순서대로 모으기
    last_day = calendar.monthrange(y, m)[1]
    weekdays: list[date] = []
    for d in range(1, last_day + 1):
        dt = date(y, m, d)
        if dt.weekday() <= 4:  # 0=월 ... 4=금
            weekdays.append(dt)

    # 5열(월~금)로 채우기
    rows: list[list[date | None]] = []
    row: list[date | None] = []
    for dt in weekdays:
        row.append(dt)
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        while len(row) < 5:
            row.append(None)
        rows.append(row)

    # 1페이지 맞춤: 행 수에 따라 셀 높이 조정
    row_count = len(rows)
    # 일반적으로 4~5행. 5행이면 조금 타이트하게.
    cell_h = 124 if row_count <= 4 else 110

    # 배경
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
        bg_css = """
        body {
          background: radial-gradient(1200px 600px at 30% 10%, rgba(255,255,255,0.9), rgba(255,255,255,0.35)),
                      linear-gradient(135deg, rgba(170,220,255,0.65), rgba(255,200,230,0.55));
        }
        """

    logo_html = ""
    if logo_uri:
        logo_html = f'<img src="{logo_uri}" class="logo-img" alt="logo"/>'
    else:
        # 로고가 없을 때도 "M" 느낌의 대체 로고(인쇄용)
        logo_html = """
        <div class="logo-fallback">
          <div class="mf">M</div>
        </div>
        """

    css = f"""
    <style>
      /* ✅ 1장 출력 전제 */
      @page {{ size: A4 landscape; margin: 7mm; }}
      html, body {{ height: 100%; }}
      {bg_css}

      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
        color: #0f172a;
      }}

      /* ✅ 인쇄 선명도: 테두리/텍스트 대비 강화 */
      .sheet {{
        width: 100%;
        border-radius: 18px;
        padding: 10px 12px 10px 12px;
        box-sizing: border-box;
        background: rgba(255,255,255,0.12);
        backdrop-filter: blur(2px);
      }}

      /* 헤더: 좌(로고+MOMS) / 중(제목) / 우(동약협회) */
      .header {{
        display:grid;
        grid-template-columns: 180px 1fr 180px;
        gap: 10px;
        align-items: center;
        margin-bottom: 8px;
      }}

      .brand {{
        height: 98px;
        border-radius: 16px;
        background: rgba(255,255,255,0.84);
        border: 2px solid rgba(15,23,42,0.20);
        box-shadow: 0 6px 16px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        gap: 10px;
        padding: 10px 12px;
        box-sizing: border-box;
      }}
      .logo-img {{
        height: 68px;
        width: auto;
        object-fit: contain;
        filter: drop-shadow(0 4px 10px rgba(15,23,42,0.10));
      }}
      .logo-fallback {{
        height: 68px; width: 68px;
        border-radius: 18px;
        background: linear-gradient(180deg, rgba(255,120,160,0.55), rgba(255,180,90,0.55));
        border: 2px solid rgba(15,23,42,0.15);
        display:flex; align-items:center; justify-content:center;
        box-shadow: inset 0 0 0 2px rgba(255,255,255,0.55);
      }}
      .logo-fallback .mf {{
        font-size: 48px;
        font-weight: 1000;
        color: rgba(15,23,42,0.85);
        text-shadow: 0 2px 0 rgba(255,255,255,0.65);
        line-height: 1;
      }}

      .brand-text {{
        line-height: 1.0;
        font-weight: 1000;
        letter-spacing: -0.3px;
        color: rgba(15,23,42,0.92);
      }}
      .brand-text .moms {{
        font-size: 28px;
      }}
      .brand-text .style {{
        font-size: 13px;
        font-weight: 900;
        opacity: 0.70;
        margin-top: 6px;
      }}

      .title {{
        font-size: 36px;
        font-weight: 1000;
        letter-spacing: -1.0px;
        text-align: center;
        color: rgba(15,23,42,0.92);
        text-shadow: 0 2px 0 rgba(255,255,255,0.65), 0 6px 18px rgba(15,23,42,0.12);
      }}

      /* 우측 상단: MOMS와 같은 크기 느낌으로 */
      .rightbox {{
        height: 98px;
        border-radius: 16px;
        background: rgba(255,255,255,0.84);
        border: 2px solid rgba(15,23,42,0.20);
        box-shadow: 0 6px 16px rgba(15,23,42,0.10);
        display:flex;
        align-items:center;
        justify-content:center;
        padding: 10px 12px;
        box-sizing: border-box;
      }}
      .rightbox .label {{
        font-size: 28px;
        font-weight: 1000;
        letter-spacing: -0.3px;
        color: rgba(15,23,42,0.92);
      }}

      /* 달력: 월~금 5열(토/일 제외) → 훨씬 여유 */
      table {{
        border-collapse: separate;
        border-spacing: 10px 10px;
        width: 100%;
        table-layout: fixed;
      }}
      th {{
        font-size: 15px;
        font-weight: 1000;
        text-align:center;
        color: rgba(15,23,42,0.92);
        text-shadow: 0 1px 0 rgba(255,255,255,0.6);
        padding: 2px 0 0 0;
      }}
      td {{
        height: {cell_h}px;
        vertical-align: top;
        background: rgba(255,255,255,0.92);
        border: 2px solid rgba(15,23,42,0.22);      /* ✅ 인쇄 선명 */
        border-radius: 14px;
        box-shadow: 0 10px 18px rgba(15,23,42,0.10);
        padding: 10px 12px;
        box-sizing: border-box;
        overflow: hidden;
      }}
      .empty {{
        background: rgba(255,255,255,0.40);
        border: 2px dashed rgba(15,23,42,0.18);
        box-shadow: none;
      }}

      /* ✅ 변경/배달불요 색 구분(깔끔하게) */
      .has-change {{
        border-color: rgba(196,0,0,0.40);
        box-shadow: 0 10px 18px rgba(196,0,0,0.10);
      }}
      .no-delivery {{
        background: rgba(255, 245, 247, 0.95);
        border-color: rgba(176,0,32,0.32);
        box-shadow: 0 10px 18px rgba(176,0,32,0.10);
      }}
      .both {{
        background: rgba(250, 246, 255, 0.95);
        border-color: rgba(125, 60, 152, 0.38);
        box-shadow: 0 10px 18px rgba(125,60,152,0.10);
      }}

      .cell-top {{
        display:flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }}
      .datechip {{
        display:inline-flex;
        align-items:baseline;
        gap: 8px;
        font-weight: 1000;
        font-size: 16px;
        letter-spacing: -0.3px;
      }}
      .dow {{
        font-size: 12.5px;
        font-weight: 900;
        opacity: 0.72;
      }}

      .badge-nodelivery {{
        font-size: 12px;
        font-weight: 1000;
        color: #b00020;
        background: rgba(255, 235, 238, 0.98);
        border: 1px solid rgba(176,0,32,0.30);
        padding: 4px 10px;
        border-radius: 999px;
        letter-spacing: -0.2px;
      }}

      .menu {{
        font-size: 16px;
        line-height: 1.18;
        letter-spacing: -0.35px;
        word-break: keep-all;
      }}
      .base {{
        font-weight: 1000;
        color: rgba(15,23,42,0.93);
      }}

      /* 변경메뉴: 붉은색 + 굵게 */
      .change {{
        margin-top: 10px;
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
        border: 1px solid rgba(196,0,0,0.30);
        margin-right: 8px;
      }}

      /* 인쇄 시 색이 너무 연하게 나오는 것을 방지 */
      @media print {{
        * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      }}
    </style>
    """

    # 헤더(월~금)
    thead = "<tr>" + "".join([f"<th>{w}</th>" for w in WEEKDAY_KR_WD]) + "</tr>"

    body_rows = []
    for r in rows:
        tds = []
        for dt in r:
            if dt is None:
                tds.append('<td class="empty"></td>')
                continue

            day = dt.day
            dow = WEEKDAY_FULL[dt.weekday()]
            rec = data_map.get(day, {})
            base = html.escape(rec.get("base", "").strip())
            change = html.escape(rec.get("change", "").strip())
            delivery = (rec.get("delivery", "Y") or "Y").strip().upper()
            is_nodelivery = (delivery == "N")
            has_change = bool(change)

            cls = ""
            if has_change and is_nodelivery:
                cls = "both"
            elif has_change:
                cls = "has-change"
            elif is_nodelivery:
                cls = "no-delivery"

            badge = f'<span class="badge-nodelivery">배달불요</span>' if is_nodelivery else ""
            base_line = f'<div class="menu base">{base}</div>' if base else '<div class="menu base">&nbsp;</div>'

            change_block = ""
            if change:
                change_block = f"""
                <div class="menu change"><span class="label">변경</span>{change}</div>
                """

            tds.append(f"""
            <td class="{cls}">
              <div class="cell-top">
                <div class="datechip">{day:02d}<span class="dow">({dow})</span></div>
                {badge}
              </div>
              {base_line}
              {change_block}
            </td>
            """)

        body_rows.append("<tr>" + "".join(tds) + "</tr>")

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
              {logo_html}
              <div class="brand-text">
                <div class="moms">MOMS</div>
                <div class="style">Style</div>
              </div>
            </div>

            <div class="title">{html.escape(title)}</div>

            <div class="rightbox">
              <div class="label">{html.escape(right_label)}</div>
            </div>
          </div>

          <table>
            <thead>{thead}</thead>
            <tbody>
              {''.join(body_rows)}
            </tbody>
          </table>
        </div>
      </body>
    </html>
    """


# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption("맘스락 포스터 포맷을 살려 ‘평일(월~금)만’ 크게, 선명하게 1장 출력되도록 구성합니다.")

colL, colR = st.columns([1.05, 1.0], vertical_alignment="top")

with colL:
    st.subheader("0) 포스터 이미지(선택)")
    bg_up = st.file_uploader("배경 이미지 업로드(선택)", type=["jpg", "jpeg", "png", "webp"], key="bg")
    logo_up = st.file_uploader("M 자 로고 업로드(권장: PNG, 투명 배경)", type=["png", "jpg", "jpeg", "webp"], key="logo")

    c0a, c0b = st.columns([1, 1])
    with c0a:
        if st.button("🖼️ 배경 저장", use_container_width=True):
            if bg_up is None:
                st.warning("업로드한 배경 파일이 없습니다.")
            else:
                _save_bytes(BG_IMAGE_PATH, bg_up)
                st.success("배경 저장 완료")
    with c0b:
        if st.button("🧹 배경 삭제", use_container_width=True):
            if BG_IMAGE_PATH.exists():
                BG_IMAGE_PATH.unlink()
            st.success("배경 삭제 완료")

    c0c, c0d = st.columns([1, 1])
    with c0c:
        if st.button("🖼️ 로고 저장", use_container_width=True):
            if logo_up is None:
                st.warning("업로드한 로고 파일이 없습니다.")
            else:
                # 로고는 업로드 확장자 유지
                ext = Path(logo_up.name).suffix.lower()
                path = DATA_DIR / f"moms_logo{ext}"
                _save_bytes(path, logo_up)
                st.success("로고 저장 완료")
    with c0d:
        if st.button("🧹 로고 삭제", use_container_width=True):
            for p in DATA_DIR.glob("moms_logo.*"):
                try:
                    p.unlink()
                except Exception:
                    pass
            st.success("로고 삭제 완료")

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
    labels = [f"{d.strftime('%m/%d')}({WEEKDAY_FULL[d.weekday()]})" for d in days]
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

    st.markdown(f"**선택 날짜:** {key}  ({WEEKDAY_FULL[dsel.weekday()]})")

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

    org = st.text_input("우측 상단 표기", value="동약협회")
    # ✅ 제목: “맘스락    월 식단변경”
    title = f"맘스락   {m:02d}월 식단변경"

    bg_uri = _data_uri(BG_IMAGE_PATH)
    logo_uri = _data_uri(_find_logo_path())

    poster_html = _build_weekday_poster_html(
        y=y,
        m=m,
        title=title,
        right_label=(org or "동약협회").strip(),
        bg_uri=bg_uri,
        logo_uri=logo_uri,
    )

    components.html(poster_html, height=780, scrolling=True)

    st.divider()
    st.subheader("4) 업체 전달용 파일 만들기")
    st.download_button(
        label="⬇️ HTML 다운로드(열고 Ctrl+P → PDF 저장/바로 출력)",
        data=poster_html.encode("utf-8"),
        file_name=f"{y}-{m:02d}_식단표_평일포스터.html",
        mime="text/html",
        use_container_width=True,
    )

    st.info("인쇄 권장: 가로 / 여백 좁게 / 한 페이지에 맞춤")
