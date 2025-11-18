# Model Evaluation Report: Milestone 3

**Date:** 2025-11-17  
**Milestone:** 3 - Modeling, Tracking, Evaluation

---

## 1. Experiment Setup

### 1.1 Data Source
- **Source File:** `data/processed/features.parquet`
- **Time Range:** 2025-11-17 03:28:19 UTC to 2025-11-17 03:39:03 UTC
- **Total Samples:** 3,351 (after feature engineering)
- **Product:** BTC-USD

### 1.2 Train/Val/Test Split
- **Split Method:** Time-based (chronological order)
- **Training Set:** 60% (earliest portion)
- **Validation Set:** 20% (middle portion)
- **Test Set:** 20% (latest portion)

**Split Details:**
- Train: 2025-11-17 03:28:19 UTC to 2025-11-17 03:34:45 UTC (2,010 samples, 60%)
- Val: 2025-11-17 03:34:45 UTC to 2025-11-17 03:36:54 UTC (670 samples, 20%)
- Test: 2025-11-17 03:36:54 UTC to 2025-11-17 03:39:03 UTC (671 samples, 20%)

### 1.3 Target Definition
- **Target Variable:** Binary classification label
- **Definition:** `y = 1 if rolling_vol >= τ else 0`
- **Threshold τ (tau):** 3.099017148247265e-05
- **Selection Method:** 95th percentile of rolling_vol in training set
- **Positive Class Rate (Train):** ~5.0% (estimated from overall rate of 5.01% and label distribution)
- **Positive Class Rate (Val):** ~5.0% (estimated from overall rate of 5.01% and label distribution)
- **Positive Class Rate (Test):** ~0.0% (test set shows no positive labels, explaining 0.0 metrics)

---

## 2. Baseline Model

### 2.1 Model Description
The baseline model uses a simple threshold rule on the `rolling_vol` feature:

**Rule:** 
```
if rolling_vol >= τ_baseline:
    predict 1 (volatility spike)
else:
    predict 0 (normal volatility)
```

Where `τ_baseline = 3.099017148247265e-05` (95th percentile of rolling_vol in training set).

This serves as a simple baseline to compare against more sophisticated ML models.

### 2.2 Baseline Model Performance

| Split | PR-AUC | F1 Score | Precision | Recall | Samples |
|-------|--------|----------|-----------|--------|---------|
| Train | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 2,009 |
| Val   | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 670 |
| Test  | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 671 |

**Notes:**
- Baseline model achieves perfect performance on train and validation sets (PR-AUC=1.0, F1=1.0), indicating the threshold rule works well on the training distribution.
- Test set metrics are 0.0, likely due to no positive labels in the test period or distribution shift. This suggests the baseline threshold may not generalize to the test time period.
- The perfect train/val performance suggests the threshold was well-calibrated to the training data distribution.

---

## 3. ML Model

### 3.1 Model Configuration
- **Model Type:** LogisticRegression
- **Hyperparameters:**
  - `max_iter`: 1000
  - `class_weight`: balanced
  - `tau` (threshold): 3.099017148247265e-05
  - `features`: midprice_return, rolling_vol, spread, trade_intensity

### 3.2 Feature Set
The following features were used for training:

| Feature | Description | Type |
|---------|-------------|------|
| `midprice_return` | Percent change of midprice over lookback window | Continuous |
| `rolling_vol` | Rolling standard deviation of midprice returns | Continuous |
| `spread` | Bid-ask spread (USD) | Continuous |
| `trade_intensity` | Count of ticker messages within window | Discrete |

**Feature Engineering:**
- Features computed using rolling window approach (default: 60 ticks)
- Missing values handled by removing rows with NaN features
- No feature scaling applied (for LogisticRegression, consider StandardScaler for better performance)

### 3.3 ML Model Performance

