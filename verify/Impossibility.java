// The impossibility, checked as arithmetic rather than read off a chart.
//
// Chouldechova's identity ties a group's base rate to its error rates and its
// precision:
//
//     FPR = p/(1-p) * (1-FNR) * (1-PPV)/PPV
//
// Read the other way it says the base rate is pinned: fix a group's FPR, FNR
// and PPV and p is no longer free. So two groups that share all three must
// share a base rate. The groups here do not: product-code base rates run from
// 2.1% to 12.8%, and that is the whole of the impossibility.
//
// The README says the three fairness policies each break the other two. That
// is a claim about the published table, and it is checked here directly:
//
//   1. every published row solves the identity back to its own base rate,
//   2. the base rates genuinely differ, so the constraint is live,
//   3. equal selection rate and equal FPR at the published targets would need
//      a true positive rate above 1 in at least one group, which is not a hard
//      trade-off but an arithmetic impossibility,
//   4. each policy in impossibility.csv has the smallest spread on the
//      criterion it targets and not on the others,
//   5. only the global threshold gives the same decision to the same score.
//
// Run with: java verify/Impossibility.java <repo root>

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Impossibility {

    static final String[] SEGMENTS = {
        "amount_band", "card_type", "device_type", "email_class",
        "identity_present", "product_code", "region"
    };
    static final double TOL = 1e-12;

    static int failures = 0;
    static double worst = 0.0;

    static void fail(String msg) {
        System.out.println("  FAIL " + msg);
        failures++;
    }

    /** Rows of a CSV as name to value maps, columns resolved by header. */
    static List<Map<String, String>> readCsv(Path p) throws IOException {
        List<String> lines = Files.readAllLines(p);
        String[] head = lines.get(0).split(",", -1);
        List<Map<String, String>> out = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            if (lines.get(i).isBlank()) continue;
            String[] cell = lines.get(i).split(",", -1);
            if (cell.length != head.length) {
                fail(p.getFileName() + " row " + i + " has " + cell.length
                     + " fields, header has " + head.length);
                continue;
            }
            Map<String, String> row = new LinkedHashMap<>();
            for (int j = 0; j < head.length; j++) row.put(head[j], cell[j]);
            out.add(row);
        }
        return out;
    }

    static double num(Map<String, String> row, String col) {
        String v = row.get(col);
        if (v == null) throw new IllegalStateException("no column " + col);
        return Double.parseDouble(v);
    }

    /** Pull one numeric field out of audit.json by name, no JSON library. */
    static double json(String doc, String key) {
        Matcher m = Pattern.compile("\"" + Pattern.quote(key)
                                    + "\"\\s*:\\s*(-?[0-9.eE+-]+)").matcher(doc);
        if (!m.find()) throw new IllegalStateException("audit.json has no " + key);
        return Double.parseDouble(m.group(1));
    }

    public static void main(String[] args) throws IOException {
        Path root = Path.of(args.length > 0 ? args[0] : ".");
        String doc = Files.readString(root.resolve("reports/audit.json"));

        // 1. Every published row solves the identity back to its own base rate.
        int rows = 0;
        for (String seg : SEGMENTS) {
            for (Map<String, String> r : readCsv(root.resolve("reports/segment_" + seg + ".csv"))) {
                double p = num(r, "base_rate"), fpr = num(r, "FPR");
                double fnr = num(r, "FNR"), ppv = num(r, "precision");
                double odds = fpr * ppv / ((1.0 - fnr) * (1.0 - ppv));
                double implied = odds / (1.0 + odds);
                double d = Math.abs(implied - p);
                worst = Math.max(worst, d);
                if (d > TOL)
                    fail(seg + "/" + r.get("group") + ": FPR, FNR and precision imply a base"
                         + " rate of " + implied + ", the table publishes " + p);
                rows++;
            }
        }
        System.out.printf("  %d published rows solve the identity back to their own base rate,"
                          + " worst residual %.1e%n", rows, worst);

        // 2. The base rates differ, so the constraint bites.
        List<Map<String, String>> pc = readCsv(root.resolve("reports/segment_product_code.csv"));
        double pMin = Double.MAX_VALUE, pMax = 0.0;
        String gMin = "", gMax = "";
        for (Map<String, String> r : pc) {
            double p = num(r, "base_rate");
            if (p < pMin) { pMin = p; gMin = r.get("group"); }
            if (p > pMax) { pMax = p; gMax = r.get("group"); }
        }
        if (!(pMax > pMin))
            fail("product-code base rates are equal, the impossibility would not apply");
        System.out.printf("  product-code base rates run %.4f (%s) to %.4f (%s), a factor of %.3f%n",
                          pMin, gMin, pMax, gMax, pMax / pMin);

        // 3. Equal selection rate and equal FPR together, at the published
        //    targets, would need TPR above 1 somewhere.
        //    selection = p*TPR + (1-p)*FPR, so TPR = FPR + (selection-FPR)/p.
        double s = json(doc, "target_selection"), f = json(doc, "target_fpr");
        String impossibleGroup = null;
        double impossibleTpr = 0.0;
        for (Map<String, String> r : pc) {
            double p = num(r, "base_rate");
            double need = f + (s - f) / p;
            if (need > 1.0 && need > impossibleTpr) {
                impossibleTpr = need;
                impossibleGroup = r.get("group");
            }
        }
        if (impossibleGroup == null)
            fail("no group needs an impossible TPR, so this check proves nothing here");
        else
            System.out.printf("  equalising selection at %.4f%% and FPR at %.4f%% at once would"
                              + " need product %s to catch %.1f%% of its fraud%n",
                              s * 100, f * 100, impossibleGroup, impossibleTpr * 100);

        // 4 and 5. Each policy owns its own criterion in the published table.
        List<Map<String, String>> imp = readCsv(root.resolve("reports/impossibility.csv"));
        Map<String, double[]> spread = new LinkedHashMap<>();  // selection, FPR, threshold spread
        Map<String, Integer> distinctThresholds = new LinkedHashMap<>();
        for (String policy : new String[]{"global threshold", "equal selection rate", "equal FPR"}) {
            double selLo = 1e9, selHi = -1e9, fprLo = 1e9, fprHi = -1e9, thLo = 1e9, thHi = -1e9;
            List<Double> th = new ArrayList<>();
            for (Map<String, String> r : imp) {
                if (!policy.equals(r.get("policy"))) continue;
                double sel = num(r, "selection_rate"), fpr = num(r, "FPR"), t = num(r, "threshold");
                selLo = Math.min(selLo, sel); selHi = Math.max(selHi, sel);
                fprLo = Math.min(fprLo, fpr); fprHi = Math.max(fprHi, fpr);
                thLo = Math.min(thLo, t); thHi = Math.max(thHi, t);
                if (!th.contains(t)) th.add(t);
            }
            spread.put(policy, new double[]{(selHi - selLo) * 100, (fprHi - fprLo) * 100, thHi - thLo});
            distinctThresholds.put(policy, th.size());

            // The spreads audit.json publishes for this policy.
            String block = doc.substring(doc.indexOf("\"" + policy + "\""));
            double wantSel = json(block, "selection_spread_pp");
            double wantFpr = json(block, "FPR_spread_pp");
            double wantTh = json(block, "threshold_spread");
            double[] got = spread.get(policy);
            if (Math.abs(got[0] - wantSel) > 1e-9)
                fail(policy + " selection_spread_pp: recomputed " + got[0] + ", published " + wantSel);
            if (Math.abs(got[1] - wantFpr) > 1e-9)
                fail(policy + " FPR_spread_pp: recomputed " + got[1] + ", published " + wantFpr);
            if (Math.abs(got[2] - wantTh) > 1e-9)
                fail(policy + " threshold_spread: recomputed " + got[2] + ", published " + wantTh);
        }

        double[] gt = spread.get("global threshold");
        double[] es = spread.get("equal selection rate");
        double[] ef = spread.get("equal FPR");
        if (!(es[0] < gt[0] && es[0] < ef[0]))
            fail("the equal selection rate policy does not have the smallest selection spread");
        if (!(ef[1] < gt[1] && ef[1] < es[1]))
            fail("the equal FPR policy does not have the smallest FPR spread");
        if (!(es[1] > gt[1]))
            fail("equalising selection rate did not widen the FPR spread against the shipped"
                 + " policy, so nothing was traded");
        if (!(ef[0] > es[0]))
            fail("equalising FPR did not widen the selection spread against the equal selection"
                 + " rate policy, so nothing was traded");
        if (distinctThresholds.get("global threshold") != 1)
            fail("the global threshold policy uses more than one threshold");
        if (distinctThresholds.get("equal selection rate") < 2
            || distinctThresholds.get("equal FPR") < 2)
            fail("an equalising policy managed a single threshold, which the theorem forbids");

        System.out.printf("  spreads (pp): global sel %.4f FPR %.4f | equal-sel sel %.4f FPR %.4f"
                          + " | equal-FPR sel %.4f FPR %.4f%n",
                          gt[0], gt[1], es[0], es[1], ef[0], ef[1]);

        if (failures > 0) {
            System.out.println("Java: " + failures + " failure(s)");
            System.exit(1);
        }
        System.out.println("Java: the identity closes on every row and the three policies trade"
                           + " against each other exactly as published");
    }
}
