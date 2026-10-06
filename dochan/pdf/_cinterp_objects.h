/* Handwritten content-object acceleration from this repository's PDFLexer.
 * Included by _cinterp.c after PDFLexerType, PDFSyntaxErrorType, PDFNameType.
 * All structured fast paths commit the offset only after complete success. */
#ifndef DOCHAN_CINTERP_OBJECTS_H
#define DOCHAN_CINTERP_OBJECTS_H

#include <string.h>

typedef struct {
    PyObject *data;
    PyObject *lexer;
    PyObject *parse_object;
    const unsigned char *buf;
    Py_ssize_t size, pos, cursor;
} ObjScanner;

static int obj_ws(unsigned char c)
{
    return c == 0 || c == 9 || c == 10 || c == 12 || c == 13 || c == 32;
}

static int obj_delim(unsigned char c)
{
    return c == '(' || c == ')' || c == '<' || c == '>' ||
        c == '[' || c == ']' || c == '{' || c == '}' || c == '/' || c == '%';
}

static Py_ssize_t obj_token_end(const unsigned char *b, Py_ssize_t p, Py_ssize_t n)
{
    Py_ssize_t e = p;
    unsigned char c;
    if (p < 0 || p >= n) return n;
    c = b[p];
    if (obj_ws(c)) {
        do { e++; } while (e < n && obj_ws(b[e]));
    } else if (c == '%') {
        do { e++; } while (e < n && b[e] != '\r' && b[e] != '\n');
    } else if (obj_delim(c)) {
        e++;
    } else {
        do { e++; } while (e < n && !obj_ws(b[e]) && !obj_delim(b[e]));
    }
    return e;
}

static Py_ssize_t obj_gap(const unsigned char *b, Py_ssize_t p, Py_ssize_t n)
{
    if (p < 0 || p > n) return n;
    while (p < n) {
        if (obj_ws(b[p])) p++;
        else if (b[p] == '%') {
            do { p++; } while (p < n && b[p] != '\r' && b[p] != '\n');
        } else break;
    }
    return p;
}

static int obj_may_be_ref(const unsigned char *b, Py_ssize_t p, Py_ssize_t n)
{
    Py_ssize_t first = obj_gap(b, p, n), e, second;
    if (first == p || first >= n || b[first] < '0' || b[first] > '9') return 0;
    e = first;
    while (e < n && !obj_ws(b[e]) && !obj_delim(b[e])) {
        if (b[e] < '0' || b[e] > '9') return 0;
        e++;
    }
    second = obj_gap(b, e, n);
    return second > e && second < n && b[second] == 'R' &&
        (second == n - 1 || obj_ws(b[second + 1]) || obj_delim(b[second + 1]));
}

/* Exact copy of _cscan's numeric conversion, with a private symbol prefix. */
static PyObject *obj_number(const unsigned char *b, Py_ssize_t n, int *real, int *negative)
{
    Py_ssize_t i = 0, digits = 0;
    int sign = 1, dots = 0, plain = 1;
    long long integer = 0;
    PyObject *token, *value;
    *real = memchr(b, '.', (size_t)n) != NULL;
    if (n > 0 && (b[0] == '+' || b[0] == '-')) {
        sign = b[0] == '-' ? -1 : 1;
        i++;
    }
    for (; i < n; i++) {
        if (b[i] >= '0' && b[i] <= '9') {
            digits++;
            if (digits <= 18 && !*real) integer = integer * 10 + b[i] - '0';
        } else if (b[i] == '.') dots++;
        else { plain = 0; break; }
    }
    if (plain && digits > 0 && dots == 0 && digits <= 18) {
        *negative = sign < 0 && integer != 0;
        return PyLong_FromLongLong(sign * integer);
    }
    if (plain && digits > 0 && dots == 1 && n <= 64) {
        char text[65], *end;
        double value_real;
        memcpy(text, b, (size_t)n);
        text[n] = '\0';
        value_real = PyOS_string_to_double(text, &end, NULL);
        if (PyErr_Occurred()) return NULL;
        if (end == text + n) return PyFloat_FromDouble(value_real);
    }
    token = PyBytes_FromStringAndSize((const char *)b, n);
    if (token == NULL) return NULL;
    value = PyObject_CallFunctionObjArgs(
        *real ? (PyObject *)&PyFloat_Type : (PyObject *)&PyLong_Type, token, NULL);
    Py_DECREF(token);
    if (value != NULL && !*real) {
        PyObject *zero = PyLong_FromLong(0);
        if (zero == NULL) { Py_DECREF(value); return NULL; }
        *negative = PyObject_RichCompareBool(value, zero, Py_LT);
        Py_DECREF(zero);
        if (*negative < 0) { Py_DECREF(value); return NULL; }
    }
    return value;
}

