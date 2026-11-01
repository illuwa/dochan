/* Compile-time-only instrumentation; no counters or clock calls in release. */
#ifdef DOCHAN_PROFILE_INTERNALS
#include <time.h>
static double internal_times[8];
static unsigned long long internal_calls[8];
static double internal_clock(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}
#define INTERNAL_START double internal_stamp = internal_clock()
#define INTERNAL_END(i) do { internal_times[i] += internal_clock() - internal_stamp; internal_calls[i]++; } while (0)
static PyObject *internal_profile(PyObject *self, PyObject *unused)
{
    (void)self; (void)unused;
    PyObject *result = PyList_New(8);
    if (!result) return NULL;
    for (int i = 0; i < 8; i++) {
        PyObject *entry = Py_BuildValue("dK", internal_times[i], internal_calls[i]);
        if (!entry) { Py_DECREF(result); return NULL; }
        PyList_SetItem(result, i, entry);
    }
    return result;
}
#define INTERNAL_METHOD {"_profile", internal_profile, METH_NOARGS, NULL},
#else
#define INTERNAL_START ((void)0)
#define INTERNAL_END(i) ((void)0)
#define INTERNAL_METHOD
#endif
