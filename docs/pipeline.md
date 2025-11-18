# Pipeline Flow Documentation

This document describes the end-to-end data flow through the crypto volatility prediction pipeline, from raw data ingestion to model predictions.

---

## Pipeline Overview

The pipeline consists of five main stages:

1. **Data Ingestion:** WebSocket → Kafka → Raw Storage
2. **Feature Engineering:** Raw Data → Features → Kafka + Parquet
3. **Model Training:** Features → Train/Val/Test → Models → MLflow
4. **Model Inference:** Features → Models → Predictions
5. **Monitoring:** Data → Evidently → Drift Reports

---

## Stage 1: Data Ingestion

### Components
- **Script:** `scripts/ws_ingest.py`
- **Input:** Coinbase Advanced Trade WebSocket API
- **Output:** Kafka topic `ticks.raw` + NDJSON files

### Flow

```
Coinbase WebSocket API
    │
    │ (ticker messages)
    ▼
WebSocket Ingestor (ws_ingest.py)
    │
    ├──► Kafka Producer ──► ticks.raw topic
    │
    └──► File Writer ──► data/raw/YYYYMMDD.ndjson
```

### Process Details

1. **Connection:**
   - Establishes WebSocket connection to `wss://advanced-trade-ws.coinbase.com`
   - Sends subscription message for `ticker` channel, `BTC-USD` product

2. **Message Processing:**
   - Receives ticker messages in JSON format
   - Extracts: `timestamp`, `product_id`, `best_bid`, `best_ask`, `price`
   - Validates message structure

3. **Publishing:**
   - Publishes raw message to Kafka topic `ticks.raw`
   - Appends message to daily NDJSON file (`data/raw/YYYYMMDD.ndjson`)

4. **Error Handling:**
   - Exponential backoff reconnection on connection loss
   - Heartbeat monitoring
   - Graceful shutdown on SIGINT/SIGTERM

### Message Format

**Input (WebSocket):**
```json
{
  "channel": "ticker",
  "timestamp": "2025-11-17T00:34:11.02474387Z",
  "events": [{
    "type": "snapshot",
    "tickers": [{
      "type": "ticker",
      "product_id": "BTC-USD",
      "price": "94655.99",
      "best_bid": "94655.98",
      "best_ask": "94655.99"
    }]
  }]
}
```

**Output (Kafka/NDJSON):** Same JSON structure

---

## Stage 2: Feature Engineering

### Components
- **Script:** `features/featurizer.py`
- **Input:** Kafka topic `ticks.raw`
- **Output:** Kafka topic `ticks.features` + Parquet file

### Flow

```
Kafka ticks.raw topic
    │
    ▼
Feature Engineering Pipeline (featurizer.py)
    │
    │ (rolling window computation)
    │
    ├──► Kafka Producer ──► ticks.features topic
    │
    └──► Parquet Writer ──► data/processed/features.parquet
```

### Process Details

1. **Consumption:**
   - Consumes messages from Kafka `ticks.raw` topic
   - Maintains in-memory buffer of recent ticks (default: 10,000 rows)

2. **Feature Computation:**
   - **Window Size:** 60 ticks (configurable via `FEATURE_WINDOW_SIZE`)
   - **Features Computed:**
     - `midprice = (best_bid + best_ask) / 2`
     - `midprice_return = percent_change(midprice, window)`
     - `rolling_vol = std(midprice_return, window)`
     - `spread = best_ask - best_bid`
     - `trade_intensity = count(messages, window)`

3. **Output:**
   - **Kafka:** Publishes feature messages to `ticks.features` topic
   - **Parquet:** Appends features to `data/processed/features.parquet` in batches

4. **Data Quality:**
   - Filters out rows with NaN features
   - Handles missing bid/ask by falling back to `price`
   - Validates timestamp format

### Feature Message Format

