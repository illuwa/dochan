"""Independent BIFF8 oracle for embedded Excel.Chart.8 workbooks (written from the MS-XLS layout).

For the active chart sheet: SERIES -> BRAI(values/categories) -> Area3d/Ref3d -> worksheet cells.
Also reads the chart's own SIIndex cache. No dochan imports.
"""

import struct
import sys


def recs(data):
    i = 0
    while i + 4 <= len(data):
        t, n = struct.unpack_from("<HH", data, i)
        yield i, t, data[i + 4 : i + 4 + n]
        i += 4 + n


def rk(v):
    if v & 2:
        x = v >> 2
        if x & 0x20000000:
            x -= 0x40000000
        x = float(x)
    else:
        x = struct.unpack("<d", struct.pack("<Q", (v & 0xFFFFFFFC) << 32))[0]
    return x / 100 if v & 1 else x


def xlstr(b, off, cch, flags):
    hb = flags & 1
    rich = flags & 8
    ext = flags & 4
    i = off
    runs = struct.unpack_from("<H", b, i)[0] if rich else 0
    i += 2 if rich else 0
    extn = struct.unpack_from("<I", b, i)[0] if ext else 0
    i += 4 if ext else 0
    n = cch * (2 if hb else 1)
    s = b[i : i + n].decode("utf-16le" if hb else "latin-1")
    return s, i + n + runs * 4 + extn


def sst_strings(chunks):
    """chunks: SST data followed by CONTINUE datas."""
    out = []
    first = chunks[0]
    total_unique = struct.unpack_from("<I", first, 4)[0]
    ci, pos = 0, 8

    def need():
        nonlocal ci, pos
        if pos >= len(chunks[ci]):
            ci += 1
            pos = 0

    while len(out) < total_unique and ci < len(chunks):
        need()
        if ci >= len(chunks):
            break
        c = chunks[ci]
        cch = struct.unpack_from("<H", c, pos)[0]
        flags = c[pos + 2]
        pos += 3
        hb = flags & 1
        rich = flags & 8
        ext = flags & 4
        runs = 0
        extn = 0
        if rich:
            runs = struct.unpack_from("<H", c, pos)[0]
            pos += 2
        if ext:
            extn = struct.unpack_from("<I", c, pos)[0]
            pos += 4
        s = ""
        left = cch
        while left:
            c = chunks[ci]
            avail = (len(c) - pos) // (2 if hb else 1)
            take = min(avail, left)
            n = take * (2 if hb else 1)
            s += c[pos : pos + n].decode("utf-16le" if hb else "latin-1")
            pos += n
            left -= take
            if left:
                ci += 1
                pos = 0
                hb = chunks[ci][0] & 1
                pos = 1
        skip = runs * 4 + extn
        while skip:
            c = chunks[ci]
            take = min(skip, len(c) - pos)
            pos += take
            skip -= take
            if skip:
                ci += 1
                pos = 0
        out.append(s)
    return out


