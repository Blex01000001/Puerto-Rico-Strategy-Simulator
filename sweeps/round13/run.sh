#!/bin/bash
# Runs every sweep in this folder; results go to ./results/round13/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/round13
dotnet build -c Release Runner >/dev/null
for cfg in sweeps/round13/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/round13/$n.json" ] && continue
  dotnet Runner/bin/Release/net8.0/Runner.dll --config "$cfg" --sweep --out "results/round13/$n.json" >/dev/null 2>&1
done
echo ALLDONE
