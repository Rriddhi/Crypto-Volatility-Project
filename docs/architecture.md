# System Architecture

## Overview

This document describes the architecture of the crypto volatility prediction pipeline. The system ingests real-time cryptocurrency ticker data, computes volatility features, trains ML models, and provides predictions for risk management and trading decisions.

---

## High-Level Architecture

```
┌─────────────────┐
│ Coinbase WebSocket│
│   API (BTC-USD)  │
└────────┬─────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│ WebSocket       │─────▶│   Kafka      │
│ Ingestor        │      │  (ticks.raw) │
└─────────────────┘      └──────┬───────┘
                                │
                                ▼
                        ┌──────────────┐
                        │   Feature    │
                        │  Engineering │
                        │   Pipeline   │
                        └──────┬───────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
                ▼                               ▼
        ┌──────────────┐              ┌──────────────┐
        │   Kafka      │              │   Parquet    │
        │(ticks.features)│              │   Storage    │
        └──────┬───────┘              └──────────────┘
               │
               ▼
        ┌──────────────┐
        │   Model      │
        │  Training   │
        │  & Inference│
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │   MLflow     │
        │  Tracking    │
        └──────────────┘
```

---

## Components

### 1. Data Ingestion Layer

**WebSocket Ingestor** (`scripts/ws_ingest.py`)
- **Purpose:** Real-time data ingestion from Coinbase Advanced Trade WebSocket API
- **Functionality:**
  - Establishes WebSocket connection to Coinbase API
  - Subscribes to `ticker` channel for BTC-USD
  - Handles reconnection with exponential backoff
  - Publishes raw ticker messages to Kafka topic `ticks.raw`
  - Saves raw data to NDJSON files (`data/raw/YYYYMMDD.ndjson`)
- **Output:** Raw ticker messages in JSON format

### 2. Message Streaming Layer

**Apache Kafka** (Docker container)
- **Purpose:** Distributed message streaming and buffering
- **Configuration:**
  - Mode: KRaft (no ZooKeeper dependency)
  - Port: 9092 (host) → 9094 (container)
  - Topics:
    - `ticks.raw`: Raw ticker messages from WebSocket
    - `ticks.features`: Computed features for downstream consumption
- **Benefits:**
  - Decouples data ingestion from processing
  - Provides message buffering and replay capability
  - Enables multiple consumers for different use cases

### 3. Feature Engineering Layer

**Feature Pipeline** (`features/featurizer.py`)
- **Purpose:** Compute rolling window features from raw ticker data
- **Input:** Raw ticker messages from Kafka (`ticks.raw`)
- **Features Computed:**
  - `midprice`: Average of best bid and best ask
  - `midprice_return`: Percent change over lookback window
  - `rolling_vol`: Rolling standard deviation of returns
  - `spread`: Bid-ask spread (USD)
  - `trade_intensity`: Count of ticker messages in window
- **Output:**
  - Kafka topic: `ticks.features` (real-time streaming)
  - Parquet file: `data/processed/features.parquet` (batch storage)
- **Window Size:** Configurable (default: 60 ticks)

### 4. Model Training & Inference Layer

**Training Script** (`models/train.py`)
- **Purpose:** Train baseline and ML models with MLflow tracking
- **Models:**
  - **Baseline:** Rule-based threshold classifier on `rolling_vol`
  - **ML Model:** Logistic Regression (extensible to XGBoost)
- **Features:** Time-based train/val/test splits (60/20/20)
- **Metrics:** PR-AUC, F1, Precision, Recall
- **Output:** Trained model artifacts saved to `models/artifacts/`

**Inference Script** (`models/infer.py`)
- **Purpose:** Generate predictions on new data
- **Input:** Feature data (Parquet or Kafka)
- **Output:** Predictions with optional MLflow evaluation logging

### 5. Model Tracking & Registry

**MLflow** (Docker container)
- **Purpose:** Experiment tracking, model versioning, and artifact storage
- **Configuration:**
  - Port: 5001 (host) → 5000 (container)
  - Backend: SQLite (`mlruns/mlflow.db`)
  - Artifact storage: `mlruns/` directory
- **Tracked Information:**
  - Model parameters and hyperparameters
  - Training metrics (PR-AUC, F1, Precision, Recall)
  - Model artifacts (pickle files)
  - Run metadata (timestamps, git commits)

### 6. Data Storage

**Raw Data Storage:**
- Format: NDJSON (one file per day)
- Location: `data/raw/YYYYMMDD.ndjson`
- Purpose: Historical data archive and replay capability

