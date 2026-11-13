"""Columnar partitioned Parquet storage exporter and reader.

Enables partition pruning on Condition and age_band for high-throughput OLAP.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

logger = logging.getLogger(__name__)


def export_partitioned_parquet(
    df: pd.DataFrame,
    base_dir: Path | str,
    partition_cols: list[str] | None = None,
) -> Path:
    """Export DataFrame into Hive-partitioned columnar Parquet files.
    
    Args:
        df: Input DataFrame to export (immutable; not modified).
        base_dir: Destination root folder for partitioned files.
        partition_cols: Columns used to partition data on disk.
    
    Returns:
        Path to base directory containing partitioned dataset.
    """
    out_dir = Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cols = partition_cols or ["Condition", "age_band"]
    
    # Convert pandas DataFrame to PyArrow Table
    table = pa.Table.from_pandas(df, preserve_index=False)
    
    # Write partitioned dataset using Hive partitioning schema
    ds.write_dataset(
        data=table,
        base_dir=str(out_dir),
        format="parquet",
        partitioning=cols,
        partitioning_flavor="hive",
        existing_data_behavior="overwrite_or_ignore",
    )
    logger.info(f"Exported {len(df)} rows to partitioned Parquet at {out_dir}")
    return out_dir


def read_partitioned_parquet(
    base_dir: Path | str,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Read partitioned Parquet dataset into a pandas DataFrame."""
    in_dir = Path(base_dir)
    if not in_dir.exists():
        raise FileNotFoundError(f"Parquet dataset directory not found: {in_dir}")
        
    dataset = ds.dataset(str(in_dir), format="parquet", partitioning="hive")
    table = dataset.to_table(columns=columns)
    return table.to_pandas()
