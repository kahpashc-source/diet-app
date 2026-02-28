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
import textwrap

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ✅ 이미지(포스터 PNG/PDF) 생성용
from PIL import Image, ImageDraw, ImageFont


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
# 폰트 찾기 (Noto Sans KR 우선)
# -----------------------------
def find_korean_font() -> str | None:
    candidates = [
        # Linux common
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        # Windows common (로컬 실행 시)
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    fp = find_korean_font()
    if fp:
        try:
            return ImageFont.truetype(fp, size=size)
        except Exception:
            pass
    # 최후 fallback (한글 품질 떨어질 수 있음)
    return ImageFont.load_default()


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
# 사이드바
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
    screenshot_mode = st.toggle("포스터 스크린샷 모드(미리보기 최적화)", value=True)

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
# 상단
# -----------------------------
st.markdown(f"## 맘스락 {m:02d}월 식단 변경 프로그램")
st.caption("달력은 1달만 표시됩니다. 날짜 클릭 → 입력 → 저장 즉시 달력/포스터/문자내용 반영")


# -----------------------------
# 공양게 편집
# -----------------------------
with st.expander("공양게 문구(편집)"):
    new_g = st.text_area("공양게", gongyang_text, height=140)
    if st.button("공양게 저장"):
        write_text(GONGYANG_PATH, new_g)
        st.success("저장 완료. (필요시 새로고침)")


# -----------------------------
# 메뉴 인덱스 관리
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

    base_pick = st.selectbox(
        "기본메뉴 (인덱스 선택)",
        ["(선택없음)"] + idx_list,
        index=(idx_list.index(cur_base) + 1) if cur_base in idx_list else 0,
    )
    base_text = st.text_input(
        "기본메뉴 (직접 입력)",
        value=cur_base if base_pick == "(선택없음)" else base_pick,
    )

    chg_pick = st.selectbox(
        "변경메뉴 (인덱스 선택)",
        ["(변경없음)"] + idx_list,
        index=(idx_list.index(cur_change) + 1) if cur_change in idx_list else 0,
    )
    chg_text = st.text_input(
        "변경메뉴 (직접 입력)",
        value=cur_change if chg_pick == "(변경없음)" else chg_pick,
    )

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
# 포스터 HTML (A4 1페이지)
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


def build_poster_html(y: int, m: int, screenshot_mode: bool) -> str:
    mt = html.escape(month_title(y, m))
    main_title = f"맘스락 {m:02d}월<br/>식단(배달) 변경"
    gong = html.escape(read_text(GONGYANG_PATH, DEFAULT_GONGYANG)).replace("\n", "<br/>")
    table = month_table_html(y, m)

    pad = "6mm" if screenshot_mode else "10mm"
    cal_spacing = "6px" if screenshot_mode else "7px"
    cell_h = "84px" if screenshot_mode else "92px"
    title_size = "34px" if screenshot_mode else "36px"
    gong_size = "15px" if screenshot_mode else "16px"

    return f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  @page {{ size: A4; margin: 10mm; }}
  html, body {{
    margin: 0;
    font-family: "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    background: #fff;
  }}
  .sheet {{
    width: 210mm; min-height: 297mm; margin: 0 auto;
    box-sizing: border-box; background: #fff; border-radius: 12px;
  }}
  .content {{ padding: {pad}; box-sizing: border-box; }}

  .top {{
    display: grid; grid-template-columns: 1fr 1.4fr 1fr;
    gap: 10mm; align-items: center;
  }}
  .box {{
    border: 1px solid rgba(0,0,0,0.14);
    border-radius: 16px;
    padding: 12px 14px;
    min-height: 62px;
    display: flex; flex-direction: column; justify-content: center;
    background: #fff;
  }}
  .box .t {{ font-size: 24px; font-weight: 950; line-height: 1.05; }}
  .box .p {{ margin-top: 6px; font-size: 16px; font-weight: 900; opacity: 0.9; }}

  .centerTitle {{ text-align: center; }}
  .centerTitle .main {{
    font-size: {title_size};
    font-weight: 950;
    line-height: 1.06;
    letter-spacing: -0.6px;
  }}
  .centerTitle .sub {{ margin-top: 6px; font-size: 18px; font-weight: 900; opacity: 0.85; }}

  .gong {{
    margin-top: 5mm;
    padding: 10px 14px;
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(0,0,0,0.03);
    font-family: "Noto Sans KR", "Malgun Gothic", Arial, sans-serif;
    font-size: {gong_size};
    font-weight: 800;
    line-height: 1.35;
    text-align: center;
  }}

  .calWrap {{
    margin-top: 6mm;
    border-radius: 16px;
    padding: 10px;
    border: 1px solid rgba(0,0,0,0.12);
    background: #fff;
  }}
  table.cal {{ width: 100%; border-collapse: separate; border-spacing: {cal_spacing}; table-layout: fixed; }}
  .cal th {{
    font-size: 14px; padding: 7px 4px; text-align: center;
    background: rgba(0,0,0,0.06);
    border-radius: 12px;
    font-weight: 950;
  }}
  .cal td.cell {{
    vertical-align: top;
    border-radius: 14px;
    padding: 9px 9px;
    height: {cell_h};
    border: 1px solid rgba(0,0,0,0.10);
    position: relative;
    overflow: hidden;
    background: #fff;
  }}
  .cal td.other {{ background: rgba(0,0,0,0.02); border: 1px dashed rgba(0,0,0,0.08); }}

  .cal td.base {{ background: rgba(232,245,255,0.92); }}
  .cal td.base::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
    background: rgba(0,120,255,0.45);
  }}
  .cal td.chg {{ background: rgba(255,243,197,0.95); }}
  .cal td.chg::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
    background: rgba(255,170,0,0.60);
  }}
  .cal td.no {{ background: rgba(255,218,218,0.95); }}
  .cal td.no::before {{
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
    background: rgba(220,0,0,0.60);
  }}

  .toprow {{ display: flex; justify-content: space-between; align-items: center; gap: 6px; }}
  .day {{ font-size: 16px; font-weight: 950; }}
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
  .menu {{ margin-top: 8px; font-size: 13px; line-height: 1.22; word-break: keep-all; }}
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


