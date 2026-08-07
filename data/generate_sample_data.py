import os
import random
import polars as pl
from datetime import datetime, timedelta

def generate_dirty_dataset(num_rows: int = 500_000, output_path: str = "data/raw/messy_sales_500k.csv"):
    """
    Generates a realistic, dirty enterprise dataset with:
    - Mixed date formats & null dates
    - Numbers disguised as currency strings ("$1,250.00", "N/A", "FREE")
    - Messy text with leading/trailing whitespaces and mixed casing
    - Duplicate primary keys
    - Inconsistent country names
    """
    print(f"🚀 Generating {num_rows:,} dirty rows...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    regions = ["  us ", "USA", "United States", "UK", "  united kingdom  ", "Germany", "GER", "N/A", None]
    product_categories = ["Electronics", "home appliances", "FURNITURE", "Clothing", " toys & games "]
    bad_revenue_values = ["$1,250.00", "$45.50", "N/A", " - ", "FREE", "$0.00", "$9,999.99", None]
    
    # Generate base lists
    order_ids = [f"ORD-{random.randint(100000, 100000 + int(num_rows * 0.85))}" for _ in range(num_rows)] # Intentional duplicates
    customer_names = [f"  Customer_{random.randint(1, 50000)}  " for _ in range(num_rows)]
    
    # Mixed date strings
    base_date = datetime(2023, 1, 1)
    dates = []
    for _ in range(num_rows):
        d = base_date + timedelta(days=random.randint(0, 730))
        fmt = random.choice(["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y", "NULL"])
        dates.append(d.strftime(fmt) if fmt != "NULL" else None)
        
    revenues = [random.choice(bad_revenue_values) if random.random() < 0.15 else f"${round(random.uniform(10.0, 5000.0), 2):,}" for _ in range(num_rows)]
    quantities = [random.choice(["1", "2", "5", "-1", "0", "N/A", None]) for _ in range(num_rows)]
    chosen_regions = [random.choice(regions) for _ in range(num_rows)]
    categories = [random.choice(product_categories) for _ in range(num_rows)]

    # Use Polars to construct and dump fast
    df = pl.DataFrame({
        "order_id": order_ids,
        "customer_name": customer_names,
        "order_date": dates,
        "revenue": revenues,
        "quantity": quantities,
        "region": chosen_regions,
        "category": categories
    })

    df.write_csv(output_path)
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ Generated {num_rows:,} rows successfully!")
    print(f"📁 Saved to: {output_path} ({file_size_mb:.2f} MB)")

if __name__ == "__main__":
    generate_dirty_dataset(num_rows=500_000)