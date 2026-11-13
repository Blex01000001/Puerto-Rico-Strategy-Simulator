#!/bin/bash
# Runs every config in this folder; results go to ./results/round11/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/round11
dotnet build -c Release Runner >/dev/null
for cfg in sweeps/round11/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/round11/$n.json" ] && continue
  dotnet Runner/bin/Release/net8.0/Runner.dll --config "$cfg" --out "results/round11/$n.json" >/dev/null 2>&1
done
echo ALLDONE
