#!/bin/bash

#
# LimeSurvey version upgrade detector script
#
# - The downloads page is used instead of GitHub tags, since they lag the official releases
# - Finds the newest LimeSurvey release listed on the downloads page and outputs the new version URL as the last line of stdout, if the current version in the Dockerfile is out of date
# - If no update is available/required, nothing is output
# - Exit codes other than 0 indicate failure
#
# Optional environment variables:
#   LS_MAJOR            Track a specific major release branch, e.g. 7. Unset tracks latest.
#   LS_CURRENT_VERSION  Version to compare against. Default: parsed from the Dockerfile.
#   LS_URL              Downloads listing page. Default: the community downloads page.
#   LS_DOWNLOAD_BASE    Base for the release URL. Default: https://download.limesurvey.org
#

# Abort on error
set -euo pipefail

# Define environment variable inputs with fallback defaults
: "${LS_URL:=https://community.limesurvey.org/downloads/}"
: "${LS_DOWNLOAD_BASE:=https://download.limesurvey.org}"
: "${LS_MAJOR:=}"
# Parse existing version code from LIMESURVEY_URL in Dockerfile if not provided
: "${LS_CURRENT_VERSION:=$(grep -m1 -Po '^[[:space:]]*ARG[[:space:]]+LIMESURVEY_URL=.*limesurvey\K[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+(?=\.zip)' Dockerfile 2>/dev/null || true)}"

# Collect release versions (X.Y.Z+build) advertised on the page
# Pre-release names (containing a hyphen, e.g. 7.0.0-RC1) do not match the pattern.
page="$(curl -fsSL "$LS_URL")" || { echo "ERROR: could not fetch ${LS_URL}" >&2; exit 1; }
versions="$(grep -oiP 'limesurvey\K[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+(?=\.zip)' <<< "$page" | sort -u || true)"
[ -n "$versions" ] || { echo "ERROR: no release versions found on ${LS_URL}" >&2; exit 1; }

# Optionally restrict to a single major line
if [ -n "$LS_MAJOR" ]; then
  versions="$(grep -E "^${LS_MAJOR}\." <<< "$versions" || true)"
  [ -n "$versions" ] || { echo "ERROR: no release found for major line '${LS_MAJOR}'" >&2; exit 2; }
fi

# Highest version wins (version-aware sort)
latest="$(sort -V <<< "$versions" | tail -n 1)"

# If already current, emit nothing on stdout
if [ -n "$LS_CURRENT_VERSION" ] && [ "$LS_CURRENT_VERSION" = "$latest" ]; then
  echo "Already up to date (${LS_CURRENT_VERSION})." >&2
  exit 0
fi

# Don't propose a downgrade, e.g. when LS_MAJOR pins a line below the current version
if [ -n "$LS_CURRENT_VERSION" ]; then
  newer="$(printf '%s\n%s\n' "$LS_CURRENT_VERSION" "$latest" | sort -V | tail -n 1)"
  if [ "$newer" != "$latest" ]; then
    echo "Current version ${LS_CURRENT_VERSION} is newer than the latest found (${latest}); nothing to do." >&2
    exit 0
  fi
fi

download_url="${LS_DOWNLOAD_BASE}/limesurvey${latest}.zip"

# Confirm the download link works before using it
if ! curl -fsIL -o /dev/null "$download_url"; then
  echo "ERROR: constructed URL is not reachable: ${download_url}" >&2
  exit 3
fi

echo "Current version: ${LS_CURRENT_VERSION:-unknown}"
echo "New version available: ${latest}"
echo "${download_url}"
exit 0
