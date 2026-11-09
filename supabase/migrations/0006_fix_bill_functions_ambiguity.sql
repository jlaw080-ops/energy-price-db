-- 0005 의 계산 함수 버그 수정
--
-- 무엇이 틀렸나
--   0005 에서 "이 버전에 주택용 요율이 있는가" 를 이렇게 확인했다.
--
--     select * from pricing.electricity_tariff_version
--      where effective_from <= billing_month
--        and exists (select 1 from pricing.electricity_rate r
--                     where r.version_id = id ...)          -- ← 이 id
--
--   여기서 id 에는 후보가 둘 있다. 바깥 표(electricity_tariff_version.id)와
--   안쪽 표(electricity_rate.id)다. Postgres 는 더 가까운 쪽, 즉 안쪽을 고른다.
--   그래서 "version_id = 자기 자신의 id" 를 비교하게 되어 사실상 아무 행도 맞지 않고,
--   함수는 늘 '요금표가 없습니다' 예외를 던졌다.
--
--   교훈: 서브쿼리에서 바깥 표의 컬럼을 참조할 때는 반드시 별칭을 붙인다.
--         이름이 겹치면 Postgres 는 조용히 안쪽을 고르고, 오류도 내지 않는다.
--
-- 어떻게 고쳤나
--   1) 바깥 표에 별칭 tv2 를 주어 어느 id 인지 못 헷갈리게 했다. (버그의 본체)
--   2) 모든 컬럼 참조에 표 별칭을 붙였다. 인수 이름(voltage, season, contract_type ...)이
--      컬럼 이름과 같아서, 별칭 없이 쓰면 같은 종류의 혼동이 계속 생긴다.
--   3) 누진 3단계를 못 찾거나 시간대 요율이 3개가 아니면 조용히 틀린 값을 내는 대신
--      예외를 던지게 했다. 틀린 요금은 못 찾은 요금보다 나쁘다.
--   4) 기금율이 비어 있으면(2021-01-01 요금표) 0 으로 뭉개지 않고 '주의' 칸에 적는다.
--      coalesce(..., 0) 은 '자료 없음' 을 '0원' 으로 바꿔버려 가장 위험한 종류의 버그다.
--
--   함수 이름과 인수 이름은 0005 와 똑같이 두었다. 그래야 drop 없이
--   create or replace 로 교체된다. (인수 이름을 바꾸면 Postgres 가 drop 을 요구한다)
--
-- 적용 방법
--   이 파일은 create or replace 뿐이라 몇 번 실행해도 안전하다.
--   Supabase 대시보드 > SQL Editor 에 붙여넣고 Run 하면 된다.
--   (실제 DB 에는 마이그레이션 도구가 아니라 SQL 로 직접 적용했다. 그래서
--    supabase_migrations 이력에는 0005 까지만 남아 있다. 새 프로젝트에
--    처음부터 올릴 때는 0001~0006 을 순서대로 실행하면 같은 상태가 된다.)
--
-- 검증
--   한전이 2024-01-01 주택용 요금표에 직접 인쇄해 둔 계산 예시 두 건과
--   전 항목(기본요금·전력량요금·기후환경요금·연료비조정요금·부가가치세·기금·청구금액)이
--   한 원 단위로 일치한다.
--     · 기타계절 450kWh 저압 1가구  → 109,010원
--     · 기타계절 900kWh 저압 3가구  → 174,830원
--   supabase/tests/verify_bill_functions.sql 로 언제든 다시 확인할 수 있다.


