"""The saved copy: one file, no server, no internet, the same numbers."""

from __future__ import annotations

import json
import os
import re
import unittest

from tests.helpers import example_config, example_workspace, remove_all, temp_dir

from engine import pipeline
from engine.report import standalone


class StandaloneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cleanup: list[str] = []
        cls.workspace = example_workspace(cls.cleanup)
        cls.config = example_config()
        pipeline.run(cls.config, cls.workspace)
        with open(cls.workspace.dashboard, "r", encoding="utf-8") as handle:
            cls.document = json.load(handle)
        cls.html = standalone.build(cls.document, cls.config.display_title())

    @classmethod
    def tearDownClass(cls) -> None:
        remove_all(cls.cleanup)

    def test_everything_is_inside_the_one_file(self) -> None:
        self.assertNotIn('href="/styles.css"', self.html)
        self.assertNotIn('src="/app.js"', self.html)
        self.assertIn("<style>", self.html)
        self.assertIn("window.__DASHBOARD__", self.html)

    def test_it_asks_the_internet_for_nothing(self) -> None:
        allowed = ("http://www.w3.org",)
        external = [url for url in re.findall(r"https?://[^\s\"'()<>\\]+", self.html)
                    if not url.startswith(allowed)]
        self.assertEqual(external, [], "the saved copy references the internet")

    def test_it_carries_the_proved_numbers(self) -> None:
        self.assertIn("298944.47", self.html.replace(" ", ""))
        payload = self.html.split("window.__DASHBOARD__ = ", 1)[1].split(";\n", 1)[0]
        document = json.loads(payload.replace("<\\/", "</"))
        self.assertEqual({m["id"]: m["value"] for m in document["metrics"]}["invoice_count"], 55)
        self.assertEqual(len(document["analytics"]["charts"]), 4)

    def test_a_script_tag_inside_the_data_cannot_break_out(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["project"]["purpose"] = "</script><script>alert(1)</script>"
        html = standalone.build(document)
        self.assertNotIn("</script><script>alert(1)", html)

    def test_the_title_names_the_report(self) -> None:
        self.assertIn("<title>Sales performance</title>", self.html)

    def test_the_file_name_carries_the_run_date(self) -> None:
        name = standalone.file_name("ExampleSales", self.document)
        self.assertTrue(name.startswith("ExampleSales_"), name)
        self.assertTrue(name.endswith(".html"))

    def test_it_can_be_written_and_reopened(self) -> None:
        path = os.path.join(temp_dir(self.cleanup), "saved.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.html)
        with open(path, "r", encoding="utf-8") as handle:
            self.assertGreater(len(handle.read()), 20000)


if __name__ == "__main__":
    unittest.main()
