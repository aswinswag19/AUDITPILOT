"""
Deterministic Data Generator for AuditPilot (Phase 1).
Generates Dataset A and Dataset B with exact specified flaws, variations, and ground truth.
"""

import os
import csv
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

SEED = 42

def generate_datasets(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    
    # ---------------------------------------------------------
    # DATASET A: sales.csv, exchange_rates.csv, branches.csv, executive_summary.csv
    # ---------------------------------------------------------
    
    # 1. branches.csv
    branches_data = [
        {"branch_id": "BR001", "branch_name": "Chennai Main", "city": "chennai ", "region": "South"},
        {"branch_id": "BR002", "branch_name": "Chennai Anna Salai", "city": "CHENNAI", "region": "South"},
        {"branch_id": "BR003", "branch_name": "Mumbai Fort", "city": "Mumbai", "region": "West"},
        {"branch_id": "BR004", "branch_name": "Bengaluru Central", "city": "Bengaluru", "region": "South"}
    ]
    branches_path = output_dir / "branches.csv"
    with open(branches_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["branch_id", "branch_name", "city", "region"])
        writer.writeheader()
        writer.writerows(branches_data)

    # 2. exchange_rates.csv
    rates_data = [
        {"currency": "INR", "rate_to_inr": "1.00", "effective_date": "2025-01-01"},
        {"currency": "USD", "rate_to_inr": "82.50", "effective_date": "2025-09-01"},
        {"currency": "USD", "rate_to_inr": "83.00", "effective_date": "2025-11-01"},
        # No EUR rate included deliberately to trigger unsupported currency / missing rate rules
    ]
    rates_path = output_dir / "exchange_rates.csv"
    with open(rates_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["currency", "rate_to_inr", "effective_date"])
        writer.writeheader()
        writer.writerows(rates_data)

    # 3. sales.csv base transactions (~150 base transactions)
    # Entity variants for Chennai: "chennai ", "CHENNAI", "Chennai"
    branches_list = ["Chennai", "chennai ", "CHENNAI", "Mumbai", "Bengaluru"]
    products = ["Widget A", "Widget B", "Service X", "License Y"]
    
    sales_rows = []
    invoice_counter = 1001
    
    # Generate anchor dates in Q3 (Jul-Sep 2025) and Q4 (Oct-Dec 2025)
    # Let's ensure Q4 dates span Oct 1 to Dec 31, 2025
    
    # Let's create base transactions deterministically (146 base rows so plus 4 exact dups = 150 base + dups)
    for i in range(146):
        inv_id = f"INV-{invoice_counter}"
        invoice_counter += 1
        
        # Decide date format variant
        # at least 7 ambiguous slash dates (day and month both <= 12, e.g., 05/10/2025 -> could be May 10 or Oct 5)
        # unambiguous slash dates where day > 12 (e.g. 25/10/2025)
        if i < 7:
            # Ambiguous DD/MM vs MM/DD (e.g., 04/10/2025)
            day = rng.randint(1, 12)
            month = rng.randint(1, 12)
            date_str = f"{day:02d}/{month:02d}/2025"
        else:
            # Unambiguous or standard DD/MM/YYYY
            day = rng.randint(13, 28)
            month = rng.choice([9, 10, 11, 12]) # Q3 and Q4
            date_str = f"{day:02d}/{month:02d}/2025"
            
        branch = rng.choice(branches_list)
        product = rng.choice(products)
        amount = round(rng.uniform(1000.0, 50000.0), 2)
        currency = rng.choice(["INR", "USD", "USD", "EUR"]) # mix of INR, USD, EUR
        
        sales_rows.append({
            "invoice_id": inv_id,
            "order_date": date_str,
            "branch": branch,
            "product": product,
            "amount": str(amount),
            "currency": currency
        })

    # Save clean base list to compute ground truth later
    # Now inject required special anomalies:
    # - exactly 4 exact duplicate invoices (same invoice_id, order_date, branch, product, amount, currency)
    # Let's explicitly create 4 distinct rows with unique invoice_ids and append their exact copies once each.
    for dup_idx in range(4):
        dup_inv = f"INV-DUP-{dup_idx}"
        row = {
            "invoice_id": dup_inv,
            "order_date": "15/10/2025",
            "branch": "Chennai",
            "product": "Widget A",
            "amount": "1000.00",
            "currency": "INR"
        }
        sales_rows.append(row)
        sales_rows.append(row.copy()) # exact duplicate
        
    # - exactly 1 conflicting duplicate (same invoice_id, different amount)
    conflict_base = sales_rows[10].copy()
    conflict_row = conflict_base.copy()
    conflict_row["amount"] = str(float(conflict_base["amount"]) + 5000.0)
    sales_rows.append(conflict_base)
    sales_rows.append(conflict_row)
    
    # - exactly 2 missing order_date rows
    sales_rows[20]["order_date"] = ""
    sales_rows[25]["order_date"] = ""
    
    # - exactly 2 EUR records already injected via choice, let's ensure at least 2 have currency="EUR"
    sales_rows[30]["currency"] = "EUR"
    sales_rows[35]["currency"] = "EUR"
    
    # - exactly 1 negative refund
    sales_rows[40]["amount"] = "-2500.00"
    sales_rows[40]["currency"] = "INR"

    # Shuffle deterministically
    rng.shuffle(sales_rows)

    sales_path = output_dir / "sales.csv"
    sales_fields = ["invoice_id", "order_date", "branch", "product", "amount", "currency"]
    with open(sales_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sales_fields)
        writer.writeheader()
        writer.writerows(sales_rows)

    # 4. executive_summary.csv
    # Q4 executive summary value must deliberately differ from verified raw result
    # We will compute true Q4 Chennai revenue during ground truth generation and offset it.
    exec_summary_path = output_dir / "executive_summary.csv"
    exec_fields = ["quarter", "reported_revenue_inr", "source"]
    
    # We'll write placeholder or preliminary summary, then update once ground truth is computed.
    # For now write standard structure.
    exec_rows = [
        {"quarter": "Q3_2025", "reported_revenue_inr": "1500000.00", "source": "Legacy ERP"},
        {"quarter": "Q4_2025", "reported_revenue_inr": "99999999.00", "source": "Manual Rollup"} # Discrepancy value
    ]
    with open(exec_summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=exec_fields)
        writer.writeheader()
        writer.writerows(exec_rows)

    # ---------------------------------------------------------
    # DATASET B: orders.csv, customers.csv, refunds.csv, exchange_rates_b.csv, mapping json
    # ---------------------------------------------------------
    # Schema differs from Dataset A, has EUR and INR, unit_multiplier = 10 (amounts in thousands)
    dataset_b_dir = output_dir / "dataset_b"
    dataset_b_dir.mkdir(parents=True, exist_ok=True)
    
    b_rates = [
        {"cur": "INR", "rate": "1.0", "dt": "2025-01-01"},
        {"cur": "EUR", "rate": "90.0", "dt": "2025-01-01"}
    ]
    with open(dataset_b_dir / "exchange_rates_b.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cur", "rate", "dt"])
        writer.writeheader()
        writer.writerows(b_rates)
        
    b_customers = [
        {"cust_id": "C01", "name": "Acme Corp", "loc": "Delhi"},
        {"cust_id": "C02", "name": "Globex", "loc": "Mumbai"}
    ]
    with open(dataset_b_dir / "customers.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cust_id", "name", "loc"])
        writer.writeheader()
        writer.writerows(b_customers)
        
    b_refunds = [
        {"ref_id": "ORD-501", "ref_amt": "150.0", "ref_dt": "15/10/2025"}
    ]
    with open(dataset_b_dir / "refunds.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ref_id", "ref_amt", "ref_dt"])
        writer.writeheader()
        writer.writerows(b_refunds)

    b_orders = [
        {"order_id": "ORD-501", "order_date": "10/10/2025", "customer_id": "C01", "region": "North", "amount": "1200.0", "currency": "INR"},
        {"order_id": "ORD-502", "order_date": "12/10/2025", "customer_id": "C02", "region": "West", "amount": "450.0", "currency": "EUR"},
        {"order_id": "ORD-503", "order_date": "20/10/2025", "customer_id": "C01", "region": "North", "amount": "800.0", "currency": "INR"}
    ]
    with open(dataset_b_dir / "orders.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["order_id", "order_date", "customer_id", "region", "amount", "currency"])
        writer.writeheader()
        writer.writerows(b_orders)
        
    dataset_b_mapping = {
        "transactions_table": "orders.csv",
        "key_column": "order_id",
        "date_column": "order_date",
        "entity_column": "region",
        "amount_column": "amount",
        "currency_column": "currency",
        "rates_table": "exchange_rates_b.csv",
        "rate_currency_column": "cur",
        "rate_value_column": "rate",
        "rate_effective_date_column": "dt",
        "refunds_table": "refunds.csv",
        "refund_key_column": "ref_id",
        "refund_amount_column": "ref_amt",
        "refund_date_column": "ref_dt",
        "unit_multiplier": 10
    }
    with open(dataset_b_dir / "dataset_b_mapping.json", "w", encoding="utf-8") as f:
        json.dump(dataset_b_mapping, f, indent=2)

    return sales_rows, rates_data

if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent.parent / "data"
    generate_datasets(data_dir)
    print("Datasets generated successfully.")
