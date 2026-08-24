"""Reproduce two real-world edge cases against the shipped V14 engine."""
import datetime as dt, os, shutil, sys, json
sys.path.insert(0, os.getcwd())
from engine.excel.xlsx_writer import write_sheet

BASE = "/tmp/claude-0/-home-user-Excel-Automation-V-2/48826f72-f994-5b45-91c4-bf4492b21161/scratchpad/edge"
shutil.rmtree(BASE, ignore_errors=True)
HEAD = ["Invoice No","Line","Invoice Date","Customer ID","Product","Quantity","Unit Price","Amount","Status"]

rows_a = [["INV-1", 1, dt.date(2026,1,5), "C001", "Pump", 2, 100.0, 200.0, "Posted"],
          ["INV-2", 1, dt.date(2026,1,6), "C002", "Valve", 3, 100.0, 300.0, "Posted"]]
subtotal = ["Subtotal", None, None, None, None, 5, None, 500.0, None]
rows_b = [["INV-3", 1, dt.date(2026,2,7), "C001", "Filter", 1, 100.0, 100.0, "Posted"]]
grand   = ["TOTAL", None, None, None, None, 6, None, 600.0, None]

# --- CASE 1: subtotal + grand-total rows inside the data block -----------------
c1 = os.path.join(BASE, "case1"); os.makedirs(c1, exist_ok=True)
write_sheet(os.path.join(c1, "sales_totals.xlsx"), HEAD, rows_a + [subtotal] + rows_b + [grand], "Sales")
write_sheet(os.path.join(c1, "customers.xlsx"),
            ["Customer ID","Customer Name","Segment","Country"],
            [["C001","Customer 01","Retail","Saudi Arabia"],["C002","Customer 02","Retail","Saudi Arabia"]],
            "Customers")

# --- CASE 2: one extra title/banner row above the header ----------------------
c2 = os.path.join(BASE, "case2"); os.makedirs(c2, exist_ok=True)
write_sheet(os.path.join(c2, "sales_banner.xlsx"), ["Monthly Sales Export - Confidential"],
            [HEAD] + rows_a + rows_b, "Sales")
write_sheet(os.path.join(c2, "customers.xlsx"),
            ["Customer ID","Customer Name","Segment","Country"],
            [["C001","Customer 01","Retail","Saudi Arabia"],["C002","Customer 02","Retail","Saudi Arabia"]],
            "Customers")
print("fixtures written")
