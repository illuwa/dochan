/* Handwritten mirrors of tables.py geometry. All allocations are call-local. */
#include <math.h>
#include <stdlib.h>

typedef struct { PyObject **items; Py_ssize_t size, cap; } GeoPool;
static PyObject *geo_keep(GeoPool *p, PyObject *o)
{
    PyObject **v;
    if (!o) return NULL;
    if (p->size == p->cap) {
        Py_ssize_t cap = p->cap ? p->cap * 2 : 32;
        v = PyMem_Realloc(p->items, (size_t)cap * sizeof(*v));
        if (!v) { Py_DECREF(o); PyErr_NoMemory(); return NULL; }
        p->items = v; p->cap = cap;
    }
    p->items[p->size++] = o;
    return o;
}
static PyObject *geo_finish(GeoPool *p, PyObject *o)
{
    Py_ssize_t i;
    Py_XINCREF(o);
    for (i = p->size; i > 0; i--) Py_DECREF(p->items[i - 1]);
    PyMem_Free(p->items);
    return o;
}
#define GK(v, expr) do { (v) = geo_keep(&pool, (expr)); if (!(v)) goto done; } while (0)
#define GC(expr) do { if ((expr) < 0) goto done; } while (0)
#define GI(seq, i) PyTuple_GetItem((seq), (i))
static PyObject *geo_sorted(PyObject *o)
{
    PyObject *v = PySequence_List(o);
    if (v && PyList_Sort(v) < 0) Py_CLEAR(v);
    return v;
}
static int geo_double(PyObject *o, double *out)
{
    if (!o) return -1;
    if (!PyFloat_CheckExact(o) && !PyLong_CheckExact(o)) {
        PyErr_SetString(ct_bailout, "nonstandard table coordinate"); return -1;
    }
    *out = PyFloat_AsDouble(o);
    if (PyErr_Occurred()) {
        if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
            PyErr_Clear(); PyErr_SetString(ct_bailout, "coordinate requires Python arithmetic");
        }
        return -1;
    }
    if (!isfinite(*out) || fabs(*out) > 1e100 ||
            (PyLong_CheckExact(o) && fabs(*out) > 9007199254740991.0)) {
        PyErr_SetString(ct_bailout, "nonfinite table coordinate"); return -1;
    }
    return 0;
}
/* Reject foreign shapes before borrowed tuple/list access. */
static int geo_vector(PyObject *value)
{
    Py_ssize_t i, n; double ignored;
    if (!PyList_CheckExact(value)) goto unsupported;
    n = PyList_Size(value);
    for (i = 0; i < n; i++) if (geo_double(PyList_GetItem(value, i), &ignored) < 0) return -1;
    return 0;
unsupported:
    PyErr_SetString(ct_bailout, "table vector requires an exact list"); return -1;
}
static int geo_rules(PyObject *value, Py_ssize_t width)
{
    Py_ssize_t i, j, n; double ignored;
    if (!PyList_CheckExact(value)) goto unsupported;
    n = PyList_Size(value);
    for (i = 0; i < n; i++) {
        PyObject *row = PyList_GetItem(value, i);
        if (!PyTuple_CheckExact(row) || PyTuple_Size(row) != width) goto unsupported;
        for (j = 0; j < width; j++) if (geo_double(PyTuple_GetItem(row, j), &ignored) < 0) return -1;
    }
    return 0;
unsupported:
    PyErr_SetString(ct_bailout, "table rules require exact coordinate tuples"); return -1;
}
static Py_ssize_t geo_find(Py_ssize_t *parents, Py_ssize_t a)
{
    while (parents[a] != a) { parents[a] = parents[parents[a]]; a = parents[a]; }
    return a;
}
static void geo_join(Py_ssize_t *parents, Py_ssize_t *sizes, Py_ssize_t a, Py_ssize_t b)
{
    Py_ssize_t tmp;
    a = geo_find(parents, a); b = geo_find(parents, b);
    if (a == b) return;
    if (sizes[a] < sizes[b]) { tmp = a; a = b; b = tmp; }
    parents[b] = a; sizes[a] += sizes[b];
}
static PyObject *geo_bucket(PyObject *dict, PyObject *key)
{
    PyObject *v = PyDict_GetItemWithError(dict, key);
    if (v || PyErr_Occurred()) return v;
    v = PyList_New(0);
    if (!v) return NULL;
    if (PyDict_SetItem(dict, key, v) < 0) { Py_DECREF(v); return NULL; }
    Py_DECREF(v);
    return PyDict_GetItemWithError(dict, key);
}
static PyObject *geo_tables_attr(const char *name)
{
    PyObject *m = PyImport_ImportModule("dochan.pdf.tables"), *value;
    if (!m) return NULL;
    value = PyObject_GetAttrString(m, name); Py_DECREF(m); return value;
}
static PyObject *ct_snap_runs(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *input, *tol, *lines, *out, *res = NULL;
    PyObject *sum, *coord, *spans, *start, *end, *item, *next, *lenobj, *values, *sumfunc;
    Py_ssize_t i, j, k, n; double tolerance, a, b;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO", &input, &tol)) return NULL;
    GC(geo_rules(input, 3)); GC(geo_double(tol, &tolerance)); GK(lines, geo_sorted(input)); GK(out, PyList_New(0));
    n = PyList_Size(lines);
    for (i = 0; i < n; i = j) {
        GC(geo_double(GI(PyList_GetItem(lines, i), 0), &a));
        for (j = i + 1; j < n; j++) {
            GC(geo_double(GI(PyList_GetItem(lines, j), 0), &b));
            if (b - a > tolerance) break;
        }
        GK(values, PyList_New(0)); GK(spans, PyList_New(0));
        for (k = i; k < j; k++) {
            item = PyList_GetItem(lines, k);
            GC(PyList_Append(values, GI(item, 0)));
            GK(next, PyTuple_Pack(2, GI(item, 1), GI(item, 2))); GC(PyList_Append(spans, next));
        }
        sumfunc = PyDict_GetItemString(PyEval_GetBuiltins(), "sum");
        if (!sumfunc) { PyErr_SetString(PyExc_RuntimeError, "sum is unavailable"); goto done; }
        GK(sum, PyObject_CallFunctionObjArgs(sumfunc, values, NULL));
        GK(lenobj, PyLong_FromSsize_t(j - i)); GK(coord, PyNumber_TrueDivide(sum, lenobj));
        GC(PyList_Sort(spans)); item = PyList_GetItem(spans, 0); start = GI(item, 0); end = GI(item, 1);
        for (k = 1; k < j - i; k++) {
            int cmp; item = PyList_GetItem(spans, k);
            GK(next, PyNumber_Add(end, tol));
            cmp = PyObject_RichCompareBool(GI(item, 0), next, Py_LE); GC(cmp);
            if (cmp) {
                cmp = PyObject_RichCompareBool(GI(item, 1), end, Py_GT); GC(cmp);
                if (cmp) end = GI(item, 1);
            } else {
                GK(next, PyTuple_Pack(3, coord, start, end)); GC(PyList_Append(out, next));
                start = GI(item, 0); end = GI(item, 1);
            }
        }
        GK(next, PyTuple_Pack(3, coord, start, end)); GC(PyList_Append(out, next));
    }
    res = out;
done: return geo_finish(&pool, res);
}
static PyObject *ct_components(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *hs, *vs, *tol, *groups, *out, *res = NULL, *limit;
    PyObject *line, *key, *pair, *h, *v;
    Py_ssize_t nh, nv, i, j, lo, hi, mid, checks = 0, maxchecks, root;
    Py_ssize_t *parents = NULL, *sizes = NULL; double *xs = NULL;
    double tolerance, y, left, right, bottom, top;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOO", &hs, &vs, &tol)) return NULL;
    GC(geo_rules(hs, 3)); GC(geo_rules(vs, 3));
    GC(geo_double(tol, &tolerance)); nh = PyList_Size(hs); nv = PyList_Size(vs); GC(nh); GC(nv);
    GK(limit, geo_tables_attr("MAX_INTERSECTION_CHECKS")); maxchecks = PyLong_AsSsize_t(limit);
    if (PyErr_Occurred()) goto done;
    parents = PyMem_Malloc((size_t)(nh + nv + 1) * sizeof(*parents));
    sizes = PyMem_Malloc((size_t)(nh + nv + 1) * sizeof(*sizes));
    xs = PyMem_Malloc((size_t)(nv + 1) * sizeof(*xs));
    if (!parents || !sizes || !xs) { PyErr_NoMemory(); goto done; }
    for (i = 0; i < nh + nv; i++) { parents[i] = i; sizes[i] = 1; }
    for (i = 0; i < nv; i++) GC(geo_double(GI(PyList_GetItem(vs, i), 0), &xs[i]));
    for (i = 0; i < nh; i++) {
        line = PyList_GetItem(hs, i);
        GC(geo_double(GI(line, 0), &y)); GC(geo_double(GI(line, 1), &left)); GC(geo_double(GI(line, 2), &right));
        lo = 0; hi = nv;
        while (lo < hi) { mid = (lo + hi) / 2; if (xs[mid] < left - tolerance) lo = mid + 1; else hi = mid; }
        j = lo; hi = nv;
        while (lo < hi) { mid = (lo + hi) / 2; if (right + tolerance < xs[mid]) hi = mid; else lo = mid + 1; }
        checks += lo - j;
        if (checks > maxchecks) { res = Py_None; goto done; }
        for (; j < lo; j++) {
            line = PyList_GetItem(vs, j);
            GC(geo_double(GI(line, 1), &bottom)); GC(geo_double(GI(line, 2), &top));
            if (bottom - tolerance <= y && y <= top + tolerance) geo_join(parents, sizes, i, nh + j);
        }
    }
    GK(groups, PyDict_New());
    for (i = 0; i < nh + nv; i++) {
        root = geo_find(parents, i); GK(key, PyLong_FromSsize_t(root)); pair = PyDict_GetItemWithError(groups, key);
        if (!pair) {
            if (PyErr_Occurred()) goto done;
            GK(h, PyList_New(0)); GK(v, PyList_New(0)); GK(pair, PyTuple_Pack(2, h, v)); GC(PyDict_SetItem(groups, key, pair));
        }
        GC(PyList_Append(GI(pair, i < nh ? 0 : 1), PyList_GetItem(i < nh ? hs : vs, i < nh ? i : i - nh)));
    }
    GK(out, PyDict_Values(groups)); res = out;
done: PyMem_Free(parents); PyMem_Free(sizes); PyMem_Free(xs); return geo_finish(&pool, res);
}
static int geo_covered(PyObject *runs, double lo, double hi, double tolerance)
{
    Py_ssize_t i, n = PyList_Size(runs); double coverage, a, b, value;
    PyObject *values = NULL, *number = NULL, *sum = NULL, *sumfunc;
    int result = -1;
    if (n < 0) return -1;
    if (!n) return 0 >= (hi - lo) * 0.5;
    if (n == 1) {
        PyObject *run = PyList_GetItem(runs, 0);
        if (geo_double(GI(run, 0), &a) < 0 || geo_double(GI(run, 1), &b) < 0) return -1;
        b += tolerance; a -= tolerance;
        value = (b < hi ? b : hi) - (a > lo ? a : lo);
        return (value > 0 ? value : 0) >= (hi - lo) * 0.5;
    }
    values = PyList_New(n); if (!values) return -1;
    for (i = 0; i < n; i++) {
        PyObject *run = PyList_GetItem(runs, i);
        if (geo_double(GI(run, 0), &a) < 0 || geo_double(GI(run, 1), &b) < 0) goto done;
        b += tolerance; a -= tolerance;
        value = (b < hi ? b : hi) - (a > lo ? a : lo);
        number = value > 0 ? PyFloat_FromDouble(value) : PyLong_FromLong(0);
        if (!number) goto done;
        if (PyList_SetItem(values, i, number) < 0) goto done;
    }
    sumfunc = PyDict_GetItemString(PyEval_GetBuiltins(), "sum");
    if (!sumfunc) { PyErr_SetString(PyExc_RuntimeError, "sum is unavailable"); goto done; }
    sum = PyObject_CallFunctionObjArgs(sumfunc, values, NULL); if (!sum) goto done;
    coverage = PyFloat_AsDouble(sum); if (PyErr_Occurred()) goto done;
    result = coverage >= (hi - lo) * 0.5;
done:
    Py_XDECREF(sum); Py_DECREF(values); return result;
}
static PyObject *ct_covered(PyObject *self, PyObject *args)
{
    PyObject *runs; double lo, hi, tolerance; int ok; (void)self;
    if (!PyArg_ParseTuple(args, "Oddd", &runs, &lo, &hi, &tolerance)) return NULL;
    if (geo_rules(runs, 2) < 0) return NULL;
    ok = geo_covered(runs, lo, hi, tolerance); return ok < 0 ? NULL : PyBool_FromLong(ok);
}
static PyObject *ct_rectangles(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *indices, *ordered, *out, *item, *res = NULL;
    Py_ssize_t cols, n, i, r0, r1, c0, c1, index, r, c, start, end, row;
    (void)self;
    if (!PyArg_ParseTuple(args, "On", &indices, &cols)) return NULL;
    if (cols <= 0) { PyErr_SetString(ct_bailout, "invalid column count"); return NULL; }
    GC(geo_vector(indices)); GK(ordered, geo_sorted(indices)); n = PyList_Size(ordered);
    if (!n) { PyErr_SetString(ct_bailout, "empty region"); goto done; }
    GK(out, PyList_New(0)); r0 = r1 = c0 = c1 = 0;
    for (i = 0; i < n; i++) {
        index = PyLong_AsSsize_t(PyList_GetItem(ordered, i)); if (PyErr_Occurred()) goto done;
        if (index < 0) { PyErr_SetString(ct_bailout, "negative region"); goto done; }
        r = index / cols; c = index % cols;
        if (!i) { r0 = r1 = r; c0 = c1 = c; }
        if (r < r0) r0 = r;
        if (r > r1) r1 = r;
        if (c < c0) c0 = c;
        if (c > c1) c1 = c;
    }
    if (n == (r1 - r0 + 1) * (c1 - c0 + 1)) {
        GK(item, Py_BuildValue("(nnnn)", r0, c0, r1 + 1, c1 + 1)); GC(PyList_Append(out, item));
    } else {
        index = PyLong_AsSsize_t(PyList_GetItem(ordered, 0)); row = index / cols; start = end = index % cols;
        for (i = 1; i <= n; i++) {
            index = i < n ? PyLong_AsSsize_t(PyList_GetItem(ordered, i)) : -1;
            r = index / cols; c = index % cols;
            if (i == n || r != row || c != end + 1) {
                GK(item, Py_BuildValue("(nnnn)", row, start, row + 1, end + 1)); GC(PyList_Append(out, item));
                start = c; row = r;
            }
            end = c;
        }
    }
    res = out;
done: return geo_finish(&pool, res);
}
static PyObject *ct_inside(PyObject *self, PyObject *args)
{
    PyObject *inner, *outer; int i, ok; static const int lhs[] = {0, 1, 2, 3}; (void)self;
    if (!PyArg_ParseTuple(args, "OO", &inner, &outer)) return NULL;
    if (!PyTuple_CheckExact(inner) || PyTuple_Size(inner) != 4 || !PyTuple_CheckExact(outer) || PyTuple_Size(outer) != 4) {
        PyErr_SetString(ct_bailout, "bbox requires four coordinates"); return NULL;
    }
    for (i = 0; i < 4; i++) {
        PyObject *a = GI(i < 2 ? outer : inner, lhs[i]), *b = GI(i < 2 ? inner : outer, lhs[i]);
        if (!a || !b) return NULL;
        ok = PyObject_RichCompareBool(a, b, Py_LE); if (ok < 0) return NULL;
        if (!ok) Py_RETURN_FALSE;
    }
    Py_RETURN_TRUE;
}
static PyObject *ct_shared_extent(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *values, *ordered, *res = NULL, *a, *b;
    double tolerance, x, y; int reverse; Py_ssize_t i, n; (void)self;
    if (!PyArg_ParseTuple(args, "Odp", &values, &tolerance, &reverse)) return NULL;
    GC(geo_vector(values)); GK(ordered, PySequence_List(values));
    if (reverse) {
        PyObject *method, *empty, *kwargs, *ignored;
        GK(method, PyObject_GetAttrString(ordered, "sort")); GK(empty, PyTuple_New(0));
        GK(kwargs, Py_BuildValue("{s:O}", "reverse", Py_True));
        GK(ignored, PyObject_Call(method, empty, kwargs));
    } else GC(PyList_Sort(ordered));
    n = PyList_Size(ordered);
    for (i = 0; i + 1 < n; i++) {
        a = PyList_GetItem(ordered, i); b = PyList_GetItem(ordered, i + 1);
        GC(geo_double(a, &x)); GC(geo_double(b, &y));
        if (fabs(x - y) <= tolerance) { res = a; goto done; }
    }
    res = Py_None;
done: return geo_finish(&pool, res);
}
static PyObject *ct_extend_to_rule_extents(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *xs, *hs, *tol, *lefts, *rights, *a, *left, *right, *res = NULL;
    Py_ssize_t i, n; double tolerance, margin, x, y;
    if (!PyArg_ParseTuple(args, "OOO", &xs, &hs, &tol)) return NULL;
    GC(geo_vector(xs)); GC(geo_rules(hs, 3));
    GC(geo_double(tol, &tolerance)); margin = 4 * tolerance; if (margin < 6) margin = 6;
    GK(lefts, PyList_New(0)); GK(rights, PyList_New(0)); n = PyList_Size(hs); GC(n);
    for (i = 0; i < n; i++) {
        a = PyList_GetItem(hs, i); GC(PyList_Append(lefts, GI(a, 1))); GC(PyList_Append(rights, GI(a, 2)));
    }
    GK(a, PyTuple_Pack(3, lefts, tol, Py_False)); GK(left, ct_shared_extent(self, a));
    GK(a, PyTuple_Pack(3, rights, tol, Py_True)); GK(right, ct_shared_extent(self, a));
    if (left != Py_None) {
        GC(geo_double(PyList_GetItem(xs, 0), &x)); GC(geo_double(left, &y));
        if (x - y > margin) GC(PyList_Insert(xs, 0, left));
    }
    if (right != Py_None) {
        GC(geo_double(PyList_GetItem(xs, PyList_Size(xs) - 1), &x)); GC(geo_double(right, &y));
        if (y - x > margin) GC(PyList_Append(xs, right));
    }
    res = Py_None;
done: return geo_finish(&pool, res);
}
/* Cell's dataclass positional contract: paragraphs, row, col, spans,
 * provenance. Each call owns a fresh paragraph list, just like default_factory.
 * Avoid rebuilding five keyword strings and a dictionary for every grid cell. */
