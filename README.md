# energinno-DB

ENERGINNO 에너지 경제성 평가용 **기초 데이터 저장소**입니다.
VE·LCC 검토, ZEB 사업성 분석 등에 반복적으로 쓰이는 공공요금·단가와 법규 원문을 모아 두고,
단가는 다른 앱에서 바로 불러 쓸 수 있게 DB 로도 올려 둡니다.

## 어떻게 굴러가나요

```
원본 자료(PDF·CSV)  →  JSON 데이터  →  Supabase(DB)  →  다른 앱에서 조회
  단가정보/            data/           supabase/        제안서·경제성분석 등
```

- **`data/` 안의 JSON이 원본(정답)** 입니다. 값이 바뀌면 여기부터 고칩니다.
- Git에 기록이 남으므로 **"언제 누가 어떤 단가를 왜 바꿨는지"가 그대로 요금 개정 이력**이 됩니다.
- Supabase는 다른 앱이 가져다 쓰기 편하라고 두는 **사본**입니다.

## 폴더 설명

| 폴더 | 내용 |
|---|---|
| `단가정보/` | 근거가 되는 **원문 자료** (전기요금표 PDF, 가스요금 CSV) |
| `법규기준/` | 법령·고시·규정 **원문** (데이터센터 전력설비 기준, KEC, 한전 계통연결 규정) |
| `data/` | 단가 데이터 (JSON) — **여기가 원본** |
| `docs/` | 사용법·데이터 구조 설명서 |
| `scripts/` | 변환·검증·SQL 생성 도구 |
| `supabase/` | DB 테이블·계산함수 정의(`migrations/`), 적재용 SQL(`seed/`), 검증 SQL(`tests/`) |

원문 자료의 보유 현황은 각 폴더의 README 에 정리돼 있습니다.

- [`단가정보/README.md`](단가정보/README.md) — 시행일별 요금표 보유 현황
- [`법규기준/README.md`](법규기준/README.md) — 법령별 원문 목록과 활용 포인트

## 파일명 규칙

원문 자료는 `시행일(YYYY-MM-DD)_자료명.확장자` 형식입니다.
시행일 순으로 정렬되므로 평가 기준일에 해당하는 자료를 바로 찾을 수 있습니다.

```
단가정보/전기요금/종합/2024-01-01_전기요금표_종합.pdf
단가정보/가스요금/2026-09-01_한국가스공사_천연가스요금정보.csv
```

## 지금 들어있는 데이터

| 항목 | 범위 | 상태 |
|---|---|---|
| 전기요금 (한전) | **14개 시행일 전부** (2021-01-01 ~ 2026-04-16). 9개는 전 종별, 5개는 주택용만 | ✅ 6개는 숫자 전량 대조, 8개는 한전 계산 예시로 검산 |
| 가스 도매요금 (가스공사) | 2026-09-01 기준 용도별 11건 | ✅ 원본 CSV 전량 변환 |
| 발전용 천연가스요금 | 2008-01 ~ 2022-12 월별 180건 | ✅ 원본 CSV 전량 변환 |
| 신재생에너지 장비 단가 | 태양광·BIPV·지열·연료전지(PAFC/PEMFC/SOFC)·ESS | ✅ 7개 (사용자 제공) |
| 기타 단가 | 전기요금 절감 단가(회피단가) | ✅ 1개 (사용자 제공) |

위 데이터는 Supabase 프로젝트 **`jlaw80_DB`** (`qhnyrkbmkzhsgthcxoiw`, 도쿄 리전) 의
`pricing` 스키마에 그대로 올라가 있습니다. JSON 원본과 DB 내용이 한 칸도 다르지 않다는 것을
체크섬으로 확인했습니다 (`scripts/checksum.py`).

| 테이블 | 행수 |
|---|---:|
| `pricing.electricity_rate` | 3,075 (요금표 15개 버전) |
| `pricing.gas_power_generation_monthly` | 180 |
| `pricing.gas_wholesale_price` | 11 |
| `pricing.electricity_surcharge` | 13 (기후환경요금·연료비조정단가) |
| `pricing.residential_welfare_discount` | 9 (주택용 복지할인) |
| `pricing.renewable_equipment_price` | 7 (신재생 장비 단가) |
| `pricing.misc_price` | 1 (기타 단가) |

전기요금표 중 **4부(2022-04-01, 2022-07-01, 2023-01-01, 2023-11-09)는 글자가 없는 이미지 PDF**라
비주택용 종별은 사람이 옮겨 적어야 합니다. 현황은
`python3 scripts/read_kepco_tables.py --survey` 또는
[docs/HOW-TO-UPDATE.md](docs/HOW-TO-UPDATE.md) 의 체크리스트를 보세요.

## 자주 쓰는 명령

```bash
python3 scripts/validate.py              # 데이터 형식 점검 (고친 뒤 꼭 실행)
python3 scripts/verify_electricity.py    # 전기요금 숫자를 원본 PDF와 대조
python3 scripts/export_sql.py            # Supabase 에 넣을 SQL 다시 만들기
python3 scripts/convert_gas_csv.py       # 가스 CSV → JSON 다시 변환
python3 scripts/checksum.py              # DB 와 대조할 기대 체크섬 출력
python3 scripts/checksum.py --sql        # DB 에서 돌릴 대조 SQL 출력
python3 scripts/verify_functions_match.py # 레포와 DB 의 계산 함수가 같은지 대조
python3 scripts/read_kepco_tables.py --survey   # 요금표 PDF 현황과 추출 가능 여부
```

## 자료를 추가할 때

1. `단가정보/` 의 성격에 맞는 하위 폴더에 원문 파일을 넣고 파일명 규칙을 맞춥니다.
2. `단가정보/README.md` 의 보유 현황을 갱신합니다.
3. `data/` 의 JSON 에 값을 옮기고 `meta.source_file` 에 원문 경로를 적습니다.
4. [docs/HOW-TO-UPDATE.md](docs/HOW-TO-UPDATE.md) 의 절차를 따라 검증·적재합니다.

## API 키 관리

API 키는 **절대 이 저장소에 커밋하지 않습니다.**
`.env.example` 을 복사해 `.env` 를 만들고 거기에만 넣으세요. `.env` 는 `.gitignore` 에 등록돼 있습니다.

```bash
cp .env.example .env
```

## 더 읽을 것

- [docs/HOW-TO-USE-API.md](docs/HOW-TO-USE-API.md) — **다른 앱(Vercel 등)에서 불러 쓰는 방법**
- [docs/HOW-TO-QUERY.md](docs/HOW-TO-QUERY.md) — **단가를 꺼내 쓰는 방법**
  - 전기요금은 함수 한 줄로 계산됩니다: `select * from calc_residential_bill(450, '저압', '2025-07-15');`
  - 한전이 요금표에 인쇄해 둔 계산 예시와 전 항목 1원 단위로 대조해 검증했습니다.
- [docs/DATA-MODEL.md](docs/DATA-MODEL.md) — 각 단가를 어떤 항목으로 저장하는지
- [docs/HOW-TO-UPDATE.md](docs/HOW-TO-UPDATE.md) — 요금이 바뀌었을 때 갱신하는 방법
