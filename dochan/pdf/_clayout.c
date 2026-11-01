/* Handwritten mirrors of layout.py. Also embedded in the table kernel so
 * cell assembly does not enter a Python wrapper per block. */
#ifndef Py_LIMITED_API
#define Py_LIMITED_API 0x03090000
#endif
#include <Python.h>
#include <math.h>
#include <string.h>

#ifdef CLAYOUT_EMBEDDED
#define ly_bailout ct_bailout
#else
static PyObject *ly_bailout;
#endif
typedef struct { PyObject **v; Py_ssize_t n, cap; } LyPool;
static PyObject *ly_keep(LyPool *p, PyObject *v)
{
    if (!v) return NULL;
    if (p->n == p->cap) {
        Py_ssize_t cap = p->cap ? p->cap * 2 : 64;
        PyObject **items = PyMem_Realloc(p->v, (size_t)cap * sizeof(*items));
        if (!items) { Py_DECREF(v); return PyErr_NoMemory(); }
        p->v = items; p->cap = cap;
    }
    p->v[p->n++] = v; return v;
}
static PyObject *ly_done(LyPool *p, PyObject *v)
{
    Py_XINCREF(v);
    while (p->n) Py_DECREF(p->v[--p->n]);
    PyMem_Free(p->v); return v;
}
static PyObject *ly_bail(void)
{
    PyErr_SetString(ly_bailout ? ly_bailout : PyExc_ValueError, "unsupported layout input");
    return NULL;
}
#define LK(v, expr) do { (v) = ly_keep(&pool, (expr)); if (!(v)) goto done; } while (0)
#define LC(expr) do { if ((expr) < 0) goto done; } while (0)
static PyObject *ly_attr(PyObject *o, const char *name)
{
    static const char *names[32]; static PyObject *keys[32]; static int n;
    int i;
    for (i = 0; i < n; i++) if (!strcmp(names[i], name)) return PyObject_GetAttr(o, keys[i]);
    if (n < 32) {
        PyObject *key = PyUnicode_InternFromString(name);
        if (!key) return NULL;
        names[n] = name; keys[n++] = key; return PyObject_GetAttr(o, key);
    }
    return PyObject_GetAttrString(o, name);
}
static int ly_space(Py_UCS4 c)
{
    return (c >= 9 && c <= 13) || (c >= 28 && c <= 32) || c == 0x85 || c == 0xa0 ||
        c == 0x1680 || (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
        c == 0x202f || c == 0x205f || c == 0x3000;
}
static int ly_decimal(PyObject *text, Py_ssize_t i)
{
    Py_UCS4 c = PyUnicode_ReadChar(text, i);
    PyObject *one, *answer; int ok;
    if (c < 128) return c >= '0' && c <= '9';
    /* Unicode tables belong to the running interpreter, not the build headers. */
    one = PyUnicode_Substring(text, i, i + 1); if (!one) return -1;
    answer = PyObject_CallMethod(one, "isdecimal", NULL); Py_DECREF(one);
    if (!answer) return -1;
    ok = PyObject_IsTrue(answer); Py_DECREF(answer); return ok;
}
static int ly_number_span(PyObject *text, Py_ssize_t i, Py_ssize_t end)
{
    Py_UCS4 c; int ok;
    if (i == end) return 0;
    c = PyUnicode_ReadChar(text, i);
    if (c == '+' || c == '-' || c == 0x2212) i++;
    if (i == end) return 0;
    ok = ly_decimal(text, i++); if (ok <= 0) return ok;
    while (i < end) {
        c = PyUnicode_ReadChar(text, i);
        if (c == ',') { i++; continue; }
        ok = ly_decimal(text, i); if (ok < 0) return -1;
        if (!ok) break;
        i++;
    }
    if (i < end && PyUnicode_ReadChar(text, i) == '.') {
        i++; if (i == end) return 0;
        ok = ly_decimal(text, i++); if (ok <= 0) return ok;
        while (i < end) {
            ok = ly_decimal(text, i); if (ok < 0) return -1;
            if (!ok) break;
            i++;
        }
    }
    if (i < end && PyUnicode_ReadChar(text, i) == '%') i++;
    return i == end;
}
static int ly_numeric_text(PyObject *text)
{
    Py_ssize_t i = 0, start, n; int any = 0, ok;
    if (!PyUnicode_CheckExact(text)) { ly_bail(); return -1; }
    n = PyUnicode_GetLength(text);
    while (i < n) {
        while (i < n && ly_space(PyUnicode_ReadChar(text, i))) i++;
        start = i;
        while (i < n && !ly_space(PyUnicode_ReadChar(text, i))) i++;
        if (start == i) break;
        ok = ly_number_span(text, start, i); if (ok <= 0) return ok;
        any = 1;
    }
    return any;
}
static PyObject *ly_trim(PyObject *runs)
{
    LyPool pool = {0}; PyObject *out, *run, *text, *trim, *tuple, *result = NULL;
    Py_ssize_t lo = 0, hi, i, j, n, start, end;
    if (!PyList_CheckExact(runs) && !PyTuple_CheckExact(runs)) return ly_bail();
    n = PySequence_Size(runs); hi = n;
    LK(out, PyList_New(0));
    for (i = 0; i < n; i++) {
        LK(run, PySequence_GetItem(runs, i));
        if (!PyTuple_CheckExact(run) || PyTuple_Size(run) < 1 ||
                !PyUnicode_CheckExact(PyTuple_GetItem(run, 0))) { ly_bail(); goto done; }
    }
    while (lo < hi) {
        LK(run, PySequence_GetItem(runs, lo)); text = PyTuple_GetItem(run, 0);
        end = PyUnicode_GetLength(text); start = 0;
        while (start < end && ly_space(PyUnicode_ReadChar(text, start))) start++;
        if (start < end) break;
        lo++;
    }
    while (hi > lo) {
        LK(run, PySequence_GetItem(runs, hi - 1)); text = PyTuple_GetItem(run, 0);
        end = PyUnicode_GetLength(text);
        while (end && ly_space(PyUnicode_ReadChar(text, end - 1))) end--;
        if (end) break;
        hi--;
    }
    for (i = lo; i < hi; i++) {
        LK(run, PySequence_GetItem(runs, i)); text = PyTuple_GetItem(run, 0);
        if (i != lo && i != hi - 1) { LC(PyList_Append(out, run)); continue; }
        start = 0; end = PyUnicode_GetLength(text);
        if (i == lo) while (start < end && ly_space(PyUnicode_ReadChar(text, start))) start++;
        if (i == hi - 1) while (end > start && ly_space(PyUnicode_ReadChar(text, end - 1))) end--;
        LK(trim, PyUnicode_Substring(text, start, end));
        LK(tuple, PyTuple_New(PyTuple_Size(run)));
        Py_INCREF(trim); LC(PyTuple_SetItem(tuple, 0, trim));
        for (j = 1; j < PyTuple_Size(run); j++) {
            PyObject *v = PyTuple_GetItem(run, j); Py_INCREF(v); LC(PyTuple_SetItem(tuple, j, v));
        }
        LC(PyList_Append(out, tuple));
    }
    result = out;
done: return ly_done(&pool, result);
}
static PyObject *ly_paragraph(PyObject *block, PyObject *page, PyObject *layout)
{
    LyPool pool = {0}; PyObject *runs, *out, *provtype, *ptype, *rtype, *prov;
    PyObject *run, *value, *result = NULL, *zero, *minusone, *ten, *blank, *footnote, *pdf;
    Py_ssize_t i, n;
    LK(runs, ly_attr(block, "runs"));
    if (!PyList_CheckExact(runs) && !PyTuple_CheckExact(runs)) { ly_bail(); goto done; }
    LK(provtype, ly_attr(layout, "Provenance")); LK(ptype, ly_attr(layout, "Paragraph"));
    LK(rtype, ly_attr(layout, "TextRun")); LK(pdf, PyUnicode_FromString("pdf"));
    LK(prov, PyObject_CallFunctionObjArgs(provtype, pdf, page, NULL)); LK(out, PyList_New(0));
    LK(zero, PyLong_FromLong(0)); LK(minusone, PyLong_FromLong(-1)); LK(ten, PyFloat_FromDouble(10.0));
    LK(blank, PyUnicode_FromString("")); LK(footnote, PyUnicode_FromString("footnote"));
    n = PySequence_Size(runs);
    for (i = 0; i < n; i++) {
        PyObject *note, *kind; Py_ssize_t count; int hasnote, comment;
        LK(run, PySequence_GetItem(runs, i));
        if (!PyTuple_CheckExact(run) || (count = PyTuple_Size(run)) < 3) { ly_bail(); goto done; }
        note = count > 4 ? PyTuple_GetItem(run, 4) : zero;
        kind = count > 5 ? PyTuple_GetItem(run, 5) : footnote;
        hasnote = PyObject_IsTrue(note); LC(hasnote);
        comment = PyUnicode_Check(kind) ? PyUnicode_CompareWithASCIIString(kind, "comment") == 0 : 0;
        /* Positional dataclass field order: avoid allocating a keyword dictionary
         * and eight Unicode keys for every run. Defaults remain model values. */
        LK(value, PyObject_CallFunctionObjArgs(rtype,
            PyTuple_GetItem(run, 0), minusone, PyTuple_GetItem(run, 1), PyTuple_GetItem(run, 2),
            Py_False, Py_False, Py_False, Py_False, ten,
            count > 3 ? PyTuple_GetItem(run, 3) : blank,
            comment ? zero : note, prov, hasnote ? kind : blank,
            hasnote ? note : Py_None, Py_None, NULL));
        LC(PyList_Append(out, value));
    }
    LK(value, PyObject_CallFunctionObjArgs(ptype, out, minusone, minusone, zero, prov, NULL));
    result = value;
done: return ly_done(&pool, result);
}
static int ly_double(PyObject *o, const char *name, double *out)
{
    PyObject *v = ly_attr(o, name);
    if (!v) return -1;
    if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v)) { Py_DECREF(v); ly_bail(); return -1; }
    *out = PyFloat_AsDouble(v); Py_DECREF(v);
    if (PyErr_Occurred()) return -1;
    if (!isfinite(*out) || fabs(*out) > 67108864.) { ly_bail(); return -1; }
    return 0;
}
static double ly_odds(double p)
{ if (p < .01) p = .01; if (p > .99) p = .99; return p / (1 - p); }
static int ly_cjk(Py_UCS4 c)
{ return (c >= 0xac00 && c <= 0xd7a3) || (c >= 0x3400 && c <= 0x9fff) || (c >= 0xf900 && c <= 0xfaff); }
static int ly_join(PyObject *lasttext, PyObject *text, PyObject *layout)
{
    LyPool pool = {0}; PyObject *last, *first, *loader, *cls, *model, *pairs, *ls, *fs, *prior, *pair, *v;
    Py_UCS4 a, b; double p, l, f, odds; int result = -1;
    Py_ssize_t n = PyUnicode_GetLength(lasttext);
    if (!n || !PyUnicode_GetLength(text)) return 0;
    a = PyUnicode_ReadChar(lasttext, n - 1); b = PyUnicode_ReadChar(text, 0);
    LK(last, PyUnicode_Substring(lasttext, n - 1, n)); LK(first, PyUnicode_Substring(text, 0, 1));
    if (a >= 0xac00 && a <= 0xd7a3 && b >= 0xac00 && b <= 0xd7a3) {
        LK(loader, PyImport_ImportModule("dochan.pdf.spacing"));
        LK(cls, ly_attr(loader, "SpacingModel"));
        LK(model, ly_attr(loader, "_DEFAULT_MODEL"));
        if (model == Py_None) {
            LK(loader, ly_attr(layout, "load_model")); LK(model, PyObject_CallObject(loader, NULL));
        }
        /* joins_with_space 를 재정의한 하위 클래스는 표를 직접 읽을 수 없다 — Python 으로 */
        if ((PyObject *)Py_TYPE(model) != cls) { ly_bail(); goto done; }
        LK(pairs, ly_attr(model, "pairs")); LK(ls, ly_attr(model, "last")); LK(fs, ly_attr(model, "first"));
        LK(prior, ly_attr(model, "prior")); LK(pair, PyUnicode_Concat(last, first));
        if (!PyDict_CheckExact(pairs) || !PyDict_CheckExact(ls) || !PyDict_CheckExact(fs)) { ly_bail(); goto done; }
        v = PyDict_GetItemWithError(pairs, pair); if (PyErr_Occurred()) goto done;
        if (v) p = PyFloat_AsDouble(v);
        else {
            PyObject *lv = PyDict_GetItemWithError(ls, last), *fv = PyDict_GetItemWithError(fs, first);
            if (PyErr_Occurred()) goto done;
            p = PyFloat_AsDouble(prior);
            if (lv || fv) {
                l = lv ? PyFloat_AsDouble(lv) : p; f = fv ? PyFloat_AsDouble(fv) : p;
                odds = ly_odds(l) * ly_odds(f) / ly_odds(p); p = odds / (1 + odds);
            }
        }
        if (PyErr_Occurred()) goto done;
        result = !(p > .5 + 1e-9);
    } else if (ly_cjk(a) && ly_cjk(b)) result = 1;
    else {
        LK(v, PyObject_CallMethod(last, "isdigit", NULL)); result = PyObject_IsTrue(v); LC(result);
        if (result && b != '.') { LK(v, PyObject_CallMethod(first, "isdigit", NULL)); result = PyObject_IsTrue(v); }
    }
done: ly_done(&pool, NULL); return result;
}
typedef struct { PyObject *line, *text; double left, right, y, size, first, last; int dir; } LyLine;
static PyObject *ly_merge(PyObject *lines, PyObject *bounds, PyObject *layout)
{
    LyPool pool = {0}; PyObject *out, *type, *observer, *marker, *v, *runs, *block = NULL, *blockruns = NULL;
    PyObject *blocklines = NULL, *blocktext = NULL, *args, *size, *order, *y, *result = NULL;
    LyLine *data = NULL, *previous = NULL;
    Py_ssize_t i, n; double edge[4] = {0}, origin[4] = {0}; int have[4] = {0};
    static const char *directions[] = {"ltr", "rtl", "down", "up"};
    if (!PyList_CheckExact(lines) && !PyTuple_CheckExact(lines)) return ly_bail();
    n = PySequence_Size(lines);
    LK(out, PyList_New(0)); if (!n) { result = out; goto done; }
    if (n > 1000000) { ly_bail(); goto done; }
    /* Most cells contain one already-assembled _Line. No join boundary or
     * arithmetic is needed: retain its original field objects directly. */
    if (n == 1) {
        static PyObject *line_type;
        PyObject *line, *actual;
        if (!line_type) {
            LK(v, PyImport_ImportModule("dochan.pdf.content"));
            line_type = ly_attr(v, "_Line"); if (!line_type) goto done;
        }
        LK(line, PySequence_GetItem(lines, 0)); LK(actual, PyObject_Type(line));
        if (actual == line_type) {
            LK(blocktext, ly_attr(line, "text"));
            if (!PyUnicode_CheckExact(blocktext)) { ly_bail(); goto done; }
            if (!PyUnicode_GetLength(blocktext)) { result = out; goto done; }
            LK(v, ly_attr(line, "runs")); LK(blockruns, ly_trim(v));
            LK(blocklines, PyList_New(0)); LC(PyList_Append(blocklines, line));
            LK(size, ly_attr(line, "size")); LK(order, ly_attr(line, "order")); LK(y, ly_attr(line, "y"));
            LK(type, ly_attr(layout, "TextBlock"));
            LK(args, PyTuple_Pack(6, blocktext, size, order, blockruns, y, blocklines));
            LK(block, PyObject_CallObject(type, args)); LC(PyList_Append(out, block));
            result = out; goto done;
        }
    }
    data = PyMem_Malloc((size_t)n * sizeof(*data)); if (!data) { PyErr_NoMemory(); goto done; }
    memset(data, 0, (size_t)n * sizeof(*data));
    LK(type, ly_attr(layout, "TextBlock")); LK(observer, ly_attr(layout, "JOIN_OBSERVER"));
    if (observer != Py_None) { ly_bail(); goto done; }
    LK(v, ly_attr(layout, "_joins_without_space"));
    { PyObject *original; LK(original, ly_attr(layout, "_original_join"));
      if (v != original) { ly_bail(); goto done; } }
    LK(v, ly_attr(layout, "load_model"));
    { PyObject *original; LK(original, ly_attr(layout, "_original_load_model"));
      if (v != original) { ly_bail(); goto done; } }
    LK(marker, ly_attr(layout, "_BLOCK_MARKER"));
    for (i = 0; i < n; i++) {
        LyLine *l = data + i; int d;
        LK(l->line, PySequence_GetItem(lines, i)); LK(l->text, ly_attr(l->line, "text"));
        if (!PyUnicode_CheckExact(l->text)) { ly_bail(); goto done; }
        LK(v, ly_attr(l->line, "direction"));
        if (!PyUnicode_CheckExact(v)) { ly_bail(); goto done; }
        for (d = 0; d < 4; d++) if (!PyUnicode_CompareWithASCIIString(v, directions[d])) break;
        if (d == 4) { ly_bail(); goto done; }
        l->dir = d;
        LC(ly_double(l->line, "left", &l->left)); LC(ly_double(l->line, "right", &l->right));
        LC(ly_double(l->line, "y", &l->y)); LC(ly_double(l->line, "size", &l->size));
        LC(ly_double(l->line, "first_size", &l->first)); LC(ly_double(l->line, "last_size", &l->last));
        if (!have[d] || l->right > edge[d]) edge[d] = l->right;
        if (!have[d] || l->left < origin[d]) origin[d] = l->left;
        have[d] = 1;
    }
    edge[0] *= .90;
    if (bounds != Py_None && n >= 2) {
        double left, right;
        if ((!PyTuple_CheckExact(bounds) && !PyList_CheckExact(bounds)) || PySequence_Size(bounds) != 2) {
            ly_bail(); goto done;
        }
        LK(v, PySequence_GetItem(bounds, 0));
        if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v)) { ly_bail(); goto done; }
        left = PyFloat_AsDouble(v);
        LK(v, PySequence_GetItem(bounds, 1));
        if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v)) { ly_bail(); goto done; }
        right = PyFloat_AsDouble(v);
        if (PyErr_Occurred()) goto done;
        if (!isfinite(left) || !isfinite(right) || fabs(left) > 67108864. || fabs(right) > 67108864.) { ly_bail(); goto done; }
        edge[0] = left + .90 * (right - left);
    }
    for (i = 1; i < 4; i++) if (have[i]) edge[i] = origin[i] + .90 * (edge[i] - origin[i]);
    for (i = 0; i < n; i++) {
        LyLine *l = data + i; int joins = 0;
        if (!PyUnicode_GetLength(l->text)) continue;
        if (previous && previous->dir == l->dir && previous->right >= edge[l->dir] &&
                (!l->dir || l->right >= edge[l->dir]) && previous->y - l->y > 0 &&
                previous->y - l->y <= 1.8 * previous->size && .85 * previous->last <= l->first &&
                l->first <= 1.15 * previous->last) {
            LK(v, PyObject_CallMethod(marker, "match", "O", l->text));
            joins = !PyObject_IsTrue(v);
        }
        LK(v, ly_attr(l->line, "runs")); LK(runs, ly_trim(v));
        if (joins) {
            int sep; PyObject *separator, *joined;
            LK(v, ly_attr(previous->line, "trailing_space")); sep = PyObject_IsTrue(v); LC(sep);
            if (!sep) { int no = ly_join(blocktext, l->text, layout); LC(no); sep = !no; }
            LK(separator, PyUnicode_FromString(sep ? " " : "")); LK(joined, PyUnicode_Concat(separator, l->text));
            LK(blocktext, PyUnicode_Concat(blocktext, joined)); LC(PyObject_SetAttrString(block, "text", blocktext));
            LC(PyList_Append(blocklines, l->line));
            if (sep) { LK(v, PyTuple_Pack(3, separator, Py_False, Py_False)); LC(PyList_Append(blockruns, v)); }
            LC(PyList_SetSlice(blockruns, PyList_Size(blockruns), PyList_Size(blockruns), runs));
        } else {
            blocktext = l->text; blockruns = runs;
            LK(blocklines, PyList_New(0)); LC(PyList_Append(blocklines, l->line));
            LK(size, ly_attr(l->line, "size")); LK(order, ly_attr(l->line, "order")); LK(y, ly_attr(l->line, "y"));
            LK(args, PyTuple_Pack(6, blocktext, size, order, blockruns, y, blocklines));
            LK(block, PyObject_CallObject(type, args)); LC(PyList_Append(out, block));
        }
        previous = l;
    }
    result = out;
