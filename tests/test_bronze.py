import pytest
from pyspark.sql import functions as F

from factorypulse.pipeline.bronze import add_lineage
from factorypulse.utils.run_context import RunContext


@pytest.mark.slow
def test_lineage_columns_are_added(spark):
    context = RunContext(pipeline="test")
    source = spark.range(5).withColumn("x", F.lit("a"))
    output = add_lineage(source, context, "unit_test")

    for column in ("_ingested_at", "_source_system", "_source_file", "_batch_id"):
        assert column in output.columns
    assert output.select("_batch_id").distinct().first()[0] == context.run_id
    assert output.select("_source_system").distinct().first()[0] == "unit_test"


@pytest.mark.slow
def test_lineage_does_not_drop_or_alter_source_columns(spark):
    context = RunContext(pipeline="test")
    source = spark.range(5).withColumn("x", F.lit("a"))
    output = add_lineage(source, context, "unit_test")

    assert set(source.columns).issubset(output.columns)
    assert output.select("id", "x").exceptAll(source.select("id", "x")).count() == 0


@pytest.mark.slow
def test_bronze_write_is_idempotent(spark, tmp_delta):
    source = (
        spark.range(100)
        .withColumn("event_date", F.lit("2025-10-01").cast("date"))
        .withColumn("v", F.col("id") * 2)
    )
    for _ in range(2):
        source.write.format("delta").mode("overwrite").partitionBy("event_date").save(tmp_delta)

    assert spark.read.format("delta").load(tmp_delta).count() == 100
