# Template: synthetic report (dataset → report → human review)

The smallest reusable flow the pilot drives end to end without a model, a
network or a personal path: one producer writes a seeded CSV, a second one
writes a report from it, two declared verifiers check shape and facts, one
human gate closes it. Copy the directory, change `input.txt`, run.

**What it proves:** the infrastructure — worker, declared verifiers, contract
order, human gate, resume, evidence on disk. **What it does not prove:** that
any LLM is available, authenticated or good. Nothing here spends.

```
graph.json        two capability nodes (tier trivial), each with an x_verifier;
                  the report node also declares the human gate `review`
registry.json     one binding: python3 -c {mission}; probe python3 --version
check_dataset.py  verifier: header id,value; 100 rows; values in [10, 20]
check_report.py   verifier: title + rows/mean/min/max, min <= mean <= max
input.txt         the run's frozen input (its hash enters run identity)
```

## Run it

```bash
cp -r examples/template-report ~/dagwell-ops/report-1 && cd ~/dagwell-ops/report-1

dagwell doctor  --graph graph.json --registry registry.json --data-dir data
RUN=$(dagwell start --ledger run.jsonl --graph graph.json --input input.txt)
A="dagwell advance --ledger run.jsonl --graph graph.json --run $RUN --registry registry.json --data-dir data"

$A          # plan: what would run; writes nothing
$A --go     # dataset → csv-shape → report → report-facts → gate `review` opens → stops
dagwell status --ledger run.jsonl --graph graph.json --run $RUN
#   report: waiting_human attempt 1
#   next: decide --node report approved|rejected --actor <you> [--reason ...]

# read the report before deciding:
cat data/runs/report-template/$RUN/report/t1/out

dagwell decide --ledger run.jsonl --graph graph.json --run $RUN --node report approved --actor "$USER" --reason "read it"
$A --go     # nothing left to run: the projection says completed
```

`{graph_dir}` in `x_verifier` is replaced by the directory of the `--graph`
file, so the template works wherever it is copied. The `report` mission finds
the dataset by the attempt-directory convention (`../../dataset/t<k>/out`),
because a producer receives only `$OUT` — see the limits in
[USAGE §5.8](../../docs/USAGE.md#58-drive-a-run-with-one-command-doctor--advance).

## What lands on disk

```
run.jsonl                                                 the ledger (append-only)
graphs/                                                   frozen graph snapshot
data/runs/report-template/<run>/dataset/t1/out            the CSV (evidence)
data/runs/report-template/<run>/report/t1/out             the report (evidence)
data/verifications/report-template/<run>/dataset/csv-shape/t1-v1/{result.json,log.txt,exit}
data/verifications/report-template/<run>/report/report-facts/t1-v1/{...}
```

## Make it fail on purpose

- Edit `check_report.py` to print `{"verdict": "rejected", ...}` → `report`
  lands `failed`; `status` says `human-retry --node report opens attempt 2`.
- Make it `sys.exit(2)` → `verification_status: error`, no verdict,
  `human_escalation`, `report: waiting_human`; `decide` or `human-retry`.
- Set `"x_verifier_timeout_seconds": 1` and add `time.sleep(5)` →
  `verification_status: timeout`, same escalation path.
- Overwrite `data/.../report/t1/out` after the return, before verifying →
  `inconsistent`: the verifier is not run, nothing is recorded.
