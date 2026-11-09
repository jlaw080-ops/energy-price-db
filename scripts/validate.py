#!/usr/bin/env python3
"""data/ 안의 모든 단가 JSON이 약속한 형식을 지키는지 점검한다.

사용법:
    python3 scripts/validate.py

단가를 수정한 뒤 커밋하기 전에 돌리면 형식 실수를 미리 잡을 수 있다.
"""
import json
import math
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

VALID_SEASONS = {"여름철", "봄·가을철", "겨울철", "여름·겨울철", "하계", "기타계절", "연중", "단일요금", "동절기", "하절기", "기타월"}
VALID_TIME_ZONES = {"경부하", "중간부하", "최대부하", "심야시간", "기타시간",
                    # 2021 요금표의 제주 계시별은 주말/평일 구분을 쓴다
                    "주말 전체시간", "평일 기타시간", "평일 수요시간"}
VALID_COST_TYPES = {"자재비", "설치비", "턴키(합계)"}

errors: list[str] = []
warnings: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def warn(path: Path, msg: str) -> None:
    warnings.append(f"{path.relative_to(ROOT)}: {msg}")


def check_iso_date(path: Path, value: str, field: str) -> None:
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError):
        err(path, f"{field} 가 YYYY-MM-DD 형식이 아닙니다: {value!r}")


def check_electricity(path: Path, doc: dict) -> None:
    meta = doc.get("meta", {})
    for field in ("dataset", "source_file", "currency"):
        if not meta.get(field):
            err(path, f"meta.{field} 가 없습니다")
    src = ROOT / meta.get("source_file", "")
    if meta.get("source_file") and not src.exists():
        err(path, f"원본 파일이 없습니다: {meta['source_file']}")

    seen_ids: set[str] = set()
    for tariff in doc.get("tariffs", []):
        tid = tariff.get("id")
        if not tid:
            err(path, "id 없는 종별이 있습니다")
        elif tid in seen_ids:
            err(path, f"id 중복: {tid}")
        else:
            seen_ids.add(tid)
        if tariff.get("effective_from"):
            check_iso_date(path, tariff["effective_from"], f"{tid}.effective_from")
        if not tariff.get("rates"):
            err(path, f"{tid}: rates 가 비어 있습니다")
        for rate in tariff.get("rates", []):
            for e in rate.get("energy") or []:
                s, z = e.get("season"), e.get("time_zone")
                if s and s not in VALID_SEASONS:
                    err(path, f"{tid}: 모르는 계절값 {s!r}")
                if z and z not in VALID_TIME_ZONES:
                    err(path, f"{tid}: 모르는 시간대값 {z!r}")
                if not isinstance(e.get("charge"), (int, float)):
                    err(path, f"{tid}: charge 가 숫자가 아닙니다 ({e})")
            for tier in rate.get("tiers") or []:
                if not isinstance(tier.get("energy_charge"), (int, float)):
                    err(path, f"{tid}: energy_charge 가 숫자가 아닙니다 ({tier})")

    if doc.get("surcharges", {}).get("climate_charge_won_per_kwh") is None:
        warn(path, "기후환경요금 단가가 비어 있습니다 (한전 공지에서 채워야 전기요금 계산 가능)")
    if doc.get("surcharges", {}).get("fuel_adjustment_won_per_kwh") is None:
        warn(path, "연료비조정단가가 비어 있습니다 (분기마다 바뀜)")


def check_gas(path: Path, doc: dict) -> None:
    meta = doc.get("meta", {})
    if "series" in doc:
        series = doc["series"]
        months = [s["month"] for s in series]
        if len(months) != len(set(months)):
            err(path, "month 중복이 있습니다")
        if months != sorted(months):
            err(path, "month 가 오름차순이 아닙니다")
        for s in series:
            total = round(s["feedstock_cost_won_per_nm3"] + s["supply_cost_won_per_nm3"], 2)
            if abs(total - s["total_won_per_nm3"]) > 0.01:
                err(path, f"{s['month']}: 원/Nm3 합계가 맞지 않습니다")
        if meta.get("record_count") != len(series):
            err(path, "meta.record_count 와 실제 건수가 다릅니다")
    if "items" in doc and meta.get("dataset") == "kogas_wholesale":
        for i in doc["items"]:
            total = round(i["feedstock_cost_won_per_mj"] + i["supply_cost_won_per_mj"], 4)
            if abs(total - i["wholesale_price_won_per_mj"]) > 0.0001:
                err(path, f"{i['sector']}/{i['use']}: 원료비+공급비 != 도매요금")
            if i["season"] not in VALID_SEASONS:
                err(path, f"모르는 계절값 {i['season']!r}")


