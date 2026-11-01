/* Handwritten mirror of cmap.py's permissive regex grammar, not a PDF lexer.
 * Work is private until success. Large integer spellings replay in Python. */
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

typedef struct { PyObject *bailout; } State;
typedef struct { const char *p; Py_ssize_t n; int bracket; uint64_t v; } Token;
static PyObject *bail(PyObject *self) {
    PyErr_SetString(((State *)PyModule_GetState(self))->bailout, "replay font preparation in Python");
    return NULL;
}
static int hx(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
/* Equivalent to <([0-9A-Fa-f]+)> | [ | ]. No comment stripping here. */
static int next(const char *s, Py_ssize_t n, Py_ssize_t *pos, Token *t, int brackets) {
    while (*pos < n) {
        Py_ssize_t at = (*pos)++, end;
        if (brackets && (s[at] == '[' || s[at] == ']')) {
            t->p = s + at; t->n = 1; t->bracket = s[at]; t->v = 0; return 1;
        }
        if (s[at] != '<') continue;
        end = at + 1;
        while (end < n && hx((unsigned char)s[end]) >= 0) end++;
        if (end == at + 1 || end == n || s[end] != '>') { *pos = end; continue; }
        t->p = s + at + 1; t->n = end - at - 1; t->bracket = 0; t->v = 0;
        *pos = end + 1;
        if (t->n > 15) return -1;
        for (Py_ssize_t i = 0; i < t->n; i++) t->v = (t->v << 4) | hx((unsigned char)t->p[i]);
        return 1;
    }
    return 0;
}
static PyObject *hextext(Token t) {
    char raw[8]; Py_ssize_t size = (t.n + 1) / 2; int order = 1;
    for (Py_ssize_t i = 0; i < size; i++) {
        int a = hx((unsigned char)t.p[i * 2]);
        int b = i * 2 + 1 < t.n ? hx((unsigned char)t.p[i * 2 + 1]) : 0;
        raw[i] = (char)(a * 16 + b);
    }
    return PyUnicode_DecodeUTF16(raw, size, "replace", &order);
}
static PyObject *inttext(uint64_t value, Py_ssize_t digits) {
    char raw[8]; int order = 1;
    Py_ssize_t width = digits < 4 ? 4 : digits;
    width = ((width + 3) / 4) * 2;
    if (width < 8 && value >> (width * 8)) return PyUnicode_FromString("");
    for (Py_ssize_t i = width; i-- > 0;) { raw[i] = (char)(value & 255); value >>= 8; }
    return PyUnicode_DecodeUTF16(raw, width, "replace", &order);
}
static int addlength(PyObject *lengths, Py_ssize_t digits) {
    PyObject *v = PyLong_FromSsize_t(digits < 2 ? 1 : digits / 2);
    int rc;
    if (!v) return -1;
    rc = PySet_Add(lengths, v); Py_DECREF(v); return rc;
}
static int put(PyObject *map, Py_ssize_t digits, uint64_t code, PyObject *text) {
    PyObject *key; int rc;
    if (!text) return -1;
    key = Py_BuildValue("(nK)", digits < 2 ? (Py_ssize_t)1 : digits / 2, (unsigned long long)code);
    if (!key) { Py_DECREF(text); return -1; }
    rc = PyDict_SetItem(map, key, text); Py_DECREF(key); Py_DECREF(text); return rc;
}
static int full(PyObject *map, int *truncated) {
    if (PyDict_Size(map) < 100000) return 0;
    *truncated = 1; return 1;
}
static int unicode_block(PyObject *self, int kind, const char *s, Py_ssize_t n,
                         PyObject *map, PyObject *lengths, int *truncated) {
    Token tokens[3], t; Py_ssize_t pos = 0; int count = 0, rc;
    /* Validate the whole block first, including ignored tails. This preserves
     * transactional Bailout for long hex spellings without retaining tokens. */
    while ((rc = next(s, n, &pos, &t, kind == 2)) > 0) {}
    if (rc < 0) { bail(self); return -1; }
    pos = 0;
    if (kind == 0) {
        while (next(s, n, &pos, &t, 0) > 0)
            if (addlength(lengths, t.n) < 0) return -1;
        return 0;
    }
    if (kind == 1) {
        while (next(s, n, &pos, &tokens[0], 0) > 0 &&
               next(s, n, &pos, &tokens[1], 0) > 0) {
            if (full(map, truncated)) break;
            if (addlength(lengths, tokens[0].n) < 0 ||
                put(map, tokens[0].n, tokens[0].v, hextext(tokens[1])) < 0) return -1;
        }
        return 0;
    }
    for (;;) {
        /* A sliding three-token window mirrors i += 1 recovery. Array
         * destinations are consumed directly, so memory is input-independent. */
        while (count < 3 && next(s, n, &pos, &tokens[count], 1) > 0) count++;
        if (count < 3) break;
        Token lo = tokens[0], hi = tokens[1], dst = tokens[2];
        if (lo.bracket || hi.bracket) {
            tokens[0] = tokens[1]; tokens[1] = tokens[2]; count = 2; continue;
        }
        count = 0;
        if (hi.v < lo.v || hi.v - lo.v >= 65536 || dst.bracket == ']') continue;
        if (addlength(lengths, lo.n) < 0) return -1;
        if (dst.bracket == '[') {
            uint64_t code = lo.v;
            while (next(s, n, &pos, &t, 1) > 0 && t.bracket != ']') {
                if (code <= hi.v && !full(map, truncated)) {
                    /* A nested '[' raises ValueError; caller skips rest of block. */
                    if (t.bracket) return 0;
                    if (put(map, lo.n, code, hextext(t)) < 0) return -1;
                }
                code++;
            }
        } else {
            uint64_t last = dst.v + hi.v - lo.v;
            int scalar = dst.n <= 4 && (last < 0xd800 || (dst.v >= 0xe000 && last <= 0xffff));
            for (uint64_t k = 0; k <= hi.v - lo.v; k++) {
                PyObject *text;
                if (full(map, truncated)) break;
                text = scalar ? PyUnicode_FromOrdinal((int)(dst.v + k)) : inttext(dst.v + k, dst.n);
                if (put(map, lo.n, lo.v + k, text) < 0) return -1;
            }
        }
    }
    return 0;
}

static const char *kinds[] = {"codespacerange", "bfchar", "bfrange", "cidrange", "cidchar", "notdefrange", "notdefchar"};
/* Regex (begin|end)(kind...) has no word boundaries, including in comments. */
static int block_token(const char *s, Py_ssize_t n, Py_ssize_t *p, int encoding, int *begin, int *kind) {
    for (; *p < n; (*p)++) {
        Py_ssize_t size = 0;
        if (n - *p >= 5 && !memcmp(s + *p, "begin", 5)) { *begin = 1; size = 5; }
        else if (n - *p >= 3 && !memcmp(s + *p, "end", 3)) { *begin = 0; size = 3; }
        if (!size) continue;
        for (int k = 0; k < 7; k++) {
            Py_ssize_t len = (Py_ssize_t)strlen(kinds[k]);
            if ((encoding && (k == 1 || k == 2)) || (!encoding && k > 2)) continue;
            if (n - *p - size >= len && !memcmp(s + *p + size, kinds[k], (size_t)len)) {
                *kind = k; *p += size + len; return 1;
            }
        }
    }
    return 0;
}
static PyObject *tounicode(PyObject *self, PyObject *data) {
    const char *s; Py_ssize_t n, p, start; int active, begin = 0, kind = 0, truncated = 0;
    PyObject *map = NULL, *lengths = NULL, *result = NULL;
    if (!PyBytes_CheckExact(data)) return bail(self);
    n = PyBytes_Size(data); s = PyBytes_AsString(data);
    if (n > 16 * 1024 * 1024) return bail(self);
    map = PyDict_New(); lengths = PySet_New(NULL);
    if (!map || !lengths) goto done;
    /* Three bounded passes preserve kind ordering without retaining block copies. */
    for (int wanted = 0; wanted < 3; wanted++) {
        p = 0; start = 0; active = -1;
        while (p < n) {
            if (!block_token(s, n, &p, 0, &begin, &kind)) break;
            if (begin) { active = kind; start = p; }
            else if (active == kind) {
                Py_ssize_t end = p - 3 - (Py_ssize_t)strlen(kinds[kind]);
                if (kind == wanted && unicode_block(self, kind, s + start, end - start, map, lengths, &truncated) < 0) goto done;
                active = -1;
            }
        }
    }
    if (!PySet_Size(lengths) && addlength(lengths, 2) < 0) goto done;
    result = Py_BuildValue("OOO", map, lengths, truncated ? Py_True : Py_False);
done:
    Py_XDECREF(map); Py_XDECREF(lengths); return result;
}
static int white(unsigned char c) { return c == ' ' || (c >= 9 && c <= 13); }
static int enc_hex(const char *s, Py_ssize_t n, Py_ssize_t *p, Token *t) {
    Py_ssize_t at = *p, end = at + 1;
    if (at >= n || s[at] != '<') return 0;
    while (end < n && hx((unsigned char)s[end]) >= 0 && end - at <= 8) end++;
    if (end >= n || s[end] != '>' || (end - at - 1) % 2 || end == at + 1) return 0;
    t->n = end - at - 1; t->v = 0;
    for (Py_ssize_t i = at + 1; i < end; i++) t->v = (t->v << 4) | hx((unsigned char)s[i]);
    *p = end + 1; return 1;
}
static int encoding_block(int kind, const char *s, Py_ssize_t n, PyObject *spaces,
                          PyObject *ranges, PyObject *notdef, long *count, int *truncated) {
    Py_ssize_t p = 0;
    while (p < n) {
        Py_ssize_t at = p++, q = at; Token lo, hi; unsigned long cid = 0; int ndigits = 0;
        PyObject *row, *target;
        if (!enc_hex(s, n, &q, &lo)) continue;
        while (q < n && white((unsigned char)s[q])) q++;
        if (kind == 4 || kind == 6) hi = lo;
        else {
            if (!enc_hex(s, n, &q, &hi)) continue;
            while (q < n && white((unsigned char)s[q])) q++;
        }
        if (kind != 0) {
            while (q < n && s[q] >= '0' && s[q] <= '9' && ndigits < 6) {
                cid = cid * 10 + s[q++] - '0'; ndigits++;
            }
            if (!ndigits || ndigits > 5) continue;
        }
        /* regex finditer consumes even invalid semantic rows */
        p = q;
        if (*count >= 100000) { *truncated = 1; break; }
        if (lo.n != hi.n) continue;
        if (hi.v < lo.v || (kind != 0 && hi.v - lo.v > 0x10ffff) || cid > 65535 ||
            (kind == 3 && cid + hi.v - lo.v > 65535) || (kind == 0 && PyList_Size(spaces) >= 100)) {
            *truncated = 1; continue;
        }
        target = kind == 0 ? spaces : kind >= 5 ? notdef : ranges;
        row = kind == 0 ? Py_BuildValue("(nKK)", lo.n / 2, (unsigned long long)lo.v, (unsigned long long)hi.v) :
                         Py_BuildValue("(nKKk)", lo.n / 2, (unsigned long long)lo.v, (unsigned long long)hi.v, cid);
        if (!row) return -1;
        int rc = PyList_Append(target, row); Py_DECREF(row);
        if (rc < 0) return -1;
        (*count)++;
    }
    return 0;
}
static PyObject *encoding_rows(PyObject *self, PyObject *data) {
    const char *s; Py_ssize_t n, p = 0, start = 0; int active = -1, begin = 0, kind = 0, truncated = 0;
    long count = 0; PyObject *spaces = NULL, *ranges = NULL, *notdef = NULL, *result = NULL;
    if (!PyBytes_CheckExact(data)) return bail(self);
    n = PyBytes_Size(data); s = PyBytes_AsString(data);
    if (n > 4 * 1024 * 1024) return bail(self);
    spaces = PyList_New(0); ranges = PyList_New(0); notdef = PyList_New(0);
    if (!spaces || !ranges || !notdef) goto done;
    while (p < n && block_token(s, n, &p, 1, &begin, &kind)) {
        if (begin) { active = kind; start = p; }
        else if (active == kind) {
            Py_ssize_t end = p - 3 - (Py_ssize_t)strlen(kinds[kind]);
            if (encoding_block(kind, s + start, end - start, spaces, ranges, notdef, &count, &truncated) < 0) goto done;
            active = -1;
            if (truncated && count >= 100000) break;
        }
    }
    result = Py_BuildValue("OOOO", spaces, ranges, notdef, truncated ? Py_True : Py_False);
done:
    Py_XDECREF(spaces); Py_XDECREF(ranges); Py_XDECREF(notdef); return result;
}

/* Only builtin numeric objects enter arithmetic. Subclasses and wide integers
 * bail before publishing, retaining Python's conversion and exception rules. */
static int integer(PyObject *v, long long *out) {
    if (!PyLong_CheckExact(v) && !PyBool_Check(v)) return 0;
    *out = PyLong_AsLongLong(v);
    if (PyErr_Occurred()) { PyErr_Clear(); return -1; }
    if (*out < -1000000000LL || *out > 1000000000LL) return -1;
    return 1;
}
static int number(PyObject *v, double *out) {
    if (!PyFloat_CheckExact(v) && !PyLong_CheckExact(v) && !PyBool_Check(v)) {
        if (PyFloat_Check(v) || PyLong_Check(v)) return -1;
        return 0;
    }
    *out = PyFloat_AsDouble(v);
    if (PyErr_Occurred()) { PyErr_Clear(); return -1; }
    return 1;
}
static int width_put(PyObject *table, long long code, double value) {
    PyObject *key = PyLong_FromLongLong(code), *width = PyFloat_FromDouble(value); int rc;
    if (!key || !width) { Py_XDECREF(key); Py_XDECREF(width); return -1; }
    rc = PyDict_SetItem(table, key, width); Py_DECREF(key); Py_DECREF(width); return rc;
}
static PyObject *simple_widths(PyObject *self, PyObject *args) {
    PyObject *first, *values, *table; long long start; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "OO", &first, &values)) return NULL;
    if (!PyList_CheckExact(values) || integer(first, &start) != 1) return bail(self);
    table = PyDict_New(); if (!table) return NULL;
    n = PyList_Size(values);
    for (Py_ssize_t i = 0; i < n; i++) {
        double value; int rc = number(PyList_GetItem(values, i), &value);
        if (rc < 0) { Py_DECREF(table); return bail(self); }
        if (rc && isfinite(value) && start + i >= 0 && start + i < 256 && width_put(table, start + i, value) < 0) {
            Py_DECREF(table); return NULL;
        }
    }
    return table;
}
static PyObject *cid_widths(PyObject *self, PyObject *args) {
    PyObject *values, *table = NULL, *warnings = NULL, *result = NULL; double def;
    Py_ssize_t n, length, i = 0, budget = 65536;
    if (!PyArg_ParseTuple(args, "Od", &values, &def)) return NULL;
    if (!PyList_CheckExact(values)) return bail(self);
    table = PyDict_New(); warnings = PyList_New(0);
    if (!table || !warnings) goto done;
    if (!isfinite(def)) {
        PyObject *message = PyUnicode_FromString("WARN: PDF CID 기본 폭이 비유한 수 — 표준 기본 폭 사용");
        if (!message) goto done;
        int rc = PyList_Append(warnings, message); Py_DECREF(message);
        if (rc < 0) goto done;
        def = 1000.0;
    }
    length = PyList_Size(values); n = length < 65536 ? length : 65536;
    while (i < n) {
        long long start, end; double value;
        PyObject *item = PyList_GetItem(values, i), *second = i + 1 < n ? PyList_GetItem(values, i + 1) : NULL;
        int rc = integer(item, &start);
        if (rc < 0 || (!rc && PyLong_Check(item))) goto fallback;
        if (!rc) { i++; continue; }
        if (second && PyList_Check(second)) {
            Py_ssize_t size, count;
            if (!PyList_CheckExact(second)) goto fallback;
            size = PyList_Size(second); count = size < budget ? size : budget;
            for (Py_ssize_t j = 0; j < count; j++) {
                if (start + j < 0 || start + j > 65535) continue;
                rc = number(PyList_GetItem(second, j), &value);
                if (rc < 0) goto fallback;
                if (rc && isfinite(value) && width_put(table, start + j, value) < 0) goto done;
            }
            budget -= size; i += 2;
        } else if (i + 2 < n && PyLong_Check(second)) {
            if (integer(second, &end) != 1) goto fallback;
            rc = number(PyList_GetItem(values, i + 2), &value);
            if (rc < 0) goto fallback;
            if (rc && isfinite(value)) {
                if (start >= 0 && start <= end && end <= 65535) {
                    long long stop = end + 1 < start + budget ? end + 1 : start + budget;
                    for (long long code = start; code < stop; code++) if (width_put(table, code, value) < 0) goto done;
                    budget -= (Py_ssize_t)(end - start + 1);
                }
                i += 3;
            } else i++;
        } else i++;
        if (budget <= 0 && i < n) break;
    }
    if (i < length || budget < 0) {
        PyObject *message = PyUnicode_FromString("WARN: PDF CID 폭 배열 처리 한도(65536)를 초과 — 일부만 사용");
        if (!message) goto done;
        int rc = PyList_Append(warnings, message); Py_DECREF(message);
        if (rc < 0) goto done;
    }
    result = Py_BuildValue("OdO", table, def, warnings); goto done;
fallback:
    bail(self);
done:
    Py_XDECREF(table); Py_XDECREF(warnings); return result;
}
static PyObject *differences(PyObject *self, PyObject *args) {
    PyObject *base, *values, *table; long long code = -1; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "OO", &base, &values)) return NULL;
    if (!PyDict_CheckExact(base) || !PyList_CheckExact(values)) return bail(self);
    table = PyDict_Copy(base); if (!table) return NULL;
    n = PyList_Size(values); if (n > 4096) n = 4096;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *value = PyList_GetItem(values, i);
        if (PyLong_Check(value) && !PyBool_Check(value)) {
            if (integer(value, &code) != 1) { Py_DECREF(table); return bail(self); }
        } else if (PyUnicode_Check(value)) {
            if (code >= 0 && code < 256) {
                PyObject *key = PyLong_FromLongLong(code);
                if (!key) { Py_DECREF(table); return NULL; }
                int rc = PyDict_SetItem(table, key, value); Py_DECREF(key);
                if (rc < 0) { Py_DECREF(table); return NULL; }
            }
            code++;
        }
    }
    return table;
}

