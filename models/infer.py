#!/usr/bin/env python3
"""
Inference script for volatility prediction models.

Loads a trained model and generates predictions on feature data.
"""
import argparse
import logging
import pickle
from pathlib import Path
from typing import Optional, Tuple

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TRACKING_URI = "http://localhost:5001"

# Feature columns used during training (must match train.py)
FEATURE_COLUMNS = [
    "midprice_return",
    "rolling_vol",
    "spread",
    "trade_intensity",
]


class BaselineRuleModel:
    """Simple baseline rule model using threshold on rolling_vol."""
    
    def __init__(self, threshold: float):
        self.threshold = threshold
        self.feature_name = "rolling_vol"
    
    def predict(self, X: np.ndarray, feature_names: list) -> np.ndarray:
        """Predict using threshold rule."""
        if self.feature_name not in feature_names:
            raise ValueError(f"Feature '{self.feature_name}' not found in feature list")
        
        feature_idx = feature_names.index(self.feature_name)
        return (X[:, feature_idx] >= self.threshold).astype(int)
    
    def predict_proba(self, X: np.ndarray, feature_names: list) -> np.ndarray:
        """Predict probabilities (hard threshold -> 0 or 1)."""
        predictions = self.predict(X, feature_names)
        # Convert to probabilities (0 or 1)
        proba = np.zeros((len(predictions), 2))
        proba[:, 1] = predictions
        proba[:, 0] = 1 - predictions
        return proba


def find_project_root() -> Path:
    """Find project root directory."""
    current = Path(__file__).resolve()
    # Go up from models/ to project root
    project_root = current.parent.parent
    if (project_root / "data" / "processed").exists():
        return project_root
    # Fallback: try current directory
    if (Path.cwd() / "data" / "processed").exists():
        return Path.cwd()
    return project_root


def load_model(model_path: Path):
    """Load a trained model from pickle file."""
    logger.info(f"Loading model from {model_path}...")
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    
    logger.info(f"Loaded model: {type(model).__name__}")
    return model


def load_features(parquet_path: Path) -> pd.DataFrame:
    """Load features from Parquet file."""
    logger.info(f"Loading features from {parquet_path}...")
    if not parquet_path.exists():
        raise FileNotFoundError(f"Features file not found: {parquet_path}")
    
    df = pd.read_parquet(parquet_path)
    logger.info(f"Loaded {len(df)} rows with {len(df.columns)} columns")
    
    # Convert timestamp to datetime if needed
    if "timestamp" in df.columns and df["timestamp"].dtype == "object":
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Sort by timestamp
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    
    return df


def prepare_features(
    df: pd.DataFrame,
    feature_columns: list = FEATURE_COLUMNS,
    model_type: str = "ml",
) -> Tuple[np.ndarray, list]:
    """
    Prepare feature matrix X.
    
    Args:
        df: DataFrame with features
        feature_columns: List of feature column names to use
        model_type: "baseline" or "ml" - determines which features to use
    
    Returns:
        Tuple of (X, feature_names)
    """
    if model_type == "baseline":
        # Baseline model only needs rolling_vol
        feature_columns = ["rolling_vol"]
    
    # Select available features
    available_features = [col for col in feature_columns if col in df.columns]
    missing = set(feature_columns) - set(available_features)
    if missing:
        logger.warning(f"Missing features: {missing}")
    
    X = df[available_features].values
    
    # Handle NaN values
    nan_mask = np.isnan(X).any(axis=1)
    if nan_mask.sum() > 0:
        logger.warning(f"Found {nan_mask.sum()} rows with NaN features - will be excluded from predictions")
        # Keep track of which rows to exclude
        valid_mask = ~nan_mask
    else:
        valid_mask = np.ones(len(df), dtype=bool)
    
    logger.info(f"Feature matrix shape: {X.shape}")
    logger.info(f"Features used: {available_features}")
    
    return X, available_features, valid_mask


