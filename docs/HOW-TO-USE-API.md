# 다른 앱에서 이 단가 데이터를 불러 쓰는 방법

Vercel 에 올린 웹앱이나 엑셀, 혹은 그냥 브라우저에서 이 DB 를 읽는 방법입니다.

```
Supabase (pricing 스키마)  →  REST API  →  내 앱 (Vercel 등)
```

---

## 0단계. 준비 — 할 게 없습니다

대시보드 설정은 **필요 없습니다.** 단가 자료는 `pricing` 스키마에 있지만,
Supabase 가 기본으로 공개하는 `public` 스키마에 **바라보기용 뷰**를 두었기 때문입니다.

```
public.renewable_equipment_price  →  (창문)  →  pricing.renewable_equipment_price
```

사본이 아니라 창문이라서, 단가를 고치면 양쪽에 동시에 반영됩니다.
권한과 뷰는 `supabase/migrations/0008`·`0009` 에 들어 있고 이미 적용돼 있습니다.

> 왜 이렇게 했나요? REST API 는 요청에 스키마 지정 헤더가 없으면 `public` 에서 찾습니다.
> 브라우저 주소창이나 엑셀처럼 헤더를 붙일 수 없는 곳에서는 `pricing` 을 공개해 두어도
> `Could not find the table 'public.…'` 오류가 납니다. 창문을 두면 그 문제가 사라집니다.

---

## 1단계. 접속 정보

| 항목 | 값 |
|---|---|
| URL | `https://qhnyrkbmkzhsgthcxoiw.supabase.co` |
| 공개 키 (publishable) | `sb_publishable_dfdUxuMV1p-Zlst2p37eDQ_moJEDgtl` |

**공개 키는 브라우저에 노출돼도 괜찮습니다.** 읽기 전용이고 RLS 가 막아줍니다.

> 🚨 **`service_role` 키는 절대 브라우저나 깃허브에 넣지 마세요.**
> 그 키는 RLS 를 통째로 무시합니다. 서버 환경변수로만 쓰고, 이 레포에는 넣지 않습니다.

---

## 2단계. 제일 빠른 확인 — 브라우저 주소창

아래 주소를 브라우저에 붙여넣으세요. JSON 이 나오면 성공입니다.

```
https://qhnyrkbmkzhsgthcxoiw.supabase.co/rest/v1/renewable_equipment_price?select=*&apikey=sb_publishable_dfdUxuMV1p-Zlst2p37eDQ_moJEDgtl
```

전기요금 계산도 주소창으로 됩니다.

```
https://qhnyrkbmkzhsgthcxoiw.supabase.co/rest/v1/rpc/calc_residential_bill?usage_kwh=450&voltage=저압&billing_month=2025-07-15&apikey=sb_publishable_dfdUxuMV1p-Zlst2p37eDQ_moJEDgtl
```

---

## 3단계. Next.js (Vercel) 에서 쓰기

### 설치

```bash
npm install @supabase/supabase-js
```

### 환경변수

프로젝트 루트에 `.env.local` 을 만듭니다. (Vercel 에는 프로젝트 Settings → Environment Variables 에 같은 두 줄을 넣습니다)

```
NEXT_PUBLIC_SUPABASE_URL=https://qhnyrkbmkzhsgthcxoiw.supabase.co
NEXT_PUBLIC_SUPABASE_KEY=sb_publishable_dfdUxuMV1p-Zlst2p37eDQ_moJEDgtl
```

### 연결 파일

`lib/pricing.ts` 를 만듭니다.

```ts
import { createClient } from '@supabase/supabase-js'

export const db = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_KEY!,
)
```

> `.schema('pricing')` 같은 건 필요 없습니다. 창문 뷰가 `public` 에 있어서 그냥 읽힙니다.

### 장비 단가 불러오기

```ts
const { data, error } = await db
  .from('renewable_equipment_price')
  .select('category, subcategory, name, unit_price, price_unit')
  .order('category')

// [{ category: '태양광', subcategory: '일반', name: '태양광 발전설비',
//    unit_price: 2200000, price_unit: '원/kW' }, ...]
```

### 전기요금 절감 단가(회피단가) 불러오기

```ts
const { data } = await db
  .from('misc_price')
  .select('unit_price, price_unit')
  .eq('slug', 'electricity-avoided-cost')
  .single()

// { unit_price: 173, price_unit: '원/kWh' }
```

### 전기요금 계산하기 (함수 호출)

표를 읽어다 직접 계산하지 마세요. 누진구간·반올림 규칙이 까다롭습니다.
**함수를 호출하면 한전 요금표대로 계산된 내역이 통째로 옵니다.**

```ts
// 주택용 450kWh, 저압, 2025년 7월분
const { data, error } = await db.rpc('calc_residential_bill', {
  usage_kwh: 450,
  voltage: '저압',
  billing_month: '2025-07-15',
  household_count: 1,
})

const bill = data[0]   // ⚠️ 결과는 '행이 하나인 배열' 입니다

// bill = {
//   적용요금표: '2025년 4월 1일 시행',
//   계절: '하계',
//   기본요금: 1600, 전력량요금: 68190,
//   기후환경요금: 4050, 연료비조정요금: 2250,
//   전기요금: 76090, 부가가치세: 7609, 전력산업기반기금: 2430,
//   청구금액: 86120,
//   주의: null
// }
```

