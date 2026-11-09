#!/usr/bin/env python3
"""레포의 마이그레이션 파일과 Supabase 에 배포된 계산 함수가 같은지 대조한다.

왜 필요한가
    0006 은 마이그레이션 도구가 아니라 SQL Editor 로 직접 적용했다.
    그래서 "레포 파일을 고쳤지만 DB 에는 안 올렸다" 또는 그 반대가 생길 수 있다.
    함수 본문을 주석·공백을 걷어내고 md5 로 비교하면 그걸 잡을 수 있다.

사용법
    python3 scripts/verify_functions_match.py          # 레포 쪽 해시
    python3 scripts/verify_functions_match.py --sql    # DB 쪽 해시를 구하는 SQL

    두 결과의 해시가 같으면 레포와 DB 의 함수 논리가 같다.
    다르면 0006 파일을 SQL Editor 에 다시 붙여넣어 Run 하면 맞춰진다.
    (create or replace 뿐이라 여러 번 실행해도 안전하다)
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

DB_SQL = """\
-- Supabase 대시보드 > SQL Editor 에서 실행하세요.
with d as (
  select p.proname, pg_get_functiondef(p.oid) as def
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'pricing'
    and p.proname like 'calc\\_%'
),
body as (
  -- 'declare' 부터 마지막 'end' 까지만 떼어내고 -- 주석을 지운다
  select proname,
         regexp_replace(
           substring(def from position('declare' in def)
                          for  position('end $function$' in def)
                             - position('declare' in def) + 3),
           '--[^\\n]*', '', 'g') as raw
  from d
)
select proname as 함수,
       md5(btrim(regexp_replace(raw, '\\s+', ' ', 'g'))) as 정규화_md5,
       length(btrim(regexp_replace(raw, '\\s+', ' ', 'g'))) as 글자수
from body order by proname;
"""


def normalize(body: str) -> str:
    """-- 주석을 지우고 공백을 하나로 모은다. DB 쪽 SQL 과 같은 처리여야 한다."""
    body = re.sub(r"--[^\n]*", "", body)
    return re.sub(r"\s+", " ", body).strip()


def repo_hashes() -> dict[str, tuple[str, int, str]]:
    """마이그레이션 파일들에서 calc_* 함수 본문을 찾아 해시한다.

    같은 함수가 여러 파일에 있으면 (0005 → 0006 처럼) 나중 파일이 이긴다.
    실제 DB 에 남는 것도 마지막에 실행된 정의이기 때문이다.
    """
    result: dict[str, tuple[str, int, str]] = {}
    for path in MIGRATIONS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"function pricing\.(calc_\w+)\(", text):
            name = match.group(1)
            try:
                declare = text.index("declare", match.end())
                end = text.index("end $$;", declare)
            except ValueError:
                continue
            body = normalize(text[declare:end] + "end")
            result[name] = (hashlib.md5(body.encode()).hexdigest(), len(body), path.name)
    return dict(sorted(result.items()))


def main() -> None:
    if "--sql" in sys.argv:
        print(DB_SQL)
        return
    print("레포의 마이그레이션 파일에서 읽은 계산 함수\n")
    for name, (digest, size, src) in repo_hashes().items():
        print(f"  {name:24s} {digest}  ({size}자)  ← {src}")
    print("\n이 해시를 DB 쪽 값과 비교하세요:")
    print("  python3 scripts/verify_functions_match.py --sql")


if __name__ == "__main__":
    main()
