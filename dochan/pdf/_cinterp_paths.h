/* Hand-written PathCollector translation. Included after the shared Num helpers.
 * Numeric storage has no Python references; the three output lists are borrowed.
 * Segment objects are materialized only when a painted edge reaches output. */
#define PATH_MAX_SEGMENTS 20000

typedef struct {
    Num x0, y0, x1, y1;
    Py_ssize_t first, last;
} PathGroup;

typedef struct {
    Num x0, y0, x1, y1;
    double length;
    Py_ssize_t next;
} PathEdge;

typedef struct {
    PathGroup *groups;
    PathEdge *edges;
    Py_ssize_t ngroups, groups_cap, nedges, edges_cap, current;
    Py_ssize_t edge_count, short_count;
    int overflow, short_disabled, has_point, has_start;
    Point point, start;
    PyObject *segments, *short_segments, *warnings;
} PathState;

static void
path_init(PathState *s, PyObject *segments, PyObject *short_segments,
          PyObject *warnings)
{
    memset(s, 0, sizeof(*s));
    s->current = -1;
    s->segments = segments;
    s->short_segments = short_segments;
    s->warnings = warnings;
}

static void
path_clear(PathState *s)
{
    PyMem_Free(s->groups);
    PyMem_Free(s->edges);
    s->groups = NULL;
    s->edges = NULL;
    s->ngroups = s->nedges = s->groups_cap = s->edges_cap = 0;
    s->current = -1;
}

static int
path_warn(PathState *s)
{
    Py_ssize_t n = PyList_Size(s->warnings);
    if (n < 0) return -1;
    return n == 0 ? PyList_Append(s->warnings, PathWarning) : 0;
}

static int
path_hypot(Num dx, Num dy, double *result)
{
    PyObject *x, *y, *r;
    if (dx.v == 0.0) { *result = fabs(dy.v); return 0; }
    if (dy.v == 0.0) { *result = fabs(dx.v); return 0; }
    x = num_obj(dx);
    if (x == NULL) return -1;
    y = num_obj(dy);
    if (y == NULL) { Py_DECREF(x); return -1; }
    r = PyObject_CallFunctionObjArgs(HypotFunction, x, y, NULL);
    Py_DECREF(x);
    Py_DECREF(y);
    if (r == NULL) return -1;
    *result = PyFloat_AsDouble(r);
    Py_DECREF(r);
    return PyErr_Occurred() ? -1 : 0;
}

static int
path_point(Num x, Num y, Num ctm[6], Point *out)
{
    Num xa, yc, xb, yd, sum;
    if (num_mul(x, ctm[0], &xa) || num_mul(y, ctm[2], &yc) ||
        num_add(xa, yc, &sum) || num_add(sum, ctm[4], &out->x)) return -1;
    if (num_mul(x, ctm[1], &xb) || num_mul(y, ctm[3], &yd) ||
        num_add(xb, yd, &sum) || num_add(sum, ctm[5], &out->y)) return -1;
    return 0;
}

static int
path_move(PathState *s, Point p)
{
    if (s->ngroups < PATH_MAX_SEGMENTS) {
        PathGroup *g;
        if (s->ngroups == s->groups_cap) {
            Py_ssize_t cap = s->groups_cap ? s->groups_cap * 2 : 16;
            PathGroup *groups;
            if (cap > PATH_MAX_SEGMENTS) cap = PATH_MAX_SEGMENTS;
            groups = PyMem_Realloc(s->groups, (size_t)cap * sizeof(*groups));
            if (groups == NULL) { PyErr_NoMemory(); return -1; }
            s->groups = groups;
            s->groups_cap = cap;
        }
        s->current = s->ngroups++;
        g = &s->groups[s->current];
        g->x0 = g->x1 = p.x;
        g->y0 = g->y1 = p.y;
        g->first = g->last = -1;
    } else {
        s->current = -1;
        s->overflow = 1;
        if (path_warn(s)) return -1;
    }
    s->point = s->start = p;
    s->has_point = s->has_start = 1;
    return 0;
}

static void
path_include(PathGroup *g, Point p)
{
    if (isfinite(p.x.v) && isfinite(p.y.v)) {
        /* Python min/max retain their first operand on ties (also with NaN). */
        if (p.x.v < g->x0.v) g->x0 = p.x;
        if (p.x.v > g->x1.v) g->x1 = p.x;
        if (p.y.v < g->y0.v) g->y0 = p.y;
        if (p.y.v > g->y1.v) g->y1 = p.y;
    }
}

