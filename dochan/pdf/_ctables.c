/* Handwritten mirror of tables.py. Public mutations are committed only after
 * the page has completed. All uncertain inputs replay through the Python path.
 * Object arithmetic retains Python's int/float tags and evaluation order. */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <math.h>
#include <stdarg.h>
#include <string.h>
#include "_csegments.h"

static PyObject *ct_bailout;
#include "_ctables_geometry.h"
#include "_ctables_text.h"

/* A page-local ownership ledger. No reference escapes on an error, including
 * failures in external paragraph construction or connected-table splitting. */
typedef struct { PyObject **refs; Py_ssize_t n, cap; } MainPool;
static PyObject *m_keep(MainPool *p, PyObject *o)
{
    if (!o) return NULL;
    if (p->n == p->cap) {
        Py_ssize_t cap = p->cap ? p->cap * 2 : 128;
        PyObject **next = PyMem_Realloc(p->refs, (size_t)cap * sizeof(*next));
        if (!next) { Py_DECREF(o); return PyErr_NoMemory(); }
        p->refs = next; p->cap = cap;
    }
    p->refs[p->n++] = o;
    return o;
}
static void m_reset(MainPool *p, Py_ssize_t mark)
{ while (p->n > mark) Py_DECREF(p->refs[--p->n]); }
static void m_clear(MainPool *p)
{ m_reset(p, 0); PyMem_Free(p->refs); }
static PyObject *m_attr(MainPool *p, PyObject *o, const char *name)
{
    static struct { const char *text; PyObject *key; } keys[64];
    static int count;
    int i;
    if (!o) return NULL;
    for (i = 0; i < count; i++)
        if (keys[i].text == name || strcmp(keys[i].text, name) == 0)
            return m_keep(p, PyObject_GetAttr(o, keys[i].key));
    if (count < 64) {
        PyObject *key = PyUnicode_InternFromString(name);
        if (!key) return NULL;
        keys[count].text = name; keys[count++].key = key;
        return m_keep(p, PyObject_GetAttr(o, key));
    }
    return m_keep(p, PyObject_GetAttrString(o, name));
}
static PyObject *m_at(PyObject *seq, Py_ssize_t i)
{
    if (!seq) return NULL;
    return PyList_Check(seq) ? PyList_GetItem(seq, i) : PyTuple_GetItem(seq, i);
}
static Py_ssize_t m_len(PyObject *seq)
{ return PyList_Check(seq) ? PyList_Size(seq) : PyTuple_Size(seq); }
static PyObject *m_tuple(MainPool *p, Py_ssize_t n, ...)
{
    va_list ap; Py_ssize_t i; PyObject *t = PyTuple_New(n);
    if (!t) return NULL;
    va_start(ap, n);
    for (i = 0; i < n; i++) {
        PyObject *v = va_arg(ap, PyObject *);
        if (!v) { va_end(ap); Py_DECREF(t); return NULL; }
        Py_INCREF(v); PyTuple_SetItem(t, i, v);
    }
    va_end(ap); return m_keep(p, t);
}
static PyObject *m_native(MainPool *p, PyObject *self, PyCFunction fn, PyObject *args)
{ return args ? m_keep(p, fn(self, args)) : NULL; }
static PyObject *m_call(MainPool *p, PyObject *fn, PyObject *args, PyObject *kwargs)
{ return fn && args ? m_keep(p, PyObject_Call(fn, args, kwargs)) : NULL; }
static PyObject *m_area(MainPool *p, PyObject *box)
{
    PyObject *w, *h;
    if (!box) return NULL;
    w = m_keep(p, PyNumber_Subtract(m_at(box, 2), m_at(box, 0)));
    h = m_keep(p, PyNumber_Subtract(m_at(box, 3), m_at(box, 1)));
    return w && h ? m_keep(p, PyNumber_Multiply(w, h)) : NULL;
}
static int m_inside(PyObject *inner, PyObject *outer)
{
    int a = PyObject_RichCompareBool(m_at(outer, 0), m_at(inner, 0), Py_LE);
    if (a <= 0) return a;
    a = PyObject_RichCompareBool(m_at(outer, 1), m_at(inner, 1), Py_LE);
    if (a <= 0) return a;
    a = PyObject_RichCompareBool(m_at(inner, 2), m_at(outer, 2), Py_LE);
    if (a <= 0) return a;
    return PyObject_RichCompareBool(m_at(inner, 3), m_at(outer, 3), Py_LE);
}
static int m_warn(PyObject *warnings, const char *message)
{
    PyObject *s; int present, status = 0;
    if (warnings == Py_None) return 0;
    s = PyUnicode_FromString(message);
    if (!s) return -1;
    present = PySequence_Contains(warnings, s);
    if (present < 0) status = -1;
    else if (!present) status = PyList_Append(warnings, s);
    Py_DECREF(s); return status;
}
static PyObject *m_axes(MainPool *p, PyObject *rules, int reverse)
{
    PyObject *set = m_keep(p, PySet_New(NULL)), *axes;
    Py_ssize_t i;
    if (!set) return NULL;
    for (i = 0; i < m_len(rules); i++)
        if (PySet_Add(set, m_at(m_at(rules, i), 0)) < 0) return NULL;
    axes = m_keep(p, PySequence_List(set));
    if (!axes || PyList_Sort(axes) < 0 || (reverse && PyList_Reverse(axes) < 0)) return NULL;
    return axes;
}
static PyObject *m_bbox(MainPool *p, PyObject *xs, PyObject *ys)
{ return m_tuple(p, 4, m_at(xs, 0), m_at(ys, m_len(ys)-1), m_at(xs, m_len(xs)-1), m_at(ys, 0)); }
/* Stable decoration avoids ever comparing model objects when keys tie. */
static PyObject *m_sorted(MainPool *p, PyObject *items, int kind)
{
    PyObject *decorated = m_keep(p, PyList_New(0)), *out;
    Py_ssize_t i;
    if (!decorated) return NULL;
    for (i = 0; i < m_len(items); i++) {
        PyObject *item = m_at(items, i), *key = NULL, *entry, *order;
        if (kind == 0) key = m_area(p, m_at(item, 0));
        else if (kind == 1) key = m_area(p, m_attr(p, item, "bbox"));
        else if (kind == 2) key = m_attr(p, item, "anchor_order");
        else {
            PyObject *negative = m_keep(p, PyNumber_Negative(m_at(item, 0)));
            key = m_tuple(p, 3, negative, m_at(item, 1), m_at(item, 2));
        }
        if (!key) return NULL;
        if (kind == 0) key = m_keep(p, PyNumber_Negative(key));
        order = m_keep(p, PyLong_FromSsize_t(i));
        entry = m_tuple(p, 3, key, order, item);
        if (!entry || PyList_Append(decorated, entry) < 0) return NULL;
    }
    if (PyList_Sort(decorated) < 0) return NULL;
    out = m_keep(p, PyList_New(0));
    if (!out) return NULL;
    for (i = 0; i < m_len(decorated); i++)
        if (PyList_Append(out, m_at(m_at(decorated, i), 2)) < 0) return NULL;
    return out;
}
static int m_exact(PyObject *o, PyObject *type)
{
    PyObject *actual = PyObject_Type(o); int same;
    if (!actual) return -1;
    same = actual == type; Py_DECREF(actual); return same;
}
static int m_preflight(PyObject *items, PyObject *type, const char **names)
{
    Py_ssize_t i; int j, same;
    if (!PyList_CheckExact(items)) goto unsupported;
    for (i = 0; i < PyList_Size(items); i++) {
        PyObject *item = PyList_GetItem(items, i);
        same = m_exact(item, type);
        if (same < 0) return -1;
        if (!same) goto unsupported;
        for (j = 0; names[j]; j++) {
            PyObject *value = PyObject_GetAttrString(item, names[j]);
            double number;
            if (!value) return -1;
            if (!PyFloat_CheckExact(value) && !PyLong_CheckExact(value)) {
                Py_DECREF(value); goto unsupported;
            }
            number = PyFloat_AsDouble(value); Py_DECREF(value);
            if (PyErr_Occurred()) { PyErr_Clear(); goto unsupported; }
            if (!isfinite(number) || fabs(number) > 1e100) goto unsupported;
        }
    }
    return 0;
unsupported:
    PyErr_SetString(ct_bailout, "unsupported table input; replay with Python"); return -1;
}

