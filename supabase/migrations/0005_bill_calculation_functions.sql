-- 전기요금 계산 함수
--
-- 매번 긴 CTE 를 쓰는 대신 조건만 넣으면 내역이 나오도록 한다.
-- 반올림 규칙은 한전 요금표를 따른다.
--   부가가치세   : 원 미만 4사5입  (Postgres round() 가 numeric 에서 4사5입이다)
--   전력기반기금 : 10원 미만 절사
--   청구금액     : 10원 미만 절사
--
-- 주의: 이 판본의 두 계산 함수에는 버그가 있다. 0006 에서 고쳤다.
--       (exists 서브쿼리의 id 가 바깥 버전 표가 아니라 요율 표의 id 로 해석된다)
--       새 프로젝트에 처음부터 적용할 때도 0005 → 0006 순서로 그대로 실행하면 된다.

create type pricing.bill_breakdown as (
    적용요금표      text,
    적용시행일      date,
    계절            text,
    기본요금        numeric,
    전력량요금      numeric,
    기후환경요금    numeric,
    연료비조정요금  numeric,
    전기요금        numeric,
    부가가치세      numeric,
    전력산업기반기금 numeric,
    청구금액        numeric,
    주의            text
);


-- 청구월이 속한 계절을 돌려준다. 주택용 기준(하계 7~8월).
create or replace function pricing.residential_season(billing_month date)
returns text language sql immutable
set search_path = ''
as $$
    select case when extract(month from billing_month) in (7, 8) then '하계' else '기타계절' end;
$$;


-- 주택용 전기요금 계산.
--   household_count 를 2 이상으로 주면 1주택수가구(공동주택 단일계량기) 방식으로 계산한다.
create or replace function pricing.calc_residential_bill(
    usage_kwh       numeric,
    voltage         text default '저압',
    billing_month   date default current_date,
    household_count integer default 1
) returns pricing.bill_breakdown
language plpgsql stable as $$
declare
    v           record;
    season      text := pricing.residential_season(billing_month);
    t1          record;  t2 record;  t3 record;
    per_house   numeric := usage_kwh / greatest(household_count, 1);
    lim1        numeric := case when season = '하계' then 300 else 200 end;
    lim2        numeric := case when season = '하계' then 450 else 400 end;
    basic       numeric;
    energy      numeric;
    climate     numeric;
    fuel        numeric;
    elec        numeric;
    vat         numeric;
    fund        numeric;
    warn        text := null;
    out         pricing.bill_breakdown;
begin
    select * into v from pricing.electricity_tariff_version
    where effective_from <= billing_month
      and exists (select 1 from pricing.electricity_rate r
                  where r.version_id = id and r.contract_type = '주택용전력'
                    and r.voltage = calc_residential_bill.voltage)
    order by effective_from desc limit 1;
    if v is null then
        raise exception '% 시점에 적용할 주택용 % 요금표가 없습니다', billing_month, voltage;
    end if;

    select * into t1 from pricing.electricity_rate
     where version_id=v.id and contract_type='주택용전력' and voltage=calc_residential_bill.voltage
       and season=calc_residential_bill.season and tier=1;
    select * into t2 from pricing.electricity_rate
     where version_id=v.id and contract_type='주택용전력' and voltage=calc_residential_bill.voltage
       and season=calc_residential_bill.season and tier=2;
    select * into t3 from pricing.electricity_rate
     where version_id=v.id and contract_type='주택용전력' and voltage=calc_residential_bill.voltage
       and season=calc_residential_bill.season and tier=3;

    -- 기본요금: 가구별 평균사용량이 속한 단계의 기본요금 × 가구수
    basic := case when per_house <= lim1 then t1.basic_charge
                  when per_house <= lim2 then t2.basic_charge
                  else t3.basic_charge end * greatest(household_count, 1);

    -- 전력량요금: 단계별 적용전력량 × 단계 단가
    energy := least(usage_kwh, lim1 * household_count) * t1.energy_charge
            + greatest(least(usage_kwh, lim2 * household_count)
                       - lim1 * household_count, 0) * t2.energy_charge
            + greatest(usage_kwh - lim2 * household_count, 0) * t3.energy_charge;
    energy := trunc(energy);   -- 원 미만 절사

    select coalesce(won_per_kwh, 0) into climate from pricing.electricity_surcharge
     where kind='기후환경요금' and effective_from <= billing_month
     order by effective_from desc limit 1;
    select coalesce(won_per_kwh, 0) into fuel from pricing.electricity_surcharge
     where kind='연료비조정단가' and effective_from <= billing_month
     order by effective_from desc limit 1;
    if climate is null then
        climate := 0; warn := coalesce(warn || ' / ', '') || '기후환경요금 단가 없음';
    end if;
    if fuel is null then
        fuel := 0; warn := coalesce(warn || ' / ', '') || '연료비조정단가 없음 (0 으로 계산함)';
    end if;

    climate := trunc(climate * usage_kwh);
    fuel    := trunc(fuel * usage_kwh);
    elec    := basic + energy + climate + fuel;
    vat     := round(elec * v.vat_rate);                      -- 원미만 4사5입
    fund    := trunc(elec * coalesce(v.power_fund_rate,0) / 10) * 10;  -- 10원미만 절사

    if usage_kwh > 1000 and (extract(month from billing_month) in (7,8,12,1,2)) then
        warn := coalesce(warn || ' / ', '')
             || '1,000kWh 초과 + 하계/동계라 슈퍼유저요금이 적용되는 구간이다. 이 함수는 반영하지 않는다.';
    end if;
    if v.is_partial then
        warn := coalesce(warn || ' / ', '') || '이 시행일은 주택용만 수록된 불완전 버전이다.';
    end if;

    out := (v.published_label, v.effective_from, season, basic, energy, climate, fuel,
            elec, vat, fund, trunc((elec + vat + fund) / 10) * 10, warn);
    return out;
