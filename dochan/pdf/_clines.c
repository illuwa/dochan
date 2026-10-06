/* Handwritten from dochan.pdf.content's row and _Line contracts.
 * No external implementation, generated code or private CPython API.
 * Floating point expressions deliberately retain Python's operation order. */
#define Py_LIMITED_API 0x03090000
#ifndef DOCHAN_CLINES_NUMERIC_ONLY
#include <Python.h>
#else
#include <stddef.h>
typedef void PyObject;
typedef ptrdiff_t Py_ssize_t;
typedef unsigned int Py_UCS4;
#endif
#include <math.h>
#include <stdint.h>

enum { X, Y, WIDTH, SIZE, SPACE, DX, DY, NUMBERS };
enum { LTR, RTL, DOWN, UP };

typedef struct {
    PyObject *object;                    /* borrowed from the private snapshot */
    PyObject *number[NUMBERS];
    PyObject *text, *bold, *italic, *order, *invisible;
    PyObject *across_object;
    double value[NUMBERS], along, across;
    int direction, plain;
    Py_UCS4 hangul;                       /* zero unless one Hangul syllable */
} FragmentData;

#ifndef DOCHAN_CLINES_NUMERIC_ONLY
static const char *numeric_names[] = {
    "x", "y", "width", "size", "space_width", "dir_x", "dir_y"
};
static const char *direction_names[] = {"ltr", "rtl", "down", "up"};

static int
exact_type(PyObject *object, PyObject *type)
{
    PyObject *actual = PyObject_Type(object);
    int same;
    if (actual == NULL)
        return -1;
    same = actual == type;
    Py_DECREF(actual);
    return same;
}

static void
clear_fragment(FragmentData *f)
{
    int j;
    for (j = 0; j < NUMBERS; j++)
        Py_XDECREF(f->number[j]);
    Py_XDECREF(f->text);
    Py_XDECREF(f->bold);
    Py_XDECREF(f->italic);
    Py_XDECREF(f->order);
    Py_XDECREF(f->invisible);
    Py_XDECREF(f->across_object);
}

/* Reject callback-capable annotation values before constructing any row. */
static int
ordinary_spans(PyObject *spans, int links)
{
    Py_ssize_t i, n;
    if (!PyList_CheckExact(spans))
        return 0;
    n = PyList_Size(spans);
    if (n < 0)
        return -1;
    for (i = 0; i < n; i++) {
        PyObject *span = PyList_GetItem(spans, i);
        PyObject *first, *last;
        if (!span)
            return -1;
        if (!PyTuple_CheckExact(span) || PyTuple_Size(span) != (links ? 3 : 2))
            return 0;
        first = PyTuple_GetItem(span, 0);
        last = PyTuple_GetItem(span, 1);
        if (!first || !last)
            return -1;
        if (!PyLong_CheckExact(first) || !PyLong_CheckExact(last))
            return 0;
        if (links && !PyUnicode_CheckExact(PyTuple_GetItem(span, 2)))
            return 0;
    }
    return 1;
}

/* 1: supported, 0: use Python for the entire call, -1: genuine error.
 * Only exact Fragment instances are inspected: a subclass may have getters
 * with side effects. All numeric inputs are finite floats or small exact ints.
 * Integers outside the exactly representable range need Python comparisons. */
