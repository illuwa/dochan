/* Handwritten from this repository's ContentScanner and PDFLexer contracts.
 * ISO 32000-1 sections 7.2 and 7.3 define whitespace and delimiters.
 * No generated code, external parser code, or private CPython API is used. */
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <string.h>

typedef struct {
    PyObject_HEAD
    PyObject *data;
    PyObject *lexer;
    PyObject *parse_object;
    PyObject *syntax_error;
    PyObject *external_pos;
    const unsigned char *buf;
    Py_ssize_t size;
    Py_ssize_t pos;
    /* The Python regex iterator never rewinds when the public pos rewinds. */
    Py_ssize_t cursor;
} Scanner;

static int
whitespace(unsigned char ch)
{
    return ch == 0 || ch == 9 || ch == 10 || ch == 12 || ch == 13 || ch == 32;
}

static int
delimiter(unsigned char ch)
{
    return ch == '(' || ch == ')' || ch == '<' || ch == '>' ||
           ch == '[' || ch == ']' || ch == '{' || ch == '}' ||
           ch == '/' || ch == '%';
}

/* All loop indices originate at a checked, nonnegative regex cursor. */
static Py_ssize_t
token_end(const unsigned char *buf, Py_ssize_t start, Py_ssize_t size)
{
    Py_ssize_t end = start;
    unsigned char ch;
    if (start < 0 || start >= size)
        return size;
    ch = buf[start];
    if (whitespace(ch)) {
        do { end++; } while (end < size && whitespace(buf[end]));
    } else if (ch == '%') {
        do { end++; } while (end < size && buf[end] != '\r' && buf[end] != '\n');
    } else if (delimiter(ch)) {
        end++;
    } else {
        do { end++; } while (end < size && !whitespace(buf[end]) && !delimiter(buf[end]));
    }
    return end;
}

static Py_ssize_t
gap(const unsigned char *buf, Py_ssize_t pos, Py_ssize_t size)
{
    if (pos < 0 || pos > size)
        return size;
    while (pos < size) {
        if (whitespace(buf[pos])) {
            pos++;
        } else if (buf[pos] == '%') {
            do { pos++; } while (pos < size && buf[pos] != '\r' && buf[pos] != '\n');
        } else {
            break;
        }
    }
    return pos;
}

static int
may_be_reference(const unsigned char *buf, Py_ssize_t pos, Py_ssize_t size)
{
    Py_ssize_t first = gap(buf, pos, size), end, second;
    if (first == pos || first >= size || buf[first] < '0' || buf[first] > '9')
        return 0;
    end = first;
    while (end < size && !whitespace(buf[end]) && !delimiter(buf[end])) {
        if (buf[end] < '0' || buf[end] > '9')
            return 0;
        end++;
    }
    second = gap(buf, end, size);
    return second > end && second < size && buf[second] == 'R' &&
           (second == size - 1 || whitespace(buf[second + 1]) || delimiter(buf[second + 1]));
}

static void
set_position(Scanner *self, Py_ssize_t pos)
{
    self->pos = pos;
    Py_CLEAR(self->external_pos);
}

static PyObject *
get_pos(Scanner *self, void *closure)
{
    (void)closure;
    if (self->external_pos != NULL) {
        Py_INCREF(self->external_pos);
        return self->external_pos;
    }
    return PyLong_FromSsize_t(self->pos);
}

static int
set_pos(Scanner *self, PyObject *value, void *closure)
{
    (void)closure;
    Py_ssize_t pos;
    PyObject *previous;
    if (value == NULL || !PyLong_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "pos must be an integer");
        return -1;
    }
    pos = PyLong_AsSsize_t(value);
    if (pos == -1 && PyErr_Occurred()) {
        int negative;
        PyObject *zero;
        if (!PyErr_ExceptionMatches(PyExc_OverflowError))
            return -1;
        PyErr_Clear();
        zero = PyLong_FromLong(0);
        if (zero == NULL)
            return -1;
        negative = PyObject_RichCompareBool(value, zero, Py_LT);
        Py_DECREF(zero);
        if (negative < 0)
            return -1;
        /* Retain the actual arbitrary-sized integer for the public property.
         * Only comparisons use the saturated value; it is never a pointer index. */
        pos = negative ? PY_SSIZE_T_MIN : PY_SSIZE_T_MAX;
    }
    Py_INCREF(value);
    previous = self->external_pos;
    self->external_pos = value;
    self->pos = pos;
    Py_XDECREF(previous);
    return 0;
}

