#!/usr/bin/env python3
"""전기요금 JSON의 모든 숫자가 원본 PDF에 실제로 존재하는지 대조 검증한다.

사용법:
    python3 scripts/verify_electricity.py [data/electricity/kepco_2026-04-16.json ...]

손으로 옮겨 적은 단가의 오타를 잡기 위한 장치다.
PDF에서 뽑은 숫자 집합에 JSON의 숫자가 하나라도 없으면 실패로 끝난다.
"""
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_kepco_tables import extract_words  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")

# 요율이 아니라 설명문에서 온 값이라 PDF 숫자 집합에 없을 수 있는 키
SKIP_KEYS = {"tier", "source_pages", "vat_rate", "power_industry_fund_rate"}


def pdf_numbers(pdf_path: Path, pages: list[int]) -> set[str]:
    """PDF 해당 페이지의 모든 숫자를 정규화해 집합으로 반환.

    extract_text() 를 쓰면 안 된다. 일부 요금표는 '116.7' 을 글자 단위로 그려서
    그런 숫자가 통째로 빠지고, 멀쩡한 값이 '없다'고 나온다.
    read_kepco_tables 의 글자 단위 토큰화를 써야 전부 잡힌다.
    """
    found: set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page_no in pages:
            for token in extract_words(pdf.pages[page_no - 1]):
                for raw in NUM_RE.findall(token["text"]):
                    found.add(normalize(raw))
    return found


def normalize(raw: str) -> str:
    """'7,170' -> '7170', '120.0' -> '120'. 비교용 표준형."""
    value = float(raw.replace(",", ""))
    return f"{value:g}"


def walk(node, path: str, out: list[tuple[str, float]]) -> None:
    """JSON 트리를 돌며 (경로, 숫자) 쌍을 모은다."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in SKIP_KEYS:
                continue
            walk(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk(value, f"{path}[{i}]", out)
    elif isinstance(node, bool) or node is None:
        return
    elif isinstance(node, (int, float)):
        out.append((path, float(node)))


def show(path: Path) -> str:
    """레포 안이면 상대경로로, 밖이면 절대경로 그대로 보여준다."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def verify(json_path: Path) -> int:
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    meta = doc["meta"]

    if meta.get("skip_pdf_number_check"):
        print(f"\n[{show(json_path)}]")
        print("  — 자동 대조 건너뜀")
        print(f"    {meta['skip_pdf_number_check']}")
        return 0

    pdf_path = ROOT / meta["source_file"]
    if not pdf_path.exists():
        print(f"  !! 원본 PDF 없음: {meta['source_file']}")
        return 1

    available = pdf_numbers(pdf_path, meta["source_pages"])

    values: list[tuple[str, float]] = []
    walk(doc["tariffs"], "tariffs", values)

    missing = [(p, v) for p, v in values if normalize(str(v)) not in available]

    print(f"\n[{show(json_path)}]")
    print(f"  원본: {meta['source_file']} (p.{', p.'.join(map(str, meta['source_pages']))})")
    print(f"  검사한 숫자 {len(values)}개 / PDF에서 읽은 숫자 {len(available)}개")
    if missing:
        print(f"  ✗ PDF에서 찾지 못한 값 {len(missing)}개:")
        for path, value in missing:
            print(f"      {path} = {value}")
        return 1
    print("  ✓ 모든 값이 원본 PDF에 존재함")
    return 0


def main() -> None:
    targets = (
        [Path(a).resolve() for a in sys.argv[1:]]
        if len(sys.argv) > 1
        else sorted((ROOT / "data" / "electricity").glob("*.json"))
    )
    if not targets:
        print("검증할 JSON이 없습니다.")
        return
    sys.exit(sum(verify(t) for t in targets))


if __name__ == "__main__":
    main()
