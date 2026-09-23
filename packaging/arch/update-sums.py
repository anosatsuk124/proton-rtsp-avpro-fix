#!/usr/bin/env python3
"""Rewrite sha256sums in PKGBUILD from versions.lock.json and the local source files."""

import hashlib
import json
import re
from pathlib import Path

here = Path(__file__).resolve().parent
pkgbuild = here / "PKGBUILD"
text = pkgbuild.read_text()
lock = json.loads((here / "versions.lock.json").read_text())
block = text.split("source=(", 1)[1].split(")", 1)[0]
sources = [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", block)]
sums = [lock["proton"]["archive_sha256"]]
sums += [hashlib.sha256((here / name).read_bytes()).hexdigest() for name in sources[1:]]
new_block = "sha256sums=(" + "\n  ".join(f"'{s}'" for s in sums) + ")"
text = re.sub(r"sha256sums=\([^)]*\)", new_block, text, count=1)
pkgbuild.write_text(text)
print("\n".join(f"{s}  {n}" for s, n in zip(sums, sources)))
