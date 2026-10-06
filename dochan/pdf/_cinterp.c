/* Handwritten content interpreter, based only on this repository's Python
 * contracts and ISO 32000-1. No generated or external PDF engine code.
 * Every scalar carries Python's exact int/float category; contraction is
 * disabled by the build so the affine evaluation order remains unchanged. */
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

static PyObject *Bailout;
static PyObject *PDFLexerType, *PDFSyntaxErrorType, *PDFNameType;
static PyObject *SegmentType, *HypotFunction, *PathWarning, *PathModule;

typedef struct { double v; int integer; } Num;
typedef struct { Num x, y; } Point;
#define INT_LIMIT INT64_C(9007199254740992)

static void replace_ref(PyObject **slot, PyObject *value)
{
    PyObject *previous = *slot;
    *slot = value;
    Py_XDECREF(previous);
}

static int bail(const char *reason)
{
    PyErr_SetString(Bailout, reason);
    return -1;
}
static Num ni(double v) { Num n = {v == 0 ? 0 : v, 1}; return n; }
static Num nf(double v) { Num n = {v, 0}; return n; }
static Num num_abs(Num n) { n.v = fabs(n.v); return n; }
static int num_from(PyObject *o, Num *n)
{
    if (PyLong_CheckExact(o)) {
        int64_t i = PyLong_AsLongLong(o);
        if (PyErr_Occurred()) {
            if (!PyErr_ExceptionMatches(PyExc_OverflowError)) return -1;
            PyErr_Clear();
            return bail("integer outside exact range");
        }
        if (i > INT_LIMIT || i < -INT_LIMIT)
            return bail("integer outside exact range");
        *n = ni((double)i);
    } else if (PyFloat_CheckExact(o)) {
        double value = PyFloat_AsDouble(o);
        if (!isfinite(value)) return bail("non-finite numeric value");
        *n = nf(value);
    } else {
        return bail("non-exact numeric type");
    }
    return 0;
}
static PyObject *num_obj(Num n)
{
    return n.integer ? PyLong_FromLongLong((int64_t)n.v) : PyFloat_FromDouble(n.v);
}
static int num_add(Num a, Num b, Num *out)
{
    if (a.integer && b.integer) {
        int64_t v = (int64_t)a.v + (int64_t)b.v;
        if (v > INT_LIMIT || v < -INT_LIMIT) return bail("integer addition outside exact range");
        *out = ni((double)v);
    } else { *out = nf(a.v + b.v); if (!isfinite(out->v)) return bail("non-finite arithmetic result"); }
    return 0;
}
static int num_sub(Num a, Num b, Num *out)
{
    if (a.integer && b.integer) {
        int64_t v = (int64_t)a.v - (int64_t)b.v;
        if (v > INT_LIMIT || v < -INT_LIMIT) return bail("integer subtraction outside exact range");
        *out = ni((double)v);
    } else { *out = nf(a.v - b.v); if (!isfinite(out->v)) return bail("non-finite arithmetic result"); }
    return 0;
}
static int num_mul(Num a, Num b, Num *out)
{
    if (a.integer && b.integer) {
        int64_t av = (int64_t)a.v, bv = (int64_t)b.v;
        int64_t aa = av < 0 ? -av : av, ab = bv < 0 ? -bv : bv;
        if (ab && aa > INT_LIMIT / ab) return bail("integer multiplication outside exact range");
        *out = ni((double)(av * bv));
    } else { *out = nf(a.v * b.v); if (!isfinite(out->v)) return bail("non-finite arithmetic result"); }
    return 0;
}
static Num num_neg(Num n) { n.v = -n.v; if (n.integer && n.v == 0) n.v = 0; return n; }
static int matrix_from(PyObject *o, Num n[6])
{
    if (!PyTuple_CheckExact(o) || PyTuple_Size(o) != 6) return bail("matrix must be an exact six-tuple");
    for (int i = 0; i < 6; i++) if (num_from(PyTuple_GetItem(o, i), &n[i]) < 0) return -1;
    return 0;
}
static PyObject *matrix_obj(Num n[6])
{
    PyObject *t = PyTuple_New(6);
    if (!t) return NULL;
    for (int i = 0; i < 6; i++) {
        PyObject *v = num_obj(n[i]);
        if (!v) { Py_DECREF(t); return NULL; }
        PyTuple_SetItem(t, i, v);
    }
    return t;
}
static int matrix_mul(Num a[6], Num b[6], Num result[6])
{
    Num r[6], p, q;
    static const int indices[6][4] = {{0,0,1,2},{0,1,1,3},{2,0,3,2},{2,1,3,3},{4,0,5,2},{4,1,5,3}};
    for (int i = 0; i < 6; i++) {
        const int *j = indices[i];
        if (num_mul(a[j[0]], b[j[1]], &p) < 0 || num_mul(a[j[2]], b[j[3]], &q) < 0 ||
            num_add(p, q, &r[i]) < 0) return -1;
        if (i >= 4 && num_add(r[i], b[i], &r[i]) < 0) return -1;
    }
    memcpy(result, r, sizeof(r));
    return 0;
}
static void identity(Num m[6])
{
    for (int i = 0; i < 6; i++) m[i] = ni(i == 0 || i == 3);
}

