#!/bin/bash
# Runs every tournament config in this folder and writes the result files to ./results/ (git-ignored).
# Usage: tournaments/run.sh [games]   (default: the games value in each config)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
dotnet build -c Release Runner >/dev/null
for cfg in tournaments/*.json; do
  name=$(basename "$cfg" .json)
  echo "== $name"
  args=(--config "$cfg" --out "results/$name.json")
  if [ $# -ge 1 ]; then args+=(--games "$1"); fi
  dotnet Runner/bin/Release/net8.0/Runner.dll "${args[@]}" 2>/dev/null
done