static int
path_axis(Point p0, Point p1, PathEdge *edge)
{
    Num dx, dy, tmp;
    double length;
    if (!(isfinite(p0.x.v) && isfinite(p0.y.v) &&
          isfinite(p1.x.v) && isfinite(p1.y.v))) return 0;
    if (num_sub(p1.x, p0.x, &dx) || num_sub(p1.y, p0.y, &dy)) return -1;
    dx = num_abs(dx);
    dy = num_abs(dy);
    if (dx.v == 0.0) {
        if (!(dy.v > 0.0)) return 0;
    } else if (dy.v != 0.0) {
        if (!(dx.v <= 0.6 || dy.v <= 0.6)) return 0;
        if (path_hypot(dx, dy, &length)) return -1;
        if (!(length >= 1.0)) return 0;
    }
    edge->x0 = p0.x; edge->x1 = p1.x;
    edge->y0 = p0.y; edge->y1 = p1.y;
    /* Segment.__post_init__ sorts stably, retaining signed zero and Num tags. */
    if (edge->x1.v < edge->x0.v) {
        tmp = edge->x0; edge->x0 = edge->x1; edge->x1 = tmp;
    }
    if (edge->y1.v < edge->y0.v) {
        tmp = edge->y0; edge->y0 = edge->y1; edge->y1 = tmp;
    }
    if (num_sub(edge->x1, edge->x0, &dx) ||
        num_sub(edge->y1, edge->y0, &dy) ||
        path_hypot(dx, dy, &edge->length)) return -1;
    return 1;
}

static int
path_append_edge(PathState *s, PathGroup *g, PathEdge edge)
{
    Py_ssize_t i;
    if (s->nedges == s->edges_cap) {
        Py_ssize_t cap = s->edges_cap ? s->edges_cap * 2 : 32;
        PathEdge *edges;
        if (cap > PATH_MAX_SEGMENTS * 2) cap = PATH_MAX_SEGMENTS * 2;
        /* Long and short budgets bound stored edges to 40,000 per paint. */
        if (cap <= s->nedges) return bail("path edge storage bound");
        edges = PyMem_Realloc(s->edges, (size_t)cap * sizeof(*edges));
        if (edges == NULL) { PyErr_NoMemory(); return -1; }
        s->edges = edges;
        s->edges_cap = cap;
    }
    i = s->nedges++;
    edge.next = -1;
    s->edges[i] = edge;
    if (g->last >= 0) s->edges[g->last].next = i;
    else g->first = i;
    g->last = i;
    return 0;
}

static int
path_line(PathState *s, Point p, int emit, Point *extras, int nextras)
{
    PathGroup *g;
    PathEdge edge;
    int i, accepted;
    if (!s->has_point) return path_move(s, p);
    if (s->current < 0 && !s->overflow && path_move(s, s->point)) return -1;
    if (s->current >= 0) {
        g = &s->groups[s->current];
        for (i = 0; i < nextras; i++) path_include(g, extras[i]);
        path_include(g, p);
        if (emit) {
            accepted = path_axis(s->point, p, &edge);
            if (accepted < 0) return -1;
            if (accepted) {
                if (edge.length < 1.0) {
                    if (!s->short_disabled) {
                        s->short_count++;
                        if (s->short_count <= PATH_MAX_SEGMENTS) {
                            if (path_append_edge(s, g, edge)) return -1;
                        } else {
                            s->short_disabled = 1;
                            if (PyList_SetSlice(s->short_segments, 0,
                                                PyList_Size(s->short_segments), NULL)) return -1;
                        }
                    }
                } else if (s->edge_count < PATH_MAX_SEGMENTS) {
                    if (path_append_edge(s, g, edge)) return -1;
                    s->edge_count++;
                } else s->overflow = 1;
            }
        }
    }
    s->point = p;
    return 0;
}

static int
path_deviation(Point p0, Point p1, Point control, double *out)
{
    Num dx, dy, cx, cy, a, b, delta;
    double length;
    if (num_sub(p1.x, p0.x, &dx) || num_sub(p1.y, p0.y, &dy) ||
        path_hypot(dx, dy, &length)) return -1;
    if (length < 1e-9) {
        if (num_sub(control.x, p0.x, &cx) || num_sub(control.y, p0.y, &cy)) return -1;
        return path_hypot(cx, cy, out);
    }
    if (num_sub(control.y, p0.y, &cy) || num_mul(dx, cy, &a) ||
        num_sub(control.x, p0.x, &cx) || num_mul(dy, cx, &b) ||
        num_sub(a, b, &delta)) return -1;
    *out = num_abs(delta).v / length;
    return 0;
}

static int
path_curve(PathState *s, Point *controls, int ncontrols, Point end)
{
    int i, straight = 1;
    double deviation;
    if (!s->has_point) return path_move(s, end);
    for (i = 0; i < ncontrols; i++) {
        if (path_deviation(s->point, end, controls[i], &deviation)) return -1;
        if (!(deviation <= 1.0)) { straight = 0; break; }
    }
    return path_line(s, end, straight, controls, ncontrols);
}