def parse(data):
    sheets = []
    externs = []
    supbooks = []
    chunks = None
    sst = []
    itab_cur = 0
    it = list(recs(data))
    # globals until first EOF
    k = 0
    while k < len(it):
        off, t, b = it[k]
        if t == 0x0085:
            pos, st, dt = struct.unpack_from("<IBB", b)
            cch, fl = b[6], b[7]
            name = b[8 : 8 + cch * (2 if fl & 1 else 1)].decode(
                "utf-16le" if fl & 1 else "latin-1"
            )
            sheets.append((pos, dt, name))
        elif t == 0x003D and len(b) >= 12:
            itab_cur = struct.unpack_from("<H", b, 10)[0]
        elif t == 0x01AE:
            supbooks.append(struct.unpack_from("<HH", b))
        elif t == 0x0017:
            n = struct.unpack_from("<H", b)[0]
            externs = [struct.unpack_from("<HHH", b, 2 + 6 * j) for j in range(n)]
        elif t == 0x00FC:
            chunks = [b]
            j = k + 1
            while j < len(it) and it[j][1] == 0x003C:
                chunks.append(it[j][2])
                j += 1
            sst = sst_strings(chunks)
        elif t == 0x000A:
            break
        k += 1
    offsets = {o: idx for idx, (o, _, _) in enumerate(it)}

    def substream(pos):
        idx = offsets[pos]
        out = []
        depth = 0
        for o, t, b in it[idx:]:
            if t == 0x0809:
                depth += 1
                if depth > 1:
                    continue
            if depth == 1:
                out.append((t, b))
            if t == 0x000A:
                depth -= 1
                if depth == 0:
                    break
        return out

    cells = {}
    for si, (pos, dt, name) in enumerate(sheets):
        if dt != 0 or pos not in offsets:
            continue
        pending = None
        for t, b in substream(pos):
            if t == 0x0203:
                r, c = struct.unpack_from("<HH", b)
                cells[(si, r, c)] = struct.unpack_from("<d", b, 6)[0]
            elif t == 0x027E:
                r, c = struct.unpack_from("<HH", b)
                cells[(si, r, c)] = rk(struct.unpack_from("<I", b, 6)[0])
            elif t == 0x00BD:
                r, c0 = struct.unpack_from("<HH", b)
                n = (len(b) - 6) // 6
                for j in range(n):
                    cells[(si, r, c0 + j)] = rk(
                        struct.unpack_from("<I", b, 4 + 6 * j + 2)[0]
                    )
            elif t == 0x00FD:
                r, c = struct.unpack_from("<HH", b)
                cells[(si, r, c)] = sst[struct.unpack_from("<I", b, 6)[0]]
            elif t == 0x0204:
                r, c = struct.unpack_from("<HH", b)
                cch = struct.unpack_from("<H", b, 6)[0]
                cells[(si, r, c)] = xlstr(b, 9, cch, b[8])[0]
            elif t == 0x0006:
                r, c = struct.unpack_from("<HH", b)
                v = b[6:14]
                if v[6:8] == b"\xff\xff":
                    if v[0] == 0:
                        pending = (si, r, c)
                    elif v[0] == 1:
                        cells[(si, r, c)] = bool(v[2])
                else:
                    cells[(si, r, c)] = struct.unpack("<d", v)[0]
            elif t == 0x0207 and pending:
                cch = struct.unpack_from("<H", b)[0]
                cells[pending] = xlstr(b, 3, cch, b[2])[0]
                pending = None
    charts = [(i, s) for i, s in enumerate(sheets) if s[1] == 2]
    chosen = next(
        (c for c in charts if c[0] == itab_cur), charts[0] if charts else None
    )
    if chosen is None:
        return None
    series = []
    cur = None
    cache = {}
    si_idx = None
    for t, b in substream(chosen[1][0]):
        if t == 0x1003:
            cur = {"values": None, "cats": None, "name": None}
            series.append(cur)
        elif t == 0x1051 and cur is not None:
            bid, rt = b[0], b[1]
            cce = struct.unpack_from("<H", b, 6)[0]
            rgce = b[8 : 8 + cce]
            key = {0: "name", 1: "values", 2: "cats"}.get(bid)
            if key and rt == 2:
                cur[key] = ("ref", rgce)
        elif t == 0x100D and cur is not None and cur["name"] is None:
            cch = b[2]
            cur["name"] = (
                "lit",
                b[4 : 4 + cch * (2 if b[3] & 1 else 1)].decode(
                    "utf-16le" if b[3] & 1 else "latin-1"
                ),
            )
        elif t == 0x1065:
            si_idx = struct.unpack_from("<H", b)[0]
        elif t in (0x0203, 0x0204, 0x0201) and si_idx:
            r, c = struct.unpack_from("<HH", b)
            v = (
                struct.unpack_from("<d", b, 6)[0]
                if t == 0x0203
                else (
                    xlstr(b, 9, struct.unpack_from("<H", b, 6)[0], b[8])[0]
                    if t == 0x0204
                    else None
                )
            )
            cache[(si_idx, c, r)] = v

    def resolve(ref):
        out = []
        if not ref:
            return None
        rg = ref[1]
        i = 0
        while i < len(rg):
            p = rg[i]
            if p in (0x3B, 0x5B, 0x7B):
                ixti, r0, r1, c0, c1 = struct.unpack_from("<HHHHH", rg, i + 1)
                i += 11
            elif p in (0x3A, 0x5A, 0x7A):
                ixti, r0, c0 = struct.unpack_from("<HHH", rg, i + 1)
                r1, c1 = r0, c0
                i += 7
            elif p == 0x10 or p == 0x15:
                i += 1
                continue
            elif p == 0x29:
                i += 3
                continue  # ptgMemFunc + cce
            else:
                return "unsupported ptg 0x%02X" % p
            sb, itab, _ = externs[ixti]
            c0 &= 0x3FFF
            c1 &= 0x3FFF
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    out.append(cells.get((itab, r, c)))
        return out

    result = []
    for j, s in enumerate(series):
        name = s["name"]
        nm = (
            resolve(name)
            if name and name[0] == "ref"
            else ([name[1]] if name else None)
        )
        result.append(
            {
                "name": nm,
                "values": resolve(s["values"]),
                "cats": resolve(s["cats"]),
                "cache_values": [
                    cache.get((1, j, r)) for r in range(64) if (1, j, r) in cache
                ],
                "cache_cats": [
                    cache.get((2, j, r)) for r in range(64) if (2, j, r) in cache
                ],
            }
        )
    return {
        "chart_sheet": chosen[1][2],
        "itab_cur": itab_cur,
        "sheets": [(s[1], s[2]) for s in sheets],
        "series": result,
    }


if __name__ == "__main__":
    import json

    for p in sys.argv[1:]:
        r = parse(open(p, "rb").read())
        print(p.split("/")[-1], json.dumps(r, ensure_ascii=False, default=str)[:900])
