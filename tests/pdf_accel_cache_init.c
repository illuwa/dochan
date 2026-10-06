/* Test-only fault injection around the real handwritten module initializers.
 * Compile once per CACHE_MODULE (1=lines, 2=interpreter, 3=scanner). */
#define Py_LIMITED_API 0x03090000
#include <Python.h>

static int intern_at, intern_calls, create_fails, type_fails;
static int add_at, add_calls, import_at, import_calls;

static PyObject *probe_intern(const char *name)
{
    if (++intern_calls == intern_at) return PyErr_NoMemory();
    return PyUnicode_InternFromString(name);
}
static PyObject *probe_create(PyModuleDef *def, int version)
{
    if (create_fails) return PyErr_NoMemory();
    return PyModule_Create2(def, version);
}
static PyObject *probe_type(PyType_Spec *specification)
{
    if (type_fails) return PyErr_NoMemory();
    return PyType_FromSpec(specification);
}
static int probe_add(PyObject *mod, const char *name, PyObject *value)
{
    if (++add_calls == add_at) { PyErr_NoMemory(); return -1; }
    return PyModule_AddObject(mod, name, value);
}
static PyObject *probe_import(const char *name)
{
    if (++import_calls == import_at) return PyErr_NoMemory();
    return PyImport_ImportModule(name);
}

#define PyUnicode_InternFromString probe_intern
#define PyModule_Create2 probe_create
#define PyType_FromSpec probe_type
#define PyModule_AddObject probe_add
#define PyImport_ImportModule probe_import
#if CACHE_MODULE == 1
#define PyInit__clines subject_init
#include "../dochan/pdf/_clines.c"
#elif CACHE_MODULE == 2
#define PyInit__cinterp subject_init
#include "../dochan/pdf/_cinterp.c"
#else
#define PyInit__cscan subject_init
#include "../dochan/pdf/_cscan.c"
#endif
#undef PyUnicode_InternFromString
#undef PyModule_Create2
#undef PyType_FromSpec
#undef PyModule_AddObject
#undef PyImport_ImportModule

static int cache_empty(void)
{
    if (cache_ready) return 0;
#if CACHE_MODULE == 1
    for (int i = 0; i < NAME_COUNT; i++) if (names[i]) return 0;
    for (int i = 0; i < 4; i++) if (directions[i]) return 0;
    return !empty_string && !space_string;
#elif CACHE_MODULE == 2
    return !LexerPosName && !Bailout && !PDFLexerType && !PDFSyntaxErrorType &&
        !PDFNameType && !SegmentType && !HypotFunction && !PathWarning && !PathModule;
#else
    return !kind_operand && !kind_operator && !lexer_pos_name;
#endif
}

static PyObject *cached_position_or_direction(void)
{
#if CACHE_MODULE == 1
    return directions[DOWN];
#elif CACHE_MODULE == 2
    return LexerPosName;
#else
    return lexer_pos_name;
#endif
}

static int failed_init(int ready, PyObject *saved)
{
    PyObject *result = subject_init();
    int memory_error = PyErr_ExceptionMatches(PyExc_MemoryError);
    PyErr_Clear();
    Py_XDECREF(result);
    if (result || !memory_error || (ready ?
            (!cache_ready || cached_position_or_direction() != saved) : !cache_empty())) {
        PyErr_SetString(PyExc_AssertionError, "initializer failed to preserve cache ownership");
        return -1;
    }
    return 0;
}

static PyObject *run_probe(PyObject *self, PyObject *unused)
{
    PyObject *result, *saved;
    int checks = 0;
    (void)self;
    (void)unused;
    if (!cache_empty()) {
        PyErr_SetString(PyExc_AssertionError, "probe must run once in a fresh module");
        return NULL;
    }
#if CACHE_MODULE == 1
    int strings = NAME_COUNT + 6;
#elif CACHE_MODULE == 2
    int strings = 1;
#else
    int strings = 3;
#endif
    for (intern_at = 1; intern_at <= strings; intern_at++) {
        intern_calls = 0;
        if (failed_init(0, NULL)) return NULL;
        checks++;
    }
    intern_at = 0;
    create_fails = 1;
    if (failed_init(0, NULL)) return NULL;
    checks++;
    create_fails = 0;
#if CACHE_MODULE == 2
    /* Fail each dependency import after interning pos, including partially
     * owned lexer/path dependencies. Imports still use the real Python modules. */
    for (import_at = 1; import_at <= 7; import_at++) {
        import_calls = 0;
        if (failed_init(0, NULL)) return NULL;
        checks++;
    }
    import_at = 0;
#endif
#if CACHE_MODULE != 1
    type_fails = 1;
    if (failed_init(0, NULL)) return NULL;
    checks++;
    type_fails = 0;
    for (add_at = 1; add_at <= (CACHE_MODULE == 2 ? 2 : 1); add_at++) {
        add_calls = 0;
        if (failed_init(0, NULL)) return NULL;
        checks++;
    }
    add_at = 0;
#endif
    result = subject_init();
    if (!result) return NULL;
    Py_DECREF(result);
    saved = cached_position_or_direction();
    create_fails = 1;
    if (failed_init(1, saved)) return NULL;
    checks++;
    create_fails = 0;
#if CACHE_MODULE != 1
    type_fails = 1;
    if (failed_init(1, saved)) return NULL;
    checks++;
    type_fails = 0;
    for (add_at = 1; add_at <= (CACHE_MODULE == 2 ? 2 : 1); add_at++) {
        add_calls = 0;
        if (failed_init(1, saved)) return NULL;
        checks++;
    }
    add_at = 0;
#endif
    /* Later successful initialization must also reuse the same cache. */
    result = subject_init();
    if (!result) return NULL;
    Py_DECREF(result);
    if (cached_position_or_direction() != saved) {
        PyErr_SetString(PyExc_AssertionError, "later initialization replaced the cache");
        return NULL;
    }
    return PyLong_FromLong(checks);
}

static PyMethodDef probe_methods[] = {
    {"run", run_probe, METH_NOARGS, NULL}, {NULL, NULL, 0, NULL}
};
static PyModuleDef probe_module = {
    PyModuleDef_HEAD_INIT, "_cache_init_probe", NULL, -1,
    probe_methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__cache_init_probe(void)
{
    return PyModule_Create(&probe_module);
}