```ts
// 일반용(갑)Ⅰ 저압, 계약 100kW, 10,000kWh
const { data } = await db.rpc('calc_seasonal_bill', {
  contract_type: '일반용전력(갑)Ⅰ',
  voltage: '저압',
  rate_option: null,
  contract_kw: 100,
  billing_month: '2026-07-15',
  usage_kwh: 10000,
})
```

```ts
// 일반용(갑)Ⅱ 고압A 선택Ⅰ, 계약 300kW, 시간대별 사용량
const { data } = await db.rpc('calc_demand_bill', {
  contract_type: '일반용전력(갑)Ⅱ',
  voltage: '고압A',
  rate_option: '선택Ⅰ',
  contract_kw: 300,
  billing_month: '2025-07-15',
  off_peak_kwh: 10000,
  mid_peak_kwh: 10000,
  on_peak_kwh: 10000,
})
```

### ⚠️ 결과의 `주의` 칸을 꼭 보세요

`주의` 가 비어 있지 않으면 **그 금액을 그대로 쓰면 안 됩니다.** 자세한 뜻은
[HOW-TO-QUERY.md 9절](HOW-TO-QUERY.md)에 있습니다.

```ts
if (bill.주의) {
  console.warn('이 계산에는 단서가 있습니다:', bill.주의)
}
```

---

## 4단계. 서버에서만 쓰고 싶다면

단가를 외부에 안 보이게 하려면 브라우저가 아니라 서버에서 부르면 됩니다.
Next.js 에서는 `app/api/.../route.ts` 나 서버 컴포넌트에서 같은 코드를 쓰면 됩니다.
그때는 환경변수 이름에서 `NEXT_PUBLIC_` 을 빼세요. 그래야 브라우저 번들에 안 들어갑니다.

```
SUPABASE_URL=https://qhnyrkbmkzhsgthcxoiw.supabase.co
SUPABASE_KEY=sb_publishable_dfdUxuMV1p-Zlst2p37eDQ_moJEDgtl
```

---

## 어떤 표와 함수를 쓸 수 있나

| 이름 | 종류 | 내용 |
|---|---|---|
| `renewable_equipment_price` | 표 | 신재생 장비 단가 (태양광·BIPV·지열·연료전지·ESS) |
| `misc_price` | 표 | 기타 단가 (전기요금 회피단가 등) |
| `electricity_rate_current` | 뷰 | 지금 적용되는 전기 요율 |
| `electricity_surcharge_current` | 뷰 | 지금 적용되는 기후환경요금·연료비조정단가 |
| `electricity_tariff_coverage` | 뷰 | 시행일별로 어떤 종별이 수록돼 있는지 |
| `electricity_rate` | 표 | 전기 요율 전체 (시행일별) |
| `electricity_tariff_version` | 표 | 요금표 버전 (시행일·세율) |
| `electricity_surcharge` | 표 | 기후환경요금·연료비조정단가 시계열 |
| `residential_welfare_discount` | 표 | 주택용 복지할인 |
| `gas_wholesale_price` | 표 | 가스 도매요금 |
| `gas_power_generation_monthly` | 표 | 발전용 천연가스요금 월별 |
| `calc_residential_bill` | 함수 | 주택용 전기요금 |
| `calc_seasonal_bill` | 함수 | 계절별 요금 (일반용(갑)Ⅰ·심야전력·농사용 등) |
| `calc_demand_bill` | 함수 | 계절×시간대 요금 (일반용(갑)Ⅱ·(을) 등) |

---

## 자주 나는 오류

| 메시지 | 뜻 | 해결 |
|---|---|---|
| `Could not find the table 'public.…' in the schema cache` | 창문 뷰가 없거나 캐시가 안 바뀌었습니다 | `supabase/migrations/0009_public_api_views.sql` 을 SQL Editor 에서 실행 |
| `permission denied for schema pricing` | 권한이 없습니다 | `supabase/migrations/0008_rest_api_grants.sql` 을 SQL Editor 에서 실행 |

| `Could not find the function ... in the schema cache` | 함수 이름·인수 이름이 틀렸습니다 | 위 예시의 인수 이름을 그대로 쓰세요 |
| `No API key found in request` | `apikey` 가 빠졌습니다 | 환경변수 확인 |
| 결과가 빈 배열 `[]` | 권한은 있는데 보이는 행이 없습니다 | RLS 정책 확인, 또는 조건이 너무 좁은지 확인 |

---

## 쓰기는 막아 두었습니다

이 API 로는 **읽기만** 됩니다. 단가를 고치는 일은 레포의 JSON 을 고치고
`scripts/export_sql.py` 로 SQL 을 만들어 적재하는 경로로만 합니다
([HOW-TO-UPDATE.md](HOW-TO-UPDATE.md) 참고).

그래야 Git 이력이 곧 단가 개정 이력이 되고, 체크섬으로 대조할 수 있습니다.
앱에서 직접 고치게 하면 그 추적이 끊깁니다.
