#!/usr/bin/env python3
import json
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from kafka import KafkaConsumer, KafkaProducer


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
        return float(value)
    except Exception:
        return None


@dataclass
class FeatureConfig:
    window_size: int = 50
    df_max_rows: int = 5000
    parquet_batch_size: int = 100


class FeatureProcessor:
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        input_topic: str = "ticks.raw",
        output_topic: str = "ticks.features",
        parquet_path: Path = Path("data/processed/features.parquet"),
        config: FeatureConfig = FeatureConfig(),
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.parquet_path = parquet_path
        self.config = config

        self._stop = False
        self._df = pd.DataFrame(
            columns=["ts", "bid", "ask", "price", "midprice"]
        )
        self._producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            linger_ms=20,
            retries=5,
            acks="1",
        )
        self._consumer = KafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda v: v,  # raw bytes, we'll parse
        )

        # Prepare parquet writer (append mode). If file exists, reuse schema.
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        self._pq_writer: Optional[pq.ParquetWriter] = None
        self._pq_schema: Optional[pa.Schema] = None
        self._parquet_buffer: List[Dict[str, Any]] = []
        if self.parquet_path.exists():
            try:
                existing = pq.ParquetFile(self.parquet_path)
                self._pq_schema = existing.schema_arrow
                self._pq_writer = pq.ParquetWriter(self.parquet_path, self._pq_schema, use_dictionary=True)
            except Exception:
                # If corrupt or unreadable, we will re-create on first write
                self._pq_writer = None
                self._pq_schema = None

    def stop(self) -> None:
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
            if self._pq_writer is not None:
                self._pq_writer.close()
        except Exception:
            pass

    def _parse_tick(self, payload: bytes) -> Optional[Dict[str, Any]]:
        try:
            text = payload.decode("utf-8")
            obj = json.loads(text)
        except Exception:
            return None

        # Coinbase Advanced Trade "ticker" tends to include one or more of:
        # "best_bid", "best_ask", "price", with a timestamp field.
        # We'll be permissive and try several keys.
        bid = _to_float(obj.get("best_bid") or obj.get("bid"))
        ask = _to_float(obj.get("best_ask") or obj.get("ask"))
        price = _to_float(obj.get("price") or obj.get("last") or obj.get("trade_price"))

        # Timestamp extraction
        ts = (
            obj.get("time")
            or obj.get("timestamp")
            or obj.get("ts")
            or obj.get("event_time")
        )
        if isinstance(ts, (int, float)):
            try:
                ts = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
            except Exception:
                ts = None
        if not isinstance(ts, str) or not ts:
            ts = _now_iso()

        if bid is None and ask is None and price is None:
            return None
        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        elif price is not None:
            mid = price

        return {"ts": ts, "bid": bid, "ask": ask, "price": price, "midprice": mid}

    def _append_df(self, row: Dict[str, Any]) -> None:
        self._df = pd.concat([self._df, pd.DataFrame([row])], ignore_index=True)
        # Keep only last N rows to bound memory
        if len(self._df) > self.config.df_max_rows:
            self._df = self._df.tail(self.config.df_max_rows).reset_index(drop=True)

    def _compute_latest_features(self) -> Optional[Dict[str, Any]]:
        if self._df.empty:
            return None
        w = max(2, self.config.window_size)
        # We only need last w rows for rolling metrics
        dfw = self._df.tail(w).copy()
        # Ensure midprice exists
        dfw["midprice"] = pd.to_numeric(dfw["midprice"], errors="coerce")
        # Returns as log return or simple pct? Use simple pct change
        dfw["return"] = dfw["midprice"].pct_change()
        # Rolling volatility as std of returns over window (not annualized)
        dfw["rolling_vol"] = dfw["return"].rolling(window=min(w, len(dfw)), min_periods=2).std()
        # Spread
        dfw["spread"] = pd.to_numeric(dfw["ask"], errors="coerce") - pd.to_numeric(dfw["bid"], errors="coerce")
        # Latest row with features
        latest = dfw.iloc[-1]
        features = {
            "ts": latest.get("ts"),
            "midprice": _to_float(latest.get("midprice")),
            "return": _to_float(latest.get("return")),
            "rolling_vol": _to_float(latest.get("rolling_vol")),
            "spread": _to_float(latest.get("spread")),
        }
        return features

    def _publish_features(self, features: Dict[str, Any]) -> None:
        self._producer.send(self.output_topic, features)

    def _buffer_parquet(self, features: Dict[str, Any]) -> None:
        self._parquet_buffer.append(features)
        if len(self._parquet_buffer) >= self.config.parquet_batch_size:
            self._flush_parquet(force=False)

    def _flush_parquet(self, force: bool) -> None:
        if not self._parquet_buffer:
            return
        if not force and len(self._parquet_buffer) < self.config.parquet_batch_size:
            return
        df = pd.DataFrame(self._parquet_buffer)
        table = pa.Table.from_pandas(df, preserve_index=False)
        if self._pq_writer is None:
            # Create or overwrite file with new schema
            self._pq_schema = table.schema
            self._pq_writer = pq.ParquetWriter(self.parquet_path, self._pq_schema, use_dictionary=True)
        self._pq_writer.write_table(table)
        self._parquet_buffer.clear()

    def run_forever(self) -> None:
        while not self._stop:
            try:
                for msg in self._consumer:
                    if self._stop:
                        break
                    parsed = self._parse_tick(msg.value)
                    if not parsed:
                        continue
                    self._append_df(parsed)
                    features = self._compute_latest_features()
                    if features is None:
                        continue
                    self._publish_features(features)
                    self._buffer_parquet(features)
            except KeyboardInterrupt:
                break
            except Exception:
                # On unexpected consumer error, continue loop
                continue
        # Shutdown/flush
        self.stop()


def main() -> None:
    # Config from env for flexibility
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    in_topic = os.getenv("KAFKA_INPUT_TOPIC", "ticks.raw")
    out_topic = os.getenv("KAFKA_OUTPUT_TOPIC", "ticks.features")
    parquet_path = Path(os.getenv("FEATURES_PARQUET_PATH", "data/processed/features.parquet"))
    window = int(os.getenv("FEATURE_WINDOW", "50"))

    processor = FeatureProcessor(
        bootstrap_servers=bootstrap,
        input_topic=in_topic,
        output_topic=out_topic,
        parquet_path=parquet_path,
        config=FeatureConfig(window_size=window),
    )

    def handle_sig(_sig, _frm):
        processor.stop()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    processor.run_forever()


if __name__ == "__main__":
    main()


