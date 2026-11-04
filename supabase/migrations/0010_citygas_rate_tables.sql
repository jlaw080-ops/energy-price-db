-- 도시가스 요금표(공시용 엑셀) 월별 시계열
--
-- 출처
--   enerbuild/energinno-knowledge-bank 저장소(jlaw80-price 브랜치)의
--   '도시가스요금 단가' 폴더에 있는 엑셀 93개. 2016-01 ~ 2026-11 월별이다.
--   각 파일의 '요금표(MJ)' 시트에 도매요금 1줄과 시·도별 소매요금 33줄이 있다.
--
-- 기존 pricing.gas_wholesale_price 와 무엇이 다른가
--   저쪽: 한국가스공사 공시. 원료비·공급비용으로 나뉘지만 시점이 2개뿐이다.
--   이쪽: 93개 시점. 총액만 있지만 용도가 훨씬 잘게 나뉜다(주택용 취사/난방/중앙난방,
--         일반용1/2, 열병합1/2, 열전용1/2/3 등 27종).
--   둘은 서로를 대체하지 않는다. 2026-09-01 시점의 10개 용도를 대조해 전부 일치했다.
--
-- 소매요금을 따로 두는 이유
--   도매요금은 가스공사가 전국 단일로 정하지만, 소매요금은 시·도지사 승인으로
--   지역마다 다르게 정해진다. 경제성분석에서 실제 연료비로 쓰는 것은 소매요금이다.
--   도매 변동이 지역별로 늦게 반영되기도 한다(원본 파일명의 'pending/미반영' 표기).

create table if not exists pricing.citygas_wholesale_monthly (
    id             bigserial primary key,
    effective_from date          not null,
    use_category   text          not null,   -- 주택용, 일반용1, 냉난방공조용, 연료전지용 ...
    use_detail     text          not null default '',  -- 취사용 / 동절기 / 열전용(1) ...
    won_per_mj     numeric(10,4) not null,
    note           text,
    unique (effective_from, use_category, use_detail)
);

create table if not exists pricing.citygas_retail_monthly (
    id             bigserial primary key,
    effective_from date          not null,
    region         text          not null,   -- 서울특별시, 경남 창원시 ...
    use_category   text          not null,
    use_detail     text          not null default '',
    won_per_mj     numeric(10,4) not null,
    note           text,
    unique (effective_from, region, use_category, use_detail)
);

-- 공급회사와 기본요금은 (시점·지역)마다 하나뿐이라 요율과 분리했다.
-- 기본요금은 '(취) 1,100 (지) 1,700' 처럼 지역마다 형식이 달라 원문 그대로 둔다.
create table if not exists pricing.citygas_retail_region (
    id                bigserial primary key,
    effective_from    date not null,
    region            text not null,
    company           text,
    basic_charge_note text,
    unique (effective_from, region)
);

create index if not exists citygas_wholesale_lookup_idx
    on pricing.citygas_wholesale_monthly (use_category, effective_from desc);
create index if not exists citygas_retail_lookup_idx
    on pricing.citygas_retail_monthly (region, use_category, effective_from desc);

alter table pricing.citygas_wholesale_monthly enable row level security;
alter table pricing.citygas_retail_monthly    enable row level security;
alter table pricing.citygas_retail_region     enable row level security;

do $$
declare t text;
begin
    foreach t in array array['citygas_wholesale_monthly','citygas_retail_monthly','citygas_retail_region'] loop
        if not exists (select 1 from pg_policies
                        where schemaname='pricing' and tablename=t and policyname=t||'_read') then
            execute format('create policy %I on pricing.%I for select to anon, authenticated using (true)',
                           t||'_read', t);
        end if;
    end loop;
end $$;

-- public 에 바라보기용 뷰 (0009 와 같은 이유 — 헤더 없이도 REST 로 읽히게)
create or replace view public.citygas_wholesale_monthly with (security_invoker = true)
  as select * from pricing.citygas_wholesale_monthly;
create or replace view public.citygas_retail_monthly with (security_invoker = true)
  as select * from pricing.citygas_retail_monthly;
create or replace view public.citygas_retail_region with (security_invoker = true)
  as select * from pricing.citygas_retail_region;

grant select on all tables in schema pricing to anon, authenticated;
grant select on all tables in schema public  to anon, authenticated;
notify pgrst, 'reload schema';
