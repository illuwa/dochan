/* Marked-content and ExtGState transitions mirror ContentTextExtractor.
 * The owner retains the public stack; the interpreter owns the page ID sets.
 * Only the standard, explicitly enabled owner consumes these events. */
static PyObject *marked_optional_attr(PyObject *owner, const char *name)
{
    PyObject *value = PyObject_GetAttrString(owner, name);
    if (!value && PyErr_ExceptionMatches(PyExc_AttributeError)) {
        PyErr_Clear();
        return PyDict_New();
    }
    return value;
}

static PyObject *marked_get(PyObject *mapping, const char *key)
{
    if (PyDict_CheckExact(mapping)) {
        PyObject *value = PyDict_GetItemString(mapping, key);
        if (!value) value = Py_None;
        Py_INCREF(value);
        return value;
    }
    return PyObject_CallMethod(mapping, "get", "s", key);
}

static int marked_begin(Interpreter *s, int bdc)
{
    PyObject *props = NULL, *mcid = NULL, *stack = NULL, *overflow = NULL;
    PyObject *zero = NULL, *one = NULL, *entry = NULL, *name = NULL;
    int result = -1, artifact = 0;
    Py_ssize_t count = PyList_Size(s->operands);
    props = bdc && count ? PyList_GetItem(s->operands, count - 1) : Py_None;
    Py_INCREF(props);
    int is_name = PyObject_IsInstance(props, PDFNameType);
    if (is_name < 0) goto done;
    if (is_name) {
        PyObject *properties = marked_optional_attr(s->owner, "properties");
        if (!properties) goto done;
        name = PyObject_Str(props);
        if (!name) { Py_DECREF(properties); goto done; }
        PyObject *resolved = PyObject_CallMethod(properties, "get", "O", name);
        Py_DECREF(properties);
        if (!resolved) goto done;
        replace_ref(&props, resolved);
    }
    if (PyDict_Check(props)) mcid = marked_get(props, "MCID");
    else { mcid = Py_None; Py_INCREF(mcid); }
    if (!mcid) goto done;
    zero = PyLong_FromLong(0);
    if (!zero) goto done;
    int valid = PyLong_CheckExact(mcid) ? PyObject_RichCompareBool(mcid, zero, Py_GE) : 0;
    if (valid < 0) goto done;
    if (!valid) { Py_INCREF(Py_None); replace_ref(&mcid, Py_None); }
    stack = PyObject_GetAttrString(s->owner, "_marked_stack");
    overflow = PyObject_GetAttrString(s->owner, "_marked_overflow");
    if (!stack || !overflow) goto done;
    if (!PyList_CheckExact(stack) || !PyLong_CheckExact(overflow)) {
        bail("invalid native marked state"); goto done;
    }
    int over = PyObject_IsTrue(overflow);
    if (over < 0) goto done;
    if (PyList_Size(stack) < 64 && !over) {
        if (count) {
            PyObject *tag = PyObject_Str(PyList_GetItem(s->operands, 0));
            if (!tag) goto done;
            artifact = PyUnicode_CompareWithASCIIString(tag, "Artifact") == 0;
            Py_DECREF(tag);
            if (PyErr_Occurred()) goto done;
        }
        entry = PyTuple_Pack(2, mcid, artifact ? Py_True : Py_False);
        if (!entry || PyList_Append(stack, entry) < 0) goto done;
        if (mcid != Py_None) {
            int duplicate = PySet_Contains(s->marked_ids, mcid);
            if (duplicate < 0 || (duplicate && PySet_Add(s->duplicate_marked_ids, mcid) < 0) ||
                PySet_Add(s->marked_ids, mcid) < 0) goto done;
        }
    } else {
        one = PyLong_FromLong(1);
        if (!one) goto done;
        PyObject *incremented = PyNumber_Add(overflow, one);
        if (!incremented) goto done;
        replace_ref(&overflow, incremented);
        if (PyObject_SetAttrString(s->owner, "_marked_overflow", overflow) < 0) goto done;
        int first = PyObject_RichCompareBool(overflow, one, Py_EQ);
        if (first < 0) goto done;
        if (first) {
            PyObject *warning = PyUnicode_FromString("WARN: PDF marked-content 깊이 한도 초과");
            if (!warning) goto done;
            int ok = PyList_Append(s->warnings, warning);
            Py_DECREF(warning);
            if (ok < 0) goto done;
        }
    }
    result = 0;
done:
    Py_XDECREF(props); Py_XDECREF(mcid); Py_XDECREF(stack); Py_XDECREF(overflow);
    Py_XDECREF(zero); Py_XDECREF(one); Py_XDECREF(entry); Py_XDECREF(name);
    return result;
}

