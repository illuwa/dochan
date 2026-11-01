/* Handwritten sized_runs mirror. Unicode and dataclass operations retain
 * Python semantics; sizes are owned objects, never coerced to doubles. */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <stdint.h>

static PyObject *bailout, *replace_fn;
static PyObject *paragraph_type, *run_type, *line_type, *segment_type, *namespace_type;
static int exact_type(PyObject *o, PyObject *expected)
{
    PyObject *type = PyObject_Type(o);
    int matches = type == expected;
    Py_XDECREF(type);
    return matches;
}
static int numeric(PyObject *o)
{ return PyFloat_CheckExact(o) || PyLong_CheckExact(o); }
typedef struct { PyObject **items; Py_ssize_t n, cap; } Pool;
static PyObject *keep(Pool *p, PyObject *o)
{
    if (!o) return NULL;
    if (p->n == p->cap) {
        Py_ssize_t cap = p->cap ? p->cap * 2 : 32;
        PyObject **items = PyMem_Realloc(p->items, (size_t)cap * sizeof(*items));
        if (!items) { Py_DECREF(o); return PyErr_NoMemory(); }
        p->items = items; p->cap = cap;
    }
    p->items[p->n++] = o;
    return o;
}
static void reset(Pool *p, Py_ssize_t mark)
{ while (p->n > mark) Py_DECREF(p->items[--p->n]); }
static int seq(PyObject *o)
{ return PyList_CheckExact(o) || PyTuple_CheckExact(o); }
static Py_ssize_t count(PyObject *o)
{ return PyList_CheckExact(o) ? PyList_Size(o) : PyTuple_Size(o); }
static PyObject *item(PyObject *o, Py_ssize_t i)
{ return PyList_CheckExact(o) ? PyList_GetItem(o, i) : PyTuple_GetItem(o, i); }
static int reject(void)
{ PyErr_SetString(bailout, "unsupported heading input"); return 0; }
static PyObject *attr(Pool *p, PyObject *o, const char *name)
{ return keep(p, PyObject_GetAttrString(o, name)); }
static PyObject *run_text(Pool *p, PyObject *owner)
{
    PyObject *runs, *texts, *empty;
    if (!exact_type(owner, line_type) && !exact_type(owner, segment_type)
            && !exact_type(owner, namespace_type)) { reject(); return NULL; }
    runs = attr(p, owner, "runs");
    Py_ssize_t i, n;
    if (!runs) return NULL;
    if (!seq(runs)) { reject(); return NULL; }
    n = count(runs);
    texts = keep(p, PyList_New(n));
    if (!texts) return NULL;
    for (i = 0; i < n; i++) {
        PyObject *run = item(runs, i), *text;
        if (!seq(run) || count(run) < 1) { reject(); return NULL; }
        text = item(run, 0);
        if (!PyUnicode_CheckExact(text)) { reject(); return NULL; }
        Py_INCREF(text);
        if (PyList_SetItem(texts, i, text) < 0) return NULL;
    }
    empty = keep(p, PyUnicode_FromString(""));
    return empty ? keep(p, PyUnicode_Join(empty, texts)) : NULL;
}
typedef struct { Py_ssize_t start, end; PyObject *size; } Span;
typedef struct { Span *items; Py_ssize_t n, cap; } Spans;
static int append_span(Spans *spans, Py_ssize_t start, Py_ssize_t end, PyObject *size)
{
    if (spans->n && spans->items[spans->n - 1].end == start) {
        PyObject *equal = PyObject_RichCompare(spans->items[spans->n - 1].size, size, Py_EQ);
        int eq;
        if (!equal) return 0;
        eq = PyObject_IsTrue(equal); Py_DECREF(equal);
        if (eq < 0) return 0;
        if (eq) {
            Span *last = &spans->items[spans->n - 1];
            Py_INCREF(size); Py_DECREF(last->size);
            last->end = end; last->size = size; return 1;
        }
    }
    if (spans->n == spans->cap) {
        Py_ssize_t cap = spans->cap ? spans->cap * 2 : 32;
        Span *items = PyMem_Realloc(spans->items, (size_t)cap * sizeof(*items));
        if (!items) { PyErr_NoMemory(); return 0; }
        spans->items = items; spans->cap = cap;
    }
    Py_INCREF(size);
    spans->items[spans->n++] = (Span){start, end, size};
    return 1;
}
static PyObject *replacement(Pool *p, PyObject *run, PyObject *text, PyObject *size)
{
    PyObject *args = keep(p, PyTuple_Pack(1, run));
    PyObject *kwargs = keep(p, PyDict_New());
    if (!args || !kwargs || PyDict_SetItemString(kwargs, "text", text) < 0) return NULL;
    if (size && PyDict_SetItemString(kwargs, "font_size_pt", size) < 0) return NULL;
    return keep(p, PyObject_Call(replace_fn, args, kwargs));
}
static PyObject *sized_runs(PyObject *self, PyObject *args)
{
    PyObject *paragraph, *lines, *sizes, *paragraph_text, *runs, *result = NULL, *answer = NULL;
    Pool pool = {NULL, 0, 0}; Spans spans = {NULL, 0, 0};
    Py_ssize_t i, j, offset = 0, position = 0, at = 0, base;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOO:sized_runs", &paragraph, &lines, &sizes)) return NULL;
    if (!exact_type(paragraph, paragraph_type)
            || !PyList_CheckExact(lines) || !PyDict_CheckExact(sizes)) { reject(); return NULL; }
    runs = attr(&pool, paragraph, "runs");
    if (!runs) goto done;
    if (!PyList_CheckExact(runs)) { reject(); goto done; }
    for (i = 0; i < PyList_Size(runs); i++) {
        PyObject *run = PyList_GetItem(runs, i), *text;
        if (!exact_type(run, run_type)) { reject(); goto done; }
        text = attr(&pool, run, "text");
        if (!text) goto done;
        if (!PyUnicode_CheckExact(text)) { reject(); goto done; }
    }
    paragraph_text = attr(&pool, paragraph, "text");
    if (!paragraph_text) goto done;
    if (!PyUnicode_CheckExact(paragraph_text)) { reject(); goto done; }
    base = pool.n;
    for (i = 0; i < PyList_Size(lines); i++) {
        PyObject *line = PyList_GetItem(lines, i), *text = run_text(&pool, line);
        PyObject *trimmed, *left_trimmed, *orders, *segments, *line_size;
        Py_ssize_t leading, length, cursor = 0, n;
        if (!text) goto done;
        trimmed = keep(&pool, PyObject_CallMethod(text, "strip", NULL));
        left_trimmed = keep(&pool, PyObject_CallMethod(text, "lstrip", NULL));
        orders = attr(&pool, line, "fragment_orders");
        segments = attr(&pool, line, "segments");
        line_size = attr(&pool, line, "size");
        if (!trimmed || !left_trimmed || !orders || !segments || !line_size) goto done;
        if (!numeric(line_size) || !seq(orders) || !seq(segments)) { reject(); goto done; }
        leading = PyUnicode_GetLength(text) - PyUnicode_GetLength(left_trimmed);
        length = PyUnicode_GetLength(trimmed);
        n = count(orders) < count(segments) ? count(orders) : count(segments);
        for (j = 0; j < n; j++) {
            Py_ssize_t mark = pool.n, end, start_at, end_at;
            PyObject *part = run_text(&pool, item(segments, j)), *size;
            if (!part) goto done;
            end = PyUnicode_Find(text, part, cursor, PyUnicode_GetLength(text), 1);
            if (end == -2) goto done;
            if (end < 0) goto original;
            end += PyUnicode_GetLength(part);
            start_at = cursor > leading ? cursor - leading : 0;
            end_at = end - leading < length ? end - leading : length;
            if (end_at > start_at) {
                if (!PyLong_CheckExact(item(orders, j))) { reject(); goto done; }
                size = PyDict_GetItemWithError(sizes, item(orders, j));
                if (!size) { if (PyErr_Occurred()) goto done; size = line_size; }
                if (!numeric(size)) { reject(); goto done; }
                if (offset > PY_SSIZE_T_MAX - end_at) { reject(); goto done; }
                if (!append_span(&spans, offset + start_at, offset + end_at, size)) goto done;
            }
            cursor = end;
            reset(&pool, mark);
        }
        if (offset > PY_SSIZE_T_MAX - length) { reject(); goto done; }
        offset += length;
        if (line != PyList_GetItem(lines, PyList_Size(lines) - 1)) {
            PyObject *char_text, *space;
            if (offset == PY_SSIZE_T_MAX) { reject(); goto done; }
            char_text = keep(&pool, PyUnicode_Substring(paragraph_text, offset, offset + 1));
            if (!char_text) goto done;
            space = keep(&pool, PyObject_CallMethod(char_text, "isspace", NULL));
            if (!space) goto done;
            j = PyObject_IsTrue(space);
            if (j < 0) goto done;
            if (j) {
                if (!append_span(&spans, offset, offset + 1, line_size)) goto done;
                offset++;
            }
        }
        reset(&pool, base);
    }
    if (offset != PyUnicode_GetLength(paragraph_text)) goto original;
    result = keep(&pool, PyList_New(0));
    if (!result) goto done;
    base = pool.n;
    for (i = 0; i < PyList_Size(runs); i++) {
        PyObject *run = PyList_GetItem(runs, i), *text = attr(&pool, run, "text");
        Py_ssize_t start = position, end, run_base;
        if (!text) goto done;
        if (!PyUnicode_CheckExact(text)) { reject(); goto done; }
        if (position > PY_SSIZE_T_MAX - PyUnicode_GetLength(text)) { reject(); goto done; }
        end = position + PyUnicode_GetLength(text);
        while (at < spans.n && spans.items[at].end <= position) at++;
        run_base = pool.n;
        while (position < end) {
            Py_ssize_t stop;
            PyObject *part, *piece;
            int merged = 0;
            if (at >= spans.n || spans.items[at].start > position) goto original;
            stop = end < spans.items[at].end ? end : spans.items[at].end;
            part = keep(&pool, PyUnicode_Substring(text, position - start, stop - start));
            if (!part) goto done;
            piece = replacement(&pool, run, part, spans.items[at].size);
            if (!piece) goto done;
            if (PyList_Size(result)) {
                PyObject *last = PyList_GetItem(result, PyList_Size(result) - 1);
                PyObject *last_text = attr(&pool, last, "text"), *comparison;
                if (!last_text) goto done;
                comparison = replacement(&pool, piece, last_text, NULL);
                if (!comparison) goto done;
                merged = PyObject_RichCompareBool(comparison, last, Py_EQ);
                if (merged < 0) goto done;
                if (merged) {
                    PyObject *combined = keep(&pool, PyUnicode_Concat(last_text, part));
                    if (!combined || PyObject_SetAttrString(last, "text", combined) < 0) goto done;
                }
            }
            if (!merged && PyList_Append(result, piece) < 0) goto done;
            position = stop;
            if (position >= spans.items[at].end) at++;
            reset(&pool, run_base);
        }
        reset(&pool, base);
    }
    answer = result; Py_INCREF(answer); goto done;
original:
    answer = runs; Py_INCREF(answer);
done:
    reset(&pool, 0); PyMem_Free(pool.items);
    for (i = 0; i < spans.n; i++) Py_DECREF(spans.items[i].size);
    PyMem_Free(spans.items);
    return answer;
}
static PyMethodDef methods[] = {
    {"sized_runs", sized_runs, METH_VARARGS, "Restore fragment sizes without altering text."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_cheadings", NULL, -1, methods, NULL, NULL, NULL, NULL
};
static PyObject *import_type(const char *module_name, const char *name)
{
    PyObject *mod = PyImport_ImportModule(module_name), *type;
    if (!mod) return NULL;
    type = PyObject_GetAttrString(mod, name); Py_DECREF(mod); return type;
}
PyMODINIT_FUNC PyInit__cheadings(void)
{
    PyObject *m = PyModule_Create(&module), *dataclasses;
    if (!m) return NULL;
    dataclasses = PyImport_ImportModule("dataclasses");
    if (!dataclasses) { Py_DECREF(m); return NULL; }
    replace_fn = PyObject_GetAttrString(dataclasses, "replace");
    Py_DECREF(dataclasses);
    paragraph_type = import_type("dochan.model.document", "Paragraph");
    run_type = import_type("dochan.model.document", "TextRun");
    line_type = import_type("dochan.pdf.content", "_Line");
    segment_type = import_type("dochan.pdf.content", "_Segment");
    namespace_type = import_type("types", "SimpleNamespace");
    if (!paragraph_type || !run_type || !line_type || !segment_type || !namespace_type) {
        Py_DECREF(m); return NULL;
    }
    bailout = PyErr_NewException("dochan.pdf._cheadings.Bailout", PyExc_Exception, NULL);
    if (!replace_fn || !bailout) { Py_DECREF(m); return NULL; }
    Py_INCREF(bailout);
    if (PyModule_AddObject(m, "Bailout", bailout) < 0) { Py_DECREF(bailout); Py_DECREF(m); return NULL; }
    return m;
}
