#!/usr/bin/env bash
# Build a Debian package installing the patched proton-rtsp compatibility tool
# under /usr/share/steam/compatibilitytools.d/.
#
#   build-deb.sh [--proton DIR | --tarball FILE] [--docker | --no-docker]
#
# dpkg-deb from the host is used when available; otherwise the pinned SteamRT4
# SDK image (which ships dpkg-deb) runs it. The maintainer field comes from
# DEB_MAINTAINER or, failing that, from git config user.name / user.email.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
here=$root/packaging/deb
lock=$root/versions.lock.json
lockval() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d=d[k]
print(d)' "$lock" "$1"; }

package=proton-rtsp-avpro-fix
version=11.0.20260609.4-1
proton= tarball= use_docker=auto
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
    --docker)
      use_docker=yes
      shift
      ;;
    --no-docker)
      use_docker=no
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

maintainer=${DEB_MAINTAINER:-}
if [[ -z $maintainer ]]; then
  gname=$(git config user.name || true)
  gmail=$(git config user.email || true)
  [[ -n $gname && -n $gmail ]] || {
    echo "set DEB_MAINTAINER='Name <email>' or git config user.name/user.email" >&2
    exit 2
  }
  maintainer="$gname <$gmail>"
fi

if [[ $use_docker == auto ]]; then
  if command -v dpkg-deb >/dev/null; then use_docker=no; else use_docker=yes; fi
fi

release=$(lockval proton.name)
name=$release-avpro-fix

if [[ -z $proton && -z $tarball ]]; then
  python3 "$root/scripts/repro.py" fetch --only proton
  proton=$root/.cache/proton/$release
fi

work=$here/work
rm -rf "$work"
pkgroot=$work/$package
tools=$pkgroot/usr/share/steam/compatibilitytools.d
docdir=$pkgroot/usr/share/doc/$package
mkdir -p "$tools" "$docdir" "$pkgroot/DEBIAN"

if [[ -n $tarball ]]; then
  "$root/scripts/make-compat-tool.sh" --from-tarball "$tarball" --out "$tools" --name "$name" >/dev/null
else
  "$root/scripts/make-compat-tool.sh" --from-dir "$proton" --out "$tools" --name "$name" >/dev/null
fi
for f in LICENSE LICENSE.OFL PATENTS.AV1; do
  [[ -f $tools/$name/$f ]] && cp "$tools/$name/$f" "$docdir/$f"
done
cp "$root/THIRD_PARTY.md" "$docdir/"
cp "$root/patches/0001-live-network-state.patch" "$docdir/"
cp "$root/docs/patch.md" "$docdir/"
find "$pkgroot" -type d -exec chmod 0755 {} +

installed_kb=$(du -sk --apparent-size "$pkgroot" | cut -f1)
cat >"$pkgroot/DEBIAN/control" <<CONTROL
Package: $package
Version: $version
Section: games
Priority: optional
Architecture: amd64
Installed-Size: $installed_kb
Depends: python3
Recommends: steam
Maintainer: $maintainer
Homepage: https://github.com/SpookySkeletons/proton-rtsp
Description: proton-rtsp with the AVPro RTSP live playback fix for Steam
 $release with a patched mfmediaengine.dll so that AVPro Video
 (VRChat) keeps playing RTSP live streams instead of staying in Loading.
 Installs the tool as "$name" under compatibilitytools.d.
CONTROL

deb=$here/${package}_${version}_amd64.deb
rm -f "$deb"
if [[ $use_docker == yes ]]; then
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -v "$root:/work" -w /work "$(lockval sdk)" \
    dpkg-deb --root-owner-group -Zgzip -b "packaging/deb/work/$package" "packaging/deb/$(basename "$deb")"
else
  dpkg-deb --root-owner-group -Zgzip -b "$pkgroot" "$deb"
fi
rm -rf "$work"
echo "$deb"
