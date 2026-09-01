//! How much of the audit is sampling noise?
//!
//! The disparate impact ratio for product code is 0.0012, and the README calls
//! that 661 times below the four-fifths line. It rests on 29 flagged rows out
//! of 355,414 for product W. A point estimate built on 29 events can move a
//! long way, and the Python never resampled anything: it reported the ratio it
//! computed once and stopped.
//!
//! This draws the whole audit again, many times. Each published row is a
//! binomial: `flagged ~ Bin(n, selection_rate)` and `FP ~ Bin(negatives, FPR)`,
//! with the counts recovered from the published rates. Every replicate gives a
//! fresh disparate impact ratio and false-positive ratio per segment, and the
//! interval over replicates says how firm the published numbers are.
//!
//! Two things are then required to hold:
//!   1. no replicate, in any segment, passes the four-fifths rule,
//!   2. the ratio audit.json publishes falls inside the resampled interval,
//!      which ties the JSON to the tables through the sampling distribution
//!      rather than through a single division.
//!
//! No crates. The generator is xorshift64*, seeded fixed so the run is
//! reproducible, and the binomial sampler is exact inversion walking out from
//! the mode rather than a normal approximation, because some of these counts
//! are far too small for that.

use std::env;
use std::fs;
use std::process::exit;

const REPLICATES: usize = 200_000;
const SEED: u64 = 0x5EED_A17_FA12_C0DE;

const SEGMENTS: [&str; 7] = [
    "amount_band", "card_type", "device_type", "email_class",
    "identity_present", "product_code", "region",
];

struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Self {
        Rng(if seed == 0 { 1 } else { seed })
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    /// Uniform in (0,1), never exactly 0 or 1.
    fn uniform(&mut self) -> f64 {
        ((self.next_u64() >> 11) as f64 + 0.5) * (1.0 / 9007199254740992.0)
    }
}

/// Lanczos log-gamma, enough precision for a binomial pmf.
fn ln_gamma(x: f64) -> f64 {
    const G: [f64; 9] = [
        0.999_999_999_999_809_93,
        676.520_368_121_885_1,
        -1259.139_216_722_402_8,
        771.323_428_777_653_13,
        -176.615_029_162_140_6,
        12.507_343_278_686_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    let x = x - 1.0;
    let mut a = G[0];
    let t = x + 7.5;
    for (i, g) in G.iter().enumerate().skip(1) {
        a += g / (x + i as f64);
    }
    0.5 * (2.0 * std::f64::consts::PI).ln() + (x + 0.5) * t.ln() - t + a.ln()
}

/// Exact binomial draw by inversion, enumerating outward from the mode so the
/// cost is proportional to the standard deviation rather than to n.
fn binomial(rng: &mut Rng, n: u64, p: f64) -> u64 {
    if p <= 0.0 || n == 0 {
        return 0;
    }
    if p >= 1.0 {
        return n;
    }
    let nf = n as f64;
    let mode = (((nf + 1.0) * p).floor() as u64).min(n);
    let k = mode as f64;
    let ln_pmf_mode = ln_gamma(nf + 1.0) - ln_gamma(k + 1.0) - ln_gamma(nf - k + 1.0)
        + k * p.ln()
        + (nf - k) * (1.0 - p).ln();
    let pmf_mode = ln_pmf_mode.exp();

    let u = rng.uniform();
    let mut acc = pmf_mode;
    if acc >= u {
        return mode;
    }
    // Walk down and up alternately. Any fixed enumeration order of the support
    // makes inversion valid; this one converges in O(sd) steps.
    let ratio = p / (1.0 - p);
    let (mut down, mut up) = (mode, mode);
    let (mut pd, mut pu) = (pmf_mode, pmf_mode);
    loop {
        let mut moved = false;
        if down > 0 {
            pd *= (down as f64) / (nf - down as f64 + 1.0) / ratio;
            down -= 1;
            acc += pd;
            moved = true;
            if acc >= u {
                return down;
            }
        }
        if up < n {
            pu *= (nf - up as f64) / (up as f64 + 1.0) * ratio;
            up += 1;
            acc += pu;
            moved = true;
            if acc >= u {
                return up;
            }
        }
        if !moved {
            return mode; // support exhausted, rounding took the last of the mass
        }
    }
}

struct Group {
    n: u64,
    negatives: u64,
    selection_rate: f64,
    fpr: f64,
}

fn column(header: &[&str], name: &str) -> usize {
    header
        .iter()
        .position(|h| *h == name)
        .unwrap_or_else(|| {
            eprintln!("  FAIL column {name} is missing");
            exit(1)
        })
}

fn read_segment(root: &str, seg: &str) -> Vec<Group> {
    let path = format!("{root}/reports/segment_{seg}.csv");
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        eprintln!("  FAIL cannot read {path}: {e}");
        exit(1)
    });
    let mut lines = text.lines().filter(|l| !l.trim().is_empty());
    let header: Vec<&str> = lines.next().unwrap().split(',').collect();
    let (c_n, c_br) = (column(&header, "n"), column(&header, "base_rate"));
    let c_sel = column(&header, "selection_rate");
    let c_fpr = column(&header, "FPR");
    lines
        .map(|l| {
            let f: Vec<&str> = l.split(',').collect();
            let n: u64 = f[c_n].parse().expect("n is not an integer");
            let br: f64 = f[c_br].parse().expect("base_rate is not a number");
            let positives = (br * n as f64).round() as u64;
            Group {
                n,
                negatives: n - positives,
                selection_rate: f[c_sel].parse().expect("selection_rate"),
                fpr: f[c_fpr].parse().expect("FPR"),
            }
        })
        .collect()
}

