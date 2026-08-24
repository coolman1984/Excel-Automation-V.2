"""Create the safe example Excel files used by tests and demonstrations.

The data is invented. It contains a few deliberate problems (a duplicate line,
a negative quantity, a cancelled invoice, an unknown customer) so the quality,
quarantine and reconciliation paths are exercised by the golden test.
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.excel.xlsx_writer import write_sheet  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "projects", "example_sales", "fixtures")

SEGMENTS = ["Retail", "Wholesale", "Government"]
PRODUCTS = ["Pump", "Valve", "Filter", "Gasket", "Sensor"]


def build(seed: int = 11) -> tuple[str, str]:
    random.seed(seed)
    os.makedirs(OUT_DIR, exist_ok=True)

    customers = []
    for index in range(1, 13):
        customers.append([f"C{index:03d}", f"Customer {index:02d}",
                          SEGMENTS[index % len(SEGMENTS)], "Saudi Arabia"])

    sales = []
    invoice = 1000
    for month in (1, 2, 3):
        for _ in range(18):
            invoice += 1
            customer = random.choice(customers)[0]
            day = random.randint(1, 27)
            date = _dt.date(2026, month, day)
            for line in range(1, random.randint(2, 4)):
                quantity = random.randint(1, 25)
                price = round(random.uniform(15, 400), 2)
                amount = round(quantity * price, 2)
                sales.append([f"INV-{invoice}", line, date, customer,
                              random.choice(PRODUCTS), quantity, price, amount, "Posted"])

    # Deliberate, documented problems for the quality path:
    sales.append(["INV-1002", 1, _dt.date(2026, 1, 5), "C002", "Pump", 3, 100.0, 300.0, "Posted"])
    sales.append(["INV-9001", 1, _dt.date(2026, 3, 2), "C004", "Valve", -2, 50.0, -100.0, "Posted"])
    sales.append(["INV-9002", 1, _dt.date(2026, 3, 3), "C999", "Filter", 4, 25.0, 100.0, "Posted"])
    sales.append(["INV-9003", 1, _dt.date(2026, 3, 4), "C005", "Sensor", 1, 900.0, 900.0, "Cancelled"])

    sales_path = os.path.join(OUT_DIR, "sales_2026Q1.xlsx")
    customers_path = os.path.join(OUT_DIR, "customers.xlsx")
    write_sheet(sales_path,
                ["Invoice No", "Line", "Invoice Date", "Customer ID", "Product", "Quantity",
                 "Unit Price", "Amount", "Status"], sales, "Sales")
    write_sheet(customers_path, ["Customer ID", "Customer Name", "Segment", "Country"],
                customers, "Customers")
    return sales_path, customers_path


if __name__ == "__main__":
    for path in build():
        print("wrote", path)
