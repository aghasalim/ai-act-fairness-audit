# Auditing my own fraud model against the EU AI Act

[![ci](https://github.com/aghasalim/ai-act-fairness-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/aghasalim/ai-act-fairness-audit/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A fairness audit of the LightGBM fraud model from
[ieee-fraud-ml](https://github.com/aghasalim/ieee-fraud-ml), against the text of
Regulation (EU) 2024/1689 from
[eu-ai-act-rag](https://github.com/aghasalim/eu-ai-act-rag). Auditing my own
model, using my own corpus of the law, so nobody grades the homework but the
primary source.

Predictions are the honest ones, chronological folds, 30-day embargo,
fold-local encodings. Auditing a leaky split would measure the leak.

---


---

## Abstract

The EU AI Act obliges providers of high-risk systems to assess discriminatory
impact. This work audits a fraud-detection model I built myself, on 442,905
transactions, under a fixed 1% review budget, so the threshold is
the operational one rather than one chosen to make the audit look good.

7 of the 7 available segments fall below the four-fifths disparate-impact
threshold. The worst is product code at 0.0012, which is 661 times below the
0.8 line. More usefully, selection-rate parity turns out to be the wrong thing
to look at: false-negative gaps are an order of magnitude larger than
false-positive gaps in every segment, and it is the false negative a customer
experiences.

The impossibility result is measured on this model rather than cited. Equalising
selection rate, equalising false-positive rate and holding a single global
threshold are three policies; each satisfies its own criterion and breaks the
other two, because the groups have different base rates. Choosing between them is
a decision about who bears which error, and no amount of tuning removes it.

The audit's own limitation is stated up front: none of the available segments is a
protected characteristic under the Act. Card type and device type are proxies at
best, so this demonstrates the machinery rather than discharging the obligation.

**Contributions.** (i) An audit at the operational review budget. (ii) Error-rate
gaps reported alongside selection-rate parity. (iii) The impossibility theorem
instantiated on a real model. (iv) A stated scope limit about what the available
segments can and cannot support.

---

## 1. I started from a premise that turned out to be false

I began this convinced that fraud scoring is a textbook Annex III high-risk
system. It is not. **Annex III, point 5(b)** covers creditworthiness scoring
**"with the exception of AI systems used for the purpose of detecting financial
fraud"**.

Fraud detection is expressly carved out. This model is not high-risk, Article
10's bias-examination duty does not bind it, and **this audit was never legally
required**.

Which makes the result more interesting than compliance paperwork. A model that
blocks legitimate customers at **793× different rates** across product lines,
and catches **1.4%** of the fraud in the 82% of transactions without identity
data, passes through the Regulation's high-risk net untouched.

I am not claiming the carve-out is a mistake, anti-fraud has an obvious
rationale, since explaining detection to the people being detected defeats it.
The narrower point is that **"not high-risk" describes a regulatory category,
not whether anyone is harmed.** A false positive is a declined card for a real
person regardless of which annex applies.

---

## 2. The limitation that decides what this audit can conclude

**IEEE-CIS contains no protected attributes.** No race, sex, age or nationality.
So every segment below is a *proxy*, debit vs credit, free webmail vs
corporate, mobile vs desktop, transaction size.

Proxies can prove error is distributed unevenly. They **cannot** tell you whether
that unevenness tracks a protected characteristic. You cannot audit an attribute
you never collected, and no method repairs that.

The Act anticipates exactly this. **Article 10(5)** lets providers process
special-category data *specifically for bias detection*, gated on the test that
"bias detection and correction cannot be effectively fulfilled by processing
other data". It treats not-knowing as a problem to solve rather than a defence
which is the opposite of how "we don't collect race" is usually deployed in an
argument. Full mapping in **[docs/ai_act_mapping.md](docs/ai_act_mapping.md)**.

---

## 3. What the audit found

At the 1% alert budget all seven segments fail the four-fifths rule, and the
worst is product code, where the false-positive rate runs 793 times higher for
product C than for product W. Most of that is arithmetic rather than
discrimination: one global threshold flags more of the groups that offend more,
and base rates across product codes run from 2.1% to 12.8%. The second figure
is the one that changed how I read the first. False-negative gaps are an order
of magnitude larger than false-positive gaps in every segment, 46.2 points
against 0.9 points for product code.

![every segment against the four-fifths rule](reports/figures/four-fifths.png)
![false-positive and false-negative gaps](reports/figures/error-gaps.png)
![the worst segment, group by group](reports/figures/worst-segment.png)
![calibration by group across every segment](reports/figures/calibration.png)

Full detail in [notes/METHODS.md](notes/METHODS.md#3-what-the-audit-found).
### The group treated "best" is the one the model fails
Transactions with no identity record, **361,483 rows, 82% of volume**: have a
false-positive rate of 0.0001, 90 times lower than where identity is present.
That looks like the best-served group in the data and it is not. The model
catches **1.4%** of the fraud there against 42.6% where identity is present, so
**7,626** frauds go through, more in absolute terms than the 5,187 missed in the
segment the model actually works on. The low false-positive rate is a model with nothing to say
about 82% of its traffic.

Full detail in [notes/METHODS.md](notes/METHODS.md#the-group-treated-best-is-the-one-the-model-fails).
### At matched base rates, high-value fraud is missed twice as often

Amount quartiles Q1 and Q4 have near-identical fraud rates, so base-rate
arithmetic cannot explain a gap between them:

| | Q1 lowest | Q4 highest |
|---|---|---|
| base fraud rate | 4.62% | 4.78% |
| **TPR** | **34.3%** | **17.1%** |
| fraud missed | 3,385 | **4,313** |

Same prevalence, half the detection. The model is markedly worse at the
transactions that cost the most when missed.

---

## 4. The impossibility, measured rather than cited

Equal selection rates, equal false-positive rates, and a calibrated score cannot
hold together when base rates differ. I built all three policies on product code
and measured what each one costs. One global threshold leaves a **6.74pp**
spread in selection rate; equalising selection rate closes that to 0.01pp but
more than doubles the false-positive spread, 0.91pp to **2.21pp**; equalising
false-positive rate closes that gap to 0.01pp and opens a 3.26pp selection
spread instead. Both equalising policies need a different threshold per group,
so the same score gets a different decision depending on which group you are in.

![three fairness policies, each breaking the other two](reports/figures/impossibility.png)

Full detail in [notes/METHODS.md](notes/METHODS.md#4-the-impossibility-measured-rather-than-cited).
## 5. Running it

```bash
make setup && make audit
```

`make audit` needs `data/scored.parquet`. Regenerate it from a checkout of the
model repo:

```bash
FRAUD_REPO=~/ieee-fraud-ml make export
```

Row-level predictions are gitignored, IEEE-CIS is not redistributable, so this
repo commits aggregate results only. `make test` runs without any of it.

## 6. Everything here is computed at least twice

Every number above came out of one pandas implementation in `src/auditor`. The
tables, the figures and the sentences all read that same output, so if
`disparity()` had divided by the wrong denominator, or `group_metrics()` had
swapped FPR and FNR, nothing in the repo would have noticed. `tests/` checks the
metric functions on small hand-built cases. It does not check the numbers this
README publishes.

So those numbers are recomputed by seven programs in seven other languages, none
of which share code with the audit or with each other. `verify/verify.sh` runs
them all, skips a language whose toolchain is missing, and exits non-zero if any
of them disagrees. CI runs it, then corrupts a false-positive rate in
`reports/segment_product_code.csv` and requires the suite to reject it.

The rawest thing this repo can commit is the segment tables, because IEEE-CIS is
not redistributable and row-level predictions stay local. That turns out to be
enough. Every rate in those tables is a ratio of whole rows, so the integer
confusion matrix behind it can be recovered exactly, and the rest follows from
those integers.

| language | file | what it recomputes, and from what | measured agreement |
|---|---|---|---|
| SQL | `verify/summary.sql` | all 77 numeric fields of `reports/audit.json` from the seven segment tables, plus the extreme group names, the four-fifths verdicts and the two impossibility targets | worst relative residual 0.0e+00, tolerance 1e-9 |
| C | `verify/kernel.c` | the integer confusion matrix behind every published rate, then every rate back out of the integers | worst residual 0.0e+00, tolerance 1e-12 |
| Java | `verify/Impossibility.java` | Chouldechova's identity on all 23 published group rows, and the three policy spreads in `reports/impossibility.csv` | worst residual 2.4e-16 on the identity, spreads agree to 1e-9 |
| Go | `verify/gocheck/` | the structure of all 8 results files, and the three impossibility fields no other check owns | 8 files well formed, fraud caught 3962 / 4136 / 3273, exact |
| R | `verify/inference.R` | exact Clopper-Pearson intervals on the four-fifths verdict, and whether the extreme FPR pairs separate | best case for the model 0.3696, still under 0.8; largest p 3.2e-17 |
| Rust | `verify/resample/` | 200,000 binomial replicates of the whole audit per segment, 9,200,000 draws, no crates | product code 0.0012 sits in [0.0005, 0.0020] at 99.9%; 0 of 200,000 replicates in any segment pass four-fifths |
| JavaScript | `verify/readme.js` | the 25 numeric claims in this README, rebuilt from `reports/` and required to appear word for word | all 25 match |

The C kernel also does something the Python never did. The seven segment tables
are seven different partitions of the same transactions, so once the counts are
recovered they have to agree on the totals. They do: **442,905 rows, 16,775
frauds, 4,430 flagged, 3,962 true positives and 468 false positives**, from all
seven independently. A grouping bug in any one of them would show up here.

Each check was then tested by corrupting the file it reads and confirming it
fails. That is what caught the one real error this found. An earlier draft of
section 3 called the identity-absent group the lowest false-positive rate of any
segment; product code W is lower, so the JavaScript check would not match, and
the sentence is now the 90x comparison the data actually supports. SQL and Rust
both tie `audit.json` to the segment tables. SQL does it exactly, Rust adds the
sampling interval the Python never computed.

## 7. Limitations

- **No claim about protected attributes.** See above; the data has none.
- **No mitigation shipped as a recommendation.** The impossibility table shows
  the options and their costs; picking one is a business decision I am not in a
  position to make on someone's behalf.
- **No causal claim.** These are associations between segment membership and
  error rates. Whether the model *causes* the disparity, or inherits it from how
  the data was collected, is not answerable from this dataset.

## 8. Licence

MIT, see [LICENSE](LICENSE). Quoted provisions of Regulation (EU) 2024/1689 are
official EU legal texts.

## References

The papers and sources this implementation follows. Each one is here because
the code uses the method, the dataset or the metric it describes.

- **Hardt, Price, Srebro. Equality of Opportunity in Supervised Learning. NeurIPS 2016.** [arXiv:1610.02413](https://arxiv.org/abs/1610.02413) equalised odds and equal opportunity.
- **Feldman, Friedler, Moeller, Scheidegger, Venkatasubramanian. Certifying and removing disparate impact. KDD 2015.** [arXiv:1412.3756](https://arxiv.org/abs/1412.3756) the disparate impact ratio.
- **Chouldechova. Fair prediction with disparate impact. Big Data 5, 2017.** [arXiv:1610.07524](https://arxiv.org/abs/1610.07524) why several fairness criteria cannot hold at once.
- **Regulation (EU) 2024/1689 of the European Parliament and of the Council, the AI Act.** the obligations the audit is written against.