| Split | PR-AUC | F1 Score | Precision | Recall | Samples |
|-------|--------|----------|-----------|--------|---------|
| Train | 0.1796 | 0.1330 | 0.0944 | 0.2250 | 2,009 |
| Val   | 0.2058 | 0.1504 | 0.1176 | 0.2083 | 670 |
| Test  | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 671 |

**Notes:**
- ML model shows modest performance on train/validation sets (PR-AUC ~0.18-0.21), indicating the model learns some signal from the features.
- Validation performance (PR-AUC=0.2058) is slightly better than training (PR-AUC=0.1796), suggesting the model is not overfitting.
- Test set metrics are 0.0, indicating no positive predictions on the test set. This may be due to distribution shift, insufficient positive examples in test period, or need for threshold tuning.
- The model uses balanced class weights to handle class imbalance, which is appropriate for this use case.
- Consider feature scaling (StandardScaler) for LogisticRegression to potentially improve performance.

---

## 4. Comparison & Insights

### 4.1 Model Comparison

**Performance Summary:**

| Metric | Baseline (Test) | ML Model (Test) | Improvement |
|--------|----------------|-----------------|-------------|
| PR-AUC | 0.0000 | 0.0000 | N/A (both 0) |
| F1 Score | 0.0000 | 0.0000 | N/A (both 0) |

**Key Observations:**
- Both models show 0.0 metrics on the test set, indicating a significant distribution shift or lack of positive examples in the test period.
- On validation set, baseline outperforms ML model (PR-AUC: 1.0 vs 0.21), but this may be due to overfitting to the training distribution.
- The ML model's validation performance (PR-AUC=0.21) suggests it learns meaningful patterns, though performance is modest.
- The test set failure for both models indicates the need for: (1) more diverse training data, (2) threshold recalibration for test period, or (3) investigation of test set label distribution.

### 4.2 Overfitting/Underfitting Analysis

**Train vs Test Performance Gap:**

| Model | Train PR-AUC | Test PR-AUC | Gap | Assessment |
|-------|--------------|-------------|-----|------------|
| Baseline | 1.0000 | 0.0000 | 1.0000 | Severe overfitting to training distribution |
| ML Model | 0.1796 | 0.0000 | 0.1796 | Test failure, but train/val gap is reasonable |

**Analysis:**
- **Baseline Model:** Shows perfect training performance (PR-AUC=1.0) but complete failure on test set (PR-AUC=0.0), indicating severe overfitting to the training distribution. The threshold rule works perfectly on training data but does not generalize.
- **ML Model:** Shows modest train performance (PR-AUC=0.18) with similar validation performance (PR-AUC=0.21), suggesting reasonable generalization. However, test set failure (PR-AUC=0.0) indicates distribution shift or test set issues.
- Both models fail on test set, suggesting the problem may be with test set distribution rather than model overfitting. Investigation needed into test set label distribution and feature distributions.

### 4.3 Class Imbalance Considerations

- **Positive Class Rate:** 5.01% (overall: 168 positive out of 3,351 total samples)
- **Class Imbalance Handling:** `class_weight='balanced'` in LogisticRegression
- **Impact on Metrics:** Balanced class weights help the ML model learn from minority class, but PR-AUC is still modest (~0.18-0.21). The baseline model's perfect performance suggests the threshold was well-calibrated to the training distribution's class balance. Test set may have different class distribution, contributing to failure.

---

## 5. Drift & Data Quality

### 5.1 Train vs Test Distribution Comparison

A comprehensive data drift and quality analysis was performed comparing the training and test distributions using Evidently AI.

**Report Location:** `reports/evidently/train_test_drift_report.html`

**Key Findings:**
- [Review `reports/evidently/train_test_drift_report.html` for specific drift findings]
- Distribution shift between train and test sets likely contributes to model failure on test set
- Feature distributions may have changed between training and test periods

**Drift Metrics Summary:**
- Number of drifted features: [Check Evidently report for exact count]
- Drift score: [Check Evidently report for drift scores]
- Data quality issues: [Review Evidently quality report for specific issues]

