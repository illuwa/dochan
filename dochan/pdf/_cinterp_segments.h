/* Producer implementation; the consumer imports only the capsule ABI. */
static SegmentAPI segment_api;
static int segment_check(PyObject *o)
{ return Py_TYPE(o) == segment_api.type; }
static Py_ssize_t segment_len(SegmentList *s) { return s->size; }
static int segment_clear_gc(SegmentList *s)
{
    Py_ssize_t size = s->size;
    PyObject **cache = s->cache;
    SegmentRecord *records = s->records;
    s->size = s->capacity = 0; s->cache = NULL; s->records = NULL;
    s->generation++;
    for (Py_ssize_t i = 0; i < size; i++) Py_XDECREF(cache[i]);
    PyMem_Free(cache); PyMem_Free(records);
    return 0;
}
static int segment_traverse(SegmentList *s, visitproc visit, void *arg)
{
    Py_VISIT(Py_TYPE(s));
    for (Py_ssize_t i = 0; i < s->size; i++) Py_VISIT(s->cache[i]);
    return 0;
}
static void segment_dealloc(SegmentList *s)
{
    PyObject *type = (PyObject *)Py_TYPE(s);
    PyObject_GC_UnTrack(s);
    segment_clear_gc(s);
    PyMem_Free(s->records); PyMem_Free(s->cache);
    ((freefunc)PyType_GetSlot((PyTypeObject *)type, Py_tp_free))(s);
    Py_DECREF(type);
}
static PyObject *segment_clear(SegmentList *s, PyObject *unused)
{ (void)unused; segment_clear_gc(s); Py_RETURN_NONE; }
static PyObject *segment_item(SegmentList *s, Py_ssize_t i)
{
    if (i < 0 || i >= s->size) {
        PyErr_SetString(PyExc_IndexError, "SegmentList index out of range"); return NULL;
    }
    if (!s->cache[i]) {
        uint64_t generation = s->generation;
        SegmentRecord r = s->records[i];
        PyObject *a = num_obj(r.x0), *b = num_obj(r.y0);
        PyObject *c = num_obj(r.x1), *d = num_obj(r.y1), *item = NULL;
        if (a && b && c && d) item = PyObject_CallFunctionObjArgs(SegmentType, a, b, c, d, NULL);
        Py_XDECREF(a); Py_XDECREF(b); Py_XDECREF(c); Py_XDECREF(d);
        if (!item) return NULL;
        /* User-modified Segment constructors may clear/repopulate the list.
         * Never attach their result to a different generation or lose its ref. */
        if (s->generation != generation) return item;
        if (s->cache[i]) {
            PyObject *cached = s->cache[i];
            Py_INCREF(cached); Py_DECREF(item); return cached;
        }
        s->cache[i] = item;
    }
    Py_INCREF(s->cache[i]); return s->cache[i];
}
static PyObject *segment_subscript(SegmentList *s, PyObject *key)
{
    if (PySlice_Check(key)) {
        Py_ssize_t start, stop, step, n;
        if (PySlice_GetIndicesEx(key, s->size, &start, &stop, &step, &n) < 0) return NULL;
        PyObject *out = PyList_New(n);
        if (!out) return NULL;
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *item = segment_item(s, start + i * step);
            if (!item) { Py_DECREF(out); return NULL; }
            PyList_SetItem(out, i, item);
        }
        return out;
    }
    Py_ssize_t i = PyNumber_AsSsize_t(key, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred()) return NULL;
    if (i < 0) i += s->size;
    return segment_item(s, i);
}
static PyObject *segment_compare(PyObject *left, PyObject *right, int op)
{
    if (!segment_check(left) || (!segment_check(right) && !PyList_Check(right))) Py_RETURN_NOTIMPLEMENTED;
    PyObject *a = PySequence_List(left), *b = PySequence_List(right), *out = NULL;
    if (a && b) out = PyObject_RichCompare(a, b, op);
    Py_XDECREF(a); Py_XDECREF(b); return out;
}
static int segment_append_record(PyObject *o, SegmentRecord record)
{
    SegmentList *s = (SegmentList *)o;
    if (s->size == s->capacity) {
        Py_ssize_t cap = s->capacity ? s->capacity * 2 : 64;
        if (cap < s->capacity || (size_t)cap > SIZE_MAX / sizeof(SegmentRecord)) {
            PyErr_NoMemory(); return -1;
        }
        SegmentRecord *records = PyMem_Realloc(s->records, (size_t)cap * sizeof(*records));
        if (!records) { PyErr_NoMemory(); return -1; }
        s->records = records;
        PyObject **cache = PyMem_Realloc(s->cache, (size_t)cap * sizeof(*cache));
        if (!cache) { PyErr_NoMemory(); return -1; }
        s->cache = cache; s->capacity = cap;
    }
    s->records[s->size] = record; s->cache[s->size++] = NULL;
    return 0;
}
/* copy/deepcopy/pickle and `+` behave like a list (감수 M: 저장소 도구 두 개가 list 연산을 썼다). */
static PyObject *segment_reduce(PyObject *self, PyObject *unused)
{
    (void)unused;
    PyObject *items = PySequence_List(self);
    if (!items) return NULL;
    return Py_BuildValue("(O(N))", (PyObject *)&PyList_Type, items);
}
static PyObject *segment_concat(PyObject *self, PyObject *other)
{
    PyObject *items = PySequence_List(self);
    if (!items) return NULL;
    PyObject *out = PySequence_InPlaceConcat(items, other);
    Py_DECREF(items);
    return out;
}
static PyMethodDef segment_methods[] = {
    {"clear", (PyCFunction)segment_clear, METH_NOARGS, NULL},
    {"__reduce__", (PyCFunction)segment_reduce, METH_NOARGS, NULL}, {NULL,NULL,0,NULL}
};
static PyType_Slot segment_slots[] = {
    {Py_tp_new, (void *)PyType_GenericNew}, {Py_tp_dealloc, (void *)segment_dealloc},
    {Py_tp_traverse, (void *)segment_traverse}, {Py_tp_clear, (void *)segment_clear_gc},
    {Py_tp_richcompare, (void *)segment_compare},
    {Py_tp_methods, segment_methods}, {Py_sq_length, (void *)segment_len},
    {Py_sq_item, (void *)segment_item}, {Py_sq_concat, (void *)segment_concat}, {Py_mp_length, (void *)segment_len},
    {Py_mp_subscript, (void *)segment_subscript}, {0,NULL}
};
static PyType_Spec segment_spec = {"dochan.pdf._cinterp.SegmentList", sizeof(SegmentList), 0,
                                 Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC, segment_slots};
static int segment_register(PyObject *module)
{
    if (!segment_api.type) {
        segment_api.type = (PyTypeObject *)PyType_FromSpec(&segment_spec);
        if (!segment_api.type) return -1;
    }
    Py_INCREF(segment_api.type);
    if (PyModule_AddObject(module, "SegmentList", (PyObject *)segment_api.type) < 0) {
        Py_DECREF(segment_api.type); return -1;
    }
    PyObject *capsule = PyCapsule_New(&segment_api, SEGMENT_CAPSULE, NULL);
    if (!capsule) return -1;
    if (PyModule_AddObject(module, "_segments_api", capsule) < 0) { Py_DECREF(capsule); return -1; }
    return 0;
}
