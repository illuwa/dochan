/* Handwritten mirror of the read-only preflight in notes.py. */
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <math.h>
#include <string.h>

static PyObject *bailout, *fragment_class, *regex_class;
static PyObject *names[7];
enum { NX, NY, NW, NS, NDX, NDY, NT };

static int
fail(void)
{
    if (!PyErr_Occurred()) PyErr_SetString(bailout, "unsupported note input");
    return -1;
}

static int
exact(PyObject *object, PyObject *type)
{
    PyObject *actual = PyObject_Type(object);
    int result;
    if (!actual) return -1;
    result = actual == type;
    Py_DECREF(actual);
    return result;
}

/* Restrict integer arithmetic to an exactly represented bounded domain. */
static int
number(PyObject *object, double *value)
{
    if (!object) return fail();
    if (!PyFloat_CheckExact(object) && !PyLong_CheckExact(object)) return fail();
    *value = PyFloat_AsDouble(object);
    if (PyErr_Occurred()) return -1;
    if (PyLong_CheckExact(object) && fabs(*value) > 67108864.0) return fail();
    return 0;
}

static int
attribute_number(PyObject *dict, int name, double *value)
{
    return number(PyDict_GetItemWithError(dict, names[name]), value);
}

static PyObject *
fragment_dict(PyObject *fragment, PyObject *fragment_type)
{
    PyObject *dict;
    int same;
    if (fragment_type != fragment_class) { fail(); return NULL; }
    same = exact(fragment, fragment_type);
    if (same != 1) { if (same == 0) fail(); return NULL; }
    dict = PyObject_GetAttrString(fragment, "__dict__");
    if (!dict) return NULL;
    if (!PyDict_CheckExact(dict)) { Py_DECREF(dict); fail(); return NULL; }
    return dict;
}

static PyObject *
horizontal(PyObject *self, PyObject *args)
{
    PyObject *fragments, *type, *result, *dict = NULL;
    Py_ssize_t i, count;
    (void)self;
    if (!PyArg_ParseTuple(args, "OO", &fragments, &type)) return NULL;
    if (!PyList_CheckExact(fragments)) { fail(); return NULL; }
    count = PyList_Size(fragments);
    result = PyList_New(0);
    if (!result) return NULL;
    if (count > 50000) return result;
    for (i = 0; i < count; i++) {
        PyObject *fragment = PyList_GetItem(fragments, i);
        double size, dx, dy;
        dict = fragment_dict(fragment, type);
        if (!dict || attribute_number(dict, NS, &size) < 0) goto error;
        if (size > 0) {
            if (attribute_number(dict, NDX, &dx) < 0 ||
                attribute_number(dict, NDY, &dy) < 0) goto error;
            if (fabs(dx) >= fabs(dy) && dx >= 0 && PyList_Append(result, fragment) < 0)
                goto error;
        }
        Py_CLEAR(dict);
    }
    return result;
error:
    Py_XDECREF(dict);
    Py_DECREF(result);
    return NULL;
}