static int obj_hex_digit(unsigned char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Pure byte loops also exercised by the standalone sanitizer harness.
 * Return 1 for a proven complete spelling, 0 to invoke the original lexer.
 * The caller reserves n-start bytes, which bounds all writes. */
static int obj_literal_bytes(const unsigned char *b, Py_ssize_t start, Py_ssize_t n,
                             unsigned char *out, Py_ssize_t *used, Py_ssize_t *end)
{
    Py_ssize_t p = start + 1, k = 0;
    while (p < n) {
        unsigned char c = b[p++];
        if (c == ')') { *used = k; *end = p; return 1; }
        if (c == '(') return 0; /* Nested parentheses stay with PDFLexer. */
        if (c == '\\') {
            unsigned int octal;
            int j;
            if (p >= n) return 0;
            c = b[p++];
            switch (c) {
                case 'n': c = '\n'; break;
                case 'r': c = '\r'; break;
                case 't': c = '\t'; break;
                case 'b': c = '\b'; break;
                case 'f': c = '\f'; break;
                case '(': case ')': case '\\': break;
                case '\r':
                    if (p < n && b[p] == '\n') p++;
                    continue;
                case '\n': continue;
                default:
                    if (c < '0' || c > '7') return 0;
                    octal = c - '0';
                    for (j = 0; j < 2 && p < n && b[p] >= '0' && b[p] <= '7'; j++)
                        octal = octal * 8 + b[p++] - '0';
                    c = (unsigned char)(octal & 255);
            }
        }
        if (out != NULL) out[k] = c;
        k++;
    }
    return 0;
}

static int obj_hex_bytes(const unsigned char *b, Py_ssize_t start, Py_ssize_t n,
                         unsigned char *out, Py_ssize_t *used, Py_ssize_t *end)
{
    Py_ssize_t p = start + 1, k = 0;
    int high = -1;
    if (p < n && b[p] == '<') return 0;
    while (p < n) {
        unsigned char c = b[p++];
        int digit;
        if (c == '>') {
            if (high >= 0) {
                if (out != NULL) out[k] = (unsigned char)(high << 4);
                k++;
            }
            *used = k; *end = p; return 1;
        }
        if (obj_ws(c)) continue;
        digit = obj_hex_digit(c);
        if (digit < 0) return 0;
        if (high < 0) high = digit;
        else {
            if (out != NULL) out[k] = (unsigned char)((high << 4) | digit);
            k++;
            high = -1;
        }
    }
    return 0;
}

static int obj_name_bytes(const unsigned char *b, Py_ssize_t start, Py_ssize_t n,
                          unsigned char *out, Py_ssize_t *used, Py_ssize_t *end)
{
    Py_ssize_t p = start + 1, k = 0, stop = p;
    while (stop < n && !obj_ws(b[stop]) && !obj_delim(b[stop])) stop++;
    while (p < stop) {
        unsigned char c = b[p];
        if (c == '#' && stop - p > 2) {
            int a = obj_hex_digit(b[p + 1]), d = obj_hex_digit(b[p + 2]);
            /* Python int(two bytes, 16) accepts signs and underscores in a
             * few spellings. Let Python handle every non-hex pair. */
            if (a < 0 || d < 0) return 0;
            if (out != NULL) out[k] = (unsigned char)((a << 4) | d);
            k++;
            p += 3;
        } else {
            if (out != NULL) out[k] = c;
            k++; p++;
        }
    }
    *used = k; *end = stop; return 1;
}

/* One simple structured object, with no array recursion. */
static int obj_simple(ObjScanner *s, Py_ssize_t start, PyObject **value, Py_ssize_t *end)
{
    unsigned char *out;
    unsigned char c = s->buf[start];
    Py_ssize_t used = 0;
    int good;
    *value = NULL;
    if (c != '(' && c != '<' && c != '/') return 0;
    if (c == '(') good = obj_literal_bytes(s->buf, start, s->size, NULL, &used, end);
    else if (c == '<') good = obj_hex_bytes(s->buf, start, s->size, NULL, &used, end);
    else good = obj_name_bytes(s->buf, start, s->size, NULL, &used, end);
    if (!good) return 0;
    out = PyMem_Malloc((size_t)(used > 0 ? used : 1));
    if (out == NULL) { PyErr_NoMemory(); return -1; }
    if (c == '(') obj_literal_bytes(s->buf, start, s->size, out, &used, end);
    else if (c == '<') obj_hex_bytes(s->buf, start, s->size, out, &used, end);
    else obj_name_bytes(s->buf, start, s->size, out, &used, end);
    if (good && c == '/') {
        PyObject *text = PyUnicode_DecodeUTF8((const char *)out, used, "replace");
        if (text != NULL) {
            *value = PyObject_CallFunctionObjArgs(PDFNameType, text, NULL);
            Py_DECREF(text);
        }
    } else if (good) *value = PyBytes_FromStringAndSize((const char *)out, used);
    PyMem_Free(out);
    return good ? (*value == NULL ? -1 : 1) : 0;
}

static int obj_flat_array(ObjScanner *s, Py_ssize_t start, PyObject **value, Py_ssize_t *end)
{
    Py_ssize_t p = start + 1, count = 0;
    PyObject *items = PyList_New(0), *item = NULL;
    if (items == NULL) return -1;
    while (1) {
        unsigned char c;
        Py_ssize_t e;
        int simple;
        p = obj_gap(s->buf, p, s->size);
        if (p >= s->size) break;
        c = s->buf[p];
        if (c == ']') { *end = p + 1; *value = items; return 1; }
        if (count >= 100000) break;
        e = obj_token_end(s->buf, p, s->size);
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '"' || c == '\'') {
            if (e - p == 4 && memcmp(s->buf + p, "true", 4) == 0) item = Py_True;
            else if (e - p == 5 && memcmp(s->buf + p, "false", 5) == 0) item = Py_False;
            else if (e - p == 4 && memcmp(s->buf + p, "null", 4) == 0) item = Py_None;
            else { p = e; continue; }
            Py_INCREF(item);
        } else if ((c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.') {
            int real = 0, negative = 0;
            item = obj_number(s->buf + p, e - p, &real, &negative);
            if (item == NULL) {
                if (!PyErr_ExceptionMatches(PyExc_ValueError)) goto error;
                PyErr_Clear();
                break;
            }
            /* PDFLexer immediately returns float(token), before its
             * reference lookahead. Only nonnegative integers may be refs;
             * [1.0 0 R] remains [1.0, 0] because R is an array operator. */
            if (!real && !negative && obj_may_be_ref(s->buf, e, s->size)) {
                Py_CLEAR(item); break;
            }
        } else {
            simple = obj_simple(s, p, &item, &e);
            if (simple < 0) goto error;
            if (!simple) break;
        }
        if (PyList_Append(items, item) < 0) goto error;
        Py_CLEAR(item);
        count++;
        p = e;
    }
    Py_DECREF(items);
    return 0;
error:
    Py_XDECREF(item);
    Py_DECREF(items);
    return -1;
}

static int objscan_clear(ObjScanner *s)
{
    s->buf = NULL;
    s->size = s->pos = s->cursor = 0;
    Py_CLEAR(s->data);
    Py_CLEAR(s->lexer);
    Py_CLEAR(s->parse_object);
    return 0;
}

static int objscan_traverse(ObjScanner *s, visitproc visit, void *arg)
{
    Py_VISIT(s->data);
    Py_VISIT(s->lexer);
    Py_VISIT(s->parse_object);
    return 0;
}

static int objscan_init(ObjScanner *s, PyObject *data)
{
    PyObject *lexer, *parse;
    char *buf;
    Py_ssize_t size;
    if (!PyBytes_Check(data)) {
        PyErr_SetString(PyExc_TypeError, "data must be bytes"); return -1;
    }
    if (PyBytes_AsStringAndSize(data, &buf, &size) < 0) return -1;
    lexer = PyObject_CallFunctionObjArgs(PDFLexerType, data, NULL);
    if (lexer == NULL) return -1;
    if (PyObject_SetAttrString(lexer, "skip_array_operators", Py_True) < 0) {
        Py_DECREF(lexer); return -1;
    }
    parse = PyObject_GetAttrString(lexer, "parse_object");
    if (parse == NULL) { Py_DECREF(lexer); return -1; }
    objscan_clear(s);
    Py_INCREF(data);
    s->data = data; s->lexer = lexer; s->parse_object = parse;
    s->buf = (const unsigned char *)buf;
    s->size = size;
    return 0;
}

/* 1 operand, 2 operator, 0 EOF, -1 exception; *value is a new reference.
 * Regex-cursor behavior is identical to _cscan, including position rewinds. */
static int scan_next(ObjScanner *s, PyObject **value)
{
    PyObject *backing;
    int event = -1;
    *value = NULL;
    if (s->data == NULL) {
        PyErr_SetString(PyExc_TypeError, "Scanner is not initialized"); return -1;
    }
    backing = s->data;
    Py_INCREF(backing);
    while (s->cursor < s->size) {
        Py_ssize_t start = s->cursor, end = obj_token_end(s->buf, start, s->size);
        unsigned char c;
        s->cursor = end;
        if (start < s->pos) {
            if (s->pos < end) s->cursor = s->pos;
            continue;
        }
        c = s->buf[start];
        s->pos = end;
        if (obj_ws(c) || c == '%') continue;
        if (c == '(' || c == '<' || c == '/' || c == '[' ||
            (c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.') {
            if (c == '(' || c == '<' || c == '/' || c == '[') {
                int fast = c == '[' ? obj_flat_array(s, start, value, &end)
                                      : obj_simple(s, start, value, &end);
                if (fast < 0) goto done;
                if (fast) { s->pos = end; event = 1; goto done; }
            } else {
                int real = 0, negative = 0;
                *value = obj_number(s->buf + start, end - start, &real, &negative);
                if (*value == NULL) {
                    if (!PyErr_ExceptionMatches(PyExc_ValueError)) goto done;
                    PyErr_Clear();
                } else if (negative || real || !obj_may_be_ref(s->buf, end, s->size)) {
                    event = 1; goto done;
                } else Py_CLEAR(*value);
            }
            {
                PyObject *position = PyLong_FromSsize_t(start);
                Py_ssize_t lexer_pos;
                if (position == NULL) goto done;
                if (PyObject_SetAttrString(s->lexer, "pos", position) < 0) {
                    Py_DECREF(position); goto done;
                }
                Py_DECREF(position);
                *value = PyObject_CallObject(s->parse_object, NULL);
                if (*value == NULL) {
                    if (!PyErr_ExceptionMatches(PDFSyntaxErrorType)) goto done;
                    PyErr_Clear();
                    position = PyObject_GetAttrString(s->lexer, "pos");
                    if (position == NULL) goto done;
                    lexer_pos = PyLong_AsSsize_t(position);
                    Py_DECREF(position);
                    if (lexer_pos == -1 && PyErr_Occurred()) goto done;
                    if (lexer_pos == PY_SSIZE_T_MAX) {
                        PyErr_SetString(PyExc_OverflowError, "lexer position overflow"); goto done;
                    }
                    s->pos = lexer_pos + 1;
                    continue;
                }
                position = PyObject_GetAttrString(s->lexer, "pos");
                if (position == NULL) { Py_CLEAR(*value); goto done; }
                lexer_pos = PyLong_AsSsize_t(position);
                Py_DECREF(position);
                if (lexer_pos == -1 && PyErr_Occurred()) { Py_CLEAR(*value); goto done; }
                s->pos = lexer_pos;
                event = 1; goto done;
            }
        }
        if (obj_delim(c)) continue;
        *value = PyBytes_FromStringAndSize((const char *)s->buf + start, end - start);
        if (*value != NULL) event = 2;
        goto done;
    }
    event = 0;
done:
    Py_DECREF(backing);
    return event;
}

#endif
