/* Shared ABI for lazy, tagged path coordinates. No CPython-private layouts. */
#ifndef DOCHAN_CSEGMENTS_H
#define DOCHAN_CSEGMENTS_H
#include <stdint.h>
typedef struct { double v; int integer; } SegmentNumber;
typedef struct { SegmentNumber x0, y0, x1, y1; } SegmentRecord;
typedef struct {
    PyObject_HEAD
    SegmentRecord *records;
    PyObject **cache;
    Py_ssize_t size, capacity;
    uint64_t generation;
} SegmentList;
typedef struct {
    PyTypeObject *type;
} SegmentAPI;
#define SEGMENT_CAPSULE "dochan.pdf._cinterp._segments_api"
#endif
