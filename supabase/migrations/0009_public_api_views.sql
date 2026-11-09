-- public 스키마에 바라보기용 뷰·함수를 둔다
--
-- 왜 필요했나
--   PostgREST 는 요청에 스키마 지정 헤더(Accept-Profile)가 없으면
--   '공개된 스키마 중 첫 번째' 에서 표를 찾는다. 기본값은 public 이다.
--   그래서 브라우저 주소창으로 부르면 pricing 을 공개해 두었더라도
--
--     {"code":"PGRST205","message":"Could not find the table
--      'public.renewable_equipment_price' in the schema cache"}
--
--   가 난다. 헤더를 붙일 수 없는 주소창·엑셀·간단한 fetch 에서는 방법이 없다.
--
-- 어떻게 했나
--   public 에 pricing 을 그대로 비추는 뷰를 두었다. public 은 Supabase 가
--   기본으로 공개하므로 대시보드 설정이 아예 필요 없어진다.
--
--     public.renewable_equipment_price  →  pricing.renewable_equipment_price
--
--   자료는 여전히 pricing 한 곳에만 있다. 뷰는 창문일 뿐 사본이 아니다.
--   단가를 고치면 양쪽에 동시에 반영된다.
--
--   security_invoker = true 가 중요하다. 이게 없으면 뷰가 '만든 사람' 권한으로
--   돌아 pricing 쪽 RLS 를 건너뛴다. true 면 '부르는 사람' 권한이라 그대로 적용된다.
--
-- 계산 함수도 감쌌다
--   returns pricing.bill_breakdown 대신 컬럼을 하나하나 적은 returns table 로 썼다.
--   공개되지 않은 스키마의 복합타입을 PostgREST 가 풀어야 하는 상황을 피하려는 것이다.
--   다만 그 때문에 결과가 '객체 하나' 가 아니라 '행이 하나인 배열' 로 온다.
--   호출하는 쪽에서 [0] 을 꺼내거나 .single() 을 쓰면 된다.
--
-- 검증
--   anon 역할로 바꿔 직접 읽어 확인했다 (장비단가 7, 기타단가 1, 요율 320).
--   한전 계산 예시 2건과 손계산 2건도 public 경유로 전부 일치했다.

-- ── 바라보기용 뷰 ───────────────────────────────────────────
create or replace view public.renewable_equipment_price with (security_invoker = true)
  as select * from pricing.renewable_equipment_price;
create or replace view public.misc_price with (security_invoker = true)
  as select * from pricing.misc_price;
create or replace view public.electricity_rate with (security_invoker = true)
  as select * from pricing.electricity_rate;
create or replace view public.electricity_tariff_version with (security_invoker = true)
  as select * from pricing.electricity_tariff_version;
create or replace view public.electricity_surcharge with (security_invoker = true)
  as select * from pricing.electricity_surcharge;
create or replace view public.residential_welfare_discount with (security_invoker = true)
  as select * from pricing.residential_welfare_discount;
create or replace view public.gas_wholesale_price with (security_invoker = true)
  as select * from pricing.gas_wholesale_price;
create or replace view public.gas_power_generation_monthly with (security_invoker = true)
  as select * from pricing.gas_power_generation_monthly;
create or replace view public.electricity_rate_current with (security_invoker = true)
  as select * from pricing.electricity_rate_current;
create or replace view public.electricity_surcharge_current with (security_invoker = true)
  as select * from pricing.electricity_surcharge_current;
create or replace view public.electricity_tariff_coverage with (security_invoker = true)
  as select * from pricing.electricity_tariff_coverage;

-- pricing 쪽 뷰도 호출자 권한으로 바꾼다.
-- 뷰는 기본이 '만든 사람' 권한이라 RLS 를 건너뛴다 (advisor 가 ERROR 로 잡는다).
alter view pricing.electricity_rate_current      set (security_invoker = true);
alter view pricing.electricity_surcharge_current set (security_invoker = true);
alter view pricing.electricity_tariff_coverage   set (security_invoker = true);


-- ── 계산 함수 감싸기 ────────────────────────────────────────
create or replace function public.calc_residential_bill(
    usage_kwh numeric, voltage text default '저압',
    billing_month date default current_date, household_count integer default 1)
returns table (적용요금표 text, 적용시행일 date, 계절 text,
               기본요금 numeric, 전력량요금 numeric, 기후환경요금 numeric,
               연료비조정요금 numeric, 전기요금 numeric, 부가가치세 numeric,
               전력산업기반기금 numeric, 청구금액 numeric, 주의 text)
language sql stable set search_path = '' as $$
  select * from pricing.calc_residential_bill(usage_kwh, voltage, billing_month, household_count);
$$;

create or replace function public.calc_seasonal_bill(
    contract_type text, voltage text, rate_option text, contract_kw numeric,
    billing_month date, usage_kwh numeric, season text default null)
returns table (적용요금표 text, 적용시행일 date, 계절 text,
               기본요금 numeric, 전력량요금 numeric, 기후환경요금 numeric,
               연료비조정요금 numeric, 전기요금 numeric, 부가가치세 numeric,
               전력산업기반기금 numeric, 청구금액 numeric, 주의 text)
language sql stable set search_path = '' as $$
  select * from pricing.calc_seasonal_bill(contract_type, voltage, rate_option,
                                           contract_kw, billing_month, usage_kwh, season);
$$;

create or replace function public.calc_demand_bill(
    contract_type text, voltage text, rate_option text, contract_kw numeric,
    billing_month date, off_peak_kwh numeric, mid_peak_kwh numeric,
    on_peak_kwh numeric, season text default null)
returns table (적용요금표 text, 적용시행일 date, 계절 text,
               기본요금 numeric, 전력량요금 numeric, 기후환경요금 numeric,
               연료비조정요금 numeric, 전기요금 numeric, 부가가치세 numeric,
               전력산업기반기금 numeric, 청구금액 numeric, 주의 text)
language sql stable set search_path = '' as $$
  select * from pricing.calc_demand_bill(contract_type, voltage, rate_option, contract_kw,
                                         billing_month, off_peak_kwh, mid_peak_kwh,
                                         on_peak_kwh, season);
$$;

grant select  on all tables    in schema public to anon, authenticated;
grant execute on all functions in schema public to anon, authenticated;

-- PostgREST 가 스키마 캐시를 새로 읽게 한다. 안 하면 방금 만든 것이 안 보인다.
notify pgrst, 'reload schema';
