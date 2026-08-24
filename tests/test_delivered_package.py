"""The end-to-end proof: build the ZIP, extract it, start it, use it.

This is the closest thing to the final user's experience that can run without
Windows. It uses the extracted package exactly as delivered - its own copy of
the engine, its own project configuration and its own Data folder.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import unittest
import urllib.request
import zipfile

from tests.helpers import EXAMPLE_PROJECT, FIXTURES, remove_all, temp_dir

from engine.packaging import builder, verifier


class DeliveredPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleanup: list[str] = []
        work = temp_dir(cls.cleanup)

        runtime = os.path.join(work, "runtime")
        os.makedirs(runtime)
        for name in ("python.exe", "pythonw.exe"):
            with open(os.path.join(runtime, name), "wb") as handle:
                handle.write(b"placeholder for the Windows embeddable runtime")

        app_dir = os.path.join(work, "app")
        builder.stage_application(EXAMPLE_PROJECT, app_dir, runtime)
        built = builder.build("ExampleSales", app_dir, os.path.join(work, "release"))
        cls.verification = verifier.verify(built.zip_path)

        cls.extracted = os.path.join(work, "extracted")
        with zipfile.ZipFile(built.zip_path) as archive:
            archive.extractall(cls.extracted)
        cls.package_root = os.path.join(cls.extracted, "ExampleSales")

        cls.process = subprocess.Popen(
            [sys.executable, os.path.join(cls.package_root, "Application", "app", "launch.py"),
             "--no-browser", "--port", "0"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=dict(os.environ, PYTHONUNBUFFERED="1"))
        cls.url = None
        deadline = time.time() + 30
        while time.time() < deadline:
            line = cls.process.stdout.readline()
            if not line:
                break
            match = re.search(r"(http://127\.0\.0\.1:\d+/\?k=[\w\-]+)", line)
            if match:
                cls.url = match.group(1)
                break
        assert cls.url, "the packaged application did not report its address"
        cls.base, cls.key = cls.url.split("/?k=")[0], cls.url.split("/?k=")[1]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.call("/api/shutdown", {})
        except Exception:
            pass
        cls.process.terminate()
        cls.process.wait(timeout=10)
        remove_all(cls.cleanup)

    @classmethod
    def call(cls, path: str, payload=None):
        separator = "&" if "?" in path else "?"
        request = urllib.request.Request(
            f"{cls.base}{path}{separator}k={cls.key}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())

    # -- the shape the user receives ---------------------------------------
    def test_the_user_sees_only_three_things(self) -> None:
        self.assertEqual(sorted(os.listdir(self.package_root)),
                         ["Application", "QUICK_START.html", "START.bat"])

    def test_the_package_passes_verification(self) -> None:
        self.assertTrue(self.verification.ok, self.verification.report())

    def test_quick_start_never_mentions_a_technical_step(self) -> None:
        with open(os.path.join(self.package_root, "QUICK_START.html"), "r",
                  encoding="utf-8") as handle:
            raw = handle.read()
        visible = re.sub(r"<style.*?</style>|<[^>]+>", " ", raw, flags=re.S).lower()
        # Saying "there is nothing to install" is reassurance, not an instruction.
        visible = visible.replace("nothing to install", "")
        for word in ("python", "pip", "sql", "terminal", "install", "port", "git",
                     "configuration", "administrator", "database", "server"):
            self.assertIsNone(re.search(rf"\b{word}", visible),
                              f"QUICK_START.html mentions '{word}'")

    # -- the user's journey ------------------------------------------------
    def test_extract_start_add_files_process_and_trust_the_result(self) -> None:
        payload = []
        for name in ("sales_2026Q1.xlsx", "customers.xlsx"):
            with open(os.path.join(FIXTURES, name), "rb") as handle:
                payload.append({"name": name,
                                "content_base64": base64.b64encode(handle.read()).decode()})
        self.call("/api/files", {"files": payload})
        self.assertTrue(self.call("/api/process", {})["started"])

        progress = {"busy": True}
        for _ in range(240):
            progress = self.call("/api/progress")
            if not progress["busy"]:
                break
            time.sleep(0.25)
        self.assertFalse(progress["busy"], "the run never finished")
        self.assertIn(progress["result"]["status"], ("PASS", "WARNING"))

        dashboard = self.call("/api/dashboard")
        values = {metric["id"]: metric["value"] for metric in dashboard["metrics"]}
        self.assertAlmostEqual(values["total_amount"], 298944.47, places=2)
        self.assertEqual(values["invoice_count"], 55)
        analytics = dashboard["analytics"]
        self.assertEqual(len(analytics["charts"]), 4)
        self.assertEqual(analytics["periods"], ["2026-01", "2026-02", "2026-03"])
        self.assertTrue(dashboard["reconciliation"])
        self.assertTrue(all(check["status"] in ("PASS", "WARNING")
                            for check in dashboard["reconciliation"]))

    def test_the_application_keeps_its_data_inside_the_package(self) -> None:
        data_dir = os.path.join(self.package_root, "Application", "Data")
        self.assertTrue(os.path.isdir(data_dir))
        self.assertTrue(os.path.isfile(os.path.join(data_dir, "data", "warehouse.db")))


if __name__ == "__main__":
    unittest.main()
