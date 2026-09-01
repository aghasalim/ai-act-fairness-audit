// Does the README still say what the results files say?
//
// Prose goes stale in a way tables do not. Rerun the audit, get a slightly
// different threshold, regenerate reports/, and every figure redraws itself
// while the sentences around them keep the old numbers. Nothing in the repo
// noticed, because nothing in the repo read the README.
//
// This does. Every number the README states about the audit is rebuilt from
// reports/audit.json and reports/segment_*.csv, formatted the way the sentence
// formats it, and then the exact sentence is required to appear in README.md.
// That binds it in both directions: change the data and the sentence stops
// matching, edit the sentence and it stops matching too.
//
// Run with: node verify/readme.js <repo root>

const fs = require("fs");
const path = require("path");

const root = process.argv[2] || ".";
const readmeRaw = fs.readFileSync(path.join(root, "README.md"), "utf8");
// Collapse whitespace so a claim can straddle a line break in the source.
const readme = readmeRaw.replace(/\s+/g, " ");
const audit = JSON.parse(fs.readFileSync(path.join(root, "reports/audit.json"), "utf8"));

function segment(name) {
  const file = path.join(root, `reports/segment_${name}.csv`);
  const [head, ...lines] = fs.readFileSync(file, "utf8").trim().split("\n");
  const cols = head.split(",");
  return lines.map((l) => {
    const cell = l.split(",");
    const row = {};
    cols.forEach((c, i) => {
      const v = cell[i];
      row[c] = c === "group" ? v : Number(v);
    });
    return row;
  });
}

const by = (rows, g) => {
  const r = rows.find((x) => x.group === g);
  if (!r) throw new Error(`no group ${g}`);
  return r;
};
// Whole rows behind a rate, the same reconstruction the C kernel does.
const falseNegatives = (r) => Math.round(r.base_rate * r.n * r.FNR);
const thousands = (x) => x.toLocaleString("en-US");

let failures = 0;
const claims = [];
function claim(why, phrase) {
  claims.push(why);
  if (!readme.includes(phrase)) {
    console.log(`  FAIL ${why}`);
    console.log(`       the results give: ${phrase}`);
    console.log(`       README.md does not contain that sentence`);
    failures++;
  }
}
function assert(why, ok, detail) {
  claims.push(why);
  if (!ok) {
    console.log(`  FAIL ${why}: ${detail}`);
    failures++;
  }
}

const pc = segment("product_code");
const ident = segment("identity_present");
const amt = segment("amount_band");
const S = audit.segments;
const names = Object.keys(S);

// Abstract and section 1.
claim("row count", `on ${thousands(audit.n)} transactions`);
claim("review budget", `under a fixed ${audit.budget * 100}% review budget`);

const failing = names.filter((k) => !S[k].passes_four_fifths).length;
claim(
  "how many segments fail four-fifths",
  `${failing} of the ${names.length} available segments fall below the four-fifths`
);

const worstSeg = names.reduce((a, b) =>
  S[a].disparate_impact_ratio <= S[b].disparate_impact_ratio ? a : b
);
const di = S[worstSeg].disparate_impact_ratio;
claim(
  "the worst disparate impact ratio and which segment holds it",
  `The worst is ${worstSeg.replace("_", " ")} at ${di.toFixed(4)}, which is ` +
    `${Math.round(0.8 / di)} times below the 0.8 line`
);

const nIdent = by(ident, "no");
claim(
  "detection rate where identity is absent",
  `catches **${(nIdent.TPR * 100).toFixed(1)}%** of the fraud in the ` +
    `${Math.round((nIdent.n / audit.n) * 100)}% of transactions without identity data`
);

// Section 3.
claim(
  "the product-code false-positive ratio",
  `${Math.round(S.product_code.FPR_ratio)} times higher for product ` +
    `${S.product_code.worst_FPR_group} than for product ${S.product_code.best_FPR_group}`
);

const brs = pc.map((r) => r.base_rate);
claim(
  "the product-code base rate range",
  `base rates across product codes run from ${(Math.min(...brs) * 100).toFixed(1)}% ` +
    `to ${(Math.max(...brs) * 100).toFixed(1)}%`
);

claim(
  "the false-negative against false-positive gap for product code",
  `${S.product_code.FNR_gap_pp.toFixed(1)} points against ` +
    `${S.product_code.FPR_gap_pp.toFixed(1)} points for product code`
);

