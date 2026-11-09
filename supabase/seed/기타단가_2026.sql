-- 기타 단가
insert into pricing.misc_price
  (slug, category, name, spec, unit_price, price_unit, base_date, source, source_type, note)
values
  ('electricity-avoided-cost', '전기요금', '전기요금 절감 단가 (회피단가)', '자가발전·절감량 1kWh 당 줄어드는 전기요금', 173, '원/kWh', '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 173 원/kWh. 종별·계절·시간대에 따라 실제 한계단가는 달라지므로, pricing.calc_* 함수로 대상 건물의 실제 요금제에서 역산해 검증하는 것을 권합니다.')
on conflict (slug, base_date) do update set
  category = excluded.category,
  name = excluded.name,
  spec = excluded.spec,
  unit_price = excluded.unit_price,
  price_unit = excluded.price_unit,
  source = excluded.source,
  source_type = excluded.source_type,
  note = excluded.note;
