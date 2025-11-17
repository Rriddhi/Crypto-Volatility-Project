#!/usr/bin/env python3
"""
Feature Engineering Pipeline for Crypto Volatility Prediction.

Consumes raw ticker data from Kafka, computes windowed features,
and publishes to both Kafka and Parquet storage.
"""
import json
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from kafka import KafkaConsumer, KafkaProducer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Configuration (can be overridden via environment variables)
DEFAULT_WINDOW_SIZE = int(os.getenv("FEATURE_WINDOW_SIZE", "60"))  # 60-second window
DEFAULT_KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_INPUT_TOPIC = os.getenv("KAFKA_INPUT_TOPIC", "ticks.raw")
DEFAULT_OUTPUT_TOPIC = os.getenv("KAFKA_OUTPUT_TOPIC", "ticks.features")
DEFAULT_PARQUET_PATH = os.getenv("FEATURES_PARQUET_PATH", "data/processed/features.parquet")
DEFAULT_PARQUET_BATCH_SIZE = int(os.getenv("PARQUET_BATCH_SIZE", "100"))


@dataclass
class FeatureConfig:
    """Configuration for feature computation."""
    window_size: int = DEFAULT_WINDOW_SIZE
    parquet_batch_size: int = DEFAULT_PARQUET_BATCH_SIZE
    max_buffer_rows: int = 10000  # Max rows to keep in memory


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse timestamp from various formats."""
    if value is None:
        return None
    
    # Already a datetime
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    
    # ISO format string
    if isinstance(value, str):
        try:
            # Try ISO format
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except Exception:
            pass
    
    # Unix timestamp (int or float)
    try:
        ts = float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass
    
    return None


def to_float(value: Any) -> Optional[float]:
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
        return float(value)
    except Exception:
        return None


def parse_tick_message(payload: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse a raw ticker message from Coinbase WebSocket.
    
    Handles both nested format (events[].tickers[]) and flat format.
    
    Returns dict with: timestamp, product_id, best_bid, best_ask, price
    Returns None if message is malformed or missing required fields.
    """
    try:
        text = payload.decode("utf-8")
        obj = json.loads(text)
    except Exception as e:
        logger.debug(f"Failed to parse message: {e}")
        return None
    
    # Coinbase Advanced Trade sends nested format: events[].tickers[]
    ticker_data = None
    if "events" in obj and isinstance(obj["events"], list) and len(obj["events"]) > 0:
        event = obj["events"][0]
        if "tickers" in event and isinstance(event["tickers"], list) and len(event["tickers"]) > 0:
            ticker_data = event["tickers"][0]
    
    # Skip subscription confirmations and control messages
    msg_type = obj.get("type", "")
    if msg_type in ("subscriptions", "error", "heartbeat"):
        return None
    # Also check nested type
    if ticker_data and ticker_data.get("type") in ("subscriptions", "error", "heartbeat"):
        return None
    
    # If no nested format, try top-level fields
    if ticker_data is None:
        ticker_data = obj
    
    # Extract product_id (required)
    product_id = (
        ticker_data.get("product_id")
        or ticker_data.get("symbol")
        or ticker_data.get("pair")
        or obj.get("product_id")  # Fallback to top-level
    )
    if not product_id:
        logger.debug("Missing product_id in message")
        return None
    
    # Extract prices
    best_bid = to_float(
        ticker_data.get("best_bid")
        or ticker_data.get("bid")
        or obj.get("best_bid")
    )
    best_ask = to_float(
        ticker_data.get("best_ask")
        or ticker_data.get("ask")
        or obj.get("best_ask")
    )
    price = to_float(
        ticker_data.get("price")
        or ticker_data.get("last")
        or ticker_data.get("trade_price")
        or obj.get("price")
    )
    
    # Extract timestamp
    ts_raw = (
        ticker_data.get("time")
        or ticker_data.get("timestamp")
        or ticker_data.get("ts")
        or ticker_data.get("event_time")
        or ticker_data.get("created_at")
        or obj.get("time")
        or obj.get("timestamp")
    )
    timestamp = parse_timestamp(ts_raw)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
        logger.debug(f"Using current time for message without timestamp")
    
    # Need at least bid+ask or price to compute midprice
    if best_bid is None and best_ask is None and price is None:
        logger.debug(f"Missing price data for product {product_id}")
        return None
    
    return {
        "timestamp": timestamp,
        "product_id": str(product_id),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "price": price,
    }


