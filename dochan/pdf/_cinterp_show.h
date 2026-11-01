/* Optional instrumented build only; normal builds have no timer overhead. */
#ifdef DOCHAN_PROFILE_SHOW
#include <time.h>
static double ShowTimes[4];
static unsigned long long ShowCalls, ShowGlyphs;
#define SHOW_START clock_t show_stamp = clock(); ShowCalls++
#define SHOW_PHASE(i) do { clock_t now = clock(); ShowTimes[i] += (double)(now - show_stamp) / CLOCKS_PER_SEC; show_stamp = now; } while (0)
#define SHOW_GLYPHS(n) (ShowGlyphs += (unsigned long long)(n))
static PyObject *show_profile(PyObject *self, PyObject *unused)
{
    (void)self; (void)unused;
    return Py_BuildValue("{s:d,s:d,s:d,s:d,s:K,s:K}",
        "decode_widths", ShowTimes[0], "positions", ShowTimes[1],
        "size_space", ShowTimes[2], "fragment", ShowTimes[3],
        "shows", ShowCalls, "glyphs", ShowGlyphs);
}
#else
#define SHOW_START ((void)0)
#define SHOW_PHASE(i) ((void)0)
#define SHOW_GLYPHS(n) ((void)0)
#endif
static PyObject *ShowFields[22];
static int show_fields_init(void)
{
    static const char *names[] = {"x","y","width","size","text","space_width","bold","italic","order","dir_x","dir_y","up_x","up_y","char_offsets","link_spans","note_ref","link_geometry_reliable","comment_spans","comment_markers","mcids","artifact","invisible"};
    for (int i = 0; i < 22; i++) {
        if (!ShowFields[i]) ShowFields[i] = PyUnicode_InternFromString(names[i]);
        if (!ShowFields[i]) return -1;
    }
    return 0;
}
/* Full horizontal glyph execution. Font snapshots are conservative and no
 * decoder callback runs inside this loop. Unsupported fonts yield the original
 * operator, without applying quote movement or TJ adjustments first. */
