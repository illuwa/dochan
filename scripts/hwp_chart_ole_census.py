"""Independent HWP chart OLE census (olefile + own record walker; no dochan imports)."""

import json
import struct
import sys
import zlib
from multiprocessing import Pool
from pathlib import Path
import olefile

TAG_BEGIN = 0x10
T_BIN_DATA = TAG_BEGIN + 2  # DocInfo BIN_DATA
T_CTRL_HEADER = TAG_BEGIN + 55  # 71
T_LIST_HEADER = TAG_BEGIN + 56  # 72
T_SHAPE_COMPONENT = TAG_BEGIN + 60  # 76
T_SC_PICTURE = TAG_BEGIN + 69  # 85
T_SC_OLE = TAG_BEGIN + 68  # 84
LIMIT = 256 * 1024 * 1024


def inflate(data):
    d = zlib.decompressobj(-15)
    out = d.decompress(data, LIMIT)
    return out


def records(buf):
    i = 0
    n = len(buf)
    while i + 4 <= n:
        h = struct.unpack_from("<I", buf, i)[0]
        i += 4
        tag = h & 0x3FF
        level = (h >> 10) & 0x3FF
        size = h >> 20
        if size == 0xFFF:
            if i + 4 > n:
                break
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4
        yield tag, level, buf[i : i + size]
        i += size


def ctrl_name(data):
    return data[:4][::-1].decode("latin-1") if len(data) >= 4 else "?"


def walk_section(buf):
    refs = []
    stack = []  # (level, tag, ctrlname)
    for tag, level, data in records(buf):
        while stack and stack[-1][0] >= level:
            stack.pop()
        name = ctrl_name(data) if tag == T_CTRL_HEADER else None
        if tag == T_SC_OLE:
            ctrls = [s[2] for s in stack if s[1] == T_CTRL_HEADER]
            bid = struct.unpack_from("<H", data, 12)[0] if len(data) >= 14 else None
            refs.append({"bin": bid, "ctrls": ctrls})
        stack.append((level, tag, name))
    return refs


def inner_info(raw):
    info = {"len": len(raw)}
    if len(raw) < 4:
        info["bad"] = "short"
        return info
    decl = struct.unpack_from("<I", raw)[0]
    info["prefix_ok"] = decl == len(raw) - 4
    body = raw[4:]
    if not body.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        info["bad"] = "nocfb"
        return info
    try:
        o = olefile.OleFileIO(body)
        info["clsid"] = o.root.clsid
        info["streams"] = sorted(
            "/".join(p) for p in o.listdir(streams=True, storages=False)
        )
        info["ooxml"] = o.exists("OOXMLChartContents")
        info["contents"] = o.exists("Contents")
        if info["ooxml"]:
            x = o.openstream("OOXMLChartContents").read()
            info["xml_len"] = len(x)
            info["xml_doctype"] = b"<!DOCTYPE" in x.upper()
        o.close()
    except Exception as e:
        info["bad"] = "olefail:%s" % type(e).__name__
    return info


def doc(path):
    rec = {"name": path.name}
    try:
        o = olefile.OleFileIO(str(path))
    except Exception as e:
        rec["open_fail"] = type(e).__name__
        return rec
    try:
        fh = o.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", fh, 36)[0]
        comp, dist = bool(flags & 1), bool(flags & 4)
        rec["compressed"] = comp
        rec["dist"] = dist
        rec["enc"] = bool(flags & 2)
        oles = [
            p
            for p in o.listdir()
            if len(p) == 2 and p[0] == "BinData" and p[1].upper().endswith(".OLE")
        ]
        rec["ole_count"] = len(oles)
        if not oles:
            return rec
        # DocInfo BIN_DATA entries
        di = o.openstream("DocInfo").read()
        if comp:
            di = inflate(di)
        entries = []
        for tag, level, data in records(di):
            if tag == T_BIN_DATA and len(data) >= 2:
                typ = struct.unpack_from("<H", data)[0] & 0xF
                bid = (
                    struct.unpack_from("<H", data, 2)[0]
                    if typ in (1, 2) and len(data) >= 4
                    else None
                )
                entries.append((typ, bid))
        rec["bin_entries"] = entries
        # OLE storages
        infos = {}
        for p in oles:
            sid = int(p[1].split(".")[0][3:], 16)
            raw = o.openstream(p).read()
            if comp:
                try:
                    raw = inflate(raw)
                except zlib.error:
                    infos[sid] = {"bad": "zlib"}
                    continue
            infos[sid] = inner_info(raw)
        rec["oles"] = {str(k): v for k, v in infos.items()}
        refs = []
        if not dist and not rec["enc"]:
            secs = sorted(
                (
                    p
                    for p in o.listdir()
                    if len(p) == 2 and p[0] == "BodyText" and p[1].startswith("Section")
                ),
                key=lambda p: int(p[1][7:]),
            )
            for p in secs:
                b = o.openstream(p).read()
                if comp:
                    b = inflate(b)
                refs.extend(walk_section(b))
        rec["refs"] = refs
    except Exception as e:
        rec["fail"] = "%s: %s" % (type(e).__name__, e)
    finally:
        o.close()
    return rec


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), sys.argv[2]
    files = sorted(p for p in src.iterdir() if p.suffix.lower() == ".hwp")
    with Pool(12) as pool, open(out, "w") as f:
        for r in pool.imap_unordered(doc, files, chunksize=8):
            if r.get("ole_count") or r.get("fail") or r.get("open_fail"):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("done", len(files))
