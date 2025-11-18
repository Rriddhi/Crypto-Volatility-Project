# Feature Specification: Crypto Volatility Prediction

**Version:** 1.0  
**Date:** 2025-11-16  
**Milestone:** 2 - Feature Engineering, EDA & Evidently

---

## 1. Overview

This document specifies the feature engineering pipeline for predicting cryptocurrency volatility spikes. The system ingests real-time ticker data from Coinbase Advanced Trade, computes windowed features, and generates binary labels indicating whether future volatility exceeds a threshold.

**Objective:** Predict if the 60-second forward volatility will exceed a spike threshold (τ), enabling real-time risk management and trading decisions.

---

## 2. Data Source

### 2.1 Input Data
- **Source:** Coinbase Advanced Trade WebSocket API
- **Trading Pair:** BTC-USD (primary), extensible to additional pairs
- **Channel:** `ticker` channel
- **Message Format:** JSON with nested structure (`events[].tickers[]`)
- **Update Frequency:** Real-time (typically 1-10 messages per second during active trading)

### 2.2 Data Fields Extracted
From each ticker message, we extract:
- `product_id`: Trading pair identifier (e.g., "BTC-USD")
- `best_bid`: Best bid price (USD)
- `best_ask`: Best ask price (USD)
- `price`: Last trade price (USD)
- `timestamp`: Event timestamp (ISO 8601 or Unix timestamp)

### 2.3 Data Storage
- **Raw Data:** `data/raw/YYYYMMDD.ndjson` (one file per day, NDJSON format)
- **Processed Features:** `data/processed/features.parquet` (Parquet format for efficient querying)

---

## 3. Target Definition

### 3.1 Target Horizon
- **Horizon:** 60 seconds forward
- **Rationale:** Short enough for real-time trading decisions, long enough to capture meaningful volatility patterns

### 3.2 Volatility Proxy
The target variable is defined as:

**σ_future = rolling standard deviation of midprice returns over the next 60 seconds**

Where:
- `midprice = (best_bid + best_ask) / 2`
- `midprice_return = percent change of midprice`
- `σ_future = std(midprice_return[t+1 : t+60])`

This measures the realized volatility over the prediction window.

### 3.3 Label Definition
Binary classification label:

```
y = 1  if σ_future >= τ
y = 0  if σ_future < τ
```

Where:
- **τ (tau)** is the spike threshold, determined via EDA percentile analysis
- **Label = 1** indicates a "volatility spike" event
- **Label = 0** indicates normal volatility

**Note:** The threshold τ is selected based on percentile analysis of historical rolling volatility (see `notebooks/eda.ipynb`). Common choices are 95th or 99th percentile.

---

## 4. Features

All features are computed using a rolling window approach. The window size is configurable (default: 60 ticks) and represents the lookback period for feature computation.

### 4.1 Feature List

#### 4.1.1 `midprice`
- **Definition:** Average of best bid and best ask prices
- **Formula:** `midprice = (best_bid + best_ask) / 2`
- **Fallback:** If bid/ask unavailable, uses `price` field
- **Units:** USD
- **Type:** Continuous
- **Purpose:** Represents the "fair value" price at each timestamp

#### 4.1.2 `midprice_return`
- **Definition:** Percent change of midprice over the lookback window
- **Formula:** `midprice_return = (midprice[t] - midprice[t-window]) / midprice[t-window]`
- **Units:** Decimal (e.g., 0.01 = 1% return)
- **Type:** Continuous
- **Purpose:** Captures price movement magnitude, a key driver of volatility

#### 4.1.3 `rolling_vol`
- **Definition:** Rolling standard deviation of `midprice_return` over the window
- **Formula:** `rolling_vol = std(midprice_return[t-window : t])`
- **Units:** Decimal (same scale as returns)
- **Type:** Continuous
- **Purpose:** Historical volatility measure, directly related to the target variable

#### 4.1.4 `spread`
- **Definition:** Bid-ask spread
- **Formula:** `spread = best_ask - best_bid`
- **Units:** USD
- **Type:** Continuous
- **Purpose:** Market liquidity indicator; wider spreads often correlate with higher volatility

#### 4.1.5 `trade_intensity`
- **Definition:** Count of ticker messages (trades/updates) within the window
- **Formula:** `trade_intensity = count(messages[t-window : t])`
- **Units:** Count (integer)
- **Type:** Discrete
- **Purpose:** Trading activity indicator; higher intensity may signal volatility events

### 4.2 Window Parameters

- **Default Window Size:** 60 ticks
- **Configurable via:** Environment variable `FEATURE_WINDOW_SIZE` or code parameter
- **Rationale:** Balances signal quality (longer windows) with responsiveness (shorter windows)

### 4.3 Feature Schema

All features include:
- `timestamp`: ISO 8601 timestamp string
- `product_id`: Trading pair identifier (string)

Feature output schema:
```
{
    "timestamp": "2025-11-16T22:30:00.123456+00:00",
    "product_id": "BTC-USD",
    "midprice": 95432.50,
    "midprice_return": 0.0012,
    "rolling_vol": 0.0034,
    "spread": 0.10,
    "trade_intensity": 60
}
```