/* Ordered disjoint integer rows are already the sweep-line result. Otherwise
 * keep the original stable event sort/heap algorithm, including odd inputs. */
static PyObject *flatten_ordered(PyObject *self, PyObject *rows) {
    Py_ssize_t n; long long previous = 0;
    if (!PyList_CheckExact(rows)) return bail(self);
    n = PyList_Size(rows);
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *row = PyList_GetItem(rows, i); long long values[3];
        if (!PyTuple_CheckExact(row) || PyTuple_Size(row) != 3) return bail(self);
        for (int j = 0; j < 3; j++) {
            PyObject *value = PyTuple_GetItem(row, j);
            if (!PyLong_CheckExact(value)) return bail(self);
            values[j] = PyLong_AsLongLong(value);
            if (PyErr_Occurred()) { PyErr_Clear(); return bail(self); }
        }
        if (values[0] > values[1] || (i && previous >= values[0])) return bail(self);
        previous = values[1];
    }
    return PyList_GetSlice(rows, 0, n);
}

static PyMethodDef methods[] = {
    {"tounicode", tounicode, METH_O, NULL},
    {"flatten_ordered", flatten_ordered, METH_O, NULL},
    {"simple_widths", simple_widths, METH_VARARGS, NULL},
    {"cid_widths", cid_widths, METH_VARARGS, NULL},
    {"differences", differences, METH_VARARGS, NULL},
    {"encoding_rows", encoding_rows, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static int traverse(PyObject *m, visitproc visit, void *arg) {
    State *s = PyModule_GetState(m); Py_VISIT(s->bailout); return 0;
}
static int clear(PyObject *m) { State *s = PyModule_GetState(m); Py_CLEAR(s->bailout); return 0; }
static void release(void *m) { clear((PyObject *)m); }
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_ccmap", NULL, sizeof(State), methods, NULL, traverse, clear, release
};
PyMODINIT_FUNC PyInit__ccmap(void) {
    PyObject *m = PyModule_Create(&module); State *s;
    if (!m) return NULL;
    s = PyModule_GetState(m);
    s->bailout = PyErr_NewException("dochan.pdf._ccmap.Bailout", NULL, NULL);
    if (!s->bailout) { Py_DECREF(m); return NULL; }
    Py_INCREF(s->bailout);
    if (PyModule_AddObject(m, "Bailout", s->bailout) < 0) { Py_DECREF(s->bailout); Py_DECREF(m); return NULL; }
    return m;
}
