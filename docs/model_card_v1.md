# Model Card: Crypto Volatility Spike Prediction

**Version:** 1.0  
**Date:** 2025-11-17  
**Milestone:** 3 - Modeling, Tracking, Evaluation

---

## 1. Model Details

### 1.1 Model Information

- **Model Name:** Crypto Volatility Spike Prediction System
- **Model Types:**
  - **Baseline Model:** Rule-based threshold classifier on `rolling_vol` feature
  - **ML Model:** Logistic Regression classifier (extensible to XGBoost)
- **Date Created:** 2025-11-17
- **Owner:** [Smridhi]
- **Version:** v1.0

### 1.2 Model Architecture

**Baseline Model:**
- Simple threshold rule: `if rolling_vol >= τ_baseline then predict 1 (spike) else predict 0 (normal)`
- Threshold `τ_baseline` set to 95th percentile of `rolling_vol` in training set
- No trainable parameters

**ML Model:**
- Algorithm: Logistic Regression (with optional XGBoost support)
- Features: `midprice_return`, `rolling_vol`, `spread`, `trade_intensity`
- Hyperparameters:
  - `max_iter`: 1000
  - `class_weight`: balanced
  - `tau` (threshold): 3.099017148247265e-05
- Class weights: Balanced (handles class imbalance)

---

## 2. Intended Use

### 2.1 Primary Use Case

**Scenario:** Real-time volatility spike detection for BTC-USD trading pair

The model predicts whether the 60-second forward volatility will exceed a spike threshold (τ), enabling:
- **Risk Management:** Early warning system for volatility events
- **Trading Decisions:** Signal generation for volatility-based strategies
- **Market Monitoring:** Automated detection of unusual market conditions

### 2.2 Intended Users

- **Quantitative Researchers:** Model development and validation
- **Traders:** Real-time volatility signal generation
- **Risk Analysts:** Market risk monitoring and alerting
- **System Developers:** Integration into trading and risk management systems

### 2.3 Out-of-Scope Use Cases

- **Not intended for:**
  - Direct trading execution without human oversight
  - Prediction of absolute price movements (only volatility)
  - Multi-asset or cross-pair predictions (currently BTC-USD only)
  - Long-term volatility forecasting (60-second horizon only)

---

## 3. Data

### 3.1 Data Source

- **Source:** Coinbase Advanced Trade WebSocket API
- **Trading Pair:** BTC-USD (primary)
- **Channel:** `ticker` channel
- **Update Frequency:** Real-time (typically 1-10 messages per second during active trading)
- **Data Format:** JSON ticker messages with `best_bid`, `best_ask`, `price`, `timestamp`

### 3.2 Time Period

- **Training Period:** 2025-11-17 03:28:19 UTC to 2025-11-17 03:34:45 UTC (60% of chronological data)
- **Validation Period:** 2025-11-17 03:34:45 UTC to 2025-11-17 03:36:54 UTC (20% of chronological data)
- **Test Period:** 2025-11-17 03:36:54 UTC to 2025-11-17 03:39:03 UTC (20% of chronological data)
- **Total Samples:** 3,351 (after feature engineering)

### 3.3 Preprocessing Steps

1. **Raw Data Ingestion:** WebSocket messages stored as NDJSON (`data/raw/YYYYMMDD.ndjson`)
2. **Feature Engineering:** Rolling window features computed (default: 60 ticks lookback)
   - See `docs/feature_spec.md` for detailed feature specifications
3. **Label Creation:** Binary labels based on volatility threshold τ
   - `y = 1` if `rolling_vol >= τ` (spike)
   - `y = 0` if `rolling_vol < τ` (normal)
4. **Data Splitting:** Time-based chronological split (60% train, 20% val, 20% test)
5. **Missing Value Handling:** Rows with NaN features removed

### 3.4 Feature Description

| Feature | Description | Type | Units |
|---------|-------------|------|-------|
| `midprice_return` | Percent change of midprice over lookback window | Continuous | Decimal (e.g., 0.01 = 1%) |
| `rolling_vol` | Rolling standard deviation of midprice returns | Continuous | Decimal |
| `spread` | Bid-ask spread | Continuous | USD |
| `trade_intensity` | Count of ticker messages within window | Discrete | Count |

**Additional Details:** See `docs/feature_spec.md` for complete feature specifications, formulas, and computation methods.

---

## 4. Performance

### 4.1 Evaluation Metrics

**Primary Metrics:**
- **PR-AUC (Precision-Recall Area Under Curve):** Primary metric for imbalanced classification
- **F1 Score:** Harmonic mean of precision and recall at threshold 0.5

**Secondary Metrics:**
- Precision, Recall (at threshold 0.5)

### 4.2 Baseline Model Performance

