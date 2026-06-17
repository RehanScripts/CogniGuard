"""CogniGuard Flink Feature Engine (Architecture §3.2 / §6).

Consumes the 4 input Kafka topics and applies online-feature updates to the Redis
feature store + mirrors raw events to S3. The transformation logic lives in `sinks.py`
(unit-tested); this module is the thin PyFlink wrapper.

The Redis/S3 side effect runs inside a per-source map (parallelism 1 → records are
serialized, so the per-user read-modify-write updates stay consistent without a keyBy
shuffle).

Submit:  flink run -d -py /jobs/feature_engine.py
"""

import json
import logging
import os

from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream import RuntimeExecutionMode, StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.functions import MapFunction

logging.basicConfig(level="INFO")

INPUT_TOPICS = ["login_events", "behavior_events", "transaction_events", "device_events"]
KEY_FIELD = {
    "login_events": "user_id",
    "behavior_events": "user_id",
    "transaction_events": "user_id",
    "device_events": "device_id",
}
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")


class FeatureMapper(MapFunction):
    """Applies one topic's Redis feature updates + S3 mirror per record."""

    def __init__(self, topic: str):
        self.topic = topic

    def open(self, runtime_context):
        import boto3
        import redis as redislib
        from botocore.client import Config

        import sinks  # shipped via add_python_file

        self._sinks = sinks
        self.redis = redislib.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
        )
        self.s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT", "http://minio:9000"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self.bucket = os.environ.get("S3_BUCKET", "cogniguard")

    def map(self, s: str) -> str:
        payload = json.loads(s)
        key = str(payload.get(KEY_FIELD[self.topic], ""))
        self._sinks.process_record(self.redis, self.s3, self.bucket, self.topic, key, payload)
        return f"{self.topic}|{key}"


def build_job(env: StreamExecutionEnvironment) -> None:
    for topic in INPUT_TOPICS:
        source = (
            KafkaSource.builder()
            .set_bootstrap_servers(BOOTSTRAP)
            .set_topics(topic)
            .set_group_id("cogniguard-feature-engine")
            .set_starting_offsets(KafkaOffsetsInitializer.earliest())
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )
        (
            env.from_source(source, WatermarkStrategy.no_watermarks(), f"kafka-{topic}")
            .map(FeatureMapper(topic), output_type=Types.STRING())
            .name(f"feature-sink-{topic}")
            .print()
        )


def main() -> None:
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(1)
    for mod in ("/jobs/sinks.py", "/jobs/windows.py"):
        if os.path.exists(mod):
            env.add_python_file(mod)
    build_job(env)
    env.execute("cogniguard-feature-engine")


if __name__ == "__main__":
    main()
