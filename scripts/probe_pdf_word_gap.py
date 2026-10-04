"""PDF 줄 내부 어절 공백 추정 규칙을 켜고 끈 출력을 한 프로세스에서 비교해 HWPX 정답 문맥으로 채점한다.

새로 넣은 공백마다 앞뒤 글자를 같은 문서 HWPX 출력에서 찾아 공백 유무로 정답·오답·판정 불가를 매기고,
문서별 tok_ratio·경계 혼동 수·출력 해시·Producer 를 JSON 으로 저장한다(짧은 문맥은 공개 문서에만 쓴다).

    python -m scripts.probe_pdf_word_gap . corpus/press-pairs-holdout out.json [허용 목록 파일]
"""

import statistics
import sys
import json
import hashlib
import subprocess
import unicodedata
import time
import os
from multiprocessing import Pool

if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
from dochan.pdf import content as C
import scripts.compare_pdf_pairs as CP

ORIG = C._Line.__dict__["_hangul_tracking_gaps"].__func__
STATE = {"on": True, "record": False}
KS = (0.1, 0.15, 0.25, 0.35, 0.5)


def patched(cls, frags):
    return ORIG(cls, frags) if STATE["on"] else []


C._Line._hangul_tracking_gaps = classmethod(patched)

REC = {}
ORIG_INIT = C._Line.__init__


def init(self, frags):
    ORIG_INIT(self, frags)
    if not STATE["record"]:
        return
    REC["lines"] += 1
    if not frags or C.writing_direction(frags[0]) != "ltr":
        return
    refs = ORIG(C._Line, frags)
    comparable = sum(C._Line._comparable_hangul(left, r) for left, r in zip(frags, frags[1:]))
    if comparable >= 6 and not refs:
        REC["lines_overprint_off"] += 1
    if comparable >= 1:
        REC["lines_hangul_single"] += 1
    if not refs:
        return
    REC["lines_eval"] += 1
    texts = [f.text for f in frags]
    allg = [
        (C.along(b) - C.along(a) - a.width)
        if C._Line._comparable_hangul(a, b)
        else None
        for a, b in zip(frags, frags[1:])
    ]
    for i, (left, r) in enumerate(zip(frags, frags[1:])):
        if refs[i] is None or not C._Line._comparable_hangul(left, r):
            continue
        key = (round(left.x, 2), round(left.y, 2), round(r.x, 2), left.text, r.text)
        if key in REC["seen"]:
            continue
        REC["seen"].add(key)
        gap = C.along(r) - C.along(left) - left.width
        sp = max(left.space_width, r.space_width)
        left = "".join(texts[: i + 1]).replace(" ", "")[-4:]
        right = "".join(texts[i + 1 :]).replace(" ", "")[:4]

        def same(j):
            a = frags[j]
            return (
                abs(a.size - left.size) <= left.size * 0.02
                and abs(a.width - left.width) <= left.width * 0.02
            )

        lo, hi = max(0, i - 4), min(len(allg), i + 5)
        nb_same = [
            allg[j] for j in range(lo, hi) if j != i and allg[j] is not None and same(j)
        ]
        ref_same = statistics.median(nb_same) if len(nb_same) >= 3 else None
        left_nb = [allg[j] for j in range(lo, i) if allg[j] is not None and same(j)]
        right_nb = [
            allg[j] for j in range(i + 1, hi) if allg[j] is not None and same(j)
        ]
        sides = [statistics.median(x) for x in (left_nb, right_nb) if len(x) >= 2]
        ref_two = max(sides) if sides else None
        REC["bounds"].append(
            (left, right, gap, refs[i], sp, gap > 0.5 * sp, left.size, ref_same, ref_two)
        )


C._Line.__init__ = init

STASH = {}
ORIG_TR = CP.token_ratio


def tr(a, b):
    STASH["a"], STASH["b"] = a, b
    return ORIG_TR(a, b)


CP.token_ratio = tr


def answer_index(answer):
    s = unicodedata.normalize("NFC", answer)
    chars, spaced = [], []
    pend = False
    for ch in s:
        if ch.isspace():
            pend = True
            continue
        chars.append(ch)
        spaced.append(pend)
        pend = False
    return "".join(chars), spaced


def label(ns, spaced, left, right):
    if len(left) < 3 or len(right) < 3:
        return None
    pat = left + right
    votes = set()
    at = ns.find(pat)
    n = 0
    while at >= 0 and n < 50:
        votes.add(spaced[at + len(left)])
        n += 1
        at = ns.find(pat, at + 1)
    if len(votes) != 1:
        return None
    return votes.pop()


def insertions(off, on):
    """on 에만 있는 공백 위치를 두 포인터로 찾는다. 다른 차이가 있으면 anomalies 증가."""
    i = j = 0
    ins = []
    anomalies = 0
    while i < len(on) and j < len(off):
        if on[i] == off[j]:
            i += 1
            j += 1
        elif on[i] == " ":
            ins.append(i)
            i += 1
        else:
            anomalies += 1
            if anomalies > 20:
                break
            i += 1
            j += 1
    return ins, anomalies


def ctx(text, pos):
    left = text[:pos].replace(" ", "").replace("\n", "")[-4:]
    right = text[pos + 1 :].replace(" ", "").replace("\n", "")[:4]
    return left, right