static PyObject *
prepare(PyObject *self, PyObject *args)
{
    PyObject *fragments, *bounds, *supplied, *type;
    PyObject *h = NULL, *body = NULL, *dict = NULL, *sizes = NULL, *texts = NULL;
    PyObject *max_size = NULL, *rounder = NULL, *rounded = NULL, *round_args = NULL;
    PyObject *call_args = NULL, *result = NULL;
    Py_ssize_t i, count, n;
    double bottom, top, threshold, maximum = 0, limit;
    int candidate = 0;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOO", &fragments, &bounds, &supplied, &type)) return NULL;
    if (!PyList_CheckExact(fragments) || !PyTuple_CheckExact(bounds) || PyTuple_Size(bounds) != 2) {
        fail(); return NULL;
    }
    count = PyList_Size(fragments);
    /* Callers handle empty/limit before this helper. Direct callers are bounded. */
    if (count > 50000) { fail(); return NULL; }
    if (number(PyTuple_GetItem(bounds, 0), &bottom) < 0 ||
        number(PyTuple_GetItem(bounds, 1), &top) < 0) return NULL;
    if (!isfinite(bottom) || !isfinite(top)) { fail(); return NULL; }
    if (supplied == Py_None) {
        for (i = 0; i < count; i++) {
            double v;
            int j;
            dict = fragment_dict(PyList_GetItem(fragments, i), type);
            if (!dict) goto done;
            for (j = NX; j <= NS; j++) {
                if (attribute_number(dict, j, &v) < 0) goto done;
                if (!isfinite(v)) { Py_INCREF(Py_None); result = Py_None; goto done; }
            }
            Py_CLEAR(dict);
        }
        call_args = PyTuple_Pack(2, fragments, type);
        if (!call_args) goto done;
        h = horizontal(NULL, call_args);
        Py_CLEAR(call_args);
        if (!h) goto done;
    } else {
        if (!PyList_CheckExact(supplied) || PyList_Size(supplied) > 50000) { fail(); goto done; }
        h = supplied;
        Py_INCREF(h);
    }
    n = PyList_Size(h);
    if (!n) { Py_INCREF(Py_None); result = Py_None; goto done; }
    threshold = bottom + (top - bottom) * 0.25;
    body = PyList_New(0);
    sizes = PyList_New(0);
    texts = PyList_New(0);
    if (!body || !sizes || !texts) goto done;
    for (i = 0; i < n; i++) {
        PyObject *fragment = PyList_GetItem(h, i), *size, *text;
        double y, s;
        dict = fragment_dict(fragment, type);
        if (!dict || attribute_number(dict, NY, &y) < 0 ||
            attribute_number(dict, NS, &s) < 0) goto done;
        /* Cached horizontal inputs can bypass finite validation in Python.
         * Reject rather than impose a different NaN max/sort semantics. */
        if (!isfinite(y) || !isfinite(s)) { fail(); goto done; }
        size = PyDict_GetItemWithError(dict, names[NS]);
        text = PyDict_GetItemWithError(dict, names[NT]);
        if (!text || !PyUnicode_CheckExact(text)) { fail(); goto done; }
        if (y > threshold && PyList_Append(body, fragment) < 0) goto done;
        if (i == 0 || s > maximum) { maximum = s; max_size = size; }
        if (PyList_Append(sizes, size) < 0 || PyList_Append(texts, text) < 0) goto done;
        Py_CLEAR(dict);
    }
    if (PyList_Size(body) == 0) { Py_INCREF(Py_None); result = Py_None; goto done; }
    rounder = PyDict_GetItemString(PyEval_GetBuiltins(), "round");
    if (!rounder) { fail(); goto done; }
    round_args = Py_BuildValue("(Oi)", max_size, 3);
    if (!round_args) goto done;
    rounded = PyObject_CallObject(rounder, round_args);
    if (!rounded) goto done;
    limit = PyFloat_AsDouble(rounded) * 0.9;
    if (PyErr_Occurred()) goto done;
    for (i = 0; i < n; i++) {
        PyObject *text = PyList_GetItem(texts, i);
        Py_ssize_t at = PyUnicode_FindChar(text, ')', 0, PyUnicode_GetLength(text), 1);
        double size;
        if (at == -2) goto done;
        if (at < 0) continue;
        if (number(PyList_GetItem(sizes, i), &size) < 0) goto done;
        if (size < limit) { candidate = 1; break; }
    }
    if (candidate) result = PyTuple_Pack(2, h, body);
    else { Py_INCREF(Py_None); result = Py_None; }
done:
    Py_XDECREF(h); Py_XDECREF(body); Py_XDECREF(dict);
    Py_XDECREF(sizes); Py_XDECREF(texts); Py_XDECREF(rounded);
    Py_XDECREF(round_args); Py_XDECREF(call_args);
    return result;
}

typedef struct {
    PyObject *fragment, *text, *order, *match;
    double x, y, width, size;
    int note;
} NoteFragment;

/* Stable merge sort: equal y retains the original horizontal-list order. */
static void
sort_hosts(NoteFragment **items, NoteFragment **scratch, Py_ssize_t start, Py_ssize_t stop)
{
    Py_ssize_t middle, left, right, out;
    if (stop - start < 2) return;
    middle = start + (stop - start) / 2;
    sort_hosts(items, scratch, start, middle);
    sort_hosts(items, scratch, middle, stop);
    left = start; right = middle; out = start;
    while (left < middle && right < stop) {
        scratch[out++] = items[right]->y < items[left]->y ? items[right++] : items[left++];
    }
    while (left < middle) scratch[out++] = items[left++];
    while (right < stop) scratch[out++] = items[right++];
    for (out = start; out < stop; out++) items[out] = scratch[out];
}

