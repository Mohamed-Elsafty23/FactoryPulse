"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from pyspark.sql import SparkSession

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
