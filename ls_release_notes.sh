#!/bin/bash

#
# LimeSurvey release notes extractor
#
# Prints the newest changelog block from a LimeSurvey release_notes.txt.
#
# The single argument selects the source:
#   - a path to an existing `release_notes.txt`: read it directly
#   - a release zip URL:                         download it and extract docs/release_notes.txt
#   - omitted entirely:                          parse LIMESURVEY_URL from the Dockerfile to download
#
# Exits 0 only when a changelog block is printed. Any error (a missing source, a failed download
# or extraction, or an unparseable release_notes.txt) prints a message to stderr and exits 1.
#

# Abort on error
set -euo pipefail

arg="${1:-}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

notes=""
if [ -n "$arg" ] && [ -f "$arg" ]; then
  # Source is a local release_notes.txt
  notes="$arg"
else
  # Source is a release zip URL, given directly or parsed from the Dockerfile
  url="$arg"
  if [ -z "$url" ]; then
    url="$(grep -m1 -oP '^\s*ARG\s+LIMESURVEY_URL=\K\S+' Dockerfile 2>/dev/null || true)"
  fi
  if [ -z "$url" ]; then
    echo "ERROR: no release_notes.txt path, release URL, or Dockerfile LIMESURVEY_URL found" >&2
    exit 1
  fi
  # docs/release_notes.txt lives under a top-level directory in the zip (e.g. limesurvey/docs/...)
  if ! curl -fsSL --retry 3 -o "$tmp/ls.zip" "$url"; then
    echo "ERROR: failed to download $url" >&2
    exit 1
  fi
  if ! unzip -p "$tmp/ls.zip" '*/docs/release_notes.txt' > "$tmp/release_notes.txt" 2>/dev/null; then
    echo "ERROR: docs/release_notes.txt not found in the archive at $url" >&2
    exit 1
  fi
  notes="$tmp/release_notes.txt"
fi

if [ ! -s "$notes" ]; then
  echo "ERROR: release notes source is empty: $notes" >&2
  exit 1
fi

# release_notes.txt lists releases newest-first; print the first "Changes from ..." block only.
block="$(awk '/^Changes from /{c++; if (c>=2) exit} c>=1{print}' "$notes" || true)"
if [ -z "$block" ]; then
  echo "ERROR: no 'Changes from ...' changelog block found in $notes" >&2
  exit 1
fi
printf '%s\n' "$block"
