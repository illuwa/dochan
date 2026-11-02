/* Original indented JSON writer. CPython stable ABI, Python 3.9 minimum.
 * Fields live on the C stack: no dict/list mirror of a document is constructed.
 * Unsupported subtrees are recomputed before emitting them, so a one-shot Stream
 * or a non-seekable sink never needs to be replayed after a bailout.
 */
#define Py_LIMITED_API 0x03090000
#include <Python.h>
#include <math.h>
#include <string.h>
#include <stdint.h>

#define CHUNK 65536
#define MAX_FIELDS 18
/* Model roles; 100 + role means a list whose members have that role. */
enum { GENERIC, DOCUMENT, SECTION, ELEMENT, CELL, RUN, PROVENANCE, ASSET, INLINE_EQ };
enum { T_DOCUMENT, T_SECTION, T_PARAGRAPH, T_CELL, T_RUN, T_PROVENANCE,
       T_TABLE, T_IMAGE, T_EQUATION, T_HEADER, T_FOOTNOTE, T_COMMENT, T_ASSET };
static const char *const names[] = {
    "metadata", "assets", "sections", "elements", "type", "text", "runs", "style_id",
    "heading_level", "provenance", "row_count", "col_count", "rows", "caption",
    "caption_text", "caption_side", "side", "row_span", "col_span", "paragraphs",
    "is_merged_away", "merged_away", "row", "col", "bold", "italic", "underline",
    "strikeout", "superscript", "subscript", "font_size_pt", "equation", "latex",
    "script", "script_format", "link", "note_ref", "note_reference_type",
    "note_reference_number", "source_format", "page", "slide", "sheet", "cell",
    "section", "paragraph", "path", "visibility", "hidden", "bin_id", "filename",
    "width", "height", "ocr_text", "alt_text", "number", "author", "id",
    "source_path", "content_type", "count", "items"
};
enum {
    N_metadata, N_assets, N_sections, N_elements, N_type, N_text, N_runs, N_style_id,
    N_heading_level, N_provenance, N_row_count, N_col_count, N_rows, N_caption, N_caption_text,
    N_caption_side, N_side, N_row_span, N_col_span, N_paragraphs, N_is_merged_away,
    N_merged_away, N_row, N_col, N_bold, N_italic, N_underline, N_strikeout, N_superscript,
    N_subscript, N_font_size_pt, N_equation, N_latex, N_script, N_script_format, N_link,
    N_note_ref, N_note_reference_type, N_note_reference_number, N_source_format, N_page,
    N_slide, N_sheet, N_cell, N_section, N_paragraph, N_path, N_visibility, N_hidden, N_bin_id,
    N_filename, N_width, N_height, N_ocr_text, N_alt_text, N_number, N_author, N_id,
    N_source_path, N_content_type, N_count, N_items
};
#define NAME_COUNT (sizeof(names) / sizeof(names[0]))
typedef struct { PyObject *bailout; PyObject *names[NAME_COUNT]; } ModuleState;
typedef struct {
    ModuleState *state;
    PyObject *fp, *chunks, *keys, *pads, *unit, *stream, *types, *fallback, *indent;
    char *buf;
    Py_ssize_t size, capacity;
    PyObject **active;
    int nactive, active_capacity, compact;
} Writer;
typedef struct { int key; PyObject *value; int role; } Field;
typedef struct { Field fields[MAX_FIELDS]; int count; } Record;