---

## 5. Threshold τ (Tau)

### 5.1 Selection Method
The spike threshold τ is determined via exploratory data analysis (EDA) using percentile plots of historical `rolling_vol` values.

**Process:**
1. Compute percentiles (50th, 75th, 90th, 95th, 97.5th, 99th, 99.5th, 99.9th) of `rolling_vol`
2. Visualize distribution and tail behavior
3. Select threshold based on:
   - **Sensitivity vs Specificity trade-off:** Lower threshold (e.g., 90th percentile) catches more spikes but may have more false positives. Higher threshold (e.g., 99th percentile) is more selective.
   - **Business requirements:** Risk tolerance and trading strategy
   - **Class balance:** Ensure sufficient positive examples for model training

### 5.2 Chosen Threshold

**Chosen τ = 3.099017148247265e-05**

**Selected Threshold:**
- Selected percentile: 95th
- Threshold value: 3.099017148247265e-05 (determined from training data)
- Justification: The 95th percentile threshold was selected to balance sensitivity (catching volatility spikes) with specificity (avoiding false positives). This threshold identifies approximately 5% of samples as positive class (volatility spikes), providing sufficient positive examples for model training while maintaining a meaningful definition of "spike" relative to normal volatility patterns.

---

## 6. Data Quality & Assumptions

### 6.1 Missing Data Handling

- **Missing bid/ask:** Falls back to `price` field for midprice calculation
- **Missing price data:** Tick is skipped (not processed)
- **Missing timestamp:** Uses current system time (UTC)
- **Missing product_id:** Tick is skipped (required field)

### 6.2 Outlier Handling

- **Price outliers:** No explicit filtering; relies on rolling window to smooth extreme values
- **Volatility spikes:** Preserved as they represent the target events we're predicting
- **Negative spreads:** Logged as warning, treated as missing data

### 6.3 Timestamp Alignment

- **Assumption:** Ticks arrive in approximate chronological order
- **Processing:** Features computed on a per-tick basis (not time-bucketed)
- **Window:** Rolling window uses tick count, not absolute time
- **Note:** For precise time-based windows, future versions may implement time-bucketing

### 6.4 Data Quality Checks

- **Subscription confirmations:** Filtered out (control messages)
- **Heartbeat messages:** Filtered out
- **Error messages:** Logged and skipped
- **Malformed JSON:** Logged and skipped

### 6.5 Feature Computation Requirements

- **Minimum data:** At least 2 ticks required before computing `midprice_return` (needed for percent change)
- **Window initialization:** First `window_size` ticks may have incomplete features (NaN for rolling metrics)
- **Product isolation:** Features computed separately per `product_id` (no cross-product aggregation)

---

## 7. Implementation Details

### 7.1 Feature Computation
- **Location:** `features/featurizer.py`
- **Class:** `FeatureCalculator` (reusable component)
- **Method:** Rolling window with pandas operations

### 7.2 Replay Capability
- **Script:** `scripts/replay.py`
- **Purpose:** Regenerate features from saved raw NDJSON files
- **Requirement:** Must produce bit-for-bit identical features as live consumer
- **Output:** `data/processed/features_replay.parquet`

### 7.3 Output Formats
- **Kafka:** JSON messages published to `ticks.features` topic
- **Parquet:** Batch writes to `data/processed/features.parquet` (append mode)

---

## 8. Validation & Testing

### 8.1 Feature Consistency
- **Test:** Compare `features.parquet` (live) vs `features_replay.parquet` (replay)
- **Requirement:** Features must be identical for the same input data
- **Method:** Load both Parquet files, compare row-by-row (allowing for minor floating-point differences)

### 8.2 Data Quality Monitoring
- **Tool:** Evidently AI (see `reports/evidently/`)
- **Metrics:** Data drift, feature distribution shifts, missing value rates
- **Comparison:** Early window vs late window to detect concept drift

---

## 9. Future Enhancements

Potential improvements for future iterations:
- Time-based windows (instead of tick-based)
- Order book imbalance features
- Multi-timeframe features (multiple window sizes)
- Feature normalization/scaling
- Lag features (previous N values)
- Cross-product features (if multiple pairs)

---

## Appendix A: Configuration

### Environment Variables
- `FEATURE_WINDOW_SIZE`: Window size for feature computation (default: 60)
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker address (default: localhost:9092)
- `KAFKA_INPUT_TOPIC`: Input topic for raw ticks (default: ticks.raw)
- `KAFKA_OUTPUT_TOPIC`: Output topic for features (default: ticks.features)
- `FEATURES_PARQUET_PATH`: Path to Parquet output (default: data/processed/features.parquet)

### File Locations
- Raw data: `data/raw/*.ndjson`
- Processed features: `data/processed/features.parquet`
- Replay features: `data/processed/features_replay.parquet`
- EDA notebook: `notebooks/eda.ipynb`

---

**Document Status:** Draft - Threshold τ to be finalized after EDA analysis

