/* Compile the actual numerical core, not a rewritten approximation:
 * clang -std=c99 -O1 -g -ffp-contract=off -fsanitize=address,undefined
 *       -fno-omit-frame-pointer tests/pdf_clines_sanitize.c -o /tmp/clines-sanitize
 */
#define DOCHAN_CLINES_NUMERIC_ONLY
#include "../dochan/pdf/_clines.c"
#include <assert.h>
#include <float.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t random_state = UINT64_C(20261006);
static uint64_t
random_word(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 7;
    random_state ^= random_state << 17;
    return random_state;
}

static double
number(void)
{
    static const double special[] = {0.0, -0.0, DBL_MAX, -DBL_MAX,
                                    DBL_MIN, -DBL_MIN, 3.0, 5.0, 10.0};
    uint64_t value = random_word();
    if (value % 3 == 0)
        return special[value % (sizeof(special) / sizeof(special[0]))];
    return (double)(value % 10001) / 100.0 - 50.0;
}

int
main(void)
{
    unsigned long trial;
    size_t cases = 200000;
    for (trial = 0; trial < cases; trial++) {
        Py_ssize_t n = (Py_ssize_t)(random_word() % 129);
        size_t allocated = n ? (size_t)n : 1;
        FragmentData *data = calloc(allocated, sizeof(*data));
        FragmentData **items = malloc(allocated * sizeof(*items));
        FragmentData **scratch = malloc(allocated * sizeof(*scratch));
        double *gaps = malloc(allocated * sizeof(*gaps));
        double *references = malloc(allocated * sizeof(*references));
        Py_ssize_t i, j;
        assert(data && items && scratch && gaps && references);
        for (i = 0; i < n; i++) {
            data[i].along = number();
            data[i].across = number();
            data[i].direction = (int)(random_word() % 4);
            data[i].value[WIDTH] = number();
            data[i].value[SIZE] = number();
            data[i].hangul = (Py_UCS4)(0xac00 + random_word() % 8);
            items[i] = &data[i];
        }
        sort_row(items, scratch, n);
        for (i = 1; i < n; i++) {
            assert(!(items[i]->along < items[i - 1]->along));
            if (items[i]->along == items[i - 1]->along)
                assert(items[i] > items[i - 1]);
        }
        if (n) {
            double size = number(), minimum = number();
            double tolerance = fmax(minimum, 0.5 * size);
            for (i = 0; i < n; i++) {
                int expected = data[i].direction == data[0].direction &&
                    fabs(data[i].across - data[0].across) <= tolerance;
                assert(same_row(&data[i], &data[0], size, minimum) == expected);
            }
            /* Exercise every tracking window, gaps and repeated glyphs. */
            items[0]->direction = LTR;
            (void)tracking(items, n, gaps, references);
            for (i = 0; i < n; i++) {
                data[i].along = (double)i * 10.2;
                data[i].value[WIDTH] = 10.0;
                data[i].value[SIZE] = 10.0;
                data[i].hangul = (Py_UCS4)(0xac00 + i % 8);
                items[i] = &data[i];
            }
            data[0].direction = LTR;
            assert(tracking(items, n, gaps, references) == (n >= 7));
        }
        {
            double values[8], ordered[8], expected, actual;
            int count = 3 + (int)(random_word() % 6);
            for (i = 0; i < count; i++)
                ordered[i] = values[i] = number();
            /* Independent stable bubble sort for the median oracle. */
            for (i = count; i > 1; i--)
                for (j = 1; j < i; j++)
                    if (ordered[j] < ordered[j - 1]) {
                        double temp = ordered[j];
                        ordered[j] = ordered[j - 1];
                        ordered[j - 1] = temp;
                    }
            expected = count % 2 ? ordered[count / 2] :
                (ordered[count / 2 - 1] + ordered[count / 2]) / 2;
            actual = median(values, count);
            assert(memcmp(&expected, &actual, sizeof(double)) == 0);
        }
        free(data);
        free(items);
        free(scratch);
        free(gaps);
        free(references);
    }
    printf("200000 numeric cases: stable sort, row grouping, Hangul tracking, median; ASan/UBSan clean\n");
    return 0;
}
