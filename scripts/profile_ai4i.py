"""Extract the statistical parameters the simulator will generate from."""

import json
from pathlib import Path

import pandas as pd

SRC = Path("ai4i2020.csv")
OUT = Path("src/factorypulse/simulator/ai4i_profile.json")

COLS = {
    "Air temperature [K]": "air_temp_k",
    "Process temperature [K]": "process_temp_k",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
}


def main() -> None:
    """Profile AI4I and persist parameters used by the simulator."""
    df = pd.read_csv(SRC, encoding="utf-8-sig")
    df = df.rename(columns={**COLS, "Type": "machine_type", "Machine failure": "machine_failure"})

    print("=== Shape ===")
    print(df.shape)

    print("\n=== Machine type mix ===")
    mix = df["machine_type"].value_counts(normalize=True).round(4)
    print(mix)

    print("\n=== Sensor distributions ===")
    print(df[list(COLS.values())].describe().T.round(3))

    print("\n=== Failure mode counts ===")
    for column in ["machine_failure", "TWF", "HDF", "PWF", "OSF", "RNF"]:
        print(f"  {column:16s} {df[column].sum():5d}   ({df[column].mean() * 100:.2f}%)")

    print("\n=== Correlation: rpm vs torque ===")
    correlation = df["rotational_speed_rpm"].corr(df["torque_nm"])
    print(f"  r = {correlation:.4f}")

    print("\n=== Derived: temperature difference ===")
    df["temp_diff"] = df["process_temp_k"] - df["air_temp_k"]
    print(df["temp_diff"].describe().round(3))

    profile = {
        "type_mix": mix.to_dict(),
        "air_temp_k": {"mean": float(df.air_temp_k.mean()), "std": float(df.air_temp_k.std())},
        "temp_diff_k": {"mean": float(df.temp_diff.mean()), "std": float(df.temp_diff.std())},
        "rotational_speed_rpm": {
            "mean": float(df.rotational_speed_rpm.mean()),
            "std": float(df.rotational_speed_rpm.std()),
        },
        "torque_nm": {"mean": float(df.torque_nm.mean()), "std": float(df.torque_nm.std())},
        "rpm_torque_corr": float(correlation),
        "failure_rates": {
            column: float(df[column].mean())
            for column in ["machine_failure", "TWF", "HDF", "PWF", "OSF", "RNF"]
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(profile, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