end $$;


-- 계약전력 기반(일반용·산업용·교육용 등) 시간대별 요금 계산.
create or replace function pricing.calc_demand_bill(
    contract_type   text,
    voltage         text,
    rate_option     text,
    contract_kw     numeric,
    billing_month   date,
    off_peak_kwh    numeric,
    mid_peak_kwh    numeric,
    on_peak_kwh     numeric,
    season          text default null
) returns pricing.bill_breakdown
language plpgsql stable as $$
declare
    v        record;
    ssn      text := coalesce(season,
                 case when extract(month from billing_month) between 6 and 8 then '여름철'
                      when extract(month from billing_month) in (11,12,1,2)   then '겨울철'
                      else '봄·가을철' end);
    total    numeric := off_peak_kwh + mid_peak_kwh + on_peak_kwh;
    basic    numeric;  energy numeric;  climate numeric;  fuel numeric;
    elec     numeric;  vat numeric;  fund numeric;  warn text := null;
    out      pricing.bill_breakdown;
begin
    select * into v from pricing.electricity_tariff_version
    where effective_from <= billing_month
      and exists (select 1 from pricing.electricity_rate r
                  where r.version_id = id and r.contract_type = calc_demand_bill.contract_type)
    order by effective_from desc limit 1;
    if v is null then
        raise exception '% 시점에 적용할 % 요금표가 없습니다', billing_month, contract_type;
    end if;

    select max(r.basic_charge) into basic from pricing.electricity_rate r
     where r.version_id=v.id and r.contract_type=calc_demand_bill.contract_type
       and r.voltage=calc_demand_bill.voltage
       and r.rate_option is not distinct from calc_demand_bill.rate_option;
    if basic is null then
        raise exception '% / % / % 요율을 찾지 못했습니다', contract_type, voltage, rate_option;
    end if;
    basic := basic * contract_kw;

    select trunc(sum(u.kwh * r.energy_charge)) into energy
      from (values ('경부하', off_peak_kwh), ('중간부하', mid_peak_kwh), ('최대부하', on_peak_kwh))
             as u(tz, kwh)
      join pricing.electricity_rate r on r.time_zone = u.tz
     where r.version_id=v.id and r.contract_type=calc_demand_bill.contract_type
       and r.voltage=calc_demand_bill.voltage
       and r.rate_option is not distinct from calc_demand_bill.rate_option
       and r.season = ssn;

    select coalesce(won_per_kwh,0) into climate from pricing.electricity_surcharge
     where kind='기후환경요금' and effective_from <= billing_month
     order by effective_from desc limit 1;
    select coalesce(won_per_kwh,0) into fuel from pricing.electricity_surcharge
     where kind='연료비조정단가' and effective_from <= billing_month
     order by effective_from desc limit 1;
    if fuel is null then
        fuel := 0; warn := '연료비조정단가 없음 (0 으로 계산함)';
    end if;

    climate := trunc(coalesce(climate,0) * total);
    fuel    := trunc(coalesce(fuel,0) * total);
    elec    := basic + energy + climate + fuel;
    vat     := round(elec * v.vat_rate);
    fund    := trunc(elec * coalesce(v.power_fund_rate,0) / 10) * 10;

    out := (v.published_label, v.effective_from, ssn, basic, energy, climate, fuel,
            elec, vat, fund, trunc((elec + vat + fund) / 10) * 10, warn);
    return out;
end $$;
