#!/usr/bin/env python3
"""
Generate Evidently reports for data drift and data quality monitoring.

Compares early (reference) and late (current) windows of feature data
to detect drift and quality issues.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Tuple

import pandas as pd

# Evidently imports - handle different API versions
# Try to import Report first (most common API)
try:
    from evidently import Report
    EVIDENTLY_NEW_API = False
    # Try different preset import paths (order matters - try most common first)
    try:
        from evidently.presets import DataDriftPreset, DataSummaryPreset
        # DataSummaryPreset is used for data quality in newer versions
        DataQualityPreset = DataSummaryPreset
    except ImportError:
        try:
            from evidently.presets import DataDriftPreset
            from evidently.presets import DatasetStats as DataQualityPreset
        except ImportError:
            try:
                from evidently.preset import DataDriftPreset, DataQualityPreset
            except ImportError:
                try:
                    from evidently.metric_preset import DataDriftPreset, DataQualityPreset
                except ImportError:
                    # Last resort: try to import from metrics and construct manually
                    raise ImportError("Could not find DataDriftPreset or DataQualityPreset")
except ImportError:
    # Try newer Dashboard API
    try:
        from evidently.dashboard import Dashboard
        from evidently.tabs import DataDriftTab, DataQualityTab
        EVIDENTLY_NEW_API = True
    except ImportError:
        raise ImportError(
            "Could not import Evidently. Please install it with: pip install evidently"
        )

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
    # Go up from reports/ to project root
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
    
    df = pd.read_parquet(parquet_path)
    logger.info(f"Loaded {len(df)} feature rows")
    
    # Convert timestamp to datetime if it's a string
    if 'timestamp' in df.columns and df['timestamp'].dtype == 'object':
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Sort by timestamp to ensure chronological order
    if 'timestamp' in df.columns:
        df = df.sort_values('timestamp').reset_index(drop=True)
        logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df


def split_windows(
    df: pd.DataFrame,
    reference_pct: float = 0.35,
    current_pct: float = 0.35,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split data into reference (early) and current (late) windows.
    
    Args:
        df: Full feature dataframe
        reference_pct: Percentage of data for reference window (default: 0.35 = 35%)
        current_pct: Percentage of data for current window (default: 0.35 = 35%)
    
    Returns:
        Tuple of (reference_df, current_df)
    """
    total_rows = len(df)
    reference_size = int(total_rows * reference_pct)
    current_start = total_rows - int(total_rows * current_pct)
    
    reference_df = df.iloc[:reference_size].copy()
    current_df = df.iloc[current_start:].copy()
    
    logger.info(
        f"Split data: {len(reference_df)} rows (reference, {reference_pct*100:.0f}%) "
        f"and {len(current_df)} rows (current, {current_pct*100:.0f}%)"
    )
    
    if 'timestamp' in reference_df.columns:
        logger.info(
            f"Reference window: {reference_df['timestamp'].min()} to {reference_df['timestamp'].max()}"
        )
        logger.info(
            f"Current window: {current_df['timestamp'].min()} to {current_df['timestamp'].max()}"
        )
    
    return reference_df, current_df


def save_report(snapshot, html_path: Path, json_path: Path, report_name: str) -> None:
    """Helper function to save Evidently report as HTML and JSON."""
    # Save JSON report from snapshot
    try:
        report_dict = snapshot.as_dict() if hasattr(snapshot, 'as_dict') else {}
        with open(json_path, 'w') as f:
            json.dump(report_dict, f, indent=2, default=str)
        logger.info(f"✓ Saved JSON {report_name}: {json_path}")
    except Exception as e:
        logger.warning(f"Could not save JSON {report_name}: {e}")
        report_dict = {}
    
    # Save HTML report - use template if available
    try:
        # Try to use template to render HTML
        try:
            from evidently.template import Template
            template = Template()
            html_content = template.render(snapshot)
            with open(html_path, 'w') as f:
                f.write(html_content)
            logger.info(f"✓ Saved HTML {report_name}: {html_path}")
        except ImportError:
            # Fallback: try to use snapshot's render method
            if hasattr(snapshot, 'render'):
                html_content = snapshot.render()
                with open(html_path, 'w') as f:
                    f.write(html_content)
                logger.info(f"✓ Saved HTML {report_name}: {html_path}")
            else:
                # Last resort: create a simple HTML from JSON
                logger.warning(f"Could not render HTML template for {report_name}, creating basic HTML from JSON")
                html_content = f"""<!DOCTYPE html>
<html>
<head><title>{report_name.title()}</title></head>
<body>
<h1>{report_name.title()}</h1>
<p>JSON data saved to: {json_path.name}</p>
<pre>{json.dumps(report_dict, indent=2, default=str)}</pre>
</body>
</html>"""
                with open(html_path, 'w') as f:
                    f.write(html_content)
                logger.info(f"✓ Saved basic HTML {report_name}: {html_path}")
    except Exception as e:
        logger.warning(f"Could not save HTML {report_name}: {e}")