def half_up(value: float) -> int:
    """원 미만 4사5입. 파이썬 round() 는 은행가 반올림이라 9588.5 를 9588 로 만든다."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def check_welfare(path: Path, doc: dict) -> None:
    """복지할인 항목과, 한전이 인쇄한 요금계산 예시의 산술을 점검한다.

    예시의 숫자를 우리가 옮겨 적은 것이므로, 합이 맞는지 다시 계산해 보면
    전사 오류를 잡을 수 있다.
    """
    for w in doc.get("welfare_discount", []):
        if not w.get("target"):
            err(path, "복지할인 target 이 비어 있습니다")
        if w.get("type") not in {"정액할인", "정률할인"}:
            err(path, f"{w.get('target')}: type 은 정액할인/정률할인 중 하나여야 합니다")
        if w["type"] == "정률할인" and not w.get("percent"):
            err(path, f"{w.get('target')}: 정률할인인데 percent 가 없습니다")
        if w["type"] == "정액할인" and not w.get("monthly_cap"):
            err(path, f"{w.get('target')}: 정액할인인데 monthly_cap 이 없습니다")

    fund_rate = 0.037   # 2024-01-01 요금표 기준
    examples = [("단일가구 예시", doc.get("single_household_example")),
                ("1주택수가구 예시",
                 (doc.get("multi_household_single_meter") or {}).get("worked_example"))]
    for label, ex in examples:
        if not ex:
            continue
        parts = sum(ex[k]["값"] for k in
                    ("기본요금", "전력량요금", "기후환경요금", "연료비조정요금"))
        if parts != ex["전기요금계"]:
            err(path, f"{label}: 항목 합 {parts:,} 가 전기요금계 {ex['전기요금계']:,} 와 다릅니다")
        vat = half_up(ex["전기요금계"] * 0.10)
        if vat != ex["부가가치세"]["값"]:
            err(path, f"{label}: 부가가치세 계산 {vat:,} ≠ 적힌 값 {ex['부가가치세']['값']:,}")
        fund = math.floor(ex["전기요금계"] * fund_rate / 10) * 10
        if fund != ex["전력기반기금"]["값"]:
            err(path, f"{label}: 전력기반기금 계산 {fund:,} ≠ 적힌 값 {ex['전력기반기금']['값']:,}")
        total = math.floor((ex["전기요금계"] + ex["부가가치세"]["값"]
                            + ex["전력기반기금"]["값"]) / 10) * 10
        if total != ex["청구금액"]["값"]:
            err(path, f"{label}: 청구금액 계산 {total:,} ≠ 적힌 값 {ex['청구금액']['값']:,}")


def check_surcharge(path: Path, doc: dict) -> None:
    """기후환경요금·연료비조정단가 시계열 점검."""
    for key in ("climate_charge", "fuel_adjustment"):
        rows = doc.get(key, [])
        if not rows:
            err(path, f"{key} 가 비어 있습니다")
            continue
        dates = [r.get("effective_from") for r in rows]
        if dates != sorted(d for d in dates if d):
            err(path, f"{key} 가 시행일 오름차순이 아닙니다")
        if len(dates) != len(set(dates)):
            err(path, f"{key} 에 시행일 중복이 있습니다")
        for r in rows:
            check_iso_date(path, r.get("effective_from"), f"{key}.effective_from")
            if not isinstance(r.get("won_per_kwh"), (int, float)):
                err(path, f"{key}: won_per_kwh 가 숫자가 아닙니다 ({r.get('effective_from')})")
            if r.get("source_type") not in {"요금표", "보도", "한전공시"}:
                err(path, f"{key}: source_type 은 요금표/보도/한전공시 중 하나여야 합니다 ({r.get('source_type')!r})")
            if not r.get("source"):
                err(path, f"{key}: source 가 비어 있습니다 ({r.get('effective_from')})")
    unconfirmed = [r for k in ("climate_charge", "fuel_adjustment")
                   for r in doc.get(k, []) if r.get("source_type") == "보도"]
    if unconfirmed:
        warn(path, f"한전 공식 고시로 확인되지 않은 값이 {len(unconfirmed)}건 있습니다 (source_type=보도)")


def check_citygas(path: Path, doc: dict, retail: bool) -> None:
    """도시가스 요금표에서 뽑은 월별 시계열."""
    meta = doc.get("meta", {})
    for field in ("dataset", "source_dir", "unit"):
        if not meta.get(field):
            err(path, f"meta.{field} 가 없습니다")
    if meta.get("unit") != "원/MJ":
        err(path, f"단위가 원/MJ 이 아닙니다: {meta.get('unit')!r}")

    items = doc.get("items", [])
    if not items:
        err(path, "items 가 비어 있습니다")
        return
    if meta.get("record_count") != len(items):
        err(path, f"meta.record_count({meta.get('record_count')}) 와 "
                  f"실제 항목 수({len(items)}) 가 다릅니다")

    keys, dates = set(), set()
    for i in items:
        for field in ("effective_from", "use_category", "won_per_mj"):
            if i.get(field) is None:
                err(path, f"{field} 가 없는 항목이 있습니다: {i}")
                return
        check_iso_date(path, i["effective_from"], "effective_from")
        dates.add(i["effective_from"])
        if not isinstance(i["won_per_mj"], (int, float)) or i["won_per_mj"] <= 0:
            err(path, f"요금이 숫자가 아니거나 0 이하입니다: {i}")
        k = (i["effective_from"], i.get("region", ""), i["use_category"],
             i.get("use_detail", ""))
        if k in keys:
            err(path, f"같은 키가 두 번 있습니다: {k}")
        keys.add(k)

    if retail:
        regs = {(r["effective_from"], r["region"]) for r in doc.get("regions", [])}
        missing = {(i["effective_from"], i["region"]) for i in items} - regs
        if missing:
            err(path, f"regions 에 없는 (시점,지역) 이 {len(missing)}건 있습니다: "
                      f"{sorted(missing)[:3]}")
        if meta.get("year") and {d[:4] for d in dates} != {str(meta["year"])}:
            err(path, f"meta.year({meta['year']}) 와 다른 연도의 자료가 섞여 있습니다")


def check_price_list(path: Path, doc: dict, equipment: bool) -> None:
    required = {"slug", "category", "name", "unit_price", "price_unit", "base_date"}
    if equipment:
        required.add("cost_type")
    seen: set[tuple] = set()
    for item in doc.get("items", []):
        missing = required - item.keys()
        if missing:
            err(path, f"{item.get('slug', '?')}: 필수 항목 누락 {sorted(missing)}")
            continue
        check_iso_date(path, item["base_date"], f"{item['slug']}.base_date")
        if not isinstance(item["unit_price"], (int, float)):
            err(path, f"{item['slug']}: unit_price 가 숫자가 아닙니다")
        if equipment and item["cost_type"] not in VALID_COST_TYPES:
            err(path, f"{item['slug']}: cost_type 은 {sorted(VALID_COST_TYPES)} 중 하나여야 합니다")
        key = (item["slug"], item["base_date"])
        if key in seen:
            err(path, f"slug+base_date 중복: {key}")
        seen.add(key)
    if not doc.get("items"):
        warn(path, "items 가 비어 있습니다 (아직 단가 자료를 넣지 않은 템플릿)")


def main() -> None:
    files = sorted(DATA.rglob("*.json"))
    if not files:
        sys.exit("data/ 에 JSON 파일이 없습니다.")

    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            err(path, f"JSON 문법 오류: {exc}")
            continue
        dataset = doc.get("meta", {}).get("dataset", "")
        if dataset == "kepco_electricity_tariff":
            check_electricity(path, doc)
        elif dataset.startswith("kogas"):
            check_gas(path, doc)
        elif dataset == "renewable_equipment_price":
            check_price_list(path, doc, equipment=True)
        elif dataset == "misc_price":
            check_price_list(path, doc, equipment=False)
        elif dataset == "kepco_electricity_surcharge":
            check_surcharge(path, doc)
        elif dataset == "citygas_wholesale_monthly":
            check_citygas(path, doc, retail=False)
        elif dataset == "citygas_retail_monthly":
            check_citygas(path, doc, retail=True)
        elif dataset == "kepco_residential_welfare_discount":
            check_welfare(path, doc)
        else:
            err(path, f"meta.dataset 값을 알 수 없습니다: {dataset!r}")

    print(f"검사한 파일 {len(files)}개")
    for w in warnings:
        print(f"  [참고] {w}")
    if errors:
        print(f"\n✗ 오류 {len(errors)}건")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("✓ 형식 오류 없음")


if __name__ == "__main__":
    main()
