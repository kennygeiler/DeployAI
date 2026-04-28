#!/usr/bin/env bash
# Story 11.5 — emit apps/edge-agent/dist/appcast.xml from template values (CI / release).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:?version}"
DOWNLOAD_URL="${2:?download url for enclosure}"
SIG_ATTR="${3:?sparkle:edSignature and length fragment from sign-sparkle-archive}"
OUT="${4:-"$ROOT/dist/appcast.xml"}"
mkdir -p "$(dirname "$OUT")"
PUB_DATE="$(date -R -u)"
cat >"$OUT" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>DeployAI Edge Agent Updates</title>
    <description>Story 11.5 signed appcast (generated)</description>
    <language>en</language>
    <item>
      <title>DeployAI Edge Agent ${VERSION}</title>
      <pubDate>${PUB_DATE}</pubDate>
      <sparkle:version>${VERSION}</sparkle:version>
      <sparkle:shortVersionString>${VERSION}</sparkle:shortVersionString>
      <enclosure url="${DOWNLOAD_URL}" type="application/octet-stream" ${SIG_ATTR} />
    </item>
  </channel>
</rss>
EOF
echo "wrote $OUT"
