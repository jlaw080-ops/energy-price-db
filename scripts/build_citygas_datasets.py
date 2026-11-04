"""raw.json → 레포에 넣을 도매/소매 데이터셋.

행마다 반복되는 값(원본 파일명, 공급회사, 기본요금 문구)은 items 에서 빼고
meta/regions 에 한 번만 적는다. 그렇게 하지 않으면 파일이 20MB 가 넘는다.
"""
import json, os, sys, collections

raw = json.load(open(sys.argv[1], encoding="utf-8"))
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)
SRC = "단가정보/가스요금/시도별_도시가스_요금표"
REPO = "enerbuild/energinno-knowledge-bank (jlaw80-price)"

def split(key):
    a, _, b = key.partition("|")
    return a, b

def dump(path, doc):
    """items 는 한 줄에 하나씩 — 사람이 diff 를 읽을 수 있게."""
    with open(path, "w", encoding="utf-8") as f:
        head = {k: v for k, v in doc.items() if k != "items"}
        f.write(json.dumps(head, ensure_ascii=False, indent=1)[:-2] + ",\n")
        f.write(' "items": [\n')
        f.write(",\n".join("  " + json.dumps(i, ensure_ascii=False, separators=(",", ":"))
                           for i in doc["items"]))
        f.write("\n ]\n}\n")

srcmap = {d["effective_from"]: d["file"] for d in raw}

# ── 도매 ─────────────────────────────────────────────
wholesale = [{"effective_from": d["effective_from"], "use_category": c,
              "use_detail": t, "won_per_mj": v}
             for d in raw
             for k, v in sorted(d["wholesale"].items())
             for c, t in [split(k)]]
dump(f"{outdir}/citygas_도매요금_월별.json", {
  "meta": {
    "dataset": "citygas_wholesale_monthly",
    "title": "도시가스 용도별 도매요금 월별 시계열",
    "provider": "시·도별 도시가스 요금표 (공시용 엑셀)",
    "source_dir": SRC, "source_repo": REPO, "source_type": "추출본",
    "unit": "원/MJ", "vat": "부가세 별도",
    "period": f"{raw[0]['effective_from']} ~ {raw[-1]['effective_from']}",
    "snapshot_count": len(raw), "record_count": len(wholesale),
    "converted_at": "2026-11-04",
    "verification": "2026-09-01 시점의 10개 용도를 한국가스공사 공시 도매요금과 대조해 전부 일치했다.",
    "caveat": "2026-11-01 파일의 도매요금란은 2026-10-01 값과 같다(11월 도매 인상 미반영). "
              "그 시점은 pricing.gas_wholesale_price 의 가스공사 공시값을 쓸 것.",
    "source_files": srcmap,
  }, "items": wholesale})

# ── 소매 (연도별) ─────────────────────────────────────
items_by_year = collections.defaultdict(list)
regs_by_year = collections.defaultdict(list)
for d in raw:
    y = d["effective_from"][:4]
    for r in d["retail"]:
        regs_by_year[y].append({"effective_from": d["effective_from"],
                                "region": r["region"], "company": r["company"],
                                "basic_charge_note": r["basic_charge_raw"]})
        for k, v in sorted(r["rates"].items()):
            c, t = split(k)
            items_by_year[y].append({"effective_from": d["effective_from"],
                                     "region": r["region"], "use_category": c,
                                     "use_detail": t, "won_per_mj": v})
total = 0
for y in sorted(items_by_year):
    items = items_by_year[y]; total += len(items)
    dump(f"{outdir}/citygas_소매요금_{y}.json", {
      "meta": {
        "dataset": "citygas_retail_monthly",
        "title": f"시·도별 도시가스 소매요금 월별 ({y}년)",
        "provider": "시·도별 도시가스 요금표 (공시용 엑셀)",
        "source_dir": SRC, "source_repo": REPO, "source_type": "추출본",
        "unit": "원/MJ", "vat": "부가세 별도", "year": int(y),
        "record_count": len(items), "converted_at": "2026-11-04",
        "caveat": "소매요금은 시·도지사 승인으로 정해져 지역마다 다르고, 도매 변동이 지역별로 "
                  "늦게 반영되기도 한다. 원본 파일명의 'pending/미반영' 표기가 그 뜻이다.",
        "source_files": {k: v for k, v in srcmap.items() if k[:4] == y},
      },
      "regions": regs_by_year[y],
      "items": items})

print(f"도매 {len(wholesale):,}행 / 소매 {total:,}행")
