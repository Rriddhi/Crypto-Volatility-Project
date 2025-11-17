# Crypto Volatility Prediction: Scoping Brief

## Use Case

**Real-time cryptocurrency volatility prediction for algorithmic trading risk management.**

We aim to predict short-term volatility (60-second forward window) for BTC-USD using live ticker data from Coinbase Advanced Trade WebSocket API. The system ingests real-time price updates, computes rolling volatility features, and provides predictions to support trading decisions such as position sizing, stop-loss placement, and risk-adjusted entry/exit timing.

## 60-Second Prediction Goal

**Target:** Predict the realized volatility over the next 60 seconds using:
- Current bid/ask spread
- Recent price returns (rolling windows)
- Historical volatility patterns
- Order book depth indicators (if available)

**Output:** A volatility forecast (e.g., annualized volatility percentage) that traders can use to:
- Adjust position sizes dynamically
- Set adaptive stop-loss levels
- Identify high-volatility periods for risk reduction

## Success Metric

**Primary Metric:** Mean Absolute Error (MAE) of predicted vs. realized 60-second volatility
- **Target:** MAE < 2.0% (annualized volatility units)
- **Baseline:** Simple historical rolling standard deviation (benchmark)

**Secondary Metrics:**
- Prediction latency < 100ms (from tick arrival to prediction)
- System uptime > 99.5% (WebSocket reconnection resilience)
- Data freshness: predictions based on data no older than 5 seconds

**Evaluation Period:** 1 week of live trading data (24/7 operation)

## Risk Assumptions

1. **Data Quality Risks:**
   - Coinbase WebSocket may experience temporary outages or rate limits
   - **Mitigation:** Exponential backoff reconnection, heartbeat monitoring, optional fallback to REST API

2. **Model Drift:**
   - Crypto market regimes change rapidly (bull/bear/consolidation)
   - **Mitigation:** Continuous monitoring with Evidently, periodic model retraining (daily/weekly), concept drift detection

3. **Latency Risks:**
   - Network delays or Kafka lag could make predictions stale
   - **Mitigation:** End-to-end latency monitoring, Kafka consumer lag alerts, WebSocket connection health checks

4. **Overfitting to Historical Patterns:**
   - Model may not generalize to unseen market conditions
   - **Mitigation:** Train on diverse time periods (bull/bear/sideways), use regularization, cross-validation on time-series splits

5. **Operational Risks:**
   - Docker container failures, MLflow tracking server downtime
   - **Mitigation:** Health checks, auto-restart policies, persistent Kafka offsets, MLflow artifact backups

6. **Regulatory/Exchange Risks:**
   - Coinbase API changes or service discontinuation
   - **Mitigation:** Abstract API layer, support multiple exchange sources, maintain historical data archive

---

**Document Version:** 1.0  
**Date:** 2025-11-16  
**Author:** Crypto Volatility Project Team