static int show_enter(Interpreter *s)
{
    if (show_fields_init() < 0) return -1;
    PyObject *value = PyObject_GetAttrString(s->owner, "_link_position_reliable");
    if (!value) return -1;
    s->link_reliable = PyObject_IsTrue(value); Py_DECREF(value);
    if (s->link_reliable < 0) return -1;
    /* A Python fallback may mutate fonts/widths. Never retain snapshots across
     * a yield; the hot loop has no arbitrary callbacks. */
    if (s->invalidate_tables) PyDict_Clear(s->tables);
    s->invalidate_tables = 0; s->show_table = NULL; s->show_font = NULL;
    return 0;
}
static int show_get_table(Interpreter *s)
{
    if (s->show_table && s->show_font == s->font) return 1;
    PyObject *key = PyLong_FromVoidPtr(s->font);
    if (!key) return -1;
    PyObject *table = PyDict_GetItemWithError(s->tables, key);
    if (!table && !PyErr_Occurred()) {
        table = PyObject_CallFunctionObjArgs(s->table_builder, s->font, NULL);
        if (!table) { Py_DECREF(key); return -1; }
        int ok = PyDict_SetItem(s->tables, key, table);
        Py_DECREF(table);
        if (ok < 0) { Py_DECREF(key); return -1; }
        table = PyDict_GetItemWithError(s->tables, key);
    }
    Py_DECREF(key);
    if (!table) return -1;
    s->glyph_yield_safe = table == Py_False;
    if (table == Py_None || table == Py_False) return 0;
    if (!PyTuple_CheckExact(table) || PyTuple_Size(table) != 12) return bail("invalid glyph table");
    PyObject *step = PyTuple_GetItem(table, 0), *mapping = PyTuple_GetItem(table, 1);
    if (!PyLong_CheckExact(step)) return bail("invalid glyph step");
    long n = PyLong_AsLong(step);
    if (PyErr_Occurred()) return -1;
    if ((n != 1 && n != 2) ||
        (n == 1 && (!PyTuple_CheckExact(mapping) || PyTuple_Size(mapping) != 256)) ||
        (n == 2 && !PyDict_CheckExact(mapping)) ||
        !PyUnicode_CheckExact(PyTuple_GetItem(table, 2)) ||
        !PyDict_CheckExact(PyTuple_GetItem(table, 3))) return bail("invalid glyph mapping");
    for (int i = 5; i <= 9; i++) {
        PyObject *item = PyTuple_GetItem(table, i);
        if (i == 7 ? !PyLong_CheckExact(item) : item != Py_True && item != Py_False)
            return bail("invalid glyph flags");
    }
    if ((PyTuple_GetItem(table, 10) != Py_True && PyTuple_GetItem(table, 10) != Py_False) ||
        (PyTuple_GetItem(table, 11) != Py_None && !PyFrozenSet_CheckExact(PyTuple_GetItem(table, 11))))
        return bail("invalid glyph reliability");
    s->show_table = table; s->show_font = s->font;
    return 1;
}
static int show_set(PyObject *dict, const char *key, PyObject *value)
{
    if (!value) return -1;
    int ok = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return ok;
}
static int show_number(PyObject *dict, const char *key, Num n)
{
    return show_set(dict, key, num_obj(n));
}
static int show_width(Interpreter *s, PyObject *code, double *out, int *explicit_width)
{
    PyObject *t = s->show_table, *widths = PyTuple_GetItem(t, 3);
    PyObject *value = PyDict_GetItemWithError(widths, code);
    if (!value && PyErr_Occurred()) return -1;
    if (explicit_width) {
        Num c;
        if (num_from(code, &c) < 0) return -1;
        if (PyTuple_GetItem(t, 11) != Py_None) {
            *explicit_width = PySet_Contains(PyTuple_GetItem(t, 11), code);
            if (*explicit_width < 0) return -1;
        } else *explicit_width = PyTuple_GetItem(t, 5) == Py_True &&
            (value || (PyTuple_GetItem(t, 6) == Py_True && c.v >= 0 && c.v <= 65535));
    }
    Num n;
    if (num_from(value ? value : PyTuple_GetItem(t, 4), &n) < 0) return -1;
    *out = n.v;
    return 0;
}
static int show_field(PyObject *dict, int index, PyObject *value)
{
    if (!value) return -1;
    int ok = PyDict_SetItem(dict, ShowFields[index], value);
    Py_DECREF(value); return ok;
}
static int show_field_number(PyObject *dict, int index, Num n)
{
    return show_field(dict, index, num_obj(n));
}
static int show_fragment(Interpreter *s, PyObject *text, Num start[6], double total,
                         double xs, double ys, double sw, double size,
                         PyObject *offsets, int geometry)
{
    PyObject *dict = NULL, *frag = NULL, *stack = NULL, *mcids = NULL, *overflow = NULL;
    int result = -1, artifact = 0;
    if (!s->fragment_template) {
        PyObject *sample = PyObject_CallFunction(s->fragment_type, "ddddsd", 0.0, 0.0, 0.0, 0.0, "", 0.0);
        if (!sample) goto done;
        s->fragment_template = PyObject_GetAttrString(sample, "__dict__"); Py_DECREF(sample);
        if (!s->fragment_template) goto done;
        if (!PyDict_CheckExact(s->fragment_template)) { bail("invalid Fragment dictionary"); goto done; }
    }
    /* Preserve CPython's shared instance keys; growing a fresh combined dict
     * for each fragment costs both memory and downstream attribute lookups. */
    dict = PyDict_Copy(s->fragment_template);
    if (!dict) goto done;
    stack = PyObject_GetAttrString(s->owner, "_marked_stack");
    overflow = PyObject_GetAttrString(s->owner, "_marked_overflow");
    mcids = PyList_New(0);
    if (!stack || !overflow || !mcids) goto done;
    if (!PyList_CheckExact(stack)) { bail("invalid marked stack"); goto done; }
    int over = PyObject_IsTrue(overflow);
    if (over < 0) goto done;
    for (Py_ssize_t i = 0; i < PyList_Size(stack); i++) {
        PyObject *entry = PyList_GetItem(stack, i);
        if (!PyTuple_CheckExact(entry) || PyTuple_Size(entry) != 2) { bail("invalid marked entry"); goto done; }
        PyObject *id = PyTuple_GetItem(entry, 0);
        PyObject *flag = PyTuple_GetItem(entry, 1);
        if ((id != Py_None && !PyLong_CheckExact(id)) || (flag != Py_True && flag != Py_False)) {
            bail("invalid marked values"); goto done;
        }
        artifact |= flag == Py_True;
        if (!over && id != Py_None && PyList_Append(mcids, id) < 0) goto done;
    }
    double scale = xs ? xs : 1.0;
    int bold = PyTuple_GetItem(s->show_table, 8) == Py_True ||
               ((s->tr.v == 2 || s->tr.v == 6) && s->stroke_width.v > 0);
    if (show_field_number(dict, 0, start[4]) < 0 || show_field_number(dict, 1, start[5]) < 0 ||
        show_field_number(dict, 2, nf(fabs(total) * scale)) < 0 ||
        show_field_number(dict, 3, nf(size)) < 0 ||
        PyDict_SetItem(dict, ShowFields[4], text) < 0 ||
        show_field_number(dict, 5, nf(sw)) < 0 ||
        PyDict_SetItem(dict, ShowFields[6], bold ? Py_True : Py_False) < 0 ||
        PyDict_SetItem(dict, ShowFields[7], PyTuple_GetItem(s->show_table, 9)) < 0 ||
        show_field(dict, 8, PyLong_FromSsize_t(PyList_Size(s->frags))) < 0 ||
        show_field_number(dict, 9, start[0]) < 0 || show_field_number(dict, 10, start[1]) < 0 ||
        show_field_number(dict, 11, start[2]) < 0 || show_field_number(dict, 12, start[3]) < 0 ||
        PyDict_SetItem(dict, ShowFields[13], offsets) < 0 ||
        show_field(dict, 14, PyList_New(0)) < 0 || show_field_number(dict, 15, ni(0)) < 0 ||
        PyDict_SetItem(dict, ShowFields[16], geometry ? Py_True : Py_False) < 0 ||
        show_field(dict, 17, PyList_New(0)) < 0 ||
        show_field(dict, 18, PyList_New(0)) < 0 ||
        show_field(dict, 19, PyList_AsTuple(mcids)) < 0 ||
        PyDict_SetItem(dict, ShowFields[20], artifact ? Py_True : Py_False) < 0 ||
        PyDict_SetItem(dict, ShowFields[21], s->tr.v == 3 || s->tr.v == 7 ? Py_True : Py_False) < 0) goto done;
    /* Generic allocation preserves the public dataclass type, fields, instance
     * dictionary and independent mutable defaults without its Python __init__. */
    frag = PyType_GenericAlloc((PyTypeObject *)s->fragment_type, 0);
    if (!frag || PyObject_SetAttrString(frag, "__dict__", dict) < 0) goto done;
    result = PyList_Append(s->frags, frag);
    (void)ys;
done:
    Py_XDECREF(dict); Py_XDECREF(frag); Py_XDECREF(stack); Py_XDECREF(mcids); Py_XDECREF(overflow);
    return result;
}
static int show_raw(Interpreter *s, PyObject *raw)
{
    Py_ssize_t bytes = PyBytes_Size(raw);
    if (bytes <= 0) return bytes < 0 ? -1 : 0;
    SHOW_START;
    int step = (int)PyLong_AsLong(PyTuple_GetItem(s->show_table, 0));
    const unsigned char *data = (const unsigned char *)PyBytes_AsString(raw);
    Py_ssize_t count = bytes / step, length = 0;
    SHOW_GLYPHS(count);
    PyObject *pieces = PyList_New(count), *text = NULL, *offsets = NULL;
    PyObject *context = NULL, *budget = NULL, *tracking = NULL, *stripped = NULL;
    PyObject *mapping = PyTuple_GetItem(s->show_table, 1), *missing = PyTuple_GetItem(s->show_table, 2);
    double *widths = NULL, total = 0.0, xs, ys, sw, size;
    Num start[6], trans[6], end[6], p, q, det;
    int result = -1, explicit_all = s->link_reliable && PyTuple_GetItem(s->show_table, 10) == Py_True;
    if (!pieces) goto done;
    if (count > PY_SSIZE_T_MAX / (Py_ssize_t)sizeof(double)) { PyErr_NoMemory(); goto done; }
    widths = PyMem_Malloc((size_t)count * sizeof(double));
    if (!widths && count) { PyErr_NoMemory(); goto done; }
    for (Py_ssize_t i = 0; i < count; i++) {
        if (i % 1024 == 0 && PyErr_CheckSignals() < 0) goto done;
        unsigned code = data[i * step];
        if (step == 2) code = (code << 8) | data[i * step + 1];
        PyObject *key = PyLong_FromUnsignedLong(code);
        if (!key) goto done;
        PyObject *piece = step == 1 ? PyTuple_GetItem(mapping, code) : PyDict_GetItemWithError(mapping, key);
        if (!piece && PyErr_Occurred()) { Py_DECREF(key); goto done; }
        if (!piece) piece = missing;
        if (!PyUnicode_CheckExact(piece)) { Py_DECREF(key); bail("invalid glyph text"); goto done; }
        /* Own the piece before any width lookup: a direct extension caller
         * can supply a dict whose equality callback mutates the mapping. */
        Py_INCREF(piece); PyList_SetItem(pieces, i, piece);
        int explicit_width;
        double w;
        if (show_width(s, key, &w, &explicit_width) < 0) { Py_DECREF(key); goto done; }
        Py_DECREF(key);
        explicit_all &= explicit_width;
        widths[i] = (w / 1000.0 * s->fs.v + s->tc.v + (step == 1 && code == 32 ? s->tw.v : 0.0)) * s->th.v;
        if (!isfinite(widths[i])) { bail("non-finite glyph displacement"); goto done; }
        Py_ssize_t n = PyUnicode_GetLength(piece);
        if (n < 0 || length > PY_SSIZE_T_MAX - n) { if (!PyErr_Occurred()) PyErr_NoMemory(); goto done; }
        length += n;
    }
    PyObject *empty = PyUnicode_FromString("");
    if (!empty) goto done;
    text = PyUnicode_Join(empty, pieces); Py_DECREF(empty);
    if (!text) goto done;
    SHOW_PHASE(0);
    tracking = PyObject_GetAttrString(s->owner, "track_char_positions");
    context = PyObject_GetAttrString(s->owner, "_form_context");
    if (!tracking || !context) goto done;
    if (!PyDict_CheckExact(context)) { bail("invalid glyph context"); goto done; }
    budget = PyDict_GetItemString(context, "char_positions");
    if (!budget) { bail("missing glyph budget"); goto done; }
    Py_INCREF(budget);
    Num available;
    if (num_from(budget, &available) < 0) goto done;
    int track = PyObject_IsTrue(tracking);
    if (track < 0) goto done;
    track = track && length <= 50000 && length <= available.v;
    if (track && show_number(context, "char_positions", ni(available.v - length)) < 0) goto done;
    if (matrix_mul(s->tm, s->ctm, start) < 0 || path_hypot(start[0], start[1], &xs) < 0 ||
        path_hypot(start[2], start[3], &ys) < 0) goto done;
    s->link_reliable = explicit_all;
    Num dot;
    if (num_mul(start[0], start[2], &p) < 0 || num_mul(start[1], start[3], &q) < 0 ||
        num_add(p, q, &dot) < 0) goto done;
    int geometry = explicit_all && xs > 0 && ys > 0 &&
        (fabs(xs - ys) <= 1e-3 * ys || fabs(xs - ys) <= 1e-3 * xs) &&
        fabs(dot.v) <= 1e-6 * xs * ys;
    double scale = xs ? xs : 1.0;
    offsets = PyTuple_New(track ? length + 1 : 0);
    if (!offsets) goto done;
    Py_ssize_t offset = 0;
    if (track) {
        PyObject *zero = PyFloat_FromDouble(0.0 * scale);
        if (!zero) goto done;
        PyTuple_SetItem(offsets, offset++, zero);
    }
    for (Py_ssize_t i = 0; i < count; i++) {
        if (track) {
            Py_ssize_t n = PyUnicode_GetLength(PyList_GetItem(pieces, i));
            for (Py_ssize_t j = 0; j < n; j++) {
                double v = fabs(total + widths[i] * (j + 1) / n) * scale;
                PyObject *value = PyFloat_FromDouble(v);
                if (!value) goto done;
                PyTuple_SetItem(offsets, offset++, value);
            }
        }
        total += widths[i];
    }
    if (!isfinite(total)) { bail("non-finite glyph total"); goto done; }
    SHOW_PHASE(1);
    if (show_width(s, PyTuple_GetItem(s->show_table, 7), &sw, NULL) < 0) goto done;
    sw = sw / 1000.0 * s->fs.v * s->th.v * scale;
    if (sw <= 0) sw = 0.25 * s->fs.v * scale;
    if (num_mul(start[0], start[3], &p) < 0 || num_mul(start[1], start[2], &q) < 0 ||
        num_sub(p, q, &det) < 0) goto done;
    PyObject *base = num_obj(num_abs(det)), *exponent = PyFloat_FromDouble(0.5);
    PyObject *power = base && exponent ? PyNumber_Power(base, exponent, Py_None) : NULL;
    Py_XDECREF(base); Py_XDECREF(exponent);
    if (!power) goto done;
    double root = PyFloat_AsDouble(power); Py_DECREF(power);
    if (PyErr_Occurred()) goto done;
    size = s->fs.v * (root ? root : 1.0);
    SHOW_PHASE(2);
    stripped = PyObject_CallMethod(text, "strip", NULL);
    if (!stripped) goto done;
    if (PyUnicode_GetLength(stripped) && show_fragment(s, text, start, total, xs, ys, sw, size, offsets, geometry) < 0) goto done;
    identity(trans); trans[4] = nf(total);
    if (matrix_mul(trans, s->tm, end) < 0) goto done;
    memcpy(s->tm, end, sizeof(end));
    SHOW_PHASE(3);
    result = 0;
done:
    Py_XDECREF(pieces); Py_XDECREF(text); Py_XDECREF(offsets);
    Py_XDECREF(context); Py_XDECREF(budget); Py_XDECREF(tracking); Py_XDECREF(stripped);
    PyMem_Free(widths);
    return result;
}
static int show_can_decode(Interpreter *s, PyObject *raw)
{
    if (!PyBytes_CheckExact(raw)) return 1;
    int step = (int)PyLong_AsLong(PyTuple_GetItem(s->show_table, 0));
    Py_ssize_t n = PyBytes_Size(raw);
    if (n % step) return 0;
    if (PyTuple_GetItem(s->show_table, 11) == Py_None) return 1;
    PyObject *map = PyTuple_GetItem(s->show_table, 1);
    const unsigned char *data = (const unsigned char *)PyBytes_AsString(raw);
    for (Py_ssize_t i = 0; i < n; i += step) {
        unsigned code = data[i];
        if (step == 2) code = (code << 8) | data[i+1];
        if (step == 1) { if (PyTuple_GetItem(map, code) == Py_None) return 0; }
        else {
            PyObject *key = PyLong_FromUnsignedLong(code);
            if (!key) return -1;
            int found = PyDict_Contains(map, key); Py_DECREF(key);
            if (found <= 0) return found;
        }
    }
    return 1;
}
static int show_operator(Interpreter *s, const char *op, Py_ssize_t size)
{
    int supported = show_get_table(s);
    if (supported <= 0) return supported;
    Py_ssize_t count = PyList_Size(s->operands);
    PyObject *last = count ? PyList_GetItem(s->operands, count - 1) : Py_None;
    /* Preflight the whole TJ before applying any movement or budget charge. */
    int allowed = show_can_decode(s, last);
    if (allowed <= 0) return allowed;
    if (OP("TJ") && PyList_CheckExact(last)) {
        for (Py_ssize_t i = 0; i < PyList_Size(last); i++) {
            allowed = show_can_decode(s, PyList_GetItem(last, i));
            if (allowed <= 0) return allowed;
        }
    }
    if (OP("'") || OP("\"")) {
        s->link_reliable = 1;
        if (move_line(s, ni(0), num_neg(s->tl)) < 0) return -1;
        if (OP("\"") && count >= 3) {
            if (operand_float(s, count-3, &s->tw) < 0 || operand_float(s, count-2, &s->tc) < 0) return -1;
        }
    }
    if (OP("TJ")) {
        if (PyList_CheckExact(last)) {
            for (Py_ssize_t i = 0; i < PyList_Size(last); i++) {
                PyObject *item = PyList_GetItem(last, i);
                if (PyBytes_CheckExact(item)) { if (show_raw(s, item) < 0) return -1; }
                else if (PyLong_Check(item) || PyFloat_Check(item)) {
                    Num n, trans[6];
                    if (num_from(item, &n) < 0) return -1;
                    identity(trans); trans[4] = nf(num_neg(n).v / 1000.0 * s->fs.v * s->th.v);
                    if (!isfinite(trans[4].v)) return bail("non-finite TJ advance");
                    if (matrix_mul(trans, s->tm, s->tm) < 0) return -1;
                }
            }
        }
    } else if (PyBytes_CheckExact(last) && show_raw(s, last) < 0) return -1;
    return 1;
}
