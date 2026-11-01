/* Read-only mirror of PDFReader._body_groups event preparation.
 * Public anchor writes and line assembly remain in Python, in original order. */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <math.h>

static PyObject *bailout;
typedef struct { PyObject **items; Py_ssize_t n, cap; } Pool;
typedef struct { PyObject *order, *item; int kind; } Event;
static PyObject *keep(Pool *p, PyObject *v)
{
    if (!v) return NULL;
    if (p->n == p->cap) {
        Py_ssize_t cap = p->cap ? p->cap * 2 : 128;
        PyObject **items = PyMem_Realloc(p->items, (size_t)cap * sizeof(*items));
        if (!items) { Py_DECREF(v); return PyErr_NoMemory(); }
        p->items = items; p->cap = cap;
    }
    p->items[p->n++] = v;
    return v;
}
static void clear(Pool *p)
{
    while (p->n) Py_DECREF(p->items[--p->n]);
    PyMem_Free(p->items);
}
static PyObject *attr(Pool *p, PyObject *v, const char *name)
{
    static const char *names[8];
    static PyObject *keys[8];
    static int count;
    int i;
    for (i = 0; i < count; i++)
        if (names[i] == name) return keep(p, PyObject_GetAttr(v, keys[i]));
    if (count < 8) {
        PyObject *key = PyUnicode_InternFromString(name);
        if (!key) return NULL;
        names[count] = name; keys[count++] = key;
        return keep(p, PyObject_GetAttr(v, key));
    }
    return keep(p, PyObject_GetAttrString(v, name));
}
static int exact(PyObject *v, PyObject *type)
{
    PyObject *actual = PyObject_Type(v);
    int same = actual == type;
    Py_XDECREF(actual);
    return same;
}
static int numeric(PyObject *v)
{
    double value;
    if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v)) return 0;
    value = PyFloat_AsDouble(v);
    return !PyErr_Occurred() && isfinite(value);
}
static int before(Event *a, Event *b)
{
    int eq = PyObject_RichCompareBool(a->order, b->order, Py_EQ);
    if (eq < 0) return -1;
    if (eq) return a->kind <= b->kind;
    return PyObject_RichCompareBool(a->order, b->order, Py_LT);
}
/* Stable merge: equality always consumes the left input first. */
static int sort_events(Event *a, Event *tmp, Py_ssize_t lo, Py_ssize_t hi)
{
    Py_ssize_t mid, i, j, at;
    if (hi - lo < 2) return 0;
    mid = lo + (hi - lo) / 2;
    if (sort_events(a, tmp, lo, mid) || sort_events(a, tmp, mid, hi)) return -1;
    i = lo; j = mid; at = lo;
    while (i < mid && j < hi) {
        int first = before(&a[i], &a[j]);
        if (first < 0) return -1;
        tmp[at++] = first ? a[i++] : a[j++];
    }
    while (i < mid) tmp[at++] = a[i++];
    while (j < hi) tmp[at++] = a[j++];
    for (i = lo; i < hi; i++) a[i] = tmp[i];
    return 0;
}
static PyObject *partition(PyObject *self, PyObject *args)
{
    PyObject *fragments, *tables, *boundaries, *fragment_type, *table_type;
    PyObject *consumed, *anchors, *groups, *singles, *pending, *zero, *result = NULL;
    Pool pool = {NULL, 0, 0};
    Event *events = NULL, *tmp = NULL;
    Py_ssize_t nf, nt, nb, i, j, ne = 0;
    int allzero = 1;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOOO", &fragments, &tables, &boundaries,
                          &fragment_type, &table_type)) return NULL;
    if (!PyList_CheckExact(fragments) || !PyList_CheckExact(tables)
        || (!PyList_CheckExact(boundaries) && !PyTuple_CheckExact(boundaries))) goto unsupported;
    nf = PyList_Size(fragments); nt = PyList_Size(tables); nb = PySequence_Size(boundaries);
    if (nf > 1000000 || nt > 100000 || nb > 100000) goto unsupported;
    consumed = keep(&pool, PySet_New(NULL));
    anchors = keep(&pool, PyList_New(0));
    groups = keep(&pool, PyList_New(0));
    singles = keep(&pool, PyList_New(0));
    zero = keep(&pool, PyLong_FromLong(0));
    if (!consumed || !anchors || !groups || !singles || !zero) goto done;
    events = PyMem_Malloc((size_t)(nf + nt + nb + 1) * sizeof(*events));
    tmp = PyMem_Malloc((size_t)(nf + nt + nb + 1) * sizeof(*tmp));
    if (!events || !tmp) { PyErr_NoMemory(); goto done; }
    /* Validate every fragment before calculating anchors; no public writes. */
    for (i = 0; i < nf; i++) {
        PyObject *f = PyList_GetItem(fragments, i), *order, *size;
        if (!exact(f, fragment_type)) goto unsupported;
        order = attr(&pool, f, "order"); size = attr(&pool, f, "size");
        if (!order || !size) goto done;
        if (!PyLong_CheckExact(order) || (!PyLong_CheckExact(size) && !PyFloat_CheckExact(size))) goto unsupported;
        events[i] = (Event){order, f, 1};
        if (PyObject_RichCompareBool(size, zero, Py_EQ) != 1) allzero = 0;
    }
    for (i = 0; i < nt; i++) {
        PyObject *t = PyList_GetItem(tables, i), *orders, *anchor, *box, *iter, *v;
        int negative;
        if (!exact(t, table_type)) goto unsupported;
        orders = attr(&pool, t, "fragment_orders"); anchor = attr(&pool, t, "anchor_order");
        box = attr(&pool, t, "bbox");
        if (!orders || !anchor || !box) goto done;
        if (!exact(orders, (PyObject *)&PySet_Type) || !PyLong_CheckExact(anchor)
            || !PyTuple_CheckExact(box) || PyTuple_Size(box) != 4) goto unsupported;
        if (!numeric(PyTuple_GetItem(box, 3))) goto unsupported;
        iter = keep(&pool, PyObject_GetIter(orders));
        if (!iter) goto done;
        while ((v = PyIter_Next(iter))) {
            if (!PyLong_CheckExact(v)) { Py_DECREF(v); goto unsupported; }
            if (PySet_Add(consumed, v) < 0) { Py_DECREF(v); goto done; }
            Py_DECREF(v);
        }
        if (PyErr_Occurred()) goto done;
        negative = PyObject_RichCompareBool(anchor, zero, Py_LT);
        if (negative < 0) goto done;
        if (negative) {
            PyObject *assignment;
            anchor = keep(&pool, PyLong_FromSsize_t(nf));
            if (!anchor) goto done;
            for (j = 0; j < nf; j++) {
                PyObject *y = attr(&pool, PyList_GetItem(fragments, j), "y");
                int below;
                if (!y) goto done;
                if (!numeric(y)) goto unsupported;
                below = PyObject_RichCompareBool(y, PyTuple_GetItem(box, 3), Py_LT);
                /* y is the last pool entry and cannot escape this comparison.
                 * Retaining it until return would make an unmatched anchor scan
                 * keep O(number of tables * number of fragments) references. */
                Py_DECREF(pool.items[--pool.n]);
                if (below < 0) goto done;
                if (below) { anchor = events[j].order; break; }
            }
            assignment = keep(&pool, PyTuple_Pack(2, t, anchor));
            if (!assignment || PyList_Append(anchors, assignment) < 0) goto done;
        }
        events[nf + i] = (Event){anchor, t, 0};
    }
    for (i = 0; i < nf; i++) {
        int contains = PySet_Contains(consumed, events[i].order);
        if (contains < 0) goto done;
        if (!contains) {
            if (allzero && PyList_Append(singles, events[i].item) < 0) goto done;
            events[ne++] = events[i];
        }
    }
    for (i = 0; i < nt; i++) events[ne++] = events[nf + i];
    for (i = 0; i < nb; i++) {
        PyObject *order = keep(&pool, PySequence_GetItem(boundaries, i));
        if (!order) goto done;
        if (!PyLong_CheckExact(order)) goto unsupported;
        events[ne++] = (Event){order, Py_None, 0};
    }
    for (i = 1; i < ne; i++) {
        int ordered = before(&events[i - 1], &events[i]);
        if (ordered < 0) goto done;
        if (!ordered) break;
    }
    if (i < ne && sort_events(events, tmp, 0, ne)) goto done;
    pending = keep(&pool, PyList_New(0));
    if (!pending) goto done;
    for (i = 0; i < ne; i++) {
        if (events[i].kind) {
            if (PyList_Append(pending, events[i].item) < 0) goto done;
        } else {
            if (PyList_Append(groups, pending) < 0) goto done;
            pending = keep(&pool, PyList_New(0));
            if (!pending) goto done;
        }
    }
    if (PyList_Append(groups, pending) < 0) goto done;
    result = PyTuple_Pack(3, groups, anchors, allzero && nf ? singles : Py_None);
    goto done;
unsupported:
    PyErr_Clear();
    PyErr_SetString(bailout, "unsupported body partition input");
done:
    PyMem_Free(events); PyMem_Free(tmp); clear(&pool);
    return result;
}
static PyMethodDef methods[] = {
    {"partition", partition, METH_VARARGS, "Prepare stable body groups without public mutation."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_cbody", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__cbody(void)
{
    PyObject *m = PyModule_Create(&module);
    if (!m) return NULL;
    bailout = PyErr_NewException("dochan.pdf._cbody.Bailout", NULL, NULL);
    if (!bailout || PyModule_AddObject(m, "Bailout", bailout) < 0) {
        Py_XDECREF(bailout); Py_DECREF(m); return NULL;
    }
    return m;
}
