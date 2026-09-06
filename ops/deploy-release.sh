#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: deploy-release.sh <40-character commit> <release archive>" >&2
  exit 2
fi

release_sha=$1
archive=$2
case "$release_sha" in
  *[!0-9a-f]*|'') echo "invalid release commit" >&2; exit 2 ;;
esac
[ "${#release_sha}" -eq 40 ] || { echo "invalid release commit length" >&2; exit 2; }
[ -f "$archive" ] || { echo "release archive is missing" >&2; exit 2; }
command -v zstd >/dev/null 2>&1 || { echo "zstd is required for Beast batch processing" >&2; exit 1; }

base="$HOME/antenna-observatory"
releases="$base/releases"
release="$releases/$release_sha"
current="$base/current"
previous=$(readlink "$current" 2>/dev/null || true)

mkdir -p "$releases" "$HOME/.local/state/antenna-observatory"
if [ ! -d "$release" ]; then
  mkdir "$release"
  tar -xzf "$archive" -C "$release"
fi

for required in dist/client/index.html server/observatory.py ops/servercheap-supervisor.py; do
  [ -f "$release/$required" ] || { echo "release is missing $required" >&2; exit 1; }
done

restart_relay() {
  pkill -TERM -f 'servercheap-supervisor.py relay' 2>/dev/null || true
  attempts=0
  while pgrep -f 'servercheap-supervisor.py relay' >/dev/null 2>&1 && [ "$attempts" -lt 20 ]; do
    sleep 1
    attempts=$((attempts + 1))
  done
  nohup python3 "$current/ops/servercheap-supervisor.py" relay </dev/null >/dev/null 2>&1 &
}

ln -sfn "releases/$release_sha" "$base/current-next"
mv -Tf "$base/current-next" "$current"
restart_relay

healthy=false
attempts=0
while [ "$attempts" -lt 30 ]; do
  if curl --fail --silent --show-error --header 'Host: antenna.ramideltoro.com' \
    http://127.0.0.1:8787/ >/dev/null; then
    healthy=true
    break
  fi
  sleep 1
  attempts=$((attempts + 1))
done

if [ "$healthy" != true ]; then
  echo "new release failed its local health check; rolling back" >&2
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$base/current-next"
    mv -Tf "$base/current-next" "$current"
    restart_relay
  fi
  exit 1
fi

find "$releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -nr \
  | tail -n +6 \
  | cut -d' ' -f2- \
  | xargs -r rm -rf

echo "deployed $release_sha"
