/* Handwritten table text kernels. All object ownership is local to a call. */
#include <math.h>
#include <stdint.h>
#include <string.h>
#define CLAYOUT_EMBEDDED
#include "_clayout.c"
#undef CLAYOUT_EMBEDDED

/* Intern attribute names once: GetAttrString would allocate each hot-loop key. */
static const char *tx_attr_names[] = {
    "x", "y", "width", "size", "dir_x", "dir_y", "up_x", "up_y", "order",
    "direction", "text", "_c_assemble_lines", "_Line", "_Segment", "Fragment",
    "_LINE_Y_TOLERANCE", "assemble_lines", "merge_lines", "_NUMBER",
    "MAX_INTERSECTION_CHECKS", "MAX_PAGE_CELLS", "defaultdict"
};
static PyObject *tx_attr_keys[sizeof(tx_attr_names) / sizeof(tx_attr_names[0])];
static PyObject *tx_getattr(PyObject *o, const char *name)
{
    size_t i;
    for (i = 0; i < sizeof(tx_attr_names) / sizeof(tx_attr_names[0]); i++) {
        if (strcmp(name, tx_attr_names[i]) == 0) {
            if (!tx_attr_keys[i]) tx_attr_keys[i] = PyUnicode_InternFromString(name);
            if (!tx_attr_keys[i]) return NULL;
            return PyObject_GetAttr(o, tx_attr_keys[i]);
        }
    }
    return PyObject_GetAttrString(o, name);
}
typedef struct { PyObject *object; double first, second; } TxSort;
static void tx_merge_sort(TxSort *data, TxSort *scratch, Py_ssize_t lo, Py_ssize_t hi)
{
    Py_ssize_t mid, i, j, k;
    if (hi - lo < 2) return;
    mid = lo + (hi - lo) / 2;
    tx_merge_sort(data, scratch, lo, mid); tx_merge_sort(data, scratch, mid, hi);
    i = lo; j = mid; k = lo;
    while (i < mid && j < hi) {
        int right = data[j].first < data[i].first ||
            (data[j].first == data[i].first && data[j].second < data[i].second);
        scratch[k++] = right ? data[j++] : data[i++];
    }
    while (i < mid) scratch[k++] = data[i++];
    while (j < hi) scratch[k++] = data[j++];
    for (i = lo; i < hi; i++) data[i] = scratch[i];
}
typedef struct { PyObject **items; Py_ssize_t size, capacity; } TxArena;
static PyObject *tx_hold(TxArena *a, PyObject *v)
{
    if (!v) return NULL;
    if (a->size == a->capacity) {
        Py_ssize_t cap = a->capacity ? a->capacity * 2 : 32;
        PyObject **p = PyMem_Realloc(a->items, (size_t)cap * sizeof(*p));
        if (!p) { Py_DECREF(v); return PyErr_NoMemory(); }
        a->items = p; a->capacity = cap;
    }
    a->items[a->size++] = v;
    return v;
}
static void tx_reset(TxArena *a, Py_ssize_t mark)
{ while (a->size > mark) Py_DECREF(a->items[--a->size]); }
static PyObject *tx_done(TxArena *a, PyObject *result)
{
    Py_XINCREF(result); tx_reset(a, 0); PyMem_Free(a->items); return result;
}
static PyObject *tx_bail(void)
{ PyErr_SetString(ct_bailout, "unsupported table numeric input"); return NULL; }
/* Exact built-in numbers only. Bounded integers avoid loss in squared axes. */
static int tx_double(PyObject *v, double *out)
{
    if (!v) return -1;
    if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v)) { tx_bail(); return -1; }
    *out = PyFloat_AsDouble(v);
    if (PyErr_Occurred()) {
        if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
            PyErr_Clear(); PyErr_SetString(ct_bailout, "coordinate requires Python arithmetic");
        }
        return -1;
    }
    if (!isfinite(*out) || fabs(*out) > 1e100 ||
            (PyLong_CheckExact(v) && fabs(*out) > 67108864.0)) {
        tx_bail(); return -1;
    }
    return 0;
}
static int tx_attr_double(PyObject *o, const char *name, double *out)
{
    PyObject *v = tx_getattr(o, name);
    int rc;
    if (!v) return -1;
    rc = tx_double(v, out); Py_DECREF(v); return rc;
}
static PyObject *tx_item(PyObject *seq, Py_ssize_t i)
{
    if (PyList_Check(seq)) return PyList_GetItem(seq, i);
    if (PyTuple_Check(seq)) return PyTuple_GetItem(seq, i);
    tx_bail(); return NULL;
}
static int tx_number(PyObject *seq, Py_ssize_t i, double *out)
{ return tx_double(tx_item(seq, i), out); }
static PyObject *tx_attr_default(PyObject *o, const char *name, double fallback)
{
    PyObject *v = tx_getattr(o, name);
    if (!v && PyErr_ExceptionMatches(PyExc_AttributeError)) {
        PyErr_Clear(); v = PyFloat_FromDouble(fallback);
    }
    return v;
}
static int tx_axes(PyObject *f, double out[4])
{
    double dx, dy, ux, uy, scale, uscale;
    PyObject *u, *v;
    int ok; volatile double two = 2.0, half = 0.5;
    if (tx_attr_double(f, "dir_x", &dx) < 0 || tx_attr_double(f, "dir_y", &dy) < 0) return -1;
    u = tx_attr_default(f, "up_x", 0.0); v = tx_attr_default(f, "up_y", 1.0);
    ok = tx_double(u, &ux) == 0 && tx_double(v, &uy) == 0;
    Py_XDECREF(u); Py_XDECREF(v);
    if (!ok) return -1;
    scale = pow(pow(dx, two) + pow(dy, two), half);
    if (scale) { out[0] = dx / scale; out[1] = dy / scale; }
    else { out[0] = 1.0; out[1] = 0.0; }
    uscale = pow(pow(ux, two) + pow(uy, two), half);
    if (uscale) { out[2] = ux / uscale; out[3] = uy / uscale; }
    else { out[2] = -out[1]; out[3] = out[0]; }
    return 0;
}
static int tx_point(PyObject *f, const double axes[4], double *x, double *y)
{
    double fx, fy, width, size;
    if (tx_attr_double(f, "x", &fx) < 0 || tx_attr_double(f, "y", &fy) < 0 ||
            tx_attr_double(f, "width", &width) < 0 || tx_attr_double(f, "size", &size) < 0) return -1;
    *x = fx + axes[0] * width / 2 + axes[2] * 0.35 * size;
    *y = fy + axes[1] * width / 2 + axes[3] * 0.35 * size;
    return 0;
}
static PyObject *ct_reference_axes(PyObject *self, PyObject *args)
{
    PyObject *f; double a[4]; (void)self;
    if (!PyArg_ParseTuple(args, "O", &f) || tx_axes(f, a) < 0) return NULL;
    return Py_BuildValue("(dddd)", a[0], a[1], a[2], a[3]);
}
static PyObject *ct_reference_point(PyObject *self, PyObject *args)
{
    PyObject *f, *axes = Py_None; double a[4], x, y; int i; (void)self;
    if (!PyArg_ParseTuple(args, "O|O", &f, &axes)) return NULL;
    if (axes == Py_None) { if (tx_axes(f, a) < 0) return NULL; }
    else for (i = 0; i < 4; i++) if (tx_number(axes, i, &a[i]) < 0) return NULL;
    if (tx_point(f, a, &x, &y) < 0) return NULL;
    return Py_BuildValue("(dd)", x, y);
}
static PyObject *ct_reading_key(PyObject *self, PyObject *args)
{
    PyObject *f, *x = NULL, *y = NULL, *first = NULL, *second = NULL, *out = NULL;
    double dx, dy; (void)self;
    if (!PyArg_ParseTuple(args, "O", &f)) return NULL;
    if (tx_attr_double(f, "dir_x", &dx) < 0 || tx_attr_double(f, "dir_y", &dy) < 0) return NULL;
    x = tx_getattr(f, "x"); y = tx_getattr(f, "y");
    if (!x || !y) goto done;
    if (fabs(dx) >= fabs(dy)) {
        if (dx >= 0) { first = PyNumber_Negative(y); second = x; Py_INCREF(second); }
        else { first = y; Py_INCREF(first); second = PyNumber_Negative(x); }
    } else if (dy < 0) { first = PyNumber_Negative(x); second = PyNumber_Negative(y); }
    else { first = x; second = y; Py_INCREF(first); Py_INCREF(second); }
    if (first && second) out = PyTuple_Pack(2, first, second);
done:
    Py_XDECREF(x); Py_XDECREF(y); Py_XDECREF(first); Py_XDECREF(second); return out;
}
static PyObject *ct_fragment_index(PyObject *self, PyObject *args)
{
    TxArena a = {0}; PyObject *fs, *points, *ys, *result = NULL;
    TxSort *data = NULL, *scratch = NULL;
    Py_ssize_t i, n, mark; double axes[4], previous[4] = {0}, key[4], x, y; int have = 0, j;
    (void)self;
    if (!PyArg_ParseTuple(args, "O", &fs)) return NULL;
    n = PySequence_Size(fs); if (n < 0) return NULL;
    if ((size_t)n > SIZE_MAX / sizeof(*data)) return PyErr_NoMemory();
    data = PyMem_Malloc((size_t)(n ? n : 1) * sizeof(*data));
    if (data) memset(data, 0, (size_t)(n ? n : 1) * sizeof(*data));
    scratch = PyMem_Malloc((size_t)(n ? n : 1) * sizeof(*scratch));
    if (!data || !scratch) { PyErr_NoMemory(); goto done; }
    points = tx_hold(&a, PyList_New(0)); ys = tx_hold(&a, PyList_New(0));
    if (!points || !ys) goto done;
    mark = a.size;
    for (i = 0; i < n; i++) {
        PyObject *f = tx_item(fs, i), *u, *v, *point;
        if (!f || tx_attr_double(f, "dir_x", key) < 0 || tx_attr_double(f, "dir_y", key + 1) < 0) goto done;
        u = tx_hold(&a, tx_attr_default(f, "up_x", 0.0)); v = tx_hold(&a, tx_attr_default(f, "up_y", 1.0));
        if (tx_double(u, key + 2) < 0 || tx_double(v, key + 3) < 0) goto done;
        if (!have || key[0] != previous[0] || key[1] != previous[1] || key[2] != previous[2] || key[3] != previous[3]) {
            if (tx_axes(f, axes) < 0) goto done;
            for (j = 0; j < 4; j++) previous[j] = key[j];
            have = 1;
        }
        if (tx_point(f, axes, &x, &y) < 0) goto done;
        point = tx_hold(&a, Py_BuildValue("(dd)", x, y)); if (!point) goto done;
        data[i].object = PyTuple_Pack(2, point, f); if (!data[i].object) goto done;
        data[i].first = y; data[i].second = 0;
        tx_reset(&a, mark);
    }
    tx_merge_sort(data, scratch, 0, n);
    for (i = 0; i < n; i++) {
        PyObject *pair = data[i].object;
        if (PyList_Append(points, pair) < 0 || PyList_Append(ys, PyTuple_GetItem(PyTuple_GetItem(pair, 0), 1)) < 0) goto done;
    }
    result = tx_hold(&a, PyTuple_Pack(2, points, ys));
done:
    if (data) for (i = 0; i < n; i++) Py_XDECREF(data[i].object);
    PyMem_Free(data); PyMem_Free(scratch);
    return tx_done(&a, result);
}
static Py_ssize_t tx_bisect(PyObject *seq, double v, int right, int reverse)
{
    Py_ssize_t lo = 0, n = PySequence_Size(seq), hi = n;
    if (n < 0) return -1;
    while (lo < hi) {
        Py_ssize_t mid = lo + (hi - lo) / 2; double x;
        if (tx_number(seq, reverse ? n - 1 - mid : mid, &x) < 0) return -1;
        if (right ? v < x : x >= v) hi = mid; else lo = mid + 1;
    }
    return lo;
}
static PyObject *tx_inside_index(PyObject *args, int any)
{
    PyObject *index, *box, *points, *ys, *out;
    Py_ssize_t lo, hi, i; double left, bottom, right, top;
    if (!PyArg_ParseTuple(args, "OO", &index, &box)) return NULL;
    points = tx_item(index, 0); ys = tx_item(index, 1);
    if (!points || !ys || tx_number(box, 0, &left) < 0 || tx_number(box, 1, &bottom) < 0 ||
        tx_number(box, 2, &right) < 0 || tx_number(box, 3, &top) < 0) return NULL;
    lo = tx_bisect(ys, bottom, 0, 0); hi = tx_bisect(ys, top, 1, 0);
    if (lo < 0 || hi < 0) return NULL;
    out = PyList_New(0); if (!out) return NULL;
    for (i = lo; i < hi; i++) {
        PyObject *pair = tx_item(points, i), *p; double x;
        if (!pair || !(p = tx_item(pair, 0)) || tx_number(p, 0, &x) < 0) { Py_DECREF(out); return NULL; }
        if (left <= x && x <= right) {
            if (any) { Py_DECREF(out); Py_RETURN_TRUE; }
            if (PyList_Append(out, tx_item(pair, 1)) < 0) { Py_DECREF(out); return NULL; }
        }
    }
    if (any) { Py_DECREF(out); Py_RETURN_FALSE; }
    return out;
}
static PyObject *ct_fragments_inside(PyObject *self, PyObject *args)
{ (void)self; return tx_inside_index(args, 0); }
static PyObject *ct_has_fragment_inside(PyObject *self, PyObject *args)
{ (void)self; return tx_inside_index(args, 1); }
static PyObject *tx_lines(PyObject *self, PyObject *fs, PyObject *cache)
{
    TxArena a = {0}; PyObject *key, *ordered, *content, *native, *result = NULL;
    TxSort *data = NULL, *scratch = NULL;
    Py_ssize_t i, n = PySequence_Size(fs);
    (void)self;
    if (n < 0) return NULL;
    key = tx_hold(&a, PyTuple_New(n)); if (!key) goto done;
    for (i = 0; i < n; i++) {
        PyObject *f = tx_item(fs, i), *id;
        if (!f) goto done;
        id = PyLong_FromVoidPtr(f); if (!id) goto done;
        if (PyTuple_SetItem(key, i, id) < 0) goto done;
    }
    if (cache != Py_None) {
        PyObject *cached = PyDict_GetItemWithError(cache, key);
        if (PyErr_Occurred()) goto done;
        if (cached) { result = cached; goto done; }
    }
    if ((size_t)n > SIZE_MAX / sizeof(*data)) { PyErr_NoMemory(); goto done; }
    data = PyMem_Malloc((size_t)(n ? n : 1) * sizeof(*data));
    scratch = PyMem_Malloc((size_t)(n ? n : 1) * sizeof(*scratch));
    if (!data || !scratch) { PyErr_NoMemory(); goto done; }
    ordered = tx_hold(&a, PyList_New(0)); if (!ordered) goto done;
    for (i = 0; i < n; i++) {
        PyObject *f = tx_item(fs, i); double x, y, dx, dy;
        if (!f || tx_attr_double(f, "x", &x) < 0 || tx_attr_double(f, "y", &y) < 0 ||
                tx_attr_double(f, "dir_x", &dx) < 0 || tx_attr_double(f, "dir_y", &dy) < 0) goto done;
        data[i].object = f;
        if (fabs(dx) >= fabs(dy)) {
            data[i].first = dx >= 0 ? -y : y; data[i].second = dx >= 0 ? x : -x;
        } else {
            data[i].first = dy < 0 ? -x : x; data[i].second = dy < 0 ? -y : y;
        }
    }
    tx_merge_sort(data, scratch, 0, n);
    for (i = 0; i < n; i++) if (PyList_Append(ordered, data[i].object) < 0) goto done;
    content = tx_hold(&a, PyImport_ImportModule("dochan.pdf.content")); if (!content) goto done;
    native = tx_hold(&a, tx_getattr(content, "_c_assemble_lines")); if (!native) goto done;
    if (native != Py_None) {
        PyObject *line = tx_hold(&a, tx_getattr(content, "_Line"));
        PyObject *segment = tx_hold(&a, tx_getattr(content, "_Segment"));
        PyObject *fragment = tx_hold(&a, tx_getattr(content, "Fragment"));
        PyObject *tolerance = tx_hold(&a, tx_getattr(content, "_LINE_Y_TOLERANCE"));
        if (!line || !segment || !fragment || !tolerance) goto done;
        result = tx_hold(&a, PyObject_CallFunctionObjArgs(native, ordered, line, segment, fragment, tolerance, NULL));
        if (!result) goto done;
    }
    if (!result || result == Py_None) {
        PyObject *fallback = tx_hold(&a, tx_getattr(content, "assemble_lines"));
        if (!fallback) { result = NULL; goto done; }
        result = tx_hold(&a, PyObject_CallFunctionObjArgs(fallback, ordered, NULL));
        if (!result) goto done;
    }
    if (cache != Py_None && PyObject_SetItem(cache, key, result) < 0) result = NULL;
done:
    PyMem_Free(data); PyMem_Free(scratch); return tx_done(&a, result);
}
static PyObject *ct_cell_lines(PyObject *self, PyObject *args)
{
    PyObject *fs, *cache;
    if (!PyArg_ParseTuple(args, "OO", &fs, &cache)) return NULL;
    return tx_lines(self, fs, cache);
}
/* Borrowed dict value, creating the list on its first insertion. */
static PyObject *tx_bucket(PyObject *dict, PyObject *key)
{
    PyObject *value = PyDict_GetItemWithError(dict, key);
    if (!value && !PyErr_Occurred()) {
        value = PyList_New(0); if (!value) return NULL;
        if (PyDict_SetItem(dict, key, value) < 0) { Py_DECREF(value); return NULL; }
        Py_DECREF(value); value = PyDict_GetItemWithError(dict, key);
    }
    return value;
}
static PyObject *tx_defaultdict(void)
{
    PyObject *m = PyImport_ImportModule("collections"), *cls, *result;
    if (!m) return NULL;
    cls = tx_getattr(m, "defaultdict"); Py_DECREF(m);
    if (!cls) return NULL;
    result = PyObject_CallFunctionObjArgs(cls, (PyObject *)&PyList_Type, NULL);
    Py_DECREF(cls); return result;
}
static int tx_reference(PyObject *f, PyObject *references, double *x, double *y)
{
    double axes[4];
    if (references != Py_None) {
        PyObject *key = PyLong_FromVoidPtr(f), *point; int rc;
        if (!key) return -1;
        point = PyObject_GetItem(references, key); Py_DECREF(key);
        if (!point) return -1;
        rc = tx_number(point, 0, x) < 0 || tx_number(point, 1, y) < 0;
        Py_DECREF(point); return rc ? -1 : 0;
    }
    if (tx_axes(f, axes) < 0) return -1;
    return tx_point(f, axes, x, y);
}
static int tx_horizontal_line(PyObject *line, int only_ltr)
{
    PyObject *direction = tx_getattr(line, "direction"); int ltr, rtl = 0;
    if (!direction) return -1;
    if (!PyUnicode_Check(direction)) {
        Py_DECREF(direction); PyErr_SetString(PyExc_TypeError, "line direction must be str"); return -1;
    }
    ltr = PyUnicode_CompareWithASCIIString(direction, "ltr");
    if (!only_ltr) rtl = PyUnicode_CompareWithASCIIString(direction, "rtl");
    Py_DECREF(direction);
    if (PyErr_Occurred()) return -1;
    return !ltr || (!only_ltr && !rtl);
}
static PyObject *ct_assign_text(PyObject *self, PyObject *args)
{
    TxArena a = {0}; PyObject *grid, *owners, *boxes, *xs, *ys, *fs, *page;
    PyObject *breaks = Py_None, *refs = Py_None, *cache = Py_None;
    PyObject *by_cell, *consumed, *events, *layout, *merge, *result = NULL;
    Py_ssize_t n, nx, ny, rows, i, pos = 0, mark;
    PyObject *key, *frags;
    if (!PyArg_ParseTuple(args, "OOOOOOO|OOO", &grid, &owners, &boxes, &xs, &ys, &fs, &page, &breaks, &refs, &cache)) return NULL;
    n = PySequence_Size(fs); nx = PySequence_Size(xs); ny = PySequence_Size(ys); rows = PySequence_Size(grid);
    if (n < 0 || nx < 1 || ny < 1 || rows < 0) { if (!PyErr_Occurred()) tx_bail(); return NULL; }
    by_cell = tx_hold(&a, PyDict_New()); consumed = tx_hold(&a, PySet_New(NULL)); events = tx_hold(&a, tx_defaultdict());
    layout = tx_hold(&a, PyImport_ImportModule("dochan.pdf.layout"));
    if (!by_cell || !consumed || !events || !layout) goto done;
    merge = tx_hold(&a, tx_getattr(layout, "merge_lines")); if (!merge) goto done;
    mark = a.size;
    for (i = 0; i < n; i++) {
        PyObject *f = tx_item(fs, i), *box, *order, *bucket;
        Py_ssize_t c, r, iy; double x, y, left, bottom, right, top;
        if (!f || tx_reference(f, refs, &x, &y) < 0) goto done;
        c = tx_bisect(xs, x, 1, 0); iy = tx_bisect(ys, y, 1, 1);
        if (c < 0 || iy < 0) goto done;
        c--; r = ny - 1 - iy;
        if (c < 0 || c >= nx - 1 || r < 0 || r >= rows) continue;
        key = tx_item(owners, r * (nx - 1) + c); if (!key) goto done;
        box = tx_hold(&a, PyObject_GetItem(boxes, key)); if (!box) goto done;
        if (tx_number(box, 0, &left) < 0 || tx_number(box, 1, &bottom) < 0 ||
            tx_number(box, 2, &right) < 0 || tx_number(box, 3, &top) < 0) goto done;
        if (left + .5 <= x && x <= right - .5 && bottom + .5 <= y && y <= top - .5) {
            bucket = tx_bucket(by_cell, key); if (!bucket || PyList_Append(bucket, f) < 0) goto done;
            order = tx_hold(&a, tx_getattr(f, "order"));
            if (!order || PySet_Add(consumed, order) < 0) goto done;
        }
        tx_reset(&a, mark);
    }
    while (PyDict_Next(by_cell, &pos, &key, &frags)) {
        PyObject *lines = tx_hold(&a, tx_lines(self, frags, cache)), *box, *groups, *group, *bounds, *cuts = NULL;
        Py_ssize_t j, count; double left, right;
        if (!lines) goto done;
        box = tx_hold(&a, PyObject_GetItem(boxes, key));
        if (!box || tx_number(box, 0, &left) < 0 || tx_number(box, 2, &right) < 0) goto done;
        groups = tx_hold(&a, PyList_New(0)); group = tx_hold(&a, PyList_New(0));
        if (!groups || !group || PyList_Append(groups, group) < 0) goto done;
        if (breaks != Py_None) { cuts = PyDict_GetItemWithError(breaks, key); if (!cuts && PyErr_Occurred()) goto done; }
        count = PySequence_Size(lines); if (count < 0) goto done;
        for (j = 0; j < count; j++) {
            PyObject *line = tx_item(lines, j); int horizontal;
            if (!line) goto done;
            if (PyList_Size(group) && cuts) {
                horizontal = tx_horizontal_line(line, 0); if (horizontal < 0) goto done;
                if (horizontal) {
                    double y, last; Py_ssize_t k, nc = PySequence_Size(cuts);
                    if (nc < 0 || tx_attr_double(line, "y", &y) < 0 ||
                        tx_attr_double(PyList_GetItem(group, PyList_Size(group) - 1), "y", &last) < 0) goto done;
                    for (k = 0; k < nc; k++) {
                        double cut; if (tx_number(cuts, k, &cut) < 0) goto done;
                        if (y < cut && cut <= last) {
                            group = tx_hold(&a, PyList_New(0));
                            if (!group || PyList_Append(groups, group) < 0) goto done;
                            break;
                        }
                    }
                }
            }
            if (PyList_Append(group, line) < 0) goto done;
        }
        bounds = tx_hold(&a, Py_BuildValue("(dd)", left + .5, right - .5)); if (!bounds) goto done;
        for (j = 0; j < PyList_Size(groups); j++) {
            PyObject *blocks = tx_hold(&a, ly_merge(PyList_GetItem(groups, j), bounds, layout));
            Py_ssize_t k, nb;
            if (!blocks) goto done;
            nb = PySequence_Size(blocks); if (nb < 0) goto done;
            for (k = 0; k < nb; k++) {
                PyObject *block = tx_item(blocks, k), *y, *order, *paragraph, *event, *bucket;
                if (!block) goto done;
                y = tx_hold(&a, tx_getattr(block, "y"));
                order = tx_hold(&a, tx_getattr(block, "order"));
                paragraph = tx_hold(&a, ly_paragraph(block, page, layout));
                if (!y || !order || !paragraph) goto done;
                event = tx_hold(&a, Py_BuildValue("(OiOO)", y, 0, order, paragraph)); bucket = tx_bucket(events, key);
                if (!event || !bucket || PyList_Append(bucket, event) < 0) goto done;
            }
        }
        tx_reset(&a, mark);
    }
    result = tx_hold(&a, PyTuple_Pack(2, consumed, events));
done: return tx_done(&a, result);
}
static int tx_runs(PyObject *source, PyObject *dest)
{
    Py_ssize_t i, n = PySequence_Size(source);
    if (n < 0) return -1;
    for (i = 0; i < n; i++) {
        PyObject *line = tx_item(source, i), *coord, *lo, *hi, *span, *bucket;
        if (!line || !(coord = tx_item(line, 0)) || !(lo = tx_item(line, 1)) || !(hi = tx_item(line, 2))) return -1;
        span = PyTuple_Pack(2, lo, hi); if (!span) return -1;
        bucket = tx_bucket(dest, coord);
        if (!bucket || PyList_Append(bucket, span) < 0) { Py_DECREF(span); return -1; }
        Py_DECREF(span);
    }
    return 0;
}
static int tx_coverage(PyObject *self, PyObject *runs, PyObject *key, PyObject *lo, PyObject *hi, PyObject *tolerance)
{
    PyObject *bucket = tx_bucket(runs, key), *args, *out; int rc;
    if (!bucket) return -1;
    args = PyTuple_Pack(4, bucket, lo, hi, tolerance); if (!args) return -1;
    out = ct_covered(self, args); Py_DECREF(args); if (!out) return -1;
    rc = PyObject_IsTrue(out); Py_DECREF(out); return rc;
}
static int tx_numeric_column(PyObject *lines, PyObject *number)
{
    Py_ssize_t i, n = PySequence_Size(lines);
    if (n < 0) return -1;
    (void)number;
    if (n < 2) return 0;
    for (i = 0; i < n; i++) {
        PyObject *line = tx_item(lines, i), *text; int ok;
        if (!line) return -1;
        ok = tx_horizontal_line(line, 1); if (ok <= 0) return ok;
        text = tx_getattr(line, "text"); if (!text) return -1;
        ok = ly_numeric_text(text); Py_DECREF(text);
        if (ok <= 0) return ok;
    }
    return 1;
}
static PyObject *ct_numeric_row_rules(PyObject *self, PyObject *args)
{
    TxArena a = {0}; PyObject *horizontal, *vertical, *xs, *ys, *fs, *tolerance;
    PyObject *refs = Py_None, *cache = Py_None, *mod, *number, *h_runs, *v_runs, *bands, *additions;
    PyObject *limit, *result = NULL;
    Py_ssize_t nx, ny, nf, i, band, mark; long checks, cells; double tol, left, right;
    if (!PyArg_ParseTuple(args, "OOOOOO|OO", &horizontal, &vertical, &xs, &ys, &fs, &tolerance, &refs, &cache)) return NULL;
    nx = PySequence_Size(xs); ny = PySequence_Size(ys); nf = PySequence_Size(fs);
    if (nx < 0 || ny < 0 || nf < 0) return NULL;
    mod = tx_hold(&a, PyImport_ImportModule("dochan.pdf.tables")); if (!mod) goto done;
    limit = tx_hold(&a, tx_getattr(mod, "MAX_INTERSECTION_CHECKS")); if (!limit) goto done;
    checks = PyLong_AsLong(limit); if (PyErr_Occurred()) goto done;
    limit = tx_hold(&a, tx_getattr(mod, "MAX_PAGE_CELLS")); if (!limit) goto done;
    cells = PyLong_AsLong(limit); if (PyErr_Occurred()) goto done;
    if (nx < 4 || checks < 0 || cells < 0 || (ny && nf > checks / ny) || (ny && nx > cells / ny)) {
        result = tx_hold(&a, PyTuple_Pack(2, horizontal, ys)); goto done;
    }
    if (ny < 1) { PyErr_SetString(PyExc_ValueError, "ys must not be empty"); goto done; }
    if (tx_double(tolerance, &tol) < 0 || tx_number(xs, 0, &left) < 0 || tx_number(xs, nx - 1, &right) < 0) goto done;
    number = tx_hold(&a, tx_getattr(mod, "_NUMBER"));
    if (!number) goto done;
    {
        PyObject *pattern = tx_hold(&a, tx_getattr(number, "pattern"));
        PyObject *flags = tx_hold(&a, tx_getattr(number, "flags"));
        PyObject *expected = tx_hold(&a, PyUnicode_FromString(
            "[+\xe2\x88\x92-]?\\d[\\d,]*(?:\\.\\d+)?%?"));
        int equal;
        if (!pattern || !flags || !expected) goto done;
        equal = PyObject_RichCompareBool(pattern, expected, Py_EQ);
        if (equal < 0) goto done;
        if (!equal || PyLong_AsLong(flags) != 32) { tx_bail(); goto done; }
    }
    h_runs = tx_hold(&a, PyDict_New()); v_runs = tx_hold(&a, PyDict_New());
    bands = tx_hold(&a, PyDict_New()); additions = tx_hold(&a, PyList_New(0));
    if (!number || !h_runs || !v_runs || !bands || !additions) goto done;
    if (tx_runs(horizontal, h_runs) < 0 || tx_runs(vertical, v_runs) < 0) goto done;
    mark = a.size;
    for (i = 0; i < nf; i++) {
        PyObject *f = tx_item(fs, i), *key, *pair, *bucket;
        double x, y, top, bottom; Py_ssize_t iy, column;
        if (!f || tx_reference(f, refs, &x, &y) < 0) goto done;
        iy = tx_bisect(ys, y, 1, 1); if (iy < 0) goto done;
        band = ny - 1 - iy;
        if (band < 0 || band >= ny - 1) continue;
        if (tx_number(ys, band, &top) < 0 || tx_number(ys, band + 1, &bottom) < 0) goto done;
        if (!(bottom + .5 < y && y < top - .5 && left + .5 < x && x < right - .5)) continue;
        column = tx_bisect(xs, x, 1, 0); if (column < 0) goto done;
        key = tx_hold(&a, PyLong_FromSsize_t(band));
        pair = tx_hold(&a, Py_BuildValue("(nO)", column - 1, f));
        if (!key || !pair) goto done;
        bucket = tx_bucket(bands, key); if (!bucket || PyList_Append(bucket, pair) < 0) goto done;
        tx_reset(&a, mark);
    }
    for (band = 0; band < ny - 1; band++) {
        PyObject *top = tx_item(ys, band), *bottom = tx_item(ys, band + 1);
        PyObject *columns, *lines, *numeric, *key, *pairs, *reference, *boundaries;
        Py_ssize_t j, k, nr; double row_tol, min_size = 0; int ok, valid = 1;
        if (!top || !bottom) goto done;
        ok = tx_coverage(self, h_runs, top, tx_item(xs, 0), tx_item(xs, nx - 1), tolerance);
        if (ok < 0) goto done;
        if (!ok) continue;
        ok = tx_coverage(self, h_runs, bottom, tx_item(xs, 0), tx_item(xs, nx - 1), tolerance);
        if (ok < 0) goto done;
        if (!ok) continue;
        for (j = 1; j < nx - 1; j++) {
            ok = tx_coverage(self, v_runs, tx_item(xs, j), bottom, top, tolerance);
            if (ok < 0) goto done;
            if (!ok) { valid = 0; break; }
        }
        if (!valid) continue;
        columns = tx_hold(&a, PyDict_New()); lines = tx_hold(&a, PyList_New(0)); numeric = tx_hold(&a, PyList_New(0));
        key = tx_hold(&a, PyLong_FromSsize_t(band));
        if (!columns || !lines || !numeric || !key) goto done;
        pairs = tx_bucket(bands, key); if (!pairs) goto done;
        for (j = 0; j < PyList_Size(pairs); j++) {
            PyObject *pair = PyList_GetItem(pairs, j), *bucket = tx_bucket(columns, PyTuple_GetItem(pair, 0));
            if (!bucket || PyList_Append(bucket, PyTuple_GetItem(pair, 1)) < 0) goto done;
        }
        for (j = 0; j < nx - 1; j++) {
            PyObject *column, *assembled;
            key = tx_hold(&a, PyLong_FromSsize_t(j)); if (!key) goto done;
            column = tx_bucket(columns, key); if (!column) goto done;
            assembled = tx_hold(&a, tx_lines(self, column, cache));
            if (!assembled || PyList_Append(lines, assembled) < 0) goto done;
            ok = tx_numeric_column(assembled, number); if (ok < 0) goto done;
            if (ok && PyList_Append(numeric, assembled) < 0) goto done;
        }
        if (PyList_Size(numeric) < 3 || PyList_Size(numeric) * 2 < PyList_Size(lines)) { tx_reset(&a, mark); continue; }
        reference = PyList_GetItem(numeric, 0); nr = PySequence_Size(reference);
        if (nr < 0) goto done;
        if (nr > 500) { tx_reset(&a, mark); continue; }
        for (j = 0; j < nr; j++) {
            double size; if (tx_attr_double(tx_item(reference, j), "size", &size) < 0) goto done;
            if (!j || size < min_size) min_size = size;
        }
        row_tol = min_size * .2; if (tol < row_tol) row_tol = tol;
        if (row_tol <= 0) { tx_reset(&a, mark); continue; }
        for (j = 0; j < PyList_Size(numeric); j++) {
            PyObject *column = PyList_GetItem(numeric, j);
            if (PySequence_Size(column) != nr) { valid = 0; break; }
            for (k = 0; k < nr; k++) {
                double y1, y2;
                if (tx_attr_double(tx_item(reference, k), "y", &y1) < 0 || tx_attr_double(tx_item(column, k), "y", &y2) < 0) goto done;
                if (fabs(y1 - y2) > row_tol) { valid = 0; break; }
            }
            if (!valid) break;
        }
        if (!valid) { tx_reset(&a, mark); continue; }
        for (j = 0; j < PyList_Size(lines); j++) {
            PyObject *column = PyList_GetItem(lines, j);
            for (k = 0; k < PySequence_Size(column); k++) {
                PyObject *line = tx_item(column, k); Py_ssize_t t; double y;
                ok = tx_horizontal_line(line, 1); if (ok < 0) goto done;
                if (!ok) { valid = 0; break; }
                if (tx_attr_double(line, "y", &y) < 0) goto done;
                ok = 0;
                for (t = 0; t < nr; t++) {
                    double baseline; if (tx_attr_double(tx_item(reference, t), "y", &baseline) < 0) goto done;
                    if (fabs(y - baseline) <= row_tol) { ok = 1; break; }
                }
                if (!ok) { valid = 0; break; }
            }
            if (!valid) break;
        }
        if (!valid) { tx_reset(&a, mark); continue; }
        boundaries = tx_hold(&a, PyList_New(0)); if (!boundaries) goto done;
        for (j = 0; j < nr - 1; j++) {
            PyObject *upper = tx_item(reference, j), *lower = tx_item(reference, j + 1), *boundary;
            double uy, ly, us, ls, largest;
            if (tx_attr_double(upper, "y", &uy) < 0 || tx_attr_double(lower, "y", &ly) < 0 ||
                tx_attr_double(upper, "size", &us) < 0 || tx_attr_double(lower, "size", &ls) < 0) goto done;
            largest = us < ls ? ls : us;
            if (uy - ly < largest * 1.2) { valid = 0; break; }
            boundary = tx_hold(&a, Py_BuildValue("(dOO)", (uy + ly + ls) / 2, tx_item(xs, 0), tx_item(xs, nx - 1)));
            if (!boundary || PyList_Append(boundaries, boundary) < 0) goto done;
        }
        if (valid) for (j = 0; j < PyList_Size(boundaries); j++)
            if (PyList_Append(additions, PyList_GetItem(boundaries, j)) < 0) goto done;
        tx_reset(&a, mark);
    }
    if (!PyList_Size(additions)) result = tx_hold(&a, PyTuple_Pack(2, horizontal, ys));
    else {
        PyObject *hs = tx_hold(&a, PySequence_Concat(horizontal, additions));
        PyObject *coordinates = tx_hold(&a, PySet_New(ys)), *newys;
        if (!hs || !coordinates) goto done;
        for (i = 0; i < PyList_Size(additions); i++)
            if (PySet_Add(coordinates, PyTuple_GetItem(PyList_GetItem(additions, i), 0)) < 0) goto done;
        newys = tx_hold(&a, PySequence_List(coordinates)); if (!newys) goto done;
        if (PyList_Sort(newys) < 0 || PyList_Reverse(newys) < 0) goto done;
        result = tx_hold(&a, PyTuple_Pack(2, hs, newys));
    }
done: return tx_done(&a, result);
}