#include "_cinterp_objects.h"
#include "_cinterp_paths.h"

typedef struct {
    Num ctm[6], fs, tc, tw, th, tl, tr, stroke_width;
    PyObject *font;
} SavedState;
typedef struct {
    PyObject_HEAD
    ObjScanner scanner;
    PyObject *fonts, *font, *segments, *short_segments, *warnings, *operands;
    Num ctm[6], tm[6], tlm[6], fs, tc, tw, th, tl, tr, stroke_width;
    SavedState stack[256];
    Py_ssize_t depth, overflow;
    int initialized, text_line_reset, busy;
    PathState paths;
} Interpreter;

static int interp_clear(Interpreter *s)
{
    s->initialized = 0;
    path_clear(&s->paths);
    objscan_clear(&s->scanner);
    Py_CLEAR(s->fonts); Py_CLEAR(s->font); Py_CLEAR(s->segments);
    Py_CLEAR(s->short_segments); Py_CLEAR(s->warnings); Py_CLEAR(s->operands);
    for (Py_ssize_t i = 0; i < s->depth; i++) Py_CLEAR(s->stack[i].font);
    s->depth = s->overflow = 0;
    return 0;
}
static int interp_traverse(Interpreter *s, visitproc visit, void *arg)
{
    Py_VISIT(Py_TYPE(s));
    Py_VISIT(s->fonts); Py_VISIT(s->font); Py_VISIT(s->segments);
    Py_VISIT(s->short_segments); Py_VISIT(s->warnings); Py_VISIT(s->operands);
    for (Py_ssize_t i = 0; i < s->depth; i++) Py_VISIT(s->stack[i].font);
    return objscan_traverse(&s->scanner, visit, arg);
}
static void interp_dealloc(Interpreter *s)
{
    PyObject *type = (PyObject *)Py_TYPE(s);
    PyObject_GC_UnTrack(s);
    interp_clear(s);
    ((freefunc)PyType_GetSlot((PyTypeObject *)type, Py_tp_free))(s);
    Py_DECREF(type);
}
static int interp_init(Interpreter *s, PyObject *args, PyObject *kwargs)
{
    static char *kw[] = {"data", "fonts", "ctm", "text_state", "segments", "short_segments", "warnings", NULL};
    PyObject *data, *fonts, *ctm, *state, *segments, *shorts, *warnings;
    Num m[6], scalars[7];
    if (s->busy) return bail("reentrant interpreter initialization");
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOOOOOO:Interpreter", kw,
                                    &data, &fonts, &ctm, &state, &segments, &shorts, &warnings)) return -1;
    if (!PyBytes_CheckExact(data) || !PyDict_CheckExact(fonts) || !PyList_CheckExact(segments) ||
        !PyList_CheckExact(shorts) || !PyList_CheckExact(warnings) ||
        !PyTuple_CheckExact(state) || PyTuple_Size(state) != 8) return bail("unsupported constructor types");
    /* Mutable Python limits are also used by existing callers/tests. An
     * altered configuration is delegated rather than silently frozen in C. */
    PyObject *limit = PyObject_GetAttrString(PathModule, "MAX_SEGMENTS");
    if (!limit) return -1;
    int default_limit = PyLong_CheckExact(limit) && PyLong_AsLong(limit) == PATH_MAX_SEGMENTS;
    Py_DECREF(limit);
    if (PyErr_Occurred()) {
        if (!PyErr_ExceptionMatches(PyExc_OverflowError)) return -1;
        PyErr_Clear();
        return bail("changed path segment limit");
    }
    if (!default_limit) return bail("changed path segment limit");
    if (matrix_from(ctm, m) < 0) return -1;
    for (int i = 0; i < 7; i++) if (num_from(PyTuple_GetItem(state, i + 1), &scalars[i]) < 0) return -1;
    s->busy = 1;
    interp_clear(s);
    if (objscan_init(&s->scanner, data) < 0) { s->busy = 0; return -1; }
    Py_INCREF(fonts); s->fonts = fonts;
    s->font = PyTuple_GetItem(state, 0); Py_INCREF(s->font);
    Py_INCREF(segments); s->segments = segments;
    Py_INCREF(shorts); s->short_segments = shorts;
    Py_INCREF(warnings); s->warnings = warnings;
    s->operands = PyList_New(0);
    if (!s->operands) { interp_clear(s); s->busy = 0; return -1; }
    memcpy(s->ctm, m, sizeof(m)); identity(s->tm); identity(s->tlm);
    s->fs = scalars[0]; s->tc = scalars[1]; s->tw = scalars[2]; s->th = scalars[3];
    s->tl = scalars[4]; s->tr = scalars[5]; s->stroke_width = scalars[6];
    path_init(&s->paths, segments, shorts, warnings);
    s->text_line_reset = 0; s->initialized = 1; s->busy = 0;
    return 0;
}
static int operand_float(Interpreter *s, Py_ssize_t index, Num *n)
{
    PyObject *value = PyList_GetItem(s->operands, index);
    if (!value || num_from(value, n) < 0) return -1;
    *n = nf(n->v);
    return 0;
}
static int move_line(Interpreter *s, Num tx, Num ty)
{
    Num trans[6]; identity(trans); trans[4] = tx; trans[5] = ty;
    if (matrix_mul(trans, s->tlm, s->tlm) < 0) return -1;
    memcpy(s->tm, s->tlm, sizeof(s->tm)); return 0;
}
#define OP(lit) (size == (Py_ssize_t)(sizeof(lit)-1) && memcmp(op, lit, sizeof(lit)-1) == 0)
static int operate(Interpreter *s, const char *op, Py_ssize_t size)
{
    Py_ssize_t count = PyList_Size(s->operands);
    Num v[64];
    if (count < 0) return -1;
    if (OP("BT") || OP("Tm") || OP("Td") || OP("TD") || OP("T*")) s->text_line_reset = 1;
    if (OP("q")) {
        if (s->depth < 256) {
            SavedState *q = &s->stack[s->depth++];
            memcpy(q->ctm, s->ctm, sizeof(s->ctm));
            q->font = s->font; Py_INCREF(q->font);
            q->fs = s->fs; q->tc = s->tc; q->tw = s->tw; q->th = s->th; q->tl = s->tl;
            q->tr = s->tr; q->stroke_width = s->stroke_width;
        } else {
            if (s->overflow == PY_SSIZE_T_MAX) return bail("graphics stack overflow counter");
            s->overflow++;
        }
    } else if (OP("Q")) {
        if (s->overflow) s->overflow--;
        else if (s->depth) {
            SavedState *q = &s->stack[--s->depth];
            memcpy(s->ctm, q->ctm, sizeof(s->ctm));
            replace_ref(&s->font, q->font); q->font = NULL;
            s->fs = q->fs; s->tc = q->tc; s->tw = q->tw; s->th = q->th; s->tl = q->tl;
            s->tr = q->tr; s->stroke_width = q->stroke_width;
        }
    } else if (OP("BT")) { identity(s->tm); identity(s->tlm); }
    else if (OP("cm") || OP("Tm")) {
        if (count < 6) return bail("missing matrix operands");
        for (int i = 0; i < 6; i++) if (operand_float(s, count-6+i, &v[i]) < 0) return -1;
        if (OP("cm")) { if (matrix_mul(v, s->ctm, s->ctm) < 0) return -1; }
        else { memcpy(s->tm, v, sizeof(s->tm)); memcpy(s->tlm, v, sizeof(s->tlm)); }
    } else if (OP("Tf")) {
        if (count >= 2) {
            PyObject *name = PyList_GetItem(s->operands, count-2);
            if (!name) return -1;
            Py_INCREF(name); /* Keep alive across Python name callbacks. */
            int is_name = PyObject_IsInstance(name, PDFNameType);
            if (is_name < 0) { Py_DECREF(name); return -1; }
            if (is_name) {
                PyObject *key = PyObject_Str(name), *font;
                Py_DECREF(name);
                if (!key) return -1;
                font = PyDict_GetItemWithError(s->fonts, key); Py_DECREF(key);
                if (!font && PyErr_Occurred()) return -1;
                if (!font) font = Py_None;
                Py_INCREF(font); replace_ref(&s->font, font);
            } else Py_DECREF(name);
        }
        /* Font name and size tests are independent, exactly as in Python. */
        if (count) {
            PyObject *last = PyList_GetItem(s->operands, count-1);
            if (!last) return -1;
            if (PyLong_Check(last) || PyFloat_Check(last)) {
                if (operand_float(s, count-1, &s->fs) < 0) return -1;
            }
        }
    } else if (OP("Tc") || OP("Tw") || OP("Tz") || OP("TL") || OP("Tr") || OP("w")) {
        if (!count) return bail("missing text-state operand");
        if (operand_float(s, count-1, &v[0]) < 0) return -1;
        if (OP("Tc")) s->tc = v[0];
        else if (OP("Tw")) s->tw = v[0];
        else if (OP("Tz")) s->th = nf(v[0].v / 100.0);
        else if (OP("TL")) s->tl = v[0];
        else if (OP("w")) { s->stroke_width = v[0]; path_width(&s->paths, v[0]); }
        else if (isfinite(v[0].v) && floor(v[0].v) == v[0].v) {
            if (fabs(v[0].v) > (double)INT_LIMIT) return bail("render mode outside exact range");
            s->tr = ni(v[0].v);
        }
    } else if (OP("Td") || OP("TD")) {
        if (count < 2) return bail("missing text-position operands");
        if (operand_float(s, count-2, &v[0]) < 0 || operand_float(s, count-1, &v[1]) < 0) return -1;
        if (OP("TD")) s->tl = num_neg(v[1]);
        if (move_line(s, v[0], v[1]) < 0) return -1;
    } else if (OP("T*")) {
        if (move_line(s, ni(0), num_neg(s->tl)) < 0) return -1;
    } else if (OP("m") || OP("l") || OP("c") || OP("v") || OP("y") || OP("re") || OP("h") ||
               OP("S") || OP("s") || OP("f") || OP("F") || OP("f*") || OP("B") || OP("B*") ||
               OP("b") || OP("b*") || OP("n")) {
        if (count > 64) return bail("too many path operands");
        for (Py_ssize_t i = 0; i < count; i++) if (operand_float(s, i, &v[i]) < 0) return -1;
        if (path_operate(&s->paths, op, size, v, count, s->ctm) < 0) return -1;
    }
    return 0;
}
static PyObject *interp_next_inner(Interpreter *s)
{
    unsigned int operators = 0;
    if (!s->initialized) { PyErr_SetString(PyExc_RuntimeError, "Interpreter is not initialized"); return NULL; }
    while (1) {
        PyObject *value = NULL;
        int event = scan_next(&s->scanner, &value);
        if (event < 0) return NULL;
        if (event == 0) Py_RETURN_NONE;
        if (event == 1) {
            int ok = PyList_Append(s->operands, value); Py_DECREF(value);
            if (ok < 0) return NULL;
            Py_ssize_t count = PyList_Size(s->operands);
            if (count > 64 && PyList_SetSlice(s->operands, 0, count-8, NULL) < 0) return NULL;
            continue;
        }
        char *op; Py_ssize_t size;
        if (PyBytes_AsStringAndSize(value, &op, &size) < 0) { Py_DECREF(value); return NULL; }
        if (++operators % 1024 == 0 && PyErr_CheckSignals() < 0) {
            Py_DECREF(value);
            return NULL;
        }
        if (OP("Tj") || OP("'") || OP("\"") || OP("TJ") || OP("Do") || OP("BDC") || OP("BMC") ||
            OP("EMC") || OP("gs") || OP("BI")) {
            PyObject *empty = PyList_New(0), *result;
            if (!empty) { Py_DECREF(value); return NULL; }
            result = PyTuple_Pack(2, value, s->operands); Py_DECREF(value);
            if (!result) { Py_DECREF(empty); return NULL; }
            replace_ref(&s->operands, empty);
            return result;
        }
        int ok = operate(s, op, size); Py_DECREF(value);
        if (ok < 0 || PyList_SetSlice(s->operands, 0, PyList_Size(s->operands), NULL) < 0) return NULL;
    }
}
static PyObject *interp_next(Interpreter *s, PyObject *unused)
{
    (void)unused;
    PyObject *result;
    if (s->busy) { bail("reentrant interpreter next"); return NULL; }
    s->busy = 1; result = interp_next_inner(s); s->busy = 0;
    return result;
}
/* Bulk reads/writes keep Python callbacks inexpensive; scalar properties are
 * also available for callers that only change one field. */