static Py_ssize_t
bisect_hosts(NoteFragment **hosts, Py_ssize_t n, double y, int right)
{
    Py_ssize_t low = 0, high = n;
    while (low < high) {
        Py_ssize_t middle = low + (high - low) / 2;
        if (right ? y < hosts[middle]->y : hosts[middle]->y >= y) high = middle;
        else low = middle + 1;
    }
    return low;
}

static PyObject *
endnotes(PyObject *self, PyObject *args)
{
    PyObject *fragments, *type, *pattern, *dict = NULL, *result = NULL, *returned = NULL;
    PyObject *fullmatch = NULL, *entry = NULL, *group = NULL;
    NoteFragment *items = NULL, **hosts = NULL, **scratch = NULL, **vertical = NULL;
    Py_ssize_t i, j, n, budget, maximum, near_count = 0, vertical_count = 0;
    double max_size = 0, previous_y = 0, previous_size = 0;
    int have_previous = 0, warning = 0;
    (void)self;
    if (!PyArg_ParseTuple(args, "OOOnn", &fragments, &type, &pattern, &budget, &maximum))
        return NULL;
    if (!PyList_CheckExact(fragments)) { fail(); return NULL; }
    if (type != fragment_class || exact(pattern, regex_class) != 1) { fail(); return NULL; }
    n = PyList_Size(fragments);
    if (n > 50000 || budget < 0 || maximum < 0) { fail(); return NULL; }
    result = PyList_New(0);
    if (!result) return NULL;
    if (!n) { returned = Py_BuildValue("(Oi)", result, 0); goto done; }
    items = PyMem_Malloc((size_t)n * sizeof(*items));
    if (items) memset(items, 0, (size_t)n * sizeof(*items));
    hosts = PyMem_Malloc((size_t)n * sizeof(*hosts));
    scratch = PyMem_Malloc((size_t)n * sizeof(*scratch));
    vertical = PyMem_Malloc((size_t)n * sizeof(*vertical));
    if (!items || !hosts || !scratch || !vertical) { PyErr_NoMemory(); goto done; }
    /* Validate every callback-sensitive field before invoking even regex code. */
    for (i = 0; i < n; i++) {
        PyObject *note, *text, *order;
        NoteFragment *f = &items[i];
        f->fragment = PyList_GetItem(fragments, i);
        dict = fragment_dict(f->fragment, type);
        if (!dict || attribute_number(dict, NX, &f->x) < 0 ||
            attribute_number(dict, NY, &f->y) < 0 ||
            attribute_number(dict, NW, &f->width) < 0 ||
            attribute_number(dict, NS, &f->size) < 0) goto done;
        if (!isfinite(f->x) || !isfinite(f->y) || !isfinite(f->width) || !isfinite(f->size)) {
            fail(); goto done;
        }
        text = PyDict_GetItemWithError(dict, names[NT]);
        order = PyDict_GetItemString(dict, "order");
        note = PyDict_GetItemString(dict, "note_ref");
        if (!text || !PyUnicode_CheckExact(text) || !order ||
            !PyLong_CheckExact(order) || !note ||
            (!PyLong_CheckExact(note) && note != Py_True && note != Py_False)) {
            fail(); goto done;
        }
        f->text = text; Py_INCREF(text);
        f->order = order; Py_INCREF(order);
        f->note = PyObject_IsTrue(note);
        if (f->note < 0) goto done;
        hosts[i] = f;
        if (i == 0 || f->size > max_size) max_size = f->size;
        Py_CLEAR(dict);
    }
    fullmatch = PyObject_GetAttrString(pattern, "fullmatch");
    if (!fullmatch) goto done;
    for (i = 0; i < n; i++) {
        if (items[i].note) continue;
        entry = PyTuple_Pack(1, items[i].text);
        if (!entry) goto done;
        items[i].match = PyObject_CallObject(fullmatch, entry);
        Py_CLEAR(entry);
        if (!items[i].match) goto done;
    }
    sort_hosts(hosts, scratch, 0, n);
    for (i = 0; i < n; i++) {
        NoteFragment *m = &items[i];
        double min_y = 0, max_y = 0, min_s = 0, max_s = 0;
        int valid = 0;
        if (!m->match || m->match == Py_None) continue;
        if (!have_previous || m->y != previous_y || m->size != previous_size) {
            Py_ssize_t lo = bisect_hosts(hosts, n, m->y - max_size, 0);
            Py_ssize_t hi = bisect_hosts(hosts, n, m->y, 1);
            near_count = hi - lo;
            vertical_count = 0;
            for (j = lo; j < hi; j++) {
                NoteFragment *h = hosts[j];
                double first = .30 * h->size, second = h->size - m->size;
                double upper = (first >= second ? first : second) + 1e-6;
                if (m->size <= h->size * .8 && .15 * h->size <= m->y - h->y &&
                    m->y - h->y <= upper) vertical[vertical_count++] = h;
            }
            previous_y = m->y; previous_size = m->size; have_previous = 1;
        }
        if (budget < near_count) { warning = 1; break; }
        budget -= near_count;
        for (j = 0; j < vertical_count; j++) {
            NoteFragment *h = vertical[j];
            double gap = m->x - h->x - h->width;
            if (-.1 * h->size <= gap && gap <= .5 * h->size) {
                if (!valid) { min_y = max_y = h->y; min_s = max_s = h->size; }
                else {
                    if (h->y < min_y) min_y = h->y;
                    if (h->y > max_y) max_y = h->y;
                    if (h->size < min_s) min_s = h->size;
                    if (h->size > max_s) max_s = h->size;
                }
                valid = 1;
            }
        }
        if (valid && max_y - min_y <= .1 && max_s - min_s <= .1) {
            group = PyObject_CallMethod(m->match, "group", "i", 1);
            if (!group) goto done;
            entry = PyTuple_Pack(2, m->order, group);
            if (!entry || PyList_Append(result, entry) < 0) goto done;
            Py_CLEAR(entry); Py_CLEAR(group);
            if (PyList_Size(result) > maximum) { warning = 2; break; }
        }
    }
    if (warning && PyList_SetSlice(result, 0, PyList_Size(result), NULL) < 0) goto done;
    returned = Py_BuildValue("(Oi)", result, warning);
done:
    Py_XDECREF(dict); Py_XDECREF(result); Py_XDECREF(fullmatch);
    Py_XDECREF(entry); Py_XDECREF(group);
    if (items) for (i = 0; i < n; i++) {
        Py_XDECREF(items[i].match); Py_XDECREF(items[i].text); Py_XDECREF(items[i].order);
    }
    PyMem_Free(items); PyMem_Free(hosts); PyMem_Free(scratch); PyMem_Free(vertical);
    return returned;
}