# -----------------------------
# ✅ 포스터 PNG/PDF 생성 (문자/카톡 전송용)
# -----------------------------
def wrap_korean(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    """간단 줄바꿈: 단어(공백) 기준, 너무 길면 글자 기준으로 보정"""
    text = (text or "").strip()
    if not text:
        return []
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if draw.textlength(cand, font=font) <= max_width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
                cur = w
            else:
                # 단어 자체가 너무 길면 글자 단위로 쪼갬
                tmp = ""
                for ch in w:
                    cand2 = tmp + ch
                    if draw.textlength(cand2, font=font) <= max_width:
                        tmp = cand2
                    else:
                        if tmp:
                            lines.append(tmp)
                        tmp = ch
                cur = tmp
    if cur:
        lines.append(cur)
    return lines


def render_poster_png(y: int, m: int) -> bytes:
    # 크기: A4 비율(세로형) / 문자 전송용으로 1200~1600폭이 적당
    W, H = 1240, 1754  # 약 A4@150dpi 느낌
    margin = 60

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 폰트
    f_box_title = load_font(44)
    f_box_phone = load_font(30)
    f_title = load_font(58)
    f_month = load_font(34)
    f_gong = load_font(30)
    f_week = load_font(28)
    f_day = load_font(28)
    f_badge = load_font(22)
    f_menu = load_font(24)

    # 색
    c_border = (220, 220, 220)
    c_text = (10, 10, 10)
    c_muted = (90, 90, 90)
    c_base_bg = (232, 245, 255)
    c_chg_bg = (255, 243, 197)
    c_no_bg = (255, 218, 218)
    c_base_bar = (100, 170, 255)
    c_chg_bar = (255, 180, 80)
    c_no_bar = (235, 100, 100)

    # 상단 3영역
    top_h = 190
    gap = 40
    left_w = 310
    right_w = 310
    center_w = W - margin * 2 - left_w - right_w - gap * 2

    x0 = margin
    y0 = margin

    def rounded_rect(x, y, w, h, r=22, fill=(255, 255, 255), outline=c_border):
        draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill, outline=outline, width=2)

    # left box (맘스락 / 전화 없음)
    rounded_rect(x0, y0, left_w, top_h)
    draw.text((x0 + 22, y0 + 38), "맘스락", font=f_box_title, fill=c_text)

    # right box (동약협회 / 고정번호)
    xr = x0 + left_w + gap + center_w + gap
    rounded_rect(xr, y0, right_w, top_h)
    rt = "동약협회"
    rp = f"☎ {ASSOC_PHONE_FIXED}"
    tw = draw.textlength(rt, font=f_box_title)
    draw.text((xr + right_w - 22 - tw, y0 + 28), rt, font=f_box_title, fill=c_text)
    pw = draw.textlength(rp, font=f_box_phone)
    draw.text((xr + right_w - 22 - pw, y0 + 100), rp, font=f_box_phone, fill=c_muted)

    # center title
    xc = x0 + left_w + gap
    # 제목 2줄
    t1 = f"맘스락 {m:02d}월"
    t2 = "식단(배달) 변경"
    w1 = draw.textlength(t1, font=f_title)
    w2 = draw.textlength(t2, font=f_title)
    draw.text((xc + (center_w - w1) / 2, y0 + 25), t1, font=f_title, fill=c_text)
    draw.text((xc + (center_w - w2) / 2, y0 + 90), t2, font=f_title, fill=c_text)

    mt = month_title(y, m)
    wm = draw.textlength(mt, font=f_month)
    draw.text((xc + (center_w - wm) / 2, y0 + 150), mt, font=f_month, fill=c_muted)

    # 공양게 박스
    gy_top = y0 + top_h + 26
    gy_h = 190
    rounded_rect(margin, gy_top, W - margin * 2, gy_h, r=22, fill=(248, 248, 248))
    gong = read_text(GONGYANG_PATH, DEFAULT_GONGYANG).strip()
    gong_lines = [ln.strip() for ln in gong.splitlines() if ln.strip()]
    # 전체가 보이도록: 줄바꿈 유지 + 폭에 맞춰 보정
    inner_w = W - margin * 2 - 44
    final_lines: list[str] = []
    for ln in gong_lines:
        final_lines.extend(wrap_korean(draw, ln, f_gong, inner_w))
    # 수직 가운데 배치
    line_h = 40
    total_h = len(final_lines) * line_h
    start_y = gy_top + (gy_h - total_h) / 2
    for i, ln in enumerate(final_lines):
        wln = draw.textlength(ln, font=f_gong)
        draw.text((margin + (W - margin * 2 - wln) / 2, start_y + i * line_h), ln, font=f_gong, fill=c_text)

    # 달력 영역
    cal_top = gy_top + gy_h + 26
    cal_h = H - cal_top - margin
    rounded_rect(margin, cal_top, W - margin * 2, cal_h, r=24, fill=(255, 255, 255), outline=c_border)

    # 달력 그리드
    pad = 18
    grid_x = margin + pad
    grid_y = cal_top + pad
    grid_w = W - margin * 2 - pad * 2
    grid_h = cal_h - pad * 2

    header_h = 44
    cell_gap = 10
    cols = 7

    # 몇 주?
    cal = calendar.Calendar(firstweekday=0)
    month_days = list(cal.itermonthdates(y, m))
    weeks = [month_days[i:i + 7] for i in range(0, len(month_days), 7)]
    rows = len(weeks)

    cell_w = (grid_w - cell_gap * (cols - 1)) / cols
    cell_h = (grid_h - header_h - cell_gap * rows) / rows  # row 사이 gap 포함 느낌

    # 요일 헤더
    week_names = ["월", "화", "수", "목", "금", "토", "일"]
    for i, wname in enumerate(week_names):
        x = grid_x + i * (cell_w + cell_gap)
        y = grid_y
        draw.rounded_rectangle([x, y, x + cell_w, y + header_h], radius=14, fill=(245, 245, 245), outline=None)
        tw = draw.textlength(wname, font=f_week)
        draw.text((x + (cell_w - tw) / 2, y + 8), wname, font=f_week, fill=c_text)

    # 셀
    for r, week in enumerate(weeks):
        for c, d in enumerate(week):
            x = grid_x + c * (cell_w + cell_gap)
            y = grid_y + header_h + cell_gap + r * (cell_h + cell_gap)

            if d.month != m:
                draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=16, fill=(250, 250, 250), outline=(235, 235, 235))
                continue

            ds = d.isoformat()
            base = (base_map.get(ds, "") or "").strip()
            chg = (change_map.get(ds, "") or "").strip()
            dn = (delivery_map.get(ds, "Y") == "N")

            # 상태별 색
            fill = (255, 255, 255)
            bar = None
            badge = None
            badge_border = (210, 210, 210)

            if dn:
                fill = c_no_bg
                bar = c_no_bar
                badge = "배달불요"
                badge_border = c_no_bar
                menu_text = ""
            elif chg:
                fill = c_chg_bg
                bar = c_chg_bar
                badge = "변경"
                badge_border = c_chg_bar
                menu_text = chg
            elif base:
                fill = c_base_bg
                bar = c_base_bar
                badge = "기본"
                badge_border = c_base_bar
                menu_text = base
            else:
                fill = (255, 255, 255)
                bar = None
                badge = ""
                menu_text = ""

            draw.rounded_rectangle([x, y, x + cell_w, y + cell_h], radius=18, fill=fill, outline=c_border, width=2)

            # 좌측 바
            if bar:
                draw.rectangle([x, y, x + 8, y + cell_h], fill=bar)

            # 날짜
            draw.text((x + 14, y + 10), str(d.day), font=f_day, fill=c_text)

            # 배지
            if badge:
                bw = draw.textlength(badge, font=f_badge)
                bx2 = x + cell_w - 14
                bx1 = bx2 - (bw + 18)
                by1 = y + 10
                by2 = by1 + 28
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=14, fill=(255, 255, 255), outline=badge_border, width=2)
                draw.text((bx1 + 9, by1 + 4), badge, font=f_badge, fill=c_text)

            # 메뉴 텍스트(줄바꿈)
            if menu_text:
                max_w = int(cell_w - 24)
                lines = wrap_korean(draw, menu_text, f_menu, max_w)
                lines = lines[:3]  # 너무 많으면 3줄까지만(가독성)
                ty = y + 46
                for ln in lines:
                    draw.text((x + 14, ty), ln, font=f_menu, fill=c_text)
                    ty += 30

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -----------------------------
# 문자 텍스트 생성(요청 형식)
# -----------------------------
def build_sms_text(y: int, m: int) -> str:
    days = [d for d in days_in_month(y, m) if d.weekday() < 5]  # 평일만
    no_list: list[date] = []
    chg_list: list[tuple[date, str]] = []

    for d in days:
        ds = d.isoformat()
        dn = (delivery_map.get(ds, "Y") == "N")
        if dn:
            no_list.append(d)

        chg = (change_map.get(ds, "") or "").strip()
        if chg:
            base = (base_map.get(ds, "") or "").strip()
            msg = f"{base} → {chg}" if base else chg
            chg_list.append((d, msg))

    lines: list[str] = []
    lines.append("동약협회입니다.")
    lines.append(f"{y}년 {m:02d}월 도시락 변경/배달불요 내역입니다.")
    if no_list:
        lines.append("🚫【배달불요】")
        for d in no_list:
            lines.append(f"▶ {fmt_mmdd(d)}({weekday_kr(d)}) : 배달불요")
    if chg_list:
        lines.append("🔁【변경메뉴】")
        for d, msg in chg_list:
            lines.append(f"▶ {fmt_mmdd(d)}({weekday_kr(d)}) : {msg}")
    if (not no_list) and (not chg_list):
        lines.append("이번 달 변경/배달불요 내역이 없습니다.")
    lines.append("감사합니다.")
    return "\n".join(lines)


