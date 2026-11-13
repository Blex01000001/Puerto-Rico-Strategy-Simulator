#!/bin/bash
# Plays every table in this folder with tools/sparring and writes the behaviour reports to ./results/sparring/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p results/sparring
dotnet build -c Release tools/sparring >/dev/null
for cfg in mcts/sparring/*.json; do
  n=$(basename "$cfg" .json)
  [ -f "results/sparring/$n.md" ] && continue
  dotnet tools/sparring/bin/Release/net8.0/sparring.dll "$cfg" > "results/sparring/$n.md"
done
echo ALLDONE
