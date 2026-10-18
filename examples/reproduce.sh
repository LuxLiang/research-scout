#!/usr/bin/env bash
set -euo pipefail
# Run after installing research-scout. Every scientific record is SYNTHETIC.
export SCOUT_WORKSPACE="${SCOUT_WORKSPACE:-/tmp/research-scout-example}"
scout init
scout import-history
scout search dissipation
scout mechanism mechanism-cross
scout evolution problem-p
scout breakthroughs --result result-c
scout transfer mechanism-cross --target problem-q --mode breakthrough-first
scout_demo_report=$(mktemp)
trap 'rm -f "$scout_demo_report"' EXIT
scout demo --output "$SCOUT_WORKSPACE/proposal.md" > "$scout_demo_report"
scout_opportunity_id=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["opportunity_id"])' "$scout_demo_report")
scout export "$scout_opportunity_id" --format research-harness --output "$SCOUT_WORKSPACE/proposal.md"
scout index rebuild
scout doctor
scout eval
