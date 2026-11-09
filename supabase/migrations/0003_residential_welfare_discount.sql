-- 주택용 복지할인 요금제도
-- 복지할인은 종합요금표에 없고 주택용 별도 요금표에만 실린다.

create table if not exists pricing.residential_welfare_discount (
    id              bigserial primary key,
    effective_from  date        not null,
    target          text        not null,
    detail          text,
    discount_type   text        not null check (discount_type in ('정액할인', '정률할인')),
    percent         smallint,
    monthly_cap     integer,
    summer_cap      integer,
    source_file     text,
    note            text,
    created_at      timestamptz not null default now(),
    unique (effective_from, target)
);

comment on table pricing.residential_welfare_discount is
    '여름철은 6월 1일~8월 31일. 기초생활수급자·차상위계층 장애할인은 정률할인(30%)과 중복 적용 가능.';

create index if not exists residential_welfare_discount_idx
    on pricing.residential_welfare_discount (effective_from desc, discount_type);

alter table pricing.residential_welfare_discount enable row level security;

do $$
begin
    if not exists (select 1 from pg_policies
        where schemaname='pricing' and tablename='residential_welfare_discount'
          and policyname='residential_welfare_discount_read') then
        create policy residential_welfare_discount_read
            on pricing.residential_welfare_discount
            for select to anon, authenticated using (true);
    end if;
end $$;
