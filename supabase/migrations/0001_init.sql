-- energinno-DB 단가 데이터베이스 초기 스키마
--
-- 적용 방법 (둘 중 하나)
--   1) Supabase 대시보드 > SQL Editor 에 이 파일 내용을 붙여넣고 Run
--   2) supabase CLI: supabase db push
--
-- 설계 원칙
--   · 레포의 JSON 파일이 원본(single source of truth)이고, 이 DB는 조회용 사본이다.
--   · 요금은 개정될 뿐 과거 값이 사라지지 않으므로 모든 표에 시행일(effective_from)을 둔다.
--   · 종별마다 요금 구조가 다르므로 전기요금은 '요율 한 줄'(rate line) 단위로 정규화한다.

create schema if not exists pricing;

-- ════════════════════════════════════════════════════════════
-- 1. 전기요금 (한국전력공사)
-- ════════════════════════════════════════════════════════════

-- 요금표 1부 = 버전 1건
create table if not exists pricing.electricity_tariff_version (
    id              bigserial primary key,
    effective_from  date        not null,
    published_label text,                       -- 예: '2026년 4월 16일 시행'
    provider        text        not null default '한국전력공사',
    source_file     text        not null,       -- 레포 내 원본 PDF 경로
    vat_rate                 numeric(5,4),      -- 부가가치세율 (0.10)
    power_fund_rate          numeric(5,4),      -- 전력산업기반기금율 (0.027)
    climate_charge_per_kwh   numeric(10,2),     -- 기후환경요금 단가 (요금표 미표기 시 null)
    fuel_adjustment_per_kwh  numeric(10,2),     -- 연료비조정단가 (분기 변동, 미표기 시 null)
    note            text,
    created_at      timestamptz not null default now(),
    unique (effective_from, source_file)
);

comment on column pricing.electricity_tariff_version.climate_charge_per_kwh is
    '요금표에 단가가 적혀있지 않으면 null. 한전 공지에서 별도로 채워 넣는다.';

-- 요율 한 줄 = 계약종별 × 전압 × 선택요금 × 계절 × 시간대(or 누진단계)
create table if not exists pricing.electricity_rate (
    id              bigserial primary key,
    version_id      bigint      not null references pricing.electricity_tariff_version(id) on delete cascade,

    contract_type   text        not null,       -- 일반용전력(을), 주택용전력, 산업용전력(갑)Ⅱ ...
    rate_structure  text        not null,       -- progressive | seasonal | time_of_use | flat | mixed
    contract_power  text,                       -- '계약전력 300kW 이상'
    voltage         text,                       -- 저압 | 고압A | 고압B | 고압C
    rate_option     text,                       -- 선택Ⅰ | 선택Ⅱ | 선택Ⅲ

    basic_charge        numeric(12,2),          -- 기본요금
    basic_charge_unit   text,                   -- 원/kW | 원/호 | 원/W
    basic_charge_formula text,                  -- 산식으로만 정의되는 경우 (심야전력(을)Ⅱ)

    season          text,                       -- 여름철 | 봄·가을철 | 겨울철 | 하계 | 기타계절 | 연중
    time_zone       text,                       -- 경부하 | 중간부하 | 최대부하 | 심야시간 | 기타시간
    tier            smallint,                   -- 누진 단계 (주택용)
    usage_range     text,                       -- '201~400kWh 사용'
    energy_label    text,                       -- '다음 200kWh까지'
    energy_charge   numeric(12,2),              -- 전력량요금 (원/kWh)

    note            text
);

create index if not exists electricity_rate_lookup_idx
    on pricing.electricity_rate (version_id, contract_type, voltage, rate_option);

-- 자주 쓰는 조회: 특정 시점에 유효한 요율
create or replace view pricing.electricity_rate_current as
select r.*, v.effective_from, v.published_label
from pricing.electricity_rate r
join pricing.electricity_tariff_version v on v.id = r.version_id
where v.effective_from = (
    select max(effective_from)
    from pricing.electricity_tariff_version
    where effective_from <= current_date
);

-- ════════════════════════════════════════════════════════════
-- 2. 가스요금 (한국가스공사)
-- ════════════════════════════════════════════════════════════

