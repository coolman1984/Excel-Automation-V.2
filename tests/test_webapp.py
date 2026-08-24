"""The local application boundary: loopback only, key protected, no surprises."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request

from tests.helpers import FIXTURES, example_config, example_workspace, remove_all

from engine.webapp import server as server_module


class WebAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleanup: list[str] = []
        cls.workspace = example_workspace(cls.cleanup, with_fixtures=False)
        cls.server, cls.application = server_module.make_server(example_config(), cls.workspace)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address[0], cls.server.server_address[1]
        cls.base = f"http://{host}:{port}"
        cls.key = cls.application.session_key

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        remove_all(cls.cleanup)

    def call(self, path: str, payload=None, key: str | None = "__default__"):
        key = self.key if key == "__default__" else key
        separator = "&" if "?" in path else "?"
        url = f"{self.base}{path}{separator}k={key}" if key is not None else f"{self.base}{path}"
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())

    def test_binds_to_loopback_only(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_health_needs_no_key(self) -> None:
        with urllib.request.urlopen(f"{self.base}/api/health", timeout=10) as response:
            self.assertTrue(json.loads(response.read().decode())["ok"])

    def test_api_without_the_session_key_is_refused(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/state", key=None)
        self.assertEqual(caught.exception.code, 403)

    def test_api_with_a_wrong_key_is_refused(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/state", key="not-the-key")
        self.assertEqual(caught.exception.code, 403)

    def test_page_is_served_from_local_files_only(self) -> None:
        """No asset may come from the internet: the machine may be fully offline."""

        import re

        allowed = ("http://www.w3.org", "http://127.0.0.1")
        for asset in ("/", "/app.js", "/styles.css"):
            with urllib.request.urlopen(f"{self.base}{asset}", timeout=10) as response:
                body = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            external = [url for url in re.findall(r"https?://[^\s\"'()<>]+", body)
                        if not url.startswith(allowed)]
            self.assertEqual(external, [], f"{asset} references the internet")

    def test_directory_traversal_is_refused(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.base}/../engine/cli.py", timeout=10)
        self.assertEqual(caught.exception.code, 404)

    def test_state_tells_the_page_what_is_expected(self) -> None:
        state = self.call("/api/state")
        self.assertEqual(state["project"]["name"], "ExampleSales")
        patterns = [source["patterns"] for source in state["expected_files"]]
        self.assertIn(["sales_*.xlsx"], patterns)

    def test_a_wrong_file_type_is_refused_in_plain_language(self) -> None:
        result = self.call("/api/files", {"files": [
            {"name": "notes.exe", "content_base64": base64.b64encode(b"x").decode()}]})
        self.assertEqual(result["added"], [])
        self.assertIn("not a file type", result["errors"][0]["what_happened"])

    def test_upload_process_and_export(self) -> None:
        payload = []
        for name in ("sales_2026Q1.xlsx", "customers.xlsx"):
            with open(os.path.join(FIXTURES, name), "rb") as handle:
                payload.append({"name": name,
                                "content_base64": base64.b64encode(handle.read()).decode()})
        uploaded = self.call("/api/files", {"files": payload})
        self.assertEqual({item["name"] for item in uploaded["inbox"]},
                         {"sales_2026Q1.xlsx", "customers.xlsx"})

        self.assertTrue(self.call("/api/process", {})["started"])
        for _ in range(120):
            progress = self.call("/api/progress")
            if not progress["busy"]:
                break
            time.sleep(0.25)
        self.assertFalse(progress["busy"])
        self.assertEqual(progress["result"]["status"], "WARNING")

        dashboard = self.call("/api/dashboard")
        # The displayed KPI is the one filtering cannot answer; the filterable
        # measures travel in the analytics cube.
        self.assertEqual({kpi["id"] for kpi in dashboard["kpis"]}, {"customers_served"})
        self.assertEqual({metric["id"] for metric in dashboard["metrics"]},
                         {"total_amount", "invoice_count", "average_invoice_value",
                          "customers_served"})
        self.assertEqual({measure["id"] for measure in dashboard["analytics"]["measures"]},
                         {"revenue", "units", "lines", "average_line"})

        with urllib.request.urlopen(
                f"{self.base}/api/export/top_customers.csv?k={self.key}", timeout=10) as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertIn("Customer", response.read().decode("utf-8-sig").splitlines()[0])

        removed = self.call("/api/files/remove", {"name": "customers.xlsx"})
        self.assertTrue(removed["removed"])

    def test_unknown_endpoint_is_a_clean_404(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call("/api/does-not-exist")
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
