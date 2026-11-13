#!/bin/bash
# build-first 3-player parameter sweeps (new tie defaults); results go to ./results/round12/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/round12
dotnet build -c Release Runner >/dev/null
for cfg in sweeps/round12/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/round12/$n.json" ] && continue
  dotnet Runner/bin/Release/net8.0/Runner.dll --config "$cfg" --sweep --out "results/round12/$n.json" >/dev/null 2>&1
done
echo ALLDONE
