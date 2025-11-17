#!/usr/bin/env python3
"""
Compare live features vs replay features to verify they are effectively identical.

Loads data/processed/features.parquet (live) and data/processed/features_replay.parquet (replay),
joins on timestamp + product_id, and computes summary statistics.
"""
import argparse
import logging
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_project_root() -> Path:
    """Find project root directory."""
    current = Path(__file__).resolve()
    # Go up from scripts/ to project root
    project_root = current.parent.parent
    if (project_root / "data" / "processed").exists():
        return project_root
    # Fallback: try current directory
    if (Path.cwd() / "data" / "processed").exists():
        return Path.cwd()
    return project_root


def load_features(parquet_path: Path) -> pd.DataFrame:
    """Load features from Parquet file."""
    logger.info(f"Loading features from {parquet_path}...")
    if not parquet_path.exists():
        raise FileNotFoundError(f"Features file not found: {parquet_path}")
    
    # Try to read with pandas first
    df = None
    error_msgs = []
    
    try:
        df = pd.read_parquet(parquet_path)
        logger.info("Successfully read with default pandas method")
    except (OSError, Exception) as e:
        error_msgs.append(f"Default method: {e}")
        logger.warning(f"Error reading parquet with default method: {e}")
        logger.info("Trying alternative reading methods...")
        
        # Try with pyarrow directly and ignore metadata
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(parquet_path, use_pandas_metadata=False)
            df = table.to_pandas()
            logger.info("Successfully read with pyarrow (ignoring metadata)")
        except Exception as e2:
            error_msgs.append(f"PyArrow method: {e2}")
            logger.warning(f"PyArrow method failed: {e2}")
            
            # Try reading row groups individually
            try:
                import pyarrow.parquet as pq
                parquet_file = pq.ParquetFile(parquet_path)
                # Read all row groups
                tables = []
                for i in range(parquet_file.num_row_groups):
                    tables.append(parquet_file.read_row_group(i))
                if tables:
                    import pyarrow as pa
                    combined_table = pa.concat_tables(tables)
                    df = combined_table.to_pandas()
                    logger.info("Successfully read by reading row groups individually")
            except Exception as e3:
                error_msgs.append(f"Row group method: {e3}")
                logger.warning(f"Row group method failed: {e3}")
                
                # Try with fastparquet engine if available
                try:
                    df = pd.read_parquet(parquet_path, engine='fastparquet')
                    logger.info("Successfully read with fastparquet engine")
                except (ImportError, Exception) as e4:
                    error_msgs.append(f"Fastparquet method: {e4}")
                    # Check if this is a PyArrow version issue
                    import sys
                    pyarrow_version = None
                    try:
                        import pyarrow as pa
                        pyarrow_version = pa.__version__
                    except:
                        pass
                    
                    error_msg = (
                        f"Failed to read parquet file {parquet_path}.\n"
                        f"Tried multiple methods:\n" + "\n".join(f"  - {msg}" for msg in error_msgs) + "\n"
                    )
                    if pyarrow_version:
                        error_msg += f"PyArrow version: {pyarrow_version}\n"
                    error_msg += (
                        f"The file may be corrupted or incompatible with current PyArrow version.\n"
                        f"Suggestions:\n"
                        f"  1. Try using the conda environment: conda run -n crypto_volatility python scripts/compare_live_vs_replay.py\n"
                        f"  2. Regenerate the parquet file\n"
                        f"  3. Update or downgrade PyArrow: pip install pyarrow==<version>"
                    )
                    raise IOError(error_msg) from e4
    
    if df is None:
        raise IOError(f"Failed to read parquet file {parquet_path} - no method succeeded")
    
    logger.info(f"Loaded {len(df)} rows with {len(df.columns)} columns")
    
    # Convert timestamp to datetime if it's a string
    if 'timestamp' in df.columns and df['timestamp'].dtype == 'object':
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return df


