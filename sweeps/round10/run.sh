#!/bin/bash
# Runs every config in this folder; results go to ./results/round10/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/round10
dotnet build -c Release Runner >/dev/null
for cfg in sweeps/round10/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/round10/$n.json" ] && continue
  dotnet Runner/bin/Release/net8.0/Runner.dll --config "$cfg" --out "results/round10/$n.json" >/dev/null 2>&1
done
echo ALLDONE
