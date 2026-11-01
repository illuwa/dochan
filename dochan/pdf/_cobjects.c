/* Handwritten mirror of objects.py, based on the repository's own lexer.
 * Uncertain spellings abort transactionally: Python replays from the original
 * position, including its exception message, cursor and recovery counters.
 * No Python object/state is published until a complete parse succeeds. */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <string.h>

typedef struct { PyObject *bailout, *name, *ref; } ModuleState;
typedef struct {
    const unsigned char *b;
    Py_ssize_t n, p, depth, maxdepth, maxitems, stray, fuel;
    int skip;
    ModuleState *m;
} Parser;

static int ws(unsigned char c)
{ return c == 0 || c == 9 || c == 10 || c == 12 || c == 13 || c == 32; }
static int delim(unsigned char c)
{ return c == '(' || c == ')' || c == '<' || c == '>' || c == '[' ||
         c == ']' || c == '{' || c == '}' || c == '/' || c == '%'; }
static int hex(unsigned char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static PyObject *bail(Parser *s)
{ PyErr_SetString(s->m->bailout, "replay with Python lexer"); return NULL; }
static int spend(Parser *s, Py_ssize_t count)
{
    if (count > s->fuel) { s->fuel = 0; bail(s); return -1; }
    s->fuel -= count;
    return 0;
}
static int gap(Parser *s)
{
    Py_ssize_t start = s->p;
    while (s->p < s->n) {
        if (ws(s->b[s->p])) s->p++;
        else if (s->b[s->p] == '%') {
            do { s->p++; } while (s->p < s->n && s->b[s->p] != '\r' && s->b[s->p] != '\n');
        } else break;
    }
    return spend(s, s->p - start);
}
static int token(Parser *s, Py_ssize_t *start, Py_ssize_t *size)
{
    *start = s->p;
    while (s->p < s->n && !ws(s->b[s->p]) && !delim(s->b[s->p])) s->p++;
    *size = s->p - *start;
    return spend(s, *size);
}
static int digits(const unsigned char *b, Py_ssize_t n)
{
    Py_ssize_t i;
    if (!n) return 0;
    for (i = 0; i < n; i++) if (b[i] < '0' || b[i] > '9') return 0;
    return 1;
}
/* Plain small integers avoid allocating a token. Unusual legal spellings
 * (underscores, exponents following a dot, huge integers) use CPython itself. */
static PyObject *number(Parser *s, Py_ssize_t start, Py_ssize_t size, int *real, int *negative)
{
    const unsigned char *b = s->b + start;
    Py_ssize_t i = 0, ndigits;
    long long v = 0;
    int sign = 1;
    PyObject *raw, *value;
    *real = memchr(b, '.', (size_t)size) != NULL;
    *negative = 0;
    if (size && (b[0] == '+' || b[0] == '-')) { sign = b[0] == '-' ? -1 : 1; i++; }
    ndigits = size - i;
    if (!*real && ndigits <= 18 && digits(b + i, ndigits)) {
        for (; i < size; i++) v = v * 10 + b[i] - '0';
        *negative = sign < 0 && v != 0;
        return PyLong_FromLongLong(sign * v);
    }
    /* Ordinary decimal floats take the same locale-independent converter
     * used by CPython, without a temporary bytes object and type call.
     * Exponents/underscores and other unusual spellings retain the slow path. */
    if (*real && size <= 64) {
        Py_ssize_t j = i, count = 0;
        int dots = 0;
        for (; j < size; j++) {
            if (b[j] >= '0' && b[j] <= '9') count++;
            else if (b[j] == '.') dots++;
            else break;
        }
        if (j == size && count && dots == 1) {
            char text[65], *end;
            double decimal;
            memcpy(text, b, (size_t)size);
            text[size] = '\0';
            decimal = PyOS_string_to_double(text, &end, NULL);
            if (PyErr_Occurred()) return NULL;
            if (end == text + size) return PyFloat_FromDouble(decimal);
        }
    }
    if (size > 4096) return bail(s);
    raw = PyBytes_FromStringAndSize((const char *)b, size);
    if (!raw) return NULL;
    value = PyObject_CallFunctionObjArgs(*real ? (PyObject *)&PyFloat_Type : (PyObject *)&PyLong_Type, raw, NULL);
    Py_DECREF(raw);
    if (!value) {
        if (PyErr_ExceptionMatches(PyExc_ValueError)) { PyErr_Clear(); return bail(s); }
        return NULL;
    }
    if (!*real) {
        PyObject *zero = PyLong_FromLong(0);
        if (!zero) { Py_DECREF(value); return NULL; }
        *negative = PyObject_RichCompareBool(value, zero, Py_LT);
        Py_DECREF(zero);
        if (*negative < 0) { Py_DECREF(value); return NULL; }
    }
    return value;
}
static PyObject *name(Parser *s, int key)
{
    Py_ssize_t start, size, i, used = 0;
    unsigned char *out;
    PyObject *text, *result;
    s->p++;
    if (token(s, &start, &size) < 0) return NULL;
    /* Most names contain no escape. Decode directly from the immutable
     * input rather than allocating and copying a byte buffer per dict key. */
    if (!memchr(s->b + start, '#', (size_t)size)) {
        text = PyUnicode_DecodeUTF8((const char *)s->b + start, size, "replace");
        if (!text || key) return text;
        result = PyObject_CallFunctionObjArgs(s->m->name, text, NULL);
        Py_DECREF(text);
        return result;
    }
    out = PyMem_Malloc((size_t)(size ? size : 1));
    if (!out) return PyErr_NoMemory();
    for (i = 0; i < size; i++) {
        unsigned char c = s->b[start + i];
        if (c == '#' && size - i > 2) {
            int a = hex(s->b[start + i + 1]), b = hex(s->b[start + i + 2]);
            /* int(pair,16) accepts signs; preserve all non-hex cases by replay. */
            if (a < 0 || b < 0) { PyMem_Free(out); return bail(s); }
            c = (unsigned char)(16 * a + b); i += 2;
        }
        out[used++] = c;
    }
    text = PyUnicode_DecodeUTF8((const char *)out, used, "replace");
    PyMem_Free(out);
    if (!text || key) return text;
    result = PyObject_CallFunctionObjArgs(s->m->name, text, NULL);
    Py_DECREF(text);
    return result;
}
/* Two passes bound allocation by decoded string size, not remaining PDF size. */
static int string_bytes(Parser *s, Py_ssize_t start, int literal,
                        unsigned char *out, Py_ssize_t *used, Py_ssize_t *end)
{
    Py_ssize_t p = start + 1, k = 0, depth = 1;
    int high = -1;
    while (p < s->n) {
        unsigned char c;
        if (!out && spend(s, 1) < 0) return 0;
        c = s->b[p++];
        if (!literal) {
            int d;
            if (c == '>') {
                if (high >= 0) { if (out) out[k] = (unsigned char)(high << 4); k++; }
                *used = k; *end = p; return 1;
            }
            if (ws(c)) continue;
            d = hex(c);
            if (d < 0) return 0;
            if (high < 0) { high = d; continue; }
            c = (unsigned char)(high * 16 + d); high = -1;
        } else if (c == ')') {
            if (--depth == 0) { *used = k; *end = p; return 1; }
        } else if (c == '(') depth++;
        else if (c == '\\') {
            int j;
            unsigned int octal;
            if (p == s->n) return 0;
            c = s->b[p++];
            switch (c) {
                case 'n': c = '\n'; break;
                case 'r': c = '\r'; break;
                case 't': c = '\t'; break;
                case 'b': c = '\b'; break;
                case 'f': c = '\f'; break;
                case '\r': if (p < s->n && s->b[p] == '\n') p++; continue;
                case '\n': continue;
                default:
                    if (c >= '0' && c <= '7') {
                        octal = c - '0';
                        for (j = 0; j < 2 && p < s->n && s->b[p] >= '0' && s->b[p] <= '7'; j++)
                            octal = octal * 8 + s->b[p++] - '0';
                        c = (unsigned char)(octal & 255);
                    }
            }
        }
        if (out) out[k] = c;
        k++;
    }
    return 0;
}
static PyObject *string(Parser *s, int literal)
{
    Py_ssize_t used = 0, end = 0;
    unsigned char *out;
    PyObject *result;
    if (!string_bytes(s, s->p, literal, NULL, &used, &end)) return bail(s);
    if (spend(s, end - s->p) < 0) return NULL;
    out = PyMem_Malloc((size_t)(used ? used : 1));
    if (!out) return PyErr_NoMemory();
    string_bytes(s, s->p, literal, out, &used, &end);
    result = PyBytes_FromStringAndSize((const char *)out, used);
    PyMem_Free(out);
    s->p = end;
    return result;
}
static PyObject *object(Parser *s);
static PyObject *collection(Parser *s, int dictionary)
{
    PyObject *result = NULL, *key = NULL, *value = NULL;
    Py_ssize_t count = 0;
    int after_string = 0;
    s->p += dictionary ? 2 : 1;
    s->depth++;
    /* Hard C stack bound remains even if a caller increases the Python limit. */
    if (s->depth > s->maxdepth || s->depth > 64) { s->depth--; return bail(s); }
    result = dictionary ? PyDict_New() : PyList_New(0);
    if (!result) goto failed;
    for (;;) {
        if ((count & 1023) == 0 && PyErr_CheckSignals() < 0) goto failed;
        if (gap(s) < 0) goto failed;
        if (s->p >= s->n) { bail(s); goto failed; }
        if (dictionary) {
            if (after_string && s->b[s->p] == ')') {
                s->p++; s->stray++; after_string = 0; continue;
            }
            if (s->n - s->p >= 2 && s->b[s->p] == '>' && s->b[s->p + 1] == '>') {
                s->p += 2; break;
            }
            if (s->b[s->p] != '/' || PyDict_Size(result) >= s->maxitems) { bail(s); goto failed; }
            key = name(s, 1);
            if (!key || gap(s) < 0) goto failed;
            after_string = s->p < s->n && s->b[s->p] == '(';
        } else {
            unsigned char c = s->b[s->p];
            if (c == ']') { s->p++; break; }
            if (count >= s->maxitems) { bail(s); goto failed; }
            if (s->skip && ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '"' || c == '\'')) {
                Py_ssize_t start, size;
                if (token(s, &start, &size) < 0) goto failed;
                if (!((size == 4 && (!memcmp(s->b + start, "true", 4) || !memcmp(s->b + start, "null", 4))) ||
                      (size == 5 && !memcmp(s->b + start, "false", 5)))) continue;
                s->p = start;
            }
        }
        value = object(s);
        if (!value) goto failed;
        if (dictionary ? PyDict_SetItem(result, key, value) < 0 : PyList_Append(result, value) < 0) goto failed;
        Py_CLEAR(key); Py_CLEAR(value); count++;
    }
    s->depth--;
    return result;
failed:
    Py_XDECREF(result); Py_XDECREF(key); Py_XDECREF(value);
    s->depth--;
    return NULL;
}
static PyObject *object(Parser *s)
{
    Py_ssize_t start, size, saved, start2, size2, start3, size3;
    int real, negative;
    PyObject *value, *gen, *result;
    if (spend(s, 1) < 0 || gap(s) < 0) return NULL;
    if (s->p >= s->n) return bail(s);
    switch (s->b[s->p]) {
        case '/': return name(s, 0);
        case '(': return string(s, 1);
        case '[': return collection(s, 0);
        case '<':
            if (s->n - s->p >= 2 && s->b[s->p + 1] == '<') return collection(s, 1);
            return string(s, 0);
        default: break;
    }
    if (token(s, &start, &size) < 0) return NULL;
    if (!size) return bail(s);
    if (size == 4 && !memcmp(s->b + start, "true", 4)) Py_RETURN_TRUE;
    if (size == 5 && !memcmp(s->b + start, "false", 5)) Py_RETURN_FALSE;
    if (size == 4 && !memcmp(s->b + start, "null", 4)) Py_RETURN_NONE;
    value = number(s, start, size, &real, &negative);
    if (!value || real || negative) return value;
    saved = s->p;
    if (gap(s) < 0 || token(s, &start2, &size2) < 0) goto failed;
    if (digits(s->b + start2, size2)) {
        if (gap(s) < 0 || token(s, &start3, &size3) < 0) goto failed;
        if (size3 == 1 && s->b[start3] == 'R') {
            gen = number(s, start2, size2, &real, &negative);
            if (!gen) goto failed;
            result = PyObject_CallFunctionObjArgs(s->m->ref, value, gen, NULL);
            Py_DECREF(gen); Py_DECREF(value);
            return result;
        }
    }
    s->p = saved;
    return value;
failed:
    Py_DECREF(value); return NULL;
}
static int init_parser(Parser *s, PyObject *module, PyObject *data, Py_ssize_t pos,
                       Py_ssize_t depth, int skip, Py_ssize_t maxdepth, Py_ssize_t maxitems)
{
    char *buf;
    s->m = PyModule_GetState(module);
    if (!PyBytes_CheckExact(data)) { bail(s); return -1; }
    if (PyBytes_AsStringAndSize(data, &buf, &s->n) < 0) return -1;
    if (pos < 0 || pos > s->n || depth < 0) { bail(s); return -1; }
    s->b = (const unsigned char *)buf; s->p = pos; s->depth = depth;
    s->skip = skip; s->maxdepth = maxdepth; s->maxitems = maxitems; s->stray = 0;
    s->fuel = 32 * 1024 * 1024;
    return 0;
}
static PyObject *parse(PyObject *module, PyObject *args)
{
    PyObject *data, *value, *result;
    Py_ssize_t pos, depth, maxdepth, maxitems;
    int skip;
    Parser s;
    if (!PyArg_ParseTuple(args, "Onninn", &data, &pos, &depth, &skip, &maxdepth, &maxitems)) return NULL;
    if (init_parser(&s, module, data, pos, depth, skip, maxdepth, maxitems) < 0) return NULL;
    value = object(&s);
    if (!value) return NULL;
    result = Py_BuildValue("Onn", value, s.p, s.stray);
    Py_DECREF(value);
    return result;
}
static PyObject *scan(PyObject *module, PyObject *args)
{
    PyObject *data;
    Py_ssize_t pos, start, size;
    int whitespace;
    Parser s;
    if (!PyArg_ParseTuple(args, "Oni", &data, &pos, &whitespace)) return NULL;
    if (init_parser(&s, module, data, pos, 0, 0, 64, 100000) < 0) return NULL;
    if (whitespace) {
        if (gap(&s) < 0) return NULL;
        return PyLong_FromSsize_t(s.p);
    }
    if (token(&s, &start, &size) < 0) return NULL;
    /* No "#" formats: a wheel built with 3.13 headers (where PY_SSIZE_T_CLEAN is a
     * no-op) calls the plain Py_BuildValue, which rejects "#" on 3.10-3.12 runtimes. */
    {
        PyObject *bytes = PyBytes_FromStringAndSize((const char *)s.b + start, size);
        PyObject *end, *pair;
        if (!bytes) return NULL;
        end = PyLong_FromSsize_t(s.p);
        if (!end) { Py_DECREF(bytes); return NULL; }
        pair = PyTuple_Pack(2, bytes, end);
        Py_DECREF(bytes); Py_DECREF(end);
        return pair;
    }
}
/* Batch results are keyed by OFFSET, never by object number. This preserves
 * first-match duplicate numbers and the caller's xref-index fallback. Failed
 * objects stay absent: diagnostics are produced only when originally requested.
 * Work is bounded across the entire batch, including overlapping objects. */