static int
read_fragment(FragmentData *f, PyObject *object, PyObject *fragment_type)
{
    int j, same, negative = 0;
    PyObject *links = NULL, *comments = NULL, *note = NULL;
    PyObject *zero = NULL;
    Py_ssize_t length;
    same = exact_type(object, fragment_type);
    if (same <= 0)
        return same;
    f->object = object;
    f->plain = 1;
    for (j = 0; j < NUMBERS; j++) {
        f->number[j] = PyObject_GetAttrString(object, numeric_names[j]);
        if (f->number[j] == NULL)
            goto error;
        if (!PyFloat_CheckExact(f->number[j])) {
            f->plain = 0;
            if (!PyLong_CheckExact(f->number[j]))
                return 0;
        }
        f->value[j] = PyFloat_AsDouble(f->number[j]);
        if (PyErr_Occurred()) {
            if (PyErr_ExceptionMatches(PyExc_OverflowError)) {
                PyErr_Clear();
                return 0;
            }
            return -1;
        }
        if (!isfinite(f->value[j]))
            return 0;
        if (PyLong_CheckExact(f->number[j])) {
            /* Use the integer API, not a rounded double range check. */
            long long integer = PyLong_AsLongLong(f->number[j]);
            if (PyErr_Occurred()) {
                if (!PyErr_ExceptionMatches(PyExc_OverflowError))
                    return -1;
                PyErr_Clear();
                return 0;
            }
            if (integer < -9007199254740992LL || integer > 9007199254740992LL)
                return 0;
        }
    }
    if (fabs(f->value[DX]) >= fabs(f->value[DY]))
        f->direction = f->value[DX] >= 0 ? LTR : RTL;
    else
        f->direction = f->value[DY] < 0 ? DOWN : UP;
    switch (f->direction) {
    case LTR: f->along = f->value[X]; f->across = f->value[Y]; j = Y; break;
    case RTL: f->along = -f->value[X]; f->across = -f->value[Y]; j = Y; negative = 1; break;
    case DOWN: f->along = -f->value[Y]; f->across = f->value[X]; j = X; break;
    default: f->along = f->value[Y]; f->across = -f->value[X]; j = X; negative = 1; break;
    }
    if (negative)
        f->across_object = PyNumber_Negative(f->number[j]);
    else {
        f->across_object = f->number[j];
        Py_INCREF(f->across_object);
    }
    if (f->across_object == NULL)
        return -1;
    if (!(f->text = PyObject_GetAttrString(object, "text")) ||
            !(f->bold = PyObject_GetAttrString(object, "bold")) ||
            !(f->italic = PyObject_GetAttrString(object, "italic")) ||
            !(f->order = PyObject_GetAttrString(object, "order")) ||
            !(f->invisible = PyObject_GetAttrString(object, "invisible")) ||
            !(links = PyObject_GetAttrString(object, "link_spans")) ||
            !(comments = PyObject_GetAttrString(object, "comment_markers")) ||
            !(note = PyObject_GetAttrString(object, "note_ref")))
        goto error;
    /* Python constructs all row groups before calling _Line. An exotic
     * comparator or str method may mutate later fragments. Delegate the
     * whole original call rather than using cached coordinates in that case. */
    if (!PyUnicode_CheckExact(f->text) || !PyLong_CheckExact(f->order) ||
            (!PyBool_Check(f->bold) && !PyLong_CheckExact(f->bold)) ||
            (!PyBool_Check(f->italic) && !PyLong_CheckExact(f->italic)) ||
            (!PyBool_Check(f->invisible) && !PyLong_CheckExact(f->invisible)) ||
            (!PyLong_CheckExact(note) && !PyBool_Check(note)))
        goto unsupported;
    same = ordinary_spans(links, 1);
    if (same < 0)
        goto error;
    if (!same)
        goto unsupported;
    same = ordinary_spans(comments, 0);
    if (same < 0)
        goto error;
    if (!same)
        goto unsupported;
    if (!PyUnicode_CheckExact(f->text) || !PyBool_Check(f->bold) ||
            !PyBool_Check(f->italic) || !PyLong_CheckExact(f->order) ||
            !PyBool_Check(f->invisible) || !PyList_CheckExact(links) ||
            !PyList_CheckExact(comments) || !PyLong_CheckExact(note))
        f->plain = 0;
    else {
        zero = PyLong_FromLong(0);
        if (!zero)
            goto error;
        same = PyObject_RichCompareBool(note, zero, Py_EQ);
        if (same < 0)
            goto error;
        if (PyList_Size(links) || PyList_Size(comments) || !same)
            f->plain = 0;
    }
    if (f->plain) {
        length = PyUnicode_GetLength(f->text);
        if (length < 0)
            goto error;
        if (length == 1) {
            Py_UCS4 ch = PyUnicode_ReadChar(f->text, 0);
            if (ch == (Py_UCS4)-1 && PyErr_Occurred())
                goto error;
            if (ch >= 0xac00 && ch <= 0xd7a3)
                f->hangul = ch;
        }
    }
    Py_XDECREF(zero);
    Py_DECREF(links);
    Py_DECREF(comments);
    Py_DECREF(note);
    return 1;
unsupported:
    Py_XDECREF(zero);
    Py_XDECREF(links);
    Py_XDECREF(comments);
    Py_XDECREF(note);
    return 0;
error:
    Py_XDECREF(zero);
    Py_XDECREF(links);
    Py_XDECREF(comments);
    Py_XDECREF(note);
    if (PyErr_ExceptionMatches(PyExc_AttributeError)) {
        PyErr_Clear();
        return 0;
    }
    return -1;
}
#endif

