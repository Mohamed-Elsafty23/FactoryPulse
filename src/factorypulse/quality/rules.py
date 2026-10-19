"""Central data-quality rules shared by Silver and its tests."""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

VALID_FAILURE_TYPES = ["NONE", "TWF", "HDF", "PWF", "OSF", "RNF"]
RANGES = {
    "air_temp_k": (270.0, 330.0),
    "process_temp_k": (270.0, 340.0),
    "torque_nm": (0.0, 100.0),
    "rotational_speed_rpm": (1000, 3000),
    "tool_wear_min": (0, 300),
}


def telemetry_reject_reason(valid_machine_ids: list[str]) -> Column:
    """Return the first failed telemetry rule, or null when the row is valid."""
    running = F.col("machine_status") == F.lit("RUNNING")
    return (
        F.when(F.col("event_id").isNull(), "missing_event_id")
        .when(F.col("machine_id").isNull(), "missing_machine_id")
        .when(F.col("event_time").isNull(), "missing_event_time")
        .when(~F.col("machine_id").isin(valid_machine_ids), "orphan_machine_id")
        .when(
            ~F.col("air_temp_k").between(*RANGES["air_temp_k"]),
            "air_temp_out_of_range",
        )
        .when(
            ~F.col("process_temp_k").between(*RANGES["process_temp_k"]),
            "process_temp_out_of_range",
        )
        .when(
            ~F.col("tool_wear_min").between(*RANGES["tool_wear_min"]),
            "tool_wear_out_of_range",
        )
        .when(
            running & ~F.col("torque_nm").between(*RANGES["torque_nm"]),
            "torque_out_of_range",
        )
        .when(
            running & ~F.col("rotational_speed_rpm").between(*RANGES["rotational_speed_rpm"]),
            "rpm_out_of_range",
        )
        .when(~F.col("failure_type").isin(VALID_FAILURE_TYPES), "invalid_failure_type")
        .when(F.col("repair_minutes") < 0, "negative_duration")
        .when(F.col("event_time") > F.current_timestamp(), "future_event_time")
        .otherwise(F.lit(None).cast("string"))
    )