const gapRatios = names.map((k) => S[k].FNR_gap_pp / S[k].FPR_gap_pp);
assert(
  "false-negative gaps are an order of magnitude larger in every segment",
  Math.min(...gapRatios) >= 10,
  `the smallest ratio is ${Math.min(...gapRatios).toFixed(1)}x`
);

claim(
  "the size of the group with no identity record",
  `**${thousands(nIdent.n)} rows, ${Math.round((nIdent.n / audit.n) * 100)}% of volume**`
);
claim(
  "its false-positive rate against the group with identity",
  `false-positive rate of ${nIdent.FPR.toFixed(4)}, ` +
    `${Math.round(S.identity_present.FPR_ratio)} times lower than where identity is present`
);
assert(
  "it really is the lower of the two identity groups",
  nIdent.FPR === S.identity_present.FPR_min,
  `${nIdent.FPR} is not ${S.identity_present.FPR_min}`
);

const yIdent = by(ident, "yes");
claim(
  "detection with and without identity",
  `catches **${(nIdent.TPR * 100).toFixed(1)}%** of the fraud there against ` +
    `${(yIdent.TPR * 100).toFixed(1)}% where identity is present`
);
claim(
  "fraud missed where identity is absent",
  `so **${thousands(falseNegatives(nIdent))}** frauds go through`
);
claim(
  "fraud missed where identity is present",
  `than the ${thousands(falseNegatives(yIdent))} missed in the segment`
);

// The amount band table.
const q1 = by(amt, "Q1 lowest");
const q4 = by(amt, "Q4 highest");
claim(
  "the amount-band base rates",
  `| base fraud rate | ${(q1.base_rate * 100).toFixed(2)}% | ${(q4.base_rate * 100).toFixed(2)}% |`
);
claim(
  "the amount-band detection rates",
  `| **TPR** | **${(q1.TPR * 100).toFixed(1)}%** | **${(q4.TPR * 100).toFixed(1)}%** |`
);
claim(
  "the amount-band fraud missed",
  `| fraud missed | ${thousands(falseNegatives(q1))} | **${thousands(falseNegatives(q4))}** |`
);
assert(
  "Q1 and Q4 really do have near-identical base rates",
  Math.abs(q1.base_rate - q4.base_rate) * 100 < 0.5,
  `they differ by ${(Math.abs(q1.base_rate - q4.base_rate) * 100).toFixed(2)} points`
);
assert(
  "Q4 detection really is close to half of Q1",
  q1.TPR / q4.TPR > 1.9 && q1.TPR / q4.TPR < 2.1,
  `the ratio is ${(q1.TPR / q4.TPR).toFixed(3)}`
);

// Section 4, the impossibility.
const P = audit.impossibility.policies;
claim(
  "the spread the shipped policy leaves",
  `leaves a **${P["global threshold"].selection_spread_pp.toFixed(2)}pp** spread in selection rate`
);
claim(
  "what equalising selection rate costs",
  `closes that to ${P["equal selection rate"].selection_spread_pp.toFixed(2)}pp but more than ` +
    `doubles the false-positive spread, ${P["global threshold"].FPR_spread_pp.toFixed(2)}pp ` +
    `to **${P["equal selection rate"].FPR_spread_pp.toFixed(2)}pp**`
);
assert(
  "equalising selection rate really does more than double the false-positive spread",
  P["equal selection rate"].FPR_spread_pp / P["global threshold"].FPR_spread_pp > 2,
  `the factor is ${(P["equal selection rate"].FPR_spread_pp / P["global threshold"].FPR_spread_pp).toFixed(3)}`
);
claim(
  "what equalising false-positive rate costs",
  `closes that gap to ${P["equal FPR"].FPR_spread_pp.toFixed(2)}pp and opens a ` +
    `${P["equal FPR"].selection_spread_pp.toFixed(2)}pp selection spread instead`
);
assert(
  "both equalising policies need more than one threshold",
  !P["equal FPR"].same_score_same_decision &&
    !P["equal selection rate"].same_score_same_decision &&
    P["global threshold"].same_score_same_decision,
  "the same_score_same_decision flags do not match the README's claim"
);

if (failures > 0) {
  console.log(`Node: ${failures} of ${claims.length} README claims do not match the results`);
  process.exit(1);
}
console.log(
  `Node: ${claims.length} numeric claims in README.md rebuilt from reports/ and found ` +
    `word for word in the prose`
);
