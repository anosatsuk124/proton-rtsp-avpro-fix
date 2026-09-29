# proton-rtsp-avpro-fix

[日本語版はこちら (Japanese)](README.ja.md)

A Proton compatibility tool that fixes AVPro RTSP live playback in VRChat on Linux / Proton: audio plays but the video stays on "Loading".

Wine's `IMFMediaEngine::GetNetworkState()` returns `IDLE` for a source whose duration is positive infinity (a live stream). AVPro treats that `IDLE` as a stall and runs its recovery path (`Pause → Load`); `Load()` is unimplemented in the target Wine, which leaves the playback state broken. This tool returns `LOADING` instead, only for that exact case, so the playback state survives. Details: [docs/patch.md](docs/patch.md).

The target is pinned to **proton-rtsp-11.0-20260609-4 / Linux x86_64 / AVPro native 3.4.0f1-ultra**. Every upstream version and hash lives in [versions.lock.json](versions.lock.json), and everything fetched is verified against it. The build is self-contained in this repository; nothing outside it is referenced.

## Three ways to use it

| Goal | Command | Output |
| --- | --- | --- |
| Install as a package on Arch | `make pkg-arch` | `packaging/arch/proton-rtsp-avpro-fix-bin-*.pkg.tar.zst` |
| Install as a package on Debian / Ubuntu | `make pkg-deb` | `packaging/deb/proton-rtsp-avpro-fix_*_amd64.deb` |
| Just build the binaries | `make binary` / `make tarball` | `dist/mfmediaengine.dll` / `dist/proton-rtsp-11.0-20260609-4-avpro-fix.tar.gz` |

All three download the pinned release tarball (about 490 MB), replace only `mfmediaengine.dll`, and produce a Proton tree named `proton-rtsp-11.0-20260609-4-avpro-fix` in Steam. The SHA-256 of both the original and the patched DLL is verified; any other input is refused.

### Requirements (common)

- Linux x86_64, Python 3.12 or newer, bash, GNU tar, coreutils
- Internet access on first run (to download the Proton release)

### Arch Linux

```sh
make pkg-arch          # runs makepkg -f in packaging/arch
sudo pacman -U packaging/arch/proton-rtsp-avpro-fix-bin-*.pkg.tar.zst
```

It installs to `/usr/share/steam/compatibilitytools.d/proton-rtsp-11.0-20260609-4-avpro-fix/`. The directory name differs from the AUR `proton-rtsp-bin` package, so both can coexist. Dependencies match the AUR `proton-rtsp-bin`.

The PKGBUILD's `source=` refers to scripts in this repository through symlinks in the same directory. After editing `scripts/patch_binary.py` or `scripts/make-compat-tool.sh`, run `make pkg-sums` to refresh `sha256sums` (`make test` catches a mismatch).

### Debian / Ubuntu

```sh
make pkg-deb
sudo dpkg -i packaging/deb/proton-rtsp-avpro-fix_11.0.20260609.4-1_amd64.deb
```

`dpkg-deb` from the host is used when available; otherwise the script runs it inside the SteamRT4 SDK Docker image pinned in `versions.lock.json` (Docker required). Force either with `--docker` / `--no-docker`. The Maintainer field comes from the `DEB_MAINTAINER` environment variable, or from `git config user.name` and `user.email`.

### Binaries only

```sh
make binary                        # dist/mfmediaengine.dll plus .sha256
make tarball                       # also a tar.gz that extracts straight into compatibilitytools.d
make binary ARGS="--proton DIR"    # use an already extracted, unmodified proton-rtsp-11.0-20260609-4
make binary ARGS="--tarball FILE"  # use an already downloaded release tar.gz
```

The tar.gz works by extracting it into Steam's `compatibilitytools.d`. Flatpak Steam does not look at `/usr/share`, so extract the tar.gz into the Flatpak's `data/Steam/compatibilitytools.d/` instead.

### Steam settings

1. Restart Steam.
2. In VRChat's Properties → Compatibility, select `proton-rtsp-11.0-20260609-4-avpro-fix`.
3. Add `--disable-hw-video-decoding` to the launch options (verification was done with software decoding).
4. Use `rtspt://HOST:PORT/STREAM` (RTSP over TCP) as the URL in the world. `rtsps://` is TLS, a different scheme, and does not select TCP.

To revert, switch the compatibility setting back to the previous Proton and remove the package or the extracted directory. The game's compatdata is untouched.