/* These functions also compile unchanged into the sanitizer harness. */
static int
same_row(const FragmentData *f, const FragmentData *first, double size,
         double minimum)
{
    double tolerance = minimum;
    if (0.5 * size > tolerance)
        tolerance = 0.5 * size;
    return f->direction == first->direction &&
           fabs(f->across - first->across) <= tolerance;
}

/* Stable bottom-up mergesort: the left item wins every equal key,
 * including +0.0/-0.0. No Python callback or borrowed list slot is involved. */
static void
sort_row(FragmentData **items, FragmentData **scratch, Py_ssize_t n)
{
    Py_ssize_t width, start;
    for (width = 1; width < n; ) {
        for (start = 0; start < n; ) {
            Py_ssize_t middle = start + (n - start < width ? n - start : width);
            Py_ssize_t end = middle + (n - middle < width ? n - middle : width);
            Py_ssize_t left = start, right = middle, out = start;
            while (left < middle && right < end) {
                if (items[right]->along < items[left]->along)
                    scratch[out++] = items[right++];
                else
                    scratch[out++] = items[left++];
            }
            while (left < middle) scratch[out++] = items[left++];
            while (right < end) scratch[out++] = items[right++];
            start = end;
        }
        for (start = 0; start < n; start++) items[start] = scratch[start];
        if (width > n / 2)
            break;
        width *= 2;
    }
}

static double
median(double *values, int n)
{
    int i, j;
    for (i = 1; i < n; i++) {
        double value = values[i];
        for (j = i; j > 0 && value < values[j - 1]; j--)
            values[j] = values[j - 1];
        values[j] = value;
    }
    if (n % 2)
        return values[n / 2];
    return (values[n / 2 - 1] + values[n / 2]) / 2;
}

static int
comparable(const FragmentData *left, const FragmentData *right)
{
    return left->hangul && right->hangul && left->value[SIZE] > 0 &&
           fabs(left->value[SIZE] - right->value[SIZE]) <= left->value[SIZE] * 0.02 &&
           left->value[WIDTH] > 0 &&
           fabs(left->value[WIDTH] - right->value[WIDTH]) <= left->value[WIDTH] * 0.02;
}

/* NaN is used only as the local None sentinel. Nonfinite intermediate values
 * reject a fast row before median sorting (finite input may still overflow). */
static int
tracking(FragmentData **row, Py_ssize_t n, double *gaps, double *references)
{
    Py_ssize_t i, at, count = 0, overprinted = 0;
    if (row[0]->direction != LTR)
        return 0;
    for (i = 0; i < n - 1; i++) {
        gaps[i] = NAN;
        references[i] = NAN;
        if (comparable(row[i], row[i + 1])) {
            gaps[i] = row[i + 1]->along - row[i]->along - row[i]->value[WIDTH];
            if (!isfinite(gaps[i]))
                return -1;
            count++;
            if (row[i]->hangul == row[i + 1]->hangul)
                overprinted++;
        }
    }
    if (count < 6 || overprinted >= (count + 1) / 2)
        return 0;
    for (i = 0; i < n - 1; i++) {
        double nearby[8];
        int nearby_count = 0;
        Py_ssize_t first = i > 4 ? i - 4 : 0;
        Py_ssize_t end = n - 1 - i > 5 ? i + 5 : n - 1;
        if (isnan(gaps[i]))
            continue;
        for (at = first; at < end; at++)
            if (at != i && !isnan(gaps[at]))
                nearby[nearby_count++] = gaps[at];
        if (nearby_count >= 3) {
            references[i] = median(nearby, nearby_count);
            if (!isfinite(references[i]))
                return -1;
        }
    }
    return 1;
}

