"""Mutate machine master data so SCD Type 2 has changes to track."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import click
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from factorypulse.config import settings

LINES = ["LN-1", "LN-2", "LN-3", "LN-4"]
CRITICALITIES = ["low", "medium", "high"]
REASONS_LINE = [
    "Linienumstellung Produktwechsel",
    "Kapazitätsausgleich",
    "Umbau Fertigungszelle",
]
REASONS_CRIT = [
    "Neubewertung nach Produktanlauf",
    "Engpassmaschine identifiziert",
    "Redundanz geschaffen",
]
ALLOWED_FIELDS = {"line_id", "criticality"}


def _engine(target: str = "postgres"):
    if target == "azure":
        import os

        return create_engine(
            URL.create(
                "mssql+pymssql",
                username=os.environ.get("AZ_SQL_USER", "fpadmin"),
                password=os.environ["AZ_SQL_PASSWORD"],
                host=os.environ["AZ_SQL_SERVER"],
                database=os.environ.get("AZ_SQL_DB", "factorypulse"),
            ),
            connect_args={"timeout": 120, "login_timeout": 120},
            pool_pre_ping=True,
        )
    return create_engine(
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )


def apply_change(conn, machine_id: str, field: str, new_value: str, reason: str, at: datetime):
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"unsupported tracked field: {field}")
    old_value = conn.execute(
        text(f"SELECT {field} FROM ops.machines WHERE machine_id = :machine_id"),  # noqa: S608
        {"machine_id": machine_id},
    ).scalar_one()
    if old_value == new_value:
        return False

    conn.execute(
        text(
            f"UPDATE ops.machines SET {field} = :value, updated_at = :changed_at "  # noqa: S608
            "WHERE machine_id = :machine_id"
        ),
        {"value": new_value, "changed_at": at, "machine_id": machine_id},
    )
    conn.execute(
        text(
            """
            INSERT INTO ops.machine_change_log
                (machine_id, changed_field, old_value, new_value, change_reason, changed_at)
            VALUES (:machine_id, :field, :old, :new, :reason, :changed_at)
            """
        ),
        {
            "machine_id": machine_id,
            "field": field,
            "old": str(old_value),
            "new": new_value,
            "reason": reason,
            "changed_at": at,
        },
    )
    return True


@click.command()
@click.option("--start", default="2025-10-01")
@click.option("--months", default=None, type=click.IntRange(min=1))
@click.option("--n-changes", default=14, type=click.IntRange(min=0))
@click.option("--target", default="postgres", type=click.Choice(["postgres", "azure"]))
def main(start: str, months: int | None, n_changes: int, target: str) -> None:
    random.seed(settings.sim_seed + 7)
    start_datetime = datetime.fromisoformat(start)
    window_days = (months or settings.sim_months) * 30

    with _engine(target).begin() as connection:
        # The production trigger stamps ordinary changes with the current UTC
        # time. Disable it only while loading deterministic historical events.
        if target == "azure":
            connection.execute(text("DISABLE TRIGGER ops.trg_machines_updated ON ops.machines"))
        machine_ids = [
            row[0]
            for row in connection.execute(text("SELECT machine_id FROM ops.machines ORDER BY 1"))
        ]
        if not machine_ids:
            raise click.ClickException("ops.machines is empty; run the seed command first")

        applied = 0
        attempts = 0
        while applied < n_changes:
            attempts += 1
            if attempts > max(100, n_changes * 20):
                raise click.ClickException("could not generate the requested distinct changes")
            machine_id = random.choice(machine_ids)
            at = start_datetime + timedelta(
                days=int(window_days * (applied + 1) / (n_changes + 1)),
                hours=random.randint(6, 20),
            )
            if random.random() < 0.6:
                changed = apply_change(
                    connection,
                    machine_id,
                    "line_id",
                    random.choice(LINES),
                    random.choice(REASONS_LINE),
                    at,
                )
            else:
                changed = apply_change(
                    connection,
                    machine_id,
                    "criticality",
                    random.choice(CRITICALITIES),
                    random.choice(REASONS_CRIT),
                    at,
                )
            applied += int(changed)
        if target == "azure":
            connection.execute(text("ENABLE TRIGGER ops.trg_machines_updated ON ops.machines"))

    print(f"\napplied {applied} change events to ops.machines\n")


if __name__ == "__main__":
    main()
