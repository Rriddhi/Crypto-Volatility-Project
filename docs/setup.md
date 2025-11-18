# Setup Instructions

This guide will help you set up the crypto volatility prediction pipeline on your local machine.

---

## Prerequisites

### Required Software

1. **Python 3.8+**
   - Check version: `python3 --version`
   - Download: https://www.python.org/downloads/

2. **Docker & Docker Compose**
   - Docker Desktop: https://www.docker.com/products/docker-desktop
   - Verify installation:
     ```bash
     docker --version
     docker-compose --version
     ```

3. **Git** (for cloning the repository)
   - Verify: `git --version`

### System Requirements

- **OS:** macOS, Linux, or Windows (with WSL2)
- **RAM:** Minimum 4GB (8GB recommended)
- **Disk Space:** ~2GB for Docker images and data
- **Network:** Internet connection for WebSocket API and Docker image pulls

---

## Installation Steps

### 1. Clone Repository

```bash
git clone <repository-url>
cd crypto-volatility-project
```

### 2. Create Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected packages:**
- pandas, numpy, pyarrow (data processing)
- scikit-learn (machine learning)
- mlflow (model tracking)
- evidently (data drift monitoring)
- kafka-python, websocket-client (streaming)
- matplotlib, seaborn (visualization)
- jupyter, ipykernel (notebooks)

### 4. Start Docker Services

Navigate to the `docker/` directory and start Kafka and MLflow:

```bash
cd docker
docker-compose up -d
```

**Services started:**
- **Kafka:** Available at `localhost:9092`
- **MLflow UI:** Available at `http://localhost:5001`

**Verify services are running:**
```bash
docker ps
# Should show 'kafka' and 'mlflow' containers
```

**Check service logs:**
```bash
docker-compose logs kafka
docker-compose logs mlflow
```

### 5. Verify Kafka is Running

```bash
# From project root
python3 scripts/kafka_consume_check.py
```

Expected output: Connection successful message.

### 6. Verify MLflow is Accessible

Open in browser: `http://localhost:5001`

You should see the MLflow UI with an empty experiment list.

---

## Configuration

### Environment Variables

Create a `.env` file in the project root (optional, defaults are provided):

```bash
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_INPUT_TOPIC=ticks.raw
KAFKA_OUTPUT_TOPIC=ticks.features

# Feature Engineering
FEATURE_WINDOW_SIZE=60
FEATURES_PARQUET_PATH=data/processed/features.parquet
PARQUET_BATCH_SIZE=100

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5001

# WebSocket (Coinbase)
COINBASE_WS_URL=wss://advanced-trade-ws.coinbase.com
```

### Directory Structure

Ensure the following directories exist:

```bash
mkdir -p data/raw
mkdir -p data/processed
mkdir -p models/artifacts
mkdir -p reports/evidently
mkdir -p mlruns
```

---

## Verification & Testing

### 1. Test WebSocket Ingestion

Start the WebSocket ingestor (in a separate terminal):

```bash
python3 scripts/ws_ingest.py
```

**Expected behavior:**
- WebSocket connection established
- Subscription message sent
- Ticker messages received and logged
- Messages published to Kafka
- Raw data saved to `data/raw/YYYYMMDD.ndjson`

**Stop:** Press `Ctrl+C` to gracefully shutdown.

### 2. Test Feature Engineering

Start the feature engineering pipeline (in a separate terminal):

```bash
python3 features/featurizer.py
```

**Expected behavior:**
- Kafka consumer connected
- Features computed from raw ticks
- Features published to Kafka `ticks.features`
- Features appended to `data/processed/features.parquet`

**Stop:** Press `Ctrl+C` to gracefully shutdown.

### 3. Test Model Training

Train models with sample data:

```bash
python3 models/train.py --features_path data/processed/features.parquet
```

**Expected behavior:**
- Features loaded from Parquet
- Train/val/test splits created
- Baseline model trained and evaluated
- ML model trained and evaluated
- Metrics logged to MLflow
- Model artifacts saved to `models/artifacts/`

**View results:** Open `http://localhost:5001` to see MLflow runs.

### 4. Test Replay Pipeline

Replay features from raw data:

```bash
python3 scripts/replay.py --input_dir data/raw --output_path data/processed/features_replay.parquet
```

**Expected behavior:**
- NDJSON files read from `data/raw/`
- Features computed identically to live pipeline
- Output saved to `features_replay.parquet`

---

## Troubleshooting

### Docker Issues

**Problem:** Docker containers won't start
```bash
# Check Docker daemon is running
docker info

# Restart Docker Desktop (macOS/Windows)
# Or restart Docker service (Linux)
sudo systemctl restart docker
```

**Problem:** Port already in use
```bash
# Check what's using the port
# macOS/Linux:
lsof -i :9092
lsof -i :5001

# Kill the process or change ports in docker/compose.yaml
```

### Kafka Issues

**Problem:** Cannot connect to Kafka
```bash
# Check Kafka container is running
docker ps | grep kafka

# Check Kafka logs
docker-compose -f docker/compose.yaml logs kafka

# Restart Kafka
docker-compose -f docker/compose.yaml restart kafka
```

**Problem:** Topics not created
- Kafka auto-creates topics by default
- Manually create if needed:
  ```bash
  docker exec -it kafka kafka-topics --create \
    --bootstrap-server localhost:9092 \
    --topic ticks.raw \
    --partitions 1 \
    --replication-factor 1
  ```

### Python Dependencies

**Problem:** Import errors
```bash
# Ensure virtual environment is activated
which python3  # Should show venv path

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

**Problem:** pyarrow installation fails
```bash
# macOS: May need Xcode command line tools
xcode-select --install

# Linux: May need build tools
sudo apt-get install build-essential
```

### MLflow Issues

**Problem:** MLflow UI not accessible
```bash
# Check MLflow container
docker ps | grep mlflow

# Check MLflow logs
docker-compose -f docker/compose.yaml logs mlflow

# Verify port mapping
curl http://localhost:5001
```

**Problem:** Cannot write to mlruns directory
```bash
# Check permissions
ls -la mlruns/

# Fix permissions if needed
chmod -R 755 mlruns/
```

### WebSocket Issues

**Problem:** WebSocket connection fails
- Check internet connection
- Verify Coinbase API is accessible
- Check firewall settings
- Review WebSocket URL in code

**Problem:** No messages received
- Verify subscription message format
- Check product_id is correct (BTC-USD)
- Review WebSocket logs for errors

---

## Development Setup

### IDE Configuration

**VS Code:**
- Install Python extension
- Set Python interpreter to virtual environment
- Install Pylance for type checking

**PyCharm:**
- Configure Python interpreter to virtual environment
- Mark `src/` as source root
- Configure run configurations for scripts

### Pre-commit Hooks (Optional)

```bash
pip install pre-commit
pre-commit install
```

### Running Tests

```bash
# Run feature consistency check
python3 scripts/compare_live_vs_replay.py

# Run data quality checks
python3 scripts/check_features.py
```

---

## Production Deployment Considerations

### Differences from Development

1. **Kafka:** Multi-broker cluster with replication
2. **MLflow:** PostgreSQL backend, S3 artifact storage
3. **Monitoring:** Prometheus + Grafana
4. **Logging:** Centralized logging (ELK stack)
5. **Secrets:** Environment variables or secret management
6. **Container Orchestration:** Kubernetes

### Security Hardening

- Enable TLS/SSL for Kafka
- Implement MLflow authentication
- Use API keys for Coinbase (if required)
- Encrypt data at rest
- Network isolation between services

---

## Next Steps

After setup is complete:

1. **Ingest Data:** Run `scripts/ws_ingest.py` to collect data
2. **Generate Features:** Run `features/featurizer.py` to compute features
3. **Train Models:** Run `models/train.py` to train models
4. **View Results:** Open MLflow UI at `http://localhost:5001`
5. **Generate Reports:** Run `reports/generate_evidently.py` for drift analysis

---

## Additional Resources

- **Kafka Documentation:** https://kafka.apache.org/documentation/
- **MLflow Documentation:** https://mlflow.org/docs/latest/index.html
- **Coinbase API Docs:** https://docs.cloud.coinbase.com/advanced-trade/docs/ws-overview
- **Project README:** See `README.md` for project overview

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-17