class FeatureCalculator:
    """
    Reusable class for computing windowed features from tick data.
    
    This class maintains a rolling window of ticks per product_id and
    computes features on demand. Can be used in both streaming (Kafka)
    and batch (replay) contexts.
    """
    
    def __init__(self, window_size: int = DEFAULT_WINDOW_SIZE):
        """
        Initialize feature calculator.
        
        Args:
            window_size: Number of ticks to include in rolling window
        """
        self.window_size = window_size
        # Store ticks per product_id: {product_id: List[Dict]}
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
    
    def add_tick(self, tick: Dict[str, Any]) -> None:
        """Add a tick to the buffer for its product_id."""
        product_id = tick.get("product_id")
        if not product_id:
            return
        
        if product_id not in self._buffers:
            self._buffers[product_id] = []
        
        self._buffers[product_id].append(tick)
        
        # Keep only last window_size ticks
        if len(self._buffers[product_id]) > self.window_size:
            self._buffers[product_id] = self._buffers[product_id][-self.window_size:]
    
    def compute_features(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Compute features for a given product_id based on current buffer.
        
        Returns:
            Dict with keys: timestamp, product_id, midprice, midprice_return,
            rolling_vol, spread, trade_intensity
            Returns None if insufficient data
        """
        if product_id not in self._buffers:
            return None
        
        buffer = self._buffers[product_id]
        if len(buffer) < 2:  # Need at least 2 ticks for returns
            return None
        
        # Convert to DataFrame for easier computation
        df = pd.DataFrame(buffer)
        
        # Compute midprice
        df["midprice"] = df.apply(
            lambda row: (
                (row["best_bid"] + row["best_ask"]) / 2.0
                if row["best_bid"] is not None and row["best_ask"] is not None
                else row["price"]
            ),
            axis=1,
        )
        
        # Ensure midprice is numeric
        df["midprice"] = pd.to_numeric(df["midprice"], errors="coerce")
        
        # Compute percent change (midprice_return)
        df["midprice_return"] = df["midprice"].pct_change()
        
        # Rolling volatility: std dev of returns over window
        window = min(self.window_size, len(df))
        df["rolling_vol"] = df["midprice_return"].rolling(
            window=window, min_periods=2
        ).std()
        
        # Spread: best_ask - best_bid
        df["spread"] = df.apply(
            lambda row: (
                row["best_ask"] - row["best_bid"]
                if row["best_ask"] is not None and row["best_bid"] is not None
                else None
            ),
            axis=1,
        )
        
        # Trade intensity: count of messages in window (already in buffer)
        df["trade_intensity"] = len(df)
        
        # Get latest row (most recent tick)
        latest = df.iloc[-1]
        
        # Build feature dict
        features = {
            "timestamp": latest["timestamp"].isoformat() if isinstance(latest["timestamp"], datetime) else str(latest["timestamp"]),
            "product_id": product_id,
            "midprice": to_float(latest["midprice"]),
            "midprice_return": to_float(latest["midprice_return"]),
            "rolling_vol": to_float(latest["rolling_vol"]),
            "spread": to_float(latest["spread"]),
            "trade_intensity": int(latest["trade_intensity"]),
        }
        
        return features
    
    def get_product_ids(self) -> List[str]:
        """Get list of product_ids currently in buffer."""
        return list(self._buffers.keys())
    
    def clear(self, product_id: Optional[str] = None) -> None:
        """Clear buffer for a product_id, or all if None."""
        if product_id:
            self._buffers.pop(product_id, None)
        else:
            self._buffers.clear()


class FeatureProcessor:
    """
    Main processor that consumes from Kafka, computes features, and publishes results.
    """
    
    def __init__(
        self,
        bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP,
        input_topic: str = DEFAULT_INPUT_TOPIC,
        output_topic: str = DEFAULT_OUTPUT_TOPIC,
        parquet_path: Path = Path(DEFAULT_PARQUET_PATH),
        config: FeatureConfig = FeatureConfig(),
    ):
        self.bootstrap_servers = bootstrap_servers
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.parquet_path = parquet_path
        self.config = config
        
        self._stop = False
        
        # Feature calculator (reusable component)
        self._calculator = FeatureCalculator(window_size=config.window_size)
        
        # Kafka producer for features
        self._producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            linger_ms=50,
            retries=5,
            acks=1,  # Integer, not string
        )
        
        # Kafka consumer for raw ticks
        self._consumer = KafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda v: v,  # Keep as bytes for parsing
        )
        
        # Parquet writer setup
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        self._parquet_buffer: List[Dict[str, Any]] = []
    
    def stop(self) -> None:
        """Gracefully shutdown processor."""
        self._stop = True
        try:
            self._consumer.close()
        except Exception:
            pass
        try:
            self._producer.flush(5)
            self._producer.close(5)
        except Exception:
            pass
        try:
            self._flush_parquet(force=True)
        except Exception:
            pass
    
    def _publish_features(self, features: Dict[str, Any]) -> None:
        """Publish features to Kafka topic."""
        try:
            self._producer.send(self.output_topic, features)
        except Exception as e:
            logger.error(f"Failed to publish features to Kafka: {e}")
    
    def _buffer_parquet(self, features: Dict[str, Any]) -> None:
        """Add features to Parquet buffer and flush if batch size reached."""
        self._parquet_buffer.append(features)
        if len(self._parquet_buffer) >= self.config.parquet_batch_size:
            self._flush_parquet(force=False)
    
    def _flush_parquet(self, force: bool = False) -> None:
        """Flush Parquet buffer to disk."""
        if not self._parquet_buffer:
            return
        if not force and len(self._parquet_buffer) < self.config.parquet_batch_size:
            return
        
        try:
            new_df = pd.DataFrame(self._parquet_buffer)
            # Ensure timestamp is string for Parquet
            if "timestamp" in new_df.columns:
                new_df["timestamp"] = new_df["timestamp"].astype(str)
            
            # For append mode: read existing data, combine, write all
            if self.parquet_path.exists():
                try:
                    existing_df = pd.read_parquet(self.parquet_path)
                    # Combine with new data
                    df = pd.concat([existing_df, new_df], ignore_index=True)
                    logger.debug(f"Appending to existing Parquet: {len(existing_df)} + {len(new_df)} = {len(df)} rows")
                except Exception as e:
                    logger.warning(f"Could not read existing Parquet, creating new: {e}")
                    df = new_df
            else:
                df = new_df
            
            # Write complete dataset (always overwrites for safety)
            table = pa.Table.from_pandas(df, preserve_index=False)
            pq.write_table(
                table,
                self.parquet_path,
                use_dictionary=True,
                compression='snappy'
            )
            self._parquet_buffer.clear()
            logger.info(f"Flushed {len(df)} total features to Parquet (added {len(new_df)} new)")
        except Exception as e:
            logger.error(f"Failed to flush Parquet: {e}", exc_info=True)
    
    def run_forever(self) -> None:
        """Main processing loop."""
        logger.info(
            f"Starting feature processor: input={self.input_topic}, "
            f"output={self.output_topic}, window={self.config.window_size}"
        )
        
        msg_count = 0
        feature_count = 0
        
        while not self._stop:
            try:
                for msg in self._consumer:
                    if self._stop:
                        break
                    
                    # Parse tick message
                    tick = parse_tick_message(msg.value)
                    if tick is None:
                        continue
                    
                    msg_count += 1
                    if msg_count % 100 == 0:
                        logger.info(f"Processed {msg_count} messages, computed {feature_count} features")
                    
                    # Add tick to calculator
                    self._calculator.add_tick(tick)
                    
                    # Compute features
                    product_id = tick["product_id"]
                    features = self._calculator.compute_features(product_id)
                    
                    if features is None:
                        continue  # Not enough data yet
                    
                    feature_count += 1
                    
                    # Publish to Kafka
                    self._publish_features(features)
                    
                    # Buffer for Parquet
                    self._buffer_parquet(features)
                    
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                continue
        
        logger.info(f"Shutting down. Processed {msg_count} messages, computed {feature_count} features")
        self.stop()


def main() -> None:
    """Main entry point."""
    # Configuration from environment
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA_BOOTSTRAP)
    input_topic = os.getenv("KAFKA_INPUT_TOPIC", DEFAULT_INPUT_TOPIC)
    output_topic = os.getenv("KAFKA_OUTPUT_TOPIC", DEFAULT_OUTPUT_TOPIC)
    parquet_path = Path(os.getenv("FEATURES_PARQUET_PATH", DEFAULT_PARQUET_PATH))
    window_size = int(os.getenv("FEATURE_WINDOW_SIZE", str(DEFAULT_WINDOW_SIZE)))
    batch_size = int(os.getenv("PARQUET_BATCH_SIZE", str(DEFAULT_PARQUET_BATCH_SIZE)))
    
    config = FeatureConfig(
        window_size=window_size,
        parquet_batch_size=batch_size,
    )
    
    processor = FeatureProcessor(
        bootstrap_servers=bootstrap,
        input_topic=input_topic,
        output_topic=output_topic,
        parquet_path=parquet_path,
        config=config,
    )
    
    def handle_sig(_sig, _frm):
        logger.info("Signal received, shutting down...")
        processor.stop()
        raise SystemExit(0)
    
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    
    try:
        processor.run_forever()
    except SystemExit:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        processor.stop()
        raise


if __name__ == "__main__":
    main()