def producer(pdf):
    try:
        completed = subprocess.run(["pdfinfo", pdf], capture_output=True, timeout=30)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
        out = completed.stdout.decode("utf-8", "replace")
    except Exception:
        return "", ""
    prod = cre = ""
    for line in out.splitlines():
        if line.startswith("Producer:"):
            prod = line.split(":", 1)[1].strip()
        if line.startswith("Creator:"):
            cre = line.split(":", 1)[1].strip()
    return prod, cre


def run(pdf):
    hwpx = pdf[:-4] + ".hwpx"
    t0 = time.time()
    res = {"pdf": os.path.basename(pdf)}
    try:
        STATE.update(on=False, record=False)
        off = CP.compare_pair(hwpx, pdf)
        ans, cand_off = STASH["a"], STASH["b"]
        REC.clear()
        REC.update(
            lines=0,
            lines_eval=0,
            lines_overprint_off=0,
            lines_hangul_single=0,
            seen=set(),
            bounds=[],
        )
        STATE.update(on=True, record=True)
        on = CP.compare_pair(hwpx, pdf)
        STATE["record"] = False
        cand_on = STASH["b"]
    except Exception as exc:
        return {"pdf": os.path.basename(pdf), "error": type(exc).__name__}
    ns, spaced = answer_index(ans)
    res["answer_len"] = len(ns)
    keys = (
        "tok_ratio",
        "join_accuracy",
        "labeled_joins",
        "cell_hit",
        "signature_exact",
        "hwpx_tables",
        "pdf_tables",
        "merged_exact",
        "merged_dims_matched",
    )
    res["off"] = {k: off.get(k) for k in keys}
    res["on"] = {k: on.get(k) for k in keys}
    res["hash_off"] = hashlib.sha256(
        cand_off.encode("utf-8", "surrogatepass")
    ).hexdigest()[:16]
    res["hash_on"] = hashlib.sha256(
        cand_on.encode("utf-8", "surrogatepass")
    ).hexdigest()[:16]
    ins, anomalies = insertions(cand_off, cand_on)
    res["inserted"] = len(ins)
    res["anomalies"] = anomalies
    good = bad = unl = 0
    bad_ctx = []
    unl_ctx = []
    dup = 0
    for pos in ins:
        left, r = ctx(cand_on, pos)
        lab = label(ns, spaced, left, r)
        if len(left) >= 2 and len(r) >= 2 and left[-1] == left[-2] and r[0] == r[1]:
            dup += 1
        if lab is None:
            unl += 1
            if len(unl_ctx) < 8:
                unl_ctx.append(left + "|" + r)
        elif lab:
            good += 1
        else:
            bad += 1
            if len(bad_ctx) < 8:
                bad_ctx.append(left + "|" + r)
    res["ins_good"], res["ins_bad"], res["ins_unl"] = good, bad, unl
    res["bad_ctx"] = bad_ctx
    res["unl_ctx"] = unl_ctx
    res["dup_like"] = dup
    # 경계 단위 혼동 행렬 (old 규칙 vs k 별 새 규칙)
    conf = {"old": [0, 0, 0, 0]}
    for k in KS:
        conf[str(k)] = [0, 0, 0, 0]  # tp fp fn tn
    gaps_rel = []
    conf["same"] = [0, 0, 0, 0]
    conf["two"] = [0, 0, 0, 0]
    conf["em_floor"] = [0, 0, 0, 0]
    conf["em015"] = [0, 0, 0, 0]
    for left, right, gap, ref, sp, old, size, ref_same, ref_two in REC["bounds"]:
        lab = label(ns, spaced, left, right)
        if lab is None:
            continue

        def add(name, pred):
            c = conf[name]
            if pred and lab:
                c[0] += 1
            elif pred and not lab:
                c[1] += 1
            elif not pred and lab:
                c[2] += 1
            else:
                c[3] += 1

        add("old", old)
        for k in KS:
            add(str(k), old or gap > ref + k * sp)
        add("same", old or (ref_same is not None and gap > ref_same + 0.25 * sp))
        add("two", old or (ref_two is not None and gap > ref_two + 0.25 * sp))
        add("em_floor", old or gap > ref + 0.25 * max(sp, 0.5 * size))
        add("em015", old or gap > ref + 0.15 * size)
        gaps_rel.append((round((gap - ref) / size, 3), round(sp / size, 3), lab))
    res["conf"] = conf
    res["gaps_rel"] = gaps_rel[:4000]
    res["lines"] = REC["lines"]
    res["lines_eval"] = REC["lines_eval"]
    res["lines_overprint_off"] = REC["lines_overprint_off"]
    res["lines_hangul_single"] = REC["lines_hangul_single"]
    res["producer"], res["creator"] = producer(pdf)
    res["sec"] = round(time.time() - t0, 1)
    return res


if __name__ == "__main__":
    corpus, out = sys.argv[2], sys.argv[3]
    names = [
        n
        for n in sorted(os.listdir(corpus))
        if n.endswith(".pdf") and os.path.exists(os.path.join(corpus, n[:-4] + ".hwpx"))
    ]
    if len(sys.argv) > 4:
        allow = set(open(sys.argv[4]).read().split())
        names = [n for n in names if n[:-4] in allow]
    paths = [os.path.join(corpus, n) for n in names]
    rows = []
    with Pool(4, maxtasksperchild=10) as pool:
        for row in pool.imap_unordered(run, paths):
            rows.append(row)
            sys.stderr.write(
                "%d/%d %s %s\n"
                % (len(rows), len(paths), row["pdf"], row.get("sec", row.get("error")))
            )
    json.dump(rows, open(out, "w"), ensure_ascii=False)
