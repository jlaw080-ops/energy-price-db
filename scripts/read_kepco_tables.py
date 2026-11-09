#!/usr/bin/env python3
"""한전 전기요금표 PDF에서 요율 숫자를 좌표 기준으로 읽어낸다.

사용법:
    # 어떤 종류의 PDF인지, 글자가 들어있는지 먼저 확인
    python3 scripts/read_kepco_tables.py --survey

    # 특정 영역의 시간대별 요율 읽기 (x0,y0,x1,y1 는 PDF 좌표)
    python3 scripts/read_kepco_tables.py 단가정보/전기요금/종합/2025-04-01_전기요금표_종합.pdf 2 --tou 305,85,640,800

    # 특정 영역의 숫자를 읽기순으로 나열 (계절별·누진 표용)
    python3 scripts/read_kepco_tables.py 단가정보/전기요금/종합/2026-04-16_전기요금표_종합.pdf 1 --nums 604,259,882,380

왜 이렇게 하나
--------------
pdfplumber 의 find_tables().extract() 는 한전 요금표처럼 셀이 많이 병합된 표에서
'5,55 | 0 116.2' 같이 숫자를 잘라먹는다. 표 테두리 대신
'경부하/중간부하/최대부하' 라벨을 기준점으로 삼으면 열이 잘리지 않는다.

주의
----
종별 이름(주택용전력, 교육용전력(갑) …)은 PDF 안에 글자가 아니라 그림으로 들어있어
프로그램으로 읽을 수 없다. 어느 표가 어느 종별인지는 페이지를 이미지로 띄워
사람이 확인해야 한다.
"""
import argparse
import glob
import re
import subprocess
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
NUM = re.compile(r"^[\d,]+\.?\d*$")
ZONES = ("경부하", "중간부하", "최대부하")


def as_number(word: dict) -> float | None:
    text = word["text"].strip()
    if not NUM.match(text) or text in {",", "."}:
        return None
    return float(text.replace(",", ""))


# 일부 요금표는 '116.7' 을 '1','1','6','.','7' 처럼 글자 단위로 그린다.
# pdfplumber 의 extract_words 는 x_tolerance 를 올려도 이것을 붙이지 못해
# 해당 행을 통째로 놓친다. 그래서 글자(char)에서 직접 토큰을 만든다.
# 어떤 요금표는 실제 행 위에 0.3pt 쯤 어긋난 조각 레이어가 겹쳐 있다.
# 허용치를 넉넉히 잡으면 두 겹이 한 줄로 섞여 '152.4' 가 '52.653.7' 처럼 망가진다.
# 같은 행의 글자는 top 이 거의 정확히 같으므로 좁게 잡는다.
ROW_TOL = 0.5   # 같은 줄로 볼 세로 오차
GAP_TOL = 2.0   # 같은 토큰으로 볼 가로 간격


def extract_words(page) -> list[dict]:
    """page.chars 를 직접 묶어 토큰을 만든다. extract_words 와 같은 모양으로 반환.

    줄을 먼저 나눈 뒤 줄 안에서만 가로로 묶는다. 한 번에 정렬해 묶으면
    다른 줄의 글자가 끼어들어 '119.7' + '9~10월)' 처럼 엉뚱하게 붙는다.
    """
    chars = sorted((c for c in page.chars if c["text"].strip()),
                   key=lambda c: (c["top"], c["x0"]))
    rows: list[list[dict]] = []
    for c in chars:
        if rows and abs(c["top"] - rows[-1][0]["top"]) <= ROW_TOL:
            rows[-1].append(c)
        else:
            rows.append([c])

    tokens = []
    for row in rows:
        row.sort(key=lambda c: c["x0"])
        cur: list[dict] = []
        for c in row:
            if cur and c["x0"] - cur[-1]["x1"] > GAP_TOL:
                tokens.append(_token(cur))
                cur = []
            cur.append(c)
        if cur:
            tokens.append(_token(cur))
    return tokens


def _token(chars: list[dict]) -> dict:
    return {"text": "".join(c["text"] for c in chars),
            "x0": chars[0]["x0"], "x1": chars[-1]["x1"],
            "top": min(c["top"] for c in chars),
            "bottom": max(c["bottom"] for c in chars)}


def in_region(words: list[dict], region: tuple[float, ...]) -> list[dict]:
    x0, y0, x1, y1 = region
    return [w for w in words
            if w["x0"] >= x0 - 1 and w["x1"] <= x1 + 1
            and w["top"] >= y0 - 1 and w["bottom"] <= y1 + 1]


