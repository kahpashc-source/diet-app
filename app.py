# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import calendar
import io
import zipfile
import re
import unicodedata
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
GONGYANG_PATH = DATA_DIR / "gongyang.txt"           # 공양게 문구

DEFAULT_GONGYANG = """이 음식이 어디에서 왔는가
내 덕행으로는 받기가 부끄럽네
마음의 온갖 탐욕을 떠나
바른 생각으로 이 공양을 받습니다"""

ASSOC_PHONE_FIXED = "0101-7101-5871"


# -----------------------------
# 유틸(저장/로드 안정화)
# -----------------------------
def norm_text(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s


def ensure_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        try:
            df = pd.read_csv(path, dtype=str).fillna("")
            for c in columns:
                if c not in df.columns:
                    df[c] = ""
            return df[columns].copy()
        except Exception:
            pass
    return pd.DataFrame(columns=columns)


def save_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def load_kv(path: Path, key_col: str, val_col: str) -> dict[str, str]:
    df = ensure_csv(path, [key_col, val_col])
    d: dict[str, str] = {}
    for _, r in df.iterrows():
        k = str(r.get(key_col, "")).strip()
        v = str(r.get(val_col, "")).strip()
        if k:
            d[k] = v
    return d


def save_kv(path: Path, key_col: str, val_col: str, d: dict[str, str]) -> None:
    rows = [{"date": k, val_col: v} for k, v in sorted(d.items())]
    df = pd.DataFrame(rows)
    df.columns = [key_col, val_col]
    save_csv(path, df)


def load_delivery(path: Path) -> dict[str, str]:
    df = ensure_csv(path, ["date", "delivery"])
    d: dict[str, str] = {}
    for _, r in df.iterrows():
        k = str(r.get("date", "")).strip()
        v = str(r.get("delivery", "")).strip().upper()
        if k:
            d[k] = "N" if v == "N" else "Y"
    return d


def save_delivery(path: Path, d: dict[str, str]) -> None:
    rows = [{"date": k, "delivery": v} for k, v in sorted(d.items())]
    save_csv(path, pd.DataFrame(rows))


def read_text(path: Path, default: str) -> str:
    try:
        if path.exists():
            t = path.read_text(encoding="utf-8").strip()
            return t if t else default
    except Exception:
        pass
    return default


def write_text(path: Path, text: str) -> None:
    path.write_text((text or "").strip(), encoding="utf-8")


def month_title(y: int, m: int) -> str:
    return f"{y}년 {m:02d}월"


def days_in_month(y: int, m: int) -> list[date]:
    _, last = calendar.monthrange(y, m)
    return [date(y, m, i) for i in range(1, last + 1)]


def fmt_mmdd(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}"


def weekday_kr(d: date) -> str:
    return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]


# -----------------------------
# 데이터 로드
# -----------------------------
base_map = load_kv(BASE_MENU_PATH, "date", "base_menu")
change_map = load_kv(CHANGE_MENU_PATH, "date", "change_menu")
delivery_map = load_delivery(DELIVERY_PATH)

gongyang_text = read_text(GONGYANG_PATH, DEFAULT_GONGYANG)

idx_df = ensure_csv(MENU_INDEX_PATH, ["name"])
idx_df["name"] = idx_df["name"].astype(str).map(norm_text)
idx_df = idx_df[idx_df["name"].str.len() > 0].drop_duplicates().sort_values("name").reset_index(drop=True)