#ifndef DOCHAN_CLINES_NUMERIC_ONLY
/* Install owned temporaries and always release them, including on error. */
static int
put_owned(PyObject *dict, const char *name, PyObject *value)
{
    int result;
    if (value == NULL)
        return -1;
    result = PyDict_SetItemString(dict, name, value);
    Py_DECREF(value);
    return result;
}

static PyObject *
new_instance(PyObject *type, PyObject **dict)
{
    PyObject *instance = PyObject_CallMethod(type, "__new__", "O", type);
    if (!instance)
        return NULL;
    *dict = PyObject_GetAttrString(instance, "__dict__");
    if (!*dict) {
        Py_DECREF(instance);
        return NULL;
    }
    return instance;
}

static int
append_run(PyObject *runs, PyObject *text, PyObject *bold, PyObject *italic)
{
    Py_ssize_t n;
    int merged = 0;
    PyObject *previous, *old_text, *combined = NULL, *run;
    if (PyUnicode_GetLength(text) == 0)
        return 0;
    n = PyList_Size(runs);
    if (n < 0)
        return -1;
    if (n) {
        previous = PyList_GetItem(runs, n - 1);
        if (!previous)
            return -1;
        if (PyTuple_GetItem(previous, 1) == bold &&
                PyTuple_GetItem(previous, 2) == italic) {
            old_text = PyTuple_GetItem(previous, 0);
            if (!old_text)
                return -1;
            combined = PyUnicode_Concat(old_text, text);
            if (!combined)
                return -1;
            merged = 1;
        }
    }
    run = PyTuple_Pack(3, combined ? combined : text, bold, italic);
    Py_XDECREF(combined);
    if (!run)
        return -1;
    if (merged) {
        /* PyList_SetItem consumes the new reference on both paths. */
        return PyList_SetItem(runs, n - 1, run);
    }
    n = PyList_Append(runs, run);
    Py_DECREF(run);
    return (int)n;
}

static PyObject *
make_segment(PyObject *type, FragmentData *f)
{
    PyObject *dict = NULL, *instance = NULL, *run = NULL, *runs = NULL;
    instance = new_instance(type, &dict);
    if (!instance)
        return NULL;
    if (PyUnicode_GetLength(f->text)) {
        run = PyTuple_Pack(3, f->text, f->bold, f->italic);
        if (!run)
            goto error;
        runs = PyTuple_Pack(1, run);
    } else
        runs = PyTuple_New(0);
    if (!runs)
        goto error;
    if (put_owned(dict, "x0", PyFloat_FromDouble(f->along)) < 0 ||
            put_owned(dict, "x1", PyFloat_FromDouble(f->along + f->value[WIDTH])) < 0 ||
            PyDict_SetItemString(dict, "text", f->text) < 0 ||
            PyDict_SetItemString(dict, "space_width", f->number[SPACE]) < 0 ||
            PyDict_SetItemString(dict, "runs", runs) < 0)
        goto error;
    Py_DECREF(dict);
    Py_XDECREF(run);
    Py_DECREF(runs);
    return instance;
error:
    Py_XDECREF(instance);
    Py_XDECREF(dict);
    Py_XDECREF(run);
    Py_XDECREF(runs);
    return NULL;
}