static int marked_end(Interpreter *s)
{
    PyObject *overflow = PyObject_GetAttrString(s->owner, "_marked_overflow");
    if (!overflow) return -1;
    int over = PyObject_IsTrue(overflow);
    if (over < 0) { Py_DECREF(overflow); return -1; }
    if (over) {
        PyObject *one = PyLong_FromLong(1);
        PyObject *next = one ? PyNumber_Subtract(overflow, one) : NULL;
        Py_XDECREF(one); Py_DECREF(overflow);
        if (!next) return -1;
        int ok = PyObject_SetAttrString(s->owner, "_marked_overflow", next);
        Py_DECREF(next); return ok;
    }
    Py_DECREF(overflow);
    PyObject *stack = PyObject_GetAttrString(s->owner, "_marked_stack");
    if (!stack) return -1;
    if (!PyList_CheckExact(stack)) { Py_DECREF(stack); return bail("invalid native marked stack"); }
    Py_ssize_t count = PyList_Size(stack);
    int ok = count ? PyList_SetSlice(stack, count - 1, count, NULL) : 0;
    Py_DECREF(stack); return ok;
}

static PyObject *marked_resolve(PyObject *resolve, PyObject *value)
{
    if (!value) return NULL;
    if (!resolve) return value;
    PyObject *result = PyObject_CallFunctionObjArgs(resolve, value, NULL);
    Py_DECREF(value);
    return result;
}

static int marked_width(Interpreter *s)
{
    Py_ssize_t count = PyList_Size(s->operands);
    if (!count) return 0;
    PyObject *operand = PyList_GetItem(s->operands, count - 1);
    int is_name = PyObject_IsInstance(operand, PDFNameType);
    if (is_name <= 0) return is_name;
    PyObject *resolve = PyObject_GetAttrString(s->owner, "resolve_resource");
    if (!resolve) {
        if (!PyErr_ExceptionMatches(PyExc_AttributeError)) return -1;
        PyErr_Clear();
    }
    PyObject *resources = marked_optional_attr(s->owner, "resources");
    PyObject *states = NULL, *state = NULL, *width = NULL, *name = NULL;
    int result = -1;
    if (!resources) goto caught;
    if (PyDict_Check(resources)) states = marked_resolve(resolve, marked_get(resources, "ExtGState"));
    else { states = Py_None; Py_INCREF(states); }
    if (!states) goto caught;
    if (PyDict_Check(states)) {
        name = PyObject_Str(operand);
        if (!name) goto caught;
        state = marked_resolve(resolve, PyObject_CallMethod(states, "get", "O", name));
    } else { state = Py_None; Py_INCREF(state); }
    if (!state) goto caught;
    if (PyDict_Check(state)) width = marked_resolve(resolve, marked_get(state, "LW"));
    else { width = Py_None; Py_INCREF(width); }
    if (!width) goto caught;
    if (PyLong_Check(width) || PyFloat_Check(width)) {
        double number = PyFloat_AsDouble(width);
        if (PyErr_Occurred()) goto done;
        if (isfinite(number)) {
            PyObject *zero = PyLong_FromLong(0);
            if (!zero) goto done;
            int positive = PyObject_RichCompareBool(width, zero, Py_GE);
            Py_DECREF(zero);
            if (positive < 0) goto done;
            if (positive) {
                PyObject *converted = PyNumber_Float(width);
                if (!converted) goto done;
                number = PyFloat_AsDouble(converted);
                Py_DECREF(converted);
                if (PyErr_Occurred()) goto done;
                s->stroke_width = nf(number);
            }
        }
    }
    result = 0; goto done;
caught:
    if (PyErr_ExceptionMatches(PyExc_Exception)) { PyErr_Clear(); result = 0; }
done:
    Py_XDECREF(resolve); Py_XDECREF(resources); Py_XDECREF(states);
    Py_XDECREF(state); Py_XDECREF(width); Py_XDECREF(name);
    return result;
}

/* Include after _cinterp_show.h: callbacks observe the same published link
 * state as a former Python yield, and any callback change is read back. */
static int marked_operator(Interpreter *s, const char *op, Py_ssize_t size)
{
    if (!s->owner || !s->pure_fallbacks) return 0;
    if (!(OP("BDC") || OP("BMC") || OP("EMC") || OP("gs"))) return 0;
    if (PyObject_SetAttr(s->owner, ShowNames[SHOW_RELIABLE],
                         s->link_reliable ? Py_True : Py_False) < 0) return -1;
    int result = OP("EMC") ? marked_end(s) : OP("gs") ? marked_width(s) : marked_begin(s, OP("BDC"));
    if (result < 0) return -1;
    PyObject *reliable = PyObject_GetAttr(s->owner, ShowNames[SHOW_RELIABLE]);
    if (!reliable) return -1;
    s->link_reliable = PyObject_IsTrue(reliable);
    Py_DECREF(reliable);
    return s->link_reliable < 0 ? -1 : 1;
}
