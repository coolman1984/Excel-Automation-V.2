"""The private-runtime build helper must fail closed before it ever reaches a user."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import prepare_windows_runtime as prep


class RuntimePreparationTest(unittest.TestCase):
    def test_manifest_is_pinned_and_https_only(self) -> None:
        data = json.loads(prep.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["architecture"], "win_amd64")
        ids = {item["id"] for item in data["artifacts"]}
        self.assertEqual(ids, {"python", "duckdb", "pywin32", "pyodbc"})
        for item in data["artifacts"]:
            self.assertTrue(item["url"].startswith("https://"))
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")

    def test_extract_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            archive = Path(work) / "bad.whl"
            output = Path(work) / "out"
            output.mkdir()
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "x")
            with self.assertRaises(RuntimeError):
                prep.extract(archive, output)

    def test_sha256_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "x"
            path.write_bytes(b"abc")
            self.assertEqual(
                prep.sha256(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )


if __name__ == "__main__":
    unittest.main()
