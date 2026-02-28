# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import base64
import html
import io
import re
import unicodedata
import zipfile

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

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BASE_MENU_PATH = DATA_DIR / "base_menu.csv"         # date,base_menu
CHANGE_MENU_PATH = DATA_DIR / "change_menu.csv"     # date,change_menu
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name
GONGYANG_PATH = DATA_DIR / "gongyang.txt"           # 공양게 문구

ASSETS_DIR = APP_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# 로고/이미지 기본 경로(여러 후보)
MOMS_LOGO_CANDIDATES = [
    ASSETS_DIR / "moms_logo.png",
    ASSETS_DIR / "moms.png",
    ASSETS_DIR / "MOMS.png",
]
KAPMA_LOGO_CANDIDATES = [
    ASSETS_DIR / "kapma_logo.png",
    ASSETS_DIR / "association_logo.png",
    ASSETS_DIR / "dongyak_logo.png",
    ASSETS_DIR / "logo_kapma.png",
]
BOWL_IMG_CANDIDATES = [
    ASSETS_DIR / "gongyang_bowl.png",
    ASSETS_DIR / "bowl.png",
    ASSETS_DIR / "bowl_logo.png",
]
DEFAULT_BG_CANDIDATES = [
    ASSETS_DIR / "poster_bg.jpg",
    ASSETS_DIR / "poster_bg.png",
    ASSETS_DIR / "bg.jpg",
    ASSETS_DIR / "bg.png",
]

DEFAULT_GONGYANG = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""


# -----------------------------
# 유틸
# -----------------------------
def _read_text(path: Path, default: str = "") -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip() or default
    except Exception:
        pass
    return default


def _write_text(path: Path, text: str) -> None:
    path.write_text((text or "").strip(), encoding="utf-8")


def _find_first_existing(cands: list[Path]) -> Path | None:
    for p in cands:
        if p.exists():
            return p
    return None


def _b64_from_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _b64_from_path(path: Path) -> str | None:
    try:
        return _b64_from_bytes(path.read_bytes())
    except Exception:
        return None


def _slug_month_title(y: int, m: int) -> str:
    return f"{y}년 {m:02d}월"


