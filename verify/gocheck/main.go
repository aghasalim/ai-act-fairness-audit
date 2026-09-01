// Structural validation of every results file the repo publishes, plus an
// independent recomputation of the impossibility summary.
//
// The other checks in verify/ all assume the CSVs parse into the shape they
// expect. This one does not assume it. It reads every file in reports/ as raw
// text and rejects a ragged row, a duplicate column name, an empty cell, a
// non-finite number, a rate outside [0,1], a non-positive group size, a
// segment in audit.json with no table behind it, or a table with no entry in
// audit.json. A results file that has quietly become malformed is a failure
// here before anything downstream gets a chance to average it away.
//
// It then recomputes the three fields of the impossibility summary that no
// other check owns: the TPR spread, whether the policy uses one threshold, and
// the absolute count of fraud each policy catches.
//
// Run with: go run . -root /path/to/repo
package main

import (
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

// Columns that are rates and must lie in [0,1].
var rateCols = map[string]bool{
	"base_rate": true, "selection_rate": true, "TPR": true, "FPR": true,
	"FNR": true, "precision": true, "AUC": true, "mean_pred": true,
	"threshold": true, "mean_pred_flagged": true,
}

type table struct {
	head []string
	rows []map[string]string
}

var failures int

func fail(format string, a ...any) {
	fmt.Printf("  FAIL "+format+"\n", a...)
	failures++
}

func load(path string) (*table, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = 0 // enforce a constant field count
	recs, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(recs) < 2 {
		return nil, fmt.Errorf("fewer than two lines")
	}
	head := recs[0]
	seen := map[string]bool{}
	for _, h := range head {
		if h == "" {
			return nil, fmt.Errorf("a column has an empty name")
		}
		if seen[h] {
			return nil, fmt.Errorf("duplicate column %q", h)
		}
		seen[h] = true
	}
	t := &table{head: head}
	for _, rec := range recs[1:] {
		row := map[string]string{}
		for i, h := range head {
			row[h] = rec[i]
		}
		t.rows = append(t.rows, row)
	}
	return t, nil
}

func (t *table) num(row map[string]string, col string) float64 {
	v, err := strconv.ParseFloat(row[col], 64)
	if err != nil {
		fail("column %s does not parse as a number: %q", col, row[col])
		return math.NaN()
	}
	return v
}

// validate checks the shape of one results table.
func validate(name string, t *table) {
	for i, row := range t.rows {
		for _, h := range t.head {
			if row[h] == "" {
				fail("%s row %d: column %s is empty", name, i+1, h)
				continue
			}
			v, err := strconv.ParseFloat(row[h], 64)
			if err != nil {
				continue // a label column, not a number
			}
			if math.IsNaN(v) || math.IsInf(v, 0) {
				fail("%s row %d: %s is %s", name, i+1, h, row[h])
			}
			if rateCols[h] && (v < 0 || v > 1) {
				fail("%s row %d: %s is %v, outside [0,1]", name, i+1, h, v)
			}
			if h == "n" && v < 1 {
				fail("%s row %d: n is %v", name, i+1, v)
			}
		}
	}
}

type summary struct {
	N            int `json:"n"`
	Segments     map[string]struct {
		NGroups int `json:"n_groups"`
	} `json:"segments"`
	Impossibility struct {
		Policies map[string]struct {
			TPRSpreadPP  float64 `json:"TPR_spread_pp"`
			SameDecision bool    `json:"same_score_same_decision"`
			FraudCaught  int     `json:"fraud_caught"`
		} `json:"policies"`
	} `json:"impossibility"`
}

func main() {
	root := flag.String("root", ".", "repository root")
	flag.Parse()

	raw, err := os.ReadFile(filepath.Join(*root, "reports/audit.json"))
	if err != nil {
		fmt.Println("  FAIL cannot read reports/audit.json:", err)
		os.Exit(1)
	}
	var s summary
	if err := json.Unmarshal(raw, &s); err != nil {
		fmt.Println("  FAIL reports/audit.json does not parse:", err)
		os.Exit(1)
	}

	// Every results file, structurally.
	paths, _ := filepath.Glob(filepath.Join(*root, "reports/*.csv"))
	sort.Strings(paths)
	if len(paths) == 0 {
		fail("no results files found under reports/")
	}
	tables := map[string]*table{}
	for _, p := range paths {
		name := filepath.Base(p)
		t, err := load(p)
		if err != nil {
			fail("%s: %v", name, err)
			continue
		}
		tables[name] = t
		validate(name, t)
		fmt.Printf("  %-32s %d columns, %d rows\n", name, len(t.head), len(t.rows))
	}

	// Every segment in the JSON has a table, and the group counts agree.
	for seg, v := range s.Segments {
		name := "segment_" + seg + ".csv"
		t, ok := tables[name]
		if !ok {
			fail("audit.json reports segment %s with no %s behind it", seg, name)
			continue
		}
		if len(t.rows) != v.NGroups {
			fail("%s has %d rows, audit.json says %d groups", name, len(t.rows), v.NGroups)
		}
		total := 0
		for _, row := range t.rows {
			n, err := strconv.Atoi(row["n"])
			if err != nil {
				fail("%s: n is not an integer: %q", name, row["n"])
				continue
			}
			total += n
		}
		if total != s.N {
			fail("%s groups cover %d rows, audit.json n is %d", name, total, s.N)
		}
	}
	for name := range tables {
		if name == "impossibility.csv" {
			continue
		}
		seg := name[len("segment_") : len(name)-len(".csv")]
		if _, ok := s.Segments[seg]; !ok {
			fail("%s has no entry in audit.json", name)
		}
	}

	// The three impossibility fields nothing else recomputes.
	imp, ok := tables["impossibility.csv"]
	if !ok {
		fail("reports/impossibility.csv is missing")
	} else {
		for policy, want := range s.Impossibility.Policies {
			tprLo, tprHi := math.Inf(1), math.Inf(-1)
			thresholds := map[float64]bool{}
			caught := 0.0
			seen := 0
			for _, row := range imp.rows {
				if row["policy"] != policy {
					continue
				}
				seen++
				tpr := imp.num(row, "TPR")
				tprLo, tprHi = math.Min(tprLo, tpr), math.Max(tprHi, tpr)
				thresholds[imp.num(row, "threshold")] = true
				n, _ := strconv.Atoi(row["n"])
				caught += tpr * imp.num(row, "base_rate") * float64(n)
			}
			if seen == 0 {
				fail("impossibility.csv has no rows for policy %q", policy)
				continue
			}
			if got := (tprHi - tprLo) * 100; math.Abs(got-want.TPRSpreadPP) > 1e-9 {
				fail("%s TPR_spread_pp: recomputed %v, published %v", policy, got, want.TPRSpreadPP)
			}
			if got := len(thresholds) == 1; got != want.SameDecision {
				fail("%s same_score_same_decision: recomputed %v, published %v",
					policy, got, want.SameDecision)
			}
			if got := int(caught); got != want.FraudCaught {
				fail("%s fraud_caught: recomputed %d, published %d", policy, got, want.FraudCaught)
			}
			fmt.Printf("  %-22s %d groups, TPR spread %.4fpp, %d threshold(s), %d frauds caught\n",
				policy, seen, (tprHi-tprLo)*100, len(thresholds), int(caught))
		}
	}

	if failures > 0 {
		fmt.Printf("Go: %d structural or arithmetic failure(s)\n", failures)
		os.Exit(1)
	}
	fmt.Printf("Go: %d results files well formed, %d segments cover %d rows each,"+
		" impossibility summary reproduced\n", len(tables), len(s.Segments), s.N)
}
