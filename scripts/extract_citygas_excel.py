"""도시가스 요금표 엑셀에서 도매·소매 요금을 뽑는다.

사용법:
    python3 scripts/extract_citygas_excel.py <엑셀_폴더> <출력.json>

그 뒤 build 단계가 data/gas/citygas_*.json 을 만든다.

열 위치가 아니라 머리말 글자로 찾는다. 연도마다 열이 조금씩 다르기 때문이다.
"""
import glob, json, os, re, sys
from openpyxl import load_workbook

def norm(v):
    return "" if v is None else re.sub(r"\s+", "", str(v))

def read_one(path):
    wb = load_workbook(path, data_only=True)
    name = next(n for n in wb.sheetnames if "요금표" in n)
    ws = wb[name]

    # 병합 셀은 좌상단 값을 퍼뜨린다 (대분류가 여러 열에 걸쳐 있다)
    merged = {}
    for rng in ws.merged_cells.ranges:
        v = ws.cell(rng.min_row, rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged[(r, c)] = v
    def cell(r, c):
        return merged.get((r, c), ws.cell(r, c).value)

    # 대분류(2행) 자리가 제각각이다. 병합된 것도 있고(C2:G2), 병합 없이
    # 가운데 열에만 적힌 것도 있다(열병합1 은 V, 열병합2 는 Y). 그래서
    # 왼쪽에서 이어받기만 하면 U 가 산업용, X 가 열병합1 로 잘못 붙는다.
    # 계절 3칸(동절기·하절기·기타월)을 한 묶음으로 보고, 묶음 안 아무 칸에나
    # 있는 이름표를 그 묶음 전체에 쓴다.
    # 한 묶음으로 묶을 세부 항목들. 이름표가 묶음 안 어디에 있든 찾아낸다.
    FAMILIES = [("동절기", "하절기", "기타월"),
                ("열전용(1)", "열전용(2)", "열전용(3)")]
    raw = {c: (norm(cell(2, c)), norm(cell(3, c))) for c in range(3, ws.max_column + 1)}
    blocks, c = [], 3
    while c <= ws.max_column:
        fam = next((f for f in FAMILIES if raw.get(c, ("", ""))[1] == f[0]), None)
        if fam:
            grp = [c]
            for nxt in (c + 1, c + 2):
                if raw.get(nxt, ("", ""))[1] in fam[1:]:
                    grp.append(nxt)
            blocks.append(grp)
            c = grp[-1] + 1
        else:
            blocks.append([c])
            c += 1
    cols, major = {}, ""
    for grp in blocks:
        label = next((raw[g][0] for g in grp if raw[g][0]), "")
        if not label:  # 병합 셀에서 끌어온 값
            label = next((norm(cell(2, g)) for g in grp if norm(cell(2, g))), "")
        if label:
            major = label
        for g in grp:
            sub = raw[g][1]
            if not (major or sub): continue
            if sub == major: sub = ""   # 업무난방용|업무난방용 → 업무난방용|
            cols[g] = (major, sub)

    # 도매요금 행과 지역 행을 찾는다
    wholesale_row, region_rows = None, []
    for r in range(3, ws.max_row + 1):
        a = norm(cell(r, 1))
        if not a or a.startswith(("*", "※", "▣")): continue
        if "도매요금" in a:
            wholesale_row = r
        elif wholesale_row is not None:
            region_rows.append(r)

    # 시행일: 1행이나 도매요금 행 라벨의 (YYYY.MM.DD)
    text = " ".join(norm(cell(1, c)) for c in range(1, 8))
    if wholesale_row: text += " " + norm(cell(wholesale_row, 1))
    m = re.search(r"(20\d{2})\.(\d{1,2})\.(\d{1,2})", text)
    if m:
        eff = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    else:  # 파일명 YYMMDD
        b = re.match(r"(\d{2})(\d{2})(\d{2})", os.path.basename(path))
        eff = f"20{b.group(1)}-{b.group(2)}-{b.group(3)}" if b else None

    def row_values(r):
        out = {}
        for c, (mj, sub) in cols.items():
            v = cell(r, c)
            if isinstance(v, (int, float)):
                out[f"{mj}|{sub}"] = round(float(v), 4)
        return out

    return {
        "file": os.path.basename(path).replace("\n", " "),
        "effective_from": eff,
        "sheet": name,
        "wholesale": row_values(wholesale_row) if wholesale_row else {},
        "retail": [
            {"region": norm(cell(r, 1)),
             "company": norm(cell(r, 2)),
             "basic_charge_raw": (lambda v: None if v is None else str(v).replace("\n", " "))(cell(r, 3)),
             "rates": row_values(r)}
            # 요율이 하나도 없는 행은 지역이 아니다. 표 아래 각주
            # ('<참고> 열전용(1)의 요금이 …')가 지역 칸에 걸려 들어오는 것을 막는다.
            for r in region_rows if norm(cell(r, 1)) and row_values(r)
        ],
    }

if __name__ == "__main__":
    root, out = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(root, "**", "*.xlsx"), recursive=True))
    docs, errs = [], []
    for p in files:
        try:
            docs.append(read_one(p))
        except Exception as e:
            errs.append((os.path.basename(p).replace("\n", " "), f"{type(e).__name__}: {e}"))
    docs.sort(key=lambda d: (d["effective_from"] or "", d["file"]))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=1)
    print(f"읽음 {len(docs)}개 / 실패 {len(errs)}개")
    for n, e in errs: print("  실패:", n, "—", e)
    if docs:
        print(f"기간: {docs[0]['effective_from']} ~ {docs[-1]['effective_from']}")
        print(f"지역 행 평균: {sum(len(d['retail']) for d in docs)/len(docs):.1f}")