static PyObject *batch(PyObject *module, PyObject *args)
{
    PyObject *data, *pairs = NULL, *parsed = NULL, *num = NULL, *off = NULL;
    PyObject *pair = NULL, *value = NULL, *entry = NULL, *result = NULL;
    Py_ssize_t n, first, maxdepth, maxitems, i, a, alen, b, blen, offset;
    int real, negative, present;
    Parser s;
    if (!PyArg_ParseTuple(args, "Onnnn", &data, &n, &first, &maxdepth, &maxitems)) return NULL;
    if (init_parser(&s, module, data, 0, 0, 0, maxdepth, maxitems) < 0) return NULL;
    if (n < 0 || n > 500000 || first < 0) return bail(&s);
    if (s.n < (s.fuel - 4096) / 4) s.fuel = 4 * s.n + 4096;
    pairs = PyList_New(0); parsed = PyDict_New();
    if (!pairs || !parsed) goto done;
    for (i = 0; i < n; i++) {
        if (gap(&s) < 0 || token(&s, &a, &alen) < 0 || gap(&s) < 0 || token(&s, &b, &blen) < 0) goto done;
        if (!digits(s.b + a, alen) || !digits(s.b + b, blen)) break;
        num = number(&s, a, alen, &real, &negative);
        if (!num) goto done;
        off = number(&s, b, blen, &real, &negative);
        if (!off) goto done;
        pair = PyTuple_Pack(2, num, off);
        if (!pair || PyList_Append(pairs, pair) < 0) goto done;
        Py_CLEAR(pair); Py_CLEAR(num); Py_CLEAR(off);
    }
    for (i = 0; i < PyList_Size(pairs); i++) {
        PyObject *item = PyList_GetItem(pairs, i), *key;
        if (PyErr_CheckSignals() < 0) goto done;
        key = PyTuple_GetItem(item, 1);
        present = PyDict_Contains(parsed, key);
        if (present < 0) goto done;
        if (present) continue;
        offset = PyLong_AsSsize_t(key);
        if (offset == -1 && PyErr_Occurred()) {
            if (!PyErr_ExceptionMatches(PyExc_OverflowError)) goto done;
            PyErr_Clear(); continue;
        }
        if (first >= s.n || offset >= s.n - first) continue;
        s.p = first + offset; s.stray = 0;
        value = object(&s);
        if (!value) {
            if (!PyErr_ExceptionMatches(s.m->bailout)) goto done;
            PyErr_Clear();
            /* Stop eager work at the budget; remaining objects parse lazily. */
            if (s.fuel <= 0) break;
            /* NULL marker also prevents repeated malformed duplicate offsets. */
            if (PyDict_SetItem(parsed, key, Py_None) < 0) goto done;
            continue;
        }
        entry = Py_BuildValue("On", value, s.stray);
        Py_CLEAR(value);
        if (!entry || PyDict_SetItem(parsed, key, entry) < 0) goto done;
        Py_CLEAR(entry);
    }
    result = PyTuple_Pack(2, pairs, parsed);
done:
    Py_XDECREF(pairs); Py_XDECREF(parsed); Py_XDECREF(num); Py_XDECREF(off);
    Py_XDECREF(pair); Py_XDECREF(value); Py_XDECREF(entry);
    return result;
}
/* Parse header, object and stream keyword without Python method crossings.
 * Stream length callbacks and recovered-list side effects remain in Python,
 * after this transaction succeeds; no callback is ever replayed. */
