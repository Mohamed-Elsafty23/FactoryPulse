"""Gold dimensions: date, shift, plant, and failure type."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from factorypulse.config import Settings, settings
from factorypulse.simulator.roster import FAILURE_TYPES, SHIFTS

MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
DAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def build_dim_date(spark: SparkSession, start: str, end: str) -> DataFrame:
    """Build one contiguous row per calendar day, inclusive of both bounds."""
    df = spark.range(1).select(
        F.explode(
            F.sequence(F.to_date(F.lit(start)), F.to_date(F.lit(end)), F.expr("INTERVAL 1 DAY"))
        ).alias("date")
    )
    iso_day = ((F.dayofweek("date") + 5) % 7) + 1
    return (
        df.withColumn("date_sk", F.date_format("date", "yyyyMMdd").cast("int"))
        .withColumn("year", F.year("date"))
        .withColumn("quarter", F.quarter("date"))
        .withColumn("month", F.month("date"))
        .withColumn("day", F.dayofmonth("date"))
        .withColumn("day_of_year", F.dayofyear("date"))
        .withColumn("week_of_year", F.weekofyear("date"))
        .withColumn("day_of_week", iso_day)
        .withColumn("day_name_de", F.element_at(F.array(*[F.lit(d) for d in DAYS_DE]), iso_day))
        .withColumn(
            "month_name_de", F.element_at(F.array(*[F.lit(m) for m in MONTHS_DE]), F.month("date"))
        )
        .withColumn("is_weekend", F.col("day_of_week") >= 6)
        .withColumn("year_month", F.date_format("date", "yyyy-MM"))
        .withColumn("first_day_of_month", F.trunc("date", "month"))
        .select(
            "date_sk",
            "date",
            "year",
            "quarter",
            "month",
            "day",
            "day_of_year",
            "week_of_year",
            "day_of_week",
            "day_name_de",
            "month_name_de",
            "is_weekend",
            "year_month",
            "first_day_of_month",
        )
    )


def build_dim_shift(spark: SparkSession) -> DataFrame:
    """Build the three-shift reference dimension."""
    return spark.createDataFrame(SHIFTS).select(
        "shift_sk", "shift_name", "shift_name_de", "start_hour", "end_hour"
    )


def build_dim_failure_type(spark: SparkSession) -> DataFrame:
    """Build the stable AI4I failure taxonomy dimension."""
    keys = {"NONE": 0, "TWF": 1, "HDF": 2, "PWF": 3, "OSF": 4, "RNF": 5}
    mapping = F.create_map(
        *[item for code, key in keys.items() for item in (F.lit(code), F.lit(key))]
    )
    return (
        spark.createDataFrame(FAILURE_TYPES)
        .withColumn("failure_type_sk", mapping[F.col("code")])
        .select("failure_type_sk", "code", "name_en", "name_de", "severity")
    )


def build_dim_plant(spark: SparkSession, cfg: Settings | None = None) -> DataFrame:
    """Build the plant dimension from the clean Silver reference table."""
    cfg = cfg or settings
    plants = spark.read.format("delta").load(cfg.silver_path("plants"))
    return plants.withColumn("plant_sk", F.abs(F.xxhash64("plant_id"))).select(
        "plant_sk", "plant_id", "plant_name", "country", "timezone"
    )
