-- 전기요금: 한국전력공사 전기요금표 — 주택용만 (2022년 10월 1일 시행)
-- 원본: 단가정보/전기요금/주택용저압/2022-10-01_전기요금표_주택용저압.pdf

insert into pricing.electricity_tariff_version
  (effective_from, published_label, provider, source_file,
   vat_rate, power_fund_rate, climate_charge_per_kwh, fuel_adjustment_per_kwh,
   is_partial, covered_contract_types, note)
values
  ('2022-10-01', '2022년 10월 1일 시행', '한국전력공사', '단가정보/전기요금/주택용저압/2022-10-01_전기요금표_주택용저압.pdf', 0.1, 0.037, NULL, NULL, TRUE, '{"주택용전력"}', '이 시행일은 주택용 저압·고압만 확보했다. 종합요금표가 글자 없는 이미지 PDF 라 다른 계약종별(일반용·교육용·산업용·농사용·가로등·심야전력)은 옮기지 못했다. 이 시점을 조회해 다른 종별이 비어 있다면 ''요금이 없음'' 이 아니라 ''아직 데이터를 넣지 못함'' 이다.')
on conflict (effective_from, source_file) do update set
  published_label = excluded.published_label,
  vat_rate = excluded.vat_rate,
  power_fund_rate = excluded.power_fund_rate,
  is_partial = excluded.is_partial,
  covered_contract_types = excluded.covered_contract_types,
  note = excluded.note;

-- 같은 버전의 기존 요율을 지우고 다시 넣는다 (부분 수정 시 꼬이지 않도록)
delete from pricing.electricity_rate where version_id in (
  select id from pricing.electricity_tariff_version
  where effective_from = '2022-10-01' and source_file = '단가정보/전기요금/주택용저압/2022-10-01_전기요금표_주택용저압.pdf');

insert into pricing.electricity_rate
  (version_id, contract_type, rate_structure, contract_power, voltage, rate_option,
   basic_charge, basic_charge_unit, basic_charge_formula,
   season, time_zone, tier, usage_range, energy_label, energy_charge, note)
select v.id, x.* from pricing.electricity_tariff_version v,
(values
  ('주택용전력', 'progressive', NULL, '저압', NULL, 910, '원/호', NULL, '기타계절', NULL, 1, '200kWh 이하 사용', '처음 200kWh까지', 100.6, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '저압', NULL, 1600, '원/호', NULL, '기타계절', NULL, 2, '201~400kWh 사용', '다음 200kWh까지', 195.2, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '저압', NULL, 7300, '원/호', NULL, '기타계절', NULL, 3, '400kWh 초과 사용', '400kWh 초과', 287.9, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '저압', NULL, 910, '원/호', NULL, '하계', NULL, 1, '300kWh 이하 사용', '처음 300kWh까지', 100.6, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '저압', NULL, 1600, '원/호', NULL, '하계', NULL, 2, '301~450kWh 사용', '다음 150kWh까지', 195.2, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '저압', NULL, 7300, '원/호', NULL, '하계', NULL, 3, '450kWh 초과 사용', '450kWh 초과', 287.9, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 716.8원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 730, '원/호', NULL, '기타계절', NULL, 1, '200kWh 이하 사용', '처음 200kWh까지', 85.6, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 581.9원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 1260, '원/호', NULL, '기타계절', NULL, 2, '201~400kWh 사용', '다음 200kWh까지', 154.6, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 581.9원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 6060, '원/호', NULL, '기타계절', NULL, 3, '400kWh 초과 사용', '400kWh 초과', 222.9, '슈퍼유저요금: 동계(12월 1일~2월 말일) 1,000kWh 초과 581.9원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 730, '원/호', NULL, '하계', NULL, 1, '300kWh 이하 사용', '처음 300kWh까지', 85.6, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 581.9원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 1260, '원/호', NULL, '하계', NULL, 2, '301~450kWh 사용', '다음 150kWh까지', 154.6, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 581.9원/kWh'),
  ('주택용전력', 'progressive', NULL, '고압', NULL, 6060, '원/호', NULL, '하계', NULL, 3, '450kWh 초과 사용', '450kWh 초과', 222.9, '슈퍼유저요금: 하계(7월 1일~8월 31일) 1,000kWh 초과 581.9원/kWh')
) as x(contract_type, rate_structure, contract_power, voltage, rate_option,
       basic_charge, basic_charge_unit, basic_charge_formula,
       season, time_zone, tier, usage_range, energy_label, energy_charge, note)
where v.effective_from = '2022-10-01' and v.source_file = '단가정보/전기요금/주택용저압/2022-10-01_전기요금표_주택용저압.pdf';
