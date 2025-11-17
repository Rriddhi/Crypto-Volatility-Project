# Testing Guide: Phase 1 Assignment

## Prerequisites

1. **Activate your conda environment:**
   ```bash
   conda activate crypto_volatility
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure Docker services are running:**
   ```bash
   docker compose -f docker/compose.yaml ps
   ```
   You should see both `kafka` and `mlflow` in `Up` status.

## Step 1: Test Kafka Connection

Verify Kafka is accessible:

```bash
python3 -c "from kafka import KafkaProducer; p = KafkaProducer(bootstrap_servers='localhost:9092'); print('Kafka connection OK'); p.close()"
```

If this fails, check that Kafka container is running.

## Step 2: Run the WebSocket Ingestor

In your activated conda environment:

```bash
cd "/Users/smridhipatwari/Desktop/AIM Carnegie Mellon/Courses /Operationalizing AI/Assignments/crypto-volatility-project"

# Set environment variables (optional, defaults are fine)
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC=ticks.raw
export PRODUCT_IDS=BTC-USD

# Run the ingestor
python3 scripts/ws_ingest.py
```

**What to look for:**
- You should see logs like:
  - `Starting ingestor: WS=wss://advanced-trade-ws.coinbase.com...`
  - `WebSocket connected to...`
  - `Sending subscription: {...}`
  - `Subscription confirmed: {...}`
  - `Sent message #1 to Kafka topic 'ticks.raw'`

**If you see errors:**
- **Connection refused:** Kafka might not be running. Check `docker compose ps`
- **WebSocket errors:** Check your internet connection, Coinbase API might be down
- **No messages:** Wait 30-60 seconds. Coinbase sends ticks periodically, not continuously

**Let it run for at least 2-3 minutes** to collect messages.

## Step 3: Verify Messages in Kafka

Open a **new terminal** (keep ingestor running in the first one):

```bash
conda activate crypto_volatility
cd "/Users/smridhipatwari/Desktop/AIM Carnegie Mellon/Courses /Operationalizing AI/Assignments/crypto-volatility-project"

# Consume and print messages
python3 scripts/kafka_consume_check.py --topic ticks.raw --min 5
```

**What to look for:**
- You should see JSON messages printed (pretty-formatted)
- Each message should have fields like `type`, `product_id`, `price`, `time`, etc.

**If you see "Read 0 message(s)":**
- The ingestor might not be running or not receiving messages
- Check the ingestor logs for errors
- Make sure you're consuming from the same topic (`ticks.raw`)

## Step 4: Check Raw Data Files

Verify that raw messages are being written to disk:

```bash
ls -lh data/raw/
cat data/raw/$(date +%Y%m%d).ndjson | head -5
```

You should see a file like `20251116.ndjson` with JSON lines.

## Step 5: Test Docker Container Build

Build the ingestor container:

```bash
cd "/Users/smridhipatwari/Desktop/AIM Carnegie Mellon/Courses /Operationalizing AI/Assignments/crypto-volatility-project"

docker build -f docker/Dockerfile.ingestor -t crypto-ingestor:latest .
```

**If build succeeds:**
- Test running it (note: it will connect to `kafka:9092` inside Docker network):
  ```bash
  docker run --rm --network docker_appnet \
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
    -e PRODUCT_IDS=BTC-USD \
    crypto-ingestor:latest
  ```

## Troubleshooting

### Kafka not accessible
```bash
# Check if Kafka is running
docker compose -f docker/compose.yaml ps

# Check Kafka logs
docker compose -f docker/compose.yaml logs kafka --tail 50

# Restart if needed
docker compose -f docker/compose.yaml restart kafka
```

### No messages appearing
1. **Check ingestor logs** - look for WebSocket connection errors
2. **Verify subscription format** - Coinbase API might have changed
3. **Test WebSocket manually:**
   ```bash
   # Install wscat if needed: npm install -g wscat
   wscat -c wss://advanced-trade-ws.coinbase.com
   # Then send: {"type":"subscribe","product_ids":["BTC-USD"],"channel":"ticker"}
   ```

### Messages in Kafka but not in files
- Check file permissions: `ls -la data/raw/`
- Check disk space: `df -h`

## Assignment Checklist

- [x] `docker/compose.yaml` - Kafka + MLflow services
- [x] `docker/Dockerfile.ingestor` - Containerized ingestor
- [x] `scripts/ws_ingest.py` - WebSocket ingestor with reconnect
- [x] `scripts/kafka_consume_check.py` - Kafka consumer validator
- [ ] `docs/scoping_brief.pdf` - Convert `docs/scoping_brief.md` to PDF
- [ ] Test: `docker compose ps` shows all services running
- [ ] Test: Run `ws_ingest.py` for 15 minutes, verify messages in `ticks.raw`
- [ ] Test: Container builds and runs successfully

## Next Steps

Once Phase 1 is working:
1. Convert `docs/scoping_brief.md` to PDF (use any markdown-to-PDF tool)
2. Run the ingestor for 15+ minutes to collect data
3. Verify all deliverables are in place
4. Document any issues or limitations


