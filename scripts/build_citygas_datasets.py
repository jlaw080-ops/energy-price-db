"""raw.json → 레포에 넣을 도매/소매 데이터셋.

행마다 반복되는 값(원본 파일명, 공급회사, 기본요금 문구)은 items 에서 빼고
meta/regions 에 한 번만 적는다. 그렇게 하지 않으면 파일이 20MB 가 넘는다.
"""
import json, os, sys, glob, collections

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

# ── 원본 공시 결함 보정 ──────────────────────────────
# 공시 엑셀 자체가 잘못 인쇄된 칸을 고친다. 원래 인쇄값은 source_won_per_mj 에 남기고
# meta.corrections 에 근거를 적는다. 여기 없는 값은 공시 그대로 둔다.
CORRECTIONS = [{
  "effective_from": "2020-07-01",
  "use_category": "연료전지용",
  "rule": "add_wholesale",   # 인쇄값이 공급비용뿐 → 총요율 = 도매 + 인쇄값
  "what": "원본 공시 엑셀의 연료전지용 열에 총 요율이 아니라 지역 공급비용만 인쇄돼 있었다.",
  "evidence": ("원본 엑셀(200701 요금표(도매인하)_소매반영_공시.xlsx) 요금표(MJ) 시트 "
               "4행=도매 9.8664, 5행 서울=0.7599. 비교 가능한 27개 지역 중 26개가 "
               "2020-08-01 공급비용과 정확히 일치해 확인."),
}]


def apply_corrections(items, wholesale):
    """items 를 제자리에서 보정하고, 적용 내역을 돌려준다."""
    wh = {(w["effective_from"], w["use_category"], w["use_detail"]): w["won_per_mj"]
          for w in wholesale}
    applied = []
    for c in CORRECTIONS:
        hit = 0
        for it in items:
            if (it["effective_from"] != c["effective_from"]
                    or it["use_category"] != c["use_category"]
                    or "source_won_per_mj" in it):
                continue
            w = wh.get((it["effective_from"], it["use_category"], it["use_detail"]))
            if w is None:
                continue
            if c["rule"] == "add_wholesale":
                if it["won_per_mj"] >= w:      # 이미 총요율이면 건드리지 않는다
                    continue
                it["source_won_per_mj"] = it["won_per_mj"]
                it["won_per_mj"] = round(w + it["won_per_mj"], 4)
                it["note"] = ("공시 인쇄값은 공급비용뿐이어서 총요율 = 도매 %.4f + %.4f 로 "
                              "복원했다. 원래 인쇄값은 source_won_per_mj." % (w, it["source_won_per_mj"]))
                hit += 1
        if hit:
            applied.append({k: c[k] for k in ("effective_from", "use_category", "what", "evidence")}
                           | {"rows": hit, "rule": c["rule"]})
    return applied


if len(sys.argv) > 1 and sys.argv[1] == "--fix-existing":
    # 이미 만들어진 data/gas/*.json 에 CORRECTIONS 만 적용한다 (raw.json 불필요).
    datadir = sys.argv[2]
    wh_items = json.load(open(f"{datadir}/citygas_도매요금_월별.json",
                              encoding="utf-8"))["items"]
    for path in sorted(glob.glob(f"{datadir}/citygas_소매요금_*.json")):
        doc = json.load(open(path, encoding="utf-8"))
        applied = apply_corrections(doc["items"], wh_items)
        if applied:
            doc["meta"]["corrections"] = applied
            dump(path, doc)
            print(f"보정 적용: {os.path.basename(path)} "
                  f"({sum(a['rows'] for a in applied)}행)")
    sys.exit(0)

raw = json.load(open(sys.argv[1], encoding="utf-8"))
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)
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
    corrections = apply_corrections(items, wholesale)
    dump(f"{outdir}/citygas_소매요금_{y}.json", {
      "meta": {
        "dataset": "citygas_retail_monthly",
        "title": f"시·도별 도시가스 소매요금 월별 ({y}년)",
        "provider": "시·도별 도시가스 요금표 (공시용 엑셀)",
        "source_dir": SRC, "source_repo": REPO, "source_type": "추출본",
        "unit": "원/MJ", "vat": "부가세 별도", "year": int(y),
        "record_count": len(items), "converted_at": "2026-11-04",
        **({"corrections": corrections} if corrections else {}),
        "caveat": "소매요금은 시·도지사 승인으로 정해져 지역마다 다르고, 도매 변동이 지역별로 "
                  "늦게 반영되기도 한다. 원본 파일명의 'pending/미반영' 표기가 그 뜻이다.",
        "source_files": {k: v for k, v in srcmap.items() if k[:4] == y},
      },
      "regions": regs_by_year[y],
      "items": items})

print(f"도매 {len(wholesale):,}행 / 소매 {total:,}행")
