#!/usr/bin/env python3
"""생성된 SQL 파일을 파싱해 SQL 과 동일한 방식으로 값을 복원하고 JSON 과 대조.

사용법:  python3 scripts/verify_retail_load_sql.py <SQL폴더>
"""
import re, json, glob, sys, os
REPO=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLDIR=sys.argv[1]

def arrays(text, cte):
    # "cte(...) as (select * from unnest(A,B,...))," 에서 array[...] 들을 뽑는다
    m = re.search(re.escape(cte)+r'\([^)]*\) as \(select \* from unnest\((.*?)\)\),\n', text, re.S)
    if not m: return None
    inner = m.group(1)
    out=[]
    for am in re.finditer(r'array\[(.*?)\]::(\w+)\[\]', inner, re.S):
        body, typ = am.group(1), am.group(2)
        if body.strip()=='NULL': out.append([]); continue
        if typ in ('text','date'):
            out.append([s.strip().strip("'") for s in body.split("','")] if False else re.findall(r"'((?:[^']|'')*)'", body))
        else:
            out.append([float(x) if typ=='numeric' else int(x) for x in body.split(',')])
    return out

wholesale={}
for it in json.load(open(f'{REPO}/data/gas/citygas_도매요금_월별.json'))['items']:
    wholesale[(it['use_category'], it.get('use_detail','') or '', it['effective_from'])]=float(it['won_per_mj'])
orig={}
for f in sorted(glob.glob(f'{REPO}/data/gas/citygas_소매요금_*.json')):
    for it in json.load(open(f))['items']:
        orig[(it['region'],it['use_category'],it.get('use_detail','') or '',it['effective_from'])]=float(it['won_per_mj'])

rebuilt={}; problems=[]
for path in sorted(glob.glob(f'{SQLDIR}/*.sql')):
    t=open(path).read()
    dk,dd = arrays(t,'dates')
    gi,gv = arrays(t,'gg')
    pi,pc,pt = arrays(t,'pp')
    rg,rp,rlo,rhi = arrays(t,'rng')
    hg,hp,hk = arrays(t,'hole')
    mg,mp,mk_,mv = arrays(t,'mark')
    wg,wp,wk,wv = arrays(t,'raw')
    # 길이 점검
    for name,group in (('rng',(rg,rp,rlo,rhi)),('hole',(hg,hp,hk)),('mark',(mg,mp,mk_,mv)),('raw',(wg,wp,wk,wv))):
        ls={len(x) for x in group}
        if len(ls)>1: problems.append(f'{os.path.basename(path)} {name} 배열 길이 불일치 {[len(x) for x in group]}')
    date_by_k={k:d for k,d in zip(dk,dd)}
    reg_by_i={i:v for i,v in zip(gi,gv)}
    use_by_i={i:(c,tt) for i,c,tt in zip(pi,pc,pt)}
    holes={(a,b,c) for a,b,c in zip(hg,hp,hk)}
    raws={(a,b,c):d for a,b,c,d in zip(wg,wp,wk,wv)}
    marks={}
    for a,b,c,d in zip(mg,mp,mk_,mv): marks.setdefault((a,b),[]).append((c,d))
    for g,p,lo,hi in zip(rg,rp,rlo,rhi):
        reg=reg_by_i[g]; cat,det=use_by_i[p]
        for k in range(lo,hi+1):
            if (g,p,k) in holes: continue
            d=date_by_k[k]
            if (g,p,k) in raws: val=raws[(g,p,k)]
            else:
                w=wholesale.get((cat,det,d))
                m=None
                for ck,cv in marks.get((g,p),[]):
                    if ck<=k: m=cv
                if w is None or m is None:
                    problems.append(f'{os.path.basename(path)} NULL: {reg}/{cat}/{det}/{d} (도매={w} 차액={m})')
                    continue
                val=round(w+m,4)
            rebuilt[(reg,cat,det,d)]=val

print(f'복원 {len(rebuilt)}행 / 원본 {len(orig)}행')
extra=set(rebuilt)-set(orig); miss=set(orig)-set(rebuilt)
print(f'원본에 없는 행 {len(extra)}  빠진 행 {len(miss)}')
bad=[k for k in orig if k in rebuilt and abs(rebuilt[k]-orig[k])>1e-9]
print(f'값 불일치 {len(bad)}건')
for b in bad[:5]: print('  ',b, rebuilt[b], orig[b])
print(f'문제 {len(problems)}건')
for p in problems[:10]: print('  ',p)
