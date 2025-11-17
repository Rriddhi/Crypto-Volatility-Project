#!/usr/bin/env python3
"""Quick script to check features Parquet file."""
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

parquet_path = Path("data/processed/features.parquet")

if not parquet_path.exists():
    print(f"Parquet file not found: {parquet_path}")
    exit(1)

print(f"File size: {parquet_path.stat().st_size} bytes")

try:
    # Try reading with pyarrow first to see if file is valid
    parquet_file = pq.ParquetFile(parquet_path)
    print(f"Parquet file metadata:")
    print(f"  Schema: {parquet_file.schema}")
    print(f"  Num row groups: {parquet_file.num_row_groups}")
    
    # Read with pandas
    df = pd.read_parquet(parquet_path)
    print(f"\n✓ Successfully read Parquet file")
    print(f"Rows: {len(df)}")
    print(f"\nColumns: {df.columns.tolist()}")
    print(f"\nFirst 5 rows:")
    print(df.head())
    print(f"\nData types:")
    print(df.dtypes)
    if len(df) > 0:
        print(f"\nBasic stats:")
        print(df.describe())
except Exception as e:
    print(f"✗ Error reading Parquet: {e}")
    print(f"\nTrying to read raw file info...")
    import pyarrow as pa
    try:
        with open(parquet_path, 'rb') as f:
            data = f.read(100)
            print(f"First 100 bytes: {data[:50]}...")
    except Exception as e2:
        print(f"Could not read file: {e2}")

