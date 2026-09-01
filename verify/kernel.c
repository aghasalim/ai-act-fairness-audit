/* Rebuild the integer confusion matrix behind every published fairness rate,
 * then recompute the rates from those integers.
 *
 * Each row of reports/segment_*.csv is a group at one global threshold. The
 * five headline rates are not independent: given n and the base rate you get
 * the positive and negative counts, and given TPR and FPR you get TP and FP.
 * Everything else in the row (selection rate, FNR, precision, calibration
 * ratio) is then determined. If any published rate had been computed with the
 * wrong denominator, or copied from the wrong column, the counts would not
 * come out as whole rows and the rates would not rebuild.
 *
 * The seven segment tables are seven different partitions of the same
 * transactions, so once the counts are recovered they must agree on the totals:
 * the same number of rows, the same number of frauds, the same number flagged,
 * the same true and false positives. Nothing in the Python compared them. A
 * grouping bug in one segment shows up here as a total that does not match the
 * other six.
 *
 * Columns are resolved by header name, not position, so reordering the CSV
 * cannot silently change what is compared.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXCOL 32
#define MAXLINE 4096
#define TOL 1e-12

static const char *FILES[] = {
    "amount_band", "card_type", "device_type", "email_class",
    "identity_present", "product_code", "region"
};

static int find_col(char header[][64], int ncol, const char *want)
{
    for (int i = 0; i < ncol; i++)
        if (strcmp(header[i], want) == 0)
            return i;
    fprintf(stderr, "  column %s is missing\n", want);
    return -1;
}

static int split(char *line, char out[][64], int max)
{
    int n = 0;
    char *p = line;
    while (n < max) {
        char *c = strchr(p, ',');
        size_t len = c ? (size_t)(c - p) : strlen(p);
        if (len > 63) len = 63;
        memcpy(out[n], p, len);
        out[n][len] = '\0';
        n++;
        if (!c) break;
        p = c + 1;
    }
    return n;
}

static double worst = 0.0;

static int check(const char *seg, const char *group, const char *what,
                 double got, double want)
{
    double d = fabs(got - want);
    if (d > worst) worst = d;
    if (d <= TOL) return 0;
    printf("  FAIL %s/%s %s: recomputed %.17g, published %.17g, diff %.3g\n",
           seg, group, what, got, want, d);
    return 1;
}

typedef struct { long rows, pos, flagged, tp, fp; } Totals;

static int check_file(const char *root, const char *seg, Totals *tot)
{
    char path[1024];
    snprintf(path, sizeof path, "%s/reports/segment_%s.csv", root, seg);
    FILE *f = fopen(path, "r");
    if (!f) { printf("  FAIL cannot open %s\n", path); return 1; }

    char line[MAXLINE];
    char head[MAXCOL][64], cell[MAXCOL][64];
    if (!fgets(line, sizeof line, f)) { printf("  FAIL %s is empty\n", path); fclose(f); return 1; }
    line[strcspn(line, "\r\n")] = '\0';
    int ncol = split(line, head, MAXCOL);

    int c_g = find_col(head, ncol, "group"), c_n = find_col(head, ncol, "n");
    int c_br = find_col(head, ncol, "base_rate"), c_sel = find_col(head, ncol, "selection_rate");
    int c_tpr = find_col(head, ncol, "TPR"), c_fpr = find_col(head, ncol, "FPR");
    int c_fnr = find_col(head, ncol, "FNR"), c_pre = find_col(head, ncol, "precision");
    int c_mp = find_col(head, ncol, "mean_pred"), c_cal = find_col(head, ncol, "calibration_ratio");
    if (c_g < 0 || c_n < 0 || c_br < 0 || c_sel < 0 || c_tpr < 0 || c_fpr < 0 ||
        c_fnr < 0 || c_pre < 0 || c_mp < 0 || c_cal < 0) { fclose(f); return 1; }

    int bad = 0;
    Totals t = {0, 0, 0, 0, 0};
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = '\0';
        if (line[0] == '\0') continue;
        int k = split(line, cell, MAXCOL);
        if (k != ncol) {
            printf("  FAIL %s: row has %d fields, header has %d\n", seg, k, ncol);
            bad++; continue;
        }
        const char *g = cell[c_g];
        long n = strtol(cell[c_n], NULL, 10);
        double br = atof(cell[c_br]), tpr = atof(cell[c_tpr]), fpr = atof(cell[c_fpr]);

        /* Positives and negatives must be whole rows. */
        double Pf = br * (double)n;
        long P = lround(Pf), N = n - P;
        if (fabs(Pf - (double)P) > 1e-6) {
            printf("  FAIL %s/%s: base_rate * n = %.9f is not a whole number of rows\n",
                   seg, g, Pf);
            bad++; continue;
        }
        double TPf = tpr * (double)P, FPf = fpr * (double)N;
        long TP = lround(TPf), FP = lround(FPf);
        if (fabs(TPf - (double)TP) > 1e-6 || fabs(FPf - (double)FP) > 1e-6) {
            printf("  FAIL %s/%s: TPR and FPR do not land on whole counts (%.9f, %.9f)\n",
                   seg, g, TPf, FPf);
            bad++; continue;
        }
        long FN = P - TP, TN = N - FP;
        if (TP < 0 || FP < 0 || FN < 0 || TN < 0) {
            printf("  FAIL %s/%s: negative cell in the confusion matrix\n", seg, g);
            bad++; continue;
        }

        /* Recompute every rate from the integers alone. */
        bad += check(seg, g, "selection_rate", (double)(TP + FP) / (double)n, atof(cell[c_sel]));
        bad += check(seg, g, "TPR", (double)TP / (double)(TP + FN), tpr);
        bad += check(seg, g, "FPR", (double)FP / (double)(FP + TN), fpr);
        bad += check(seg, g, "FNR", (double)FN / (double)(TP + FN), atof(cell[c_fnr]));
        bad += check(seg, g, "precision", (double)TP / (double)(TP + FP), atof(cell[c_pre]));
        bad += check(seg, g, "base_rate", (double)P / (double)n, br);
        bad += check(seg, g, "calibration_ratio", br / atof(cell[c_mp]), atof(cell[c_cal]));

        t.rows += n; t.pos += P; t.flagged += TP + FP; t.tp += TP; t.fp += FP;

        printf("  %-16s %-16s n=%-7ld TP=%-5ld FP=%-5ld FN=%-5ld TN=%-6ld\n",
               seg, g, n, TP, FP, FN, TN);
    }
    fclose(f);
    *tot = t;
    return bad;
}