static PyObject *
make_plain_line(FragmentData **row, Py_ssize_t n, PyObject *line_type,
                PyObject *segment_type, PyObject *empty, PyObject *space,
                double *references, int has_tracking)
{
    PyObject *line = NULL, *dict = NULL, *orders = NULL, *segments = NULL;
    PyObject *runs = NULL, *parts = NULL, *joined = NULL, *stripped = NULL;
    PyObject *last_character = NULL, *white = NULL, *suffix = NULL;
    PyObject *minimum_order = row[0]->order, *maximum_size = row[0]->number[SIZE];
    PyObject *segment;
    double minimum_along = row[0]->along;
    double maximum_end = row[0]->along + row[0]->value[WIDTH];
    double largest_size = row[0]->value[SIZE];
    double prev_end = 0.0, prev_space = 0.0;
    Py_ssize_t i, length;
    int compare, trailing;
    line = new_instance(line_type, &dict);
    if (!line)
        goto error;
    orders = PyTuple_New(n);
    segments = PyList_New(0);
    runs = PyList_New(0);
    parts = PyList_New(0);
    if (!orders || !segments || !runs || !parts)
        goto error;
    for (i = 0; i < n; i++) {
        FragmentData *f = row[i];
        double end = f->along + f->value[WIDTH];
        double gap = i ? f->along - prev_end : 0.0;
        double threshold = (f->value[SPACE] > prev_space ? f->value[SPACE] : prev_space) * 0.5;
        int inferred = has_tracking && i && !isnan(references[i - 1]) &&
            comparable(row[i - 1], f) && gap > references[i - 1] + f->value[SIZE] * 0.15;
        Py_INCREF(f->order);
        if (PyTuple_SetItem(orders, i, f->order) < 0)
            goto error;
        compare = PyObject_RichCompareBool(f->order, minimum_order, Py_LT);
        if (compare < 0)
            goto error;
        if (compare)
            minimum_order = f->order;
        if (f->along < minimum_along)
            minimum_along = f->along;
        if (end > maximum_end)
            maximum_end = end;
        if (f->value[SIZE] > largest_size) {
            largest_size = f->value[SIZE];
            maximum_size = f->number[SIZE];
        }
        if (i && (gap > threshold || inferred)) {
            /* Exact str methods preserve every Unicode whitespace rule. */
            suffix = PyObject_CallMethod(row[i - 1]->text, "endswith", "O", space);
            if (!suffix)
                goto error;
            compare = PyObject_IsTrue(suffix);
            Py_CLEAR(suffix);
            if (compare < 0)
                goto error;
            if (!compare && (PyList_Append(parts, space) < 0 ||
                    append_run(runs, space, f->bold, f->italic) < 0))
                goto error;
        }
        if (PyList_Append(parts, f->text) < 0 ||
                append_run(runs, f->text, f->bold, f->italic) < 0)
            goto error;
        segment = make_segment(segment_type, f);
        if (!segment)
            goto error;
        compare = PyList_Append(segments, segment);
        Py_DECREF(segment);
        if (compare < 0)
            goto error;
        prev_end = end;
        prev_space = f->value[SPACE];
    }
    joined = PyUnicode_Join(empty, parts);
    if (!joined)
        goto error;
    stripped = PyObject_CallMethod(joined, "strip", NULL);
    if (!stripped)
        goto error;
    length = PyUnicode_GetLength(joined);
    if (length < 0)
        goto error;
    last_character = PyUnicode_Substring(joined, length ? length - 1 : 0, length);
    if (!last_character)
        goto error;
    white = PyObject_CallMethod(last_character, "isspace", NULL);
    if (!white)
        goto error;
    trailing = PyUnicode_GetLength(stripped) != 0 && white == Py_True &&
               row[n - 1]->invisible == Py_False;
    if (PyDict_SetItemString(dict, "fragment_orders", orders) < 0 ||
            PyDict_SetItemString(dict, "order", minimum_order) < 0 ||
            put_owned(dict, "direction", PyUnicode_FromString(direction_names[row[0]->direction])) < 0 ||
            put_owned(dict, "along_start", PyFloat_FromDouble(minimum_along)) < 0 ||
            put_owned(dict, "along_end", PyFloat_FromDouble(maximum_end)) < 0 ||
            put_owned(dict, "across", PyFloat_FromDouble(row[0]->across)) < 0 ||
            put_owned(dict, "left", PyFloat_FromDouble(minimum_along)) < 0 ||
            put_owned(dict, "right", PyFloat_FromDouble(maximum_end)) < 0 ||
            put_owned(dict, "y", PyFloat_FromDouble(row[0]->across)) < 0 ||
            PyDict_SetItemString(dict, "size", maximum_size) < 0 ||
            PyDict_SetItemString(dict, "first_size", row[0]->number[SIZE]) < 0 ||
            PyDict_SetItemString(dict, "last_size", row[n - 1]->number[SIZE]) < 0 ||
            PyDict_SetItemString(dict, "segments", segments) < 0 ||
            PyDict_SetItemString(dict, "runs", runs) < 0 ||
            PyDict_SetItemString(dict, "trailing_space", trailing ? Py_True : Py_False) < 0 ||
            PyDict_SetItemString(dict, "text", stripped) < 0)
        goto error;
    Py_DECREF(dict);
    Py_DECREF(orders);
    Py_DECREF(segments);
    Py_DECREF(runs);
    Py_DECREF(parts);
    Py_DECREF(joined);
    Py_DECREF(stripped);
    Py_DECREF(last_character);
    Py_DECREF(white);
    return line;
error:
    Py_XDECREF(line);
    Py_XDECREF(dict);
    Py_XDECREF(orders);
    Py_XDECREF(segments);
    Py_XDECREF(runs);
    Py_XDECREF(parts);
    Py_XDECREF(joined);
    Py_XDECREF(stripped);
    Py_XDECREF(last_character);
    Py_XDECREF(white);
    Py_XDECREF(suffix);
    return NULL;
}

