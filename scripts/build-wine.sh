#!/usr/bin/env bash
set -euo pipefail
variant=${1:?baseline or patched}
jobs=${2:-2}
case "$variant" in baseline|patched) ;; *) exit 2;; esac
export SOURCE_DATE_EPOCH=1788377970 TZ=UTC LC_ALL=C CCACHE_DISABLE=1
src=/work/.cache/src-$variant
obj=/work/build/wine-$variant
mkdir -p "$obj"
cd "$src"
export XDG_CACHE_HOME=/work/.cache/generators
python3 dlls/winevulkan/make_vulkan -x /work/.cache/downloads/vk.xml -X /work/.cache/downloads/video.xml
tools/make_specfiles
autoreconf -fiv
cd "$obj"
export CFLAGS='-O2 -fwrapv -fno-strict-aliasing -ffunction-sections -fdata-sections -fno-omit-frame-pointer -ffile-prefix-map=/work=.'
"$src/configure" --enable-win64 --enable-archs=x86_64 --with-mingw=gcc \
    --disable-tests --without-x --without-wayland --without-gstreamer \
    --prefix=/work/build/install-$variant
make -j"$jobs" __tooldeps__
make -j"$jobs" dlls/mfmediaengine/all
mkdir -p /work/artifacts/source-$variant
cp dlls/mfmediaengine/x86_64-windows/mfmediaengine.dll /work/artifacts/source-$variant/
sha256sum /work/artifacts/source-$variant/mfmediaengine.dll