static PyObject *interp_state(Interpreter *s, PyObject *unused)
{
    (void)unused;
    PyObject *t = PyTuple_New(11);
    if (!t) return NULL;
    for (int i = 0; i < 11; i++) {
        PyObject *v;
        if (i < 3) v = matrix_obj(i == 0 ? s->ctm : i == 1 ? s->tm : s->tlm);
        else if (i == 3) { v = s->font ? s->font : Py_None; Py_INCREF(v); }
        else {
            Num *n[] = {&s->fs,&s->tc,&s->tw,&s->th,&s->tl,&s->tr,&s->stroke_width};
            v = num_obj(*n[i-4]);
        }
        if (!v) { Py_DECREF(t); return NULL; }
        PyTuple_SetItem(t, i, v);
    }
    return t;
}
static PyObject *interp_resume(Interpreter *s, PyObject *args)
{
    PyObject *tm, *tlm, *tc, *tw, *width;
    Num a[6], b[6], c, d, e;
    if (s->busy) { bail("reentrant interpreter resume"); return NULL; }
    if (!PyArg_ParseTuple(args, "OOOOO:resume", &tm, &tlm, &tc, &tw, &width)) return NULL;
    if (matrix_from(tm,a)<0 || matrix_from(tlm,b)<0 || num_from(tc,&c)<0 || num_from(tw,&d)<0 || num_from(width,&e)<0) return NULL;
    memcpy(s->tm,a,sizeof(a)); memcpy(s->tlm,b,sizeof(b)); s->tc=c; s->tw=d; s->stroke_width=e;
    Py_RETURN_NONE;
}
static PyObject *get_attr(Interpreter *s, void *closure)
{
    intptr_t field = (intptr_t)closure;
    if (field < 3) return matrix_obj(field == 0 ? s->ctm : field == 1 ? s->tm : s->tlm);
    if (field == 3) { PyObject *f = s->font ? s->font : Py_None; Py_INCREF(f); return f; }
    if (field == 11) return PyLong_FromSsize_t(s->scanner.pos);
    if (field == 12) return PyBool_FromLong(s->text_line_reset);
    Num *n[] = {&s->fs,&s->tc,&s->tw,&s->th,&s->tl,&s->tr,&s->stroke_width};
    return num_obj(*n[field-4]);
}
static int set_attr(Interpreter *s, PyObject *value, void *closure)
{
    intptr_t field = (intptr_t)closure;
    if (!value) { PyErr_SetString(PyExc_TypeError,"cannot delete interpreter state"); return -1; }
    if (s->busy) return bail("reentrant interpreter state mutation");
    if (field < 3) {
        Num matrix[6];
        if (matrix_from(value, matrix) < 0) return -1;
        memcpy(field == 0 ? s->ctm : field == 1 ? s->tm : s->tlm, matrix, sizeof(matrix));
        return 0;
    }
    if (field == 3) { Py_INCREF(value); replace_ref(&s->font,value); return 0; }
    if (field == 11) {
        if (!PyLong_CheckExact(value)) return bail("non-exact position type");
        Py_ssize_t pos = PyLong_AsSsize_t(value);
        if (PyErr_Occurred()) return -1;
        s->scanner.pos = pos; return 0;
    }
    if (field == 12) { int truth = PyObject_IsTrue(value); if (truth < 0) return -1; s->text_line_reset=truth; return 0; }
    Num *n[] = {&s->fs,&s->tc,&s->tw,&s->th,&s->tl,&s->tr,&s->stroke_width};
    return num_from(value,n[field-4]);
}
#define ATTR(name, index) {name, (getter)get_attr, (setter)set_attr, NULL, (void *)(intptr_t)index}
static PyGetSetDef attributes[] = {
    ATTR("ctm",0),ATTR("tm",1),ATTR("tlm",2),ATTR("font",3),ATTR("fs",4),ATTR("tc",5),ATTR("tw",6),
    ATTR("th",7),ATTR("tl",8),ATTR("tr",9),ATTR("stroke_width",10),ATTR("pos",11),ATTR("text_line_reset",12),
    {NULL,NULL,NULL,NULL,NULL}
};
static PyMethodDef methods[] = {
    {"next",(PyCFunction)interp_next,METH_NOARGS,NULL},
    {"state",(PyCFunction)interp_state,METH_NOARGS,NULL},
    {"resume",(PyCFunction)interp_resume,METH_VARARGS,NULL},
    {NULL,NULL,0,NULL}
};
static PyType_Slot slots[] = {
    {Py_tp_init,(void *)interp_init}, {Py_tp_new,(void *)PyType_GenericNew},
    {Py_tp_dealloc,(void *)interp_dealloc}, {Py_tp_traverse,(void *)interp_traverse},
    {Py_tp_clear,(void *)interp_clear}, {Py_tp_methods,methods}, {Py_tp_getset,attributes}, {0,NULL}
};
static PyType_Spec spec = {"dochan.pdf._cinterp.Interpreter",sizeof(Interpreter),0,
                          Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,slots};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT,"_cinterp",NULL,-1,NULL,NULL,NULL,NULL,NULL};
