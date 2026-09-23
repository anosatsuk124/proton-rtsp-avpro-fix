"""Execute the patch body against boundary values using the Windows x64 ABI."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from patch_binary import BODY

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    shutil.which("gcc") and shutil.which("as") and shutil.which("objcopy"),
    "Optional x86_64 machine-code check needs GCC and GNU binutils",
)
class MachineCodeTests(unittest.TestCase):
    def test_assembler_matches_binary_and_only_changes_positive_infinite_idle(self):
        assembly = (ROOT / "patches/live-network-body.s").read_text()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            body = d / "body.s"
            body.write_text(assembly)
            subprocess.run(
                ["as", "--64", str(body), "-o", str(d / "body.o")], check=True
            )
            subprocess.run(
                [
                    "objcopy",
                    "-O",
                    "binary",
                    "-j",
                    ".text",
                    str(d / "body.o"),
                    str(d / "body.bin"),
                ],
                check=True,
            )
            actual = (d / "body.bin").read_bytes()
            self.assertEqual(BODY[: len(actual)], actual)
            self.assertEqual(BODY[len(actual) :], b"\x90" * (len(BODY) - len(actual)))
            (d / "function.s").write_text(
                ".intel_syntax noprefix\n.text\n.global getter\ngetter:\n"
                ".byte 0x55,0x53,0x48,0x83,0xec,0x38,0x48,0x8d,0x6c,0x24,0x30,0x48,0x89,0xcb\n"
                + assembly
                + '\n.section .note.GNU-stack,"",@progbits\n'
            )
            (d / "check.c").write_text(r"""
#include <stdint.h>
#include <string.h>
#include <math.h>
extern uint16_t __attribute__((ms_abi)) getter(void *);
int main(void) {
    unsigned char engine[0x100] = {0};
    double durations[] = {INFINITY, -INFINITY, NAN, 0.0, 8.0, 1e100};
    for (uint16_t state = 0; state <= 4; ++state) {
        for (unsigned i = 0; i < sizeof(durations)/sizeof(*durations); ++i) {
            memcpy(engine + 0x70, &durations[i], sizeof(double));
            memcpy(engine + 0x80, &state, sizeof(state));
            uint16_t expected = state == 1 && i == 0 ? 2 : state;
            if (getter(engine) != expected) return 1;
        }
    }
    return 0;
}
""")
            subprocess.run(
                [
                    "gcc",
                    "-O2",
                    str(d / "check.c"),
                    str(d / "function.s"),
                    "-o",
                    str(d / "check"),
                ],
                check=True,
            )
            subprocess.run([str(d / "check")], check=True, timeout=5)
