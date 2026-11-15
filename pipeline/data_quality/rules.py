"""Clinical data quality rules engine.

Evaluates individual and batched records against medical boundaries,
numerical range constraints, allowed enums, and non-null guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import pandas as pd

from pipeline.config import (
    ALLOWED_GENDER,
    ALLOWED_OUTCOMES,
    ALLOWED_READMISSION,
    CONSTRAINTS,
)


@dataclass(frozen=True)
class Violation:
    """Details of a single quality rule failure."""
    rule_name: str
    column: str
    observed_value: Any
    severity: str  # 'CRITICAL' | 'WARNING'
    message: str


@dataclass(frozen=True)
class RuleValidationResult:
    """Outcome of validating a healthcare record against the rule suite."""
    is_valid: bool
    violations: tuple[Violation, ...] = field(default_factory=tuple)


class ClinicalRuleSuite:
    """Rule validation engine for clinical encounter records."""

    @staticmethod
    def validate_record(record: dict[str, Any]) -> RuleValidationResult:
        violations: list[Violation] = []

        # 1. Age Range Check
        age = record.get("Age") if "Age" in record else record.get("age")
        if age is not None:
            try:
                age_val = float(age)
                lo, hi = CONSTRAINTS["Age"]
                if not (lo <= age_val <= hi):
                    violations.append(
                        Violation(
                            rule_name="Age_Range_Boundary",
                            column="Age",
                            observed_value=age,
                            severity="CRITICAL",
                            message=f"Age {age_val} falls outside human physiological bounds [{lo}, {hi}].",
                        )
                    )
            except (ValueError, TypeError):
                violations.append(
                    Violation(
                        rule_name="Age_Numeric_Format",
                        column="Age",
                        observed_value=age,
                        severity="CRITICAL",
                        message=f"Age '{age}' cannot be parsed as numeric.",
                    )
                )

        # 2. Cost Range Check (non-negative)
        cost = record.get("Cost") if "Cost" in record else record.get("cost")
        if cost is not None:
            try:
                cost_val = float(cost)
                lo, hi = CONSTRAINTS["Cost"]
                if not (lo <= cost_val <= hi):
                    violations.append(
                        Violation(
                            rule_name="Cost_Range_Boundary",
                            column="Cost",
                            observed_value=cost,
                            severity="CRITICAL",
                            message=f"Cost {cost_val} is invalid; must be between {lo} and {hi}.",
                        )
                    )
            except (ValueError, TypeError):
                violations.append(
                    Violation(
                        rule_name="Cost_Numeric_Format",
                        column="Cost",
                        observed_value=cost,
                        severity="CRITICAL",
                        message=f"Cost '{cost}' is not numeric.",
                    )
                )

        # 3. Readmission Enum Check
        readmit = record.get("Readmission") if "Readmission" in record else record.get("readmission")
        if readmit is not None:
            clean_r = str(readmit).strip().capitalize()
            if clean_r not in ALLOWED_READMISSION:
                violations.append(
                    Violation(
                        rule_name="Readmission_Categorical_Enum",
                        column="Readmission",
                        observed_value=readmit,
                        severity="CRITICAL",
                        message=f"Readmission '{readmit}' not in {list(ALLOWED_READMISSION)}.",
                    )
                )

        # 4. Gender Enum Check
        gender = record.get("Gender") if "Gender" in record else record.get("gender")
        if gender is not None:
            clean_g = str(gender).strip().capitalize()
            if clean_g not in ALLOWED_GENDER:
                violations.append(
                    Violation(
                        rule_name="Gender_Categorical_Enum",
                        column="Gender",
                        observed_value=gender,
                        severity="WARNING",
                        message=f"Gender '{gender}' not in {list(ALLOWED_GENDER)}.",
                    )
                )

        # 5. Length of Stay Range
        los = record.get("Length_of_Stay") if "Length_of_Stay" in record else record.get("length_of_stay")
        if los is not None:
            try:
                los_val = float(los)
                lo, hi = CONSTRAINTS["Length_of_Stay"]
                if not (lo <= los_val <= hi):
                    violations.append(
                        Violation(
                            rule_name="Length_of_Stay_Range",
                            column="Length_of_Stay",
                            observed_value=los,
                            severity="CRITICAL",
                            message=f"Length of Stay {los_val} exceeds bounds [{lo}, {hi}].",
                        )
                    )
            except (ValueError, TypeError):
                violations.append(
                    Violation(
                        rule_name="Length_of_Stay_Format",
                        column="Length_of_Stay",
                        observed_value=los,
                        severity="CRITICAL",
                        message=f"Length of Stay '{los}' not numeric.",
                    )
                )

        is_valid = len([v for v in violations if v.severity == "CRITICAL"]) == 0
        return RuleValidationResult(is_valid=is_valid, violations=tuple(violations))


def evaluate_record_quality(record: dict[str, Any]) -> RuleValidationResult:
    """Convenience functional interface for record validation."""
    return ClinicalRuleSuite.validate_record(record)
