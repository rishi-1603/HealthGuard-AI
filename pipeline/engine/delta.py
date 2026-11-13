"""Row-level incremental delta engine using SHA-256 record hashing.

Enables incremental CDC (Change Data Capture) loading to avoid processing
unchanged records across pipeline batches.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import pandas as pd


@dataclass(frozen=True)
class DeltaReport:
    """Summary of incremental CDC delta detection."""
    new_rows: int
    updated_rows: int
    unchanged_rows: int
    total_incoming_rows: int


def compute_row_hashes(df: pd.DataFrame, exclude_cols: list[str] | None = None) -> pd.Series:
    """Generate deterministic SHA-256 hashes for each row in a DataFrame."""
    cols = [c for c in sorted(df.columns) if c not in (exclude_cols or [])]
    
    def _hash_row(row) -> str:
        content = "|".join(str(row[c]) for c in cols)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    return df.apply(_hash_row, axis=1)


def detect_deltas(
    existing_df: pd.DataFrame,
    incoming_df: pd.DataFrame,
    key_col: str = "Patient_ID",
) -> tuple[pd.DataFrame, DeltaReport]:
    """Identify inserts and updates between existing dataset and incoming batch.
    
    Returns:
        tuple of:
          - delta_df: DataFrame containing only new and updated rows
          - report: DeltaReport statistics summary
    """
    if existing_df.empty:
        report = DeltaReport(
            new_rows=len(incoming_df),
            updated_rows=0,
            unchanged_rows=0,
            total_incoming_rows=len(incoming_df),
        )
        return incoming_df.copy(), report

    # Generate hashes for change detection
    exist_hashes = compute_row_hashes(existing_df)
    incom_hashes = compute_row_hashes(incoming_df)
    
    exist_map = dict(zip(existing_df[key_col], exist_hashes))
    
    new_indices = []
    updated_indices = []
    unchanged_count = 0
    
    for idx, (key_val, in_hash) in enumerate(zip(incoming_df[key_col], incom_hashes)):
        if key_val not in exist_map:
            new_indices.append(incoming_df.index[idx])
        elif exist_map[key_val] != in_hash:
            updated_indices.append(incoming_df.index[idx])
        else:
            unchanged_count += 1
            
    delta_indices = new_indices + updated_indices
    delta_df = incoming_df.loc[delta_indices].copy()
    
    report = DeltaReport(
        new_rows=len(new_indices),
        updated_rows=len(updated_indices),
        unchanged_rows=unchanged_count,
        total_incoming_rows=len(incoming_df),
    )
    return delta_df, report