```json
{
  "timestamp": "2025-11-17T00:34:11.02474387Z",
  "product_id": "BTC-USD",
  "midprice": 94655.985,
  "midprice_return": 0.0012,
  "rolling_vol": 0.0034,
  "spread": 0.01,
  "trade_intensity": 60
}
```

---

## Stage 3: Model Training

### Components
- **Script:** `models/train.py`
- **Input:** Parquet file `data/processed/features.parquet`
- **Output:** Model artifacts + MLflow runs

### Flow

```
features.parquet
    │
    ▼
Data Loading & Preprocessing
    │
    ├──► Label Creation (y = 1 if rolling_vol >= τ)
    │
    └──► Time-based Split (60/20/20)
         │
         ├──► Train Set (60%)
         ├──► Validation Set (20%)
         └──► Test Set (20%)
              │
              ▼
         Model Training
              │
              ├──► Baseline Model ──► baseline_model.pkl
              │                        └──► MLflow Run
              │
              └──► ML Model ──► logistic_regression_model.pkl
                                └──► MLflow Run
```

### Process Details

1. **Data Loading:**
   - Loads features from Parquet file
   - Sorts by timestamp (chronological order)
   - Validates required columns exist

2. **Label Creation:**
   - Threshold τ: 95th percentile of `rolling_vol` in training set
   - Binary label: `y = 1 if rolling_vol >= τ else 0`
   - Logs class distribution

3. **Data Splitting:**
   - **Method:** Time-based (chronological)
   - **Ratios:** 60% train, 20% validation, 20% test
   - **Rationale:** Prevents data leakage, simulates real-world deployment

4. **Baseline Model Training:**
   - **Algorithm:** Threshold rule on `rolling_vol`
   - **Threshold:** 95th percentile of training set
   - **Evaluation:** PR-AUC, F1, Precision, Recall on all splits

5. **ML Model Training:**
   - **Algorithm:** Logistic Regression
   - **Hyperparameters:**
     - `max_iter`: 1000
     - `class_weight`: balanced
   - **Features:** `midprice_return`, `rolling_vol`, `spread`, `trade_intensity`
   - **Evaluation:** PR-AUC, F1, Precision, Recall on all splits

6. **MLflow Logging:**
   - Logs parameters (model type, hyperparameters, threshold)
   - Logs metrics (train/val/test performance)
   - Saves model artifacts
   - Records run metadata (timestamp, git commit)

### Model Artifacts

- **Location:** `models/artifacts/`
- **Files:**
  - `baseline_model.pkl`: Pickled BaselineRuleModel
  - `logistic_regression_model.pkl`: Pickled LogisticRegression model

---

## Stage 4: Model Inference

### Components
- **Script:** `models/infer.py`
- **Input:** Features (Parquet or Kafka)
- **Output:** Predictions + optional MLflow evaluation

### Flow

```
Features (Parquet or Kafka)
    │
    ▼
Feature Preparation
    │
    ├──► Load Model (baseline or ML)
    │
    └──► Prepare Feature Matrix
         │
         ▼
    Model Prediction
         │
         ├──► Predictions (0 or 1)
         │
         └──► Probabilities (0.0 to 1.0)
              │
              └──► Optional: MLflow Evaluation Logging
```

### Process Details

1. **Model Loading:**
   - Loads model from `models/artifacts/`
   - Validates model type (baseline vs ML)

2. **Feature Preparation:**
   - Selects required feature columns
   - Handles missing values
   - Converts to numpy array

3. **Prediction:**
   - Generates binary predictions (threshold 0.5 default)
   - Generates prediction probabilities
   - Handles both baseline and ML models

4. **Evaluation (Optional):**
   - If labels available, computes metrics
   - Logs evaluation to MLflow
   - Saves predictions to `data/processed/predictions.parquet`

---

## Stage 5: Monitoring & Reporting

### Components
- **Script:** `reports/generate_evidently.py`
- **Input:** Train and test feature datasets
- **Output:** HTML and JSON drift reports

### Flow