-- ────────────────────────────────────────────────────────────
-- 주택용 전기요금
-- ────────────────────────────────────────────────────────────
-- household_count 를 2 이상으로 주면 1주택수가구(공동주택 단일계량기) 방식으로 계산한다.
-- 누진 경계가 가구수만큼 늘어나 누진 부담이 줄어드는 한전 산정방법이다.
create or replace function pricing.calc_residential_bill(
    usage_kwh       numeric,
    voltage         text default '저압',
    billing_month   date default current_date,
    household_count integer default 1
) returns pricing.bill_breakdown
language plpgsql stable
set search_path = ''   -- 호출자의 search_path 를 따르지 않는다
as $$
declare
    tv        record;
    v_season  text    := pricing.residential_season(billing_month);
    n         integer := greatest(coalesce(household_count, 1), 1);
    t1 record; t2 record; t3 record;
    per_house numeric;
    lim1      numeric;
    lim2      numeric;
    basic numeric; energy numeric; climate numeric; fuel numeric;
    elec numeric; vat numeric; fund numeric;
    warn text := null;
    out   pricing.bill_breakdown;
begin
    per_house := usage_kwh / n;
    lim1 := case when v_season = '하계' then 300 else 200 end;
    lim2 := case when v_season = '하계' then 450 else 400 end;

    select * into tv
      from pricing.electricity_tariff_version tv2
     where tv2.effective_from <= billing_month
       and exists (select 1 from pricing.electricity_rate r
                    where r.version_id = tv2.id            -- ← 0005 에서는 그냥 id 였다
                      and r.contract_type = '주택용전력'
                      and r.voltage = calc_residential_bill.voltage
                      and r.tier is not null)
     order by tv2.effective_from desc limit 1;
    if tv is null then
        raise exception '% 시점에 적용할 주택용 % 요금표가 없습니다',
            billing_month, calc_residential_bill.voltage;
    end if;

    select * into t1 from pricing.electricity_rate r
     where r.version_id = tv.id and r.contract_type = '주택용전력'
       and r.voltage = calc_residential_bill.voltage and r.season = v_season and r.tier = 1;
    select * into t2 from pricing.electricity_rate r
     where r.version_id = tv.id and r.contract_type = '주택용전력'
       and r.voltage = calc_residential_bill.voltage and r.season = v_season and r.tier = 2;
    select * into t3 from pricing.electricity_rate r
     where r.version_id = tv.id and r.contract_type = '주택용전력'
       and r.voltage = calc_residential_bill.voltage and r.season = v_season and r.tier = 3;
    if t1 is null or t2 is null or t3 is null then
        raise exception '% / % / % 의 누진 3단계를 모두 찾지 못했습니다',
            tv.effective_from, calc_residential_bill.voltage, v_season;
    end if;

    -- 기본요금: 가구별 평균사용량이 속한 단계의 기본요금 × 가구수
    basic := case when per_house <= lim1 then t1.basic_charge
                  when per_house <= lim2 then t2.basic_charge
                  else t3.basic_charge end * n;

    -- 전력량요금: 단계 경계가 가구수만큼 늘어난다
    energy := trunc(
          least(usage_kwh, lim1 * n) * t1.energy_charge
        + greatest(least(usage_kwh, lim2 * n) - lim1 * n, 0) * t2.energy_charge
        + greatest(usage_kwh - lim2 * n, 0) * t3.energy_charge);

    select s.won_per_kwh into climate from pricing.electricity_surcharge s
     where s.kind = '기후환경요금' and s.effective_from <= billing_month
     order by s.effective_from desc limit 1;
    select s.won_per_kwh into fuel from pricing.electricity_surcharge s
     where s.kind = '연료비조정단가' and s.effective_from <= billing_month
     order by s.effective_from desc limit 1;
    if climate is null then
        climate := 0;
        warn := '기후환경요금 단가를 찾지 못해 0 으로 계산했다';
    end if;
    if fuel is null then
        fuel := 0;
        warn := concat_ws(' / ', warn, '연료비조정단가를 찾지 못해 0 으로 계산했다');
    end if;

    climate := trunc(climate * usage_kwh);
    fuel    := trunc(fuel * usage_kwh);
    elec    := basic + energy + climate + fuel;

    if tv.vat_rate is null then
        raise exception '% 요금표에 부가가치세율이 없습니다', tv.effective_from;
    end if;
    vat := round(elec * tv.vat_rate);                  -- 원미만 4사5입

    -- 기금율이 비어 있으면 0 으로 뭉개지 말고 알린다. 2021-01-01 요금표가 그렇다.
    if tv.power_fund_rate is null then
        fund := 0;
        warn := concat_ws(' / ', warn,
            format('%s 요금표에 전력산업기반기금율이 없어 기금을 0원으로 뒀다. 청구금액이 실제보다 적다',
                   tv.effective_from));
    else
        fund := trunc(elec * tv.power_fund_rate / 10) * 10;   -- 10원미만 절사
    end if;

    if per_house > 1000 and extract(month from billing_month) in (7, 8, 12, 1, 2) then
        warn := concat_ws(' / ', warn,
            '가구당 1,000kWh 초과 + 하계/동계이므로 슈퍼유저요금 구간이다. 이 함수는 반영하지 않는다');
    end if;
    if tv.is_partial then
        warn := concat_ws(' / ', warn, '이 시행일 요금표는 주택용만 수록된 불완전 버전이다');
    end if;

    out := (tv.published_label, tv.effective_from, v_season,
            basic, energy, climate, fuel, elec, vat, fund,
            trunc((elec + vat + fund) / 10) * 10,      -- 청구금액: 10원미만 절사
            warn);
    return out;