done: PyMem_Free(data); return ly_done(&pool, result);
}
#ifndef CLAYOUT_EMBEDDED
static PyObject *ly_api_trim(PyObject *self, PyObject *runs)
{ (void)self; return ly_trim(runs); }
static PyObject *ly_api_number(PyObject *self, PyObject *text)
{
    int ok; (void)self;
    if (!PyUnicode_CheckExact(text)) return ly_bail();
    ok = ly_number_span(text, 0, PyUnicode_GetLength(text));
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok);
}
static PyObject *ly_api_numeric_text(PyObject *self, PyObject *text)
{
    int ok; (void)self; ok = ly_numeric_text(text);
    if (ok < 0) return NULL;
    return PyBool_FromLong(ok);
}
static PyObject *ly_api_merge(PyObject *self, PyObject *args)
{
    PyObject *lines, *bounds = Py_None, *layout, *result; (void)self;
    if (!PyArg_ParseTuple(args, "O|O", &lines, &bounds)) return NULL;
    layout = PyImport_ImportModule("dochan.pdf.layout"); if (!layout) return NULL;
    result = ly_merge(lines, bounds, layout); Py_DECREF(layout); return result;
}
static PyObject *ly_api_paragraph(PyObject *self, PyObject *args)
{
    PyObject *block, *page = Py_None, *layout, *result; (void)self;
    if (!PyArg_ParseTuple(args, "O|O", &block, &page)) return NULL;
    layout = PyImport_ImportModule("dochan.pdf.layout"); if (!layout) return NULL;
    result = ly_paragraph(block, page, layout); Py_DECREF(layout); return result;
}
static PyMethodDef ly_methods[] = {
    {"merge_lines", ly_api_merge, METH_VARARGS, NULL},
    {"paragraph", ly_api_paragraph, METH_VARARGS, NULL},
    {"trim_runs", ly_api_trim, METH_O, NULL},
    {"numeric_text", ly_api_numeric_text, METH_O, NULL},
    {"number", ly_api_number, METH_O, NULL}, {NULL, NULL, 0, NULL}
};
static struct PyModuleDef ly_module = {
    PyModuleDef_HEAD_INIT, "_clayout", NULL, -1, ly_methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__clayout(void)
{
    PyObject *m = PyModule_Create(&ly_module); if (!m) return NULL;
    ly_bailout = PyErr_NewException("dochan.pdf._clayout.Bailout", NULL, NULL);
    if (!ly_bailout || PyModule_AddObject(m, "Bailout", ly_bailout) < 0) { Py_XDECREF(ly_bailout); Py_DECREF(m); return NULL; }
    return m;
}
#endif
#undef LK
#undef LC

#ifdef CLAYOUT_EMBEDDED
#undef ly_bailout
#endif