def compare_features(
    live_df: pd.DataFrame,
    replay_df: pd.DataFrame,
) -> Dict[str, Dict[str, float]]:
    """
    Compare live and replay features.
    
    Returns a dictionary with comparison metrics per feature.
    """
    logger.info("Joining datasets on timestamp + product_id...")
    
    # Ensure timestamp is datetime and normalize timezone
    for df in [live_df, replay_df]:
        if 'timestamp' in df.columns:
            if df['timestamp'].dtype == 'object':
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            # Normalize to UTC if timezone-aware
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    
    # Check for overlap
    live_ts_range = (live_df['timestamp'].min(), live_df['timestamp'].max())
    replay_ts_range = (replay_df['timestamp'].min(), replay_df['timestamp'].max())
    logger.info(f"Live timestamp range: {live_ts_range[0]} to {live_ts_range[1]}")
    logger.info(f"Replay timestamp range: {replay_ts_range[0]} to {replay_ts_range[1]}")
    
    # Check product_id overlap
    live_products = set(live_df['product_id'].unique())
    replay_products = set(replay_df['product_id'].unique())
    common_products = live_products & replay_products
    logger.info(f"Live products: {live_products}")
    logger.info(f"Replay products: {replay_products}")
    logger.info(f"Common products: {common_products}")
    
    # Merge on timestamp and product_id
    merged = pd.merge(
        live_df,
        replay_df,
        on=['timestamp', 'product_id'],
        suffixes=('_live', '_replay'),
        how='inner'
    )
    
    logger.info(f"Found {len(merged)} matching rows after join")
    logger.info(f"Live dataset: {len(live_df)} rows")
    logger.info(f"Replay dataset: {len(replay_df)} rows")
    
    if len(merged) == 0:
        logger.warning("No matching rows found! Check timestamp and product_id alignment.")
        # Try to find why - check if timestamps match at all
        live_ts_set = set(live_df['timestamp'])
        replay_ts_set = set(replay_df['timestamp'])
        exact_ts_matches = len(live_ts_set & replay_ts_set)
        logger.info(f"Exact timestamp matches (ignoring product_id): {exact_ts_matches}")
        if exact_ts_matches > 0:
            logger.info("Timestamps do overlap, but product_id might not match at those timestamps")
        return {}
    
    # Warn if sample size is very small
    if len(merged) < 10:
        logger.warning(
            f"⚠️  WARNING: Only {len(merged)} matching rows found. "
            f"This is a very small sample size for comparison. "
            f"The results may not be representative of the full dataset."
        )
    
    # Identify feature columns (exclude timestamp and product_id)
    feature_cols = [col for col in live_df.columns 
                    if col not in ['timestamp', 'product_id']]
    
    results = {}
    
    for feature in feature_cols:
        live_col = f"{feature}_live"
        replay_col = f"{feature}_replay"
        
        if live_col not in merged.columns or replay_col not in merged.columns:
            logger.warning(f"Feature {feature} not found in merged data")
            continue
        
        live_vals = merged[live_col]
        replay_vals = merged[replay_col]
        
        # Remove NaN values for comparison
        mask = ~(pd.isna(live_vals) | pd.isna(replay_vals))
        live_clean = live_vals[mask]
        replay_clean = replay_vals[mask]
        
        if len(live_clean) == 0:
            logger.warning(f"Feature {feature}: No valid values to compare")
            continue
        
        # Compute mean absolute error
        mae = np.mean(np.abs(live_clean - replay_clean))
        
        # Compute percent of exact matches
        exact_matches = np.sum(live_clean == replay_clean)
        percent_exact = (exact_matches / len(live_clean)) * 100.0
        
        # Additional statistics
        max_diff = np.max(np.abs(live_clean - replay_clean)) if len(live_clean) > 0 else 0.0
        mean_diff = np.mean(live_clean - replay_clean)
        
        results[feature] = {
            'mae': mae,
            'percent_exact': percent_exact,
            'max_diff': max_diff,
            'mean_diff': mean_diff,
            'n_comparisons': len(live_clean),
        }
    
    return results