def generate_drift_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Generate data drift report using Evidently."""
    logger.info("Generating data drift report...")
    
    # Select only numeric features for drift analysis (exclude metadata)
    numeric_features = [
        'midprice',
        'midprice_return',
        'rolling_vol',
        'spread',
        'trade_intensity',
    ]
    numeric_features = [col for col in numeric_features if col in reference_df.columns]
    
    # Prepare dataframes with only numeric features
    ref_data = reference_df[numeric_features].copy()
    curr_data = current_df[numeric_features].copy()
    
    if EVIDENTLY_NEW_API:
        # New API: Use Dashboard with tabs
        drift_dashboard = Dashboard(
            tabs=[DataDriftTab()]
        )
        drift_dashboard.calculate(ref_data, curr_data)
        
        # Save HTML report
        html_path = output_dir / "drift_report.html"
        drift_dashboard.save(str(html_path))
        logger.info(f"✓ Saved HTML drift report: {html_path}")
        
        # Save JSON report
        json_path = output_dir / "drift_report.json"
        drift_dashboard.save_json(str(json_path))
        logger.info(f"✓ Saved JSON drift report: {json_path}")
    else:
        # Evidently 0.7+ API: Use Report with presets
        drift_report = Report(
            metrics=[
                DataDriftPreset(),
            ]
        )
        
        # Run report - returns a Snapshot
        snapshot = drift_report.run(
            reference_data=ref_data,
            current_data=curr_data,
        )
        
        # Save reports using helper function
        html_path = output_dir / "drift_report.html"
        json_path = output_dir / "drift_report.json"
        save_report(snapshot, html_path, json_path, "drift report")
        
        # Print summary
        logger.info("\n" + "="*80)
        logger.info("Data Drift Summary:")
        logger.info("="*80)
        try:
            # Extract drift metrics from snapshot
            if hasattr(snapshot, 'as_dict'):
                metrics_dict = snapshot.as_dict()
                if 'metrics' in metrics_dict:
                    for metric in metrics_dict['metrics']:
                        if isinstance(metric, dict) and 'result' in metric:
                            result = metric['result']
                            if isinstance(result, dict) and 'drift_score' in result:
                                drift_score = result['drift_score']
                                metric_name = metric.get('metric', 'Unknown')
                                logger.info(f"{metric_name}: drift_score = {drift_score:.4f}")
        except Exception as e:
            logger.debug(f"Could not parse drift summary: {e}")


def generate_quality_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Generate data quality report using Evidently."""
    logger.info("Generating data quality report...")
    
    # Select only numeric features
    numeric_features = [
        'midprice',
        'midprice_return',
        'rolling_vol',
        'spread',
        'trade_intensity',
    ]
    numeric_features = [col for col in numeric_features if col in reference_df.columns]
    
    # Prepare dataframes
    ref_data = reference_df[numeric_features].copy()
    curr_data = current_df[numeric_features].copy()
    
    if EVIDENTLY_NEW_API:
        # New API: Use Dashboard with tabs
        quality_dashboard = Dashboard(
            tabs=[DataQualityTab()]
        )
        quality_dashboard.calculate(ref_data, curr_data)
        
        # Save HTML report
        html_path = output_dir / "quality_report.html"
        quality_dashboard.save(str(html_path))
        logger.info(f"✓ Saved HTML quality report: {html_path}")
        
        # Save JSON report
        json_path = output_dir / "quality_report.json"
        quality_dashboard.save_json(str(json_path))
        logger.info(f"✓ Saved JSON quality report: {json_path}")
    else:
        # Evidently 0.7+ API: Use Report with presets
        quality_report = Report(
            metrics=[
                DataQualityPreset(),
            ]
        )
        
        # Run report - returns a Snapshot
        snapshot = quality_report.run(
            reference_data=ref_data,
            current_data=curr_data,
        )
        
        # Save reports using helper function
        html_path = output_dir / "quality_report.html"
        json_path = output_dir / "quality_report.json"
        save_report(snapshot, html_path, json_path, "quality report")


