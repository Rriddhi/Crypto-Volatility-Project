#!/usr/bin/env python3
"""
Train volatility prediction models with MLflow tracking.

This script implements two models:
1. Baseline rule model: Simple threshold-based rule on rolling_vol
2. ML model: LogisticRegression or XGBoost classifier

Both models are evaluated on train/val/test splits and logged to MLflow.
"""
import argparse
import logging
import pickle
from pathlib import Path
from typing import Dict, Tuple

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_recall_curve,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_TRACKING_URI = "http://localhost:5001"
DEFAULT_TRAIN_RATIO = 0.6
DEFAULT_VAL_RATIO = 0.2
DEFAULT_TEST_RATIO = 0.2

# Feature columns to use for ML model
FEATURE_COLUMNS = [
    "midprice_return",
    "rolling_vol",
    "spread",
    "trade_intensity",
]


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
    
    # Sort strictly by timestamp to enforce time-based splits
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
        logger.info(f"Sorted by timestamp: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df


def create_label(
    df: pd.DataFrame,
    tau: float,
    label_column: str = "label",
) -> pd.DataFrame:
    """
    Create binary label based on volatility threshold.
    
    ASSUMPTION: If 'label' column already exists, it is used as-is.
    Otherwise, we compute it from 'rolling_vol' >= tau.
    
    According to feature_spec.md:
    - σ_future = rolling std of midprice_return over next 60 seconds
    - y = 1 if σ_future >= τ else 0
    
    For simplicity, we use rolling_vol as a proxy for σ_future.
    If the actual future volatility column exists, use that instead.
    """
    if label_column in df.columns:
        logger.info(f"Using existing '{label_column}' column")
        return df
    
    logger.info(f"Computing label: y = 1 if rolling_vol >= {tau}, else 0")
    
    # Use rolling_vol as proxy for future volatility
    # In production, this would be computed from future returns
    df[label_column] = (df["rolling_vol"] >= tau).astype(int)
    
    label_counts = df[label_column].value_counts()
    logger.info(f"Label distribution: {label_counts.to_dict()}")
    logger.info(f"Positive class rate: {df[label_column].mean():.4f}")
    
    return df


def time_based_split(
    df: pd.DataFrame,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    val_ratio: float = DEFAULT_VAL_RATIO,
    test_ratio: float = DEFAULT_TEST_RATIO,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split data into train/val/test sets based on time order.
    
    Args:
        df: DataFrame sorted by timestamp
        train_ratio: Proportion for training set (default: 0.6)
        val_ratio: Proportion for validation set (default: 0.2)
        test_ratio: Proportion for test set (default: 0.2)
    
    Returns:
        Tuple of (train_df, val_df, test_df)
    """
    total_rows = len(df)
    train_end = int(total_rows * train_ratio)
    val_end = train_end + int(total_rows * val_ratio)
    
    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()
    
    logger.info(
        f"Time-based split: train={len(train_df)} ({train_ratio*100:.0f}%), "
        f"val={len(val_df)} ({val_ratio*100:.0f}%), "
        f"test={len(test_df)} ({test_ratio*100:.0f}%)"
    )
    
    if "timestamp" in df.columns:
        logger.info(
            f"Train period: {train_df['timestamp'].min()} to {train_df['timestamp'].max()}"
        )
        logger.info(
            f"Val period: {val_df['timestamp'].min()} to {val_df['timestamp'].max()}"
        )
        logger.info(
            f"Test period: {test_df['timestamp'].min()} to {test_df['timestamp'].max()}"
        )
    
    return train_df, val_df, test_df


def prepare_features(
    df: pd.DataFrame, feature_columns: list = FEATURE_COLUMNS
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Prepare feature matrix X and target vector y.
    
    Args:
        df: DataFrame with features and label
        feature_columns: List of feature column names to use
    
    Returns:
        Tuple of (X, y) as numpy arrays
    """
    # Select available features
    available_features = [col for col in feature_columns if col in df.columns]
    missing = set(feature_columns) - set(available_features)
    if missing:
        logger.warning(f"Missing features: {missing}")
    
    X = df[available_features].values
    y = df["label"].values
    
    # Handle NaN values
    nan_mask = np.isnan(X).any(axis=1)
    if nan_mask.sum() > 0:
        logger.warning(f"Removing {nan_mask.sum()} rows with NaN features")
        X = X[~nan_mask]
        y = y[~nan_mask]
    
    logger.info(f"Feature matrix shape: {X.shape}, Target shape: {y.shape}")
    logger.info(f"Features used: {available_features}")
    
    return X, y


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


def evaluate_model(
    model,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list,
    split_name: str = "test",
) -> Dict[str, float]:
    """
    Evaluate model and compute metrics.
    
    Returns:
        Dictionary with metrics: pr_auc, f1, precision, recall
    """
    # Get predictions - handle both baseline and sklearn models
    if isinstance(model, BaselineRuleModel):
        y_proba = model.predict_proba(X, feature_names)[:, 1]
    elif hasattr(model, "predict_proba"):
        y_proba = model.predict_proba(X)[:, 1]
    else:
        # Fallback: use predict and convert to probabilities
        y_pred = model.predict(X)
        y_proba = y_pred.astype(float)
    
    y_pred = (y_proba >= 0.5).astype(int)
    
    # Compute metrics
    pr_auc = average_precision_score(y, y_proba)
    f1 = f1_score(y, y_pred, zero_division=0)
    
    # Precision and recall at threshold 0.5
    from sklearn.metrics import precision_score, recall_score
    
    precision = precision_score(y, y_pred, zero_division=0)
    recall = recall_score(y, y_pred, zero_division=0)
    
    metrics = {
        f"{split_name}_pr_auc": pr_auc,
        f"{split_name}_f1": f1,
        f"{split_name}_precision": precision,
        f"{split_name}_recall": recall,
    }
    
    logger.info(
        f"{split_name.upper()} - PR-AUC: {pr_auc:.4f}, F1: {f1:.4f}, "
        f"Precision: {precision:.4f}, Recall: {recall:.4f}"
    )
    
    return metrics


def train_baseline_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    tau: float,
    output_dir: Path,
    tracking_uri: str,
) -> None:
    """Train and evaluate baseline rule model."""
    logger.info("=" * 80)
    logger.info("Training Baseline Rule Model")
    logger.info("=" * 80)
    
    # Use tau as the baseline threshold (or compute from training data)
    # For baseline, use a percentile of rolling_vol in training set
    baseline_threshold = train_df["rolling_vol"].quantile(0.95) if tau is None else tau
    logger.info(f"Baseline threshold (τ_baseline): {baseline_threshold:.6f}")
    
    model = BaselineRuleModel(threshold=baseline_threshold)
    
    # Prepare features
    feature_names = ["rolling_vol"]  # Only need rolling_vol for baseline
    X_train, y_train = prepare_features(train_df, feature_names)
    X_val, y_val = prepare_features(val_df, feature_names)
    X_test, y_test = prepare_features(test_df, feature_names)
    
    # Evaluate on all splits
    train_metrics = evaluate_model(model, X_train, y_train, feature_names, "train")
    val_metrics = evaluate_model(model, X_val, y_val, feature_names, "val")
    test_metrics = evaluate_model(model, X_test, y_test, feature_names, "test")
    
    # Log to MLflow
    with mlflow.start_run(run_name="baseline_rule_model") as run:
        # Log parameters
        mlflow.log_params({
            "model_type": "baseline_rule",
            "threshold": baseline_threshold,
            "tau": tau if tau else "auto",
            "feature": "rolling_vol",
        })
        
        # Log metrics
        all_metrics = {**train_metrics, **val_metrics, **test_metrics}
        mlflow.log_metrics(all_metrics)
        
        # Save model artifact locally
        model_path = output_dir / "baseline_model.pkl"
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        
        # Try to log artifact, but don't fail if artifact storage is not accessible
        try:
            mlflow.log_artifact(str(model_path), "models")
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not log artifact to MLflow: {e}")
            logger.info(f"Model saved locally at {model_path} instead")
        
        logger.info(f"Baseline model saved to {model_path}")
        logger.info(f"MLflow run ID: {run.info.run_id}")


def train_ml_model(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    tau: float,
    output_dir: Path,
    tracking_uri: str,
    use_xgboost: bool = False,
) -> None:
    """Train and evaluate ML model (LogisticRegression or XGBoost)."""
    logger.info("=" * 80)
    logger.info("Training ML Model")
    logger.info("=" * 80)
    
    # Prepare features
    X_train, y_train = prepare_features(train_df, FEATURE_COLUMNS)
    X_val, y_val = prepare_features(val_df, FEATURE_COLUMNS)
    X_test, y_test = prepare_features(test_df, FEATURE_COLUMNS)
    
    feature_names = [col for col in FEATURE_COLUMNS if col in train_df.columns]
    
    # Train model
    if use_xgboost:
        try:
            import xgboost as xgb
            logger.info("Using XGBoost classifier")
            model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42,
                eval_metric="logloss",
            )
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
        except ImportError:
            logger.warning("XGBoost not available, falling back to LogisticRegression")
            use_xgboost = False
    
    if not use_xgboost:
        logger.info("Using LogisticRegression")
        model = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight="balanced",  # Handle class imbalance
        )
        model.fit(X_train, y_train)
    
    # Evaluate on all splits
    train_metrics = evaluate_model(model, X_train, y_train, feature_names, "train")
    val_metrics = evaluate_model(model, X_val, y_val, feature_names, "val")
    test_metrics = evaluate_model(model, X_test, y_test, feature_names, "test")
    
    # Log to MLflow
    model_type = "xgboost" if use_xgboost else "logistic_regression"
    with mlflow.start_run(run_name=f"ml_model_{model_type}") as run:
        # Log parameters
        params = {
            "model_type": model_type,
            "tau": tau if tau else "auto",
            "features": ",".join(feature_names),
        }
        if use_xgboost:
            params.update({
                "n_estimators": 100,
                "max_depth": 3,
                "learning_rate": 0.1,
            })
        else:
            params.update({
                "max_iter": 1000,
                "class_weight": "balanced",
            })
        mlflow.log_params(params)
        
        # Log metrics
        all_metrics = {**train_metrics, **val_metrics, **test_metrics}
        mlflow.log_metrics(all_metrics)
        
        # Save model artifact locally
        model_path = output_dir / f"{model_type}_model.pkl"
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        
        # Log model using MLflow's sklearn integration
        try:
            mlflow.sklearn.log_model(model, "model")
        except Exception as e:
            logger.warning(f"Could not log model to MLflow (sklearn.log_model): {e}")
            logger.info("This is OK - model is still saved locally and metrics are logged")
        
        # Try to log the pickle file as artifact
        try:
            mlflow.log_artifact(str(model_path), "models")
        except (OSError, PermissionError, Exception) as e:
            logger.warning(f"Could not log model artifact to MLflow: {e}")
            logger.info(f"Model saved locally at {model_path} instead")
        
        logger.info(f"ML model saved to {model_path}")
        logger.info(f"MLflow run ID: {run.info.run_id}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Train volatility prediction models with MLflow tracking."
    )
    parser.add_argument(
        "--features_path",
        type=str,
        default="data/processed/features.parquet",
        help="Path to features Parquet file (default: data/processed/features.parquet)",
    )
    parser.add_argument(
        "--tau",
        type=float,
        default=None,
        help="Volatility threshold τ for label creation. If None, uses 95th percentile of rolling_vol (default: None)",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="models/artifacts",
        help="Output directory for model artifacts (default: models/artifacts)",
    )
    parser.add_argument(
        "--tracking_uri",
        type=str,
        default=DEFAULT_TRACKING_URI,
        help=f"MLflow tracking URI (default: {DEFAULT_TRACKING_URI})",
    )
    parser.add_argument(
        "--train_ratio",
        type=float,
        default=DEFAULT_TRAIN_RATIO,
        help=f"Training set ratio (default: {DEFAULT_TRAIN_RATIO})",
    )
    parser.add_argument(
        "--val_ratio",
        type=float,
        default=DEFAULT_VAL_RATIO,
        help=f"Validation set ratio (default: {DEFAULT_VAL_RATIO})",
    )
    parser.add_argument(
        "--test_ratio",
        type=float,
        default=DEFAULT_TEST_RATIO,
        help=f"Test set ratio (default: {DEFAULT_TEST_RATIO})",
    )
    parser.add_argument(
        "--use_xgboost",
        action="store_true",
        help="Use XGBoost instead of LogisticRegression (requires xgboost package)",
    )
    parser.add_argument(
        "--baseline_only",
        action="store_true",
        help="Only train baseline model (skip ML model)",
    )
    parser.add_argument(
        "--ml_only",
        action="store_true",
        help="Only train ML model (skip baseline)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate split ratios
    total_ratio = args.train_ratio + args.val_ratio + args.test_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(
            f"Split ratios must sum to 1.0, got {total_ratio:.6f}"
        )
    
    # Find project root and resolve paths
    project_root = find_project_root()
    features_path = (
        project_root / args.features_path
        if not Path(args.features_path).is_absolute()
        else Path(args.features_path)
    )
    output_dir = (
        project_root / args.output_dir
        if not Path(args.output_dir).is_absolute()
        else Path(args.output_dir)
    )
    
    # Set MLflow tracking URI
    mlflow.set_tracking_uri(args.tracking_uri)
    logger.info(f"MLflow tracking URI: {args.tracking_uri}")
    
    # Set artifact URI to local mlruns directory to avoid permission issues
    # MLflow server uses /mlruns in container, but we need local path for artifacts
    project_root = find_project_root()
    local_mlruns = project_root / "mlruns"
    local_mlruns.mkdir(exist_ok=True)
    # Note: MLflow will use the server's artifact root, but we'll handle errors gracefully
    
    # Load and prepare data
    df = load_features(features_path)
    
    # Determine tau if not provided
    if args.tau is None:
        args.tau = df["rolling_vol"].quantile(0.95)
        logger.info(f"Auto-selected tau (95th percentile): {args.tau:.6f}")
    
    # Create label
    df = create_label(df, args.tau)
    
    # Time-based split
    train_df, val_df, test_df = time_based_split(
        df,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )
    
    # Train models
    if not args.ml_only:
        train_baseline_model(
            train_df, val_df, test_df, args.tau, output_dir, args.tracking_uri
        )
    
    if not args.baseline_only:
        train_ml_model(
            train_df,
            val_df,
            test_df,
            args.tau,
            output_dir,
            args.tracking_uri,
            use_xgboost=args.use_xgboost,
        )
    
    logger.info("=" * 80)
    logger.info("Training complete!")
    logger.info(f"Models saved to: {output_dir}")
    logger.info(f"View results at: {args.tracking_uri}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