def _normalize_menu_name(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _ensure_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        try:
            df = pd.read_csv(path)
            for c in columns:
                if c not in df.columns:
                    df[c] = ""
            return df[columns].copy()
        except Exception:
            pass
    return pd.DataFrame(columns=columns)


def _save_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _load_kv_df(path: Path, key_col: str, val_col: str) -> dict[str, str]:
    df = _ensure_csv(path, [key_col, val_col])
    d = {}
    for _, r in df.iterrows():
        k = str(r.get(key_col, "")).strip()
        v = str(r.get(val_col, "")).strip()
        if k:
            d[k] = v
    return d


def _save_kv_df(path: Path, key_col: str, val_col: str, d: dict[str, str]) -> None:
    rows = [{"date": k, val_col: v} for k, v in sorted(d.items())]
    df = pd.DataFrame(rows)
    df.columns = [key_col, val_col]
    _save_csv(path, df)


def _load_delivery(path: Path) -> dict[str, str]:
    df = _ensure_csv(path, ["date", "delivery"])
    d = {}
    for _, r in df.iterrows():
        k = str(r.get("date", "")).strip()
        v = str(r.get("delivery", "")).strip().upper()
        if k:
            d[k] = "N" if v == "N" else "Y"
    return d


def _save_delivery(path: Path, d: dict[str, str]) -> None:
    rows = [{"date": k, "delivery": v} for k, v in sorted(d.items())]
    _save_csv(path, pd.DataFrame(rows))


def _ym_range_days(y: int, m: int) -> list[date]:
    _, last = calendar.monthrange(y, m)
    return [date(y, m, i) for i in range(1, last + 1)]


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


# -----------------------------
# 데이터 로드
# -----------------------------
base_map = _load_kv_df(BASE_MENU_PATH, "date", "base_menu")
change_map = _load_kv_df(CHANGE_MENU_PATH, "date", "change_menu")
delivery_map = _load_delivery(DELIVERY_PATH)

gongyang_text = _read_text(GONGYANG_PATH, DEFAULT_GONGYANG)

idx_df = _ensure_csv(MENU_INDEX_PATH, ["name"])
idx_df["name"] = idx_df["name"].astype(str).map(_normalize_menu_name)
idx_df = idx_df[idx_df["name"].str.len() > 0].drop_duplicates().sort_values("name")


# -----------------------------
# 사이드바: 월 선택
# -----------------------------
today = date.today()
with st.sidebar:
    st.subheader("월 선택")
    y = st.selectbox("년도", list(range(2024, 2031)), index=list(range(2024, 2031)).index(today.year) if 2024 <= today.year <= 2030 else 2)
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    st.divider()
    st.subheader("포스터/출력 배경 사진")
    st.caption("※ 업로드하면 ‘스크린샷 미리보기’와 ‘A4 출력’에 동일하게 꽉 차게 적용됩니다.")
    bg_upload = st.file_uploader("배경사진 업로드 (JPG/PNG)", type=["jpg", "jpeg", "png"])

    st.divider()
    st.subheader("로고/그림(선택)")
    moms_logo_upload = st.file_uploader("MOMS 로고 업로드 (PNG 권장)", type=["png", "jpg", "jpeg"], key="momslogo")
    kapma_logo_upload = st.file_uploader("동약협회 로고 업로드 (PNG 권장)", type=["png", "jpg", "jpeg"], key="kapmalogo")
    bowl_upload = st.file_uploader("그릇그림 업로드 (PNG 권장)", type=["png", "jpg", "jpeg"], key="bowlimg")

    st.divider()
    st.subheader("백업/복원")
    colb1, colb2 = st.columns(2)
    with colb1:
        if st.button("ZIP 백업 만들기"):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            mem = io.BytesIO()
            with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
                for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH, GONGYANG_PATH]:
                    if p.exists():
                        z.writestr(p.name, p.read_bytes())
            mem.seek(0)
            st.download_button(
                "다운로드", data=mem.getvalue(),
                file_name=f"moms_menu_backup_{ts}.zip",
                mime="application/zip",
            )
    with colb2:
        zip_up = st.file_uploader("ZIP 복원", type=["zip"], key="ziprestore")
        if zip_up and st.button("복원 실행"):
            try:
                zdata = zip_up.getvalue()
                with zipfile.ZipFile(io.BytesIO(zdata), "r") as z:
                    names = z.namelist()
                    for name in names:
                        if name in {BASE_MENU_PATH.name, CHANGE_MENU_PATH.name, DELIVERY_PATH.name, MENU_INDEX_PATH.name, GONGYANG_PATH.name}:
                            (DATA_DIR / name).write_bytes(z.read(name))
                st.success("복원 완료. 새로고침(F5) 하세요.")
            except Exception as e:
                st.error(f"복원 실패: {e}")


# -----------------------------
# 상단: 제목 + 공양게 편집
# -----------------------------
title = f"맘스락 {m:02d}월 식단 변경"
st.markdown(f"## {title}")

with st.expander("공양게 문구(편집)"):
    new_text = st.text_area("공양게", gongyang_text, height=140)
    if st.button("공양게 저장"):
        _write_text(GONGYANG_PATH, new_text)
        st.success("저장했습니다. (필요시 새로고침)")

st.caption("달력은 1달분만 표시됩니다. 날짜를 클릭하면 해당 날짜의 기본/변경/배달불요를 즉시 입력합니다.")