# -----------------------------
# 사이드바: 월 선택 + 백업/복원
# -----------------------------
today = date.today()
with st.sidebar:
    st.subheader("월 선택")
    y = st.selectbox(
        "년도",
        list(range(2024, 2031)),
        index=list(range(2024, 2031)).index(today.year) if 2024 <= today.year <= 2030 else 2,
    )
    m = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

    st.divider()
    st.subheader("백업/복원 (ZIP)")
    c1, c2 = st.columns(2)

    with c1:
        if st.button("ZIP 백업 생성", use_container_width=True):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            mem = io.BytesIO()
            with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
                for p in [BASE_MENU_PATH, CHANGE_MENU_PATH, DELIVERY_PATH, MENU_INDEX_PATH, GONGYANG_PATH]:
                    if p.exists():
                        z.writestr(p.name, p.read_bytes())
            mem.seek(0)
            st.download_button(
                "다운로드",
                data=mem.getvalue(),
                file_name=f"moms_menu_backup_{ts}.zip",
                mime="application/zip",
                use_container_width=True,
            )

    with c2:
        zip_up = st.file_uploader("ZIP 복원 업로드", type=["zip"])
        if zip_up and st.button("복원 실행", use_container_width=True):
            try:
                zdata = zip_up.getvalue()
                with zipfile.ZipFile(io.BytesIO(zdata), "r") as z:
                    for name in z.namelist():
                        if name in {
                            BASE_MENU_PATH.name,
                            CHANGE_MENU_PATH.name,
                            DELIVERY_PATH.name,
                            MENU_INDEX_PATH.name,
                            GONGYANG_PATH.name,
                        }:
                            (DATA_DIR / name).write_bytes(z.read(name))
                st.success("복원 완료. 새로고침(F5) 후 확인하세요.")
            except Exception as e:
                st.error(f"복원 실패: {e}")


# -----------------------------
# 상단 안내
# -----------------------------
st.markdown(f"## 맘스락 {m:02d}월 식단 변경 프로그램")
st.caption(
    "달력은 1달만 표시됩니다. 날짜를 클릭하면 입력창이 뜨고, 저장 즉시 달력/포스터/문자내용에 반영됩니다."
)


# -----------------------------
# 공양게 편집
# -----------------------------
with st.expander("공양게 문구(편집)"):
    new_g = st.text_area("공양게", gongyang_text, height=140)
    if st.button("공양게 저장"):
        write_text(GONGYANG_PATH, new_g)
        st.success("저장 완료. (필요시 새로고침)")


# -----------------------------
# 메뉴 인덱스 관리(가나다 정렬)
# -----------------------------
with st.expander("메뉴 인덱스 관리 (가나다 순 자동정렬)"):
    a1, a2 = st.columns([2, 1])
    with a1:
        add_name = st.text_input("추가할 메뉴명")
    with a2:
        if st.button("추가", use_container_width=True):
            nm = norm_text(add_name)
            if not nm:
                st.warning("메뉴명을 입력하세요.")
            else:
                tmp = pd.concat([idx_df, pd.DataFrame([{"name": nm}])], ignore_index=True)
                tmp = tmp.drop_duplicates().sort_values("name").reset_index(drop=True)
                save_csv(MENU_INDEX_PATH, tmp)
                st.success("추가 완료. 새로고침(F5) 하세요.")
    st.dataframe(idx_df, use_container_width=True)


