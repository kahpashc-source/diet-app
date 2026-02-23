# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import io

import pandas as pd
import streamlit as st

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

# (선택) 직접 PDF 생성 시 한글 폰트 파일을 repo에 넣으면 품질이 올라갑니다.
# 예: fonts/NanumGothic.ttf
FONT_TTF_PATH = APP_DIR / "fonts" / "NanumGothic.ttf"

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


# -----------------------------
# 유틸
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
    # date 표준화
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


def _read_menu_index() -> list[str]:
    _ensure_csv(MENU_INDEX_PATH, ["name"])
    df = pd.read_csv(MENU_INDEX_PATH, dtype=str, encoding="utf-8-sig")
    if "name" not in df.columns:
        return []
    items = [x.strip() for x in df["name"].fillna("").tolist() if str(x).strip()]
    # 중복 제거(순서 유지)
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _write_menu_index(items: list[str]) -> None:
    df = pd.DataFrame({"name": items})
    df.to_csv(MENU_INDEX_PATH, index=False, encoding="utf-8-sig")


def _days_in_month(y: int, m: int) -> list[date]:
    last = calendar.monthrange(y, m)[1]
    return [date(y, m, d) for d in range(1, last + 1)]


def _build_month_table(y: int, m: int) -> pd.DataFrame:
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"]).rename(columns={"base_menu": "기본메뉴"})
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"]).rename(columns={"change_menu": "변경메뉴"})
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"]).rename(columns={"delivery": "배달"})

    days = pd.DataFrame({"date": [d.isoformat() for d in _days_in_month(y, m)]})
    df = days.merge(base, on="date", how="left").merge(change, on="date", how="left").merge(delivery, on="date", how="left")

    # 요일 / 표시용 날짜
    dts = pd.to_datetime(df["date"], errors="coerce")
    df["요일"] = dts.dt.weekday.map(lambda x: WEEKDAY_KR[int(x)] if pd.notna(x) else "")
    df["날짜"] = dts.dt.strftime("%m/%d") + "(" + df["요일"] + ")"

    # 값 정리
    df["기본메뉴"] = df["기본메뉴"].fillna("")
    df["변경메뉴"] = df["변경메뉴"].fillna("")
    df["배달"] = df["배달"].fillna("Y")
    df.loc[~df["배달"].isin(["Y", "N"]), "배달"] = "Y"

    # A안: “월별 식단표 1장(표)” 중심 컬럼
    out = df[["날짜", "기본메뉴", "변경메뉴", "배달"]].copy()
    out["변경메뉴"] = out["변경메뉴"].replace("", "—")
    out["배달"] = out["배달"].map(lambda x: "배달" if x == "Y" else "배달불요")
    return out


