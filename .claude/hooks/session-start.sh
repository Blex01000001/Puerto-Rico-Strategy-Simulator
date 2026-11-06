#!/bin/bash
# SessionStart hook for Claude Code cloud sessions: make `dotnet build/test` work.
set -euo pipefail

# Only needed in remote (cloud) sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1

# .NET 8 SDK via apt (builds.dotnet.microsoft.com is blocked, so dotnet-install.sh is unusable).
# Install only if missing or not an 8.x SDK.
if ! command -v dotnet >/dev/null 2>&1 || ! dotnet --list-sdks 2>/dev/null | grep -q '^8\.'; then
  apt-get update -qq
  apt-get install -y -qq dotnet-sdk-8.0
fi

# NuGet restore, only when the solution exists and its inputs changed since the last success.
# The stamp lives in the NuGet package cache, so it disappears together with the packages.
stamp="${NUGET_PACKAGES:-$HOME/.nuget/packages}/.session-start.sha256"
if [ -f PuertoRico.sln ]; then
  current=$(
    {
      find . \( -name bin -o -name obj -o -name node_modules -o -name .git \) -prune -o -type f \
        \( -name '*.csproj' -o -name '*.props' -o -name '*.targets' -o -name '*.sln' -o -name 'global.json' -o -name 'NuGet.config' \) -print \
        | LC_ALL=C sort | xargs sha256sum
      sha256sum .claude/hooks/session-start.sh
    } | sha256sum
  )
  if [ "$(cat "$stamp" 2>/dev/null || true)" != "$current" ]; then
    # Delete the old stamp first, so a failed restore runs again next time.
    rm -f "$stamp"
    dotnet restore PuertoRico.sln
    mkdir -p "$(dirname "$stamp")"
    echo "$current" > "$stamp"
  fi
fi

# Keep dotnet quiet and telemetry-free for every command in the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo 'export DOTNET_CLI_TELEMETRY_OPTOUT=1'
    echo 'export DOTNET_NOLOGO=1'
  } >> "$CLAUDE_ENV_FILE"
fi