# -----------------------------
# 날짜 클릭 입력(대화상자)
# -----------------------------
@st.dialog("식단 입력", width="large")
def edit_day_dialog(d: date):
    ds = d.isoformat()

    cur_base = base_map.get(ds, "")
    cur_change = change_map.get(ds, "")
    cur_delivery = delivery_map.get(ds, "Y")

    st.markdown(f"### {ds} ({weekday_kr(d)})")

    idx_list = idx_df["name"].tolist()

    # 기본메뉴
    base_pick = st.selectbox(
        "기본메뉴 (인덱스 선택)",
        ["(선택없음)"] + idx_list,
        index=(idx_list.index(cur_base) + 1) if cur_base in idx_list else 0,
    )
    base_text = st.text_input(
        "기본메뉴 (직접 입력)",
        value=cur_base if base_pick == "(선택없음)" else base_pick,
    )

    # 변경메뉴
    chg_pick = st.selectbox(
        "변경메뉴 (인덱스 선택)",
        ["(변경없음)"] + idx_list,
        index=(idx_list.index(cur_change) + 1) if cur_change in idx_list else 0,
    )
    chg_text = st.text_input(
        "변경메뉴 (직접 입력)",
        value=cur_change if chg_pick == "(변경없음)" else chg_pick,
    )

    # 배달불요
    delivery_n = st.checkbox("배달불요 (체크하면 배달 N)", value=(cur_delivery == "N"))

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("저장", use_container_width=True):
            b = norm_text(base_text)
            c = norm_text(chg_text)

            if b:
                base_map[ds] = b
            else:
                base_map.pop(ds, None)

            if c:
                change_map[ds] = c
            else:
                change_map.pop(ds, None)

            delivery_map[ds] = "N" if delivery_n else "Y"

            save_kv(BASE_MENU_PATH, "date", "base_menu", base_map)
            save_kv(CHANGE_MENU_PATH, "date", "change_menu", change_map)
            save_delivery(DELIVERY_PATH, delivery_map)

            st.success("저장 완료")
            st.rerun()

    with c2:
        if st.button("이 날짜 초기화", use_container_width=True):
            base_map.pop(ds, None)
            change_map.pop(ds, None)
            delivery_map.pop(ds, None)

            save_kv(BASE_MENU_PATH, "date", "base_menu", base_map)
            save_kv(CHANGE_MENU_PATH, "date", "change_menu", change_map)
            save_delivery(DELIVERY_PATH, delivery_map)

            st.success("초기화 완료")
            st.rerun()

    with c3:
        if st.button("닫기", use_container_width=True):
            st.rerun()


# -----------------------------
# 달력(1달) - 앱 화면
# -----------------------------
st.divider()
st.markdown("### 📅 달력 (1개월)")

cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
month_days = list(cal.itermonthdates(y, m))
rows = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]

# 달력 셀 표시: 상태 배지 + 최소 텍스트
for r in rows:
    cols = st.columns(7)
    for i, d in enumerate(r):
        with cols[i]:
            if d.month != m:
                st.write(" ")
                continue

            ds = d.isoformat()
            b = base_map.get(ds, "")
            c = change_map.get(ds, "")
            dn = (delivery_map.get(ds, "Y") == "N")

            # 버튼 라벨(짧게)
            lines = [f"{d.day:02d}"]
            if dn:
                lines.append("배달불요")
            elif c:
                lines.append("변경")
            elif b:
                lines.append("기본")
            label = "\n".join(lines)

            if st.button(label, key=f"day_{ds}", use_container_width=True):
                edit_day_dialog(d)


# -----------------------------
# 업체 문자용 텍스트 생성
# -----------------------------
def build_sms_text(y: int, m: int) -> str:
    days = [d for d in days_in_month(y, m) if d.weekday() < 5]  # 평일만
    no_list: list[tuple[date, str]] = []
    chg_list: list[tuple[date, str]] = []

    for d in days:
        ds = d.isoformat()
        dn = (delivery_map.get(ds, "Y") == "N")
        chg = (change_map.get(ds, "") or "").strip()
        if dn:
            no_list.append((d, "배달불요"))
        if chg:
            chg_list.append((d, chg))

    lines: list[str] = []
    lines.append("동약협회입니다.")
    lines.append(f"{y}년 {m:02d}월 도시락 변경/배달불요 내역입니다.")
    lines.append("")

    if no_list:
        lines.append("🚫【배달불요】")
        for d, _ in no_list:
            lines.append(f"▶ {fmt_mmdd(d)}({weekday_kr(d)}) : 배달불요")
        lines.append("")

    if chg_list:
        lines.append("🟨【변경메뉴】")
        for d, menu in chg_list:
            lines.append(f"▶ {fmt_mmdd(d)}({weekday_kr(d)}) : {menu}")
        lines.append("")

    if (not no_list) and (not chg_list):
        lines.append("이번 달 변경/배달불요 내역이 없습니다.")
        lines.append("")

    lines.append("감사합니다.")
    return "\n".join(lines)


st.divider()
st.markdown("### 📩 업체 문자 발송용(복사/붙여넣기)")
sms_text = build_sms_text(y, m)
st.text_area("아래 내용을 그대로 복사해서 문자로 보내세요.", value=sms_text, height=260)