static PyObject *geo_cell(PyObject *type, Py_ssize_t row, Py_ssize_t col,
                          Py_ssize_t row_span, Py_ssize_t col_span, PyObject *provenance)
{
    PyObject *paragraphs = PyList_New(0), *args, *cell;
    if (!paragraphs) return NULL;
    args = Py_BuildValue("(OnnnnO)", paragraphs, row, col, row_span, col_span, provenance);
    Py_DECREF(paragraphs);
    if (!args) return NULL;
    cell = PyObject_CallObject(type, args);
    Py_DECREF(args);
    return cell;
}
static PyObject *ct_make_grid(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *hs, *vs, *xs, *ys, *page, *tol;
    PyObject *hr, *vr, *line, *span, *bucket, *regions, *key, *index, *indices;
    PyObject *celltype, *provtype, *provenance, *kwargs, *empty, *grid, *owners, *boxes, *row, *cell;
    PyObject *rects, *rect, *callargs, *box, *res = NULL;
    Py_ssize_t rows, cols, count, i, j, r, c, k, pos, r0, c0, r1, c1;
    Py_ssize_t *parents = NULL, *sizes = NULL; double tolerance, lo, hi; int covered;
    if (!PyArg_ParseTuple(args, "OOOOOO", &hs, &vs, &xs, &ys, &tol, &page)) return NULL;
    GC(geo_rules(hs, 3)); GC(geo_rules(vs, 3)); GC(geo_vector(xs)); GC(geo_vector(ys));
    GC(geo_double(tol, &tolerance)); cols = PyList_Size(xs) - 1; rows = PyList_Size(ys) - 1;
    if (cols < 0 || rows < 0 || cols > 100000 || rows > 100000 || (cols && rows > 1000000 / cols)) {
        PyErr_SetString(ct_bailout, "grid dimensions"); goto done;
    }
    count = rows * cols;
    parents = PyMem_Malloc((size_t)(count + 1) * sizeof(*parents)); sizes = PyMem_Malloc((size_t)(count + 1) * sizeof(*sizes));
    if (!parents || !sizes) { PyErr_NoMemory(); goto done; }
    for (i = 0; i < count; i++) { parents[i] = i; sizes[i] = 1; }
    GK(hr, PyDict_New()); GK(vr, PyDict_New());
    for (j = 0; j < 2; j++) {
        PyObject *rules = j ? vs : hs, *runs = j ? vr : hr;
        for (i = 0; i < PyList_Size(rules); i++) {
            line = PyList_GetItem(rules, i); bucket = geo_bucket(runs, GI(line, 0)); if (!bucket) goto done;
            GK(span, PyTuple_Pack(2, GI(line, 1), GI(line, 2))); GC(PyList_Append(bucket, span));
        }
    }
    for (r = 0; r < rows; r++) for (c = 0; c < cols; c++) {
        i = r * cols + c;
        if (c + 1 < cols) {
            bucket = geo_bucket(vr, PyList_GetItem(xs, c + 1)); if (!bucket) goto done;
            GC(geo_double(PyList_GetItem(ys, r + 1), &lo)); GC(geo_double(PyList_GetItem(ys, r), &hi));
            covered = geo_covered(bucket, lo, hi, tolerance); GC(covered);
            if (!covered) geo_join(parents, sizes, i, i + 1);
        }
        if (r + 1 < rows) {
            bucket = geo_bucket(hr, PyList_GetItem(ys, r + 1)); if (!bucket) goto done;
            GC(geo_double(PyList_GetItem(xs, c), &lo)); GC(geo_double(PyList_GetItem(xs, c + 1), &hi));
            covered = geo_covered(bucket, lo, hi, tolerance); GC(covered);
            if (!covered) geo_join(parents, sizes, i, i + cols);
        }
    }
    GK(regions, PyDict_New());
    for (i = 0; i < count; i++) {
        GK(key, PyLong_FromSsize_t(geo_find(parents, i))); bucket = geo_bucket(regions, key); if (!bucket) goto done;
        GK(index, PyLong_FromSsize_t(i)); GC(PyList_Append(bucket, index));
    }
    GK(celltype, geo_tables_attr("Cell")); GK(provtype, geo_tables_attr("Provenance")); GK(empty, PyTuple_New(0));
    GK(kwargs, Py_BuildValue("{s:s,s:O}", "source_format", "pdf", "page", page));
    GK(provenance, PyObject_Call(provtype, empty, kwargs)); GK(grid, PyList_New(0)); GK(owners, PyList_New(count)); GK(boxes, PyDict_New());
    for (i = 0; i < count; i++) { Py_INCREF(Py_None); GC(PyList_SetItem(owners, i, Py_None)); }
    for (r = 0; r < rows; r++) {
        GK(row, PyList_New(0)); GC(PyList_Append(grid, row));
        for (c = 0; c < cols; c++) {
            GK(cell, geo_cell(celltype, r, c, 0, 0, provenance)); GC(PyList_Append(row, cell));
        }
    }
    pos = 0;
    while (PyDict_Next(regions, &pos, &key, &indices)) {
        GK(callargs, Py_BuildValue("(On)", indices, cols)); GK(rects, ct_rectangles(self, callargs));
        for (i = 0; i < PyList_Size(rects); i++) {
            rect = PyList_GetItem(rects, i);
            r0 = PyLong_AsSsize_t(GI(rect, 0)); c0 = PyLong_AsSsize_t(GI(rect, 1));
            r1 = PyLong_AsSsize_t(GI(rect, 2)); c1 = PyLong_AsSsize_t(GI(rect, 3));
            if (PyErr_Occurred()) goto done;
            GK(cell, geo_cell(celltype, r0, c0, r1 - r0, c1 - c0, provenance));
            row = PyList_GetItem(grid, r0); Py_INCREF(cell); GC(PyList_SetItem(row, c0, cell));
            GK(key, PyLong_FromSsize_t(r0 * cols + c0));
            GK(box, PyTuple_Pack(4, PyList_GetItem(xs, c0), PyList_GetItem(ys, r1), PyList_GetItem(xs, c1), PyList_GetItem(ys, r0)));
            GC(PyDict_SetItem(boxes, key, box));
            for (r = r0; r < r1; r++) for (c = c0; c < c1; c++) {
                k = r * cols + c; Py_INCREF(key); GC(PyList_SetItem(owners, k, key));
            }
        }
    }
    GK(res, PyTuple_Pack(3, grid, owners, boxes));
done: PyMem_Free(parents); PyMem_Free(sizes); return geo_finish(&pool, res);
}
static Py_ssize_t geo_bisect(PyObject *values, double needle, int right, int reverse)
{
    Py_ssize_t lo = 0, n = PyList_Size(values), hi = n, mid; double value;
    if (n < 0) return -1;
    while (lo < hi) {
        mid = (lo + hi) / 2;
        if (geo_double(PyList_GetItem(values, reverse ? n - 1 - mid : mid), &value) < 0) return -1;
        if (right ? needle < value : value >= needle) hi = mid; else lo = mid + 1;
    }
    return lo;
}
static PyObject *ct_owner_region(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *bbox, *parent, *xs, *ys, *owners, *boxes, *key = NULL, *current, *box, *a, *inside, *res = NULL;
    double left, bottom, right, top; Py_ssize_t cs[2], rs[2], i, j, cols, rows, b;
    if (!PyArg_ParseTuple(args, "OO", &bbox, &parent)) return NULL;
    if (!PyTuple_CheckExact(bbox) || PyTuple_Size(bbox) != 4) { PyErr_SetString(ct_bailout, "bbox requires four coordinates"); goto done; }
    GC(geo_double(GI(bbox, 0), &left)); GC(geo_double(GI(bbox, 1), &bottom));
    GC(geo_double(GI(bbox, 2), &right)); GC(geo_double(GI(bbox, 3), &top));
    GK(xs, PyObject_GetAttrString(parent, "xs")); GK(ys, PyObject_GetAttrString(parent, "ys"));
    GK(owners, PyObject_GetAttrString(parent, "owners")); GK(boxes, PyObject_GetAttrString(parent, "boxes"));
    GC(geo_vector(xs)); GC(geo_vector(ys)); GC(geo_vector(owners));
    cols = PyList_Size(xs) - 1; rows = PyList_Size(ys) - 1;
    b = geo_bisect(xs, left, 1, 0); GC(b); cs[0] = b - 1;
    b = geo_bisect(xs, right, 0, 0); GC(b); cs[1] = b - 1;
    b = geo_bisect(ys, bottom, 1, 1); GC(b); rs[0] = rows - b;
    b = geo_bisect(ys, top, 0, 1); GC(b); rs[1] = rows - b;
    for (i = 0; i < 2; i++) if (cs[i] < 0 || cs[i] >= cols || rs[i] < 0 || rs[i] >= rows) { res = Py_None; goto done; }
    for (i = 0; i < 2; i++) for (j = 0; j < 2; j++) {
        int equal;
        current = PyList_GetItem(owners, rs[i] * cols + cs[j]); if (!current) goto done;
        if (!key) key = current;
        equal = PyObject_RichCompareBool(key, current, Py_EQ); GC(equal);
        if (!equal) { res = Py_None; goto done; }
    }
    box = PyDict_GetItemWithError(boxes, key);
    if (!box) { if (!PyErr_Occurred()) PyErr_SetObject(PyExc_KeyError, key); goto done; }
    GK(a, PyTuple_Pack(2, bbox, box)); GK(inside, ct_inside(self, a));
    res = inside == Py_True ? key : Py_None;
done: return geo_finish(&pool, res);
}
static int geo_isclose(double a, double b)
{
    double delta;
    if (a == b) return 1;
    if (!isfinite(a) || !isfinite(b)) return 0;
    delta = fabs(b - a);
    return delta <= fabs(1e-9 * b) || delta <= fabs(1e-9 * a) || delta <= 1e-7;
}
static PyObject *ct_short_dash_runs(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *segments, *axes, *result, *h, *v, *segment, *x0, *x1, *y0, *y1, *segment_type;
    PyObject *axis, *coord, *key, *parts, *part, *ordered, *bucket, *span, *loobj, *hiobj, *startobj = NULL, *endobj = NULL, *res = NULL;
    PyObject *collections, *defaultdict, *listtype;
    PyObject *name_x0, *name_x1, *name_y0, *name_y1, *axis_h, *axis_v;
    Py_ssize_t i, j, n, pos, iter_start, run = 0; double tolerance, len, lo, hi, ax, bx, ay, by, prev_hi = 0, first_len = 0, gap = 0; int has_gap, equal, cmp;
    (void)self;
    if (!PyArg_ParseTuple(args, "Od", &segments, &tolerance)) return NULL;
    GK(collections, PyImport_ImportModule("collections")); GK(defaultdict, PyObject_GetAttrString(collections, "defaultdict"));
    GK(part, PyList_New(0)); GK(listtype, PyObject_Type(part));
    GK(axes, PyDict_New()); GK(h, PyObject_CallFunctionObjArgs(defaultdict, listtype, NULL));
    GK(v, PyObject_CallFunctionObjArgs(defaultdict, listtype, NULL)); GK(result, Py_BuildValue("{s:O,s:O}", "h", h, "v", v));
    if (segments == Py_None) { res = result; goto done; }
    n = PyList_Size(segments); GC(n); GK(segment_type, geo_tables_attr("Segment"));
    GK(name_x0, PyUnicode_InternFromString("x0")); GK(name_x1, PyUnicode_InternFromString("x1"));
    GK(name_y0, PyUnicode_InternFromString("y0")); GK(name_y1, PyUnicode_InternFromString("y1"));
    GK(axis_h, PyUnicode_InternFromString("h")); GK(axis_v, PyUnicode_InternFromString("v"));
    iter_start = pool.size;
    for (i = 0; i < n; i++) {
        /* Axis maps retain selected values; release rejected stroke temporaries
         * before processing the next stroke instead of retaining the page. */
        while (pool.size > iter_start) Py_DECREF(pool.items[--pool.size]);
        segment = PyList_GetItem(segments, i);
        {
            PyObject *actual = PyObject_Type(segment);
            int exact;
            if (!actual) goto done;
            exact = actual == segment_type; Py_DECREF(actual);
            if (!exact) { PyErr_SetString(ct_bailout, "foreign Segment type"); goto done; }
        }
        GK(x0, PyObject_GetAttr(segment, name_x0)); GK(x1, PyObject_GetAttr(segment, name_x1));
        GK(y0, PyObject_GetAttr(segment, name_y0)); GK(y1, PyObject_GetAttr(segment, name_y1));
        cmp = PyObject_RichCompareBool(x0, x1, Py_EQ); GC(cmp);
        if (cmp) { axis = axis_v; coord = x0; loobj = y0; hiobj = y1; }
        else {
            cmp = PyObject_RichCompareBool(y0, y1, Py_EQ); GC(cmp);
            if (!cmp) continue;
            axis = axis_h; coord = y0; loobj = x0; hiobj = x1;
        }
        GC(geo_double(x0, &ax)); GC(geo_double(x1, &bx));
        GC(geo_double(y0, &ay)); GC(geo_double(y1, &by));
        /* One difference is exactly zero for these axis-aligned strokes.
         * hypot therefore has the same exact magnitude as Segment.length. */
        len = hypot(bx - ax, by - ay);
        if (!(0 < len && len < 1)) continue;
        GK(key, PyTuple_Pack(2, axis, coord)); parts = PyDict_GetItemWithError(axes, key);
        if (!parts) {
            if (PyErr_Occurred()) goto done;
            GK(parts, PySet_New(NULL)); GC(PyDict_SetItem(axes, key, parts));
        }
        GK(part, PyTuple_Pack(2, loobj, hiobj)); GC(PySet_Add(parts, part));
    }
    while (pool.size > iter_start) Py_DECREF(pool.items[--pool.size]);
    pos = 0;
    while (PyDict_Next(axes, &pos, &key, &parts)) {
        PyObject *target = PyDict_GetItemWithError(result, GI(key, 0)); if (!target) goto done;
        coord = GI(key, 1); GK(ordered, geo_sorted(parts)); run = 0; has_gap = 0;
        for (j = 0; j <= PyList_Size(ordered); j++) {
            double next_gap = 0;
            int sentinel = j == PyList_Size(ordered);
            loobj = hiobj = NULL; lo = hi = 0;
            if (!sentinel) {
                part = PyList_GetItem(ordered, j); loobj = GI(part, 0); hiobj = GI(part, 1);
                GC(geo_double(loobj, &lo)); GC(geo_double(hiobj, &hi)); next_gap = lo - prev_hi;
            }
            equal = !sentinel && run && 0 < next_gap && next_gap <= tolerance && geo_isclose(hi - lo, first_len) && (!has_gap || geo_isclose(next_gap, gap));
            if (!equal) {
                if (run >= 3) {
                    bucket = geo_bucket(target, coord); if (!bucket) goto done;
                    GK(span, PyTuple_Pack(2, startobj, endobj)); GC(PyList_Append(bucket, span));
                }
                run = 0; has_gap = 0;
            }
            if (!sentinel) {
                if (run) { gap = next_gap; has_gap = 1; }
                else { startobj = loobj; first_len = hi - lo; }
                endobj = hiobj; prev_hi = hi; run++;
            }
        }
    }
    res = result;
done: return geo_finish(&pool, res);
}
static PyObject *geo_union_overlaps(PyObject *rules)
{
    GeoPool pool = {0}; PyObject *ordered, *out, *line, *last, *merged, *high, *res = NULL; Py_ssize_t i, n; int same, overlap, greater;
    GK(ordered, geo_sorted(rules)); GK(out, PyList_New(0));
    for (i = 0; i < PyList_Size(ordered); i++) {
        line = PyList_GetItem(ordered, i); n = PyList_Size(out);
        if (n) {
            last = PyList_GetItem(out, n - 1);
            same = PyObject_RichCompareBool(GI(last, 0), GI(line, 0), Py_EQ); GC(same);
            overlap = same ? PyObject_RichCompareBool(GI(line, 1), GI(last, 2), Py_LE) : 0; GC(overlap);
            if (overlap) {
                /* max(hi, previous_hi) keeps hi on equal values, including signed zero. */
                greater = PyObject_RichCompareBool(GI(last, 2), GI(line, 2), Py_GT); GC(greater);
                high = GI(greater ? last : line, 2);
                GK(merged, PyTuple_Pack(3, GI(line, 0), GI(last, 1), high)); Py_INCREF(merged); GC(PyList_SetItem(out, n - 1, merged));
                continue;
            }
        }
        GC(PyList_Append(out, line));
    }
    res = out;
done: return geo_finish(&pool, res);
}
static PyObject *ct_supplement_rules(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *horizontal, *vertical, *xs, *ys, *dash, *hs, *vs, *result_h, *result_v, *res = NULL;
    PyObject *axes, *coords, *target, *runs, *coord, *run, *low, *high, *lo, *hi, *item;
    Py_ssize_t i, j, axis; int ok;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOO", &horizontal, &vertical, &xs, &ys, &dash)) return NULL;
    GC(geo_rules(horizontal, 3)); GC(geo_rules(vertical, 3)); GC(geo_vector(xs)); GC(geo_vector(ys));
    if (!PyDict_Check(dash)) { PyErr_SetString(ct_bailout, "dash map requires a dict"); goto done; }
    GK(hs, PySequence_List(horizontal)); GK(vs, PySequence_List(vertical));
    for (axis = 0; axis < 2; axis++) {
        axes = PyDict_GetItemString(dash, axis ? "v" : "h"); if (!axes) { PyErr_SetString(PyExc_KeyError, "dash axis"); goto done; }
        coords = axis ? xs : ys; target = axis ? vs : hs;
        low = PyList_GetItem(axis ? ys : xs, axis ? PyList_Size(ys) - 1 : 0);
        high = PyList_GetItem(axis ? ys : xs, axis ? 0 : PyList_Size(xs) - 1);
        if (!low || !high) goto done;
        for (i = 1; i + 1 < PyList_Size(coords); i++) {
            coord = PyList_GetItem(coords, i); runs = PyDict_GetItemWithError(axes, coord);
            if (!runs) { if (PyErr_Occurred()) goto done; continue; }
            GC(geo_rules(runs, 2));
            for (j = 0; j < PyList_Size(runs); j++) {
                run = PyList_GetItem(runs, j); lo = GI(run, 0); hi = GI(run, 1);
                ok = PyObject_RichCompareBool(low, lo, Py_LE); GC(ok); if (!ok) continue;
                ok = PyObject_RichCompareBool(lo, hi, Py_LT); GC(ok); if (!ok) continue;
                ok = PyObject_RichCompareBool(hi, high, Py_LE); GC(ok); if (!ok) continue;
                GK(item, PyTuple_Pack(3, coord, lo, hi)); GC(PyList_Append(target, item));
            }
        }
    }
    GK(result_h, geo_union_overlaps(hs)); GK(result_v, geo_union_overlaps(vs)); GK(res, PyTuple_Pack(2, result_h, result_v));
done: return geo_finish(&pool, res);
}
#undef GK
#undef GC
#undef GI