end $$;


-- ────────────────────────────────────────────────────────────
-- 계약전력 기반 시간대별 요금 (일반용·산업용·교육용 등)
-- ────────────────────────────────────────────────────────────
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
language plpgsql stable
set search_path = ''   -- 호출자의 search_path 를 따르지 않는다
as $$
declare
    tv    record;
    -- 계절 이름 체계가 종별마다 다르다. 명시하지 않으면 차례로 시도한다.
    cands text[] := case
        when calc_demand_bill.season is not null then array[calc_demand_bill.season]
        else array[
            case when extract(month from billing_month) between 6 and 8 then '여름철'
                 when extract(month from billing_month) in (11,12,1,2)   then '겨울철'
                 else '봄·가을철' end,
            case when extract(month from billing_month) in (1,2,6,7,8,11,12) then '여름·겨울철'
                 else '봄·가을철' end
        ] end;
    ssn   text;
    total numeric := coalesce(off_peak_kwh,0) + coalesce(mid_peak_kwh,0)
                   + coalesce(on_peak_kwh,0);
    unit text; matched integer := 0;
    avail text;
    basic numeric; energy numeric; climate numeric; fuel numeric;
    elec numeric; vat numeric; fund numeric;
    warn text := null;
    out   pricing.bill_breakdown;
