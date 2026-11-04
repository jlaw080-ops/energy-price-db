#!/usr/bin/env python3
"""JSON 원본과 Supabase 에 적재된 내용이 같은지 체크섬으로 대조한다.

사용법:
    python3 scripts/checksum.py          # 기대값 출력
    python3 scripts/checksum.py --sql    # DB 에서 돌릴 SQL 출력

--sql 로 나온 SQL 을 Supabase SQL Editor 에서 실행한 뒤,
행수와 체크섬이 이 스크립트 출력과 같으면 값이 한 칸도 어긋나지 않고 들어간 것이다.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def pg(value) -> str:
    """Postgres 의 numeric::float8::text 와 같은 문자열로 맞춘다.

    format(v, 'g') 는 유효숫자 6자리에서 반올림해 36852.07 을 36852.1 로 만든다.
    repr() 은 왕복 가능한 최단 표기를 주므로 Postgres 출력과 일치한다.
    """
    if value is None:
        return ""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def digest(lines: list[str]) -> str:
    return hashlib.md5("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def electricity_lines(doc: dict, tariffs: list[dict] | None = None) -> list[str]:
    """요율 한 줄씩을 표준 문자열로. tariffs 를 주면 그 종별만 센다.

    한 요금표 안에서 종별마다 시행일이 다르면 DB 에는 시행일별 버전으로
    나뉘어 들어간다(export_sql.py 참고). 그래서 대조도 같은 기준으로 나눠야
    행수와 체크섬이 맞는다.
    """
    lines = []
    for t in (tariffs if tariffs is not None else doc["tariffs"]):
        ct, rs = t["contract_type"], t["rate_structure"]
        for r in t["rates"]:
            volt = r.get("voltage") or r.get("class") or ""
            opt = r.get("option") or ""
            bc = r.get("basic_charge")
            for e in r.get("energy") or []:
                lines.append("|".join([ct, rs, volt, opt, e.get("season") or "",
                                       e.get("time_zone") or "", "", pg(bc), pg(e["charge"])]))
            for tier in r.get("tiers") or []:
                lines.append("|".join([ct, rs, volt, opt, r.get("season") or "", "",
                                       str(tier["tier"]), pg(tier["basic_charge"]),
                                       pg(tier["energy_charge"])]))
            if not (r.get("energy") or r.get("tiers")):
                lines.append("|".join([ct, rs, volt, opt, "", "", "", pg(bc), ""]))
    return lines


def gas_monthly_lines(doc: dict) -> list[str]:
    return ["|".join([s["month"], pg(s["feedstock_cost_won_per_nm3"]),
                      pg(s["supply_cost_won_per_nm3"]), pg(s["feedstock_cost_won_per_gj"]),
                      pg(s["supply_cost_won_per_gj"])]) for s in doc["series"]]


def surcharge_lines(doc: dict) -> list[str]:
    return ["|".join([kind, r["effective_from"], pg(r["won_per_kwh"]),
                      r["source_type"], r["confidence"]])
            for kind, key in (("기후환경요금", "climate_charge"),
                              ("연료비조정단가", "fuel_adjustment"))
            for r in doc.get(key, [])]


def gas_wholesale_lines(doc: dict) -> list[str]:
    return ["|".join([i["sector"], i["use"], i["season"], pg(i["feedstock_cost_won_per_mj"]),
                      pg(i["supply_cost_won_per_mj"]), pg(i["wholesale_price_won_per_mj"])])
            for i in doc["items"]]


SQL = """\
-- 전기요금 (요금표 버전별)
with canon as (
  select v.effective_from,
         coalesce(r.contract_type,'')||'|'||coalesce(r.rate_structure,'')||'|'||
         coalesce(r.voltage,'')||'|'||coalesce(r.rate_option,'')||'|'||
         coalesce(r.season,'')||'|'||coalesce(r.time_zone,'')||'|'||
         coalesce(r.tier::text,'')||'|'||coalesce(r.basic_charge::float8::text,'')||'|'||
         coalesce(r.energy_charge::float8::text,'') as line
  from pricing.electricity_rate r
  join pricing.electricity_tariff_version v on v.id = r.version_id
)
select '전기요금 '||effective_from as 구분, count(*) as 행수,
       md5(string_agg(line, E'\\n' order by line)) as 체크섬
from canon group by effective_from
union all
-- 발전용 가스요금 월별
select '가스 월별', count(*), md5(string_agg(line, E'\\n' order by line)) from (
  select to_char(month,'YYYY-MM')||'|'||feedstock_cost_per_nm3::float8::text||'|'||
         supply_cost_per_nm3::float8::text||'|'||feedstock_cost_per_gj::float8::text||'|'||
         supply_cost_per_gj::float8::text as line
  from pricing.gas_power_generation_monthly) m
