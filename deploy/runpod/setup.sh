#!/usr/bin/env bash
# One-time (idempotent) setup of a RunPod pod, or any Linux machine, for this project. See docs/runpod.md.
#
#   bash deploy/runpod/setup.sh            # .NET 8 SDK, Python packages, build, publish the Runner
#   bash deploy/runpod/setup.sh --test     # ... and run the C# and Python tests
#   bash deploy/runpod/setup.sh --torch    # ... and install PyTorch if missing (GPU build from PyPI; RunPod PyTorch images already have it)
#
# Safe to run again (after git pull, or on a restarted pod): every step checks what is already there.
set -euo pipefail

cd "$(dirname "$0")/../.."
ROOT=$(pwd)
RUN_TESTS=0
WANT_TORCH=0
for arg in "$@"; do
  case "$arg" in
    --test) RUN_TESTS=1 ;;
    --torch) WANT_TORCH=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
step() { printf '\n== %s\n' "$*"; }
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

# ---------------------------------------------------------------- .NET 8 SDK
step ".NET 8 SDK"
has_sdk8() { command -v dotnet >/dev/null 2>&1 && dotnet --list-sdks 2>/dev/null | grep -q '^8\.'; }
if [ -x "$HOME/.dotnet/dotnet" ] && ! has_sdk8; then export PATH="$HOME/.dotnet:$PATH"; fi
if has_sdk8; then
  echo "already installed: $(dotnet --list-sdks | grep '^8\.' | head -1)"
else
  installed=0
  if command -v apt-get >/dev/null 2>&1; then
    # Ubuntu 22.04 and 24.04 ship dotnet-sdk-8.0 in their own repositories
    if $SUDO apt-get update -qq && DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq dotnet-sdk-8.0; then installed=1; fi
  fi
  if [ "$installed" -eq 0 ] || ! has_sdk8; then
    echo "apt did not provide dotnet-sdk-8.0: using Microsoft's dotnet-install.sh (into ~/.dotnet)"
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
    bash /tmp/dotnet-install.sh --channel 8.0 --install-dir "$HOME/.dotnet"
    export PATH="$HOME/.dotnet:$PATH"
    if ! grep -q '.dotnet' "$HOME/.bashrc" 2>/dev/null; then
      echo 'export PATH="$HOME/.dotnet:$PATH"; export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1' >> "$HOME/.bashrc"
    fi
  fi
  has_sdk8 || { echo "could not install the .NET 8 SDK" >&2; exit 1; }
  echo "installed: $(dotnet --list-sdks | grep '^8\.' | head -1)"
fi

# ---------------------------------------------------------------- Python packages
step "Python packages (ml/requirements.txt)"
PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }
"$PY" -m pip install -q -r ml/requirements.txt
if "$PY" -c "import torch" >/dev/null 2>&1; then
  echo "PyTorch: $("$PY" -c 'import torch; print(torch.__version__, "cuda" if torch.cuda.is_available() else "cpu only")')"
elif [ "$WANT_TORCH" -eq 1 ]; then
  "$PY" -m pip install -q torch
  echo "PyTorch: $("$PY" -c 'import torch; print(torch.__version__, "cuda" if torch.cuda.is_available() else "cpu only")')"
else
  echo "PyTorch: not installed (train_mlp.py uses NumPy; add --torch to install it)"
fi

# ---------------------------------------------------------------- build and publish
step "build (Release)"
dotnet build -c Release PuertoRico.sln --nologo -v q
step "publish the Runner to publish/runner (long background jobs use this copy)"
dotnet publish Runner -c Release -o publish/runner --nologo -v q
echo "run with: dotnet publish/runner/Runner.dll --config <file> ..."

if [ "$RUN_TESTS" -eq 1 ]; then
  step "tests"
  dotnet test -c Release --no-build --nologo -v q
  "$PY" -m pytest -q ml/tests
fi

# ---------------------------------------------------------------- machine summary
step "machine"
echo "cores: $(nproc)   memory: $(free -g | awk '/^Mem:/ {print $2 " GB"}')   disk free here: $(df -h . | awk 'NR==2 {print $4}')"
if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true; else echo "GPU: none"; fi
case "$ROOT" in
  /workspace/*) echo "project is on the persistent volume (/workspace): data and models survive pod restarts" ;;
  *) echo "WARNING: the project is not under /workspace: on RunPod everything outside the volume is lost when the pod stops" ;;
esac
cat <<'MSG'

Next (see docs/runpod.md):
  bash deploy/runpod/start.sh          # ML UI (8501) and Dashboard (5080) in the background, bound to localhost
  then, on your computer:  ssh -N -L 8501:localhost:8501 -L 5080:localhost:5080 root@<pod ip> -p <ssh port>
MSG