static PyObject *
make_row(FragmentData *data, Py_ssize_t first, Py_ssize_t end,
         FragmentData **row, FragmentData **scratch, double *gaps, double *references,
         PyObject *line_type, PyObject *segment_type, PyObject *empty, PyObject *space)
{
    Py_ssize_t i, n = end - first;
    int plain = 1, has_tracking = 0;
    PyObject *fragments, *line;
    for (i = 0; i < n; i++) {
        row[i] = &data[first + i];
        if (!row[i]->plain)
            plain = 0;
    }
    sort_row(row, scratch, n);
    if (plain) {
        has_tracking = tracking(row, n, gaps, references);
        if (has_tracking < 0)
            plain = 0;
    }
    if (plain)
        return make_plain_line(row, n, line_type, segment_type, empty, space,
                               references, has_tracking);
    fragments = PyList_New(n);
    if (!fragments)
        return NULL;
    for (i = 0; i < n; i++) {
        Py_INCREF(row[i]->object);
        if (PyList_SetItem(fragments, i, row[i]->object) < 0) {
            Py_DECREF(fragments);
            return NULL;
        }
    }
    line = PyObject_CallFunctionObjArgs(line_type, fragments, NULL);
    Py_DECREF(fragments);
    return line;
}

static int
object_same_row(FragmentData *f, FragmentData *first, double size, double minimum)
{
    PyObject *delta = NULL, *absolute = NULL, *tolerance = NULL;
    int result = -1;
    double tol = 0.5 * size > minimum ? 0.5 * size : minimum;
    if (f->direction != first->direction)
        return 0;
    /* Python subtracts two ints exactly before comparing to float tolerance. */
    delta = PyNumber_Subtract(f->across_object, first->across_object);
    if (!delta)
        goto done;
    absolute = PyNumber_Absolute(delta);
    if (!absolute)
        goto done;
    tolerance = PyFloat_FromDouble(tol);
    if (!tolerance)
        goto done;
    result = PyObject_RichCompareBool(absolute, tolerance, Py_LE);
done:
    Py_XDECREF(delta);
    Py_XDECREF(absolute);
    Py_XDECREF(tolerance);
    return result;
}