def predict(
    model,
    X: np.ndarray,
    feature_names: list,
    threshold: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate predictions from model.
    
    Returns:
        Tuple of (y_pred, p_hat) where:
        - y_pred: Binary predictions (0 or 1)
        - p_hat: Predicted probabilities for positive class
    """
    # Get probabilities
    if isinstance(model, BaselineRuleModel):
        proba = model.predict_proba(X, feature_names)
    elif hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
    else:
        # Fallback: use predict and convert to probabilities
        y_pred = model.predict(X)
        proba = np.zeros((len(y_pred), 2))
        proba[:, 1] = y_pred.astype(float)
        proba[:, 0] = 1 - proba[:, 1]
    
    p_hat = proba[:, 1]  # Probability of positive class
    y_pred = (p_hat >= threshold).astype(int)
    
    return y_pred, p_hat


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    p_hat: np.ndarray,
) -> dict:
    """Compute evaluation metrics."""
    metrics = {}
    
    # PR-AUC
    try:
        pr_auc = average_precision_score(y_true, p_hat)
        metrics["pr_auc"] = pr_auc
    except Exception as e:
        logger.warning(f"Could not compute PR-AUC: {e}")
        metrics["pr_auc"] = None
    
    # F1, Precision, Recall
    try:
        f1 = f1_score(y_true, y_pred, zero_division=0)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        metrics["f1"] = f1
        metrics["precision"] = precision
        metrics["recall"] = recall
    except Exception as e:
        logger.warning(f"Could not compute classification metrics: {e}")
        metrics["f1"] = None
        metrics["precision"] = None
        metrics["recall"] = None
    
    return metrics


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run inference with trained volatility prediction models."
    )
    parser.add_argument(
        "--features_path",
        type=str,
        default="data/processed/features.parquet",
        help="Path to features Parquet file (default: data/processed/features.parquet)",
    )
    parser.add_argument(
        "--model_path",
        type=str,
        default="models/artifacts/logistic_regression_model.pkl",
        help="Path to trained model pickle file (default: models/artifacts/logistic_regression_model.pkl)",
    )
    parser.add_argument(
        "--out_path",
        type=str,
        default="data/processed/predictions.parquet",
        help="Output path for predictions Parquet file (default: data/processed/predictions.parquet)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Threshold for binary predictions (default: 0.5)",
    )
    parser.add_argument(
        "--tracking_uri",
        type=str,
        default=DEFAULT_TRACKING_URI,
        help=f"MLflow tracking URI (default: {DEFAULT_TRACKING_URI})",
    )
    parser.add_argument(
        "--log_eval",
        action="store_true",
        help="Log evaluation metrics to MLflow (requires true labels in data)",
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
    features_path = (
        project_root / args.features_path
        if not Path(args.features_path).is_absolute()
        else Path(args.features_path)
    )
    model_path = (
        project_root / args.model_path
        if not Path(args.model_path).is_absolute()
        else Path(args.model_path)
    )
    out_path = (
        project_root / args.out_path
        if not Path(args.out_path).is_absolute()
        else Path(args.out_path)
    )
    
    # Load model
    model = load_model(model_path)
    
    # Determine model type
    if isinstance(model, BaselineRuleModel):
        model_type = "baseline"
        logger.info("Detected baseline rule model")
    else:
        model_type = "ml"
        logger.info("Detected ML model (sklearn)")
    
    # Load features
    df = load_features(features_path)
    
    # Prepare features
    X, feature_names, valid_mask = prepare_features(df, FEATURE_COLUMNS, model_type)
    
    # Generate predictions
    logger.info("Generating predictions...")
    X_valid = X[valid_mask] if valid_mask is not None else X
    y_pred, p_hat = predict(model, X_valid, feature_names, args.threshold)
    
    # Create predictions dataframe
    predictions_df = df[valid_mask].copy() if valid_mask is not None else df.copy()
    predictions_df["p_hat"] = p_hat
    predictions_df["y_pred"] = y_pred
    
    # Add NaN rows back with NaN predictions if we excluded any
    if valid_mask is not None and not valid_mask.all():
        nan_rows = df[~valid_mask].copy()
        nan_rows["p_hat"] = np.nan
        nan_rows["y_pred"] = np.nan
        # Combine and sort by original index
        predictions_df = pd.concat([predictions_df, nan_rows]).sort_index().reset_index(drop=True)
    
    # Keep only essential columns
    output_columns = ["timestamp", "product_id", "p_hat", "y_pred"]
    
    # Include true label if present
    if "label" in predictions_df.columns:
        output_columns.append("label")
        logger.info("True labels found in data - will be included in output")
    
    predictions_df = predictions_df[output_columns]
    
    # Save predictions
    out_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_df.to_parquet(out_path, index=False)
    logger.info(f"Predictions saved to {out_path}")
    logger.info(f"Total predictions: {len(predictions_df)}")
    logger.info(f"Positive predictions (y_pred=1): {predictions_df['y_pred'].sum()}")
    
    # Evaluate if true labels are available and logging is requested
    if args.log_eval and "label" in df.columns:
        logger.info("Evaluating predictions...")
        y_true = predictions_df["label"].values
        valid_eval_mask = ~(pd.isna(y_true) | pd.isna(p_hat))
        
        if valid_eval_mask.sum() > 0:
            y_true_valid = y_true[valid_eval_mask]
            y_pred_valid = y_pred[valid_eval_mask]
            p_hat_valid = p_hat[valid_eval_mask]
            
            metrics = evaluate_predictions(y_true_valid, y_pred_valid, p_hat_valid)
            
            # Log to MLflow
            mlflow.set_tracking_uri(args.tracking_uri)
            with mlflow.start_run(run_name="inference-eval") as run:
                # Log parameters
                mlflow.log_params({
                    "model_path": str(model_path),
                    "features_path": str(features_path),
                    "threshold": args.threshold,
                    "model_type": model_type,
                    "n_samples": len(y_true_valid),
                })
                
                # Log metrics (filter out None values)
                metrics_to_log = {k: v for k, v in metrics.items() if v is not None}
                mlflow.log_metrics(metrics_to_log)
                
                logger.info(f"Inference evaluation logged to MLflow")
                logger.info(f"Run ID: {run.info.run_id}")
                logger.info(f"Metrics: {metrics_to_log}")
        else:
            logger.warning("No valid samples for evaluation (all labels or predictions are NaN)")
    elif args.log_eval:
        logger.warning("--log_eval specified but no 'label' column found in data")
    
    logger.info("=" * 80)
    logger.info("Inference complete!")
    logger.info(f"Predictions saved to: {out_path}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