def generate_combined_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Generate a combined report with both drift and quality metrics."""
    logger.info("Generating combined report (drift + quality)...")
    
    numeric_features = [
        'midprice',
        'midprice_return',
        'rolling_vol',
        'spread',
        'trade_intensity',
    ]
    numeric_features = [col for col in numeric_features if col in reference_df.columns]
    
    # Prepare dataframes
    ref_data = reference_df[numeric_features].copy()
    curr_data = current_df[numeric_features].copy()
    
    if EVIDENTLY_NEW_API:
        # New API: Use Dashboard with multiple tabs
        combined_dashboard = Dashboard(
            tabs=[DataDriftTab(), DataQualityTab()]
        )
        combined_dashboard.calculate(ref_data, curr_data)
        
        # Save HTML
        html_path = output_dir / "combined_report.html"
        combined_dashboard.save(str(html_path))
        logger.info(f"✓ Saved combined HTML report: {html_path}")
        
        # Save JSON
        json_path = output_dir / "combined_report.json"
        combined_dashboard.save_json(str(json_path))
        logger.info(f"✓ Saved combined JSON report: {json_path}")
    else:
        # Evidently 0.7+ API: Use Report with multiple presets
        combined_report = Report(
            metrics=[
                DataDriftPreset(),
                DataQualityPreset(),
            ]
        )
        
        # Run report - returns a Snapshot
        snapshot = combined_report.run(
            reference_data=ref_data,
            current_data=curr_data,
        )
        
        # Save reports using helper function
        html_path = output_dir / "combined_report.html"
        json_path = output_dir / "combined_report.json"
        save_report(snapshot, html_path, json_path, "combined report")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Evidently reports for data drift and quality monitoring."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/processed/features.parquet",
        help="Path to input features Parquet file (default: data/processed/features.parquet)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/evidently",
        help="Output directory for reports (default: reports/evidently)",
    )
    parser.add_argument(
        "--reference-pct",
        type=float,
        default=0.35,
        help="Percentage of data for reference window (default: 0.35 = 35%%)",
    )
    parser.add_argument(
        "--current-pct",
        type=float,
        default=0.35,
        help="Percentage of data for current window (default: 0.35 = 35%%)",
    )
    parser.add_argument(
        "--report-type",
        type=str,
        choices=["drift", "quality", "combined", "all"],
        default="all",
        help="Type of report to generate (default: all)",
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
    input_path = project_root / args.input if not Path(args.input).is_absolute() else Path(args.input)
    output_dir = project_root / args.output_dir if not Path(args.output_dir).is_absolute() else Path(args.output_dir)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Load features
    df = load_features(input_path)
    
    if len(df) < 100:
        logger.warning(f"Very few rows ({len(df)}). Reports may not be meaningful.")
    
    # Split into windows
    reference_df, current_df = split_windows(
        df,
        reference_pct=args.reference_pct,
        current_pct=args.current_pct,
    )
    
    # Generate reports
    if args.report_type in ("drift", "all"):
        generate_drift_report(reference_df, current_df, output_dir)
    
    if args.report_type in ("quality", "all"):
        generate_quality_report(reference_df, current_df, output_dir)
    
    if args.report_type in ("combined", "all"):
        generate_combined_report(reference_df, current_df, output_dir)
    
    logger.info("\n" + "="*80)
    logger.info("✓ Evidently report generation complete!")
    logger.info(f"Reports saved to: {output_dir}")
    logger.info("="*80)


if __name__ == "__main__":
    main()