static PyObject *
assemble_lines(PyObject *module, PyObject *args)
{
    PyObject *fragments, *line_type, *segment_type, *fragment_type, *tolerance_object;
    PyObject *snapshot = NULL, *result = NULL, *empty = NULL, *space = NULL;
    FragmentData *data = NULL;
    FragmentData **row = NULL, **scratch = NULL;
    double *gaps = NULL, *references = NULL;
    double minimum, current_size = 0.0;
    Py_ssize_t n = 0, i, first = 0;
    int supported, in_row;
    (void)module;
    if (!PyArg_ParseTuple(args, "OOOOO:assemble_lines", &fragments, &line_type,
            &segment_type, &fragment_type, &tolerance_object))
        return NULL;
    if (!PyList_CheckExact(fragments) || !PyFloat_CheckExact(tolerance_object))
        Py_RETURN_NONE;
    minimum = PyFloat_AsDouble(tolerance_object);
    if (!isfinite(minimum))
        Py_RETURN_NONE;
    n = PyList_Size(fragments);
    if (n < 0)
        return NULL;
    /* Copy only object references under the GIL. Never retain a pointer into
     * caller-owned list storage across any call into Python. */
    snapshot = PyList_GetSlice(fragments, 0, n);
    if (!snapshot)
        return NULL;
    n = PyList_Size(snapshot);
    if (n < 0)
        goto done;
    result = PyList_New(0);
    if (!result || !n)
        goto done;
    if ((size_t)n > SIZE_MAX / sizeof(FragmentData) ||
            (size_t)n > SIZE_MAX / sizeof(FragmentData *) ||
            (size_t)n > SIZE_MAX / sizeof(double)) {
        PyErr_NoMemory();
        goto error;
    }
    data = PyMem_Calloc((size_t)n, sizeof(FragmentData));
    row = PyMem_Malloc((size_t)n * sizeof(FragmentData *));
    scratch = PyMem_Malloc((size_t)n * sizeof(FragmentData *));
    gaps = PyMem_Malloc((size_t)n * sizeof(double));
    references = PyMem_Malloc((size_t)n * sizeof(double));
    empty = PyUnicode_FromString("");
    space = PyUnicode_FromString(" ");
    if (!data || !row || !scratch || !gaps || !references || !empty || !space) {
        if (!PyErr_Occurred())
            PyErr_NoMemory();
        goto error;
    }
    /* Finish validation before producing any rows. NaN/infinity anywhere must
     * delegate the whole original call, not only its affected row. */
    for (i = 0; i < n; i++) {
        PyObject *object = PyList_GetItem(snapshot, i);
        if (!object)
            goto error;
        supported = read_fragment(&data[i], object, fragment_type);
        if (supported < 0)
            goto error;
        if (!supported) {
            Py_DECREF(result);
            result = Py_None;
            Py_INCREF(result);
            goto done;
        }
    }
    for (i = 0; i < n; i++) {
        if (i == first)
            in_row = 1;
        else if (PyFloat_CheckExact(data[i].across_object) &&
                PyFloat_CheckExact(data[first].across_object))
            in_row = same_row(&data[i], &data[first], current_size, minimum);
        else
            in_row = object_same_row(&data[i], &data[first], current_size, minimum);
        if (in_row < 0)
            goto error;
        if (!in_row) {
            PyObject *line = make_row(data, first, i, row, scratch, gaps, references,
                                      line_type, segment_type, empty, space);
            if (!line)
                goto error;
            supported = PyList_Append(result, line);
            Py_DECREF(line);
            if (supported < 0)
                goto error;
            first = i;
            current_size = 0.0;
        }
        if (data[i].value[SIZE] > current_size)
            current_size = data[i].value[SIZE];
    }
    {
        PyObject *line = make_row(data, first, n, row, scratch, gaps, references,
                                  line_type, segment_type, empty, space);
        if (!line)
            goto error;
        supported = PyList_Append(result, line);
        Py_DECREF(line);
        if (supported < 0)
            goto error;
    }
    goto done;
error:
    Py_CLEAR(result);
done:
    if (data)
        for (i = 0; i < n; i++) clear_fragment(&data[i]);
    PyMem_Free(data);
    PyMem_Free(row);
    PyMem_Free(scratch);
    PyMem_Free(gaps);
    PyMem_Free(references);
    Py_XDECREF(snapshot);
    Py_XDECREF(empty);
    Py_XDECREF(space);
    return result;
}

static PyMethodDef methods[] = {
    {"assemble_lines", assemble_lines, METH_VARARGS,
     "Assemble exact Fragment lists; return None when the whole call needs Python."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef definition = {
    PyModuleDef_HEAD_INIT, "_clines", "Optional, handwritten line assembly.",
    -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC
PyInit__clines(void)
{
    return PyModule_Create(&definition);
}
#endif
