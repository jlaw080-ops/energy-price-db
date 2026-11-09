-- REST API 로 읽을 수 있게 권한을 연다
--
-- 왜 필요했나
--   0001 에서 RLS 정책(읽기는 anon·authenticated 허용)만 만들고
--   역할에 대한 GRANT 를 빠뜨렸다. 둘은 다른 장치다.
--
--     GRANT  : "이 역할이 이 표를 볼 수 있는가"      ← 문을 여는 열쇠
--     RLS    : "볼 수 있다면 어느 행까지 보이는가"   ← 방 안의 칸막이
--
--   열쇠가 없으면 칸막이가 아무리 열려 있어도 들어가지 못한다.
--   public 스키마는 Supabase 가 기본으로 열어두지만, pricing 처럼 직접 만든
--   스키마는 열어주지 않는다. 그래서 대시보드에서 스키마를 공개해도
--   "permission denied for schema pricing" 이 났다.
--
-- 이 파일을 실행한 뒤에도 한 가지가 더 필요하다 (SQL 로는 못 한다)
--   Supabase 대시보드 → Project Settings → API → Exposed schemas 에
--   'pricing' 을 추가해야 REST API 경로가 열린다.
--
-- 쓰기 권한은 주지 않는다
--   SELECT 와 EXECUTE 만 연다. 단가를 고치는 일은 레포의 JSON 을 고치고
--   seed SQL 을 돌리는 경로로만 하도록 유지한다.
--
-- ⚠️ 장비단가·기타단가는 영업 정보일 수 있다
--   지금은 전기·가스 요금(공개 고시 자료)과 같은 수준으로 anon 에게 열어 두었다.
--   외부에 보이면 안 되는 단가라면 아래 두 줄로 anon 권한만 거두면 된다.
--     revoke select on pricing.renewable_equipment_price from anon;
--     revoke select on pricing.misc_price from anon;
--   그러면 로그인한 사용자(authenticated)만 읽는다.

grant usage on schema pricing to anon, authenticated;
grant select on all tables in schema pricing to anon, authenticated;
grant execute on all functions in schema pricing to anon, authenticated;

-- 앞으로 추가될 표·함수에도 자동으로 적용되게 한다.
-- 이게 없으면 표를 하나 만들 때마다 grant 를 다시 해야 한다.
alter default privileges in schema pricing grant select on tables to anon, authenticated;
alter default privileges in schema pricing grant execute on functions to anon, authenticated;


-- 계산 함수의 search_path 를 고정한다
--
--   함수가 호출자의 search_path 를 그대로 따르면, 호출자가 pricing 보다 앞서는
--   스키마에 electricity_rate 라는 가짜 표를 만들어 두는 식으로 바꿔치기할 수 있다.
--   빈 값으로 두면 pg_catalog 만 쓰이고, 우리 함수는 모든 표를 pricing. 으로
--   명시하고 있으므로 동작은 그대로다.
--
--   주의: create or replace function 은 기존 SET 절을 지운다.
--         0005~0007 파일에도 같은 설정을 넣어 두었으니 순서는 상관없다.

alter function pricing.residential_season(date) set search_path = '';
alter function pricing.calc_residential_bill(numeric,text,date,integer) set search_path = '';
alter function pricing.calc_demand_bill(text,text,text,numeric,date,numeric,numeric,numeric,text) set search_path = '';
alter function pricing.calc_seasonal_bill(text,text,text,numeric,date,numeric,text) set search_path = '';
