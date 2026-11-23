"""
Clinical Business Metric Catalog for HealthGuard 360.

Maps natural language questions and clinical intents to governed Gold analytical marts
and Star Schema dimensional models. Defines metric semantics, aggregation formulas,
supported filter dimensions, and table references.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MetricDefinition:
    """Immutable definition of a clinical or financial business metric."""
    name: str
    display_name: str
    description: str
    target_table: str
    sql_template: str
    keywords: List[str]
    supported_filters: List[str] = field(default_factory=list)
    unit: str = ""


# Standard clinical conditions present in HealthGuard-AI
KNOWN_CONDITIONS: List[str] = [
    "Heart Attack",
    "Heart Disease",
    "Diabetes",
    "Hypertension",
    "Asthma",
    "Stroke",
    "Cancer",
    "Chronic Kidney Disease",
    "COPD",
]

# Standard gender values
KNOWN_GENDERS: List[str] = ["Male", "Female", "Other"]


class MetricCatalog:
    """
    Searchable catalog of governed healthcare analytics metrics.
    Translates user intent into validated SQL queries against Gold marts.
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, MetricDefinition] = {}
        self._register_default_metrics()

    def register(self, metric: MetricDefinition) -> None:
        self._metrics[metric.name] = metric

    def get(self, name: str) -> Optional[MetricDefinition]:
        return self._metrics.get(name)

    @property
    def all_metrics(self) -> List[MetricDefinition]:
        return list(self._metrics.values())

    def _register_default_metrics(self) -> None:
        """Register core clinical & financial metrics mapping to Gold marts."""
        # 1. Overall Readmission Rate
        self.register(MetricDefinition(
            name="readmission_rate_overall",
            display_name="Overall Readmission Rate",
            description="30-day all-cause hospital readmission rate across all patients.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT ROUND(AVG(readmission_rate_pct), 2) AS readmission_rate,
                       SUM(total_patients) AS total_patients
                FROM gold_condition_mart
            """.strip(),
            keywords=["readmission rate", "readmission", "readmitted", "return rate"],
            unit="%",
        ))

        # 2. Condition-Specific Readmission Rate
        self.register(MetricDefinition(
            name="readmission_rate_by_condition",
            display_name="Readmission Rate by Condition",
            description="30-day readmission rate for a specific clinical diagnosis.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT condition,
                       readmission_rate_pct AS readmission_rate,
                       readmitted_count,
                       total_patients
                FROM gold_condition_mart
                WHERE LOWER(condition) = LOWER('{condition}')
            """.strip(),
            keywords=["readmission rate for", "readmission for", "readmitted with"],
            supported_filters=["condition"],
            unit="%",
        ))

        # 3. Average Treatment Cost Overall
        self.register(MetricDefinition(
            name="avg_cost_overall",
            display_name="Average Treatment Cost",
            description="Mean billing expenditure across all hospital encounters.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT ROUND(AVG(avg_cost), 2) AS avg_cost,
                       ROUND(SUM(total_cost), 2) AS total_expenditure
                FROM gold_condition_mart
            """.strip(),
            keywords=["average cost", "mean cost", "average billing", "avg cost"],
            unit="$",
        ))

        # 4. Average Cost by Condition
        self.register(MetricDefinition(
            name="avg_cost_by_condition",
            display_name="Average Cost by Condition",
            description="Mean treatment cost for a specific medical condition.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT condition,
                       avg_cost,
                       total_cost
                FROM gold_condition_mart
                WHERE LOWER(condition) = LOWER('{condition}')
            """.strip(),
            keywords=["cost for", "cost of", "expensive is", "billing for"],
            supported_filters=["condition"],
            unit="$",
        ))

        # 5. Top Expensive Conditions
        self.register(MetricDefinition(
            name="top_expensive_conditions",
            display_name="Top Most Expensive Conditions",
            description="Ranking conditions with highest average medical billing.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT condition,
                       avg_cost,
                       total_cost
                FROM gold_condition_mart
                ORDER BY avg_cost DESC
                LIMIT {limit}
            """.strip(),
            keywords=["most expensive", "highest cost", "top conditions by cost", "costliest"],
            supported_filters=["limit"],
            unit="$",
        ))

        # 6. Average Length of Stay (LOS)
        self.register(MetricDefinition(
            name="avg_length_of_stay",
            display_name="Average Length of Stay",
            description="Average hospitalization days per encounter.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT ROUND(AVG(avg_length_of_stay), 2) AS avg_los,
                       ROUND(MAX(avg_length_of_stay), 2) AS max_los
                FROM gold_condition_mart
            """.strip(),
            keywords=["length of stay", "average stay", "stay duration", "hospitalization days", "los"],
            unit="days",
        ))

        # 7. Patient Volume by Condition
        self.register(MetricDefinition(
            name="patient_count_by_condition",
            display_name="Patient Count by Condition",
            description="Total diagnosed patient volume for a given condition.",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT condition,
                       total_patients AS patient_count,
                       ROUND(avg_cost, 2) AS avg_cost
                FROM gold_condition_mart
                WHERE LOWER(condition) = LOWER('{condition}')
            """.strip(),
            keywords=["how many patients", "patient count", "diagnosed with", "patients with"],
            supported_filters=["condition"],
            unit="patients",
        ))

        # 8. Gender Distribution & Costs
        self.register(MetricDefinition(
            name="gender_analytics",
            display_name="Gender Distribution & Outcomes",
            description="Patient count, average cost, and readmission rate broken down by gender.",
            target_table="gold_gender_mart",
            sql_template="""
                SELECT gender,
                       total_patients AS patient_count,
                       ROUND(avg_cost, 2) AS avg_cost,
                       ROUND(readmission_rate_pct, 2) AS readmission_rate
                FROM gold_gender_mart
                ORDER BY total_patients DESC
            """.strip(),
            keywords=["gender", "male", "female", "men vs women", "sex distribution"],
            unit="patients",
        ))

        # 9. Patient Satisfaction Score
        self.register(MetricDefinition(
            name="patient_satisfaction",
            display_name="Average Patient Satisfaction",
            description="Mean patient-reported clinical satisfaction score (1 to 5).",
            target_table="gold_condition_mart",
            sql_template="""
                SELECT ROUND(AVG(avg_satisfaction), 2) AS avg_satisfaction,
                       SUM(total_patients) AS total_ratings
                FROM gold_condition_mart
                WHERE avg_satisfaction IS NOT NULL
            """.strip(),
            keywords=["satisfaction", "satisfaction score", "patient experience", "rating"],
            unit="/5",
        ))

        # 10. Patient Discharge Outcomes
        self.register(MetricDefinition(
            name="discharge_outcomes",
            display_name="Discharge Outcomes Summary",
            description="Distribution of patient clinical outcomes (e.g. Recovered vs Stable).",
            target_table="gold_outcome_mart",
            sql_template="""
                SELECT outcome,
                       total_patients AS patient_count,
                       ROUND(readmission_rate_pct, 2) AS readmission_rate
                FROM gold_outcome_mart
                ORDER BY total_patients DESC
            """.strip(),
            keywords=["outcome", "outcomes", "recovered", "recovery rate", "stable"],
            unit="patients",
        ))

    # ------------------------------------------------------------------
    # Query Matching & Entity Extraction
    # ------------------------------------------------------------------
    def match(self, question: str) -> Optional[Tuple[MetricDefinition, Dict[str, Any]]]:
        """
        Match a natural language question to a metric definition and extract parameters.
        Returns (MetricDefinition, params_dict) or None if unmatched.
        """
        q_lower = question.lower()

        # Extract entities
        extracted_condition = self._extract_condition(q_lower)
        limit_val = self._extract_limit(q_lower)

        # 1. Condition-specific readmission
        if any(k in q_lower for k in ["readmission", "readmitted", "return"]) and extracted_condition:
            metric = self.get("readmission_rate_by_condition")
            if metric:
                return metric, {"condition": extracted_condition}

        # 2. Overall readmission
        if any(k in q_lower for k in ["readmission", "readmitted"]):
            metric = self.get("readmission_rate_overall")
            if metric:
                return metric, {}

        # 3. Top expensive conditions
        if any(k in q_lower for k in ["most expensive", "highest cost", "top conditions", "costliest"]):
            metric = self.get("top_expensive_conditions")
            if metric:
                return metric, {"limit": limit_val}

        # 4. Condition-specific cost
        if any(k in q_lower for k in ["cost", "billing", "expensive"]) and extracted_condition:
            metric = self.get("avg_cost_by_condition")
            if metric:
                return metric, {"condition": extracted_condition}

        # 5. Overall cost
        if any(k in q_lower for k in ["average cost", "mean cost", "overall cost", "total cost", "billing"]):
            metric = self.get("avg_cost_overall")
            if metric:
                return metric, {}

        # 6. Patient count by condition
        if any(k in q_lower for k in ["how many", "count", "number of patients"]) and extracted_condition:
            metric = self.get("patient_count_by_condition")
            if metric:
                return metric, {"condition": extracted_condition}

        # 7. Length of stay
        if any(k in q_lower for k in ["length of stay", "stay", "los", "hospitalization"]):
            metric = self.get("avg_length_of_stay")
            if metric:
                return metric, {}

        # 8. Satisfaction
        if any(k in q_lower for k in ["satisfaction", "rating", "experience"]):
            metric = self.get("patient_satisfaction")
            if metric:
                return metric, {}

        # 9. Gender analytics
        if any(k in q_lower for k in ["gender", "male", "female", "men", "women"]):
            metric = self.get("gender_analytics")
            if metric:
                return metric, {}

        # 10. Outcomes
        if any(k in q_lower for k in ["outcome", "recovered", "recovery"]):
            metric = self.get("discharge_outcomes")
            if metric:
                return metric, {}

        return None

    @staticmethod
    def _extract_condition(text: str) -> Optional[str]:
        """Extract exact known clinical condition from text."""
        for cond in KNOWN_CONDITIONS:
            if cond.lower() in text:
                return cond
        return None

    @staticmethod
    def _extract_limit(text: str) -> int:
        """Extract requested top N count or default to 3."""
        match = re.search(r"\btop\s+(\d+)\b", text)
        if match:
            return max(1, min(int(match.group(1)), 20))
        return 3