static int
path_emit_segment(PathState *s, PathEdge *edge, int short_segment)
{
    PyObject *x0 = NULL, *y0 = NULL, *x1 = NULL, *y1 = NULL, *segment;
    int result = -1;
    x0 = num_obj(edge->x0);
    if (x0 == NULL) goto done;
    y0 = num_obj(edge->y0);
    if (y0 == NULL) goto done;
    x1 = num_obj(edge->x1);
    if (x1 == NULL) goto done;
    y1 = num_obj(edge->y1);
    if (y1 == NULL) goto done;
    segment = PyObject_CallFunctionObjArgs(SegmentType, x0, y0, x1, y1, NULL);
    if (segment != NULL) {
        result = PyList_Append(short_segment ? s->short_segments : s->segments, segment);
        Py_DECREF(segment);
    }
done:
    Py_XDECREF(x0); Py_XDECREF(y0); Py_XDECREF(x1); Py_XDECREF(y1);
    return result;
}

static int
path_paint(PathState *s, int stroke)
{
    Py_ssize_t i, j;
    if (s->overflow && path_warn(s)) return -1;
    for (i = 0; i < s->ngroups; i++) {
        PathGroup *g = &s->groups[i];
        if (g->first < 0) continue;
        if (!stroke) {
            Num dx, dy, minimum;
            if (num_sub(g->x1, g->x0, &dx) || num_sub(g->y1, g->y0, &dy)) return -1;
            minimum = dy.v < dx.v ? dy : dx;
            if (!(minimum.v <= 2.0)) continue;
        }
        for (j = g->first; j >= 0; j = s->edges[j].next) {
            PathEdge *edge = &s->edges[j];
            if (!stroke && edge->length <= 2.0) continue;
            if (edge->length < 1.0) {
                if (!s->short_disabled && path_emit_segment(s, edge, 1)) return -1;
                continue;
            }
            if (PyList_Size(s->segments) >= PATH_MAX_SEGMENTS) return path_warn(s);
            if (path_emit_segment(s, edge, 0)) return -1;
        }
    }
    return 0;
}

static int
path_operate(PathState *s, const char *op, Py_ssize_t oplen,
             Num *values, Py_ssize_t count, Num ctm[6])
{
    Point points[4];
    Num x, y, w, h, xw, yh;
    int i, close, stroke;
    if (oplen == 1 && (op[0] == 'm' || op[0] == 'l')) {
        if (count < 2) return bail("path coordinate operands");
        if (path_point(values[count-2], values[count-1], ctm, &points[0])) return -1;
        return op[0] == 'm' ? path_move(s, points[0]) : path_line(s, points[0], 1, NULL, 0);
    }
    if (oplen == 1 && (op[0] == 'c' || op[0] == 'v' || op[0] == 'y')) {
        int n = op[0] == 'c' ? 3 : 2;
        if (count < 2*n) return bail("path curve operands");
        for (i = 0; i < n; i++) {
            if (path_point(values[count-2*n+2*i], values[count-2*n+2*i+1], ctm, &points[i])) return -1;
        }
        return path_curve(s, points, n-1, points[n-1]);
    }
    if (oplen == 2 && op[0] == 'r' && op[1] == 'e') {
        if (count < 4) return bail("path rectangle operands");
        x = values[count-4]; y = values[count-3];
        w = values[count-2]; h = values[count-1];
        if (num_add(x, w, &xw) || num_add(y, h, &yh) ||
            path_point(x, y, ctm, &points[0]) ||
            path_point(xw, y, ctm, &points[1]) ||
            path_point(xw, yh, ctm, &points[2]) ||
            path_point(x, yh, ctm, &points[3]) || path_move(s, points[0])) return -1;
        for (i = 1; i < 4; i++) {
            if (path_line(s, points[i], 1, NULL, 0)) return -1;
        }
        return path_line(s, points[0], 1, NULL, 0);
    }
    if (oplen == 1 && op[0] == 'h') {
        return s->has_start ? path_line(s, s->start, 1, NULL, 0) : 0;
    }
    if ((oplen == 1 && op[0] != '\0' && strchr("SsfFBbn", op[0]) != NULL) ||
        (oplen == 2 && op[0] != '\0' && op[1] == '*' && strchr("fBb", op[0]) != NULL)) {
        close = op[0] == 's' || op[0] == 'b';
        stroke = op[0] != 'f' && op[0] != 'F';
        if (close && s->has_start && path_line(s, s->start, 1, NULL, 0)) return -1;
        if (op[0] != 'n' && path_paint(s, stroke)) return -1;
        s->ngroups = s->nedges = s->edge_count = 0;
        s->current = -1;
        s->overflow = s->has_point = s->has_start = 0;
    }
    return 0;
}

static void
path_width(PathState *s, Num width)
{
    /* PathCollector ignores w; stroke width belongs to text rendering state. */
    (void)s;
    (void)width;
}
