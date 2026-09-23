#!/usr/bin/env bash
# Produce the patched mfmediaengine.dll (and optionally a ready-to-extract
# compatibility tool tarball) from the pinned proton-rtsp release.
#
#   build-binary.sh [--proton DIR | --tarball FILE] [--tarball-out] [--out DIR]
#
# Without --proton/--tarball the pinned release is downloaded into .cache/ and
# verified against versions.lock.json.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
lock=$root/versions.lock.json
lockval() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d=d[k]
print(d)' "$lock" "$1"; }

proton= tarball= want_tarball=0 out=$root/dist
while [[ $# -gt 0 ]]; do
  case $1 in
    --proton)
      proton=$2
      shift 2
      ;;
    --tarball)
      tarball=$2
      shift 2
      ;;
    --tarball-out)
      want_tarball=1
      shift
      ;;
    --out)
      out=$2
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

release=$(lockval proton.name)
dll_rel=$(lockval proton.dll)
name=$release-avpro-fix

if [[ -z $proton && -z $tarball ]]; then
  python3 "$root/scripts/repro.py" fetch --only proton
  proton=$root/.cache/proton/$release
fi

mkdir -p "$out"
work=$(mktemp -d "$out/.work.XXXXXX")
trap 'rm -rf "$work"' EXIT

if [[ -n $tarball ]]; then
  tool=$("$root/scripts/make-compat-tool.sh" --from-tarball "$tarball" --out "$work" --name "$name")
else
  tool=$("$root/scripts/make-compat-tool.sh" --from-dir "$proton" --out "$work" --name "$name")
fi

install -m 0644 "$tool/$dll_rel" "$out/mfmediaengine.dll"
(cd "$out" && sha256sum mfmediaengine.dll >mfmediaengine.dll.sha256)
echo "$out/mfmediaengine.dll"

if [[ $want_tarball == 1 ]]; then
  archive=$out/$name.tar.gz
  tar -C "$work" --owner=0 --group=0 --numeric-owner -czf "$archive" "$name"
  (cd "$out" && sha256sum "$name.tar.gz" >"$name.tar.gz.sha256")
  echo "$archive"
fi
