import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import patch_binary
import repro


def trace(playing=True, live=True):
    return [
        dict(
            elapsed=float(i),
            metadata=1,
            canplay=1,
            playing=int(playing),
            buffering=int(live),
            stalled=0,
            finished=int(not live and i >= 8),
            error=0,
            width=1280,
            height=720,
            frames=30 * min(i, 8) if not live else 30 * i,
            time=float(min(i, 8) if not live else i),
            live=live,
            duration=0 if live else 8,
            audio_samples=i * 48000,
            audio_peak=0.1,
        )
        for i in range(12)
    ]


class AcceptanceTests(unittest.TestCase):
    def test_decoding_without_playing_reproduces_original_bug(self):
        self.assertEqual(repro.classify(trace(False))["status"], "reproduced")

    def test_live_buffering_true_can_still_be_working(self):
        self.assertEqual(repro.classify(trace())["status"], "passed")

    def test_readiness_alone_does_not_pass(self):
        for field in ("frames", "audio_samples", "audio_peak", "time"):
            with self.subTest(field=field):
                rows = trace()
                for row in rows:
                    row[field] = 0
                self.assertNotEqual(repro.classify(rows)["status"], "passed")

    def test_late_playback_drop_does_not_pass(self):
        rows = trace()
        rows[-1]["playing"] = 0
        self.assertEqual(repro.classify(rows)["status"], "inconclusive")

    def test_error_and_empty_input_fail(self):
        self.assertEqual(repro.classify([])["status"], "failed")
        rows = trace()
        rows[-1]["error"] = 100
        self.assertEqual(repro.classify(rows)["status"], "failed")

    def test_vod_requires_end_of_stream(self):
        rows = trace(live=False)
        self.assertEqual(repro.classify(rows, vod=True)["status"], "passed")
        for row in rows:
            row["finished"] = 0
        self.assertEqual(repro.classify(rows, vod=True)["status"], "failed")


class GuardTests(unittest.TestCase):
    def test_prefix_is_cleaned_even_if_initialization_times_out(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock_patch.object(repro, "CACHE", Path(d)),
            mock_patch.object(
                repro,
                "_run_probe",
                side_effect=subprocess.TimeoutExpired("diagnostic", 90),
            ),
            mock_patch.object(repro.subprocess, "run") as stop,
        ):
            args = argparse.Namespace(keep_prefixes=False)
            with self.assertRaises(subprocess.TimeoutExpired):
                repro.run_probe(
                    args,
                    Path("/unused/proton"),
                    "baseline",
                    "rtspt://localhost/fixture",
                    "test-value",
                )
            self.assertEqual(list(Path(d).iterdir()), [])
            selected_prefix = Path(stop.call_args.kwargs["env"]["WINEPREFIX"])
            self.assertEqual(selected_prefix.parent.parent, Path(d))

    def test_wrong_binary_never_changes_input_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d) / "original.dll", Path(d) / "patched.dll"
            source.write_bytes(b"unsupported binary")
            output.write_bytes(b"keep this")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                patch_binary.patch(source, output)
            self.assertEqual(source.read_bytes(), b"unsupported binary")
            self.assertEqual(output.read_bytes(), b"keep this")

    def test_same_path_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "original.dll"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "separate"):
                patch_binary.patch(source, source)
            self.assertEqual(source.read_bytes(), b"original")

    def test_missing_dependency_is_explicit(self):
        with mock_patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Missing dependencies: docker"):
                repro.require("docker")

    def test_missing_video_token_does_not_fall_back_to_unrelated_secrets(self):
        with self.assertRaisesRegex(RuntimeError, "No Steam video token"):
            repro.video_token(None, {"STEAM_TOKEN": "unrelated-test-value"})

    def test_only_requested_process_token_is_returned(self):
        with tempfile.TemporaryDirectory() as d:
            process = Path(d) / "123"
            process.mkdir()
            (process / "environ").write_bytes(
                b"STEAMVIDEOTOKEN=test-value\0UNRELATED=not-copied\0"
            )
            self.assertEqual(repro.video_token(123, {}, Path(d)), "test-value")


if __name__ == "__main__":
    unittest.main()