**Processed Data Storage:**
- Format: Parquet (columnar, efficient for analytics)
- Location: `data/processed/features.parquet`
- Purpose: Feature storage for model training and analysis

**Model Artifacts:**
- Format: Pickle files
- Location: `models/artifacts/`
- Files:
  - `baseline_model.pkl`
  - `logistic_regression_model.pkl`

### 7. Monitoring & Reporting

**Evidently AI** (`reports/generate_evidently.py`)
- **Purpose:** Data drift detection and data quality monitoring
- **Reports Generated:**
  - Data drift reports (train vs test distribution)
  - Data quality reports
  - Combined analysis reports
- **Output:** HTML and JSON reports in `reports/evidently/`

---

## Data Flow

### Real-Time Pipeline Flow

1. **Ingestion:**
   - Coinbase WebSocket → `scripts/ws_ingest.py` → Kafka `ticks.raw` → NDJSON files

2. **Feature Engineering:**
   - Kafka `ticks.raw` → `features/featurizer.py` → Kafka `ticks.features` + Parquet

3. **Model Training (Batch):**
   - Parquet features → `models/train.py` → Trained models → MLflow tracking

4. **Inference (Real-Time or Batch):**
   - Kafka `ticks.features` or Parquet → `models/infer.py` → Predictions

### Batch Processing Flow

1. **Replay Pipeline:**
   - NDJSON files → `scripts/replay.py` → Features → `features_replay.parquet`
   - Used for validation and consistency checking

2. **Model Evaluation:**
   - Features → Train/Val/Test splits → Model training → Metrics → MLflow

3. **Drift Analysis:**
   - Train features vs Test features → Evidently → HTML reports

---

## Technology Stack

### Infrastructure
- **Containerization:** Docker & Docker Compose
- **Message Streaming:** Apache Kafka (KRaft mode)
- **Model Tracking:** MLflow

### Programming Languages & Libraries
- **Language:** Python 3.x
- **Data Processing:** pandas, numpy, pyarrow
- **Machine Learning:** scikit-learn, MLflow
- **Streaming:** kafka-python, websocket-client
- **Monitoring:** Evidently AI
- **Visualization:** matplotlib, seaborn

### External Services
- **Data Source:** Coinbase Advanced Trade WebSocket API
- **Trading Pair:** BTC-USD (primary)

---

## Deployment Architecture

### Development Environment
- **Local Docker Compose:** Single-node Kafka + MLflow
- **File-based Storage:** Local filesystem for data and artifacts
- **SQLite:** MLflow backend (development)

### Production Considerations
- **Kafka:** Multi-broker cluster for high availability
- **MLflow:** PostgreSQL backend, S3 artifact storage
- **Monitoring:** Prometheus + Grafana for system metrics
- **Logging:** Centralized logging (ELK stack or similar)
- **Container Orchestration:** Kubernetes for scaling

---

## Scalability & Performance

### Current Limitations
- Single Kafka broker (development setup)
- Single-threaded feature computation
- In-memory feature buffering (10,000 rows max)

### Scaling Opportunities
- **Horizontal Scaling:** Multiple feature engineering workers consuming from Kafka
- **Parallel Processing:** Multi-threaded feature computation
- **Caching:** Redis for frequently accessed features
- **Batch Processing:** Spark or Dask for large-scale feature engineering

---

## Security Considerations

### Current Implementation
- **Network:** Local Docker network isolation
- **Data:** No encryption at rest (development)
- **API:** No authentication for MLflow (development)

### Production Requirements
- **TLS/SSL:** Encrypted Kafka and WebSocket connections
- **Authentication:** API keys for Coinbase, MLflow authentication
- **Authorization:** Role-based access control for MLflow
- **Secrets Management:** Environment variables or secret management service

---

## Error Handling & Resilience

### WebSocket Ingestion
- Exponential backoff reconnection
- Heartbeat monitoring
- Graceful shutdown handling

### Feature Pipeline
- Kafka consumer offset management
- Parquet write error handling
- Missing data handling (NaN filtering)

### Model Training
- Data validation before training
- Model serialization error handling
- MLflow logging error recovery

---

## Future Enhancements

1. **Multi-Asset Support:** Extend to multiple trading pairs
2. **Order Book Features:** Incorporate order book depth data
3. **Real-Time Inference:** Kafka consumer for live predictions
4. **Model Serving:** REST API or gRPC service for predictions
5. **A/B Testing:** Framework for comparing model versions
6. **Automated Retraining:** Scheduled retraining based on drift detection

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-17
