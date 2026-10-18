"""Prove Spark + Delta + MinIO + Postgres all work. Run once, in Phase 02."""

import boto3
from pyspark.sql import functions as F

from factorypulse.config import settings
from factorypulse.spark import get_spark


def reset_smoke_prefix() -> None:
    """Remove artifacts from an earlier smoke run without touching other lake data."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
    )
    prefix = "_smoke/delta_test/"
    objects = client.list_objects_v2(Bucket=settings.storage_bucket, Prefix=prefix).get(
        "Contents", []
    )
    if objects:
        client.delete_objects(
            Bucket=settings.storage_bucket,
            Delete={"Objects": [{"Key": item["Key"]} for item in objects]},
        )


def main() -> None:
    reset_smoke_prefix()
    spark = get_spark("smoke-test")
    path = f"s3a://{settings.storage_bucket}/_smoke/delta_test"

    print("\n=== 1. Write a Delta table to MinIO ===")
    df = spark.range(0, 1000).withColumn("squared", F.col("id") ** 2)
    df.write.format("delta").mode("overwrite").save(path)
    print(f"   wrote 1000 rows -> {path}")

    print("\n=== 2. Read it back ===")
    back = spark.read.format("delta").load(path)
    assert back.count() == 1000, f"expected 1000, got {back.count()}"
    print(f"   read back {back.count()} rows")

    print("\n=== 3. ACID UPDATE (proves Delta, not plain Parquet) ===")
    from delta.tables import DeltaTable

    dt = DeltaTable.forPath(spark, path)
    dt.update(condition=F.col("id") < 10, set={"squared": F.lit(-1)})
    n = spark.read.format("delta").load(path).filter("squared = -1").count()
    assert n == 10, f"expected 10 updated rows, got {n}"
    print(f"   updated {n} rows in place")

    print("\n=== 4. Time travel (version 0 is unchanged) ===")
    v0 = spark.read.format("delta").option("versionAsOf", 0).load(path)
    assert v0.filter("squared = -1").count() == 0
    print("   version 0 still has the original values")

    print("\n=== 5. Transaction history ===")
    dt.history().select("version", "operation").show(truncate=False)

    print("\n=== 6. Postgres over JDBC ===")
    pg = (
        spark.read.format("jdbc")
        .option("url", settings.jdbc_url)
        .option("query", "SELECT 1 AS ok, version() AS v")
        .options(**settings.jdbc_properties)
        .load()
    )
    pg.show(truncate=False)

    print("\n=== 7. Keep the smoke table for inspection in MinIO ===")

    print("\nALL CHECKS PASSED — the local stack is ready.\n")
    spark.stop()


if __name__ == "__main__":
    main()
