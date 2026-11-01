/* Original FIPS-197 byte-state cipher; SP 800-38A CBC/ECB. Not constant time. */
#define Py_LIMITED_API 0x03090000
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

static uint8_t sub[256], inv[256], mul[16][256];

static uint8_t gf(uint8_t a, uint8_t b) {
    uint8_t out = 0;
    for (int i = 0; i < 8; ++i) {
        if (b & 1) out ^= a;
        a = (uint8_t)((a << 1) ^ ((a & 128) ? 0x11b : 0));
        b >>= 1;
    }
    return out;
}

static void tables(void) {
    uint8_t exp[255];
    unsigned int log[256] = {0};
    uint8_t v = 1;
    for (int i = 0; i < 255; ++i) {
        exp[i] = v; log[v] = (unsigned int)i; v = gf(v, 3);
    }
    for (int i = 0; i < 256; ++i) {
        v = i ? exp[(255 - log[i]) % 255] : 0;
        uint8_t s = v;
        for (int j = 0; j < 4; ++j) {
            v = (uint8_t)((v << 1) | (v >> 7)); s ^= v;
        }
        sub[i] = s ^ 0x63; inv[sub[i]] = (uint8_t)i;
        for (int j = 0; j < 16; ++j) mul[j][i] = gf((uint8_t)i, (uint8_t)j);
    }
}

static void expand(const uint8_t *key, int size, uint8_t *rk) {
    int total = 16 * (size / 4 + 7);
    uint8_t rc = 1;
    memcpy(rk, key, (size_t)size);
    for (int n = size; n < total; n += 4) {
        uint8_t t[4]; memcpy(t, rk + n - 4, 4);
        if (n % size == 0) {
            uint8_t first = t[0];
            t[0] = sub[t[1]] ^ rc; t[1] = sub[t[2]];
            t[2] = sub[t[3]]; t[3] = sub[first]; rc = mul[2][rc];
        } else if (size == 32 && n % size == 16) {
            for (int j = 0; j < 4; ++j) t[j] = sub[t[j]];
        }
        for (int j = 0; j < 4; ++j) rk[n + j] = rk[n - size + j] ^ t[j];
    }
}

static void add(uint8_t *s, const uint8_t *rk) {
    for (int i = 0; i < 16; ++i) s[i] ^= rk[i];
}
static void shift_sub(uint8_t *s, int decrypt) {
    uint8_t t[16];
    for (int c = 0; c < 4; ++c) for (int r = 0; r < 4; ++r) {
        uint8_t v = s[4 * ((c + (decrypt ? 4 - r : r)) % 4) + r];
        t[4 * c + r] = decrypt ? inv[v] : sub[v];
    }
    memcpy(s, t, 16);
}
static void mix(uint8_t *s, int decrypt) {
    const int enc[4] = {2, 3, 1, 1}, dec[4] = {14, 11, 13, 9};
    const int *f = decrypt ? dec : enc;
    for (int c = 0; c < 4; ++c) {
        uint8_t t[4] = {0};
        for (int r = 0; r < 4; ++r) for (int k = 0; k < 4; ++k)
            t[r] ^= mul[f[(k - r + 4) % 4]][s[c * 4 + k]];
        memcpy(s + c * 4, t, 4);
    }
}
static void cipher(uint8_t *s, const uint8_t *rk, int nr, int decrypt) {
    add(s, rk + (decrypt ? nr * 16 : 0));
    for (int i = 1; i < nr; ++i) {
        shift_sub(s, decrypt);
        if (decrypt) { add(s, rk + (nr - i) * 16); mix(s, 1); }
        else { mix(s, 0); add(s, rk + i * 16); }
    }
    shift_sub(s, decrypt); add(s, rk + (decrypt ? 0 : nr * 16));
}

static PyObject *block(PyObject *self, PyObject *args) {
    const char *input, *keys;
    Py_ssize_t n, k;
    int nr, decrypt;
    (void)self;
    if (!PyArg_ParseTuple(args, "y#y#ii", &input, &n, &keys, &k, &nr, &decrypt)) return NULL;
    if (n != 16 || (nr != 10 && nr != 12 && nr != 14) || k != 16 * (nr + 1)) {
        PyErr_SetString(PyExc_ValueError, "Invalid AES block or round keys"); return NULL;
    }
    uint8_t s[16]; memcpy(s, input, 16); cipher(s, (const uint8_t *)keys, nr, decrypt);
    return PyBytes_FromStringAndSize((const char *)s, 16);
}

static PyObject *aes_crypt(PyObject *self, PyObject *args) {
    const char *key, *iv, *data;
    Py_ssize_t k, v, n;
    int decrypt, cbc;
    (void)self;
    if (!PyArg_ParseTuple(args, "y#y#y#ii", &key, &k, &iv, &v, &data, &n, &decrypt, &cbc)) return NULL;
    if ((k != 16 && k != 24 && k != 32) || v != 16 || n % 16) {
        PyErr_SetString(PyExc_ValueError, "Invalid AES key, IV or data length"); return NULL;
    }
    PyObject *result = PyBytes_FromStringAndSize(NULL, n);
    if (!result) return NULL;
    char *out = PyBytes_AsString(result);
    if (!out) { Py_DECREF(result); return NULL; }
    uint8_t rk[240], prev[16], s[16];
    expand((const uint8_t *)key, (int)k, rk); memcpy(prev, iv, 16);
    for (Py_ssize_t pos = 0; pos < n; pos += 16) {
        memcpy(s, data + pos, 16);
        if (cbc && !decrypt) add(s, prev);
        cipher(s, rk, (int)k / 4 + 6, decrypt);
        if (cbc && decrypt) add(s, prev);
        memcpy(out + pos, s, 16);
        if (cbc) memcpy(prev, decrypt ? (const uint8_t *)data + pos : s, 16);
    }
    /* Erase the stack key schedule; volatile stores cannot be optimized away. */
    volatile uint8_t *wipe = rk;
    for (int i = 0; i < 240; ++i) wipe[i] = 0;
    return result;
}

static PyMethodDef methods[] = {
    {"block", block, METH_VARARGS, "AES with an expanded standard key schedule."},
    {"crypt", aes_crypt, METH_VARARGS, "AES ECB/CBC without padding."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_caes", NULL, -1, methods, NULL, NULL, NULL, NULL
};
PyMODINIT_FUNC PyInit__caes(void) { tables(); return PyModule_Create(&module); }
