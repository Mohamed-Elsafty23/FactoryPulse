"""Seed the operational source system with deterministic reference data."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import click
from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from factorypulse.config import settings
from factorypulse.simulator.roster import PLANTS, ROSTER

fake = Faker("de_DE")
PRODUCTS = ["GEAR-A1", "GEAR-B2", "SHAFT-C3", "HOUSING-D4", "FLANGE-E5"]
SCRAP_RATE = {"L": 0.045, "M": 0.022, "H": 0.009}


def _engine(target: str = "postgres"):
    """Connect to local Postgres or to Azure SQL from shell-only credentials."""
    if target == "azure":
        import os

        url = URL.create(
            "mssql+pymssql",
            username=os.environ.get("AZ_SQL_USER", "fpadmin"),
            password=os.environ["AZ_SQL_PASSWORD"],
            host=os.environ["AZ_SQL_SERVER"],
            database=os.environ.get("AZ_SQL_DB", "factorypulse"),
        )
        return create_engine(
            url,
            connect_args={"timeout": 120, "login_timeout": 120},
            pool_pre_ping=True,
        )

    return create_engine(
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def _insert_ignore(conn, table: str, key: str, statement: str, params: dict) -> None:
    """Execute an idempotent insert in either PostgreSQL or Azure SQL."""
    if conn.dialect.name == "mssql":
        sql = f"IF NOT EXISTS (SELECT 1 FROM {table} WHERE {key} = :_key) BEGIN {statement} END"  # noqa: S608
        conn.execute(text(sql), {**params, "_key": params[key]})
    else:
        conn.execute(text(f"{statement} ON CONFLICT ({key}) DO NOTHING"), params)  # noqa: S608


def seed_plants(conn, start: datetime) -> None:
    for plant in PLANTS:
        _insert_ignore(
            conn,
            "ops.plants",
            "plant_id",
            "INSERT INTO ops.plants "
            "(plant_id, plant_name, country, timezone, created_at, updated_at) "
            "VALUES (:plant_id, :plant_name, :country, :timezone, :start, :start)",
            {**plant, "start": start},
        )
    print(f"  plants            : {len(PLANTS)}")


def seed_machines(conn, start: datetime) -> None:
    for machine in ROSTER:
        params = {
            **machine.__dict__,
            "installed_date": (start - timedelta(days=random.randint(400, 2200))).date(),
            "start": start,
        }
        _insert_ignore(
            conn,
            "ops.machines",
            "machine_id",
            """
                INSERT INTO ops.machines (
                    machine_id, machine_name, plant_id, line_id, model,
                    machine_type, criticality, ideal_cycle_seconds, installed_date,
                    created_at, updated_at
                ) VALUES (
                    :machine_id, :machine_name, :plant_id, :line_id, :model,
                    :machine_type, :criticality, :ideal_cycle_seconds, :installed_date,
                    :start, :start
                )
            """,
            params,
        )
    print(f"  machines          : {len(ROSTER)}")


def seed_work_orders(conn, start: datetime, months: int) -> None:
    end = start + timedelta(days=30 * months)
    number = 0
    for machine_index, machine in enumerate(ROSTER):
        # 1,425 annual inspections across the fleet: 72 for the first five
        # machines and 71 for each remaining machine. This keeps the PM ratio
        # just below its 70% target, as required by the KPI demo dataset.
        preventive_count = round((72 if machine_index < 5 else 71) * months / 12)
        preventive_interval = (end - start) / preventive_count
        for inspection in range(preventive_count):
            at = start + preventive_interval * inspection
            started = at + timedelta(minutes=random.randint(10, 240))
            hours = round(random.uniform(1.0, 4.0), 2)
            number += 1
            params = {
                "work_order_id": f"WO-{number:06d}",
                "machine_id": machine.machine_id,
                "opened": at,
                "started": started,
                "closed": started + timedelta(hours=hours),
                "technician": fake.name(),
                "hours": hours,
                "cost": round(random.uniform(50, 800), 2),
            }
            _insert_ignore(
                conn,
                "ops.work_orders",
                "work_order_id",
                """
                    INSERT INTO ops.work_orders (
                        work_order_id, machine_id, wo_type, priority, opened_at,
                        started_at, closed_at, technician, labour_hours,
                        parts_cost_eur, notes, created_at, updated_at
                    ) VALUES (
                        :work_order_id, :machine_id, 'preventive', 'low', :opened,
                        :started, :closed, :technician, :hours, :cost,
                        'Planmäßige Wartung', :opened, :opened
                    )
                """,
                params,
            )

        # 640 annual corrective orders, weighted toward lower-grade machines.
        per_year = {"L": 40, "M": 24, "H": 8}[machine.machine_type]
        for _ in range(int(per_year * months / 12)):
            opened = start + timedelta(minutes=random.randint(0, months * 30 * 24 * 60))
            started = opened + timedelta(minutes=random.randint(5, 180))
            hours = round(random.uniform(0.5, 8.0), 2)
            failure_type = random.choices(
                ["HDF", "PWF", "OSF", "TWF", "RNF"], weights=[34, 32, 23, 9, 2]
            )[0]
            number += 1
            params = {
                "work_order_id": f"WO-{number:06d}",
                "machine_id": machine.machine_id,
                "failure_type": failure_type,
                "priority": random.choices(["medium", "high", "urgent"], weights=[40, 40, 20])[0],
                "opened": opened,
                "started": started,
                "closed": started + timedelta(hours=hours),
                "technician": fake.name(),
                "hours": hours,
                "cost": round(random.uniform(120, 4500), 2),
                "notes": f"Störung: {failure_type}",
            }
            _insert_ignore(
                conn,
                "ops.work_orders",
                "work_order_id",
                """
                    INSERT INTO ops.work_orders (
                        work_order_id, machine_id, wo_type, failure_type, priority,
                        opened_at, started_at, closed_at, technician, labour_hours,
                        parts_cost_eur, notes, created_at, updated_at
                    ) VALUES (
                        :work_order_id, :machine_id, 'corrective', :failure_type, :priority,
                        :opened, :started, :closed, :technician, :hours,
                        :cost, :notes, :opened, :opened
                    )
                """,
                params,
            )
    print(f"  work_orders       : {number}")


def seed_production_orders(conn, start: datetime, months: int) -> None:
    number = 0
    for machine in ROSTER:
        for day in range(months * 30):
            for shift_start in (6, 14, 22):
                number += 1
                planned_start = start + timedelta(days=day, hours=shift_start)
                planned_end = planned_start + timedelta(hours=8)
                planned = int(8 * 3600 / machine.ideal_cycle_seconds * random.uniform(0.75, 0.95))
                scrap = int(planned * SCRAP_RATE[machine.machine_type] * random.uniform(0.5, 1.8))
                params = {
                    "production_order_id": f"PO-{number:07d}",
                    "machine_id": machine.machine_id,
                    "product": random.choice(PRODUCTS),
                    "planned": planned,
                    "good": planned - scrap,
                    "scrap": scrap,
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    "actual_start": planned_start + timedelta(minutes=random.randint(0, 25)),
                    "actual_end": planned_end + timedelta(minutes=random.randint(-20, 70)),
                }
                _insert_ignore(
                    conn,
                    "ops.production_orders",
                    "production_order_id",
                    """
                        INSERT INTO ops.production_orders (
                            production_order_id, machine_id, product_code, planned_qty,
                            good_qty, scrap_qty, planned_start, planned_end,
                            actual_start, actual_end, status, created_at, updated_at
                        ) VALUES (
                            :production_order_id, :machine_id, :product, :planned, :good, :scrap,
                            :planned_start, :planned_end, :actual_start, :actual_end,
                            'completed', :planned_start, :planned_start
                        )
                    """,
                    params,
                )
    print(f"  production_orders : {number}")


@click.command()
@click.option("--start", default="2025-10-01")
@click.option("--months", default=None, type=click.IntRange(min=1))
@click.option(
    "--target",
    default="postgres",
    type=click.Choice(["postgres", "azure"]),
    help="Where to seed: local Postgres or Azure SQL.",
)
def main(start: str, months: int | None, target: str) -> None:
    random.seed(settings.sim_seed)
    Faker.seed(settings.sim_seed)
    start_datetime = datetime.fromisoformat(start)
    n_months = months or settings.sim_months

    print(f"\nSeeding operational source system (target={target})...")
    with _engine(target).begin() as connection:
        seed_plants(connection, start_datetime)
        seed_machines(connection, start_datetime)
        seed_work_orders(connection, start_datetime, n_months)
        seed_production_orders(connection, start_datetime, n_months)
    print("done.\n")


if __name__ == "__main__":
    main()