int main(int argc, char **argv)
{
    const char *root = argc > 1 ? argv[1] : ".";
    const size_t nseg = sizeof FILES / sizeof FILES[0];
    Totals tot[sizeof FILES / sizeof FILES[0]] = {{0, 0, 0, 0, 0}};
    int clean[sizeof FILES / sizeof FILES[0]] = {0};
    int bad = 0;
    size_t ref = nseg;

    for (size_t i = 0; i < nseg; i++) {
        int b = check_file(root, FILES[i], &tot[i]);
        clean[i] = (b == 0);
        if (clean[i] && ref == nseg)
            ref = i;
        bad += b;
    }
    if (ref == nseg) {
        printf("C: no segment table parsed\n");
        return 1;
    }

    /* Seven partitions of one dataset. The totals are not allowed to differ.
     * A table that already failed above is left out: it has been reported. */
    static const char *WHAT[5] = { "rows", "frauds", "flagged", "true positives",
                                   "false positives" };
    for (size_t i = ref + 1; i < nseg; i++) {
        if (!clean[i])
            continue;
        const long a[5] = { tot[ref].rows, tot[ref].pos, tot[ref].flagged,
                            tot[ref].tp, tot[ref].fp };
        const long b[5] = { tot[i].rows, tot[i].pos, tot[i].flagged,
                            tot[i].tp, tot[i].fp };
        for (int k = 0; k < 5; k++)
            if (a[k] != b[k]) {
                printf("  FAIL %s and %s disagree on %s: %ld against %ld\n",
                       FILES[ref], FILES[i], WHAT[k], b[k], a[k]);
                bad++;
            }
    }

    if (bad) {
        printf("C: %d disagreement(s) with the published rates\n", bad);
        return 1;
    }
    printf("C: every published rate in %zu segment tables rebuilt from its integer\n"
           "   confusion matrix, worst residual %.1e (tolerance %.0e)\n", nseg, worst, TOL);
    printf("   all %zu partitions agree: %ld rows, %ld frauds, %ld flagged, %ld TP, %ld FP\n",
           nseg, tot[ref].rows, tot[ref].pos, tot[ref].flagged, tot[ref].tp, tot[ref].fp);
    return 0;
}
