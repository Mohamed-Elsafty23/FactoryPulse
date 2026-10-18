import pytest
from pyspark.sql import functions as F


@pytest.mark.slow
def test_spark_session_starts(spark):
    assert spark.range(10).count() == 10


@pytest.mark.slow
def test_delta_roundtrip(spark, tmp_delta):
    df = spark.range(100).withColumn("x", F.col("id") * 2)
    df.write.format("delta").mode("overwrite").save(tmp_delta)

    back = spark.read.format("delta").load(tmp_delta)
    assert back.count() == 100
    assert back.filter("x = 198").count() == 1