-- 용도별 도매요금 (시점 스냅샷)
create table if not exists pricing.gas_wholesale_price (
    id              bigserial primary key,
    effective_from  date        not null,
    sector          text        not null,       -- 민수용 | 상업용 | 도시가스발전용
    use_type        text        not null,       -- 주택용 | 일반용 | 냉난방공조용 | 연료전지용 ...
    season          text        not null,       -- 단일요금 | 동절기 | 하절기 | 기타월
    feedstock_cost  numeric(12,4) not null,     -- 원료비 (원/MJ)
    supply_cost     numeric(12,4) not null,     -- 공급비용 (원/MJ)
    wholesale_price numeric(12,4) not null,     -- 도매요금 (원/MJ)
    source_file     text,
    unique (effective_from, sector, use_type, season)
);

-- 발전용 천연가스요금 월별 시계열
create table if not exists pricing.gas_power_generation_monthly (
    id                        bigserial primary key,
    month                     date        not null unique,  -- 해당 월 1일
    feedstock_cost_per_nm3    numeric(12,2) not null,
    supply_cost_per_nm3       numeric(12,2) not null,
    feedstock_cost_per_gj     numeric(12,2) not null,
    supply_cost_per_gj        numeric(12,2) not null,
    total_per_nm3             numeric(12,2) generated always as
                                  (feedstock_cost_per_nm3 + supply_cost_per_nm3) stored,
    total_per_gj              numeric(12,2) generated always as
                                  (feedstock_cost_per_gj + supply_cost_per_gj) stored,
    source_file               text
);

-- ════════════════════════════════════════════════════════════
-- 3. 신재생에너지 장비 단가
-- ════════════════════════════════════════════════════════════

create table if not exists pricing.renewable_equipment_price (
    id              bigserial primary key,
    slug            text        not null,       -- 안정적인 식별자 (pv-module-mono-550w)
    category        text        not null,       -- 태양광 | 태양열 | 지열 | 연료전지 | 풍력 | ESS | 수열 | 바이오
    subcategory     text,                       -- 모듈 | 인버터 | 구조물 | 히트펌프 | 천공 ...
    name            text        not null,
    spec            text,                       -- 단결정 550W급
    cost_type       text        not null,       -- 자재비 | 설치비 | 턴키(합계)
    unit_price      numeric(14,2) not null,
    price_unit      text        not null,       -- 원/kW | 원/m2 | 원/m | 원/식
    scope           text,                       -- 단가에 포함/제외되는 범위
    base_date       date        not null,       -- 단가 기준일
    source          text,                       -- 출처 (견적서, 고시, 실적자료 등)
    source_type     text,                       -- 견적 | 고시 | 실적 | 문헌
    note            text,
    created_at      timestamptz not null default now(),
    unique (slug, base_date)
);

create index if not exists renewable_equipment_category_idx
    on pricing.renewable_equipment_price (category, base_date desc);

-- ════════════════════════════════════════════════════════════
-- 4. 기타 단가
-- ════════════════════════════════════════════════════════════

create table if not exists pricing.misc_price (
    id              bigserial primary key,
    slug            text        not null,
    category        text        not null,
    name            text        not null,
    spec            text,
    unit_price      numeric(14,2) not null,
    price_unit      text        not null,
    base_date       date        not null,
    source          text,
    source_type     text,
    note            text,
    created_at      timestamptz not null default now(),
    unique (slug, base_date)
);

-- ════════════════════════════════════════════════════════════
-- 5. 접근 권한
-- ════════════════════════════════════════════════════════════
-- 단가는 공개 고시 자료이므로 읽기는 열고, 쓰기는 service_role 에게만 허용한다.
-- (service_role 키는 서버에서만 쓰고 브라우저에 노출하지 않는다.)

do $$
declare
    t text;
begin
    foreach t in array array[
        'electricity_tariff_version', 'electricity_rate',
        'gas_wholesale_price', 'gas_power_generation_monthly',
        'renewable_equipment_price', 'misc_price'
    ] loop
        execute format('alter table pricing.%I enable row level security', t);
        -- create policy 는 if not exists 를 지원하지 않으므로 직접 확인한다.
        if not exists (
            select 1 from pg_policies
            where schemaname = 'pricing' and tablename = t and policyname = t || '_read'
        ) then
            execute format(
                'create policy %I on pricing.%I for select to anon, authenticated using (true)',
                t || '_read', t);
        end if;
    end loop;
end $$;

-- 참고: 다른 앱이 Supabase REST API(PostgREST)로 이 표들을 읽으려면
-- Project Settings > API > Exposed schemas 에 'pricing' 을 추가해야 한다.
-- 추가하지 않으면 SQL Editor 와 서버사이드 접속으로만 읽을 수 있다.
