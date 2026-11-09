-- 기후환경요금 · 연료비조정단가
--
-- 이 두 단가는 요금표 개정과 무관하게 따로 바뀐다.
-- 연료비조정단가는 분기마다, 기후환경요금은 연 단위로 조정되므로
-- electricity_tariff_version 에 묶지 않고 자체 시행일을 가진 표로 둔다.

create table if not exists pricing.electricity_surcharge (
    id              bigserial primary key,
    kind            text        not null check (kind in ('기후환경요금', '연료비조정단가')),
    effective_from  date        not null,
    period_label    text,                       -- '2026년 4분기'
    won_per_kwh     numeric(10,2) not null,
    source          text        not null,
    source_type     text        not null check (source_type in ('요금표', '보도', '한전공시')),
    confidence      text        not null check (confidence in ('high', 'medium', 'low')),
    note            text,
    created_at      timestamptz not null default now(),
    unique (kind, effective_from)
);

comment on column pricing.electricity_surcharge.source_type is
    '요금표 = 레포의 원본 PDF 에서 직접 확인한 값. 보도 = 언론 보도 기반으로 한전 공식 고시 미확인. 한전공시 = 한전 공식 자료 확인.';

create index if not exists electricity_surcharge_lookup_idx
    on pricing.electricity_surcharge (kind, effective_from desc);

create or replace view pricing.electricity_surcharge_current as
select distinct on (kind)
       kind, effective_from, period_label, won_per_kwh, source_type, confidence, note
from pricing.electricity_surcharge
where effective_from <= current_date
order by kind, effective_from desc;

alter table pricing.electricity_surcharge enable row level security;

do $$
begin
    if not exists (select 1 from pg_policies
        where schemaname='pricing' and tablename='electricity_surcharge'
          and policyname='electricity_surcharge_read') then
        create policy electricity_surcharge_read on pricing.electricity_surcharge
            for select to anon, authenticated using (true);
    end if;
end $$;
