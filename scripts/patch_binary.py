#!/usr/bin/env python3
"""Reproduce the experimental x64 Media Engine live-network compatibility patch.

Only accepts the exact official proton-rtsp-11.0-20260609-4 binary. Apply to a
separate compatibility-tool copy; never to the original or an active prefix.
"""

import hashlib
import os
import stat
import sys
import tempfile
from pathlib import Path

EXPECTED = "93df6c48dc46c6927411234e12c11e4a733a1c18e9b7d6609d826b7b6825ab39"
RESULT = "a0c4a0a26e50158a12dca61971c47371191e67d606dfbd2ee0d2e970994111ed"
BODY = bytes.fromhex(
    "0fb7838000000083f801751548ba000000000000f07f483953707505b802000000"
    "4883c4385b5dc39090909090909090"
)


def patch(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Use a separate output file; source must remain unchanged.")
    data = bytearray(source.read_bytes())
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Unsupported source binary: SHA-256 does not match.")
    if destination.exists():
        if (
            not destination.is_symlink()
            and hashlib.sha256(destination.read_bytes()).hexdigest() == RESULT
        ):
            return RESULT
        raise ValueError(
            "Output exists with different content; refusing to overwrite it."
        )
    if destination.is_symlink():
        raise ValueError("Output must not be a symlink.")
    # Preserve the original prologue, saved registers, stack size, and unwind
    # metadata. Replace the return calculation and omit this function's TRACE.
    # Confirmed offsets in this build: network_state +0x80, duration +0x70.
    # Return LOADING (2) only for IDLE (1) plus positive infinite duration.
    # All finite-duration videos and other network states retain their result.
    if data[0x33B0:0x33BE].hex() != "55534883ec38488d6c24304889cb":
        raise ValueError("Unexpected function prologue")
    data[0x33BE:0x340A] = BODY + b"\x90" * (0x340A - 0x33BE - len(BODY))
    if hashlib.sha256(data).hexdigest() != RESULT:
        raise ValueError("Patched output hash mismatch")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        os.chmod(temporary, stat.S_IMODE(source.stat().st_mode))
        # Atomic create without replacing a file created by another process.
        os.link(temporary, destination)
    finally:
        temporary.unlink()
    return RESULT


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: patch_binary.py ORIGINAL_DLL SEPARATE_OUTPUT_DLL")
    try:
        print(patch(Path(sys.argv[1]), Path(sys.argv[2])))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