static int walk(Writer *, PyObject *, int, int);
static int exact(PyObject *v, PyTypeObject *t) { return Py_TYPE(v) == t; }
static int model(Writer *w, PyObject *v, int index) {
    return w->types != Py_None && (PyObject *)Py_TYPE(v) == PyTuple_GetItem(w->types, index);
}
static PyObject *name(Writer *w, int index) { return w->state->names[index]; }
static PyObject *attr(Writer *w, PyObject *obj, int s) {
    PyObject *key = name(w, s);
    return key ? PyObject_GetAttr(obj, key) : NULL;
}
static int flush(Writer *w) {
    PyObject *s, *result;
    int ok;
    if (!w->size) return 0;
    s = PyUnicode_DecodeUTF8(w->buf, w->size, "surrogatepass");
    if (!s) return -1;
    if (w->fp == Py_None) ok = PyList_Append(w->chunks, s);
    else {
        result = PyObject_CallMethod(w->fp, "write", "O", s);
        ok = result ? 0 : -1;
        Py_XDECREF(result);
    }
    Py_DECREF(s);
    if (ok == 0) w->size = 0;
    return ok;
}
static int put(Writer *w, const char *s, Py_ssize_t n) {
    Py_ssize_t capacity;
    char *buf;
    if (n > PY_SSIZE_T_MAX - w->size) { PyErr_NoMemory(); return -1; }
    if (w->size + n > w->capacity) {
        capacity = w->size + n;
        if (capacity < CHUNK) capacity = CHUNK;
        else if (capacity <= PY_SSIZE_T_MAX / 2) capacity *= 2;
        buf = PyMem_Realloc(w->buf, (size_t)capacity);
        if (!buf) { PyErr_NoMemory(); return -1; }
        w->buf = buf; w->capacity = capacity;
    }
    memcpy(w->buf + w->size, s, (size_t)n); w->size += n;
    /* All put calls end on a UTF-8 boundary, including surrogatepass strings. */
    return w->size >= CHUNK ? flush(w) : 0;
}
static int literal(Writer *w, const char *s) { return put(w, s, (Py_ssize_t)strlen(s)); }
static int unicode_raw(Writer *w, PyObject *s) {
    PyObject *b = PyUnicode_AsEncodedString(s, "utf-8", "surrogatepass");
    int result;
    if (!b) return -1;
    result = put(w, PyBytes_AsString(b), PyBytes_Size(b)); Py_DECREF(b); return result;
}
static int quote(Writer *w, PyObject *s) {
    static const char hex[] = "0123456789abcdef";
    PyObject *b = PyUnicode_AsEncodedString(s, "utf-8", "surrogatepass");
    const char *p;
    Py_ssize_t i, start = 0, n;
    int result = -1;
    if (!b) return -1;
    p = PyBytes_AsString(b); n = PyBytes_Size(b);
    if (literal(w, "\"") < 0) goto done;
    for (i = 0; i < n; i++) {
        unsigned char c = (unsigned char)p[i];
        const char *escape = NULL;
        char control[6] = {'\\', 'u', '0', '0', '0', '0'};
        if (c == '"') escape = "\\\"";
        else if (c == '\\') escape = "\\\\";
        else if (c == '\b') escape = "\\b";
        else if (c == '\f') escape = "\\f";
        else if (c == '\n') escape = "\\n";
        else if (c == '\r') escape = "\\r";
        else if (c == '\t') escape = "\\t";
        else if (c < 32) { control[4] = hex[c >> 4]; control[5] = hex[c & 15]; }
        else continue;
        if (put(w, p + start, i - start) < 0) goto done;
        if (escape ? literal(w, escape) < 0 : put(w, control, 6) < 0) goto done;
        start = i + 1;
    }
    if (put(w, p + start, n - start) < 0 || literal(w, "\"") < 0) goto done;
    result = 0;
done:
    Py_DECREF(b); return result;
}
static int pad(Writer *w, int depth) {
    PyObject *next, *repeated, *factor;
    if (w->compact) return 0;
    while (PyList_Size(w->pads) <= depth) {
        factor = PyLong_FromSsize_t(PyList_Size(w->pads));
        if (!factor) return -1;
        repeated = PyNumber_Multiply(w->unit, factor); Py_DECREF(factor);
        if (!repeated) return -1;
        next = PyBytes_FromStringAndSize(NULL, 1 + PyBytes_Size(repeated));
        if (next) {
            char *p = PyBytes_AsString(next); p[0] = '\n';
            memcpy(p + 1, PyBytes_AsString(repeated), (size_t)PyBytes_Size(repeated));
        }
        Py_DECREF(repeated);
        if (!next) return -1;
        if (PyList_Append(w->pads, next) < 0) { Py_DECREF(next); return -1; }
        Py_DECREF(next);
    }
    next = PyList_GetItem(w->pads, depth);
    return put(w, PyBytes_AsString(next), PyBytes_Size(next));
}
static int separator(Writer *w, int *count, int depth) {
    if ((*count)++ && literal(w, w->compact ? ", " : ",") < 0) return -1;
    return pad(w, depth + 1);
}
static int key(Writer *w, PyObject *s) {
    PyObject *cached = PyDict_GetItemWithError(w->keys, s);
    Writer temp;
    PyObject *b;
    int result;
    if (cached) return put(w, PyBytes_AsString(cached), PyBytes_Size(cached));
    if (PyErr_Occurred()) return -1;
    /* Key escaping uses the same implementation but never flushes a short key. */
    memset(&temp, 0, sizeof(temp));
    temp.fp = Py_None; temp.chunks = PyList_New(0);
    if (!temp.chunks) return -1;
    result = quote(&temp, s);
    if (result == 0) result = literal(&temp, ": ");
    if (result == 0 && PyList_Size(temp.chunks) == 0) {
        b = PyBytes_FromStringAndSize(temp.buf, temp.size);
        if (!b) result = -1;
        else {
            result = PyDict_SetItem(w->keys, s, b);
            if (result == 0) result = put(w, PyBytes_AsString(b), PyBytes_Size(b));
            Py_DECREF(b);
        }
    } else if (result == 0) {
        /* Extremely long keys: preserve bounded chunks without caching. */
        result = quote(w, s);
        if (result == 0) result = literal(w, ": ");
    }
    PyMem_Free(temp.buf); Py_DECREF(temp.chunks); return result;
}
static int field_key(Writer *w, int s) { return key(w, name(w, s)); }
static int fallback(Writer *w, PyObject *v, int depth, int role) {
    PyObject *d, *r, *text;
    int result;
    if (w->fallback == Py_None) {
        PyErr_SetString(w->state->bailout, "unsupported JSON subtree"); return -1;
    }
    d = PyLong_FromLong(depth); r = PyLong_FromLong(role);
    if (!d || !r) { Py_XDECREF(d); Py_XDECREF(r); return -1; }
    text = PyObject_CallFunctionObjArgs(w->fallback, v, r, w->indent, d, NULL);
    Py_DECREF(d); Py_DECREF(r);
    if (!text) return -1;
    if (exact(text, &PyTuple_Type) && PyTuple_Size(text) == 1)
        result = walk(w, PyTuple_GetItem(text, 0), depth, 0);
    else result = unicode_raw(w, text);
    Py_DECREF(text); return result;
}
static void clear_record(Record *r) {
    int i; for (i = 0; i < r->count; i++) Py_DECREF(r->fields[i].value);
    r->count = 0;
}
static int add(Record *r, int key_name, PyObject *v, int role) {
    Field *f;
    if (!v) return -1;
    if (r->count >= MAX_FIELDS) { Py_DECREF(v); PyErr_SetString(PyExc_SystemError, "JSON field overflow"); return -1; }
    f = &r->fields[r->count++]; f->key = key_name; f->value = v; f->role = role; return 0;
}
static int add_attr(Writer *w, Record *r, PyObject *v, int s, int role) {
    return add(r, s, attr(w, v, s), role);
}
static int add_literal(Record *r, int s, const char *v) {
    return add(r, s, PyUnicode_FromString(v), GENERIC);
}
/* 0: always, 1: truthy, 2: not None, 3: not None or empty string. */
static int optional(Writer *w, Record *r, PyObject *v, int s, int rule, int role) {
    PyObject *x = attr(w, v, s);
    int include = 1;
    if (!x) return -1;
    if (rule == 1) include = PyObject_IsTrue(x);
    else if (rule == 2) include = x != Py_None;
    else if (rule == 3 && x != Py_None && !exact(x, &PyUnicode_Type) &&
             !exact(x, &PyLong_Type) && !exact(x, &PyFloat_Type) && !PyBool_Check(x)) {
        Py_DECREF(x); PyErr_SetString(w->state->bailout, "nonstandard provenance field"); return -1;
    }
    else if (rule == 3) include = x != Py_None && !(exact(x, &PyUnicode_Type) && PyUnicode_GetLength(x) == 0);
    if (include < 0) { Py_DECREF(x); return -1; }
    if (!include) { Py_DECREF(x); return 0; }
    return add(r, s, x, role);
}
static int provenance(Writer *w, Record *r, PyObject *v) {
    static const int keys[] = {N_source_format, N_page, N_slide, N_sheet, N_cell, N_section, N_paragraph, N_path, N_visibility, N_hidden};
    int i;
    for (i = 0; i < 10; i++) if (optional(w, r, v, keys[i], i < 8 ? 3 : 2, 0) < 0) return -1;
    return 0;
}
static int add_provenance(Writer *w, Record *r, PyObject *v) {
    PyObject *p = attr(w, v, N_provenance);
    Record probe = {{{0}}, 0};
    int include;
    if (!p) return -1;
    if (p == Py_None) { Py_DECREF(p); return 0; }
    if (!model(w, p, T_PROVENANCE)) {
        Py_DECREF(p); PyErr_SetString(w->state->bailout, "nonstandard provenance"); return -1;
    }
    /* Usually visibility=0 and hidden=False make provenance nonempty. Avoid
     * reading all ten fields twice in that overwhelmingly common case. */
    {
        PyObject *x = attr(w, p, N_visibility);
        if (!x) { Py_DECREF(p); return -1; }
        include = x != Py_None; Py_DECREF(x);
    }
    if (!include) {
        if (provenance(w, &probe, p) < 0) { clear_record(&probe); Py_DECREF(p); return -1; }
        include = probe.count != 0; clear_record(&probe);
    }
    if (!include) { Py_DECREF(p); return 0; }
    return add(r, N_provenance, p, PROVENANCE);
}
static int caption(Writer *w, Record *r, PyObject *v) {
    PyObject *text = attr(w, v, N_caption_text);
    int include;
    if (!text) return -1;
    include = PyObject_IsTrue(text); Py_DECREF(text);
    if (include < 0) return -1;
    if (!include) return 0;
    /* A distinct role writes the three caption fields, without a dict. */
    Py_INCREF(v); return add(r, N_caption, v, 9);
}
#define A(s, role) do { if (add_attr(w, r, v, s, role) < 0) return -1; } while (0)
#define L(s, val) do { if (add_literal(r, s, val) < 0) return -1; } while (0)
#define O(s, rule) do { if (optional(w, r, v, s, rule, 0) < 0) return -1; } while (0)
static int prepare(Writer *w, PyObject *v, int role, Record *r) {
    if (role == DOCUMENT && model(w, v, T_DOCUMENT)) {
        A(N_metadata, 0); A(N_assets, 100 + ASSET); A(N_sections, 100 + SECTION);
    } else if (role == SECTION && model(w, v, T_SECTION)) {
        A(N_elements, 100 + ELEMENT); return add_provenance(w, r, v);
    } else if (role == CELL && model(w, v, T_CELL)) {
        PyObject *merged;
        int yes;
        A(N_text, 0); A(N_row_span, 0); A(N_col_span, 0); A(N_paragraphs, 100 + ELEMENT);
        merged = attr(w, v, N_is_merged_away); if (!merged) return -1;
        yes = PyObject_IsTrue(merged); Py_DECREF(merged); if (yes < 0) return -1;
        if (yes) { Py_INCREF(Py_True); if (add(r, N_merged_away, Py_True, 0) < 0) return -1; }
        O(N_row, 2); O(N_col, 2); return add_provenance(w, r, v);
    } else if (role == RUN && model(w, v, T_RUN)) {
        PyObject *eq, *nt, *nn;
        int note;
        A(N_text, 0); A(N_bold, 0); A(N_italic, 0); A(N_underline, 0); A(N_strikeout, 0);
        A(N_superscript, 0); A(N_subscript, 0); A(N_font_size_pt, 0);
        eq = attr(w, v, N_equation); if (!eq) return -1;
        if (eq == Py_None) Py_DECREF(eq); else if (add(r, N_equation, eq, INLINE_EQ) < 0) return -1;
        O(N_link, 1); O(N_note_ref, 1);
        nt = attr(w, v, N_note_reference_type); if (!nt) return -1;
        nn = attr(w, v, N_note_reference_number); if (!nn) { Py_DECREF(nt); return -1; }
        if (!exact(nt, &PyUnicode_Type)) {
            Py_DECREF(nt); Py_DECREF(nn); PyErr_SetString(w->state->bailout, "unexpected note type"); return -1;
        }
        note = PyUnicode_CompareWithASCIIString(nt, "footnote") == 0 ||
               PyUnicode_CompareWithASCIIString(nt, "endnote") == 0 ||
               PyUnicode_CompareWithASCIIString(nt, "comment") == 0;
        if (note && nn != Py_None) {
            if (add(r, N_note_reference_type, nt, 0) < 0) { Py_DECREF(nn); return -1; }
            if (add(r, N_note_reference_number, nn, 0) < 0) return -1;
        } else { Py_DECREF(nt); Py_DECREF(nn); }
        return add_provenance(w, r, v);
    } else if (role == PROVENANCE && model(w, v, T_PROVENANCE)) return provenance(w, r, v);
    else if (role == ASSET) {
        PyErr_SetString(w->state->bailout, "asset metadata requires deepcopy"); return -1;
    } else if ((role == INLINE_EQ || role == ELEMENT) && model(w, v, T_EQUATION)) {
        if (role == ELEMENT) L(N_type, "equation");
        A(N_latex, 0); A(N_script, 0); A(N_script_format, 0);
    } else if (role == 9 && (model(w, v, T_TABLE) || model(w, v, T_IMAGE))) {
        if (add(r, N_side, attr(w, v, N_caption_side), 0) < 0 ||
            add(r, N_text, attr(w, v, N_caption_text), 0) < 0 ||
            add(r, N_elements, attr(w, v, N_caption), 100 + ELEMENT) < 0) return -1;
    } else if (role == ELEMENT && model(w, v, T_PARAGRAPH)) {
        L(N_type, "paragraph"); A(N_text, 0); A(N_runs, 100 + RUN);
        A(N_style_id, 0); A(N_heading_level, 0); return add_provenance(w, r, v);
    } else if (role == ELEMENT && model(w, v, T_TABLE)) {
        L(N_type, "table"); A(N_row_count, 0); A(N_col_count, 0); A(N_rows, 200 + CELL);
        return caption(w, r, v);
    } else if (role == ELEMENT && model(w, v, T_IMAGE)) {
        L(N_type, "image"); A(N_bin_id, 0); A(N_filename, 0); A(N_width, 0); A(N_height, 0);
        A(N_ocr_text, 0); O(N_alt_text, 1); return caption(w, r, v);
    } else if (role == ELEMENT && (model(w, v, T_HEADER) || model(w, v, T_FOOTNOTE) || model(w, v, T_COMMENT))) {
        A(N_type, 0); A(N_text, 0);
        if (add(r, N_elements, attr(w, v, N_paragraphs), 100 + ELEMENT) < 0) return -1;
        if (!model(w, v, T_HEADER)) O(N_number, 1);
        if (model(w, v, T_COMMENT)) A(N_author, 0);
    } else { PyErr_SetString(w->state->bailout, "nonstandard model"); return -1; }
    return 0;
}
#undef A
#undef L
#undef O
static int record(Writer *w, PyObject *v, int depth, int role) {
    Record r = {{{0}}, 0};
    int i, count = 0, result = -1;
    if (prepare(w, v, role, &r) < 0) {
        clear_record(&r);
        if (PyErr_ExceptionMatches(w->state->bailout) || PyErr_ExceptionMatches(PyExc_AttributeError)) {
            PyErr_Clear(); return fallback(w, v, depth, role);
        }
        return -1;
    }
    if (literal(w, "{") < 0) goto done;
    for (i = 0; i < r.count; i++) {
        Field *f = &r.fields[i];
        if (separator(w, &count, depth) < 0 || field_key(w, f->key) < 0 ||
            walk(w, f->value, depth + 1, f->role) < 0) goto done;
    }
    if (count && pad(w, depth) < 0) goto done;
    result = literal(w, "}");
done:
    clear_record(&r); return result;
}
static int container(Writer *w, PyObject *v, int depth, int role) {
    int result = -1, count = 0;
    if (role && role < 100) return record(w, v, depth, role);
    if (role == 0 && exact(v, &PyDict_Type)) {
        PyObject *k, *item;
        Py_ssize_t pos = 0;
        /* Bail out before writing a dict containing non-string keys. */
        while (PyDict_Next(v, &pos, &k, &item)) if (!exact(k, &PyUnicode_Type)) return fallback(w, v, depth, role);
        if (literal(w, "{") < 0) return -1;
        pos = 0;
        while (PyDict_Next(v, &pos, &k, &item)) {
            Py_ssize_t original_size = PyDict_Size(v);
            int ok;
            Py_INCREF(k); Py_INCREF(item);
            ok = separator(w, &count, depth);
            if (ok == 0) ok = key(w, k);
            if (ok == 0) ok = walk(w, item, depth + 1, 0);
            Py_DECREF(k); Py_DECREF(item);
            if (ok < 0) return -1;
            if (PyDict_Size(v) != original_size) {
                PyErr_SetString(PyExc_RuntimeError, "dictionary changed size during iteration"); return -1;
            }
        }
        if (count && pad(w, depth) < 0) return -1;
        return literal(w, "}");
    }
    if (exact(v, &PyList_Type) || exact(v, &PyTuple_Type) || (PyObject *)Py_TYPE(v) == w->stream) {
        PyObject *it, *item, *items = NULL;
        int child = role >= 100 ? role - 100 : 0;
        if ((PyObject *)Py_TYPE(v) == w->stream) {
            PyObject *length = attr(w, v, N_count);
            int nonempty;
            if (!length) return -1;
            nonempty = PyObject_IsTrue(length); Py_DECREF(length);
            if (nonempty < 0) return -1;
            if (!nonempty) return literal(w, "[]");
            items = attr(w, v, N_items); if (!items) return -1;
        }
        it = PyObject_GetIter(items ? items : v); Py_XDECREF(items);
        if (!it) return -1;
        if (literal(w, "[") < 0) goto list_done;
        while ((item = PyIter_Next(it))) {
            int ok = separator(w, &count, depth);
            if (ok == 0) ok = walk(w, item, depth + 1, child);
            Py_DECREF(item); if (ok < 0) goto list_done;
        }
        if (PyErr_Occurred()) goto list_done;
        if (count && pad(w, depth) < 0) goto list_done;
        result = literal(w, "]");
list_done:
        Py_DECREF(it); return result;
    }
    return fallback(w, v, depth, role);
}
static int walk(Writer *w, PyObject *v, int depth, int role) {
    PyObject *s;
    int i, result;
    if (!role) {
        if (exact(v, &PyUnicode_Type)) return quote(w, v);
        if (v == Py_None) return literal(w, "null");
        if (v == Py_True) return literal(w, "true");
        if (v == Py_False) return literal(w, "false");
        if (exact(v, &PyLong_Type) || exact(v, &PyFloat_Type)) {
            if (exact(v, &PyFloat_Type)) {
                double f = PyFloat_AsDouble(v);
                if (isnan(f)) return literal(w, "NaN");
                if (isinf(f)) return literal(w, f < 0 ? "-Infinity" : "Infinity");
            }
            s = PyObject_Repr(v); if (!s) return -1;
            result = unicode_raw(w, s); Py_DECREF(s); return result;
        }
    }
    if (role == 9) return record(w, v, depth, role);
    for (i = 0; i < w->nactive; i++) if (w->active[i] == v) {
        PyErr_SetString(PyExc_ValueError, "Circular reference detected"); return -1;
    }
    if (w->nactive == w->active_capacity) {
        int capacity = w->active_capacity ? w->active_capacity * 2 : 32;
        PyObject **active = PyMem_Realloc(w->active, (size_t)capacity * sizeof(*active));
        if (!active) { PyErr_NoMemory(); return -1; }
        w->active = active; w->active_capacity = capacity;
    }
    if (Py_EnterRecursiveCall(" while encoding a JSON object")) return -1;
    w->active[w->nactive++] = v;
    result = container(w, v, depth, role);
    w->nactive--; Py_LeaveRecursiveCall(); return result;
}
static PyObject *encode(PyObject *module, PyObject *args) {
    Writer w;
    PyObject *v, *result = NULL, *empty = NULL;
    int role;
    memset(&w, 0, sizeof(w));
    w.state = PyModule_GetState(module);
    if (!PyArg_ParseTuple(args, "OOOOOOi", &v, &w.indent, &w.fp, &w.stream, &w.types, &w.fallback, &role)) return NULL;
    if (w.types != Py_None && (!PyTuple_Check(w.types) || PyTuple_Size(w.types) != 13)) {
        PyErr_SetString(PyExc_TypeError, "expected thirteen model classes"); return NULL;
    }
    w.compact = w.indent == Py_None;
    if (w.compact) w.unit = PyUnicode_FromString("");
    else if (exact(w.indent, &PyUnicode_Type)) { w.unit = w.indent; Py_INCREF(w.unit); }
    else if (exact(w.indent, &PyLong_Type) || PyBool_Check(w.indent)) {
        empty = PyUnicode_FromString(" ");
        if (empty) w.unit = PyNumber_Multiply(empty, w.indent);
        Py_CLEAR(empty);
    } else { PyErr_SetString(w.state->bailout, "nonstandard indent"); return NULL; }
    if (!w.unit) goto done;
    {
        PyObject *encoded = PyUnicode_AsEncodedString(w.unit, "utf-8", "surrogatepass");
        Py_DECREF(w.unit); w.unit = encoded;
        if (!encoded) goto done;
    }
    w.pads = PyList_New(0); w.keys = PyDict_New(); w.chunks = PyList_New(0);
    empty = PyBytes_FromStringAndSize("\n", 1);
    if (!w.pads || !w.keys || !w.chunks || !empty || PyList_Append(w.pads, empty) < 0) goto done;
    if (walk(&w, v, 0, role) < 0 || flush(&w) < 0) goto done;
    if (w.fp == Py_None) {
        Py_DECREF(empty); empty = PyUnicode_FromString("");
        if (empty) result = PyUnicode_Join(empty, w.chunks);
    } else { result = Py_None; Py_INCREF(result); }
done:
    Py_XDECREF(empty); Py_XDECREF(w.unit); Py_XDECREF(w.pads);
    Py_XDECREF(w.keys); Py_XDECREF(w.chunks); PyMem_Free(w.buf); PyMem_Free(w.active); return result;
}
static int traverse(PyObject *m, visitproc visit, void *arg) {
    ModuleState *s = PyModule_GetState(m); size_t i;
    Py_VISIT(s->bailout); for (i = 0; i < NAME_COUNT; i++) Py_VISIT(s->names[i]); return 0;
}
static int clear(PyObject *m) {
    ModuleState *s = PyModule_GetState(m); size_t i;
    Py_CLEAR(s->bailout); for (i = 0; i < NAME_COUNT; i++) Py_CLEAR(s->names[i]); return 0;
}
static PyMethodDef methods[] = {{"encode", encode, METH_VARARGS, "Serialize JSON or model fields with bounded output chunks."}, {NULL, NULL, 0, NULL}};
static struct PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_cjson", NULL, sizeof(ModuleState), methods, NULL, traverse, clear, NULL};
PyMODINIT_FUNC PyInit__cjson(void) {
    PyObject *m = PyModule_Create(&definition);
    ModuleState *s;
    size_t i;
    if (!m) return NULL;
    s = PyModule_GetState(m);
    s->bailout = PyErr_NewException("dochan.output._cjson.Bailout", NULL, NULL);
    if (!s->bailout) goto fail;
    Py_INCREF(s->bailout);
    if (PyModule_AddObject(m, "Bailout", s->bailout) < 0) { Py_DECREF(s->bailout); goto fail; }
    for (i = 0; i < NAME_COUNT; i++) {
        s->names[i] = PyUnicode_InternFromString(names[i]); if (!s->names[i]) goto fail;
    }
    return m;
fail:
    Py_DECREF(m); return NULL;
}
