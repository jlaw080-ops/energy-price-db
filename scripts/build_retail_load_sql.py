#!/usr/bin/env python3
"""소매요금 JSON -> 압축 SQL 조각 생성기 (자기검증 포함).

사용법:  python3 scripts/build_retail_load_sql.py [출력폴더]

인코딩: (지역,용도)별로
  - rng : 연속 시행일 구간 [lo,hi]
  - hole: 구간 내 빠진 시행일
  - mark: 차액(소매-도매) 변화시점만
  - raw : 도매값이 없어 차액을 쓸 수 없는 칸의 실측값
디코딩을 파이썬에서 그대로 재현해 JSON과 완전 일치를 확인한다.
"""
import json, glob, sys, os
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'build', 'retail_sql')

# ---------- 1) 입력 읽기 ----------
retail = {}   # (region, cat, detail) -> {date: value}
for f in sorted(glob.glob(f'{REPO}/data/gas/citygas_소매요금_*.json')):
    for it in json.load(open(f))['items']:
        key = (it['region'], it['use_category'], it.get('use_detail', '') or '')
        retail.setdefault(key, {})[it['effective_from']] = float(it['won_per_mj'])

wholesale = {}  # (cat, detail, date) -> value
for it in json.load(open(f'{REPO}/data/gas/citygas_도매요금_월별.json'))['items']:
    wholesale[(it['use_category'], it.get('use_detail', '') or '', it['effective_from'])] = float(it['won_per_mj'])

total_rows = sum(len(v) for v in retail.values())
dates  = sorted({d for v in retail.values() for d in v})
regions= sorted({k[0] for k in retail})
uses   = sorted({(k[1], k[2]) for k in retail})
di = {d: i for i, d in enumerate(dates)}
gi = {g: i for i, g in enumerate(regions)}
pi = {u: i for i, u in enumerate(uses)}
print(f'소매 행수={total_rows}  시행일={len(dates)}  지역={len(regions)}  용도={len(uses)}', file=sys.stderr)

# ---------- 2) 인코딩 ----------
enc = {}  # (g,p) -> dict(rng=[(lo,hi)], hole=[k], mark=[(k,mk)], raw=[(k,v)])
for (reg, cat, det), series in retail.items():
    g, p = gi[reg], pi[(cat, det)]
    ks = sorted(di[d] for d in series)
    # 연속 구간으로 묶는다 (틈이 1칸이면 hole 로 흡수)
    rngs, holes = [], []
    lo = prev = ks[0]
    for k in ks[1:]:
        if k == prev + 1:
            prev = k
        elif k - prev <= 40:                 # 가까운 틈은 구간에 흡수 + hole 기록
            holes.extend(range(prev + 1, k))
            prev = k
        else:
            rngs.append((lo, prev)); lo = prev = k
    rngs.append((lo, prev))
    marks, raws = [], []
    last_mk = None
    for k in ks:
        d = dates[k]
        v = series[d]
        w = wholesale.get((cat, det, d))
        if w is None:
            raws.append((k, v)); last_mk = None    # 도매 없음 -> 실측값
            continue
        mk = round(v - w, 4)
        if last_mk is None or mk != last_mk:
            marks.append((k, mk)); last_mk = mk
    enc[(g, p)] = dict(rng=rngs, hole=sorted(holes), mark=marks, raw=raws)

# ---------- 3) 디코딩 검증 ----------
rebuilt = {}
for (g, p), e in enc.items():
    reg, (cat, det) = regions[g], uses[p]
    hole = set(e['hole']); rawd = dict(e['raw'])
    for lo, hi in e['rng']:
        for k in range(lo, hi + 1):
            if k in hole: continue
            d = dates[k]
            if k in rawd:
                val = rawd[k]
            else:
                w = wholesale.get((cat, det, d))
                mk = None
                for mk_k, mk_v in e['mark']:
                    if mk_k <= k: mk = mk_v
                    else: break
                if w is None or mk is None:
                    print(f'!! 복원불가 {reg}/{cat}/{det}/{d}', file=sys.stderr); sys.exit(1)
                val = round(w + mk, 4)
            rebuilt[(reg, cat, det, d)] = val

orig = {(r, c, t, d): v for (r, c, t), s in retail.items() for d, v in s.items()}
if len(rebuilt) != len(orig):
    print(f'!! 행수 불일치 복원={len(rebuilt)} 원본={len(orig)}', file=sys.stderr); sys.exit(1)
bad = [(k, rebuilt[k], orig[k]) for k in orig if abs(rebuilt[k] - orig[k]) > 1e-9]
if bad:
    print(f'!! 값 불일치 {len(bad)}건, 예: {bad[:3]}', file=sys.stderr); sys.exit(1)
print(f'검증 통과: {len(orig)}행 완전 일치', file=sys.stderr)