static PyMethodDef methods[] = {
    {"endnotes", endnotes, METH_VARARGS, "Mirror endnote reference geometry and budgets."},
    {"horizontal", horizontal, METH_VARARGS, "Mirror horizontal fragment classification."},
    {"prepare", prepare, METH_VARARGS, "Mirror read-only note candidate preflight."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_cnotes", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC
PyInit__cnotes(void)
{
    static const char *strings[] = {"x", "y", "width", "size", "dir_x", "dir_y", "text"};
    PyObject *result = PyModule_Create(&module), *content = NULL, *re = NULL;
    int i;
    if (!result) return NULL;
    if (!fragment_class) {
        content = PyImport_ImportModule("dochan.pdf.content");
        if (content) fragment_class = PyObject_GetAttrString(content, "Fragment");
        Py_XDECREF(content);
    }
    if (!regex_class) {
        re = PyImport_ImportModule("re");
        if (re) regex_class = PyObject_GetAttrString(re, "Pattern");
        Py_XDECREF(re);
    }
    if (!fragment_class || !regex_class) { Py_DECREF(result); return NULL; }
    for (i = 0; i < 7; i++) {
        if (!names[i]) names[i] = PyUnicode_InternFromString(strings[i]);
        if (!names[i]) { Py_DECREF(result); return NULL; }
    }
    if (!bailout) bailout = PyErr_NewException("dochan.pdf._cnotes.Bailout", NULL, NULL);
    if (!bailout) { Py_DECREF(result); return NULL; }
    Py_INCREF(bailout);
    if (PyModule_AddObject(result, "Bailout", bailout) < 0) {
        Py_DECREF(bailout); Py_DECREF(result); return NULL;
    }
    return result;
}
