#!/usr/bin/env bash
# Example runner: YOU execute the work, DAGWELL governs it.
#
# DAGWELL has no adapters (that is the Adapter Transport milestone). Until then,
# this is the shape of the loop that binds it to whatever actually does the work —
# claude, codex, grok, kimi, agy, a Makefile, a person. Nothing here is part of the
# engine: it is ~60 lines of shell you are meant to copy and adapt.
#
#   ./runner.sh <ledger> <graph.json> <run-id> [outdir]
#
# Each node declares its own command in the graph, in a field DAGWELL ignores:
#
#   {"id": "script", "deps": [], "output_evidence": "artifact",
#    "verifications": [{"verification_id": "review", "family": "human"}],
#    "x_command": "codex exec \"write the script to $OUT\""}
#
# `$OUT` is exported before the command runs and points at the file this node must
# produce. The command's exit code and that file ARE the evidence — nothing is
# taken on the command's word.
set -euo pipefail

LEDGER="${1:?usage: runner.sh <ledger> <graph.json> <run-id> [outdir]}"
GRAPH="${2:?}"
RUN="${3:?}"
OUTDIR="${4:-out}"
mkdir -p "$OUTDIR"

dg() { dagwell "$@" --ledger "$LEDGER" --graph "$GRAPH" --run "$RUN"; }

command_of() {   # read the node's x_command out of the graph
  python3 -c '
import json,sys
g=json.load(open(sys.argv[1]))
n=next((n for n in g["nodes"] if n["id"]==sys.argv[2]),{})
print(n.get("x_command",""))' "$GRAPH" "$1"
}

evidence_for() { # artifact evidence: the digest of what was actually written,
                 # with the evidence_id derived from the manifest (spec §4.2)
  python3 -c '
import hashlib,json,os,sys
from dagwell.canonical import json_digest
p=sys.argv[1]
d="sha256:"+hashlib.sha256(open(p,"rb").read()).hexdigest()
m=[{"path":p.split("/")[-1],"artifact_digest":d,"size_bytes":os.path.getsize(p)}]
print(json.dumps({"type":"artifact","evidence_id":json_digest(m),
                  "output_manifest":m}))' "$1"
}

while :; do
  node=$(dg ready | head -1 | awk '{print $1}')
  [ -z "$node" ] || [ "$node" = "nothing" ] && break

  cmd=$(command_of "$node")
  if [ -z "$cmd" ]; then
    echo "!! node '$node' declares no x_command — stopping so a human decides" >&2
    exit 2
  fi

  attempt=$(dg ready | head -1 | grep -oE '[0-9]+' | tail -1)
  dg dispatch --node "$node" > /dev/null
  echo "-> $node (attempt $attempt): $cmd"

  # THE WORK. Whatever this line runs is outside DAGWELL's authority.
  # It runs in a SUBSHELL on purpose: a command containing `exit` would otherwise
  # end this loop instead of itself, and the run would look abandoned rather than
  # finished. Anything the work does to its own shell stays in its own shell.
  export OUT="$OUTDIR/$node.out"
  set +e
  bash -c "$cmd"
  rc=$?
  set -e

  if [ $rc -ne 0 ] || [ ! -s "$OUT" ]; then
    # Failing honestly is legal. Absent evidence lands the attempt as `failed`;
    # claiming an output that is not there is what gets refused.
    echo "   exit $rc, no usable output -> recording the failure"
    dg return --node "$node" --attempt "$attempt" --exit-code "${rc:-1}" > /dev/null
    echo "   $node is now: $(dg status | grep "  $node:" | xargs)"
    continue
  fi

  dg return --node "$node" --attempt "$attempt" --exit-code 0 \
     --evidence "$(evidence_for "$OUT")" > /dev/null
  echo "   returned with evidence -> $(dg status | grep "  $node:" | awk '{print $2}')"

  # Verifications, in the order the contract requires. A human family stops the
  # loop: a gate is a decision, and this script has no business making it.
  while :; do
    vid=$(python3 -c '
import json,sys
g=json.load(open(sys.argv[1]))
n=next(n for n in g["nodes"] if n["id"]==sys.argv[2])
vs=[v for v in n.get("verifications",[]) if v["family"]!="human"]
print(vs[int(sys.argv[3])]["verification_id"] if int(sys.argv[3])<len(vs) else "")' \
      "$GRAPH" "$node" "${vi:-0}")
    [ -z "$vid" ] && break
    dg request-verification --node "$node" --verification "$vid" > /dev/null
    # run your real verifier here; its exit code decides the verdict
    if [ -s "$OUT" ]; then v=approved; else v=rejected; fi
    dg verdict --node "$node" --verification "$vid" --status completed \
       --verdict "$v" ${v:+} > /dev/null
    vi=$(( ${vi:-0} + 1 ))
  done
  unset vi

  # A declared human gate is OPENED here — opening is not deciding. Then the loop
  # stops: the decision is a person's, and a script that made it would be exactly
  # the thing this engine exists to prevent.
  hvid=$(python3 -c '
import json,sys
g=json.load(open(sys.argv[1]))
n=next(n for n in g["nodes"] if n["id"]==sys.argv[2])
h=[v for v in n.get("verifications",[]) if v["family"]=="human"]
print(h[0]["verification_id"] if h else "")' "$GRAPH" "$node")
  if [ -n "$hvid" ]; then
    dg request-verification --node "$node" --verification "$hvid" > /dev/null
    echo "   human gate '$hvid' is open. Decide with:"
    echo "     dagwell decide --ledger $LEDGER --graph $GRAPH --run $RUN --node $node approved"
    break
  fi
done

echo
dg status