# -----------------------------
# 2) 포스터 미리보기 + 다운로드(스크린샷/파일)
# -----------------------------
st.divider()
st.markdown("### 2) 포스터(스크린샷용) 미리보기")

poster_html = build_poster_html(y, m, screenshot_mode)

# ✅ 미리보기: 스크린샷 모드에서는 스크롤 최소 + 중앙 정렬
components.html(
    f"""
    <div style="display:flex;justify-content:center;align-items:flex-start;padding:0;margin:0;background:#fff;">
      <div style="width: 920px; max-width: 100%; border: 0; margin:0; padding:0;">
        {poster_html}
      </div>
    </div>
    """,
    height=1040 if screenshot_mode else 1120,
    scrolling=False if screenshot_mode else True,
)

st.markdown("### 3) 파일 다운로드 (문자/카톡 전송용)")
c_dl1, c_dl2, c_dl3 = st.columns([1, 1, 1])

# ✅ PNG 생성(포스터 이미지)
png_bytes = render_poster_png(y, m)

with c_dl1:
    st.download_button(
        "📷 포스터 PNG 다운로드",
        data=png_bytes,
        file_name=f"맘스락_{y}_{m:02d}_포스터.png",
        mime="image/png",
        use_container_width=True,
    )

# ✅ PNG -> PDF (1페이지)
with c_dl2:
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        pdf_buf = io.BytesIO()
        img.save(pdf_buf, format="PDF")  # 1페이지 PDF
        pdf_bytes = pdf_buf.getvalue()
        st.download_button(
            "📄 포스터 PDF 다운로드",
            data=pdf_bytes,
            file_name=f"맘스락_{y}_{m:02d}_포스터.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        st.warning(f"PDF 생성 실패(환경/폰트 문제일 수 있음): {e}")

# ✅ HTML(A4 출력용)
with c_dl3:
    st.download_button(
        "🖨️ A4 출력용 HTML 다운로드",
        data=poster_html.encode("utf-8"),
        file_name=f"맘스락_{y}_{m:02d}_A4_출력용.html",
        mime="text/html",
        use_container_width=True,
    )


# -----------------------------
# 📩 업체 문자 발송용(복사/붙여넣기) - 맨 아래
# -----------------------------
st.divider()
st.markdown("### 📩 업체 문자 발송용(복사/붙여넣기)")
sms_text = build_sms_text(y, m)
st.text_area("아래 내용을 그대로 복사해서 문자로 보내세요.", value=sms_text, height=320)
