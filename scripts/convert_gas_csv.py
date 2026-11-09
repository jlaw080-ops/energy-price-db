#!/usr/bin/env python3
"""한국가스공사 원본 CSV(EUC-KR) -> UTF-8 JSON 변환.

사용법:
    python3 scripts/convert_gas_csv.py

단가정보/가스요금/ 의 원본 CSV를 읽어 data/gas/ 에 JSON으로 저장한다.
원본 숫자를 그대로 옮기며, 값을 보정하거나 추정하지 않는다.
"""
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "gas"
OUT = ROOT / "data" / "gas"


def read_rows(path: Path) -> list[list[str]]:
    """EUC-KR 또는 UTF-8 로 저장된 CSV를 읽는다."""
    for encoding in ("utf-8-sig", "euc-kr", "cp949"):
        try:
            with path.open(encoding=encoding, newline="") as fh:
                return [row for row in csv.reader(fh) if any(c.strip() for c in row)]
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"인코딩을 판별하지 못했습니다: {path}")


def num(value: str) -> float:
    return float(value.replace(",", "").strip())


def convert_power_generation(src: Path) -> dict:
    """발전용 천연가스요금 월별 시계열."""
    rows = read_rows(src)[1:]  # 헤더 제거
    series = [
        {
            "month": row[0][:7],                 # YYYY-MM
            "feedstock_cost_won_per_nm3": num(row[1]),   # 원료비 원/Nm3
            "supply_cost_won_per_nm3": num(row[2]),      # 공급비 원/Nm3
            "feedstock_cost_won_per_gj": num(row[3]),    # 원료비 원/GJ
            "supply_cost_won_per_gj": num(row[4]),       # 공급비 원/GJ
        }
        for row in rows
    ]
    for item in series:
        item["total_won_per_nm3"] = round(
            item["feedstock_cost_won_per_nm3"] + item["supply_cost_won_per_nm3"], 2
        )
        item["total_won_per_gj"] = round(
            item["feedstock_cost_won_per_gj"] + item["supply_cost_won_per_gj"], 2
        )
    return {
        "meta": {
            "dataset": "kogas_power_generation_monthly",
            "title": "한국가스공사 발전용 천연가스요금 (월별)",
            "provider": "한국가스공사",
            "source_file": str(src.relative_to(ROOT)),
            "source_portal": "공공데이터포털 (data.go.kr)",
            "currency": "KRW",
            "period_start": series[0]["month"],
            "period_end": series[-1]["month"],
            "record_count": len(series),
            "converted_at": date.today().isoformat(),
        },
        "series": series,
    }


def convert_wholesale(src: Path) -> dict:
    """용도별 천연가스 도매요금 (특정 시점 스냅샷)."""
    rows = read_rows(src)[1:]
    effective = src.stem.split("_")[-1]  # 파일명 끝의 YYYY-MM-DD
    items = [
        {
            "sector": row[0],                       # 구분 (민수용/상업용/도시가스발전용)
            "use": row[1],                          # 용도
            "season": row[2],                       # 계절별
            "feedstock_cost_won_per_mj": num(row[3]),   # 원료비
            "supply_cost_won_per_mj": num(row[4]),      # 공급비용
            "wholesale_price_won_per_mj": num(row[5]),  # 도매요금
        }
        for row in rows
    ]
    return {
        "meta": {
            "dataset": "kogas_wholesale",
            "title": "한국가스공사 용도별 천연가스 도매요금",
            "provider": "한국가스공사",
            "source_file": str(src.relative_to(ROOT)),
            "source_portal": "공공데이터포털 (data.go.kr)",
            "effective_from": effective,
            "currency": "KRW",
            "unit": "원/MJ",
            "record_count": len(items),
            "converted_at": date.today().isoformat(),
        },
        "items": items,
    }


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"생성: {path.relative_to(ROOT)}  ({payload['meta']['record_count']}건)")


def main() -> None:
    write(
        OUT / "kogas_발전용천연가스요금_월별.json",
        convert_power_generation(SRC / "kogas_발전용천연가스요금_2022-12-01.csv"),
    )
    write(
        OUT / "kogas_도매요금_2026-09-01.json",
        convert_wholesale(SRC / "kogas_천연가스요금정보_2026-09-01.csv"),
    )


if __name__ == "__main__":
    main()
