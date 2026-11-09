-- 일부 시행일은 종합요금표가 글자 없는 이미지 PDF 라서
-- 주택용 별도 요금표에서 주택용 종별만 확보할 수 있었다.
-- 그런 버전을 모르고 조회하면 빈 결과가 "요금 0원" 처럼 보인다. 그래서 표시해 둔다.

alter table pricing.electricity_tariff_version
    add column if not exists is_partial boolean not null default false,
    add column if not exists covered_contract_types text[];

comment on column pricing.electricity_tariff_version.is_partial is
    'true 면 이 시행일의 일부 계약종별만 들어 있다. covered_contract_types 에 어떤 종별이 있는지 적혀 있다. 빈 조회 결과를 "요금 없음" 으로 오해하지 말 것.';

create or replace view pricing.electricity_tariff_coverage as
select v.effective_from, v.published_label, v.is_partial,
       count(distinct r.contract_type) as 수록_종별수,
       array_agg(distinct r.contract_type order by r.contract_type) as 수록_종별
from pricing.electricity_tariff_version v
left join pricing.electricity_rate r on r.version_id = v.id
group by v.effective_from, v.published_label, v.is_partial
order by v.effective_from;