## Building from source and reproducing the bug

The packages use the verified binary patch. To build the same fix from Wine source and compare before/after automatically:

Additional requirements:

- A Docker daemon usable by the same user (SDK and MediaMTX are pinned by digest)
- Git, GNU Make
- Host FFmpeg / ffprobe with `libx264` and an AAC encoder
- Live playback diagnostics only: a regular desktop session, a Vulkan-capable GPU, Steam, Steam Linux Runtime 4, the user's own VRChat `AVProVideo.dll`, and Steam's H.264 video playback support

```sh
make fetch            # fetch and verify the pinned Proton tar.gz, Wine commit, Vulkan XML, container images
make build JOBS=2     # build baseline and patched mfmediaengine.dll inside the SDK (network disabled)
make patch            # apply the binary patch to the pinned release and verify SHA-256
make probe            # compile the minimal AVPro host and Media Foundation probe
make test             # unit tests (assembly vs. patch bytes, hash consistency, guards)
```

`make build` builds only `mfmediaengine.dll` from the pinned Wine commit and combines it with the rest of the pinned Proton release at runtime. It does not rebuild all of Proton. Outputs:

| Output | Content |
| --- | --- |
| `artifacts/binary-patched/` | verified binary-patched DLL and manifest |
| `artifacts/source-baseline/` | unmodified DLL built from source with the same SDK |
| `artifacts/source-patched/` | DLL with the Wine source patch applied |
| `artifacts/probes/` | diagnostic executables |
| `build/source-*.log` | compiler output |

If you already have the unmodified target Proton, point at it instead of downloading (verified by DLL hash):

```sh
make patch ARGS="--proton /path/to/proton-rtsp-11.0-20260609-4"
```

### Reproduction

With VRChat running from Steam, find its process ID. Only `STEAMVIDEOTOKEN` is inherited in memory from that process; it is never passed as an argument or written anywhere.

```sh
pgrep -f '^S:.*VRChat.exe'
make reproduce ARGS="--inherit-video-token-from 12345"
```

What it does automatically:

1. Starts MediaMTX on a temporary localhost port and publishes an FFmpeg test pattern plus a sine wave as H.264/AAC over RTSP/TCP.
2. Runs the official baseline, the binary-patched, the source baseline and the source-patched DLL, each in a fresh diagnostic prefix.
3. Checks AVPro's playback state, video frame count, playback time, and non-zero audio amplitude.
4. Checks that an 8-second finite MP4 plays to the end.
5. Cleans up the diagnostic FFmpeg / MediaMTX / prefixes and stores numeric results under `artifacts/runs/`.

The baseline live run is expected to be `reproduced`, the patched runs `passed`, and MP4 `passed`. Anything else exits non-zero. Use `--steam-root`, `--avpro-dll`, `--runtime` if Steam lives elsewhere. `--url rtsp://HOST:PORT/STREAM` tests a real stream instead (converted to `rtspt://` to force TCP; the URL is not stored).

`make install` copies the tool under the user's Steam `compatibilitytools.d` with a distinct name without using a package (`ARGS="--variant source-patched"` for the source build).

## Limitations

- AVPro's `IsBuffering` may stay true during live playback. Finite videos do not get the same adjustment.
- Hardware decoding, other worlds, and other AVPro versions are not guaranteed.
- The binary-patched build is the one confirmed in the real game. The source build has been verified with the standalone diagnostics (RTSP and MP4).
- Automated diagnostics from inside the Flatpak Steam sandbox are untested.

## Files

- `patches/0001-live-network-state.patch`: the Wine source patch
- `patches/live-network-body.s`: assembly equivalent of the binary patch
- `scripts/patch_binary.py`: binary patch for the pinned release DLL (input and output hashes verified)
- `scripts/make-compat-tool.sh`: assembles the patched Proton tree (shared by packages and binary output)
- `scripts/build-binary.sh`, `packaging/arch/PKGBUILD`, `packaging/deb/build-deb.sh`
- `scripts/repro.py`, `scripts/build-wine.sh`, `probes/`, `fixtures/`, `tests/`: source build and reproduction

## License

The modified `mfmediaengine.dll` derives from Wine and is LGPL-2.1-or-later; the corresponding source patch is in `patches/`. See [THIRD_PARTY.md](THIRD_PARTY.md) for the terms of Proton, the SteamRT SDK, MediaMTX, FFmpeg, AVPro, and Steam components. The AVPro DLL and Steam's video token are not distributed.
