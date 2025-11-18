# Crypto Volatility Prediction Project

Real-time cryptocurrency volatility spike prediction system for BTC-USD using Coinbase Advanced Trade WebSocket data, Kafka streaming, and machine learning models.

## Overview

This project implements an end-to-end ML pipeline for predicting 60-second forward volatility spikes in cryptocurrency markets. The system ingests real-time ticker data, computes rolling window features, trains baseline and ML models, and provides predictions for risk management and trading decisions.

**Key Features:**
- Real-time WebSocket data ingestion from Coinbase Advanced Trade API
- Kafka-based message streaming and buffering
- Rolling window feature engineering (midprice, returns, volatility, spread, trade intensity)
- Baseline rule-based model and Logistic Regression classifier
- MLflow experiment tracking and model versioning
- Evidently AI data drift detection and monitoring
- Comprehensive documentation and model cards

## Project Structure

```
crypto-volatility-project/
├── docker/                 # Docker Compose configuration
│   └── compose.yaml        # Kafka + MLflow services
├── docs/                   # Documentation
│   ├── architecture.md     # System architecture
│   ├── feature_spec.md     # Feature specifications
│   ├── model_card_v1.md    # Model card (Milestone 3)
│   ├── genai_appendix.md   # GenAI tool usage documentation
│   ├── pipeline.md         # Pipeline flow documentation
│   ├── scoping_brief.md    # Project scoping
│   └── setup.md            # Setup instructions
├── features/               # Feature engineering
│   └── featurizer.py       # Main feature computation pipeline
├── models/                 # Model training and inference
│   ├── train.py           # Model training with MLflow
│   ├── infer.py           # Model inference
│   └── artifacts/         # Trained model artifacts
├── notebooks/              # Jupyter notebooks
│   └── eda.ipynb          # Exploratory data analysis
├── reports/                # Reports and analysis
│   ├── model_eval.md      # Model evaluation report
│   ├── generate_evidently.py  # Evidently report generation
│   └── evidently/         # Evidently drift reports
├── scripts/                # Utility scripts
│   ├── ws_ingest.py       # WebSocket data ingestion
│   ├── replay.py          # Feature replay for validation
│   ├── kafka_consume_check.py  # Kafka connectivity check
│   ├── check_features.py  # Feature validation
│   └── compare_live_vs_replay.py  # Replay validation
└── data/                   # Data storage
    ├── raw/               # Raw NDJSON files
    └── processed/         # Processed Parquet files
```

## Quick Start

### Prerequisites

- Python 3.8+
- Docker and Docker Compose
- Git

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Rriddhi/Crypto-Volatility-Project.git
   cd Crypto-Volatility-Project
   ```

2. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Docker services:**
   ```bash
   cd docker
   docker-compose up -d
   ```

5. **Verify services:**
   - Kafka: `localhost:9092`
   - MLflow UI: `http://localhost:5001`

### Running the Pipeline

1. **Ingest data:**
   ```bash
   python scripts/ws_ingest.py
   ```

2. **Generate features:**
   ```bash
   python features/featurizer.py
   ```

3. **Train models:**
   ```bash
   python models/train.py --features_path data/processed/features.parquet
   ```

4. **Generate predictions:**
   ```bash
   python models/infer.py --features_path data/processed/features.parquet
   ```

5. **Generate Evidently reports:**
   ```bash
   python reports/generate_evidently.py --mode train_test
   ```

## Milestones

### Milestone 1: Data Ingestion & Infrastructure
- Docker Compose setup (Kafka + MLflow)
- WebSocket ingestion script
- Kafka integration
- Documentation (scoping brief, architecture, setup)

### Milestone 2: Feature Engineering, EDA & Evidently
- Feature engineering pipeline
- Feature specification document
- EDA notebook
- Replay script for validation
- Evidently drift detection reports

### Milestone 3: Modeling, Tracking, Evaluation
- Baseline and ML model training
- Model inference script
- MLflow experiment tracking
- Model Card (docs/model_card_v1.md)
- Model Evaluation Report (reports/model_eval.md)
- GenAI Appendix (docs/genai_appendix.md)

## Model Performance

**Baseline Model (Rule-based):**
- Train/Val PR-AUC: 1.0000
- Test PR-AUC: 0.0000 (no positive labels in test set)

**ML Model (Logistic Regression):**
- Train PR-AUC: 0.1796
- Val PR-AUC: 0.2058
- Test PR-AUC: 0.0000 (no positive labels in test set)

*Note: Test set shows 0.0 metrics due to no positive labels in the test period, indicating distribution shift.*

## Key Documentation

- **Model Card:** `docs/model_card_v1.md` - Complete model documentation
- **Model Evaluation:** `reports/model_eval.md` - Performance analysis
- **Architecture:** `docs/architecture.md` - System design
- **Setup Guide:** `docs/setup.md` - Installation instructions
- **Pipeline Flow:** `docs/pipeline.md` - Data flow documentation
- **Feature Spec:** `docs/feature_spec.md` - Feature definitions
- **GenAI Usage:** `docs/genai_appendix.md` - AI tool documentation

## Technology Stack

- **Data Processing:** pandas, numpy, pyarrow
- **Machine Learning:** scikit-learn, MLflow
- **Streaming:** Kafka, kafka-python
- **Data Source:** Coinbase Advanced Trade WebSocket API
- **Monitoring:** Evidently AI
- **Containerization:** Docker, Docker Compose

## Data

- **Source:** Coinbase Advanced Trade WebSocket API (BTC-USD)
- **Raw Data:** NDJSON format (`data/raw/YYYYMMDD.ndjson`)
- **Processed Data:** Parquet format (`data/processed/features.parquet`)
- **Time Period:** 2025-11-17 (sample dataset)

## Model Artifacts

Trained models are saved in `models/artifacts/`:
- `baseline_model.pkl` - Rule-based threshold classifier
- `logistic_regression_model.pkl` - Logistic Regression classifier

## MLflow Tracking

MLflow UI available at: `http://localhost:5001`

View experiment runs, metrics, parameters, and model artifacts.

## License

This project is part of an academic assignment for Operationalizing AI course.

## Author

Smridhi Patwari

## Repository

GitHub: https://github.com/Rriddhi/Crypto-Volatility-Project

---

**For detailed setup and usage instructions, see `docs/setup.md` and `docs/pipeline.md`.**