def print_report(results: Dict[str, Dict[str, float]]) -> None:
    """Print a formatted comparison report."""
    if not results:
        print("\n" + "="*80)
        print("No comparison results available.")
        print("="*80)
        return
    
    print("\n" + "="*80)
    print("LIVE vs REPLAY FEATURE COMPARISON REPORT")
    print("="*80)
    print()
    
    # Header
    print(f"{'Feature':<20} {'MAE':<15} {'Exact Match %':<15} {'Max Diff':<15} {'Mean Diff':<15} {'N':<10}")
    print("-" * 90)
    
    # Data rows
    for feature, metrics in sorted(results.items()):
        mae = metrics['mae']
        pct_exact = metrics['percent_exact']
        max_diff = metrics['max_diff']
        mean_diff = metrics['mean_diff']
        n = int(metrics['n_comparisons'])
        
        print(f"{feature:<20} {mae:<15.6f} {pct_exact:<15.2f} {max_diff:<15.6f} {mean_diff:<15.6f} {n:<10}")
    
    print("-" * 90)
    print()
    
    # Summary statistics
    all_mae = [m['mae'] for m in results.values()]
    all_pct_exact = [m['percent_exact'] for m in results.values()]
    
    # Get total sample size
    total_n = sum(m['n_comparisons'] for m in results.values())
    avg_n = total_n / len(results) if results else 0
    
    print("Summary:")
    print(f"  Average MAE across all features: {np.mean(all_mae):.6f}")
    print(f"  Average exact match %: {np.mean(all_pct_exact):.2f}%")
    print(f"  Min exact match %: {np.min(all_pct_exact):.2f}%")
    print(f"  Max exact match %: {np.max(all_pct_exact):.2f}%")
    print(f"  Average sample size per feature: {avg_n:.1f} rows")
    print()
    
    # Interpretation with sample size warning
    avg_exact = np.mean(all_pct_exact)
    if avg_n < 10:
        print("⚠️  WARNING: Very small sample size! Results may not be representative.")
        print("   The datasets may cover different time periods with minimal overlap.")
        print()
    
    if avg_exact > 99.9:
        if avg_n >= 10:
            print("✓ Datasets are effectively IDENTICAL (exact match > 99.9%)")
        else:
            print("✓ For the limited overlapping rows, datasets are IDENTICAL (exact match > 99.9%)")
            print("  ⚠️  But sample size is too small to draw conclusions about the full datasets.")
    elif avg_exact > 95.0:
        print("⚠ Datasets are VERY SIMILAR (exact match > 95%)")
    elif avg_exact > 80.0:
        print("⚠ Datasets are SIMILAR but have some differences (exact match > 80%)")
    else:
        print("✗ Datasets have SIGNIFICANT DIFFERENCES (exact match < 80%)")
    
    print("="*80)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare live features vs replay features."
    )
    parser.add_argument(
        "--live",
        type=str,
        default="data/processed/features.parquet",
        help="Path to live features Parquet file (default: data/processed/features.parquet)",
    )
    parser.add_argument(
        "--replay",
        type=str,
        default="data/processed/features_replay.parquet",
        help="Path to replay features Parquet file (default: data/processed/features_replay.parquet)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Find project root and resolve paths
    project_root = find_project_root()
    live_path = project_root / args.live if not Path(args.live).is_absolute() else Path(args.live)
    replay_path = project_root / args.replay if not Path(args.replay).is_absolute() else Path(args.replay)
    
    # Load datasets
    try:
        live_df = load_features(live_path)
        replay_df = load_features(replay_path)
    except FileNotFoundError as e:
        logger.error(f"Error loading data: {e}")
        return
    
    # Compare features
    results = compare_features(live_df, replay_df)
    
    # Print report
    print_report(results)
    
    logger.info("Comparison complete!")


if __name__ == "__main__":
    main()

