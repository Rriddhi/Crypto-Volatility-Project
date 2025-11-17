#!/usr/bin/env python3
import os
import json
import time
import random
import signal
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from kafka import KafkaProducer
from websocket import WebSocketApp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_repo_root() -> Path:
    # scripts/ is one level below repo root
    return Path(__file__).resolve().parents[1]


class TickerIngestor:
    def __init__(
        self,
        ws_url: str,
        product_ids: List[str],
        kafka_bootstrap: str,
        kafka_topic: str,
        data_dir: Path,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
    ) -> None:
        self.ws_url = ws_url
        self.product_ids = product_ids
        self.kafka_bootstrap = kafka_bootstrap
        self.kafka_topic = kafka_topic
        self.data_dir = data_dir
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self._stop = False
        self._ws: Optional[WebSocketApp] = None
        self._producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap,
            value_serializer=lambda v: v.encode("utf-8"),
            linger_ms=50,
            retries=5,
            acks=1,  # Integer, not string: 0=no ack, 1=leader only, -1 or "all"=all replicas
        )

        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _ndjson_path_for_now(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.data_dir / f"{day}.ndjson"

    def _append_raw(self, raw: str) -> None:
        path = self._ndjson_path_for_now()
        with path.open("a", encoding="utf-8") as f:
            f.write(raw)
            if not raw.endswith("\n"):
                f.write("\n")

    def _on_open(self, ws: WebSocketApp) -> None:
        logger.info(f"WebSocket connected to {self.ws_url}")
        # Coinbase Advanced Trade WebSocket subscription format
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": self.product_ids,
            "channel": "ticker",
        }
        subscribe_json = json.dumps(subscribe_msg)
        logger.info(f"Sending subscription: {subscribe_json}")
        ws.send(subscribe_json)

    def _on_message(self, _ws: WebSocketApp, message: str) -> None:
        if isinstance(message, (bytes, bytearray)):
            try:
                message = message.decode("utf-8")
            except Exception as e:
                logger.warning(f"Failed to decode message: {e}")
                return

        # Log subscription confirmations and errors
        try:
            msg_obj = json.loads(message)
            if msg_obj.get("type") == "subscriptions":
                logger.info(f"Subscription confirmed: {message}")
                return
            elif msg_obj.get("type") == "error":
                logger.error(f"WebSocket error: {message}")
                return
        except Exception:
            pass  # Not JSON or not a control message, continue processing

        # Append to NDJSON
        self._append_raw(message)

        # Forward to Kafka as-is (raw JSON string)
        try:
            future = self._producer.send(self.kafka_topic, message)
            # Log first few messages for debugging
            if hasattr(self, "_msg_count"):
                self._msg_count += 1
            else:
                self._msg_count = 1
            if self._msg_count <= 5:
                logger.info(f"Sent message #{self._msg_count} to Kafka topic '{self.kafka_topic}'")
        except Exception as e:
            logger.error(f"Failed to send to Kafka: {e}")

    def _on_error(self, _ws: WebSocketApp, error: Exception) -> None:
        logger.error(f"WebSocket error: {error}")
        # Errors cause the run loop to exit; reconnect logic is outside

    def _on_close(self, _ws: WebSocketApp, status_code, msg) -> None:
        logger.warning(f"WebSocket closed: status={status_code}, msg={msg}")
        # No action; reconnect handled by outer loop

    def stop(self) -> None:
        self._stop = True
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        try:
            self._producer.flush(5)
            self._producer.close(5)
        except Exception:
            pass

    def run_forever(self) -> None:
        retries = 0
        logger.info(f"Starting ingestor: WS={self.ws_url}, products={self.product_ids}, Kafka={self.kafka_bootstrap}, topic={self.kafka_topic}")
        while not self._stop:
            self._ws = WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            try:
                # sslopt avoid cert issues; macOS Docker Desktop friendly
                logger.info(f"Connecting to WebSocket (attempt {retries + 1})...")
                self._ws.run_forever(sslopt={"cert_reqs": 0}, ping_interval=20, ping_timeout=10)
                # If closed without stop signal, treat as error to trigger backoff
                if self._stop:
                    logger.info("Stop signal received, exiting")
                    break
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self.stop()
                break
            except Exception as e:
                logger.error(f"Exception in WebSocket run loop: {e}")
                # fall through to backoff
                pass

            if self._stop:
                break

            # Exponential backoff with jitter
            retries += 1
            sleep_s = min(self.backoff_max, self.backoff_base * (2 ** (retries - 1)))
            sleep_s = sleep_s * (0.5 + random.random())  # jitter 0.5x..1.5x
            logger.info(f"Reconnecting in {sleep_s:.2f} seconds...")
            time.sleep(sleep_s)


def main() -> None:
    repo_root = get_repo_root()
    data_raw_dir = repo_root / "data" / "raw"

    ws_url = os.getenv("WS_URL", "wss://advanced-trade-ws.coinbase.com")
    product_ids_env = os.getenv("PRODUCT_IDS", "BTC-USD")
    product_ids = [p.strip() for p in product_ids_env.split(",") if p.strip()]

    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic = os.getenv("KAFKA_TOPIC", "ticks.raw")
    
    logger.info(f"Configuration: WS_URL={ws_url}, PRODUCT_IDS={product_ids}, KAFKA={kafka_bootstrap}, TOPIC={kafka_topic}")

    ingestor = TickerIngestor(
        ws_url=ws_url,
        product_ids=product_ids,
        kafka_bootstrap=kafka_bootstrap,
        kafka_topic=kafka_topic,
        data_dir=data_raw_dir,
        backoff_base=float(os.getenv("BACKOFF_BASE", "1.0")),
        backoff_max=float(os.getenv("BACKOFF_MAX", "60.0")),
    )

    def handle_sigint(_sig, _frame):
        ingestor.stop()

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)
    ingestor.run_forever()


if __name__ == "__main__":
    main()