# -----------------------------
# 포스터(A4 1페이지) HTML 생성
# - 로고 없음
# - 맘스락 전화번호 없음
# - 동약협회 전화번호 고정
# - 공양게 전체 표시(Noto Sans KR, 줄임 없음)
# - 달력: 기본/변경/배달불요 확실 구분(바탕색+좌측컬러바+배지)
# -----------------------------
def month_table_html(y: int, m: int) -> str:
    cal = calendar.Calendar(firstweekday=0)
    month_days = list(cal.itermonthdates(y, m))
    rows = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]

    out = []
    for r in rows:
        tds = []
        for d in r:
            if d.month != m:
                tds.append('<td class="cell other"></td>')
                continue

            ds = d.isoformat()
            b = html.escape((base_map.get(ds, "") or "").strip())
            c = html.escape((change_map.get(ds, "") or "").strip())
            dn = (delivery_map.get(ds, "Y") == "N")

            cls = ["cell"]
            badge = ""
            body = ""

            if dn:
                cls.append("no")
                badge = '<span class="badge badge-no">배달불요</span>'
                body = ""
            elif c:
                cls.append("chg")
                badge = '<span class="badge badge-chg">변경</span>'
                body = f'<div class="menu"><b>{c}</b></div>'
            elif b:
                cls.append("base")
                badge = '<span class="badge badge-base">기본</span>'
                body = f'<div class="menu">{b}</div>'
            else:
                cls.append("empty")

            tds.append(
                f"""
                <td class="{' '.join(cls)}">
                  <div class="toprow">
                    <div class="day">{d.day}</div>
                    <div class="badges">{badge}</div>
                  </div>
                  {body}
                </td>
                """
            )
        out.append("<tr>" + "".join(tds) + "</tr>")

    head = "".join([f"<th>{w}</th>" for w in ["월", "화", "수", "목", "금", "토", "일"]])
    return f"""
    <table class="cal">
      <thead><tr>{head}</tr></thead>
      <tbody>
        {''.join(out)}
      </tbody>
    </table>
    """