# -----------------------------
# 메뉴 인덱스 관리
# -----------------------------
with st.expander("메뉴 인덱스 관리(가나다 순 자동정렬)"):
    c1, c2 = st.columns([2, 1])
    with c1:
        add_name = st.text_input("인덱스에 추가할 메뉴명")
    with c2:
        if st.button("추가"):
            nm = _normalize_menu_name(add_name)
            if nm:
                tmp = pd.concat([idx_df, pd.DataFrame([{"name": nm}])], ignore_index=True)
                tmp = tmp.drop_duplicates().sort_values("name")
                _save_csv(MENU_INDEX_PATH, tmp)
                st.success("추가했습니다. 새로고침(F5) 하세요.")
            else:
                st.warning("메뉴명을 입력하세요.")

    st.dataframe(idx_df.reset_index(drop=True), use_container_width=True)


# -----------------------------
# 날짜 클릭 입력(대화상자)
# -----------------------------
if "selected_date" not in st.session_state:
    st.session_state.selected_date = None

@st.dialog("식단 입력", width="large")
def edit_day_dialog(d: date):
    ds = d.isoformat()
    cur_base = base_map.get(ds, "")
    cur_change = change_map.get(ds, "")
    cur_delivery = delivery_map.get(ds, "Y")

    st.markdown(f"### {ds} ({['월','화','수','목','금','토','일'][d.weekday()]})")

    # 기본메뉴: 인덱스 선택 + 직접입력
    idx_list = idx_df["name"].tolist()
    base_pick = st.selectbox("기본메뉴(인덱스 선택)", ["(선택없음)"] + idx_list,
                             index=(idx_list.index(cur_base) + 1) if cur_base in idx_list else 0)
    base_text = st.text_input("기본메뉴(직접 입력)", value=cur_base if base_pick == "(선택없음)" else base_pick)

    # 변경메뉴: 인덱스 선택 + 직접입력
    chg_pick = st.selectbox("변경메뉴(인덱스 선택)", ["(변경없음)"] + idx_list,
                            index=(idx_list.index(cur_change) + 1) if cur_change in idx_list else 0)
    chg_text = st.text_input("변경메뉴(직접 입력)", value=cur_change if chg_pick == "(변경없음)" else chg_pick)

    # 배달불요
    delivery_n = st.checkbox("배달불요(체크하면 배달 N)", value=(cur_delivery == "N"))

    colx1, colx2, colx3 = st.columns(3)
    with colx1:
        if st.button("저장"):
            # 저장
            b = _normalize_menu_name(base_text)
            c = _normalize_menu_name(chg_text)

            if b:
                base_map[ds] = b
            else:
                base_map.pop(ds, None)

            if c:
                change_map[ds] = c
            else:
                change_map.pop(ds, None)

            delivery_map[ds] = "N" if delivery_n else "Y"

            _save_kv_df(BASE_MENU_PATH, "date", "base_menu", base_map)
            _save_kv_df(CHANGE_MENU_PATH, "date", "change_menu", change_map)
            _save_delivery(DELIVERY_PATH, delivery_map)

            st.success("저장 완료")
            st.rerun()

    with colx2:
        if st.button("이 날짜 초기화"):
            base_map.pop(ds, None)
            change_map.pop(ds, None)
            delivery_map.pop(ds, None)
            _save_kv_df(BASE_MENU_PATH, "date", "base_menu", base_map)
            _save_kv_df(CHANGE_MENU_PATH, "date", "change_menu", change_map)
            _save_delivery(DELIVERY_PATH, delivery_map)
            st.success("초기화 완료")
            st.rerun()

    with colx3:
        if st.button("닫기"):
            st.rerun()


# -----------------------------
# 달력(1달) 렌더링
# -----------------------------
st.divider()

days = _ym_range_days(y, m)

# 월~일 헤더
week_names = ["월", "화", "수", "목", "금", "토", "일"]

# 달력 행 구성
cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
month_days = list(cal.itermonthdates(y, m))

# 7일씩 묶기
rows = [month_days[i:i+7] for i in range(0, len(month_days), 7)]

