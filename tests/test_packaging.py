"""Keep the packaging metadata consistent with versions.lock.json and free of machine-specific paths."""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "versions.lock.json").read_text())
PKGBUILD = (ROOT / "packaging/arch/PKGBUILD").read_text()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PackagingTests(unittest.TestCase):
    def test_pkgbuild_sources_match_lock_and_local_files(self):
        sources = re.findall(
            r"'([^']+)'|\"([^\"]+)\"", PKGBUILD.split("source=(", 1)[1].split(")", 1)[0]
        )
        sources = [a or b for a, b in sources]
        sums = re.findall(
            r"'([0-9a-f]{64})'", PKGBUILD.split("sha256sums=(", 1)[1].split(")", 1)[0]
        )
        self.assertEqual(len(sources), len(sums))
        self.assertEqual(
            sources[0].split("::", 1)[1].replace("${_release}", LOCK["proton"]["name"]),
            LOCK["proton"]["url"],
        )
        self.assertEqual(sums[0], LOCK["proton"]["archive_sha256"])
        for name, digest in zip(sources[1:], sums[1:]):
            with self.subTest(file=name):
                self.assertEqual(sha(ROOT / "packaging/arch" / name), digest)

    def test_pkgbuild_names_follow_lock(self):
        self.assertIn(f"_release={LOCK['proton']['name']}\n", PKGBUILD)
        self.assertIn("pkgver=11.0.20260609.4\n", PKGBUILD)
        self.assertIn(
            "version=11.0.20260609.4-1\n",
            (ROOT / "packaging/deb/build-deb.sh").read_text(),
        )

    def test_no_machine_specific_paths(self):
        # Assembled at runtime so this file does not itself contain the patterns.
        forbidden = "|".join(("/" + "home" + "/", "~/" + "Work", "/" + "Users" + "/"))
        listing = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.decode()
        files = [ROOT / name for name in listing.split("\0") if name]
        checked = 0
        for path in files:
            if not path.is_file() or path.is_symlink():
                continue
            checked += 1
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertNotRegex(path.read_text(errors="replace"), forbidden)
        self.assertGreater(checked, 10)


if __name__ == "__main__":
    unittest.main()
