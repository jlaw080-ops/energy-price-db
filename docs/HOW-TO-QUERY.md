# 단가 꺼내 쓰는 방법

Supabase SQL Editor 에 붙여넣고 쓰는 예시입니다.
프로젝트는 `jlaw80_DB` (<https://supabase.com/dashboard/project/qhnyrkbmkzhsgthcxoiw>),
표는 모두 `pricing` 스키마 안에 있습니다.

---

## 1. 지금 적용되는 전기요금 보기

```sql
select contract_type as 종별, voltage as 전압, rate_option as 선택,
       basic_charge as 기본요금, season as 계절, time_zone as 시간대,
       energy_charge as "전력량요금(원/kWh)"
from pricing.electricity_rate_current
where contract_type = '일반용전력(을)'
order by voltage, rate_option, season, time_zone;
```

`electricity_rate_current` 뷰는 **오늘 기준 가장 최근 요금표**만 보여줍니다.
과거 시점으로 보려면 `electricity_rate` 를 `electricity_tariff_version` 과 조인해
`effective_from` 을 직접 고르세요.

## 2. 기후환경요금·연료비조정단가

```sql
select * from pricing.electricity_surcharge_current;
```

이 두 단가는 요금표와 따로 움직여서 별도 표에 있습니다.
**`source_type` 을 꼭 확인하세요.** `보도` 면 한전 공식 고시로 확인되지 않은 값입니다.

## 3. 전기요금 계산 (실제로 써먹는 예시)

> 💡 **더 쉬운 길이 있습니다.** 아래 쿼리는 계산 과정을 보여주기 위한 것입니다.
> 금액만 필요하면 [9절의 계산 함수](#9-전기요금-계산-함수--긴-쿼리-대신-한-줄로)를 쓰세요.
> `select * from pricing.calc_residential_bill(450, '저압', '2025-07-15');` 한 줄로 끝납니다.

일반용전력(을) 고압A 선택Ⅱ, 계약전력 300kW, 2026년 10월(봄·가을철),
경부하 20,000 / 중간부하 30,000 / 최대부하 15,000 kWh 를 쓴 경우입니다.
**조건 부분만 바꿔서 쓰면 됩니다.**

```sql
with 조건 as (
  select '2026-10-01'::date as 청구월, '일반용전력(을)' as 종별, '고압A' as 전압,
         '선택Ⅱ' as 선택, '봄·가을철' as 계절, 300 as 계약전력
), 사용량(time_zone, kwh) as (
  values ('경부하',20000),('중간부하',30000),('최대부하',15000)
), 버전 as (
  select v.* from pricing.electricity_tariff_version v, 조건 c
  where v.effective_from <= c.청구월
  order by v.effective_from desc limit 1
), 요율 as (
  select r.time_zone, r.energy_charge, r.basic_charge
  from pricing.electricity_rate r, 버전 v, 조건 c
  where r.version_id = v.id and r.contract_type = c.종별
    and r.voltage = c.전압 and r.rate_option = c.선택 and r.season = c.계절
), 단가 as (
  select max(case when kind='기후환경요금' then won_per_kwh end) as 기후환경,
         max(case when kind='연료비조정단가' then won_per_kwh end) as 연료비조정
  from pricing.electricity_surcharge_current
)
select (select published_label from 버전) as 적용요금표,
       (select max(basic_charge) from 요율) * (select 계약전력 from 조건) as 기본요금,
       (select sum(u.kwh * y.energy_charge) from 사용량 u join 요율 y using (time_zone)) as 전력량요금,
       (select sum(kwh) from 사용량) * (select 기후환경 from 단가) as 기후환경요금,
       (select sum(kwh) from 사용량) * (select 연료비조정 from 단가) as 연료비조정요금;
```

위 조건의 결과는 기본요금 2,496,000원 + 전력량요금 7,147,500원 +
기후환경요금 585,000원 + 연료비조정 325,000원 = **전기요금 10,553,500원** 입니다.

### ⚠️ 청구금액 반올림 — 파이썬 `round()` 를 쓰면 틀립니다

| 항목 | 규칙 |
|---|---|
| 부가가치세 | 전기요금 × 10%, **원 미만 4사5입** |
| 전력산업기반기금 | 전기요금 × 요율, **10원 미만 절사** |
| 청구금액 | 세 가지 합계에서 **10원 미만 절사** |

단순히 `× 1.127` 로 곱하면 실제 고지서와 몇 원 차이가 납니다.
그리고 **파이썬의 `round()` 는 4사5입이 아닙니다.** 은행가 반올림이라
`.5` 를 짝수 쪽으로 보냅니다.

```python
round(9588.5)                      # 9588  ← 틀림
from decimal import Decimal, ROUND_HALF_UP
int(Decimal('9588.5').quantize(Decimal('1'), rounding=ROUND_HALF_UP))   # 9589  ← 맞음
```

실제로 한전 요금표의 계산 예시(450kWh, 전기요금 95,885원)에서 부가가치세가
정확히 9,588.5원이라, 이 차이가 그대로 드러납니다. 한전 값은 **9,589원** 입니다.
SQL 에서는 `round()` 가 4사5입이라 그대로 쓰면 됩니다.

## 4. 주택용 복지할인

```sql
select target as 대상, discount_type as 구분,
       percent as "할인율(%)", monthly_cap as "월 한도(원)", summer_cap as "여름철 한도(원)"
from pricing.residential_welfare_discount
where effective_from = '2024-01-01'
order by discount_type, monthly_cap nulls last;
```

여름철은 6월 1일~8월 31일입니다.
기초생활수급자·차상위계층 장애할인은 정률할인(30%)과 **중복 적용**할 수 있습니다.

공동주택에서 계량기 하나를 여러 가구가 쓸 때의 산정 방법(1주택수가구)은
`data/electricity/주택용_복지할인.json` 의 `multi_household_single_meter` 에 있습니다.
가구별 평균사용량으로 누진단계를 적용해 누진 부담을 덜어주는 방식입니다.

## 5. ⚠️ 불완전한 시행일 — 빈 결과를 "요금 없음" 으로 읽지 마세요

종합요금표가 글자 없는 이미지 PDF 라서 **주택용만 확보한 시행일**이 3개 있습니다.

| 시행일 | 수록 종별 |
|---|---|
| 2022-04-01 | 주택용전력만 |
| 2022-10-01 | 주택용전력만 |
| 2023-11-09 | 주택용전력만 |

이 시점에 일반용·산업용을 조회하면 **빈 결과**가 나옵니다.
"그 종별 요금이 0원" 이 아니라 **"아직 데이터를 넣지 못함"** 입니다.
조회 전에 확인하세요.

```sql
select * from pricing.electricity_tariff_coverage;
```

```sql
-- 쓰려는 시점이 불완전한지 먼저 보기
select effective_from, published_label, is_partial, covered_contract_types
from pricing.electricity_tariff_version
where effective_from <= '2022-06-01'
order by effective_from desc limit 1;
```

### 한 요금표가 두 개의 시행일로 쪼개지는 경우

**2026-04-16 요금표**가 그렇습니다. 요금표 주석에 따르면 **산업용(을)만 4월 16일 시행**이고
나머지 15개 종별은 **6월 1일 시행**입니다. 그래서 DB 에는 버전이 둘로 들어가 있습니다.

| 버전 | 담긴 종별 | `is_partial` |
|---|---|---|
| 2026-04-16 | 산업용전력(을) 만 | `true` |
| 2026-06-01 | 16개 종별 전부 | `false` |

이렇게 나누지 않으면 **2026년 5월분을 계산할 때 아직 시행되지 않은 6월 요율이 적용됩니다.**
계산 함수는 "그 종별이 들어 있는 가장 최근 버전"을 고르므로, 5월분 일반용(갑)Ⅰ 은
자동으로 직전 요금표(2025-04-01)로 떨어집니다.

```sql
-- 확인: 5월은 2025-04-01, 7월은 2026-06-01 이 적용돼야 맞습니다
select (pricing.calc_seasonal_bill('일반용전력(갑)Ⅰ','저압',null,100,'2026-05-15',10000)).적용요금표,
       (pricing.calc_seasonal_bill('일반용전력(갑)Ⅰ','저압',null,100,'2026-07-15',10000)).적용요금표;
```

---

## 6. 과거 시점 요금 계산 — ⚠️ 빠진 데이터 주의

요금표와 부가요금 모두 시계열이라 **과거 시점 요금도 계산됩니다.**
같은 건물·같은 사용량으로 연도를 바꿔 보면 인상 폭이 바로 보입니다.

| 청구월 | 적용 요금표 | 전력량요금 | 기후환경 | 연료비조정 | 전기요금 |
|---|---|---:|---:|---:|---:|
| 2021-06 | 2021-01-01 | 4,794,500 | 344,500 | (없음) | — |
| 2023-06 | 2023-05-16 | 7,147,500 | 585,000 | 325,000 | 10,553,500 |
| 2026-10 | 2026-04-16 | 7,147,500 | 585,000 | 325,000 | 10,553,500 |

> ⚠️ **`coalesce(..., 0)` 을 쓰지 마세요.**
> 부가요금은 확보하지 못한 구간이 있습니다(연료비조정단가 2022년 1분기 이전,
> 2024년 2분기 ~ 2025년 3분기, 2026년 2분기). 그 시점을 조회하면 값이 없는데,
> `coalesce` 로 0을 넣으면 **"0원이었다" 와 "모른다" 가 구별되지 않습니다.**
> 위 표의 2021-06 연료비조정이 바로 그 경우입니다. 실제로 2021년 연료비조정단가는
> 0원이 아니었습니다.
>
> 값이 없으면 `null` 이 나오게 두고, 아래처럼 **빠진 항목을 드러내세요.**

```sql
-- 특정 시점의 부가요금. 값이 없으면 '데이터 없음' 으로 표시한다.
with 시점 as (select '2021-06-01'::date as 청구월)
select k.kind as 구분,
       coalesce(x.effective_from::text, '— 데이터 없음 —') as 적용시행일,
       x.won_per_kwh as "원/kWh",
       x.source_type as 출처
from (values ('기후환경요금'),('연료비조정단가')) k(kind)
left join lateral (
  select * from pricing.electricity_surcharge s, 시점 t
  where s.kind = k.kind and s.effective_from <= t.청구월
  order by s.effective_from desc limit 1
) x on true;
```

## 7. 연도별 요금 추이 보기

```sql
select v.effective_from as 시행일, r.energy_charge as "전력량요금(원/kWh)"
from pricing.electricity_rate r
join pricing.electricity_tariff_version v on v.id = r.version_id
where r.contract_type = '일반용전력(을)' and r.voltage = '고압A'
  and r.rate_option = '선택Ⅱ' and r.season = '여름철' and r.time_zone = '최대부하'
order by v.effective_from;
```

농사용처럼 종별 하나만 계속 오른 경우도 이렇게 바로 보입니다.

```sql
select v.effective_from as 시행일, r.energy_charge as "원/kWh"
from pricing.electricity_rate r
join pricing.electricity_tariff_version v on v.id = r.version_id
where r.contract_type = '농사용전력' and r.voltage = '갑'
order by v.effective_from;
```

## 8. 가스요금

```sql
-- 용도별 도매요금 (원/MJ)
select sector as 구분, use_type as 용도, season as 계절, wholesale_price as 도매요금
from pricing.gas_wholesale_price
where effective_from = '2026-09-01' order by sector, use_type;

-- 발전용 천연가스요금 추이
select month as 연월, total_per_nm3 as "원/Nm3", total_per_gj as "원/GJ"
from pricing.gas_power_generation_monthly
where month >= '2020-01-01' order by month;
```

---

## 9. 전기요금 계산 함수 — 긴 쿼리 대신 한 줄로

3절·6절처럼 매번 CTE 를 쓰는 대신, 조건만 넣으면 요금 내역이 나오는 함수를 만들어 뒀습니다.

### 주택용

```sql
-- 450kWh, 저압, 2025년 7월분
select * from pricing.calc_residential_bill(450, '저압', '2025-07-15');
```

| 인수 | 뜻 | 생략하면 |
|---|---|---|
| 1번 | 월 사용량 (kWh) | 필수 |
| 2번 | `'저압'` 또는 `'고압'` | `'저압'` |
| 3번 | 청구월 (그 달 아무 날짜나) | 오늘 |
| 4번 | 가구수 (1주택수가구) | `1` |

청구월을 주면 **그 시점에 유효했던 요금표**를 알아서 고릅니다. 날짜만 바꾸면 과거 요금이 됩니다.
7·8월이면 하계 누진구간(300/450kWh), 그 외에는 기타계절(200/400kWh)이 자동 적용됩니다.

```sql
-- 계량기 하나를 3가구가 함께 쓰는 공동주택, 합계 900kWh
select * from pricing.calc_residential_bill(900, '저압', '2024-01-15', 3);
```

### 계약전력 기반 (일반용·산업용·교육용 등)

```sql
-- 일반용(갑)Ⅱ 고압A 선택Ⅰ, 계약전력 300kW, 2025년 7월분
-- 경부하 10,000 / 중간부하 10,000 / 최대부하 10,000 kWh
select * from pricing.calc_demand_bill(
    '일반용전력(갑)Ⅱ', '고압A', '선택Ⅰ', 300,
    '2025-07-15', 10000, 10000, 10000);
```

계절은 청구월에서 자동으로 정합니다(6~8월 여름철 / 11~2월 겨울철 / 나머지 봄·가을철).
마지막 인수로 `'여름철'` 등을 직접 넘겨 덮어쓸 수도 있습니다.

종별·전압·선택요금 이름은 **DB 에 적힌 글자와 정확히 같아야** 합니다. 목록은 이렇게 봅니다.

```sql
select distinct contract_type, voltage, rate_option
from pricing.electricity_rate_current
where time_zone is not null
order by 1, 2, 3;
```

### 계절별 요금 (일반용(갑)Ⅰ·산업용(갑)Ⅰ·교육용(갑)·심야전력)

```sql
-- 일반용(갑)Ⅰ 저압, 계약전력 100kW, 2026년 7월분 10,000kWh
select * from pricing.calc_seasonal_bill(
    '일반용전력(갑)Ⅰ', '저압', null, 100, '2026-07-15', 10000);

-- 고압은 선택Ⅰ·선택Ⅱ 가 있습니다
select * from pricing.calc_seasonal_bill(
    '일반용전력(갑)Ⅰ', '고압A', '선택Ⅰ', 300, '2026-07-15', 50000);

-- 심야전력은 기본요금이 없어 계약전력을 null 로 둡니다 (축열식 난방)
select * from pricing.calc_seasonal_bill(
    '심야전력(갑)', null, null, null, '2026-01-15', 5000);
```

계절 이름이 종별마다 다릅니다. 비워 두면 청구월을 보고 아래를 차례로 시도합니다.

| 체계 | 쓰는 종별 |
|---|---|
| `여름철` / `봄·가을철` / `겨울철` | 일반용·산업용·교육용 |
| `겨울철` / `기타계절` | 심야전력(갑)·(을)Ⅰ |
| `연중` | 농사용 갑·을저압, 가로등 을 |
| `여름·겨울철` / `봄·가을철` | 제주 주택용 계시별 (`calc_demand_bill`) |

못 찾으면 **그 조합에 실제로 있는 계절 목록을 담아 예외**를 던집니다. 추측해서 계산하지 않습니다.

> 💡 **선택Ⅰ·선택Ⅱ 중 어느 쪽이 유리한지** 바로 비교할 수 있습니다.
> 기본요금이 싼 선택Ⅰ은 사용량이 적을 때, 전력량요금이 싼 선택Ⅱ는 많을 때 유리합니다.
>
> ```sql
> select u.사용량,
>        (pricing.calc_seasonal_bill('일반용전력(갑)Ⅰ','고압A','선택Ⅰ',100,'2026-07-15',u.사용량)).청구금액 as 선택Ⅰ,
>        (pricing.calc_seasonal_bill('일반용전력(갑)Ⅰ','고압A','선택Ⅱ',100,'2026-07-15',u.사용량)).청구금액 as 선택Ⅱ
> from (values (20000::numeric),(26500::numeric),(35000::numeric)) u(사용량);
> ```
>
> 고압A 여름철은 **계약 1kW당 265kWh** 에서 뒤집힙니다 (기본요금 차 1,060원 ÷ 전력량요금 차 4.0원).

### 어느 함수를 쓰면 되나

| 계약종별 | 요금 구조 | 쓸 함수 | 전압/구분 인수 |
|---|---|---|---|
| 주택용전력 | 누진 | `calc_residential_bill` | `'저압'` / `'고압'` |
| 일반용(갑)Ⅰ, 산업용(갑)Ⅰ, 교육용(갑) | 계절별 | `calc_seasonal_bill` | `'저압'`/`'고압A'`/`'고압B'` |
| 심야전력(갑), 심야전력(을)Ⅰ | 계절별 (기본요금 없음) | `calc_seasonal_bill` | `null`, 계약전력도 `null` |
| 농사용전력 | 연중/계절별 | `calc_seasonal_bill` | `'갑'` / `'저압'` / `'고압(A,B)'` |
| 가로등 을(종량등) | 연중 | `calc_seasonal_bill` | `'을(종량등)'` |
| 일반용(갑)Ⅱ, 일반용(을), 산업용(갑)Ⅱ, 산업용(을), 교육용(을) | 계절×시간대 | `calc_demand_bill` | `'고압A'`/`'고압B'`/`'고압C'` |
| 주택용 계시별 (제주) | 계절×시간대 | `calc_demand_bill` | `null` |
| 가로등 갑(정액등), 심야전력(을)Ⅱ | — | **아직 없음** (아래) |  |

> ⚠️ **농사용전력의 `갑`/`을` 구분**은 `voltage` 칸에 섞여 들어가 있습니다.
> `'갑'` = 농사용 갑, `'저압'`·`'고압(A,B)'` = 농사용 을 입니다.
> 원본 JSON 은 `class`(갑/을)와 `voltage`(저압/고압)를 따로 두는데, DB 적재 때
> 한 칸으로 합쳐지기 때문입니다. 값 자체는 정확하지만 이름이 헷갈릴 수 있습니다.

**아직 함수가 없는 종별 2개.** 요율은 DB 에 다 있으니 직접 조회해서 쓰시면 됩니다.

- **가로등 갑(정액등)** — 전력량요금이 없고 W당 47.2원 정액입니다 (월 최저요금 1,220원).
  계약전력 개념이 달라 다른 종별과 같은 식으로 계산되지 않습니다.
  `calc_seasonal_bill` 에 넣으면 "전력량요금 단가가 없습니다 (정액 종별)" 예외가 납니다.
- **심야전력(을)Ⅱ** — 기본요금이 숫자가 아니라 **산식**입니다.
  `7,160원 × (기타시간 사용전력량 ÷ 월간 총 사용전력량)` 이고, 월 최저요금은 kW당 710원입니다.
  시간대(심야/기타)마다 계절 구분도 달라(심야=겨울철/기타계절, 기타=연중) 별도 함수가 필요합니다.
  산식과 단가는 `basic_charge_formula` 와 요율 행에 그대로 들어 있습니다.

엉뚱한 함수에 넣으면 **조용히 틀린 값이 나오는 대신 예외가 납니다.** 예를 들어 계절별 종별을
`calc_demand_bill` 에 넣으면 "시간대 요율이 3개가 아니라 0개" 라고 멈춥니다.

### 결과에서 꼭 볼 것: `주의` 칸

마지막 `주의` 칸이 비어 있지 않으면 **그 금액을 그대로 쓰면 안 됩니다.** 들어올 수 있는 말:

| 주의 내용 | 뜻 |
|---|---|
| 전력산업기반기금율이 없어 기금을 0원으로 뒀다 | 2021-01-01 요금표에 기금율이 안 적혀 있습니다. 청구금액이 실제보다 적습니다 |
| 기후환경요금 / 연료비조정단가를 찾지 못해 0 으로 계산했다 | 그 시점 단가가 DB 에 없습니다 |
| 주택용만 수록된 불완전 버전이다 | 5절 참고 |
| 가구당 1,000kWh 초과 + 하계/동계 | 슈퍼유저요금 구간인데 함수가 반영하지 않습니다 |
| 역률요금·수요관리 할인 등 부가 정산은 포함하지 않는다 | 계약전력 기반에는 항상 붙습니다 |
| 이 종별은 기본요금 단가가 없다 | 심야전력(갑)·(을)Ⅰ 입니다. 정상입니다 |

### 반영되지 않는 것

함수가 계산하는 범위는 **기본요금 + 전력량요금 + 기후환경요금 + 연료비조정요금 + 부가가치세 + 전력산업기반기금** 까지입니다.
다음은 들어 있지 않으니 따로 더하거나 빼야 합니다.

- 주택용 복지할인 (4절)
- 슈퍼유저요금
- 역률요금, 수요관리 할인, 선택요금 변경 제약
- 계약전력 초과 사용에 따른 위약금

### 이 함수를 믿을 수 있는 근거

주택용은 한전이 2024-01-01 요금표에 **직접 인쇄해 둔 계산 예시** 두 건과 전 항목이 1원 단위로 맞습니다.

| 항목 | 450kWh 1가구 | 900kWh 3가구 |
|---|---|---|
| 기본요금 | 7,300 | 4,800 |
| 전력량요금 | 82,285 | 136,380 |
| 기후환경요금 | 4,050 | 8,100 |
| 연료비조정요금 | 2,250 | 4,500 |
| 전기요금계 | 95,885 | 153,780 |
| 부가가치세 | 9,589 | 15,378 |
| 전력산업기반기금 | 3,540 | 5,680 |
| **청구금액** | **109,010** | **174,830** |

계절별 요금은 한전이 인쇄한 계산 예시가 없어 다르게 검증했습니다. **선택Ⅰ·선택Ⅱ 손익분기점**이
요금표 숫자에서 대수적으로 유도한 값(265kWh/kW)과 정확히 맞고, 기울기도 전력량요금 차이와
일치합니다. 손계산과도 1원 단위로 맞습니다.

요금표를 새로 넣은 뒤에는 `supabase/tests/verify_bill_functions.sql` 을 SQL Editor 에 붙여넣고
판정 칸이 모두 `일치` 인지 확인하세요.

---

## 10. 도시가스 요금 — 월별 시계열 (2016~2026)

도시가스 요금표(공시용 엑셀) 93개에서 뽑은 **월별** 자료입니다. 연료전지 경제성분석의 연료비가 여기 있습니다.

| 표 | 내용 | 행수 |
|---|---|---:|
| `citygas_wholesale_monthly` | 도매요금 (전국 단일) | 2,499 |
| `citygas_retail_monthly` | 소매요금 (시·도별) | 67,181 |
| `citygas_retail_region` | 지역별 공급회사·기본요금 | 2,889 |

```sql
-- 연료전지용 도매요금 추이 (2019-05 신설 이후 80개 시점)
select effective_from, won_per_mj
from citygas_wholesale_monthly
where use_category = '연료전지용'
order by effective_from;

-- 서울의 업무난방용 소매요금 추이
select effective_from, won_per_mj
from citygas_retail_monthly
where region = '서울특별시' and use_category = '업무난방용'
order by effective_from;

-- 특정 시점, 지역별 연료전지용 소매요금 비교
select region, won_per_mj
from citygas_retail_monthly
where effective_from = '2026-11-01' and use_category = '연료전지용'
order by won_per_mj;
```

단위는 **원/MJ, 부가세 별도**입니다.

### 도매와 소매를 혼동하지 마세요

```
가스공사 도매요금  →  (+ 도시가스사 공급비용, 시·도지사 승인)  →  소매요금
   전국 단일                                                    지역마다 다름
```

경제성분석에서 **실제 연료비로 쓰는 것은 소매요금**입니다. 도매요금은 전국 기준값입니다.

### ⚠️ 2026-11-01 도매요금 주의

그 시점 행에는 `note` 가 붙어 있습니다. 원본 엑셀의 도매요금란이 10월 값 그대로여서
11월 인상이 반영돼 있지 않습니다. **그 시점의 도매요금은 `gas_wholesale_price`**(한국가스공사
공시, 연료전지용 25.0573원/MJ)**를 쓰세요.**

```sql
-- note 가 붙은 행은 그대로 쓰면 안 됩니다
select effective_from, use_category, won_per_mj, note
from citygas_wholesale_monthly where note is not null;
```

### 용도 구분

`use_category` 는 **대분류 11종**입니다: 주택용, 업무난방용, 일반용1·2, 냉난방공조용,
산업용, 열병합1(소형열병합·CES)·열병합2(집단에너지), 열전용설비용, 수송용, **연료전지용**.

여기에 `use_detail` 이 붙어 실제 요율 칸이 됩니다 — 계절이 나뉘는 용도는 동절기/하절기/기타월,
주택용은 취사용·주택난방·중앙난방·취사전용(+소매는 기본요금), 열전용설비용은 열전용(1)·(2)·(3).
**조합은 도매 28종, 소매 29종**입니다. 집계할 때 `use_category` 만으로 묶으면 계절·세부용도가
섞이므로 `(use_category, use_detail)` 로 묶으세요.

연료전지용은 **2019-05-01 신설**이라 그 이전 시점에는 없습니다.

👉 연료전지 경제성분석에 바로 쓰는 쿼리는 **§11** 에 따로 모았습니다. 2020-07-01 복원 내역도 거기 있습니다.

---

## 11. 연료전지용 가스요금 — 경제성분석에 바로 쓰기

연료전지(PAFC·PEMFC·SOFC) 경제성분석의 연료비는 **연료전지용 소매요금**입니다.
2019-05-01 신설이라 그 이전 시점은 없고, 지역별로 93개 시행일 중 최대 80개가 들어 있습니다.

### 2020-07-01 은 복원된 값입니다

원본 공시 엑셀(`200701 요금표(도매인하)_소매반영_공시.xlsx`)의 연료전지용 열에는
**총 요율이 아니라 지역 공급비용만** 인쇄돼 있었습니다(요금표(MJ) 시트 4행=도매 9.8664,
5행 서울=0.7599). 그대로 두면 31개 지역 값이 0.35~0.78원/MJ, 실제 요율의 1/14 수준이 됩니다.

**지금은 `총요율 = 도매 9.8664 + 인쇄값` 으로 복원해 두었습니다** (10.2182~10.6475원/MJ).
비교 가능한 27개 지역 중 26개가 2020-08-01 공급비용과 정확히 일치해 복원 방법을 확인했습니다
(경기도만 그 사이 공급비용이 0.6584 → 0.7291 로 바뀌어 다릅니다).

**그래서 집계할 때 걸러낼 필요가 없습니다.** 그냥 쓰세요.

- 복원된 31행에는 `note` 가 붙어 있습니다 — 값을 빼라는 표시가 아니라 **출처 설명**입니다.
- 원래 인쇄값은 JSON 원본(`data/gas/citygas_소매요금_2020.json`)의 `source_won_per_mj`
  필드와 `meta.corrections` 에 보존돼 있습니다.

```sql
-- 건전성 점검: 소매가 도매보다 낮은 행은 정상이면 있을 수 없다
select r.effective_from, r.region, r.won_per_mj as 소매, w.won_per_mj as 도매
from citygas_retail_monthly r
join citygas_wholesale_monthly w
  on w.effective_from = r.effective_from
 and w.use_category = r.use_category and w.use_detail = r.use_detail
where r.won_per_mj < w.won_per_mj;
-- → 복원 후에는 0건입니다. 1건이라도 나오면 적재가 잘못된 것입니다.
```

### 지금 적용되는 지역별 요금

```sql
with latest as (
  select region, max(effective_from) as d
  from citygas_retail_monthly
  where use_category = '연료전지용' and effective_from <= current_date
  group by region)
select r.region, r.effective_from, r.won_per_mj
from citygas_retail_monthly r
join latest l on l.region = r.region and l.d = r.effective_from
where r.use_category = '연료전지용'
order by r.won_per_mj;
```

2026-11-01 기준 육지는 **24.84 ~ 25.61원/MJ** 로 좁습니다
(가장 싼 곳 광주시 24.8402, 가장 비싼 곳 서울특별시 25.6106, 차이 0.77원/MJ).

**제주는 30.9646원/MJ 로 육지보다 5~6원/MJ 비쌉니다.** 전국 평균을 쓰면 제주 사업은
연료비를 20% 넘게 과소평가하게 됩니다. 사업지가 정해졌으면 반드시 **그 지역 값**을 쓰세요.
제주는 2025-12-01 신설이라 그 이전 시점이 없습니다(12개 시행일).

> ⚠️ 2026-11-01 시점은 §10 의 도매요금 주의사항이 함께 걸립니다. 원본 엑셀의 도매란이
> 10월 값 그대로여서, **2026-10-01 과 2026-11-01 소매요금이 완전히 같습니다**
> (서울 둘 다 25.6106). 11월 도매 인상이 반영돼 있지 않다는 뜻이므로, 10월 값으로
> 바꿔도 소용없고 `gas_wholesale_price`(연료전지용 25.0573원/MJ)로 도매분을 보정해야 합니다.

### 연도별 추이

```sql
select to_char(effective_from,'YYYY') as 연도,
       count(*) as 시행일수,
       round(avg(won_per_mj),2) as 연평균,
       round(min(won_per_mj),2) as 최저,
       round(max(won_per_mj),2) as 최고
from citygas_retail_monthly
where region = '서울특별시' and use_category = '연료전지용'
group by 1 order by 1;
```

서울 기준 연평균(원/MJ): 2019 12.78 → 2020 9.71 → 2021 13.26 → **2022 24.82** →
2023 21.07 → 2024 19.56 → 2025 16.92 → 2026 20.06.
2022년 급등(러시아-우크라이나 전쟁 LNG 가격 급등)이 뚜렷하니, **LCOE 를 계산할 때
한 시점 단가로 전 기간을 깔지 마세요.** 기간 평균이나 시나리오를 쓰는 편이 안전합니다.

### 공급비용(지역 마진)만 뽑기

도매는 전국 단일이므로, 소매 − 도매 = 그 지역 도시가스사의 공급비용입니다.

```sql
select r.region, r.effective_from,
       round(r.won_per_mj - w.won_per_mj, 4) as 공급비용
from citygas_retail_monthly r
join citygas_wholesale_monthly w
  on w.effective_from = r.effective_from
 and w.use_category = r.use_category and w.use_detail = r.use_detail
where r.use_category = '연료전지용'
  and r.effective_from = '2026-10-01'
order by 공급비용;
```

### 연료전지 연료비 단가로 변환

요금은 **원/MJ, 부가세 별도**입니다. 발전효율로 나누면 발전량 기준 연료비가 나옵니다.

```sql
-- 예: 서울, SOFC 발전효율 50% 가정 → 원/kWh(발전량)
select effective_from,
       won_per_mj                                as 원_per_MJ,
       round(won_per_mj * 3.6, 2)                as 원_per_kWh_입력,
       round(won_per_mj * 3.6 / 0.50, 2)         as 원_per_kWh_발전
from citygas_retail_monthly
where region = '서울특별시' and use_category = '연료전지용'
order by effective_from desc limit 12;
```

1 kWh = 3.6 MJ 입니다. 서울·2026-11-01 기준으로 입력열 **92.20원/kWh**,
발전효율 50% 가정 시 발전량 기준 **184.40원/kWh** (부가세 별도)가 나옵니다.
부가세 10% 와 열회수분 공제는 별도로 반영하세요.

---

## 다른 앱에서 REST API 로 읽으려면

👉 **자세한 방법은 [HOW-TO-USE-API.md](HOW-TO-USE-API.md) 에 따로 정리했습니다.**
Vercel 배포, 환경변수, 함수 호출, 자주 나는 오류까지 들어 있습니다.

요약하면, `pricing` 스키마는 기본적으로 API 에 공개돼 있지 않습니다.
Supabase 대시보드 → Project Settings → API → **Exposed schemas** 에 `pricing` 을 추가하세요.
권한(`grant`)은 `supabase/migrations/0008_rest_api_grants.sql` 로 이미 열어 두었습니다.

```js
const { data } = await supabase
  .schema('pricing')
  .from('electricity_rate_current')
  .select('*')
  .eq('contract_type', '일반용전력(을)')
```

읽기는 누구나, 쓰기는 `service_role` 만 가능합니다.
`service_role` 키는 **브라우저에 노출하면 안 됩니다** (서버·빌드 환경변수로만 사용).