# 주말(토/일) 표시 옵션: “월선택에서 토/일요일은 빼고 표시” 요구가 있었던 적이 있어
# 화면 달력은 그대로 두되, 업체 전달용(텍스트)이나 필요 시 주말 제외 로직을 따로 활용 가능
st.markdown("### 📅 달력(1개월)")

# 그리드 UI
for r in rows:
    cols = st.columns(7)
    for i, d in enumerate(r):
        with cols[i]:
            if d.month != m:
                st.caption(" ")
                st.write(" ")
                continue

            ds = d.isoformat()
            b = base_map.get(ds, "")
            c = change_map.get(ds, "")
            dn = (delivery_map.get(ds, "Y") == "N")

            # 표시 문자열
            lines = [f"{d.day:02d}"]
            if dn:
                lines.append("배달불요")
            if c:
                lines.append(f"변경: {c}")
            elif b:
                lines.append(f"기본: {b}")

            label = "\n".join(lines)

            # 강조(색은 Streamlit 버튼 자체로 제한적이라, 이모지 최소 사용 + 캡션으로 구분)
            help_txt = ""
            if dn:
                help_txt = "배달불요"
            elif c:
                help_txt = "변경메뉴"
            elif b:
                help_txt = "기본메뉴"

            if st.button(label, key=f"day_{ds}", help=help_txt, use_container_width=True):
                st.session_state.selected_date = d
                edit_day_dialog(d)


# -----------------------------
# 포스터/출력용 HTML 생성 (핵심)
# -----------------------------
def _pick_image_b64(upload, fallback_candidates: list[Path]) -> tuple[str | None, str]:
    """
    returns (b64, mime)
    """
    if upload is not None:
        data = upload.getvalue()
        name = (upload.name or "").lower()
        if name.endswith(".png"):
            return _b64_from_bytes(data), "image/png"
        return _b64_from_bytes(data), "image/jpeg"

    p = _find_first_existing(fallback_candidates)
    if p is None:
        return None, ""
    ext = p.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    b64 = _b64_from_path(p)
    return b64, mime


def _month_table_html(y: int, m: int) -> str:
    """
    A4에서 보기 좋게: 셀 높이 고정 + 글 줄바꿈.
    """
    cal = calendar.Calendar(firstweekday=0)
    month_days = list(cal.itermonthdates(y, m))
    rows = [month_days[i:i+7] for i in range(0, len(month_days), 7)]

    td_html = []
    for r in rows:
        tds = []
        for d in r:
            if d.month != m:
                tds.append('<td class="cell other"></td>')
                continue
            ds = d.isoformat()
            b = html.escape(base_map.get(ds, ""))
            c = html.escape(change_map.get(ds, ""))
            dn = (delivery_map.get(ds, "Y") == "N")

            # 상태 class
            classes = ["cell"]
            if dn:
                classes.append("no-delivery")
            elif c:
                classes.append("changed")

            # 내용
            parts = [f'<div class="daynum">{d.day}</div>']
            # 배달불요 최우선
            if dn:
                parts.append('<div class="tag tag-red">배달불요</div>')
            if c:
                parts.append(f'<div class="txt"><b>변경</b> {c}</div>')
            elif b:
                parts.append(f'<div class="txt"><b>기본</b> {b}</div>')

            inner = "\n".join(parts)
            tds.append(f'<td class="{" ".join(classes)}">{inner}</td>')
        td_html.append("<tr>" + "".join(tds) + "</tr>")

    head = "".join([f"<th>{w}</th>" for w in ["월","화","수","목","금","토","일"]])
    table = f"""
    <table class="cal">
      <thead><tr>{head}</tr></thead>
      <tbody>
        {''.join(td_html)}
      </tbody>
    </table>
    """
    return table


