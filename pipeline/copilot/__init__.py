"""
Governed Healthcare AI Data Copilot Package for HealthGuard 360.

Exports:
  - HealthcareDataCopilot: core NL-to-SQL governed agent
  - MetricCatalog: clinical metric definitions
  - SqlAstValidator: AST security governance validator
  - CopilotResponse: structured grounded response
  - CopilotEvaluationSuite: 35-question evaluation framework
"""
from pipeline.copilot.catalog import KNOWN_CONDITIONS, MetricCatalog, MetricDefinition
from pipeline.copilot.copilot import CopilotResponse, HealthcareDataCopilot
from pipeline.copilot.evals import (
    BENCHMARK_QUESTIONS,
    CopilotEvaluationSuite,
    EvaluationScorecard,
    EvalQuestion,
)
from pipeline.copilot.validator import SqlAstValidator, ValidationResult

__all__ = [
    "HealthcareDataCopilot",
    "MetricCatalog",
    "MetricDefinition",
    "KNOWN_CONDITIONS",
    "SqlAstValidator",
    "ValidationResult",
    "CopilotResponse",
    "CopilotEvaluationSuite",
    "EvaluationScorecard",
    "EvalQuestion",
    "BENCHMARK_QUESTIONS",
]
