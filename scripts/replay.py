#!/usr/bin/env python3
"""
Replay script to regenerate features from saved raw NDJSON files.

This script reads raw ticker data from NDJSON files, computes features
using the same logic as the live Kafka consumer, and writes them to Parquet.

The output should be bit-for-bit identical to features computed by the
live featurizer for the same input data.
"""
import argparse
import glob
import json
import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Import shared feature calculation logic
import sys
from pathlib import Path as PathLib

# Add project root to path to import from features
project_root = PathLib(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from features.featurizer import (
    FeatureCalculator,
    parse_tick_message,
    FeatureConfig,
    DEFAULT_WINDOW_SIZE,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_raw_files(glob_pattern: str) -> List[dict]:
    """
    Load all raw NDJSON files matching the glob pattern.
    
    Args:
        glob_pattern: Glob pattern for NDJSON files (e.g., "data/raw/*.ndjson")
    
    Returns:
        List of parsed tick dictionaries, sorted by timestamp
    """
    files = sorted(glob.glob(glob_pattern))
    if not files:
        logger.warning(f"No files found matching pattern: {glob_pattern}")
        return []
    
    logger.info(f"Found {len(files)} files matching pattern: {glob_pattern}")
    
    all_ticks = []
    for filepath in files:
        logger.info(f"Loading {filepath}...")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                line_count = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse using the same function as live consumer
                    tick = parse_tick_message(line.encode("utf-8"))
                    if tick is not None:
                        all_ticks.append(tick)
                        line_count += 1
                
                logger.info(f"  Loaded {line_count} valid ticks from {filepath}")
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            continue
    
    logger.info(f"Total ticks loaded: {len(all_ticks)}")
    
    # Sort by timestamp to ensure consistent processing order
    all_ticks.sort(key=lambda x: x["timestamp"])
    
    return all_ticks


def compute_features_replay(
    ticks: List[dict],
    window_size: int = DEFAULT_WINDOW_SIZE,
    output_path: Optional[Path] = None,
    batch_size: int = 5000,
) -> List[dict]:
    """
    Compute features for all ticks using the same logic as live consumer.
    Writes features in batches to avoid losing progress.
    
    Args:
        ticks: List of parsed tick dictionaries
        window_size: Window size for feature computation
        output_path: Optional path to write batches incrementally
        batch_size: Number of features to accumulate before writing a batch
    
    Returns:
        List of all feature dictionaries
    """
    if not ticks:
        logger.warning("No ticks to process")
        return []
    
    # Initialize feature calculator (same as live consumer)
    calculator = FeatureCalculator(window_size=window_size)
    
    all_features = []
    batch_features = []
    product_ids = set()
    
    logger.info(f"Computing features for {len(ticks)} ticks with window_size={window_size}...")
    if output_path:
        logger.info(f"Will write batches of {batch_size} features to {output_path}")
    
    for i, tick in enumerate(ticks):
        product_id = tick["product_id"]
        product_ids.add(product_id)
        
        # Add tick to calculator (same as live consumer)
        calculator.add_tick(tick)
        
        # Compute features (same as live consumer)
        # Note: Only compute after we have at least 2 ticks (same requirement as live)
        feature = calculator.compute_features(product_id)
        
        if feature is not None:
            batch_features.append(feature)
            all_features.append(feature)
            
            # Write batch if we've accumulated enough
            if output_path and len(batch_features) >= batch_size:
                _append_batch_to_parquet(batch_features, output_path)
                batch_features = []  # Clear batch after writing
        
        # Progress logging
        if (i + 1) % 1000 == 0:
            logger.info(
                f"Processed {i + 1}/{len(ticks)} ticks, computed {len(all_features)} features"
            )
    
    # Write any remaining features in the batch
    if output_path and batch_features:
        _append_batch_to_parquet(batch_features, output_path)
        batch_features = []
    
    logger.info(
        f"Feature computation complete: {len(all_features)} features from {len(ticks)} ticks "
        f"across {len(product_ids)} product(s): {sorted(product_ids)}"
    )
    
    return all_features


def _append_batch_to_parquet(features: List[dict], output_path: Path) -> None:
    """
    Append a batch of features to existing Parquet file, or create new one.
    
    Args:
        features: List of feature dictionaries to append
        output_path: Path to Parquet file
    """
    if not features:
        return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to DataFrame
    df = pd.DataFrame(features)
    if "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].astype(str)
    
    # Read existing data if file exists
    if output_path.exists():
        try:
            existing_df = pd.read_parquet(output_path)
            df = pd.concat([existing_df, df], ignore_index=True)
        except Exception as e:
            logger.warning(f"Could not read existing Parquet, creating new: {e}")
    
    # Write combined data
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(
        table,
        output_path,
        use_dictionary=True,
        compression='snappy'
    )
    logger.debug(f"Appended {len(features)} features to {output_path} (total: {len(df)})")


def write_features_parquet(features: List[dict], output_path: Path) -> None:
    """
    Write features to Parquet file.
    
    Args:
        features: List of feature dictionaries
        output_path: Path to output Parquet file
    """
    if not features:
        logger.warning("No features to write")
        return
    
    logger.info(f"Writing {len(features)} features to {output_path}...")
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to DataFrame
    df = pd.DataFrame(features)
    
    # Ensure timestamp is string (same as live consumer)
    if "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].astype(str)
    
    # Write to Parquet (same format as live consumer)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(
        table,
        output_path,
        use_dictionary=True,
        compression='snappy'
    )
    
    logger.info(f"✓ Successfully wrote {len(features)} features to {output_path}")
    logger.info(f"  File size: {output_path.stat().st_size / 1024:.2f} KB")
    logger.info(f"  Columns: {df.columns.tolist()}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Replay raw NDJSON files to regenerate features using the same logic as live consumer."
    )
    parser.add_argument(
        "--raw_glob",
        type=str,
        default="data/raw/*.ndjson",
        help="Glob pattern for raw NDJSON files (default: data/raw/*.ndjson)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="data/processed/features_replay.parquet",
        help="Output Parquet file path (default: data/processed/features_replay.parquet)",
    )
    parser.add_argument(
        "--window_size",
        type=int,
        default=DEFAULT_WINDOW_SIZE,
        help=f"Window size for feature computation (default: {DEFAULT_WINDOW_SIZE})",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=5000,
        help="Number of features to accumulate before writing a batch (default: 5000)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load raw files
    ticks = load_raw_files(args.raw_glob)
    
    if not ticks:
        logger.error("No ticks loaded. Exiting.")
        return
    
    # Compute features using same logic as live consumer
    # Features are written in batches during computation
    output_path = Path(args.out)
    features = compute_features_replay(
        ticks,
        window_size=args.window_size,
        output_path=output_path,
        batch_size=args.batch_size,
    )
    
    if not features:
        logger.warning("No features computed. Exiting.")
        return
    
    # Final summary
    logger.info(f"✓ Total features computed: {len(features)}")
    if output_path.exists():
        logger.info(f"✓ Features written to: {output_path}")
        logger.info(f"  File size: {output_path.stat().st_size / 1024:.2f} KB")
        
        # Quick validation
        try:
            df = pd.read_parquet(output_path)
            logger.info(f"  Rows in file: {len(df)}")
            logger.info(f"  Columns: {df.columns.tolist()}")
        except Exception as e:
            logger.warning(f"  Could not validate file: {e}")
    
    logger.info("✓ Replay complete!")


if __name__ == "__main__":
    main()