#define M_TUP(...) m_tuple(&pool, __VA_ARGS__)
#define M_NATIVE(name, ...) m_native(&pool, self, ct_##name, M_TUP(__VA_ARGS__))
#define M_ATTR(o, name) m_attr(&pool, o, name)
#define M_KEEP(expr) m_keep(&pool, (expr))
#define M_GET(var, expr) do { (var) = (expr); if (!(var)) goto done; } while (0)
#define M_OK(expr) do { if ((expr) < 0) goto done; } while (0)

/* Import lazily: ordinary list callers do not need the interpreter module. */
static SegmentAPI *table_segments_api;
static int table_segment_list(PyObject *value)
{
    if (PyList_CheckExact(value) || value == Py_None) return 0;
    if (!table_segments_api) {
        table_segments_api = PyCapsule_Import(SEGMENT_CAPSULE, 0);
        /* 해석기 모듈이 없으면 보통 입력(list·tuple)으로 본다 — 예외로 두면 거짓 '불일치' 경고가 붙는다 */
        if (!table_segments_api) { PyErr_Clear(); return 0; }
    }
    return Py_TYPE(value) == table_segments_api->type;
}
static PyObject *table_segment_number(SegmentNumber n)
{ return n.integer ? PyLong_FromLongLong((int64_t)n.v) : PyFloat_FromDouble(n.v); }
/* Cached elements are mutable Python dataclasses. Observe user changes rather
 * than reading stale coordinates once an element has escaped to Python. */
static int table_segment_coords(MainPool *pool, SegmentList *list, Py_ssize_t i,
                                PyObject **x0, PyObject **y0, PyObject **x1, PyObject **y1)
{
    uint64_t generation = list->generation;
    if (i >= list->size) { PyErr_SetString(ct_bailout, "changed native segment input"); return -1; }
    SegmentRecord r = list->records[i];
    PyObject *cached = list->cache[i];
    if (cached) {
        Py_INCREF(cached);
        if (!m_keep(pool, cached)) return -1;
    }
    *x0 = cached ? m_attr(pool, cached, "x0") : m_keep(pool, table_segment_number(r.x0));
    *y0 = cached ? m_attr(pool, cached, "y0") : m_keep(pool, table_segment_number(r.y0));
    *x1 = cached ? m_attr(pool, cached, "x1") : m_keep(pool, table_segment_number(r.x1));
    *y1 = cached ? m_attr(pool, cached, "y1") : m_keep(pool, table_segment_number(r.y1));
    if (list->generation != generation) {
        PyErr_SetString(ct_bailout, "changed native segment input"); return -1;
    }
    return *x0 && *y0 && *x1 && *y1 ? 0 : -1;
}