def build_poster_html(y: int, m: int) -> str:
    # 배경
    bg_b64, bg_mime = _pick_image_b64(bg_upload, DEFAULT_BG_CANDIDATES)
    bg_url = f"data:{bg_mime};base64,{bg_b64}" if bg_b64 else ""

    # 로고/그릇
    moms_b64, moms_mime = _pick_image_b64(moms_logo_upload, MOMS_LOGO_CANDIDATES)
    kapma_b64, kapma_mime = _pick_image_b64(kapma_logo_upload, KAPMA_LOGO_CANDIDATES)
    bowl_b64, bowl_mime = _pick_image_b64(bowl_upload, BOWL_IMG_CANDIDATES)

    moms_url = f"data:{moms_mime};base64,{moms_b64}" if moms_b64 else ""
    kapma_url = f"data:{kapma_mime};base64,{kapma_b64}" if kapma_b64 else ""
    bowl_url = f"data:{bowl_mime};base64,{bowl_b64}" if bowl_b64 else ""

    month_title = html.escape(_slug_month_title(y, m))
    gong = html.escape(_read_text(GONGYANG_PATH, DEFAULT_GONGYANG)).replace("\n", "<br/>")

    table = _month_table_html(y, m)

    # ✅ 핵심: A4 1페이지 + 배경사진 full-bleed(cover) + 오버레이
    # 로고(좌/우) - 가운데(그릇+공양게) - 아래 달력 구조
    return f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  @page {{
    size: A4;
    margin: 10mm;
  }}
  html, body {{
    height: 100%;
    margin: 0;
    font-family: "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
  }}

  .sheet {{
    position: relative;
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    box-sizing: border-box;
    overflow: hidden;
    border-radius: 10px;
  }}

  /* 배경사진: 꽉 채우기(cover) */
  .bg {{
    position: absolute;
    inset: 0;
    background-image: url("{bg_url}");
    background-size: cover;
    background-position: center;
    filter: none;
    transform: scale(1.02);
  }}

  /* 내용 오버레이: 너무 흐릿하지 않게, 글자 가독성만 확보 */
  .overlay {{
    position: absolute;
    inset: 0;
    background: rgba(255,255,255,0.62);
  }}

  .content {{
    position: relative;
    padding: 10mm;
    box-sizing: border-box;
  }}

  .top {{
    display: grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    gap: 8mm;
    align-items: center;
  }}

  .logoBox {{
    background: rgba(255,255,255,0.78);
    border-radius: 14px;
    padding: 10px 12px;
    border: 1px solid rgba(0,0,0,0.10);
    min-height: 64px;
    display: flex;
    gap: 10px;
    align-items: center;
  }}

  .logoBox img {{
    max-height: 46px;
    width: auto;
    display: block;
  }}

  .logoText {{
    font-weight: 800;
    font-size: 18px;
    letter-spacing: 0.2px;
    line-height: 1.1;
  }}

  .centerBox {{
    background: rgba(255,255,255,0.78);
    border-radius: 14px;
    padding: 12px 14px;
    border: 1px solid rgba(0,0,0,0.10);
    min-height: 64px;
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: center;
    text-align: center;
  }}

  .centerBox img {{
    height: 62px;
    width: auto;
    display: block;
  }}

  .gong {{
    font-family: "Nanum Brush Script", "궁서", "Gungsuh", cursive;
    font-size: 18px;
    font-weight: 700;
    line-height: 1.25;
  }}

  .title {{
    margin-top: 8mm;
    text-align: center;
    font-size: 34px;
    font-weight: 900;
    letter-spacing: -0.4px;
    line-height: 1.05;
  }}
  .subtitle {{
    text-align: center;
    margin-top: 2mm;
    font-size: 18px;
    font-weight: 700;
    opacity: 0.85;
  }}

  .calWrap {{
    margin-top: 8mm;
    background: rgba(255,255,255,0.82);
    border-radius: 14px;
    padding: 10px;
    border: 1px solid rgba(0,0,0,0.10);
  }}

  table.cal {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 6px;
    table-layout: fixed;
  }}
  .cal th {{
    font-size: 14px;
    padding: 6px 4px;
    text-align: center;
    background: rgba(0,0,0,0.06);
    border-radius: 10px;
    font-weight: 800;
  }}
  .cal td.cell {{
    vertical-align: top;
    background: rgba(255,255,255,0.88);
    border-radius: 12px;
    padding: 8px 8px;
    min-height: 86px;
    height: 86px;
    overflow: hidden;
    border: 1px solid rgba(0,0,0,0.10);
  }}
  .cal td.other {{
    background: rgba(255,255,255,0.30);
    border: 1px dashed rgba(0,0,0,0.10);
  }}

  /* 상태 강조: A4에서도 확실히 구분되도록 “은은한 바탕색”만 */
  .cal td.changed {{
    background: rgba(255, 243, 197, 0.92); /* 변경: 옅은 노랑 */
  }}
  .cal td.no-delivery {{
    background: rgba(255, 212, 212, 0.92); /* 배달불요: 옅은 빨강 */
  }}

  .daynum {{
    font-weight: 900;
    font-size: 16px;
    margin-bottom: 4px;
  }}
  .tag {{
    display: inline-block;
    font-size: 12px;
    font-weight: 900;
    padding: 2px 8px;
    border-radius: 999px;
    margin-bottom: 6px;
  }}
  .tag-red {{
    background: rgba(220, 0, 0, 0.12);
    border: 1px solid rgba(220, 0, 0, 0.25);
  }}
  .txt {{
    font-size: 12.8px;
    line-height: 1.22;
    white-space: normal;
    word-break: keep-all;
  }}

  /* 인쇄 안정화 */
  * {{
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="bg"></div>
    <div class="overlay"></div>

    <div class="content">
      <div class="top">
        <div class="logoBox">
          {"<img src='" + moms_url + "'/>" if moms_url else ""}
          <div class="logoText">MOMS</div>
        </div>

        <div class="centerBox">
          {"<img src='" + bowl_url + "'/>" if bowl_url else ""}
          <div class="gong">{gong}</div>
        </div>

        <div class="logoBox" style="justify-content:flex-end;">
          <div class="logoText">동약협회</div>
          {"<img src='" + kapma_url + "'/>" if kapma_url else ""}
        </div>
      </div>

      <div class="title">맘스락 {m:02d}월<br/>식단(배달) 변경</div>
      <div class="subtitle">{month_title}</div>

      <div class="calWrap">
        {table}
      </div>
    </div>
  </div>
</body>
</html>
"""


# -----------------------------
# 포스터(스크린샷용) 미리보기 + 업체 전달용(A4) 출력
# -----------------------------
st.divider()
st.markdown("### 2) 포스터(스크린샷용) 미리보기")
poster_html = build_poster_html(y, m)
components.html(poster_html, height=1100, scrolling=True)

st.markdown("### 3) 업체 전달용 파일 출력 (A4 1페이지 최적화)")
st.caption("아래 HTML을 다운로드한 뒤, 크롬/엣지에서 열고 Ctrl+P → ‘대상: PDF로 저장’ → ‘한 페이지에 맞춤’으로 출력하면 A4 1페이지로 깔끔합니다. (정확도: 매우 높음)")

def _download_html_button(label: str, html_text: str, filename: str):
    b = html_text.encode("utf-8")
    st.download_button(
        label,
        data=b,
        file_name=filename,
        mime="text/html",
        use_container_width=True,
    )

_download_html_button("A4 출력용 HTML 다운로드", poster_html, f"맘스락_{y}_{m:02d}_A4_출력용.html")


# -----------------------------
# 끝
# -----------------------------
st.caption("※ 로고/배경이 보이지 않으면: 좌측 사이드바에서 이미지 업로드를 먼저 해보세요.")