def _month_html(y: int, m: int, table_df: pd.DataFrame) -> str:
    title = f"{y}년 {m:02d}월 도시락 식단표(기본/변경/배달)"
    # 간단하고 인쇄 친화(브라우저에서 Ctrl+P → PDF 저장)
    css = """
    <style>
      @page { size: A4 landscape; margin: 12mm; }
      body { font-family: -apple-system, BlinkMacSystemFont, "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif; }
      h1 { font-size: 20px; margin: 0 0 10px 0; }
      .note { font-size: 12px; color: #555; margin: 0 0 12px 0; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #999; padding: 6px 8px; vertical-align: top; font-size: 12px; }
      th { background: #f3f3f3; }
      td:nth-child(1) { width: 90px; white-space: nowrap; }
      td:nth-child(4) { width: 90px; white-space: nowrap; text-align: center; }
      .footer { margin-top: 10px; font-size: 11px; color: #777; }
    </style>
    """
    html_table = table_df.to_html(index=False, escape=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    footer = f"생성 시각: {now}"
    return f"""<!doctype html>
<html lang="ko">
<head><meta charset="utf-8">{css}</head>
<body>
  <h1>{title}</h1>
  <div class="note">※ 이 파일을 열고 <b>Ctrl+P(인쇄)</b> → “PDF로 저장”을 선택하면, 업체에 보내기 좋은 PDF가 깔끔하게 생성됩니다.</div>
  {html_table}
  <div class="footer">{footer}</div>
</body>
</html>
"""


def _try_make_pdf_bytes(y: int, m: int, table_df: pd.DataFrame) -> tuple[bytes | None, str]:
    """
    정확도: 중간~높음
    - 한글 폰트(ttf)가 없으면 PDF에서 한글이 깨질 수 있어 HTML→인쇄(PDF) 방식을 권장합니다.
    """
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=18, bottomMargin=18)

        styles = getSampleStyleSheet()
        styleN = styles["Normal"]
        title_style = styles["Title"]
        title_style.fontSize = 16

        font_name = None
        if FONT_TTF_PATH.exists():
            font_name = "NanumGothic"
            pdfmetrics.registerFont(TTFont(font_name, str(FONT_TTF_PATH)))
            title_style.fontName = font_name
            styleN.fontName = font_name

        # 표 데이터
        data = [table_df.columns.tolist()] + table_df.values.tolist()

        tbl = Table(data, repeatRows=1)
        tbl_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (3, 1), (3, -1), "CENTER"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ])
        if font_name:
            tbl_style.add("FONTNAME", (0, 0), (-1, -1), font_name)
        tbl.setStyle(tbl_style)

        story = []
        story.append(Paragraph(f"{y}년 {m:02d}월 도시락 식단표(기본/변경/배달)", title_style))
        story.append(Spacer(1, 10))
        story.append(tbl)
        doc.build(story)

        pdf = buf.getvalue()
        buf.close()

        if not font_name:
            return pdf, "주의: 한글 폰트 파일이 없어 PDF에서 한글이 □ 로 보일 수 있습니다. 아래 ‘HTML 다운로드 → 인쇄(PDF)’ 방식을 권장합니다."
        return pdf, "PDF 생성 완료"
    except Exception as e:
        return None, f"PDF 생성 실패({type(e).__name__}). 아래 ‘HTML 다운로드 → 인쇄(PDF)’ 방식을 사용해 주세요."


# -----------------------------
# UI
# -----------------------------
st.title("🍱 맘스락 식단 변경 프로그램")
st.caption("A안: 월별 식단표(표 1장)로 만들어 PDF(또는 이미지)로 업체에 전송하는 방식")

colL, colR = st.columns([1.1, 1.0], vertical_alignment="top")

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
    days = _days_in_month(y, m)
    labels = []
    for d in days:
        wd = WEEKDAY_KR[d.weekday()]
        labels.append(f"{d.strftime('%m/%d')}({wd})")
    pick = st.selectbox("날짜 선택", list(range(len(days))), format_func=lambda i: labels[i])
    dsel = days[pick]

    # 현재 값 로드
    base_df = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change_df = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    deliv_df = _read_csv(DELIVERY_PATH, ["date", "delivery"])

    key = dsel.isoformat()
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
    if change_pick == "(없음)":
        # 직접입력 값 유지
        pass
    else:
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
    st.subheader("3) 월별 식단표(표 1장) 미리보기")
    month_df = _build_month_table(y, m)
    st.dataframe(month_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("4) 업체 전송용 파일 만들기")

    # HTML 다운로드(인쇄 → PDF 저장)
    html = _month_html(y, m, month_df)
    st.download_button(
        label="⬇️ HTML 다운로드(권장: 열고 Ctrl+P → PDF로 저장)",
        data=html.encode("utf-8"),
        file_name=f"{y}-{m:02d}_식단표_A안.html",
        mime="text/html",
        use_container_width=True,
    )

    # (선택) 직접 PDF 생성 시도
    pdf_bytes, pdf_msg = _try_make_pdf_bytes(y, m, month_df)
    st.caption(pdf_msg)
    if pdf_bytes:
        st.download_button(
            label="⬇️ PDF 바로 다운로드(환경에 따라 한글 깨짐 가능)",
            data=pdf_bytes,
            file_name=f"{y}-{m:02d}_식단표_A안.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.info(
        "업체 요청(사진/PDF) 대응 방법\n"
        "1) 위 HTML을 다운로드 → 열기\n"
        "2) Ctrl+P(인쇄) → ‘PDF로 저장’ 선택\n"
        "3) 생성된 PDF를 업체에 전송\n\n"
        "※ 이 방식은 한글 폰트 문제로 PDF가 깨지는 위험이 가장 적습니다."
    )