#define GK(v, expr) do { (v) = geo_keep(&pool, (expr)); if (!(v)) goto done; } while (0)
#define GC(expr) do { if ((expr) < 0) goto done; } while (0)
#define GI(seq, i) PyTuple_GetItem((seq), (i))
static PyObject *table_native_short_dash_runs(PyObject *self, PyObject *args)
{
    GeoPool pool = {0}; PyObject *segments, *axes, *result, *h, *v, *segment, *x0, *x1, *y0, *y1;
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
    n = ((SegmentList *)segments)->size; GC(n);
    uint64_t generation = ((SegmentList *)segments)->generation;
    GK(name_x0, PyUnicode_InternFromString("x0")); GK(name_x1, PyUnicode_InternFromString("x1"));
    GK(name_y0, PyUnicode_InternFromString("y0")); GK(name_y1, PyUnicode_InternFromString("y1"));
    GK(axis_h, PyUnicode_InternFromString("h")); GK(axis_v, PyUnicode_InternFromString("v"));
    iter_start = pool.size;
    for (i = 0; i < n; i++) {
        /* Axis maps retain selected values; release rejected stroke temporaries
         * before processing the next stroke instead of retaining the page. */
        while (pool.size > iter_start) Py_DECREF(pool.items[--pool.size]);
        SegmentList *list = (SegmentList *)segments;
        if (list->generation != generation || i >= list->size) {
            PyErr_SetString(ct_bailout, "changed native short segment input"); goto done;
        }
        segment = list->cache[i];
        if (segment) { Py_INCREF(segment); GK(segment, segment); }
        SegmentRecord r = list->records[i];
        GK(x0, segment ? PyObject_GetAttr(segment, name_x0) : table_segment_number(r.x0));
        GK(x1, segment ? PyObject_GetAttr(segment, name_x1) : table_segment_number(r.x1));
        GK(y0, segment ? PyObject_GetAttr(segment, name_y0) : table_segment_number(r.y0));
        GK(y1, segment ? PyObject_GetAttr(segment, name_y1) : table_segment_number(r.y1));
        if (list->generation != generation) {
            PyErr_SetString(ct_bailout, "changed native short segment input"); goto done;
        }
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

#undef GK
#undef GC
#undef GI

static PyObject *ct_build_tables(PyObject *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"segments", "fragments", "tolerance", "page_number", "warnings", "budget", "short_segments", NULL};
    static const char *segment_names[] = {NULL};
    /* Text kernels validate numeric fields while loading them, once per page. */
    static const char *fragment_names[] = {NULL};
    MainPool pool = {NULL, 0, 0};
    PyObject *segments, *fragments, *tolerance = NULL, *page = Py_None;
    PyObject *warnings = Py_None, *budget = Py_None, *shorts = Py_None, *result = NULL;
    PyObject *mod, *work_warnings, *work_budget, *zero, *two, *eight, *table_type, *node_type, *candidate_type;
    PyObject *horizontal, *vertical, *grouped, *dash, *index, *line_cache, *reference_points;
    PyObject *separated, *component_boxes, *split_budget, *components, *nodes, *used_orders;
    PyObject *max_cells_obj, *max_lines_obj, *max_components_obj, *max_depth_obj;
    Py_ssize_t max_cells, max_lines, max_components, max_depth, remaining, reserved = 0, i, j, mark;
    int has_valid = 0, native_segments;
    double numeric_tolerance;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|OOOOO:build_tables", kwlist,
            &segments, &fragments, &tolerance, &page, &warnings, &budget, &shorts)) return NULL;
    native_segments = table_segment_list(segments);
    if (native_segments < 0) goto done;
    M_GET(mod, M_KEEP(PyImport_ImportModule("dochan.pdf.tables")));
    if (!tolerance) M_GET(tolerance, M_KEEP(PyFloat_FromDouble(1.5)));
    if ((!PyFloat_CheckExact(tolerance) && !PyLong_CheckExact(tolerance)) ||
        (warnings != Py_None && !PyList_CheckExact(warnings))) {
        PyErr_SetString(ct_bailout, "unsupported table options"); goto done;
    }
    {
        numeric_tolerance = PyFloat_AsDouble(tolerance);
        if (PyErr_Occurred() || !isfinite(numeric_tolerance) || fabs(numeric_tolerance) > 1e100) {
            PyErr_Clear(); PyErr_SetString(ct_bailout, "unsupported table tolerance"); goto done;
        }
    }
    { PyObject *type;
      M_GET(type, M_ATTR(mod, "Segment")); if (!native_segments) M_OK(m_preflight(segments, type, segment_names));
    }
    M_GET(work_warnings, M_KEEP(warnings == Py_None ? PyList_New(0) : PySequence_List(warnings)));
    work_budget = Py_None;
    if (budget != Py_None) {
        PyObject *type, *value; int same;
        M_GET(type, M_ATTR(mod, "TableBudget"));
        same = m_exact(budget, type); if (same < 0) goto done;
        M_GET(value, M_ATTR(budget, "remaining"));
        if (!same || !PyLong_CheckExact(value)) { PyErr_SetString(ct_bailout, "unsupported table budget"); goto done; }
        M_GET(work_budget, m_call(&pool, type, M_TUP(1, value), NULL));
    }
    M_GET(max_cells_obj, M_ATTR(mod, "MAX_PAGE_CELLS"));
    M_GET(max_lines_obj, M_ATTR(mod, "MAX_COMPONENT_LINES"));
    M_GET(max_components_obj, M_ATTR(mod, "MAX_PAGE_COMPONENTS"));
    M_GET(max_depth_obj, M_ATTR(mod, "MAX_NESTED_DEPTH"));
    max_cells = PyLong_AsSsize_t(max_cells_obj); max_lines = PyLong_AsSsize_t(max_lines_obj);
    max_components = PyLong_AsSsize_t(max_components_obj); max_depth = PyLong_AsSsize_t(max_depth_obj);
    if (PyErr_Occurred()) goto done;
    M_GET(zero, M_KEEP(PyLong_FromLong(0))); M_GET(two, M_KEEP(PyLong_FromLong(2)));
    M_GET(eight, M_KEEP(PyLong_FromLong(8)));
    M_GET(table_type, M_ATTR(mod, "Table")); M_GET(node_type, M_ATTR(mod, "_TableNode"));
    M_GET(candidate_type, M_ATTR(mod, "TableCandidate"));
    M_GET(horizontal, M_KEEP(PyList_New(0))); M_GET(vertical, M_KEEP(PyList_New(0)));
    mark = pool.n;
    Py_ssize_t segment_count = native_segments ? ((SegmentList *)segments)->size : m_len(segments);
    uint64_t generation = native_segments ? ((SegmentList *)segments)->generation : 0;
    for (i = 0; i < segment_count; i++) {
        m_reset(&pool, mark);
        if (native_segments && ((SegmentList *)segments)->generation != generation) {
            PyErr_SetString(ct_bailout, "changed native segment input"); goto done;
        }
        PyObject *s = native_segments ? NULL : m_at(segments, i), *x0, *x1, *y0, *y1, *dy, *dx, *sum, *coord, *run;
        int aligned; double checked;
        if (native_segments && !((SegmentList *)segments)->cache[i]) {
            SegmentRecord r = ((SegmentList *)segments)->records[i];
            /* Bound both integer sums/differences below 2**53. In this
             * domain double arithmetic exactly mirrors Python integers;
             * floats retain the original subtraction/addition/division order.
             * Exotic or previously exposed coordinates use the object path. */
            const double exact_half = 4503599627370495.0;
            if (fabs(r.x0.v) <= exact_half && fabs(r.x1.v) <= exact_half &&
                fabs(r.y0.v) <= exact_half && fabs(r.y1.v) <= exact_half) {
                SegmentNumber low, high;
                double center;
                PyObject *target;
                if (fabs(r.y1.v - r.y0.v) <= numeric_tolerance) {
                    center = (r.y0.v + r.y1.v) / 2.0;
                    low = r.x0; high = r.x1; target = horizontal;
                } else if (fabs(r.x1.v - r.x0.v) <= numeric_tolerance) {
                    center = (r.x0.v + r.x1.v) / 2.0;
                    low = r.y0; high = r.y1; target = vertical;
                } else continue;
                M_GET(coord, M_KEEP(PyFloat_FromDouble(center)));
                M_GET(x0, M_KEEP(table_segment_number(low)));
                M_GET(x1, M_KEEP(table_segment_number(high)));
                M_GET(run, M_TUP(3, coord, x0, x1));
                M_OK(PyList_Append(target, run));
                continue;
            }
        }
        if (native_segments) {
            M_OK(table_segment_coords(&pool, (SegmentList *)segments, i, &x0, &y0, &x1, &y1));
        } else {
            M_GET(x0, M_ATTR(s, "x0")); M_GET(x1, M_ATTR(s, "x1"));
            M_GET(y0, M_ATTR(s, "y0")); M_GET(y1, M_ATTR(s, "y1"));
        }
        M_OK(geo_double(x0, &checked)); M_OK(geo_double(x1, &checked));
        M_OK(geo_double(y0, &checked)); M_OK(geo_double(y1, &checked));
        M_GET(dy, M_KEEP(PyNumber_Subtract(y1, y0))); M_GET(dy, M_KEEP(PyNumber_Absolute(dy)));
        aligned = PyObject_RichCompareBool(dy, tolerance, Py_LE); if (aligned < 0) goto done;
        if (aligned) {
            M_GET(sum, M_KEEP(PyNumber_Add(y0, y1))); M_GET(coord, M_KEEP(PyNumber_TrueDivide(sum, two)));
            M_GET(run, M_TUP(3, coord, x0, x1)); M_OK(PyList_Append(horizontal, run));
        } else {
            M_GET(dx, M_KEEP(PyNumber_Subtract(x1, x0))); M_GET(dx, M_KEEP(PyNumber_Absolute(dx)));
            aligned = PyObject_RichCompareBool(dx, tolerance, Py_LE); if (aligned < 0) goto done;
            if (aligned) {
                M_GET(sum, M_KEEP(PyNumber_Add(x0, x1))); M_GET(coord, M_KEEP(PyNumber_TrueDivide(sum, two)));
                M_GET(run, M_TUP(3, coord, y0, y1)); M_OK(PyList_Append(vertical, run));
            }
        }
    }
    m_reset(&pool, mark);
    M_GET(horizontal, M_NATIVE(snap_runs, 2, horizontal, tolerance));
    M_GET(vertical, M_NATIVE(snap_runs, 2, vertical, tolerance));
    M_GET(grouped, M_NATIVE(components, 3, horizontal, vertical, tolerance));
    if (grouped == Py_None) {
        M_OK(m_warn(work_warnings, "WARN: PDF 괘선 교차 검사 수 한도(2000000) 초과 — 표 생략"));
        M_GET(result, M_KEEP(PyList_New(0))); goto commit;
    }
    for (i = 0; i < m_len(grouped); i++)
        if (m_len(m_at(m_at(grouped, i), 0)) >= 2 && m_len(m_at(m_at(grouped, i), 1)) >= 2) has_valid = 1;
    if (!has_valid) { M_GET(result, M_KEEP(PyList_New(0))); goto commit; }
    /* Pages with no ruled candidate never inspect text or short strokes in
     * the Python path. Defer the same checks until a candidate exists. */
    { PyObject *type;
      M_GET(type, M_ATTR(mod, "Segment"));
      int native_shorts = table_segment_list(shorts);
      if (native_shorts < 0) goto done;
      if (shorts != Py_None && !native_shorts) M_OK(m_preflight(shorts, type, segment_names));
      M_GET(type, M_ATTR(mod, "Fragment")); M_OK(m_preflight(fragments, type, fragment_names));
    }
    if (table_segment_list(shorts)) {
        M_GET(dash, m_native(&pool, self, table_native_short_dash_runs, M_TUP(2, shorts, tolerance)));
    } else {
        M_GET(dash, M_NATIVE(short_dash_runs, 2, shorts, tolerance));
    }
    M_GET(index, M_NATIVE(fragment_index, 1, fragments));
    M_GET(line_cache, M_KEEP(PyDict_New())); M_GET(reference_points, M_KEEP(PyDict_New()));
    mark = pool.n;
    for (i = 0; i < m_len(m_at(index, 0)); i++) {
        m_reset(&pool, mark);
        PyObject *entry = m_at(m_at(index, 0), i), *id;
        M_GET(id, M_KEEP(PyLong_FromVoidPtr(m_at(entry, 1))));
        M_OK(PyDict_SetItem(reference_points, id, m_at(entry, 0)));
    }
    m_reset(&pool, mark);
    M_GET(separated, M_KEEP(PyList_New(0))); M_GET(component_boxes, M_KEEP(PyDict_New()));
    M_GET(split_budget, m_call(&pool, M_ATTR(mod, "SplitBudget"), M_TUP(0), NULL));
    mark = pool.n;
    for (i = 0; i < m_len(grouped); i++) {
        m_reset(&pool, mark);
        PyObject *pair = m_at(grouped, i), *hs = m_at(pair, 0), *vs = m_at(pair, 1), *xs, *ys, *box, *id, *ignored;
        if (m_len(hs) < 2 || m_len(vs) < 2) continue;
        M_GET(xs, m_axes(&pool, vs, 0)); M_GET(ys, m_axes(&pool, hs, 1));
        M_GET(ignored, M_NATIVE(extend_to_rule_extents, 3, xs, hs, tolerance)); (void)ignored;
        M_GET(box, m_bbox(&pool, xs, ys)); M_GET(id, M_KEEP(PyLong_FromSsize_t(i)));
        M_OK(PyDict_SetItem(component_boxes, id, box));
    }
    m_reset(&pool, mark);
    mark = pool.n;
    for (i = 0; i < m_len(grouped); i++) {
        m_reset(&pool, mark);
        PyObject *pair = m_at(grouped, i), *hs = m_at(pair, 0), *vs = m_at(pair, 1), *id, *box, *split;
        int eligible;
        M_GET(id, M_KEEP(PyLong_FromSsize_t(i))); box = PyDict_GetItemWithError(component_boxes, id);
        if (PyErr_Occurred()) goto done;
        eligible = m_len(grouped) < max_components && max_depth >= 1 && box != NULL;
        if (eligible) {
            PyObject *other_id, *other_box; Py_ssize_t pos = 0;
            while (PyDict_Next(component_boxes, &pos, &other_id, &other_box)) {
                int equal = PyObject_RichCompareBool(id, other_id, Py_EQ), inside;
                if (equal < 0) goto done;
                if (equal) continue;
                inside = m_inside(box, other_box); if (inside < 0) goto done;
                if (inside) { eligible = 0; break; }
            }
        }
        if (eligible) {
            PyObject *kw, *available = max_cells_obj;
            if (work_budget != Py_None) M_GET(available, M_ATTR(work_budget, "remaining"));
            M_GET(kw, M_KEEP(PyDict_New()));
            M_OK(PyDict_SetItemString(kw, "warnings", work_warnings));
            M_OK(PyDict_SetItemString(kw, "split_budget", split_budget));
            M_OK(PyDict_SetItemString(kw, "dash_runs", dash));
            M_OK(PyDict_SetItemString(kw, "max_cells", available));
            M_GET(split, m_call(&pool, M_ATTR(mod, "split_connected"), M_TUP(4, hs, vs, tolerance, index), kw));
            for (j = 0; j < m_len(split); j++) M_OK(PyList_Append(separated, m_at(split, j)));
        } else M_OK(PyList_Append(separated, pair));
    }
    m_reset(&pool, mark);
    if (m_len(separated) > m_len(grouped)) {
        Py_ssize_t needed = 0; int too_many;
        mark = pool.n;
        for (i = 0; i < m_len(separated); i++) {
            m_reset(&pool, mark);
            PyObject *pair = m_at(separated, i), *hs = m_at(pair, 0), *vs = m_at(pair, 1), *xs, *ys, *ignored;
            if (m_len(hs) < 2 || m_len(vs) < 2) continue;
            M_GET(xs, m_axes(&pool, vs, 0)); M_GET(ys, m_axes(&pool, hs, 0));
            M_GET(ignored, M_NATIVE(extend_to_rule_extents, 3, xs, hs, tolerance)); (void)ignored;
            if (m_len(xs) > 1000000 || m_len(ys) > 1000000 || needed > PY_SSIZE_T_MAX / 2) {
                PyErr_SetString(ct_bailout, "grid size requires Python integers"); goto done;
            }
            needed += (m_len(xs)-1) * (m_len(ys)-1);
        }
        m_reset(&pool, mark);
        too_many = m_len(separated) > max_components || needed > max_cells;
        if (!too_many && work_budget != Py_None) {
            PyObject *need, *available;
            M_GET(need, M_KEEP(PyLong_FromSsize_t(needed))); M_GET(available, M_ATTR(work_budget, "remaining"));
            too_many = PyObject_RichCompareBool(need, available, Py_GT); if (too_many < 0) goto done;
        }
        if (too_many) separated = grouped;
    }
    M_GET(components, M_KEEP(PyList_New(0)));
    mark = pool.n;
    for (i = 0; i < m_len(separated); i++) {
        m_reset(&pool, mark);
        PyObject *pair = m_at(separated, i), *hs = m_at(pair, 0), *vs = m_at(pair, 1), *xs, *ys, *box, *ignored, *w, *h, *near, *rules, *entry;
        int wide, tall;
        if (m_len(hs) < 2 || m_len(vs) < 2) continue;
        M_GET(xs, m_axes(&pool, vs, 0)); M_GET(ys, m_axes(&pool, hs, 1));
        M_GET(ignored, M_NATIVE(extend_to_rule_extents, 3, xs, hs, tolerance)); (void)ignored;
        M_GET(box, m_bbox(&pool, xs, ys));
        M_GET(w, M_KEEP(PyNumber_Subtract(m_at(box, 2), m_at(box, 0))));
        M_GET(h, M_KEEP(PyNumber_Subtract(m_at(box, 3), m_at(box, 1))));
        wide = PyObject_RichCompareBool(w, eight, Py_GE); tall = PyObject_RichCompareBool(h, eight, Py_GE);
        if (wide < 0 || tall < 0) goto done;
        if (!wide || !tall) continue;
        M_GET(near, M_NATIVE(fragments_inside, 2, index, box));
        M_GET(rules, M_NATIVE(numeric_row_rules, 8, hs, vs, xs, ys, near, tolerance, reference_points, line_cache));
        hs = m_at(rules, 0); ys = m_at(rules, 1);
        M_GET(entry, M_TUP(5, box, hs, vs, xs, ys)); M_OK(PyList_Append(components, entry));
    }
    m_reset(&pool, mark);
    M_GET(components, m_sorted(&pool, components, 0)); remaining = max_cells;
    M_GET(nodes, M_KEEP(PyList_New(0)));
    mark = pool.n;
    for (i = 0; i < m_len(components); i++) {
        m_reset(&pool, mark);
        PyObject *entry = m_at(components, i), *box = m_at(entry, 0), *hs = m_at(entry, 1), *vs = m_at(entry, 2);
        PyObject *xs = m_at(entry, 3), *ys = m_at(entry, 4), *has, *parent = Py_None, *owner = Py_None;
        PyObject *best_area = NULL, *grid_result, *cells_obj, *depth_obj, *node;
        Py_ssize_t cells, depth = 0; int has_text;
        if (m_len(hs) + m_len(vs) > max_lines) {
            M_OK(m_warn(work_warnings, "WARN: PDF 표 연결 성분의 선 수 한도(2000) 초과 — 표 생략")); continue;
        }
        M_GET(has, M_NATIVE(has_fragment_inside, 2, index, box)); has_text = PyObject_IsTrue(has);
        if (has_text < 0) goto done;
        if (!has_text && (m_len(xs) < 3 || m_len(ys) < 3)) continue;
        if (m_len(nodes) >= max_components) {
            M_OK(m_warn(work_warnings, "WARN: PDF 페이지 표 후보 수 한도(1000) 초과 — 작은 후보 생략")); break;
        }
        for (j = 0; j < m_len(nodes); j++) {
            PyObject *candidate = m_at(nodes, j), *parent_box, *area; int inside, less = 1;
            M_GET(parent_box, M_ATTR(candidate, "bbox")); inside = m_inside(box, parent_box);
            if (inside < 0) goto done;
            if (!inside) continue;
            M_GET(area, m_area(&pool, parent_box));
            if (best_area) less = PyObject_RichCompareBool(area, best_area, Py_LT);
            if (less < 0) goto done;
            if (less) { parent = candidate; best_area = area; }
        }
        if (parent != Py_None) {
            M_GET(owner, M_NATIVE(owner_region, 2, box, parent)); if (owner == Py_None) continue;
        }
        if (m_len(xs) > 1000000 || m_len(ys) > 1000000) {
            PyErr_SetString(ct_bailout, "large grid requires Python integers"); goto done;
        }
        cells = (m_len(xs)-1) * (m_len(ys)-1);
        if (parent != Py_None && !has_text && !(m_len(xs) >= 3 && m_len(ys) >= 3 && cells >= 6)) continue;
        if (parent != Py_None) {
            PyObject *parent_depth; M_GET(parent_depth, M_ATTR(parent, "depth"));
            depth = PyLong_AsSsize_t(parent_depth) + 1; if (PyErr_Occurred()) goto done;
        }
        if (depth > max_depth) {
            M_OK(m_warn(work_warnings, "WARN: PDF 중첩 표 깊이 한도(32) 초과 — 표 생략")); continue;
        }
        if (cells > remaining - reserved) {
            M_OK(m_warn(work_warnings, "WARN: PDF 페이지 표 셀 수 한도(50000) 초과 — 표 생략")); continue;
        }
        if (work_budget != Py_None) {
            PyObject *available, *reserved_obj, *needed; int exceeds;
            M_GET(available, M_ATTR(work_budget, "remaining")); M_GET(reserved_obj, M_KEEP(PyLong_FromSsize_t(reserved)));
            M_GET(available, M_KEEP(PyNumber_Subtract(available, reserved_obj))); M_GET(needed, M_KEEP(PyLong_FromSsize_t(cells)));
            exceeds = PyObject_RichCompareBool(needed, available, Py_GT); if (exceeds < 0) goto done;
            if (exceeds) {
                M_OK(m_warn(work_warnings, "WARN: PDF 문서 표 셀 수 한도(200000) 초과 — 표 생략")); continue;
            }
        }
        if (has_text) {
            PyObject *supplement; M_GET(supplement, M_NATIVE(supplement_rules, 5, hs, vs, xs, ys, dash));
            hs = m_at(supplement, 0); vs = m_at(supplement, 1);
        }
        M_GET(grid_result, M_NATIVE(make_grid, 6, hs, vs, xs, ys, tolerance, page));
        reserved += cells;
        M_GET(cells_obj, M_KEEP(PyLong_FromSsize_t(cells))); M_GET(depth_obj, M_KEEP(PyLong_FromSsize_t(depth)));
        M_GET(node, m_call(&pool, node_type, M_TUP(10, box, xs, ys, m_at(grid_result, 0), m_at(grid_result, 1),
            m_at(grid_result, 2), cells_obj, parent, owner, depth_obj), NULL));
        M_OK(PyList_Append(nodes, node));
    }
    m_reset(&pool, mark);
    M_GET(used_orders, M_KEEP(PySet_New(NULL))); M_GET(result, M_KEEP(PyList_New(0)));
    M_GET(nodes, m_sorted(&pool, nodes, 1));
    mark = pool.n;
    for (i = 0; i < m_len(nodes); i++) {
        m_reset(&pool, mark);
        PyObject *node = m_at(nodes, i), *children, *breaks, *near, *own_frags, *assignment, *own_orders, *events;
        PyObject *grid, *owners, *boxes, *xs, *ys, *box, *parent, *subtree, *cells_obj;
        Py_ssize_t cells, pos; PyObject *key, *blocks; int keep;
        M_GET(children, M_ATTR(node, "children")); M_GET(breaks, M_KEEP(PyDict_New()));
        M_GET(grid, M_ATTR(node, "grid")); M_GET(owners, M_ATTR(node, "owners")); M_GET(boxes, M_ATTR(node, "boxes"));
        M_GET(xs, M_ATTR(node, "xs")); M_GET(ys, M_ATTR(node, "ys")); M_GET(box, M_ATTR(node, "bbox"));
        M_GET(parent, M_ATTR(node, "parent")); M_GET(cells_obj, M_ATTR(node, "cells"));
        cells = PyLong_AsSsize_t(cells_obj); if (PyErr_Occurred()) goto done;
        for (j = 0; j < m_len(children); j++) {
            PyObject *child = m_at(children, j), *owner, *child_box, *values;
            M_GET(owner, M_ATTR(child, "owner_key")); M_GET(child_box, M_ATTR(child, "bbox"));
            values = PyDict_GetItemWithError(breaks, owner); if (PyErr_Occurred()) goto done;
            if (!values) { M_GET(values, M_KEEP(PyList_New(0))); M_OK(PyDict_SetItem(breaks, owner, values)); }
            M_OK(PyList_Append(values, m_at(child_box, 3)));
        }
        M_GET(near, M_NATIVE(fragments_inside, 2, index, box)); M_GET(own_frags, M_KEEP(PyList_New(0)));
        for (j = 0; j < m_len(near); j++) {
            PyObject *frag = m_at(near, j), *order; int used;
            M_GET(order, M_ATTR(frag, "order")); used = PySet_Contains(used_orders, order); if (used < 0) goto done;
            if (!used) M_OK(PyList_Append(own_frags, frag));
        }
        M_GET(assignment, M_NATIVE(assign_text, 10, grid, owners, boxes, xs, ys, own_frags, page, breaks, reference_points, line_cache));
        own_orders = m_at(assignment, 0); events = m_at(assignment, 1);
        for (j = 0; j < m_len(children); j++) {
            PyObject *child = m_at(children, j), *owner, *child_box, *anchor, *child_grid, *table, *values, *event, *one;
            M_GET(owner, M_ATTR(child, "owner_key")); M_GET(child_box, M_ATTR(child, "bbox"));
            M_GET(anchor, M_ATTR(child, "anchor_order")); M_GET(child_grid, M_ATTR(child, "grid"));
            M_GET(table, m_call(&pool, table_type, M_TUP(1, child_grid), NULL));
            M_GET(one, M_KEEP(PyLong_FromLong(1))); M_GET(event, M_TUP(4, m_at(child_box, 3), one, anchor, table));
            values = PyDict_GetItemWithError(events, owner); if (PyErr_Occurred()) goto done;
            if (!values) { M_GET(values, M_KEEP(PyList_New(0))); M_OK(PyDict_SetItem(events, owner, values)); }
            M_OK(PyList_Append(values, event));
        }
        pos = 0;
        while (PyDict_Next(events, &pos, &key, &blocks)) {
            Py_ssize_t owner = PyLong_AsSsize_t(key), k; PyObject *ordered, *paragraphs, *cell;
            if (PyErr_Occurred()) goto done;
            M_GET(ordered, m_sorted(&pool, blocks, 3)); M_GET(paragraphs, M_KEEP(PyList_New(0)));
            for (k = 0; k < m_len(ordered); k++) M_OK(PyList_Append(paragraphs, m_at(m_at(ordered, k), 3)));
            cell = m_at(m_at(grid, owner / (m_len(xs)-1)), owner % (m_len(xs)-1));
            M_OK(PyObject_SetAttrString(cell, "paragraphs", paragraphs));
        }
        M_GET(subtree, M_KEEP(PySet_New(own_orders)));
        for (j = 0; j < m_len(children); j++) {
            PyObject *orders, *merged;
            M_GET(orders, M_ATTR(m_at(children, j), "fragment_orders"));
            /* Bulk merging matches set.union's resizing and iteration order. */
            M_GET(merged, M_KEEP(PyNumber_InPlaceOr(subtree, orders))); (void)merged;
        }
        if (parent == Py_None) keep = PySet_Size(subtree) != 0 || (m_len(xs) >= 3 && m_len(ys) >= 3);
        else {
            Py_ssize_t text_cells = 0, r, c;
            double width, height;
            for (r = 0; r < m_len(grid); r++) for (c = 0; c < m_len(m_at(grid, r)); c++) {
                PyObject *cell = m_at(m_at(grid, r), c), *merged, *text; int truth;
                M_GET(merged, M_ATTR(cell, "is_merged_away")); truth = PyObject_IsTrue(merged); if (truth < 0) goto done;
                if (truth) continue;
                M_GET(text, M_ATTR(cell, "text")); truth = PyObject_IsTrue(text); if (truth < 0) goto done;
                text_cells += truth;
            }
            width = PyFloat_AsDouble(m_at(box, 2)) - PyFloat_AsDouble(m_at(box, 0));
            height = PyFloat_AsDouble(m_at(box, 3)) - PyFloat_AsDouble(m_at(box, 1));
            if (PyErr_Occurred()) goto done;
            keep = (text_cells >= 1 && (text_cells >= 2 || cells >= 4 || (cells == 1 && width >= 30 && height >= 12))) ||
                   (text_cells == 0 && m_len(xs) >= 3 && m_len(ys) >= 3 && cells >= 6);
        }
        if (!keep) {
            PyObject *iter, *order, *owner;
            M_GET(iter, M_KEEP(PyObject_GetIter(own_orders)));
            while ((order = PyIter_Next(iter))) { int status = PySet_Discard(used_orders, order); Py_DECREF(order); M_OK(status); }
            if (PyErr_Occurred()) goto done;
            M_GET(owner, M_ATTR(node, "owner_key"));
            for (j = 0; j < m_len(children); j++) {
                PyObject *child = m_at(children, j), *target;
                M_OK(PyObject_SetAttrString(child, "parent", parent)); M_OK(PyObject_SetAttrString(child, "owner_key", owner));
                if (parent != Py_None) {
                    M_GET(target, M_ATTR(parent, "children")); M_OK(PyList_Append(target, child));
                } else {
                    PyObject *child_grid, *table, *child_box, *orders, *anchor, *cx, *cy;
                    M_GET(child_grid, M_ATTR(child, "grid")); M_GET(table, m_call(&pool, table_type, M_TUP(1, child_grid), NULL));
                    M_GET(child_box, M_ATTR(child, "bbox")); M_GET(orders, M_ATTR(child, "fragment_orders")); M_GET(anchor, M_ATTR(child, "anchor_order"));
                    M_GET(cx, M_ATTR(child, "xs")); M_GET(cx, M_KEEP(PySequence_Tuple(cx)));
                    M_GET(cy, M_ATTR(child, "ys")); M_GET(cy, M_KEEP(PySequence_Tuple(cy)));
                    M_GET(target, m_call(&pool, candidate_type, M_TUP(6, table, child_box, orders, anchor, cx, cy), NULL));
                    M_OK(PyList_Append(result, target));
                }
            }
            continue;
        }
        if (work_budget != Py_None) {
            PyObject *available;
            M_GET(available, M_ATTR(work_budget, "remaining")); M_GET(available, M_KEEP(PyNumber_Subtract(available, cells_obj)));
            M_OK(PyObject_SetAttrString(work_budget, "remaining", available));
        }
        {
            PyObject *iter, *order, *anchor = NULL;
            M_OK(PyObject_SetAttrString(node, "fragment_orders", subtree)); M_GET(iter, M_KEEP(PyObject_GetIter(subtree)));
            while ((order = PyIter_Next(iter))) {
                int less = 1; M_GET(order, M_KEEP(order));
                if (anchor) less = PyObject_RichCompareBool(order, anchor, Py_LT);
                if (less < 0) goto done;
                if (less) anchor = order;
            }
            if (PyErr_Occurred()) goto done;
            if (!anchor) M_GET(anchor, M_KEEP(PyLong_FromLong(-1)));
            M_OK(PyObject_SetAttrString(node, "anchor_order", anchor));
            M_GET(iter, M_KEEP(PyObject_GetIter(own_orders)));
            while ((order = PyIter_Next(iter))) { int status = PySet_Add(used_orders, order); Py_DECREF(order); M_OK(status); }
            if (PyErr_Occurred()) goto done;
            if (parent == Py_None) {
                PyObject *table, *xt, *yt, *candidate;
                M_GET(table, m_call(&pool, table_type, M_TUP(1, grid), NULL));
                M_GET(xt, M_KEEP(PySequence_Tuple(xs))); M_GET(yt, M_KEEP(PySequence_Tuple(ys)));
                M_GET(candidate, m_call(&pool, candidate_type, M_TUP(6, table, box, subtree, anchor, xt, yt), NULL));
                M_OK(PyList_Append(result, candidate));
            } else { PyObject *target; M_GET(target, M_ATTR(parent, "children")); M_OK(PyList_Append(target, node)); }
        }
    }
    m_reset(&pool, mark);
    M_GET(result, m_sorted(&pool, result, 2));
