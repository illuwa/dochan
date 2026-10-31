/* Conservative XML allocation preflight; original implementation.
 * This is not an XML parser. Expat still checks well-formedness and namespaces.
 * Uncertain syntax returns false and is handled by the bounded Python target.
 */
#define Py_LIMITED_API 0x03090000
#include <Python.h>

static PyObject *bounded_structure(PyObject *self, PyObject *args)
{
    PyObject *data;
    char *raw;
    Py_ssize_t size, maximum, max_elements, i, depth = 0, elements = 0;
    (void)self;
    if (!PyArg_ParseTuple(args, "Onn:bounded_structure", &data, &maximum, &max_elements))
        return NULL;
    if (!PyBytes_Check(data))
        Py_RETURN_FALSE;
    if (PyBytes_AsStringAndSize(data, &raw, &size) < 0)
        return NULL;
    for (i = 0; i < size; ++i) {
        Py_ssize_t start;
        char quote = 0;
        int closing;
        if (raw[i] == '\0')
            Py_RETURN_FALSE;
        if (raw[i] != '<')
            continue;
        start = ++i;
        if (i >= size)
            Py_RETURN_FALSE;
        /* Only the leading XML declaration may contain a processing marker. */
        if (raw[i] == '?') {
            if (start != 1 || size < 7 || raw[2] != 'x' || raw[3] != 'm' ||
                raw[4] != 'l' || raw[5] != ' ')
                Py_RETURN_FALSE;
            for (; i + 1 < size; ++i) {
                if (raw[i] == '<' || raw[i] == '\0')
                    Py_RETURN_FALSE;
                if (raw[i] == '?' && raw[i + 1] == '>')
                    break;
            }
            if (i + 1 >= size)
                Py_RETURN_FALSE;
            ++i;
            continue;
        }
        if (raw[i] == '!')
            Py_RETURN_FALSE;
        closing = raw[i] == '/';
        for (; i < size; ++i) {
            char c = raw[i];
            if (c == '<' || c == '\0')
                Py_RETURN_FALSE;
            if (quote) {
                if (c == quote)
                    quote = 0;
            } else if (c == '\'' || c == '"') {
                quote = c;
            } else if (c == '>') {
                break;
            }
        }
        if (i == size)
            Py_RETURN_FALSE;
        if (closing) {
            if (depth == 0)
                Py_RETURN_FALSE;
            --depth;
        } else {
            if (++elements > max_elements || depth >= maximum)
                Py_RETURN_FALSE;
            if (i == start || raw[i - 1] != '/')
                ++depth;
        }
    }
    if (depth != 0 || elements == 0)
        Py_RETURN_FALSE;
    Py_RETURN_TRUE;
}

static PyMethodDef methods[] = {
    {"bounded_structure", bounded_structure, METH_VARARGS,
     "Prove element/depth bounds for simple byte XML before allocation."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_cxml", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__cxml(void)
{
    return PyModule_Create(&module);
}