static PyObject *
get_data(Scanner *self, void *closure)
{
    (void)closure;
    if (self->data == NULL) {
        PyErr_SetString(PyExc_AttributeError, "Scanner is not initialized");
        return NULL;
    }
    Py_INCREF(self->data);
    return self->data;
}

static int
scanner_init(Scanner *self, PyObject *args, PyObject *kwargs)
{
    static char *keywords[] = {"data", NULL};
    PyObject *data, *module = NULL, *factory = NULL, *lexer = NULL;
    PyObject *syntax_error = NULL, *parse = NULL;
    PyObject *previous_data, *previous_lexer, *previous_parse, *previous_error;
    char *buf;
    Py_ssize_t size;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O:Scanner", keywords, &data))
        return -1;
    if (!PyBytes_Check(data)) {
        PyErr_SetString(PyExc_TypeError, "data must be bytes");
        return -1;
    }
    if (PyBytes_AsStringAndSize(data, &buf, &size) < 0)
        return -1;
    module = PyImport_ImportModule("dochan.pdf.objects");
    if (module == NULL)
        goto error;
    factory = PyObject_GetAttrString(module, "PDFLexer");
    syntax_error = PyObject_GetAttrString(module, "PDFSyntaxError");
    if (factory == NULL || syntax_error == NULL)
        goto error;
    lexer = PyObject_CallFunctionObjArgs(factory, data, NULL);
    if (lexer == NULL || PyObject_SetAttrString(lexer, "skip_array_operators", Py_True) < 0)
        goto error;
    parse = PyObject_GetAttrString(lexer, "parse_object");
    if (parse == NULL)
        goto error;
    Py_INCREF(data);
    previous_data = self->data;
    previous_lexer = self->lexer;
    previous_parse = self->parse_object;
    previous_error = self->syntax_error;
    self->data = data;
    self->lexer = lexer;
    self->parse_object = parse;
    self->syntax_error = syntax_error;
    self->buf = (const unsigned char *)buf;
    self->size = size;
    self->cursor = 0;
    set_position(self, 0);
    /* Publish a complete valid state before releasing objects whose finalizers
     * might reenter Python (e.g. a user-supplied PDFLexer subclass). */
    Py_XDECREF(previous_data);
    Py_XDECREF(previous_lexer);
    Py_XDECREF(previous_parse);
    Py_XDECREF(previous_error);
    Py_DECREF(factory);
    Py_DECREF(module);
    return 0;
error:
    Py_XDECREF(parse);
    Py_XDECREF(lexer);
    Py_XDECREF(syntax_error);
    Py_XDECREF(factory);
    Py_XDECREF(module);
    return -1;
}

/* Fast paths are deliberately narrower than Python's int/float grammars.
 * Unusual spellings (including exponents and underscores) use Python itself. */