static PyObject *indirect(PyObject *module, PyObject *args)
{
    PyObject *data, *num = NULL, *gen = NULL, *value = NULL, *result = NULL;
    PyObject *stream_start = NULL;
    Py_ssize_t pos, maxdepth, maxitems, a, alen, b, blen, c, clen;
    int real, negative;
    Parser s;
    if (!PyArg_ParseTuple(args, "Onnn", &data, &pos, &maxdepth, &maxitems)) return NULL;
    if (init_parser(&s, module, data, pos, 0, 0, maxdepth, maxitems) < 0) return NULL;
    if (gap(&s) < 0 || token(&s, &a, &alen) < 0 || gap(&s) < 0 || token(&s, &b, &blen) < 0 ||
        gap(&s) < 0 || token(&s, &c, &clen) < 0) goto done;
    if (!digits(s.b + a, alen) || !digits(s.b + b, blen) || clen != 3 || memcmp(s.b + c, "obj", 3)) {
        bail(&s); goto done;
    }
    num = number(&s, a, alen, &real, &negative);
    if (!num) goto done;  /* a failed conversion leaves Bailout pending; never call PyLong on top */
    gen = number(&s, b, blen, &real, &negative);
    if (!gen) goto done;
    value = object(&s);
    if (!value || gap(&s) < 0 || token(&s, &c, &clen) < 0) goto done;
    if (clen == 6 && !memcmp(s.b + c, "stream", 6) && PyDict_Check(value)) {
        if (s.p < s.n && s.b[s.p] == '\r') {
            s.p++;
            if (s.p < s.n && s.b[s.p] == '\n') s.p++;
        } else if (s.p < s.n && s.b[s.p] == '\n') s.p++;
        stream_start = PyLong_FromSsize_t(s.p);
    } else { stream_start = Py_None; Py_INCREF(stream_start); }
    if (stream_start) result = Py_BuildValue("OOOOn", num, gen, value, stream_start, s.stray);
done:
    Py_XDECREF(num); Py_XDECREF(gen); Py_XDECREF(value); Py_XDECREF(stream_start);
    return result;
}
static PyObject *stream(PyObject *module, PyObject *args)
{
    PyObject *data, *length;
    Py_ssize_t start, size = -1, end, tail, limit;
    Parser s;
    if (!PyArg_ParseTuple(args, "OnO", &data, &start, &length)) return NULL;
    if (init_parser(&s, module, data, start, 0, 0, 64, 100000) < 0) return NULL;
    /* A resolver may return subclasses with custom arithmetic; replay just
     * boundary selection in Python, never the resolver itself. */
    if (PyLong_Check(length) && !PyLong_CheckExact(length) && !PyBool_Check(length)) return bail(&s);
    if (PyLong_Check(length)) {
        size = PyLong_AsSsize_t(length);
        if (size == -1 && PyErr_Occurred()) {
            if (!PyErr_ExceptionMatches(PyExc_OverflowError)) return NULL;
            PyErr_Clear(); size = -1;
        }
    }
    if (size >= 0 && size <= s.n - start) {
        end = start + size;
        limit = s.n - end > 20 ? end + 20 : s.n;
        tail = end;
        while (tail < limit && ws(s.b[tail])) tail++;
        if (limit - tail >= 9 && !memcmp(s.b + tail, "endstream", 9))
            return PyBytes_FromStringAndSize((const char *)s.b + start, size);
    }
    for (end = start; s.n - end >= 9; end++) {
        if ((end & 65535) == 0 && PyErr_CheckSignals() < 0) return NULL;
        if (s.b[end] == 'e' && !memcmp(s.b + end, "endstream", 9)) {
            if (end - start >= 2 && s.b[end - 2] == '\r' && s.b[end - 1] == '\n') end -= 2;
            else if (end > start && (s.b[end - 1] == '\n' || s.b[end - 1] == '\r')) end--;
            return PyBytes_FromStringAndSize((const char *)s.b + start, end - start);
        }
    }
    return bail(&s);
}

