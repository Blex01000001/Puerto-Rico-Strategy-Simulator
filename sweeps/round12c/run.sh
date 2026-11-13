#!/bin/bash
# build-first 3-player quarryTarget confirmation (new tie defaults); results go to ./results/round12c/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/round12c
dotnet build -c Release Runner >/dev/null
for cfg in sweeps/round12c/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/round12c/$n.json" ] && continue
  dotnet Runner/bin/Release/net8.0/Runner.dll --config "$cfg" --out "results/round12c/$n.json" >/dev/null 2>&1
done
echo ALLDONE