static PyObject *
number(const unsigned char *buf, Py_ssize_t size, int *is_float, int *negative)
{
    Py_ssize_t i = 0, digits = 0;
    int sign = 1, dots = 0, plain = 1;
    long long integer = 0;
    PyObject *token, *value;
    *is_float = memchr(buf, '.', (size_t)size) != NULL;
    if (size > 0 && (buf[0] == '+' || buf[0] == '-')) {
        sign = buf[0] == '-' ? -1 : 1;
        i++;
    }
    for (; i < size; i++) {
        if (buf[i] >= '0' && buf[i] <= '9') {
            digits++;
            if (digits <= 18 && !*is_float)
                integer = integer * 10 + (buf[i] - '0');
        } else if (buf[i] == '.') {
            dots++;
        } else {
            plain = 0;
            break;
        }
    }
    if (plain && digits > 0 && dots == 0 && digits <= 18) {
        *negative = sign < 0 && integer != 0;
        return PyLong_FromLongLong(sign * integer);
    }
    if (plain && digits > 0 && dots == 1 && size <= 64) {
        char text[65], *end;
        double real;
        memcpy(text, buf, (size_t)size);
        text[size] = '\0';
        real = PyOS_string_to_double(text, &end, NULL);
        if (PyErr_Occurred())
            return NULL;
        if (end == text + size)
            return PyFloat_FromDouble(real);
        /* Defensive fallback if a supported interpreter rejects this spelling. */
    }
    token = PyBytes_FromStringAndSize((const char *)buf, size);
    if (token == NULL)
        return NULL;
    value = PyObject_CallFunctionObjArgs(
        *is_float ? (PyObject *)&PyFloat_Type : (PyObject *)&PyLong_Type, token, NULL);
    Py_DECREF(token);
    if (value != NULL && !*is_float) {
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL) {
            Py_DECREF(value);
            return NULL;
        }
        *negative = PyObject_RichCompareBool(value, zero, Py_LT);
        Py_DECREF(zero);
        if (*negative < 0) {
            Py_DECREF(value);
            return NULL;
        }
    }
    return value;
}

/* Interned once at import: the interpreter loop compares the event kind against
 * the same interned literals, so sharing the objects makes that an identity test. */
static PyObject *kind_operand = NULL;
static PyObject *kind_operator = NULL;
static PyObject *lexer_pos_name = NULL;
static int cache_ready;

/* Consumes value's reference on both success and allocation failure. */
static PyObject *
event(PyObject *kind, PyObject *value)
{
    PyObject *result = PyTuple_Pack(2, kind, value);
    Py_DECREF(value);
    return result;
}

static PyObject *
scanner_next(Scanner *self, PyObject *unused)
{
    (void)unused;
    const unsigned char *buf;
    Py_ssize_t size, start, end;
    PyObject *data, *value = NULL, *result = NULL;
    if (self->data == NULL) {
        PyErr_SetString(PyExc_TypeError, "Scanner is not initialized");
        return NULL;
    }
    /* Own the backing bytes across all calls into Python, including exceptions. */
    data = self->data;
    Py_INCREF(data);
    buf = self->buf;
    size = self->size;
    while (self->cursor < size) {
        unsigned char ch;
        start = self->cursor;
        end = token_end(buf, start, size);
        self->cursor = end;
        if (start < self->pos) {
            if (self->pos < end)
                self->cursor = self->pos;
            continue;
        }
        ch = buf[start];
        set_position(self, end);
        if (whitespace(ch) || ch == '%')
            continue;
        if (ch == '(' || ch == '<' || ch == '/' || ch == '[' ||
                (ch >= '0' && ch <= '9') || ch == '+' || ch == '-' || ch == '.') {
            if (ch != '(' && ch != '<' && ch != '/' && ch != '[') {
                int is_float = 0, negative = 0;
                value = number(buf + start, end - start, &is_float, &negative);
                if (value == NULL) {
                    if (!PyErr_ExceptionMatches(PyExc_ValueError))
                        goto done;
                    PyErr_Clear();
                } else if (negative || is_float || !may_be_reference(buf, end, size)) {
                    result = event(kind_operand, value);
                    goto done;
                } else {
                    Py_CLEAR(value);
                }
            }
            value = PyLong_FromSsize_t(start);
            if (value == NULL)
                goto done;
            if (PyObject_SetAttr(self->lexer, lexer_pos_name, value) < 0) {
                Py_CLEAR(value);
                goto done;
            }
            Py_CLEAR(value);
            value = PyObject_CallObject(self->parse_object, NULL);
            if (value == NULL) {
                PyObject *position;
                Py_ssize_t pos;
                if (!PyErr_ExceptionMatches(self->syntax_error))
                    goto done;
                PyErr_Clear();
                position = PyObject_GetAttr(self->lexer, lexer_pos_name);
                if (position == NULL)
                    goto done;
                pos = PyLong_AsSsize_t(position);
                Py_DECREF(position);
                if (pos == -1 && PyErr_Occurred())
                    goto done;
                /* PDFLexer positions stay within the byte buffer. */
                if (pos == PY_SSIZE_T_MAX) {
                    PyErr_SetString(PyExc_OverflowError, "lexer position overflow");
                    goto done;
                }
                set_position(self, pos + 1);
                continue;
            } else {
                PyObject *position = PyObject_GetAttr(self->lexer, lexer_pos_name);
                if (position == NULL || set_pos(self, position, NULL) < 0) {
                    Py_XDECREF(position);
                    Py_CLEAR(value);
                    goto done;
                }
                Py_DECREF(position);
                result = event(kind_operand, value);
                goto done;
            }
        }
        if (delimiter(ch))
            continue;
        value = PyBytes_FromStringAndSize((const char *)buf + start, end - start);
        if (value == NULL)
            goto done;
        result = event(kind_operator, value);
        goto done;
    }
    Py_INCREF(Py_None);
    result = Py_None;
done:
    Py_DECREF(data);
    return result;
}

