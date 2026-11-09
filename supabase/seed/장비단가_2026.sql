-- 신재생에너지 장비 단가
insert into pricing.renewable_equipment_price
  (slug, category, subcategory, name, spec, cost_type, unit_price, price_unit, scope, base_date, source, source_type, note)
values
  ('pv-general', '태양광', '일반', '태양광 발전설비', NULL, '턴키(합계)', 2200000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 2,200 천원/kW'),
  ('pv-bipv', '태양광', 'BIPV', '건물일체형 태양광(BIPV)', NULL, '턴키(합계)', 4000000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 4,000 천원/kW'),
  ('geothermal-heatpump', '지열', NULL, '지열 히트펌프 시스템', NULL, '턴키(합계)', 1381000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 1,381 천원/kW'),
  ('fuelcell-pafc', '연료전지', 'PAFC', '인산형 연료전지(PAFC)', NULL, '턴키(합계)', 12000000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 12,000 천원/kW'),
  ('fuelcell-pemfc', '연료전지', 'PEMFC', '고분자전해질형 연료전지(PEMFC)', NULL, '턴키(합계)', 30000000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 30,000 천원/kW'),
  ('fuelcell-sofc', '연료전지', 'SOFC', '고체산화물형 연료전지(SOFC)', NULL, '턴키(합계)', 100000000, '원/kW', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 100,000 천원/kW'),
  ('ess-battery', 'ESS', NULL, '에너지저장장치(ESS)', NULL, '턴키(합계)', 450000000, '원/MWh', NULL, '2026-01-01', '사용자 제공 (경제성분석 입력값)', '제공', '입력 화면값 450,000 천원/MWh. kWh 기준으로는 450,000원/kWh 입니다.')
on conflict (slug, base_date) do update set
  category = excluded.category,
  subcategory = excluded.subcategory,
  name = excluded.name,
  spec = excluded.spec,
  cost_type = excluded.cost_type,
  unit_price = excluded.unit_price,
  price_unit = excluded.price_unit,
  scope = excluded.scope,
  source = excluded.source,
  source_type = excluded.source_type,
  note = excluded.note;