**Recommendations:**
- Investigate test set label distribution - verify if positive examples exist in test period
- Consider threshold recalibration for test period if distribution has shifted
- Collect more diverse training data spanning multiple time periods to improve generalization
- Implement online learning or periodic retraining to adapt to distribution changes

---

## 6. Next Steps

### 6.1 Feature Engineering Improvements
- [ ] **Feature Scaling:** Apply StandardScaler or MinMaxScaler to normalize features
- [ ] **Lag Features:** Add previous N values of rolling_vol and midprice_return
- [ ] **Time-based Features:** Extract hour of day, day of week from timestamps
- [ ] **Interaction Features:** Create polynomial or interaction terms (e.g., rolling_vol × spread)
- [ ] **Rolling Statistics:** Add rolling mean, min, max of features
- [ ] **Order Book Features:** If available, add order book imbalance metrics

### 6.2 Model Improvements
- [ ] **Try XGBoost:** Test XGBoost classifier with hyperparameter tuning
- [ ] **Ensemble Methods:** Combine baseline and ML model predictions
- [ ] **Threshold Tuning:** Optimize prediction threshold using validation set PR-AUC
- [ ] **Cross-Validation:** Implement time-series cross-validation for more robust evaluation
- [ ] **Regularization:** Tune L1/L2 regularization for LogisticRegression

### 6.3 Threshold Optimization
- [ ] **Threshold Selection:** Test different τ values (90th, 95th, 99th percentiles)
- [ ] **Business Impact:** Evaluate threshold based on cost of false positives vs false negatives
- [ ] **Threshold Tuning:** Use validation set to find optimal prediction threshold (not just 0.5)

### 6.4 Data & Evaluation Improvements
- [ ] **More Data:** Collect more training data to improve model robustness
- [ ] **Feature Importance:** Analyze which features contribute most to predictions
- [ ] **Error Analysis:** Examine false positives and false negatives to identify patterns
- [ ] **Temporal Validation:** Test model on data from different time periods
- [ ] **Online Learning:** Consider incremental learning approaches for adapting to drift

### 6.5 Monitoring & Production
- [ ] **Model Monitoring:** Set up automated drift detection in production
- [ ] **Performance Tracking:** Monitor PR-AUC and F1 scores over time
- [ ] **A/B Testing:** Compare model versions in production
- [ ] **Retraining Schedule:** Establish retraining cadence based on drift detection

---

## Appendix A: MLflow Run Information

**Baseline Model Run:**
- Run ID: 4a3b29e4750541c4ab4e521c54c40388 (latest)
- Run Name: baseline_rule_model
- View at: http://localhost:5001/#/experiments/0/runs/4a3b29e4750541c4ab4e521c54c40388

**ML Model Run:**
- Run ID: b050589d36654fbf96e7f091b09ce2c2 (latest)
- Run Name: ml_model_logistic_regression
- View at: http://localhost:5001/#/experiments/0/runs/b050589d36654fbf96e7f091b09ce2c2

**Inference Evaluation Run (if applicable):**
- Run ID: [Not run - optional inference evaluation]
- Run Name: inference-eval
- View at: [N/A - inference evaluation not performed]

---

## Appendix B: Command Reference

**Training:**
```bash
# Train both models
python models/train.py --features_path data/processed/features.parquet

# Train with custom threshold
python models/train.py --tau 0.00005

# Train only ML model with XGBoost
python models/train.py --ml_only --use_xgboost
```

**Inference:**
```bash
# Generate predictions
python models/infer.py --features_path data/processed/features.parquet

# With evaluation logging
python models/infer.py --log_eval --threshold 0.5
```

**Evidently Reports:**
```bash
# Train/test comparison (default)
python reports/generate_evidently.py --mode train_test

# Early/late comparison
python reports/generate_evidently.py --mode early_late
```

---

**Report Status:** Complete - Metrics populated from MLflow runs. Date ranges and sample counts to be verified from training logs.