/// One numeric field out of audit.json, by dotted-ish name, without a parser.
fn published_ratio(doc: &str, seg: &str, field: &str) -> f64 {
    let at = doc
        .find(&format!("\"{seg}\""))
        .unwrap_or_else(|| { eprintln!("  FAIL audit.json has no segment {seg}"); exit(1) });
    let rest = &doc[at..];
    let at = rest
        .find(&format!("\"{field}\""))
        .unwrap_or_else(|| { eprintln!("  FAIL audit.json has no {seg}.{field}"); exit(1) });
    let rest = &rest[at + field.len() + 2..];
    let start = rest.find(':').unwrap() + 1;
    let value: String = rest[start..]
        .trim_start()
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == '.' || *c == 'e' || *c == '-' || *c == '+')
        .collect();
    value.parse().unwrap_or_else(|_| {
        eprintln!("  FAIL {seg}.{field} is not a number: {value}");
        exit(1)
    })
}

fn percentile(sorted: &[f64], q: f64) -> f64 {
    let i = ((sorted.len() - 1) as f64 * q).round() as usize;
    sorted[i]
}

fn main() {
    let root = env::args().nth(1).unwrap_or_else(|| ".".to_string());
    let doc = fs::read_to_string(format!("{root}/reports/audit.json"))
        .unwrap_or_else(|e| { eprintln!("  FAIL cannot read audit.json: {e}"); exit(1) });

    let mut rng = Rng::new(SEED);
    let mut failures = 0usize;
    let mut draws = 0u64;

    for seg in SEGMENTS {
        let groups = read_segment(&root, seg);
        let mut di = Vec::with_capacity(REPLICATES);
        let mut fpr_ratio = Vec::with_capacity(REPLICATES);
        let mut passes = 0usize;
        let mut zero_fpr = 0usize;

        for _ in 0..REPLICATES {
            let (mut sel_lo, mut sel_hi) = (f64::INFINITY, 0.0f64);
            let (mut fpr_lo, mut fpr_hi) = (f64::INFINITY, 0.0f64);
            for g in &groups {
                let flagged = binomial(&mut rng, g.n, g.selection_rate) as f64 / g.n as f64;
                let fp = binomial(&mut rng, g.negatives, g.fpr) as f64 / g.negatives as f64;
                draws += 2;
                sel_lo = sel_lo.min(flagged);
                sel_hi = sel_hi.max(flagged);
                fpr_lo = fpr_lo.min(fp);
                fpr_hi = fpr_hi.max(fp);
            }
            let r = if sel_hi > 0.0 { sel_lo / sel_hi } else { 1.0 };
            if r >= 0.8 {
                passes += 1;
            }
            di.push(r);
            if fpr_lo > 0.0 {
                fpr_ratio.push(fpr_hi / fpr_lo);
            } else {
                zero_fpr += 1;
                fpr_ratio.push(f64::INFINITY);
            }
        }

        di.sort_by(|a, b| a.partial_cmp(b).unwrap());
        fpr_ratio.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let (lo, hi) = (percentile(&di, 0.0005), percentile(&di, 0.9995));
        let published = published_ratio(&doc, seg, "disparate_impact_ratio");
        let (flo, fhi) = (percentile(&fpr_ratio, 0.025), percentile(&fpr_ratio, 0.975));
        let published_fpr = published_ratio(&doc, seg, "FPR_ratio");

        if passes > 0 {
            println!("  FAIL {seg}: {passes} of {REPLICATES} replicates pass four-fifths");
            failures += 1;
        }
        if published < lo || published > hi {
            println!("  FAIL {seg}: audit.json publishes a disparate impact ratio of {published}, \
                      outside the resampled 99.9% band [{lo:.6}, {hi:.6}]");
            failures += 1;
        }
        if published_fpr < flo || published_fpr > fhi {
            println!("  FAIL {seg}: audit.json publishes an FPR ratio of {published_fpr:.4}, \
                      outside the resampled 95% band [{flo:.4}, {fhi:.4}]");
            failures += 1;
        }
        if flo <= 1.0 {
            println!("  FAIL {seg}: the false-positive ratio is not distinguishable from 1, \
                      lower bound {flo:.4}");
            failures += 1;
        }

        // The best group's false-positive rate can resample to zero, which
        // sends the ratio to infinity. Say so rather than printing inf.
        let upper = if fhi.is_finite() {
            format!("{fhi:.1}")
        } else {
            format!("unbounded, {zero_fpr} replicates had a group with no false positives")
        };
        println!(
            "  {seg:<17} DI {published:.5} in [{lo:.5}, {hi:.5}] (99.9%), \
             FPR ratio {published_fpr:.1} at least {flo:.1} (95%, upper {upper}), \
             {passes} of {REPLICATES} replicates pass four-fifths"
        );
    }

    if failures > 0 {
        println!("Rust: {failures} failure(s)");
        exit(1);
    }
    println!(
        "Rust: {} binomial draws over {} replicates per segment, seed {:#x}; \
         no replicate in any segment reaches four-fifths",
        draws, REPLICATES, SEED
    );
}