commit:
    /* Exact list / dataclass inputs make this commit free of user callbacks. */
    if (warnings != Py_None) M_OK(PyList_SetSlice(warnings, 0, PyList_Size(warnings), work_warnings));
    if (budget != Py_None) {
        PyObject *available; M_GET(available, M_ATTR(work_budget, "remaining")); M_OK(PyObject_SetAttrString(budget, "remaining", available));
    }
    Py_INCREF(result); m_clear(&pool); return result;
done:
    m_clear(&pool); return NULL;
}

#define CT_METHOD(name) {"_" #name, ct_##name, METH_VARARGS, "C mirror of tables._" #name}
static PyMethodDef ct_methods[] = {
    {"build_tables", (PyCFunction)(void (*)(void))ct_build_tables, METH_VARARGS | METH_KEYWORDS, "Build table candidates transactionally."},
    CT_METHOD(snap_runs), CT_METHOD(components), CT_METHOD(covered), CT_METHOD(rectangles), CT_METHOD(make_grid),
    CT_METHOD(shared_extent), CT_METHOD(extend_to_rule_extents), CT_METHOD(inside), CT_METHOD(owner_region),
    CT_METHOD(short_dash_runs), CT_METHOD(supplement_rules), CT_METHOD(reference_axes), CT_METHOD(reference_point),
    CT_METHOD(fragment_index), CT_METHOD(fragments_inside), CT_METHOD(has_fragment_inside), CT_METHOD(reading_key),
    CT_METHOD(cell_lines), CT_METHOD(assign_text), CT_METHOD(numeric_row_rules),
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef ct_definition = {
    PyModuleDef_HEAD_INIT, "_ctables", "Optional handwritten table restoration.", -1, ct_methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__ctables(void)
{
    PyObject *module = PyModule_Create(&ct_definition);
    if (!module) return NULL;
    if (!ct_bailout) ct_bailout = PyErr_NewException("dochan.pdf._ctables.Bailout", NULL, NULL);
    if (!ct_bailout) { Py_DECREF(module); return NULL; }
    Py_INCREF(ct_bailout);
    if (PyModule_AddObject(module, "Bailout", ct_bailout) < 0) {
        Py_DECREF(ct_bailout); Py_DECREF(module); return NULL;
    }
    return module;
}