static int
scanner_traverse(Scanner *self, visitproc visit, void *arg)
{
    Py_VISIT(Py_TYPE(self));
    Py_VISIT(self->data);
    Py_VISIT(self->lexer);
    Py_VISIT(self->parse_object);
    Py_VISIT(self->syntax_error);
    Py_VISIT(self->external_pos);
    return 0;
}

static int
scanner_clear(Scanner *self)
{
    self->buf = NULL;
    self->size = self->cursor = 0;
    Py_CLEAR(self->data);
    Py_CLEAR(self->lexer);
    Py_CLEAR(self->parse_object);
    Py_CLEAR(self->syntax_error);
    Py_CLEAR(self->external_pos);
    return 0;
}

static void
scanner_dealloc(Scanner *self)
{
    PyTypeObject *type = Py_TYPE(self);
    freefunc free_object = (freefunc)PyType_GetSlot(type, Py_tp_free);
    PyObject_GC_UnTrack((PyObject *)self);
    scanner_clear(self);
    free_object((PyObject *)self);
    Py_DECREF(type);
}

static PyMethodDef scanner_methods[] = {
    {"next", (PyCFunction)scanner_next, METH_NOARGS, "Return the next content-stream event."},
    {NULL, NULL, 0, NULL}
};

static PyGetSetDef scanner_getset[] = {
    {"data", (getter)get_data, NULL, "Original bytes (read-only).", NULL},
    {"pos", (getter)get_pos, (setter)set_pos, "Mutable scanner position.", NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyType_Slot scanner_slots[] = {
    {Py_tp_new, (void *)PyType_GenericNew},
    {Py_tp_init, (void *)scanner_init},
    {Py_tp_dealloc, (void *)scanner_dealloc},
    {Py_tp_traverse, (void *)scanner_traverse},
    {Py_tp_clear, (void *)scanner_clear},
    {Py_tp_methods, (void *)scanner_methods},
    {Py_tp_getset, (void *)scanner_getset},
    {0, NULL}
};

static PyType_Spec scanner_spec = {
    "dochan.pdf._cscan.Scanner", sizeof(Scanner), 0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC, scanner_slots
};

static struct PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT, "_cscan", "Optional handwritten PDF content scanner.",
    0, NULL, NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC
PyInit__cscan(void)
{
    PyObject *module = PyModule_Create(&module_def);
    PyObject *type;
    if (module == NULL)
        return NULL;
    if (kind_operand == NULL) {
        kind_operand = PyUnicode_InternFromString("operand");
        if (kind_operand == NULL) goto failed;
    }
    if (kind_operator == NULL) {
        kind_operator = PyUnicode_InternFromString("operator");
        if (kind_operator == NULL) goto failed;
    }
    if (lexer_pos_name == NULL) {
        lexer_pos_name = PyUnicode_InternFromString("pos");
        if (lexer_pos_name == NULL) goto failed;
    }
    type = PyType_FromSpec(&scanner_spec);
    if (type == NULL || PyModule_AddObject(module, "Scanner", type) < 0) {
        Py_XDECREF(type);
        goto failed;
    }
    cache_ready = 1;
    return module;
failed:
    if (!cache_ready) {
        Py_CLEAR(kind_operand);
        Py_CLEAR(kind_operator);
        Py_CLEAR(lexer_pos_name);
    }
    Py_DECREF(module);
    return NULL;
}