**Test Set Performance:**
- **PR-AUC:** 0.0000
- **F1 Score:** 0.0000
- **Precision:** 0.0000
- **Recall:** 0.0000

**Note:** Test set metrics are 0.0, likely due to no positive labels in the test set or threshold mismatch. Train/validation sets show perfect performance (PR-AUC=1.0, F1=1.0), suggesting the baseline threshold rule works well on the training distribution but may not generalize to the test period.

### 4.3 ML Model Performance

**Test Set Performance:**
- **PR-AUC:** 0.0000
- **F1 Score:** 0.0000
- **Precision:** 0.0000
- **Recall:** 0.0000

**Training/Validation Performance:**
- **Train PR-AUC:** 0.1796, **F1:** 0.1330, **Precision:** 0.0944, **Recall:** 0.2250
- **Val PR-AUC:** 0.2058, **F1:** 0.1504, **Precision:** 0.1176, **Recall:** 0.2083

**Note:** Test set metrics are 0.0, indicating no positive predictions on the test set. The model shows modest performance on train/validation sets (PR-AUC ~0.18-0.21), suggesting the model learns some signal but may need threshold tuning or additional data for the test period.

### 4.4 Performance Comparison

| Metric | Baseline (Test) | ML Model (Test) | Improvement |
|--------|----------------|-----------------|-------------|
| PR-AUC | 0.0000 | 0.0000 | N/A (both 0) |
| F1 Score | 0.0000 | 0.0000 | N/A (both 0) |

**Note:** Both models show 0.0 metrics on the test set, likely due to distribution shift or no positive labels in the test period. For comparison, on validation set: Baseline PR-AUC=1.0 vs ML Model PR-AUC=0.21, indicating the baseline rule works well on training distribution but the ML model may be more robust to distribution changes (though both fail on test set).

### 4.5 Conditions for Performance Degradation

Model performance may degrade under the following conditions:

1. **Market Regime Changes:**
   - Transition from bull to bear market (or vice versa)
   - Periods of extreme market stress (e.g., flash crashes, exchange outages)
   - Regulatory changes affecting crypto markets

2. **Data Distribution Shift:**
   - Changes in trading volume patterns
   - Evolution of market microstructure
   - Introduction of new trading mechanisms or order types

3. **Feature Quality Issues:**
   - API instability causing missing or delayed data
   - Network latency affecting real-time feature computation
   - Data quality degradation (e.g., stale prices, incorrect timestamps)

4. **Temporal Drift:**
   - Model trained on historical data may not generalize to future market conditions
   - Seasonal patterns or time-of-day effects not captured in training data

5. **Class Imbalance:**
   - Extreme class imbalance (very few positive examples) may reduce model sensitivity
   - Threshold selection may need recalibration for different market conditions

---

## 5. Ethical Considerations & Risks

### 5.1 Misuse Risks

**Potential Misuses:**
- **Automated Trading Without Safeguards:** Using model predictions for fully automated trading without human oversight could lead to significant financial losses
- **Market Manipulation:** Combining model signals with large order sizes could potentially influence market prices
- **Over-reliance on Predictions:** Treating model outputs as certainties rather than probabilistic signals

**Mitigation:**
- Model should be used as one input among many in decision-making processes
- Implement circuit breakers and position limits
- Regular monitoring and validation of model performance

### 5.2 False Positive Impact

**Consequences:**
- **Unnecessary Risk Reduction:** False positives may trigger risk management actions (e.g., position reduction) that reduce returns
- **Trading Costs:** Acting on false positives incurs transaction costs without benefit
- **Alert Fatigue:** High false positive rate may lead to ignoring legitimate warnings

**Business Impact:** Moderate - may reduce profitability but unlikely to cause catastrophic losses

### 5.3 False Negative Impact

**Consequences:**
- **Missed Volatility Events:** Failure to detect actual volatility spikes may expose positions to unexpected risk
- **Loss of Capital:** Unhedged positions during volatility spikes may experience significant drawdowns
- **Reputation Risk:** For risk management systems, missed events may damage credibility

**Business Impact:** High - false negatives represent the primary risk, as they result in exposure to unanticipated volatility

### 5.4 Limitations & Assumptions

**Key Assumptions:**
- Market microstructure remains relatively stable
- Historical patterns are indicative of future behavior
- Real-time data availability and quality
- BTC-USD market characteristics are representative

**Bias Considerations:**
- Model trained on specific time period may not generalize to all market conditions
- Class imbalance may bias model toward predicting majority class
- No explicit handling of market regime changes or structural breaks

---

## 6. Limitations

### 6.1 Market Regime Changes

**Issue:** Model trained on historical data may not adapt to fundamental changes in market behavior.

