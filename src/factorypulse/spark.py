"""Spark session construction. The only module that knows about JARs."""

from __future__ import annotations

import contextlib
import os
import sys

from delta import configure_spark_with_delta_pip
from pyspark.sql import DataFrame, SparkSession
from pyspark.storagelevel import StorageLevel

from factorypulse.config import Settings, settings

_S3_PACKAGES = [
    "org.apache.hadoop:hadoop-aws:3.3.4",
    "com.amazonaws:aws-java-sdk-bundle:1.12.262",
]
_JDBC_PACKAGES = [
    "org.postgresql:postgresql:42.7.3",
]


def get_spark(
    app_name: str = "factorypulse",
    cfg: Settings | None = None,
    shuffle_partitions: int | None = None,
) -> SparkSession:
    """Build or fetch a SparkSession configured for the current environment."""
    cfg = cfg or settings

    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
    )

    if shuffle_partitions is not None:
        builder = builder.config("spark.sql.shuffle.partitions", str(shuffle_partitions))

    extra_packages: list[str] = []

    if cfg.is_local:
        # Conda/base environments can expose a different ``python3`` than the
        # interpreter running this process. Spark workers must use the exact
        # same minor version as the driver.
        os.environ["PYSPARK_PYTHON"] = sys.executable
        os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
        extra_packages = _S3_PACKAGES + _JDBC_PACKAGES
        builder = (
            # Keep local development responsive on an 8-core/16-GB laptop.
            builder.master("local[2]")
            .config("spark.pyspark.python", sys.executable)
            .config("spark.pyspark.driver.python", sys.executable)
            .config("spark.sql.shuffle.partitions", str(shuffle_partitions or 8))
            .config("spark.driver.memory", "2g")
            .config("spark.hadoop.fs.s3a.endpoint", cfg.minio_endpoint)
            .config("spark.hadoop.fs.s3a.access.key", cfg.minio_access_key)
            .config("spark.hadoop.fs.s3a.secret.key", cfg.minio_secret_key)
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
            .config(
                "spark.hadoop.fs.s3a.impl",
                "org.apache.hadoop.fs.s3a.S3AFileSystem",
            )
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            )
            .config("spark.hadoop.fs.s3a.fast.upload", "true")
            .config("spark.hadoop.fs.s3a.fast.upload.buffer", "disk")
        )

    spark = configure_spark_with_delta_pip(builder, extra_packages=extra_packages).getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    return spark


def maybe_persist(df: DataFrame, level: StorageLevel) -> DataFrame:
    """Persist ``df`` where the runtime allows it, else return it unchanged.

    Databricks serverless compute rejects PERSIST/CACHE outright
    (NOT_SUPPORTED_WITH_SERVERLESS). Persisting is only ever a performance
    optimisation here — it avoids evaluating an expression tree twice — so
    degrading to recomputation keeps results identical and the job running.
    """
    try:
        return df.persist(level)
    except Exception:
        return df


def maybe_unpersist(df: DataFrame) -> None:
    """Release a persisted DataFrame, tolerating runtimes that never cached it."""
    with contextlib.suppress(Exception):
        df.unpersist()