static PyMethodDef methods[] = {
    {"indirect", indirect, METH_VARARGS, "Parse indirect header and stream start."},
    {"stream", stream, METH_VARARGS, "Select raw stream boundaries."},
    {"parse", parse, METH_VARARGS, "Parse one object transactionally."},
    {"scan", scan, METH_VARARGS, "Skip whitespace or read a token."},
    {"batch", batch, METH_VARARGS, "Parse an object stream header and its objects."},
    {NULL, NULL, 0, NULL}
};
static int traverse(PyObject *module, visitproc visit, void *arg)
{
    ModuleState *s = PyModule_GetState(module);
    Py_VISIT(s->bailout); Py_VISIT(s->name); Py_VISIT(s->ref); return 0;
}
static int clear(PyObject *module)
{
    ModuleState *s = PyModule_GetState(module);
    Py_CLEAR(s->bailout); Py_CLEAR(s->name); Py_CLEAR(s->ref); return 0;
}
static struct PyModuleDef definition = {
    PyModuleDef_HEAD_INIT, "_cobjects", NULL, sizeof(ModuleState), methods,
    NULL, traverse, clear, NULL
};
PyMODINIT_FUNC PyInit__cobjects(void)
{
    PyObject *module = PyModule_Create(&definition), *objects;
    ModuleState *s;
    if (!module) return NULL;
    s = PyModule_GetState(module);
    objects = PyImport_ImportModule("dochan.pdf.objects");
    if (!objects) { Py_DECREF(module); return NULL; }
    s->name = PyObject_GetAttrString(objects, "PDFName");
    s->ref = PyObject_GetAttrString(objects, "PDFRef");
    Py_DECREF(objects);
    s->bailout = PyErr_NewException("dochan.pdf._cobjects.Bailout", NULL, NULL);
    if (!s->name || !s->ref || !s->bailout) { Py_DECREF(module); return NULL; }
    Py_INCREF(s->bailout);
    if (PyModule_AddObject(module, "Bailout", s->bailout) < 0) {
        Py_DECREF(s->bailout); Py_DECREF(module); return NULL;
    }
    return module;
}
