"""Load synthetic CSVs into DuckDB for dbt to consume as seeds/sources.

This script copies all generated CSVs into the dbt seeds directory
so that `dbt seed` can load them into the raw schema.

Usage:
    python data/load_seeds.py
"""

import glob
import os
import shutil


def main():
    synthetic_dir = os.path.join(os.path.dirname(__file__), "synthetic")
    seed_dir = os.path.join(os.path.dirname(__file__), "..", "transform", "dbt", "seeds")

    os.makedirs(seed_dir, exist_ok=True)

    csv_files = glob.glob(os.path.join(synthetic_dir, "*.csv"))
    if not csv_files:
        print("No CSV files found. Run 'python data/synthetic/generate.py' first.")
        return

    for csv_path in csv_files:
        filename = os.path.basename(csv_path)
        dest = os.path.join(seed_dir, filename)
        shutil.copy2(csv_path, dest)
        size_mb = os.path.getsize(csv_path) / (1024 * 1024)
        print(f"  Copied {filename} ({size_mb:.1f} MB)")

    print(f"\nDone! {len(csv_files)} files copied to {seed_dir}")
    print("Run 'cd transform/dbt && dbt seed --profiles-dir .' to load into DuckDB.")


if __name__ == "__main__":
    main()
