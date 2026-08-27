# What the AI Act actually requires of this model

Quotations are from Regulation (EU) 2024/1689, taken from the official
Publications Office XHTML via the corpus in
[eu-ai-act-rag](https://github.com/aghasalim/eu-ai-act-rag).

## The finding that reframed this audit: the model is not high-risk

I started this expecting fraud scoring to be a textbook Annex III high-risk
system. It is not. **Annex III, point 5(b):**

> AI systems intended to be used to evaluate the creditworthiness of natural
> persons or establish their credit score, **with the exception of AI systems
> used for the purpose of detecting financial fraud**

Fraud detection is *expressly excluded*. A transaction-fraud model is not made
high-risk by 5(b), and it is not captured by another Annex III point either
it does not decide access to essential services, employment, education, law
enforcement or migration.

So the obligations everyone reaches for do not bind this system through that
route.

## Which means Article 10 does not apply here, and that is the point

Had it been high-risk, **Article 10(2)(f),(g)** would require:

> (f) examination in view of possible biases that are likely to affect the
> health and safety of persons, have a negative impact on fundamental rights or
> lead to discrimination prohibited under Union law […]
> (g) appropriate measures to detect, prevent and mitigate possible biases
> identified according to point (f)

That is exactly the examination in this repo. Nothing compelled it. A model that
blocks legitimate customers at **793× different rates** across product lines,
and catches **1.4%** of fraud for the 82% of transactions lacking identity data,
would pass through the Regulation's high-risk net untouched.

I am not arguing the carve-out is wrong. Anti-fraud has an obvious rationale:
disclosing how detection works helps the people you are detecting, and the
Regulation elsewhere treats fraud prevention as a legitimate interest. The
narrower observation is that **"not high-risk" is a statement about regulatory
category, not about whether anyone is harmed**, and a false positive is a
declined transaction for a real person either way.

## Article 10(5): why "we have no protected attributes" is not a defence

The Act anticipates the exact obstacle this audit hit. **Article 10(5)** permits
providers of high-risk systems to process special-category data, race, health,
and so on, specifically *for bias detection*:

> the providers of such systems may exceptionally process special categories of
> personal data, subject to appropriate safeguards […] all the following
> conditions must be met […] (a) the bias detection and correction cannot be
> effectively fulfilled by processing other data, including synthetic or
> anonymised data

Read that carefully, because it inverts the usual excuse. The default answer to
"is this model biased on race?" is "we do not collect race, so we cannot know."
The Regulation treats not-knowing as a problem to be solved rather than a
shield, and opens a lawful route to measuring it, gated on the honest test in
(a): you may only reach for sensitive data if proxies genuinely cannot do the
job.

This audit lives entirely on the wrong side of that gate. IEEE-CIS has no race,
sex, age or nationality, so every segment here is a **proxy**: debit versus
credit, free webmail versus corporate, mobile versus desktop. Proxies can
demonstrate that error is distributed unevenly. They cannot tell you whether the
uneven distribution tracks a protected characteristic. **You cannot audit an
attribute you never collected**, and no amount of method fixes that.

## What still applies regardless

- **GDPR Article 22**: solely automated decisions producing legal or similarly
  significant effects. A declined transaction plausibly qualifies; that duty is
  unaffected by the AI Act's classification.
- **Article 15** (accuracy, robustness) and the transparency duties bite only
  once a system *is* high-risk, which this one is not.
- **Article 6(3)** lets a provider of an otherwise-Annex-III system argue it
  poses no significant risk, irrelevant here, since the carve-out already
  settles it, but it is the other route to the same place.

## Honest summary

| question | answer |
|---|---|
| High-risk under Annex III? | **No**: 5(b) excludes fraud detection |
| Does Art. 10 bias examination bind it? | No |
| Was this audit legally required? | **No** |
| Did it find substantial disparities anyway? | **Yes**: see [RESULTS](../README.md) |
| Can it establish bias on protected attributes? | **No**: none are collected |
