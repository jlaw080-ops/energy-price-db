#!/usr/bin/env python3
"""공공데이터포털(api.odcloud.kr) 에서 한국가스공사 요금 데이터를 받아온다.

주의
----
이 스크립트는 아직 실제 호출로 검증되지 않았습니다.
작성 시점의 개발 환경에서 api.odcloud.kr 접속이 차단되어 있었기 때문입니다.
처음 실행할 때는 --dry-run 으로 요청 주소부터 확인하세요.

사전 준비
---------
1) .env 에 ODCLOUD_SERVICE_KEY_ENC 를 채운다.
2) data.go.kr 에서 각 데이터의 [오픈API] 탭을 열어 '요청주소'를 확인하고
   .env 의 KOGAS_POWER_GEN_PATH / KOGAS_WHOLESALE_PATH 에 넣는다.
   요청주소가 https://api.odcloud.kr/api/15129722/v1/uddi:abcd-1234 라면
   넣을 값은 15129722/v1/uddi:abcd-1234 이다.

사용법
------
    python3 scripts/fetch_odcloud.py --dry-run      # 요청 주소만 출력
    python3 scripts/fetch_odcloud.py                # 실제 호출 후 저장
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "_raw"
BASE = "https://api.odcloud.kr/api"
PER_PAGE = 1000

DATASETS = {
    "kogas_power_generation": {
        "path_env": "KOGAS_POWER_GEN_PATH",
        "title": "한국가스공사 발전용 천연가스요금",
    },
    "kogas_wholesale": {
        "path_env": "KOGAS_WHOLESALE_PATH",
        "title": "한국가스공사 천연가스요금정보",
    },
}


def load_env() -> dict[str, str]:
    """.env 를 읽어 딕셔너리로 반환 (외부 라이브러리 없이)."""
    env = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip())
    return env


def build_url(path: str, key_enc: str, page: int) -> str:
    # 인증키는 이미 URL 인코딩된 상태이므로 다시 인코딩하지 않는다.
    return f"{BASE}/{path}?page={page}&perPage={PER_PAGE}&serviceKey={key_enc}"


def fetch_all(path: str, key_enc: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        url = build_url(path, key_enc, page)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = payload.get("data", [])
        rows.extend(data)
        total = payload.get("totalCount", len(rows))
        if len(rows) >= total or not data:
            break
        page += 1
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="요청 주소만 출력하고 끝낸다")
    args = parser.parse_args()

    env = load_env()
    key_enc = env.get("ODCLOUD_SERVICE_KEY_ENC", "").strip()
    if not key_enc:
        sys.exit("ODCLOUD_SERVICE_KEY_ENC 가 비어 있습니다. .env 를 확인하세요.")

    failed = False
    for name, spec in DATASETS.items():
        path = env.get(spec["path_env"], "").strip()
        if not path:
            print(f"[건너뜀] {spec['title']}: .env 의 {spec['path_env']} 가 비어 있습니다.")
            continue

        if args.dry_run:
            masked = key_enc[:6] + "..." + key_enc[-4:]
            print(f"[{spec['title']}]\n  {build_url(path, masked, 1)}")
            continue

        try:
            rows = fetch_all(path, key_enc)
        except urllib.error.HTTPError as exc:
            print(f"[실패] {spec['title']}: HTTP {exc.code} {exc.reason}")
            failed = True
            continue
        except Exception as exc:  # noqa: BLE001 - 네트워크 오류 전반
            print(f"[실패] {spec['title']}: {exc}")
            failed = True
            continue

        RAW.mkdir(parents=True, exist_ok=True)
        out = RAW / f"{name}_{date.today().isoformat()}.json"
        out.write_text(
            json.dumps(
                {"meta": {"title": spec["title"], "fetched_at": date.today().isoformat(),
                          "record_count": len(rows)}, "data": rows},
                ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"[저장] {spec['title']}: {len(rows)}건 -> {out.relative_to(ROOT)}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