begin
    select * into tv
      from pricing.electricity_tariff_version tv2
     where tv2.effective_from <= billing_month
       and exists (select 1 from pricing.electricity_rate r
                    where r.version_id = tv2.id            -- ← 0005 에서는 그냥 id 였다
                      and r.contract_type = calc_demand_bill.contract_type)
     order by tv2.effective_from desc limit 1;
    if tv is null then
        raise exception '% 시점에 적용할 % 요금표가 없습니다',
            billing_month, calc_demand_bill.contract_type;
    end if;

    -- 기본요금 단가는 (종별·전압·선택) 안에서 유일하다. 전 버전에서 확인했다.
    select min(r.basic_charge), min(r.basic_charge_unit) into basic, unit
      from pricing.electricity_rate r
     where r.version_id = tv.id
       and r.contract_type = calc_demand_bill.contract_type
       and r.voltage     is not distinct from calc_demand_bill.voltage
       and r.rate_option is not distinct from calc_demand_bill.rate_option;
    if basic is null then
        raise exception '% / % / % 의 기본요금을 찾지 못했습니다',
            calc_demand_bill.contract_type, calc_demand_bill.voltage,
            calc_demand_bill.rate_option;
    end if;
    if unit is distinct from '원/kW' then
        warn := format('기본요금 단위가 %s 다. 계약전력을 곱하는 이 계산이 맞는지 확인이 필요하다', unit);
    end if;
    basic := basic * contract_kw;

    foreach ssn in array cands loop
        select trunc(sum(u.kwh * r.energy_charge)), count(*) into energy, matched
          from (values ('경부하',   coalesce(off_peak_kwh,0)),
                       ('중간부하', coalesce(mid_peak_kwh,0)),
                       ('최대부하', coalesce(on_peak_kwh,0))) as u(tz, kwh)
          join pricing.electricity_rate r on r.time_zone = u.tz
         where r.version_id = tv.id
           and r.contract_type = calc_demand_bill.contract_type
           and r.voltage     is not distinct from calc_demand_bill.voltage
           and r.rate_option is not distinct from calc_demand_bill.rate_option
           and r.season = ssn;
        exit when coalesce(matched,0) = 3;
    end loop;

    -- 계절별 요금(일반용(갑)Ⅰ 등)에는 시간대 요율이 없다. 그때 0 이 잡힌다.
    if coalesce(matched, 0) <> 3 then
        select string_agg(distinct coalesce(r.season,'(없음)'), ', ') into avail
          from pricing.electricity_rate r
         where r.version_id = tv.id
           and r.contract_type = calc_demand_bill.contract_type
           and r.voltage     is not distinct from calc_demand_bill.voltage
           and r.rate_option is not distinct from calc_demand_bill.rate_option
           and r.time_zone is not null;
        raise exception '% / % / % 의 시간대 요율이 3개가 아니라 %개 잡혔습니다. 시도한 계절: %. 이 조합의 시간대별 계절: %',
            calc_demand_bill.contract_type, calc_demand_bill.voltage,
            calc_demand_bill.rate_option, coalesce(matched,0),
            array_to_string(cands, ', '),
            coalesce(avail, '(시간대별 요율이 없음 — 계절별 요금이면 calc_seasonal_bill 을 쓰세요)');
    end if;

    select s.won_per_kwh into climate from pricing.electricity_surcharge s
     where s.kind = '기후환경요금' and s.effective_from <= billing_month
     order by s.effective_from desc limit 1;
    select s.won_per_kwh into fuel from pricing.electricity_surcharge s
     where s.kind = '연료비조정단가' and s.effective_from <= billing_month
     order by s.effective_from desc limit 1;
    if climate is null then
        climate := 0;
        warn := concat_ws(' / ', warn, '기후환경요금 단가를 찾지 못해 0 으로 계산했다');
    end if;
    if fuel is null then
        fuel := 0;
        warn := concat_ws(' / ', warn, '연료비조정단가를 찾지 못해 0 으로 계산했다');
    end if;

    climate := trunc(climate * total);
    fuel    := trunc(fuel * total);
    elec    := basic + energy + climate + fuel;

    if tv.vat_rate is null then
        raise exception '% 요금표에 부가가치세율이 없습니다', tv.effective_from;
    end if;
    vat := round(elec * tv.vat_rate);
    if tv.power_fund_rate is null then
        fund := 0;
        warn := concat_ws(' / ', warn,
            format('%s 요금표에 전력산업기반기금율이 없어 기금을 0원으로 뒀다. 청구금액이 실제보다 적다',
                   tv.effective_from));
    else
        fund := trunc(elec * tv.power_fund_rate / 10) * 10;
    end if;

    warn := concat_ws(' / ', warn, '역률요금·수요관리 할인 등 부가 정산은 포함하지 않는다');

    out := (tv.published_label, tv.effective_from, ssn,
            basic, energy, climate, fuel, elec, vat, fund,
            trunc((elec + vat + fund) / 10) * 10, warn);
    return out;
end $$;


comment on function pricing.calc_residential_bill is
    '주택용 전기요금 계산. 한전 2024-01-01 요금표의 계산 예시(450kWh 저압 1가구 → 109,010원, '
    '900kWh 저압 3가구 → 174,830원)로 전 항목 검증했다. 슈퍼유저요금과 복지할인은 반영하지 않는다.';
comment on function pricing.calc_demand_bill is
    '계약전력 기반(일반용·산업용·교육용 등) 시간대별 전기요금 계산. '
    '기본요금 = 단가 × 계약전력 이며, 역률요금과 각종 할인은 반영하지 않는다.';
