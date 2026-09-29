# Patch specification

[日本語版はこちら (Japanese)](patch.ja.md)

## Wine source build

Apply [`0001-live-network-state.patch`](../patches/0001-live-network-state.patch) to the Wine commit in `versions.lock.json`.

```c
if (engine->network_state == MF_MEDIA_ENGINE_NETWORK_IDLE && engine->duration == INFINITY)
    return MF_MEDIA_ENGINE_NETWORK_LOADING;
```

The stored state is not modified; only the return value of this getter is adjusted.

| Original network state | duration | Return value |
| --- | --- | --- |
| IDLE (1) | +INFINITY | LOADING (2) |
| IDLE (1) | finite / NaN / -INFINITY | IDLE (1) |
| anything else | any | unchanged |

The source build uses the fixed configuration in `scripts/build-wine.sh`. The Vulkan XML registry is pre-fetched with pinned hashes, and the container build runs with networking disabled. Producing a byte-identical DLL to the original release is not a goal; the goal is a build from the same inputs that lets the behaviour before and after the patch be compared.

Options such as `--without-gstreamer` are build settings for producing this single DLL. Real playback uses the Wine GStreamer / decoder / DXVK components of the pinned Proton release.

## Exact binary patch

[`patch_binary.py`](../scripts/patch_binary.py) verifies the SHA-256 of both the input DLL and the output DLL. It never guesses offsets for other versions.

- Target: `files/lib/wine/x86_64-windows/mfmediaengine.dll`
- Original SHA-256: `93df6c48dc46c6927411234e12c11e4a733a1c18e9b7d6609d826b7b6825ab39`
- Output SHA-256: `a0c4a0a26e50158a12dca61971c47371191e67d606dfbd2ee0d2e970994111ed`
- Target function: `media_engine_GetNetworkState`, RVA `0x33b0`
- In this DLL the `.text` RVA and the raw file offset coincide at the target location.
- The prologue at `0x33b0..0x33bd` is kept; the body at `0x33be..0x3409` is replaced.
- Struct offsets specific to this build: duration `+0x70`, network_state `+0x80`.
- Saved registers, stack size, epilogue, and PE unwind information stay consistent.
- The rest of the function is padded with NOPs. The binary version omits the TRACE in this getter.

The corresponding assembly is [`live-network-body.s`](../patches/live-network-body.s). The adjustment applies only when the value matches the IEEE 754 bit pattern of positive infinity, `0x7ff0000000000000`.

Refused: output path equal to the input, an unexpected input hash, an existing output with different content, and a symlink as output. If the correct output already exists the script succeeds without changes. The DLL is written to a temporary file and created atomically under its final name so a half-written DLL is never exposed.

## Where it goes

Copy Proton under a different name and replace the DLL inside its `files/lib/wine/x86_64-windows/`. During diagnostics, placing the DLL only in the prefix's `system32` did not select the built-in DLL as expected, and forcing `WINEDLLOVERRIDES=mfmediaengine=n` broke AVPro initialization. The install script therefore does not use those approaches.

The original Proton, the Proton VRChat is currently using, and the DLLs in the game prefix are never modified automatically.