```
Train Features (Parquet)
    │
    └───┐
        │
        ▼
    Evidently Analysis
        │
    Test Features (Parquet)
        │
        ▼
    Drift Detection
        │
        ├──► Data Drift Report (HTML + JSON)
        ├──► Data Quality Report (HTML + JSON)
        └──► Combined Report (HTML + JSON)
```

### Process Details

1. **Data Loading:**
   - Loads train and test feature datasets
   - Validates feature schemas match

2. **Drift Detection:**
   - Compares feature distributions (train vs test)
   - Computes drift scores (PSI, Kolmogorov-Smirnov)
   - Identifies drifted features

3. **Quality Checks:**
   - Missing value analysis
   - Outlier detection
   - Data type validation

4. **Report Generation:**
   - **HTML Reports:** Interactive visualizations
   - **JSON Reports:** Machine-readable metrics
   - **Location:** `reports/evidently/`

---

## Replay Pipeline

### Purpose
Regenerate features from saved raw data for validation and consistency checking.

### Components
- **Script:** `scripts/replay.py`
- **Input:** NDJSON files in `data/raw/`
- **Output:** `data/processed/features_replay.parquet`

### Flow

```
NDJSON Files (data/raw/YYYYMMDD.ndjson)
    │
    ▼
Replay Script (replay.py)
    │
    │ (same feature computation as live pipeline)
    │
    └──► features_replay.parquet
         │
         └──► Comparison with features.parquet
              (should be identical)
```

### Process Details

1. **File Reading:**
   - Reads NDJSON files chronologically
   - Parses ticker messages

2. **Feature Computation:**
   - Uses identical logic as `features/featurizer.py`
   - Same window size and feature calculations

3. **Validation:**
   - Compare `features.parquet` (live) vs `features_replay.parquet` (replay)
   - Should produce bit-for-bit identical features
   - Used to verify pipeline consistency

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_INPUT_TOPIC` | `ticks.raw` | Input Kafka topic |
| `KAFKA_OUTPUT_TOPIC` | `ticks.features` | Output Kafka topic |
| `FEATURE_WINDOW_SIZE` | `60` | Rolling window size (ticks) |
| `FEATURES_PARQUET_PATH` | `data/processed/features.parquet` | Parquet output path |
| `MLFLOW_TRACKING_URI` | `http://localhost:5001` | MLflow server URI |

### Pipeline Parameters

- **Window Size:** 60 ticks (configurable)
- **Train/Val/Test Split:** 60/20/20 (time-based)
- **Threshold τ:** 95th percentile of training `rolling_vol`
- **Parquet Batch Size:** 100 rows (configurable)

---

## Data Flow Summary

```
WebSocket → Kafka (raw) → Feature Engineering → Kafka (features) + Parquet
                                                      │
                                                      ▼
                                              Model Training
                                                      │
                                                      ├──► Models
                                                      └──► MLflow
                                                           │
                                                           ▼
                                                    Inference
                                                           │
                                                           └──► Predictions
```

---

## Performance Characteristics

### Latency

- **WebSocket → Kafka:** < 10ms
- **Kafka → Features:** < 50ms (per message)
- **Feature → Prediction:** < 5ms (model inference)

### Throughput

- **WebSocket Ingestion:** ~1-10 messages/second (depends on market activity)
- **Feature Engineering:** Processes messages in real-time
- **Model Training:** Batch process (minutes for ~64K samples)

### Storage

- **Raw Data:** ~30MB per day (NDJSON)
- **Features:** ~5MB per day (Parquet, compressed)
- **Model Artifacts:** ~100KB per model

---

## Error Handling & Recovery

### Ingestion Layer
- Automatic reconnection with exponential backoff
- Message validation and filtering
- Graceful shutdown handling

### Feature Engineering
- Kafka consumer offset management
- Parquet write error recovery
- Missing data handling

### Model Training
- Data validation before training
- Model serialization error handling
- MLflow logging error recovery

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-17