def build_poster_html(y: int, m: int) -> str:
    mt = html.escape(month_title(y, m))
    main_title = f"맘스락 {m:02d}월<br/>식단(배달) 변경"
    gong = html.escape(read_text(GONGYANG_PATH, DEFAULT_GONGYANG)).replace("\n", "<br/>")
    table = month_table_html(y, m)

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
    margin: 0;
    font-family: "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }}
  .sheet {{
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    box-sizing: border-box;
    background: #fff;
    border-radius: 12px;
  }}
  .content {{
    padding: 10mm;
    box-sizing: border-box;
  }}

  /* 상단: 좌(맘스락) / 중(제목) / 우(동약협회+전화) */
  .top {{
    display: grid;
    grid-template-columns: 1fr 1.4fr 1fr;
    gap: 10mm;
    align-items: center;
  }}
  .box {{
    border: 1px solid rgba(0,0,0,0.14);
    border-radius: 16px;
    padding: 14px 14px;
    min-height: 68px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    background: #fff;
  }}
  .box .t {{
    font-size: 24px;
    font-weight: 950;
    line-height: 1.05;
    letter-spacing: -0.2px;
  }}
  .box .p {{
    margin-top: 6px;
    font-size: 16px;
    font-weight: 900;
    opacity: 0.9;
    letter-spacing: -0.1px;
  }}

  .centerTitle {{
    text-align: center;
  }}
  .centerTitle .main {{
    font-size: 36px;
    font-weight: 950;
    line-height: 1.06;
    letter-spacing: -0.6px;
  }}
  .centerTitle .sub {{
    margin-top: 6px;
    font-size: 18px;
    font-weight: 900;
    opacity: 0.85;
  }}

  /* 공양게: 전체 보이게(줄임 금지) + Noto Sans KR */
  .gong {{
    margin-top: 6mm;
    padding: 12px 14px;
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(0,0,0,0.03);
    font-family: "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
    font-size: 16px;
    font-weight: 800;
    line-height: 1.35;
    text-align: center;
  }}

  /* 달력 */
  .calWrap {{
    margin-top: 7mm;
    border-radius: 16px;
    padding: 10px;
    border: 1px solid rgba(0,0,0,0.12);
    background: #fff;
  }}
  table.cal {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 7px;
    table-layout: fixed;
  }}
  .cal th {{
    font-size: 14px;
    padding: 7px 4px;
    text-align: center;
    background: rgba(0,0,0,0.06);
    border-radius: 12px;
    font-weight: 950;
  }}
  .cal td.cell {{
    vertical-align: top;
    border-radius: 14px;
    padding: 9px 9px;
    height: 92px;
    border: 1px solid rgba(0,0,0,0.10);
    position: relative;
    overflow: hidden;
    background: #fff;
  }}
  .cal td.other {{
    background: rgba(0,0,0,0.02);
    border: 1px dashed rgba(0,0,0,0.08);
  }}

  /* 상태별: 바탕색 + 좌측 컬러바 (인쇄에서 확실) */
  .cal td.base {{
    background: rgba(232, 245, 255, 0.92);
  }}
  .cal td.base::before {{
    content: "";
    position: absolute; left: 0; top: 0; bottom: 0;
    width: 6px;
    background: rgba(0, 120, 255, 0.45);
  }}

  .cal td.chg {{
    background: rgba(255, 243, 197, 0.95);
  }}
  .cal td.chg::before {{
    content: "";
    position: absolute; left: 0; top: 0; bottom: 0;
    width: 6px;
    background: rgba(255, 170, 0, 0.60);
  }}

  .cal td.no {{
    background: rgba(255, 218, 218, 0.95);
  }}
  .cal td.no::before {{
    content: "";
    position: absolute; left: 0; top: 0; bottom: 0;
    width: 6px;
    background: rgba(220, 0, 0, 0.60);
  }}

  .toprow {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
  }}
  .day {{
    font-size: 16px;
    font-weight: 950;
  }}

  .badge {{
    display: inline-block;
    font-size: 12px;
    font-weight: 950;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(255,255,255,0.78);
    white-space: nowrap;
  }}
  .badge-base {{ border-color: rgba(0,120,255,0.25); }}
  .badge-chg  {{ border-color: rgba(255,170,0,0.35); }}
  .badge-no   {{ border-color: rgba(220,0,0,0.35); }}

  .menu {{
    margin-top: 8px;
    font-size: 13px;
    line-height: 1.22;
    word-break: keep-all;
  }}
</style>
</head>
<body>
  <div class="sheet">
    <div class="content">
      <div class="top">
        <div class="box">
          <div class="t">맘스락</div>
          <div class="p">&nbsp;</div>
        </div>

        <div class="centerTitle">
          <div class="main">{main_title}</div>
          <div class="sub">{mt}</div>
        </div>

        <div class="box" style="text-align:right;">
          <div class="t">동약협회</div>
          <div class="p">☎ {ASSOC_PHONE_FIXED}</div>
        </div>
      </div>

      <div class="gong">{gong}</div>

      <div class="calWrap">
        {table}
      </div>
    </div>
  </div>
</body>
</html>
"""


st.divider()
st.markdown("### 2) 포스터(스크린샷용) 미리보기")
poster_html = build_poster_html(y, m)
components.html(poster_html, height=1100, scrolling=True)

st.markdown("### 3) 업체 전달용 파일 출력 (A4 1페이지 최적화)")
st.caption("다운로드 → 크롬/엣지에서 열기 → Ctrl+P → ‘PDF로 저장’ → ‘한 페이지에 맞춤’")

st.download_button(
    "A4 출력용 HTML 다운로드",
    data=poster_html.encode("utf-8"),
    file_name=f"맘스락_{y}_{m:02d}_A4_출력용.html",
    mime="text/html",
    use_container_width=True,
)