**Examples:**
- Transition from low-volatility to high-volatility regimes
- Changes in market maker behavior or liquidity provision
- Introduction of new trading venues or mechanisms

**Impact:** Model performance may degrade significantly during regime transitions.

**Mitigation:** Regular retraining, drift detection, and regime-aware modeling approaches.

### 6.2 API Instability

**Issue:** Dependency on Coinbase Advanced Trade WebSocket API for real-time data.

**Risks:**
- API outages or rate limiting
- Changes in API structure or message format
- Network connectivity issues

**Impact:** Model cannot generate predictions without real-time data feed.

**Mitigation:** Implement data quality checks, fallback mechanisms, and monitoring for API health.

### 6.3 Latency Considerations

**Issue:** Real-time feature computation and prediction latency may affect model utility.

**Constraints:**
- Feature computation requires rolling window of historical ticks
- Model inference time (typically < 1ms for Logistic Regression)
- Network latency for data ingestion

**Impact:** Predictions may be slightly delayed relative to market events, reducing edge in fast-moving markets.

**Mitigation:** Optimize feature computation pipeline, consider edge computing for low-latency deployment.

### 6.4 Label Choice & Threshold Selection

**Issue:** Binary classification threshold (τ) is a design choice that affects model behavior.

**Considerations:**
- Threshold selection (e.g., 95th vs 99th percentile) trades off sensitivity vs specificity
- Threshold may need recalibration for different market conditions
- Label definition (60-second forward volatility) may not align with all use cases

**Impact:** Model performance and behavior depend heavily on threshold selection.

**Mitigation:** Threshold optimization using validation set, business requirement alignment, sensitivity analysis.

### 6.5 Narrow Asset Coverage

**Issue:** Model trained and validated only on BTC-USD trading pair.

**Limitations:**
- May not generalize to other cryptocurrency pairs
- Different pairs may have different volatility characteristics
- No cross-asset or portfolio-level predictions

**Impact:** Model cannot be directly applied to other assets without retraining or validation.

**Mitigation:** Extend training to multiple pairs, test transfer learning approaches, asset-specific model variants.

### 6.6 Feature Limitations

**Issue:** Current feature set is relatively simple and may not capture all relevant signals.

**Missing Elements:**
- Order book depth and imbalance
- Cross-timeframe features
- Market microstructure indicators
- External factors (news, social sentiment)

**Impact:** Model may miss important volatility signals not captured by current features.

**Mitigation:** Feature engineering improvements, external data integration, model ensemble approaches.

### 6.7 Evaluation Limitations

**Issue:** Evaluation based on historical data may not reflect real-world performance.

**Considerations:**
- Look-ahead bias: Features computed with full window may not be available in real-time
- Transaction costs and slippage not accounted for
- No backtesting on out-of-sample periods beyond test set

**Impact:** Reported performance metrics may be optimistic relative to live trading results.

**Mitigation:** Paper trading validation, forward testing, realistic simulation environments.

---

## 7. Future Improvements

### 7.1 Model Enhancements
- [ ] Hyperparameter tuning and optimization
- [ ] XGBoost or ensemble model implementation
- [ ] Threshold optimization for prediction probability
- [ ] Online learning for adaptation to drift

### 7.2 Feature Engineering
- [ ] Additional features (order book, cross-timeframe, lag features)
- [ ] Feature scaling and normalization
- [ ] Feature importance analysis
- [ ] Interaction and polynomial features

### 7.3 Evaluation & Monitoring
- [ ] Extended backtesting on multiple time periods
- [ ] Real-time performance monitoring
- [ ] Automated drift detection and alerting
- [ ] A/B testing framework for model versions

### 7.4 Production Readiness
- [ ] Model serving infrastructure
- [ ] Latency optimization
- [ ] Error handling and fallback mechanisms
- [ ] Comprehensive logging and observability

---

## Appendix A: Model Artifacts

**Model Files:**
- Baseline model: `models/artifacts/baseline_model.pkl`
- ML model: `models/artifacts/logistic_regression_model.pkl`

**MLflow Tracking:**
- Tracking URI: `http://localhost:5001`
- Experiment: Default experiment
- Run names: `baseline_rule_model`, `ml_model_logistic_regression`

**Documentation:**
- Feature specification: `docs/feature_spec.md`
- Model evaluation: `reports/model_eval.md`
- Architecture: `docs/architecture.md`

---

## Appendix B: References

- Feature Specification: `docs/feature_spec.md`
- Model Evaluation Report: `reports/model_eval.md`
- Evidently Drift Reports: `reports/evidently/`
- Training Script: `models/train.py`
- Inference Script: `models/infer.py`

---

**Document Status:** v1.0 - Model card with metrics populated from MLflow runs. Date ranges and sample counts to be verified from training logs.

