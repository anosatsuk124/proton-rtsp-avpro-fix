#!/usr/bin/env bash
# Assemble a Steam compatibility tool: the pinned proton-rtsp release with the
# patched mfmediaengine.dll and a renamed compatibilitytool.vdf.
#
#   make-compat-tool.sh (--from-dir DIR | --from-tarball FILE) --out DIR [--name NAME]
#
# DIR/FILE must be the unmodified pinned release. Every hash is taken from
# versions.lock.json; the input DLL and the output DLL are both verified.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
lock=$here/versions.lock.json
[[ -f $lock ]] || lock=$here/../versions.lock.json
patcher=$here/patch_binary.py

lockval() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d=d[k]
print(d)' "$lock" "$1"; }

from_dir= from_tarball= out= name=
while [[ $# -gt 0 ]]; do
  case $1 in
    --from-dir)
      from_dir=$2
      shift 2
      ;;
    --from-tarball)
      from_tarball=$2
      shift 2
      ;;
    --out)
      out=$2
      shift 2
      ;;
    --name)
      name=$2
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
name=${name:-$release-avpro-fix}
[[ -n $out ]] || {
  echo "--out is required" >&2
  exit 2
}
[[ -n $from_dir || -n $from_tarball ]] || {
  echo "--from-dir or --from-tarball is required" >&2
  exit 2
}
[[ -f $patcher ]] || {
  echo "missing $patcher" >&2
  exit 1
}

sha() { sha256sum "$1" | cut -d' ' -f1; }

mkdir -p "$out"
out=$(cd "$out" && pwd)
target=$out/$name
[[ ! -e $target ]] || {
  echo "refusing to overwrite existing $target" >&2
  exit 1
}

tmp=$(mktemp -d "$out/.staging.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

if [[ -n $from_tarball ]]; then
  [[ $(sha "$from_tarball") == "$(lockval proton.archive_sha256)" ]] || {
    echo "tarball SHA-256 mismatch" >&2
    exit 1
  }
  tar -xf "$from_tarball" -C "$tmp"
  from_dir=$tmp/$release
fi
original=$from_dir/$dll_rel
[[ -f $original ]] || {
  echo "missing $original" >&2
  exit 1
}
[[ $(sha "$original") == "$(lockval proton.original_sha256)" ]] || {
  echo "input DLL is not the pinned unmodified release" >&2
  exit 1
}

staging=$tmp/$name
cp -a --reflink=auto "$from_dir" "$staging"
rm -f "$staging/$dll_rel" # never write through a release symlink/hardlink
python3 "$patcher" "$original" "$staging/$dll_rel" >/dev/null
[[ $(sha "$staging/$dll_rel") == "$(lockval proton.patched_sha256)" ]] || {
  echo "patched DLL SHA-256 mismatch" >&2
  exit 1
}

cat >"$staging/compatibilitytool.vdf" <<VDF
"compatibilitytools"
{
 "compat_tools"
 {
  "$name"
  {
   "install_path" "."
   "display_name" "$name"
   "from_oslist" "windows"
   "to_oslist" "linux"
  }
 }
}
VDF
mv "$staging" "$target"
echo "$target"