units = sum(len(e['rng']) + len(e['hole']) + len(e['mark']) + len(e['raw']) for e in enc.values())
print(f'전송 단위 {units} ({units/total_rows*100:.1f}%)', file=sys.stderr)

# ---------- 4) SQL 조각 출력 ----------
def arr(vals, typ):
    if not vals: return f"array[NULL]::{typ}[]"
    if typ == 'text':
        return "array[" + ",".join("'" + str(v).replace("'", "''") + "'" for v in vals) + "]::text[]"
    return "array[" + ",".join(str(v) for v in vals) + f"]::{typ}[]"

# 조각마다 조회표를 함께 보내 자족형으로 만든다.
# (DB 에 임시 테이블을 만들면 create/truncate 가 권한 확인창을 띄워 멈춘다)
HEAD = (
 "with dates(k,d) as (select * from unnest(%s,%s)),\n"
 "gg(i,v) as (select * from unnest(%s,%s)),\n"
 "pp(i,c,t) as (select * from unnest(%s,%s,%s)),\n"
) % (arr(range(len(dates)), 'int'), arr(dates, 'text').replace('::text[]', '::date[]'),
     arr(range(len(regions)), 'int'), arr(regions, 'text'),
     arr(range(len(uses)), 'int'), arr([u[0] for u in uses], 'text'), arr([u[1] for u in uses], 'text'))

TAIL = """ex as (select r.g,r.p,dt.k,dt.d from rng r join dates dt on dt.k between r.lo and r.hi
  where not exists (select 1 from hole h where h.g=r.g and h.p=r.p and h.k=dt.k))
insert into pricing.citygas_retail_monthly (effective_from,region,use_category,use_detail,won_per_mj)
select ex.d, gg.v, pp.c, pp.t, coalesce(rw.v, w.won_per_mj + mk.mk)
from ex join gg on gg.i=ex.g join pp on pp.i=ex.p
left join raw rw on rw.g=ex.g and rw.p=ex.p and rw.k=ex.k
left join pricing.citygas_wholesale_monthly w on w.effective_from=ex.d and w.use_category=pp.c and w.use_detail=pp.t
left join lateral (select mark.mk from mark where mark.g=ex.g and mark.p=ex.p and mark.k<=ex.k
                   order by mark.k desc limit 1) mk on true
on conflict (effective_from,region,use_category,use_detail) do update set won_per_mj=excluded.won_per_mj;
select %d as 조각, count(*) as 누적행수 from pricing.citygas_retail_monthly;
"""

def body(keys):
    R=[[],[],[],[]]; H=[[],[],[]]; M=[[],[],[],[]]; W=[[],[],[],[]]
    for (g,p) in keys:
        e=enc[(g,p)]
        for lo,hi in e['rng']: R[0].append(g);R[1].append(p);R[2].append(lo);R[3].append(hi)
        for k in e['hole']:    H[0].append(g);H[1].append(p);H[2].append(k)
        for k,v in e['mark']:  M[0].append(g);M[1].append(p);M[2].append(k);M[3].append(v)
        for k,v in e['raw']:   W[0].append(g);W[1].append(p);W[2].append(k);W[3].append(v)
    return (
      f"rng(g,p,lo,hi) as (select * from unnest({arr(R[0],'int')},{arr(R[1],'int')},{arr(R[2],'int')},{arr(R[3],'int')})),\n"
      f"hole(g,p,k) as (select * from unnest({arr(H[0],'int')},{arr(H[1],'int')},{arr(H[2],'int')})),\n"
      f"mark(g,p,k,mk) as (select * from unnest({arr(M[0],'int')},{arr(M[1],'int')},{arr(M[2],'int')},{arr(M[3],'numeric')})),\n"
      f"raw(g,p,k,v) as (select * from unnest({arr(W[0],'int')},{arr(W[1],'int')},{arr(W[2],'int')},{arr(W[3],'numeric')})),\n")

# 글자수 상한에 맞춰 (g,p) 를 조각으로 나눈다
LIMIT = 7000  # 조각이 커지면 전송 중 배열이 잘릴 수 있다
keys = sorted(enc)
chunks, cur = [], []
for k in keys:
    trial = cur + [k]
    if cur and len(body(trial)) > LIMIT:
        chunks.append(cur); cur = [k]
    else:
        cur = trial
chunks.append(cur)

outdir = OUT
os.makedirs(outdir, exist_ok=True)
for old in glob.glob(f'{outdir}/*.sql'): os.remove(old)
for i, c in enumerate(chunks, 1):
    with open(f'{outdir}/{i:02d}.sql', 'w') as fh:
        fh.write(HEAD + body(c) + TAIL % i)
print(f'조각 {len(chunks)}개 -> {outdir}', file=sys.stderr)
for i,c in enumerate(chunks,1):
    sz=os.path.getsize(f'{outdir}/{i:02d}.sql')
    print(f'  {i:02d}.sql  {sz:>6}B  (지역·용도 {len(c)}쌍)', file=sys.stderr)
