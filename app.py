# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, timedelta
import calendar
import io
import zipfile
import unicodedata
import base64

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
DELIVERY_PATH = DATA_DIR / "delivery.csv"           # date,delivery (Y/N)  -> Y만 저장(배달 필요)
MENU_INDEX_PATH = DATA_DIR / "menu_index.csv"       # name

# -----------------------------
# 유틸
# -----------------------------
def _today() -> date:
    return date.today()

def _iso(d: date) -> str:
    return d.isoformat()

def _parse_iso(s: str) -> date:
    return date.fromisoformat(s)

def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())

def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)

def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8-sig") -> None:
    _atomic_write_bytes(path, text.encode(encoding))

def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns].astype(str).fillna("")

def _write_csv(path: Path, df: pd.DataFrame) -> None:
    _atomic_write_text(path, df.to_csv(index=False), encoding="utf-8-sig")

def _ensure_menu_index_sorted(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["name"] = df["name"].map(_nfc)
    df = df[df["name"] != ""]
    df = df.drop_duplicates(subset=["name"])
    df = df.sort_values("name", kind="mergesort").reset_index(drop=True)
    return df

def load_all():
    base = _read_csv(BASE_MENU_PATH, ["date", "base_menu"])
    change = _read_csv(CHANGE_MENU_PATH, ["date", "change_menu"])
    delivery = _read_csv(DELIVERY_PATH, ["date", "delivery"])
    idx = _read_csv(MENU_INDEX_PATH, ["name"])
    idx = _ensure_menu_index_sorted(idx)
    return base, change, delivery, idx

def upsert_by_date(df: pd.DataFrame, d: date, col: str, value: str) -> pd.DataFrame:
    df = df.copy()
    ds = _iso(d)
    value = _nfc(value)
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, col] = value
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, col: value}])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df

def delete_by_date_if_empty(df: pd.DataFrame, d: date, col: str) -> pd.DataFrame:
    df = df.copy()
    ds = _iso(d)
    hit = df[df["date"] == ds]
    if hit.empty:
        return df
    v = _nfc(hit.iloc[0][col])
    if v == "":
        df = df[df["date"] != ds].reset_index(drop=True)
    return df

