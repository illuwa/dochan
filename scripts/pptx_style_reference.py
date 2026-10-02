"""Reviewer's independent PPTX inheritance resolver for b/i/u/sz/baseline (placeholders + text boxes)."""

import zipfile
import posixpath
from lxml import etree

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PARSER = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def rels(z, part):
    d, f = posixpath.split(part)
    rp = posixpath.join(d, "_rels", f + ".rels")
    out = {}
    if rp in z.namelist():
        for r in etree.fromstring(z.read(rp), PARSER):
            if r.get("TargetMode") == "External":
                continue
            out[r.get("Id")] = (
                r.get("Type").rsplit("/", 1)[-1],
                posixpath.normpath(posixpath.join(d, r.get("Target"))),
            )
    return out


def rpr_props(el):
    out = {}
    if el is None:
        return out
    for k in ("b", "i"):
        if el.get(k) is not None:
            out[k] = el.get(k) in ("1", "true")
    if el.get("u") is not None:
        out["u"] = el.get("u") != "none"
    if el.get("sz") is not None:
        out["sz"] = int(el.get("sz")) / 100
    if el.get("baseline") is not None:
        out["base"] = int(el.get("baseline"))
    return out


def lvl_props(lst, lvl):
    if lst is None:
        return {}
    e = lst.find(A + "lvl%dpPr" % (lvl + 1))
    if e is None:
        return {}
    return rpr_props(e.find(A + "defRPr"))


def ph_of(sp):
    ph = sp.find(".//" + P + "nvPr/" + P + "ph")
    if ph is None:
        return None
    return (ph.get("type", "body"), ph.get("idx", "0"))


def find_ph(tree, ph):
    if tree is None or ph is None:
        return None
    typ, idx = ph
    cands = [sp for sp in tree.iter(P + "sp") if ph_of(sp) is not None]
    for sp in cands:
        if ph_of(sp)[1] == idx and idx != "0":
            return sp

    def norm(t):
        return {"ctrTitle": "title", "subTitle": "body", "obj": "body"}.get(t, t)

    for sp in cands:
        if norm(ph_of(sp)[0]) == norm(typ):
            return sp
    return None


def pptx_paragraphs(path):
    with zipfile.ZipFile(path) as z:
        if (
            len(z.infolist()) > 100000
            or sum(i.file_size for i in z.infolist()) > 256 * 1024 * 1024
        ):
            raise ValueError("PPTX verification archive limit exceeded")
        return _paragraphs(z)


def _paragraphs(z):
    pres = etree.fromstring(z.read("ppt/presentation.xml"), PARSER)
    prels = rels(z, "ppt/presentation.xml")
    deflt = pres.find(P + "defaultTextStyle")
    slides = [prels[s.get(R + "id")][1] for s in pres.find(P + "sldIdLst")]
    result = []
    for n, sl in enumerate(slides, 1):
        st = etree.fromstring(z.read(sl), PARSER)
        lay = [t for k, t in rels(z, sl).values() if k == "slideLayout"][0]
        lt = etree.fromstring(z.read(lay), PARSER)
        mas = [t for k, t in rels(z, lay).values() if k == "slideMaster"][0]
        mt = etree.fromstring(z.read(mas), PARSER)
        tx = mt.find(P + "txStyles")
        for sp in st.iter(P + "sp"):
            body = sp.find(P + "txBody")
            if body is None:
                continue
            ph = ph_of(sp)
            if ph is None:
                chain_lists = [deflt, None]
                kind = "other"
            else:
                t = ph[0]
                style = (
                    tx.find(
                        P
                        + (
                            "titleStyle"
                            if t in ("title", "ctrTitle")
                            else "bodyStyle"
                            if t in ("body", "subTitle", "obj")
                            else "otherStyle"
                        )
                    )
                    if tx is not None
                    else None
                )
                msp = find_ph(mt, ph)
                lsp = find_ph(lt, ph)
                chain_lists = [
                    style,
                    msp.find(P + "txBody/" + A + "lstStyle")
                    if msp is not None
                    else None,
                    lsp.find(P + "txBody/" + A + "lstStyle")
                    if lsp is not None
                    else None,
                ]
                kind = t
            chain_lists.append(body.find(A + "lstStyle"))
            for para in body.findall(A + "p"):
                ppr = para.find(A + "pPr")
                lvl = int(ppr.get("lvl", "0")) if ppr is not None else 0
                base = {}
                for style_list in chain_lists:
                    base.update(lvl_props(style_list, lvl))
                if ppr is not None:
                    base.update(rpr_props(ppr.find(A + "defRPr")))
                runs = []
                for r in para:
                    if r.tag == A + "r":
                        props = dict(base)
                        props.update(rpr_props(r.find(A + "rPr")))
                        runs.append((r.findtext(A + "t") or "", props))
                    elif r.tag == A + "br":
                        runs.append(("\n", dict(base)))
                    elif r.tag == A + "fld":
                        props = dict(base)
                        props.update(rpr_props(r.find(A + "rPr")))
                        runs.append((r.findtext(A + "t") or "", props))
                result.append((n, kind, "".join(t for t, _ in runs), runs))
    return result
