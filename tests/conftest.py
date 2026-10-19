"""Shared pytest fixtures."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from pyspark.sql import SparkSession

from factorypulse.config import Settings
from factorypulse.spark import get_spark


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    """One Spark session shared by the whole test run."""
    session = get_spark("factorypulse-tests", shuffle_partitions=2)
    yield session
    session.stop()


@pytest.fixture
def tmp_delta(tmp_path) -> str:
    """A throwaway local Delta path, cleaned up automatically by pytest."""
    return f"file://{tmp_path}/delta"


@pytest.fixture(scope="session")
def mini_cfg(tmp_path_factory) -> Settings:
    """Use an isolated local filesystem lake for end-to-end quality tests."""
    root = tmp_path_factory.mktemp("lake")

    class MiniSettings(Settings):
        def landing_path(self, dataset: str) -> str:
            return f"file://{root}/landing/{dataset}"

        def bronze_path(self, table: str) -> str:
            return f"file://{root}/bronze/{table}"

        def silver_path(self, table: str) -> str:
            return f"file://{root}/silver/{table}"

        def gold_path(self, table: str) -> str:
            return f"file://{root}/gold/{table}"

        def quarantine_path(self, table: str) -> str:
            return f"file://{root}/quarantine/{table}"

        @property
        def ops_path(self) -> str:
            return f"file://{root}/ops/pipeline_runs"

    return MiniSettings()


@pytest.fixture(scope="session")
def mini_lake(spark, mini_cfg):
    """Build one complete miniature Bronze-to-Gold lake per test session."""
    from pyspark.sql import functions as F

    from factorypulse.pipeline.bronze import add_lineage
    from factorypulse.pipeline.dimensions import build_dim_failure_type, build_dim_shift
    from factorypulse.pipeline.gold import build_fact_downtime, build_fact_machine_event
    from factorypulse.pipeline.scd2 import initialise_dim_machine, merge_dim_machine
    from factorypulse.pipeline.silver import build_silver_telemetry
    from factorypulse.simulator.defects import inject_defects
    from factorypulse.simulator.generate import generate_telemetry
    from factorypulse.simulator.roster import ROSTER
    from factorypulse.utils.run_context import RunContext

    context = RunContext(pipeline="test")
    start = datetime(2025, 10, 1)
    machines = spark.createDataFrame(
        [
            (
                machine.machine_id,
                machine.machine_name,
                machine.plant_id,
                machine.line_id,
                machine.model,
                machine.machine_type,
                machine.criticality,
                float(machine.ideal_cycle_seconds),
                True,
            )
            for machine in ROSTER
        ],
        "machine_id STRING, machine_name STRING, plant_id STRING, line_id STRING, "
        "model STRING, machine_type STRING, criticality STRING, "
        "ideal_cycle_seconds DOUBLE, is_active BOOLEAN",
    ).withColumn("installed_date", F.lit("2020-01-01"))
    machines.write.format("delta").mode("overwrite").save(mini_cfg.bronze_path("machines"))

    raw = inject_defects(generate_telemetry(spark, 40_000, start), rate=0.02)
    (
        add_lineage(raw, context, "test")
        .write.format("delta")
        .mode("overwrite")
        .partitionBy("event_date")
        .option("mergeSchema", "true")
        .save(mini_cfg.bronze_path("telemetry"))
    )
    build_silver_telemetry(spark, context, mini_cfg)

    initialise_dim_machine(spark, machines, start, mini_cfg)
    changed = machines.replace("LN-1", "LN-4", subset=["line_id"])
    merge_dim_machine(spark, changed, datetime(2025, 10, 15), mini_cfg)

    build_dim_shift(spark).write.format("delta").mode("overwrite").save(
        mini_cfg.gold_path("dim_shift")
    )
    build_dim_failure_type(spark).write.format("delta").mode("overwrite").save(
        mini_cfg.gold_path("dim_failure_type")
    )
    spark.createDataFrame(
        [
            (1, "PL-INGOL", "Ingolstadt", "DE", "Europe/Berlin"),
            (2, "PL-BRNO", "Brno", "CZ", "Europe/Prague"),
        ],
        "plant_sk LONG, plant_id STRING, plant_name STRING, country STRING, timezone STRING",
    ).write.format("delta").mode("overwrite").save(mini_cfg.gold_path("dim_plant"))

    build_fact_machine_event(spark, context, mini_cfg)
    build_fact_downtime(spark, context, mini_cfg)
    return mini_cfg


@pytest.fixture
def gold(spark, mini_lake):
    """Read a table from the miniature Gold layer."""

    def _read(table: str):
        return spark.read.format("delta").load(mini_lake.gold_path(table))

    return _read


@pytest.fixture
def silver(spark, mini_lake):
    """Read a table from the miniature Silver layer."""

    def _read(table: str):
        return spark.read.format("delta").load(mini_lake.silver_path(table))

    return _read
