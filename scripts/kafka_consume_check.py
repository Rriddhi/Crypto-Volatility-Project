#!/usr/bin/env python3
import argparse
import json
import signal
import sys
from typing import Optional

from kafka import KafkaConsumer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quick Kafka consumer to read N messages from a topic and print them."
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Kafka topic to consume (e.g., ticks.raw)",
    )
    parser.add_argument(
        "--min",
        type=int,
        default=10,
        help="Minimum number of messages to read before exiting (default: 10)",
    )
    parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="Read from the beginning of the topic (default: read only new messages)",
    )
    return parser.parse_args()


class GracefulExit:
    def __init__(self) -> None:
        self.stop = False
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)

    def _handle(self, _sig, _frm) -> None:
        self.stop = True


def try_pretty_print(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except Exception:
        sys.stdout.buffer.write(payload + b"\n")
        return
    try:
        obj = json.loads(text)
        print(json.dumps(obj, indent=2, sort_keys=True))
    except Exception:
        print(text)


def main() -> None:
    args = parse_args()
    target_count = max(1, args.min)
    stopper = GracefulExit()

    offset_reset = "earliest" if args.from_beginning else "latest"
    consumer = KafkaConsumer(
        args.topic,
        bootstrap_servers="localhost:9092",
        auto_offset_reset=offset_reset,
        enable_auto_commit=True,
        consumer_timeout_ms=5000,  # timeout after 5 seconds if no messages
        value_deserializer=lambda v: v,  # keep as bytes; we handle printing
    )

    received = 0
    try:
        for msg in consumer:
            if stopper.stop:
                break
            try_pretty_print(msg.value)
            received += 1
            if received >= target_count:
                break
    finally:
        try:
            consumer.close()
        except Exception:
            pass

    print(f"Read {received} message(s) from topic '{args.topic}'.")


if __name__ == "__main__":
    main()