def read_numbers(page, region, row_tol: float = 4) -> list[float]:
    """영역 안의 숫자를 읽기순(위→아래, 왼→오른)으로 반환. 계절별·누진 표용."""
    words = sorted(in_region(extract_words(page), region),
                   key=lambda w: (w["top"], w["x0"]))
    rows, cur = [], []
    for w in words:
        if cur and w["top"] - cur[0]["top"] > row_tol:
            rows.append(cur)
            cur = []
        cur.append(w)
    if cur:
        rows.append(cur)
    out = []
    for row in rows:
        for w in sorted(row, key=lambda w: w["x0"]):
            value = as_number(w)
            if value is not None:
                out.append(value)
    return out


def read_tou(page, region, row_tol: float = 3.5, expect: int | None = None):
    """시간대별 요율을 읽는다.

    반환: (기본요금 목록, [(시간대, y좌표, [여름, 봄·가을, 겨울]), ...])
    """
    words = in_region(extract_words(page), region)
    labels = sorted((w for w in words if w["text"].strip() in ZONES),
                    key=lambda w: w["top"])
    rows = []
    for label in labels:
        same_row = [w for w in words
                    if abs(w["top"] - label["top"]) <= row_tol and w["x0"] > label["x1"]]
        values = [v for v in (as_number(w) for w in sorted(same_row, key=lambda w: w["x0"]))
                  if v is not None]
        rows.append((label["text"].strip(), round(label["top"], 1), values))
    basics = [as_number(w) for w in sorted(words, key=lambda w: w["top"])
              if "," in w["text"] and (as_number(w) or 0) >= 1000]
    if expect is not None and len(rows) != expect:
        raise SystemExit(
            f"시간대 행이 {len(rows)}개입니다 (기대 {expect}개).\n"
            "영역이 좁거나, 글자가 쪼개져 그려진 행이 있어 건너뛴 것입니다.\n"
            "영역을 넓혀 다시 시도하고, 그래도 모자라면 해당 구간을 눈으로 확인하세요.")
    return basics, rows


def survey() -> None:
    """요금표 PDF들이 글자를 품고 있는지, 몇 쪽인지 한눈에 본다."""
    print(f"{'시행일':<12} {'쪽':>2} {'크기':>10} {'숫자':>5}  비고")
    print("-" * 58)
    for path in sorted(glob.glob(str(ROOT / "단가정보/전기요금/종합/*_전기요금표_종합.pdf"))):
        name = Path(path).stem.replace("_종합", "")
        text = subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True, text=True).stdout
        count = len(re.findall(r"\d+\.\d", text))
        with pdfplumber.open(path) as pdf:
            pages, w, h = len(pdf.pages), pdf.pages[0].width, pdf.pages[0].height
        note = "글자 없음 — 이미지 PDF, 눈으로 읽어야 함" if count < 50 else "추출 가능"
        print(f"{name:<12} {pages:>2} {int(w)}x{int(h):<6} {count:>5}  {note}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", nargs="?")
    parser.add_argument("page", nargs="?", type=int)
    parser.add_argument("--survey", action="store_true", help="요금표 PDF 목록과 추출 가능 여부")
    parser.add_argument("--tou", help="시간대별 요율을 읽을 영역 x0,y0,x1,y1")
    parser.add_argument("--nums", help="숫자를 읽기순으로 나열할 영역 x0,y0,x1,y1")
    parser.add_argument("--expect", type=int,
                        help="시간대 행이 몇 개여야 하는지. 모자라면 오류로 끝낸다 (권장)")
    args = parser.parse_args()

    if args.survey or not args.pdf:
        survey()
        return

    region_text = args.tou or args.nums
    if not region_text:
        parser.error("--tou 또는 --nums 로 영역을 지정하세요.")
    region = tuple(float(v) for v in region_text.split(","))

    with pdfplumber.open(args.pdf) as pdf:
        page = pdf.pages[args.page - 1]
        if args.tou:
            basics, rows = read_tou(page, region, expect=args.expect)
            print(f"기본요금 {len(basics)}개: {basics}")
            print(f"시간대 행 {len(rows)}개  (값은 여름철 / 봄·가을철 / 겨울철 순)")
            for name, top, values in rows:
                flag = "" if len(values) == 3 else f"  ← {len(values)}개, 영역을 넓히세요"
                print(f"  y={top:6.1f} {name:<6} {values}{flag}")
        else:
            values = read_numbers(page, region)
            print(f"{len(values)}개: {values}")


if __name__ == "__main__":
    main()