def set_delivery(df: pd.DataFrame, d: date, yn: str) -> pd.DataFrame:
    """
    delivery.csv는 '배달 필요(Y)'만 저장.
    체크 해제(배달불요)면 해당 날짜 레코드 삭제.
    """
    df = df.copy()
    ds = _iso(d)
    yn = "Y" if yn == "Y" else "N"
    if yn == "N":
        df = df[df["date"] != ds].reset_index(drop=True)
        return df
    if (df["date"] == ds).any():
        df.loc[df["date"] == ds, "delivery"] = "Y"
    else:
        df = pd.concat([df, pd.DataFrame([{"date": ds, "delivery": "Y"}])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    return df

def get_value(df: pd.DataFrame, d: date, col: str) -> str:
    ds = _iso(d)
    hit = df[df["date"] == ds]
    if hit.empty:
        return ""
    return _nfc(hit.iloc[0][col])

def get_delivery_flag(df: pd.DataFrame, d: date) -> str:
    # 레코드가 있으면 Y(배달 필요), 없으면 N(배달불요)
    ds = _iso(d)
    return "Y" if not df[df["date"] == ds].empty else "N"

# -----------------------------
# ZIP 백업/복원 (DATA_DIR로 강제 덮어쓰기)
# -----------------------------
TARGET_FILES = {
    "base_menu.csv": BASE_MENU_PATH,
    "change_menu.csv": CHANGE_MENU_PATH,
    "delivery.csv": DELIVERY_PATH,
    "menu_index.csv": MENU_INDEX_PATH,
}

def make_backup_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, path in TARGET_FILES.items():
            if path.exists():
                zf.writestr(fname, path.read_bytes())
    return buf.getvalue()

def restore_from_zip(uploaded) -> tuple[bool, str]:
    if uploaded is None:
        return False, "ZIP 파일이 없습니다."
    raw = uploaded.getvalue()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as e:
        return False, f"ZIP 읽기 오류: {e}"

    found: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        name_only = Path(info.filename).name  # 폴더 경로 제거
        if name_only in TARGET_FILES:
            found[name_only] = info

    missing = sorted(list(set(TARGET_FILES.keys()) - set(found.keys())))
    if missing:
        return False, "ZIP 안에 필요한 파일이 없습니다: " + ", ".join(missing)

    for fname, info in found.items():
        _atomic_write_bytes(TARGET_FILES[fname], zf.read(info))

    return True, "복원 완료: data 폴더의 CSV를 강제로 교체했습니다."

# -----------------------------
# 로고 base64
# -----------------------------
def file_to_data_uri(uploaded) -> str:
    if uploaded is None:
        return ""
    b = uploaded.getvalue()
    mime = uploaded.type or "image/png"
    return f"data:{mime};base64,{base64.b64encode(b).decode('utf-8')}"

# -----------------------------
# 세션 상태
# -----------------------------
if "ym" not in st.session_state:
    t = _today()
    st.session_state.ym = (t.year, t.month)

if "last_clicked" not in st.session_state:
    st.session_state.last_clicked = None  # iso date string

# -----------------------------
# 상단
# -----------------------------
st.title("맘스락 식단 변경 프로그램")

base_df, change_df, delivery_df, idx_df = load_all()

# -----------------------------
# 사이드바
# -----------------------------
with st.sidebar:
    st.header("1) 메뉴 인덱스 관리")
    st.caption("가나다 순 자동 정렬")
    new_name = st.text_input("메뉴 추가", placeholder="예: 소고기무국")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("추가", use_container_width=True):
            n = _nfc(new_name)
            if n:
                idx_df2 = pd.concat([idx_df, pd.DataFrame([{"name": n}])], ignore_index=True)
                idx_df2 = _ensure_menu_index_sorted(idx_df2)
                _write_csv(MENU_INDEX_PATH, idx_df2)
                st.rerun()
    with c2:
        if st.button("전체 정렬 저장", use_container_width=True):
            idx_df2 = _ensure_menu_index_sorted(idx_df)
            _write_csv(MENU_INDEX_PATH, idx_df2)
            st.rerun()

    if not idx_df.empty:
        del_target = st.selectbox("삭제할 메뉴", ["(선택)"] + idx_df["name"].tolist())
        if st.button("선택 삭제", use_container_width=True):
            if del_target != "(선택)":
                idx_df2 = idx_df[idx_df["name"] != del_target].reset_index(drop=True)
                _write_csv(MENU_INDEX_PATH, idx_df2)
                st.rerun()

    st.divider()
    st.header("2) 백업/복원(ZIP)")
    st.download_button(
        "📦 데이터 ZIP 다운로드",
        data=make_backup_zip_bytes(),
        file_name="diet_data_backup.zip",
        mime="application/zip",
        use_container_width=True,
    )
    up = st.file_uploader("ZIP 업로드(복원)", type=["zip"])
    if st.button("ZIP에서 복원(강제 덮어쓰기)", type="primary", use_container_width=True):
        ok, msg = restore_from_zip(up)
        st.success(msg) if ok else st.error(msg)
        st.rerun()

    st.divider()
    st.header("3) 포스터 로고")
    st.caption("포스터 상단 좌/우 로고를 업로드하면 그림에 반영됩니다.")
    moms_logo_up = st.file_uploader("왼쪽(MOMS) 로고 업로드", type=["png", "jpg", "jpeg", "webp"], key="momslogo")
    kapma_logo_up = st.file_uploader("오른쪽(동약협회) 로고 업로드", type=["png", "jpg", "jpeg", "webp"], key="kapmalogo")

moms_logo_uri = file_to_data_uri(st.session_state.get("momslogo"))
kapma_logo_uri = file_to_data_uri(st.session_state.get("kapmalogo"))

# -----------------------------
# 월 선택
# -----------------------------
st.subheader("월 선택")
y, m = st.session_state.ym
years = list(range(2024, 2036))
months = list(range(1, 13))

cY, cM, cNow = st.columns([1, 1, 1])
with cY:
    y = st.selectbox("년도", years, index=years.index(y) if y in years else 0)
with cM:
    m = st.selectbox("월", months, index=months.index(m) if m in months else 0)
with cNow:
    if st.button("이번 달", use_container_width=True):
        t = _today()
        st.session_state.ym = (t.year, t.month)
        st.rerun()
st.session_state.ym = (y, m)

# -----------------------------
# 달력(입력용) - 간단 표시 + 클릭 입력창
# -----------------------------
def cell_label_input(d: date) -> str:
    base = get_value(base_df, d, "base_menu")
    change = get_value(change_df, d, "change_menu")
    delivery = get_delivery_flag(delivery_df, d)  # Y=배달, N=배달불요

    lines = [f"{d.day:02d}"]
    if delivery != "Y":
        lines.append("배달불요")
    if change:
        lines.append(f"변경: {change}")
    elif base:
        lines.append(base)
    return "\n".join(lines)

def open_editor(d: date):
    st.session_state.last_clicked = _iso(d)

weekdays = ["월", "화", "수", "목", "금", "토", "일"]
hcols = st.columns(7)
for i, w in enumerate(weekdays):
    hcols[i].markdown(f"**{w}**")

cal = calendar.Calendar(firstweekday=0)
month_days = list(cal.itermonthdates(y, m))
if len(month_days) < 42:
    last = month_days[-1]
    month_days = month_days + [last + timedelta(days=i) for i in range(1, 42 - len(month_days) + 1)]
else:
    month_days = month_days[:42]

for row in range(6):
    cols = st.columns(7)
    for col in range(7):
        d = month_days[row * 7 + col]
        in_month = (d.month == m)
        label = cell_label_input(d) if in_month else ""
        disabled = not in_month
        if cols[col].button(label if label else " ", key=f"daybtn-{y}-{m}-{row}-{col}", disabled=disabled, use_container_width=True):
            open_editor(d)

# -----------------------------
# 날짜 편집 Dialog
# -----------------------------
clicked_iso = st.session_state.last_clicked
if clicked_iso:
    clicked_date = _parse_iso(clicked_iso)

    @st.dialog("식단 입력(저장 후 달력으로 복귀)")
    def edit_dialog(d: date):
        base_df2, change_df2, delivery_df2, idx_df2 = load_all()

        st.write(f"📅 선택 날짜: **{d.year}-{d.month:02d}-{d.day:02d}**")

        current_base = get_value(base_df2, d, "base_menu")
        current_change = get_value(change_df2, d, "change_menu")
        current_delivery = get_delivery_flag(delivery_df2, d)

        delivery_ok = st.checkbox("배달 필요(체크 해제 시 배달불요)", value=(current_delivery == "Y"))

        st.divider()

        idx_list = idx_df2["name"].tolist() if not idx_df2.empty else []
        base_choices = ["(직접입력)"] + idx_list
        change_choices = ["(없음)"] + idx_list + ["(직접입력)"]

        st.markdown("**기본 메뉴**")
        base_mode = st.selectbox("기본 선택", base_choices, index=0, key="base_mode")
        base_text = st.text_input("기본(직접 입력)", value=current_base, key="base_text")
        if base_mode != "(직접입력)":
            base_text = base_mode

        st.markdown("**변경 메뉴**")
        change_mode = st.selectbox("변경 선택", change_choices, index=0, key="change_mode")
        change_text = st.text_input("변경(직접 입력)", value=current_change, key="change_text")
        if change_mode == "(없음)":
            change_text = ""
        elif change_mode != "(직접입력)":
            change_text = change_mode

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 저장", type="primary", use_container_width=True):
                base_df3 = upsert_by_date(base_df2, d, "base_menu", base_text)
                base_df3 = delete_by_date_if_empty(base_df3, d, "base_menu")

                change_df3 = upsert_by_date(change_df2, d, "change_menu", change_text)
                change_df3 = delete_by_date_if_empty(change_df3, d, "change_menu")

                delivery_df3 = set_delivery(delivery_df2, d, "Y" if delivery_ok else "N")

                _write_csv(BASE_MENU_PATH, base_df3)
                _write_csv(CHANGE_MENU_PATH, change_df3)
                _write_csv(DELIVERY_PATH, delivery_df3)

                st.session_state.last_clicked = None
                st.rerun()
        with c2:
            if st.button("닫기(저장 안함)", use_container_width=True):
                st.session_state.last_clicked = None
                st.rerun()

    edit_dialog(clicked_date)

# -----------------------------
# 4) 포스터(출력용 1장) - PNG 다운로드
# -----------------------------
st.divider()
st.header("4) 포스터(출력용 1장) 미리보기 / PNG 저장")

def build_weekday_grid(year: int, month: int):
    """
    예시처럼 '월~금'만 포스터에 배치.
    """
    cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
    days = list(cal.itermonthdates(year, month))

    # 주 단위로 잘라서 월~금만 남김
    weeks = [days[i:i+7] for i in range(0, len(days), 7)]
    rows = []
    for w in weeks:
        wk = w[:5]  # 월~금
        # 해당 월 날짜가 하나도 없으면 스킵
        if not any(d.month == month for d in wk):
            continue
        rows.append(wk)
    # 최소 5행 정도로 맞추고 싶으면 여기서 패딩 가능(지금은 실제 주수만)
    return rows

wd_kr = ["월", "화", "수", "목", "금", "토", "일"]

rows = build_weekday_grid(y, m)

title = f"맘스락 {m:02d}월<br/>식단 변경"
poster_filename = f"맘스락_{y}_{m:02d}_식단변경.png"

def esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

# 포스터 셀 HTML 생성
cells_html = ""
for wk in rows:
    cells_html += '<div class="row">'
    for d in wk:
        if d.month != m:
            # 빈칸(점선)
            cells_html += '<div class="cell empty"></div>'
            continue

        base = esc(get_value(base_df, d, "base_menu"))
        change = esc(get_value(change_df, d, "change_menu"))
        delivery = get_delivery_flag(delivery_df, d)  # Y=배달, N=배달불요

        # 스타일 결정
        cls = "cell"
        badge = ""
        change_block = ""
        menu_main = base

        if delivery != "Y":
            cls += " nodlv"
            badge = '<span class="badge nodlv">배달불요</span>'

        if change:
            cls += " changed"
            badge = (badge + ' ' if badge else '') + '<span class="badge changed">변경</span>'
            menu_main = base  # 기본도 보여주되(예시처럼)
            change_block = f'<div class="change">{change}</div>'

        # 요일 표시(월~금)
        wd = wd_kr[d.weekday()]
        cells_html += f"""
        <div class="{cls}">
          <div class="top">
            <div class="day">{d.day:02d} <span class="wd">({wd})</span></div>
            <div class="badges">{badge}</div>
          </div>
          <div class="menu">{menu_main}</div>
          {change_block}
        </div>
        """
    cells_html += "</div>"

# 로고(없으면 텍스트 박스)
left_logo_html = (
    f'<img class="logo-img" src="{moms_logo_uri}" />'
    if moms_logo_uri
    else '<div class="logo-text"><b>MOMS</b></div>'
)
right_logo_html = (
    f'<img class="logo-img" src="{kapma_logo_uri}" />'
    if kapma_logo_uri
    else '<div class="logo-text"><b>동약협회</b></div>'
)

poster_html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{
    margin:0; padding:0; background:#ffffff;
    font-family: "Noto Sans KR","Malgun Gothic",system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  }}
  .wrap {{
    width: 760px;
    padding: 18px 18px 14px 18px;
    box-sizing: border-box;
    background: #fff;
  }}
  .header {{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom: 10px;
  }}
  .logo-box {{
    width: 210px; height: 74px;
    border: 1.5px solid rgba(0,0,0,0.15);
    border-radius: 18px;
    display:flex; align-items:center; justify-content:center;
    overflow:hidden;
    background:#fff;
  }}
  .logo-img {{ max-width: 92%; max-height: 92%; object-fit: contain; }}
  .logo-text {{ font-size: 28px; color:#111; }}
  .title {{
    flex: 1;
    text-align:center;
    font-weight: 900;
    font-size: 34px;
    line-height: 1.05;
    color: #111;
  }}

  .dow {{
    display:grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin: 8px 0 6px 0;
  }}
  .dow div {{
    text-align:center;
    font-weight: 800;
    color:#111;
  }}

  .grid {{
    display:flex;
    flex-direction:column;
    gap: 10px;
  }}
  .row {{
    display:grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
  }}
  .cell {{
    border: 1.6px solid rgba(0,0,0,0.25);
    border-radius: 16px;
    padding: 10px 10px 8px 10px;
    min-height: 92px;
    box-sizing: border-box;
    background:#fff;
  }}
  .cell.empty {{
    border: 2px dashed rgba(0,0,0,0.18);
    background: #fff;
  }}
  .cell.nodlv {{
    background: #fff3f4;
    border-color: rgba(216, 65, 90, 0.55);
  }}
  .cell.changed {{
    background: #fff7e8;
    border-color: rgba(222, 150, 35, 0.6);
  }}
  .top {{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    margin-bottom: 6px;
    gap: 6px;
  }}
  .day {{
    font-weight: 900;
    color:#111;
  }}
  .wd {{ font-weight: 700; color: rgba(0,0,0,0.55); font-size: 12px; }}
  .badges {{ display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }}
  .badge {{
    font-size: 12px;
    font-weight: 800;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1.4px solid rgba(0,0,0,0.18);
    background: #fff;
    color:#111;
    white-space:nowrap;
  }}
  .badge.nodlv {{
    border-color: rgba(216, 65, 90, 0.55);
    color: rgb(190, 30, 60);
    background: rgba(216, 65, 90, 0.06);
  }}
  .badge.changed {{
    border-color: rgba(222, 150, 35, 0.6);
    color: rgb(175, 85, 0);
    background: rgba(222, 150, 35, 0.10);
  }}

  .menu {{
    font-size: 16px;
    font-weight: 750;
    color:#111;
    line-height: 1.15;
    word-break: keep-all;
  }}
  .change {{
    margin-top: 6px;
    font-size: 16px;
    font-weight: 900;
    color: rgb(200, 30, 45);
    line-height: 1.15;
    word-break: keep-all;
  }}

  .hint {{
    margin-top: 10px;
    font-size: 12px;
    color: rgba(0,0,0,0.55);
    text-align:right;
  }}

  .btnbar {{
    display:flex;
    gap: 10px;
    margin: 10px 0 14px 0;
    align-items:center;
  }}
  button {{
    border: 0;
    border-radius: 10px;
    padding: 10px 12px;
    font-weight: 800;
    cursor: pointer;
  }}
  #btnCapture {{ background:#111; color:#fff; }}
  #downloadLink {{
    display:none;
    font-weight: 800;
    text-decoration: none;
    padding: 10px 12px;
    border-radius: 10px;
    background: #1f7a1f;
    color:#fff;
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="btnbar">
      <button id="btnCapture">PNG로 저장</button>
      <a id="downloadLink" download="{poster_filename}">다운로드</a>
      <span style="font-size:12px;color:rgba(0,0,0,0.55);">※ 버튼 클릭 → PNG 다운로드 → 카톡/문자에 첨부</span>
    </div>

    <div id="poster">
      <div class="header">
        <div class="logo-box">{left_logo_html}</div>
        <div class="title">{title}</div>
        <div class="logo-box">{right_logo_html}</div>
      </div>

      <div class="dow">
        <div>월</div><div>화</div><div>수</div><div>목</div><div>금</div>
      </div>

      <div class="grid">
        {cells_html}
      </div>

      <div class="hint">{y}-{m:02d} / generated by diet-app</div>
    </div>
  </div>

<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
  const btn = document.getElementById("btnCapture");
  const link = document.getElementById("downloadLink");

  btn.addEventListener("click", async () => {{
    link.style.display = "none";
    const target = document.getElementById("poster");

    const canvas = await html2canvas(target, {{
      backgroundColor: "#ffffff",
      scale: 2
    }});

    canvas.toBlob((blob) => {{
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.style.display = "inline-block";
      link.textContent = "다운로드";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }}, "image/png");
  }});
</script>
</body>
</html>
"""

# 포스터 표시
components.html(poster_html, height=980, scrolling=True)

# -----------------------------
# 하단: 업체 전달용 텍스트(옵션)
# -----------------------------
st.divider()
st.subheader("업체 전달용 요약(월간 텍스트)")

last_day = date(y, m, calendar.monthrange(y, m)[1])
all_days = [date(y, m, d) for d in range(1, last_day.day + 1)]

lines: list[str] = []
lines.append("동약협회입니다.")
lines.append(f"{y}년 {m:02d}월 도시락 변경/배달불요 내역입니다.")

no_delivery = [d for d in all_days if get_delivery_flag(delivery_df, d) != "Y"]
if no_delivery:
    lines.append("")
    lines.append("【배달불요】")
    for d in no_delivery:
        wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
        lines.append(f"▶ {m:02d}/{d.day:02d}({wd}) : 배달불요")

changed = [d for d in all_days if get_value(change_df, d, "change_menu") != ""]
if changed:
    lines.append("")
    lines.append("【변경메뉴】")
    for d in changed:
        wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
        cm = get_value(change_df, d, "change_menu")
        lines.append(f"▶ {m:02d}/{d.day:02d}({wd}) : {cm}")

st.text_area("복사해서 문자/카톡에 붙여넣기", "\n".join(lines), height=220)