static int import_attr(const char *module_name, const char *name, PyObject **target)
{
    PyObject *m = PyImport_ImportModule(module_name);
    if (!m) return -1;
    *target = PyObject_GetAttrString(m,name); Py_DECREF(m);
    return *target ? 0 : -1;
}
PyMODINIT_FUNC PyInit__cinterp(void)
{
    PyObject *m = PyModule_Create(&module), *type;
    if (!m) return NULL;
    PathModule = PyImport_ImportModule("dochan.pdf.paths");
    if (!PathModule) goto failed;
    if (import_attr("dochan.pdf.objects","PDFLexer",&PDFLexerType)<0 ||
        import_attr("dochan.pdf.objects","PDFSyntaxError",&PDFSyntaxErrorType)<0 ||
        import_attr("dochan.pdf.objects","PDFName",&PDFNameType)<0 ||
        import_attr("dochan.pdf.paths","Segment",&SegmentType)<0 ||
        import_attr("dochan.pdf.paths","PATH_WARNING",&PathWarning)<0 ||
        import_attr("math","hypot",&HypotFunction)<0) goto failed;
    Bailout = PyErr_NewException("dochan.pdf._cinterp.Bailout",NULL,NULL);
    if (!Bailout) goto failed;
    Py_INCREF(Bailout); /* The process-global cache owns a strong reference. */
    if (PyModule_AddObject(m,"Bailout",Bailout)<0) { Py_DECREF(Bailout); goto failed; }
    type = PyType_FromSpec(&spec);
    if (!type) goto failed;
    if (PyModule_AddObject(m,"Interpreter",type)<0) { Py_DECREF(type); goto failed; }
    return m;
failed:
    Py_DECREF(m);
    Py_CLEAR(Bailout);
    Py_CLEAR(PDFLexerType); Py_CLEAR(PDFSyntaxErrorType); Py_CLEAR(PDFNameType);
    Py_CLEAR(SegmentType); Py_CLEAR(HypotFunction); Py_CLEAR(PathWarning); Py_CLEAR(PathModule);
    return NULL;
}
