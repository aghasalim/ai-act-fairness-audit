# Methods and detail

Long form detail moved out of the README.


## 3. What the audit found


![every segment against the four-fifths rule](../reports/figures/four-fifths.png)

![false-positive and false-negative gaps](../reports/figures/error-gaps.png)

The second figure is the one that changed how I read the first. Selection-rate
parity says nothing about who bears the errors, and the false-negative gap is an
order of magnitude larger in every segment.

![the worst segment, group by group](../reports/figures/worst-segment.png)

![calibration by group across every segment](../reports/figures/calibration.png)

Measured at a **1% alert budget**: one global threshold flagging 1% of
transactions, because that is how a review queue works. Parity measured at
p>0.5, where almost nothing is flagged, would report near-perfect fairness for a
model nobody uses that way.

| segment | FPR ratio | worst | best | four-fifths |
|---|---|---|---|---|
| product code | **793×** | C | W | fails |
| device type | 92× | mobile | unknown | fails |
| identity present | 90× | yes | no | fails |
| region | 52× | other | 87 | fails |
| email class | 7.6× | free webmail | missing | fails |
| card type | 5.0× | credit | debit | fails |
| amount band | 4.4× | Q1 lowest | Q2 | fails |

Every segment fails the four-fifths rule. **I do not think that means what it
looks like**, and saying so is the difference between an audit and an
accusation: selection rates track base rates, which genuinely differ 5.7× across
these groups. A single-threshold ranker mechanically flags more of the groups
that offend more. Most of this table is arithmetic, not discrimination.

Two findings survive that objection.


### The group treated "best" is the one the model fails


Transactions with no identity record, **361,483 rows, 82% of volume**: have
the *lowest* false-positive rate of any segment, 0.0001. On an FPR-only audit
they look like the best-served group in the dataset.

| | identity present | no identity |
|---|---|---|
| n | 81,422 | **361,483** |
| base fraud rate | 11.1% | 2.1% |
| FPR | 0.0061 | **0.0001** |
| **TPR (fraud caught)** | 42.6% | **1.4%** |
| fraud missed | 5,187 | **7,626** |

They are not well served. They are **unpoliced**: the model essentially never
flags them, so it neither wrongly blocks them nor catches the 7,626 frauds they
carry, more absolute fraud than the segment it works on. Low FPR here is a
symptom of a model that has nothing to say about 82% of its traffic.

An audit reporting only false positives, the standard framing, since FPs are
the harm to the innocent, would have called this the fairest segment.


## 4. The impossibility, measured rather than cited


![three fairness policies, each breaking the other two](../reports/figures/impossibility.png)

Equal selection rates, equal false-positive rates, and a calibrated score cannot
hold together when base rates differ. That is a theorem
(Kleinberg et al. 2016; Chouldechova 2017), and it is usually where the
conversation stops. Base rates here differ 5.7×, so it is a live constraint
so I built all three deployable policies and measured what each costs:

| policy | selection spread | FPR spread | same score → same decision? |
|---|---|---|---|
| one global threshold | 6.74pp | 0.91pp | **yes** |
| equal selection rate | **0.01pp** | 2.21pp | no |
| equal FPR | 3.26pp | **0.01pp** | no |

Equalising selection rates **more than doubles** the FPR gap (0.91 → 2.21pp)
the intuitive fix makes the harm-to-innocents disparity worse. And both
equalising policies require different thresholds per group, so an identical
score produces a different decision depending on which group you fall in.

There is no fair row. Choosing between them is a policy decision about who
absorbs the error, and the Regulation does not make it for you, Article
10(2)(f) requires that you *examine* it, not that you land anywhere particular.

---
