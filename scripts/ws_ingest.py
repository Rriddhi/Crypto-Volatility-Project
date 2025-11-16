#!/usr/bin/env python3
import os
import json
import time
import random
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from kafka import KafkaProducer
from websocket import WebSocketApp


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
            acks="1",
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
        subscribe_msg = {
            "type": "subscribe",
            "channel": "ticker",
            "product_ids": self.product_ids,
        }
        ws.send(json.dumps(subscribe_msg))

    def _on_message(self, _ws: WebSocketApp, message: str) -> None:
        if isinstance(message, (bytes, bytearray)):
            try:
                message = message.decode("utf-8")
            except Exception:
                return

        # Append to NDJSON
        self._append_raw(message)

        # Forward to Kafka as-is (raw JSON string)
        self._producer.send(self.kafka_topic, message)

    def _on_error(self, _ws: WebSocketApp, error: Exception) -> None:
        # Errors cause the run loop to exit; reconnect logic is outside
        pass

    def _on_close(self, _ws: WebSocketApp, _status_code, _msg) -> None:
        # No action; reconnect handled by outer loop
        pass

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
                self._ws.run_forever(sslopt={"cert_reqs": 0}, ping_interval=20, ping_timeout=10)
                # If closed without stop signal, treat as error to trigger backoff
                if self._stop:
                    break
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception:
                # fall through to backoff
                pass

            # Exponential backoff with jitter
            retries += 1
            sleep_s = min(self.backoff_max, self.backoff_base * (2 ** (retries - 1)))
            sleep_s = sleep_s * (0.5 + random.random())  # jitter 0.5x..1.5x
            time.sleep(sleep_s)


def main() -> None:
    repo_root = get_repo_root()
    data_raw_dir = repo_root / "data" / "raw"

    ws_url = os.getenv("WS_URL", "wss://advanced-trade-ws.coinbase.com")
    product_ids_env = os.getenv("PRODUCT_IDS", "BTC-USD")
    product_ids = [p.strip() for p in product_ids_env.split(",") if p.strip()]

    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic = os.getenv("KAFKA_TOPIC", "ticks.raw")

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