union all
-- 가스 도매요금
select '가스 도매요금 '||effective_from, count(*),
       md5(string_agg(line, E'\\n' order by line)) from (
  select effective_from,
         sector||'|'||use_type||'|'||season||'|'||feedstock_cost::float8::text||'|'||
         supply_cost::float8::text||'|'||wholesale_price::float8::text as line
  from pricing.gas_wholesale_price) w
group by effective_from
union all
-- 기후환경요금 · 연료비조정단가
select '부가요금', count(*), md5(string_agg(line, E'\\n' order by line)) from (
  select kind||'|'||effective_from::text||'|'||won_per_kwh::float8::text||'|'||
         source_type||'|'||confidence as line
  from pricing.electricity_surcharge) sc
union all
-- 신재생 장비 단가
select '장비단가', count(*), md5(string_agg(line, E'\\n' order by line)) from (
  select slug||'|'||category||'|'||coalesce(subcategory,'')||'|'||name||'|'||
         cost_type||'|'||unit_price::float8::text||'|'||price_unit||'|'||
         base_date::text as line
  from pricing.renewable_equipment_price) eq
union all
-- 기타 단가
select '기타단가', count(*), md5(string_agg(line, E'\\n' order by line)) from (
  select slug||'|'||category||'|'||name||'|'||unit_price::float8::text||'|'||
         price_unit||'|'||base_date::text as line
  from pricing.misc_price) mp
union all
-- 도시가스 도매요금 월별
select '도시가스 도매', count(*), md5(string_agg(line, E'\\n' order by line)) from (
  select effective_from::text||'|'||use_category||'|'||use_detail||'|'||
         won_per_mj::float8::text as line
  from pricing.citygas_wholesale_monthly) cw
union all
-- 도시가스 소매요금 월별 (연도별로 나눠서 JSON 파일과 맞춘다)
select '도시가스 소매 '||to_char(effective_from,'YYYY'), count(*),
       md5(string_agg(line, E'\\n' order by line)) from (
  select effective_from,
         effective_from::text||'|'||region||'|'||use_category||'|'||use_detail||'|'||
         won_per_mj::float8::text as line
  from pricing.citygas_retail_monthly) cr
group by to_char(effective_from,'YYYY');"""

def equipment_lines(doc: dict) -> list[str]:
    return ["|".join([i["slug"], i["category"], i.get("subcategory") or "",
                      i["name"], i["cost_type"], pg(i["unit_price"]),
                      i["price_unit"], i["base_date"]])
            for i in doc.get("items", [])]


def misc_lines(doc: dict) -> list[str]:
    return ["|".join([i["slug"], i["category"], i["name"],
                      pg(i["unit_price"]), i["price_unit"], i["base_date"]])
            for i in doc.get("items", [])]


def citygas_wholesale_lines(doc: dict) -> list[str]:
    return ["|".join([i["effective_from"], i["use_category"], i["use_detail"],
                      pg(i["won_per_mj"])]) for i in doc["items"]]


def citygas_retail_lines(doc: dict) -> list[str]:
    return ["|".join([i["effective_from"], i["region"], i["use_category"],
                      i["use_detail"], pg(i["won_per_mj"])]) for i in doc["items"]]


BUILDERS = {
    "citygas_wholesale_monthly": ("도시가스 도매", citygas_wholesale_lines),
    "citygas_retail_monthly": ("도시가스 소매", citygas_retail_lines),
    "kepco_electricity_tariff": ("전기요금", electricity_lines),
    "renewable_equipment_price": ("장비단가", equipment_lines),
    "misc_price": ("기타단가", misc_lines),
    "kogas_power_generation_monthly": ("가스 월별", gas_monthly_lines),
    "kogas_wholesale": ("가스 도매요금", gas_wholesale_lines),
    "kepco_electricity_surcharge": ("부가요금", surcharge_lines),
}


def main() -> None:
    if "--sql" in sys.argv:
        print(SQL)
        return
    print(f"{'구분':<22} {'행수':>6}  체크섬")
    print("-" * 62)
    for path in sorted(DATA.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        spec = BUILDERS.get(doc.get("meta", {}).get("dataset", ""))
        if not spec:
            continue
        label, build = spec
        if label == "전기요금":
            # 시행일별로 쪼개서 DB 의 버전 구분과 맞춘다
            for eff in sorted({t["effective_from"] for t in doc["tariffs"]}):
                tariffs = [t for t in doc["tariffs"] if t["effective_from"] <= eff]
                lines = electricity_lines(doc, tariffs)
                print(f"{label + ' ' + eff:<22} {len(lines):>6}  {digest(lines)}")
            continue
        if label == "도시가스 소매":
            label += " " + str(doc["meta"]["year"])
        if label == "가스 도매요금":
            # 스냅샷이 여러 시점이 되면 시행일로 나눠야 DB 와 대조된다
            label += " " + doc["meta"]["effective_from"]
        lines = build(doc)
        print(f"{label:<22} {len(lines):>6}  {digest(lines)}")
    print("\nDB 쪽 값은 `python3 scripts/checksum.py --sql` 의 SQL 로 확인하세요.")


if __name__ == "__main__":
    main()
