# app.py  (통째로 교체용)
# 실행: python -m streamlit run app.py

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, timedelta
import calendar
import io
import zipfile
import unicodedata

import pandas as pd
import streamlit as st

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

def debug_data_status():
    rows = []
    for fname, path in TARGET_FILES.items():
        if path.exists():
            size = path.stat().st_size
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            try:
                df = pd.read_csv(path, dtype=str).fillna("")
                shape = f"{df.shape[0]} x {df.shape[1]}"
            except Exception as e:
                shape = f"읽기 오류: {e}"
        else:
            size, mtime, shape = 0, "", "없음"
        rows.append({"파일": fname, "수정시각": mtime, "크기(bytes)": size, "행x열": shape, "경로": str(path)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

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
    st.caption("현재 앱 데이터 폴더")
    st.code(str(DATA_DIR), language="text")
    st.caption("CSV 상태(수정시각/행수)")
    debug_data_status()

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
# 달력(이전 UI 복귀: 칸 안에 기본/변경/배달불요 표시)
# -----------------------------
def cell_label(d: date) -> str:
    base = get_value(base_df, d, "base_menu")
    change = get_value(change_df, d, "change_menu")
    delivery = get_delivery_flag(delivery_df, d)  # Y=배달, N=배달불요

    lines = []
    lines.append(f"{d.day:02d}")
    if base:
        lines.append(f"기본: {base}")
    else:
        lines.append("기본:")  # 빈칸도 라인 유지(이전처럼)

    if change:
        lines.append(f"변경: {change}")
    else:
        lines.append("변경:")

    if delivery == "Y":
        lines.append("배달: O")
    else:
        lines.append("배달: X(불요)")

    return "\n".join(lines)

def open_editor(d: date):
    st.session_state.last_clicked = _iso(d)

# 요일 헤더
weekdays = ["월", "화", "수", "목", "금", "토", "일"]
hcols = st.columns(7)
for i, w in enumerate(weekdays):
    hcols[i].markdown(f"**{w}**")

cal = calendar.Calendar(firstweekday=0)  # 월요일 시작
month_days = list(cal.itermonthdates(y, m))

# 6주(42칸) 고정
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

        label = cell_label(d) if in_month else ""
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
# 하단: 월간 요약(업체 전달용)
# -----------------------------
st.divider()
st.subheader("업체 전달용 요약(월간)")

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
