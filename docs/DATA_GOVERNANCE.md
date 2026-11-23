# HealthGuard 360 — Data Governance & Trust Framework

## 1. Governance Principles & HIPAA Alignment

HealthGuard 360 enforces a **Zero-Trust, Audit-First Data Governance Architecture** engineered specifically for clinical environments governed by HIPAA (Health Insurance Portability and Accountability Act), HITECH, and ISO 27001 standards.

All ingestion pipelines, storage layers, and AI consumption surfaces implement strict boundaries:
1. **Zero Unvalidated Ingestion**: No raw payload moves to Silver without passing schema and domain contracts.
2. **Deterministic Provenance**: Every metric presented in the dashboard or copilot carries traceable lineage back to source tables.
3. **Defense-in-Depth AST Validation**: No user-facing AI model has direct unconstrained SQL execution access to the database.

---

## 2. 4-Pillar Data Trust Scoring Framework

HealthGuard 360 computes an objective, automated **Data Trust Score (0–100%)** across four mathematical pillars:

$$\text{Data Trust Score} = 0.30 \times \text{Validity} + 0.30 \times \text{Completeness} + 0.20 \times \text{Uniqueness} + 0.20 \times \text{Referential Integrity}$$

### Pillar Definitions & Weights

| Pillar | Weight | Mathematical Definition | Target Threshold |
| :--- | :--- | :--- | :--- |
| **Validity** | 30% | Percentage of field values conforming to domain data types, regex formats, and clinical bounds (e.g., cost > 0, LOS > 0, valid dates). | $\ge 98.0\%$ |
| **Completeness** | 30% | Ratio of populated non-null values across mandatory critical clinical columns. | $\ge 99.0\%$ |
| **Uniqueness** | 20% | Proportion of records free from duplicate primary or natural keys (`encounter_id`, `patient_id`). | $100.0\%$ |
| **Referential Integrity** | 20% | Percentage of child foreign keys matching active parent keys in dimension tables (`dim_patient`, `dim_date`). | $100.0\%$ |

### Trust Status Tiers
- **Grade A (Optimal / Production-Ready)**: Trust Score $\ge 95.0\%$ — Approved for downstream ML and executive reporting.
- **Grade B (Warning / Attention Required)**: $85.0\% \le \text{Score} < 95.0\%$ — Automated alerts dispatched; pipeline proceeds with caution.
- **Grade C (Critical / Blocked)**: $\text{Score} < 85.0\%$ — Pipeline halt; downstream gold mart updates gated until remediation.

---

## 3. Automated Quarantine Engine & Poison Pill Isolation

When incoming records fail schema contracts or clinical domain rules:
1. **Immediate Isolation**: Failed records are segregated from the Silver pipeline into the `quarantine_encounters` table.
2. **Diagnostic Enrichment**: Records are tagged with an immutable error code, timestamp, source bundle, and violation detail:
   - `NULL_MANDATORY_FIELD`: Missing patient ID or encounter ID.
   - `OUT_OF_BOUNDS_VALUE`: Negative cost, zero length of stay, or invalid satisfaction rating.
   - `CORRUPTED_JSON_ENVELOPE`: Malformed payload unable to be deserialized.
3. **Pipeline Non-Blocking**: Valid records in the same batch continue processing to Silver and Gold, preventing noisy poison pills from halting critical hospital operations.

---

## 4. Governed AI Copilot AST Guardrails

Natural language interactions are protected by a deterministic AST validation layer using **SQLGlot**:

1. **Read-Only Enforcement**:
   - Only `SELECT` statements are accepted.
   - Any AST containing `Drop`, `Insert`, `Update`, `Delete`, `Alter`, `Truncate`, or `Attach` is rejected before database execution.
2. **Strict Table Whitelisting**:
   - Queries are constrained strictly to approved Gold analytical marts (`gold_condition_mart`, `gold_daily_summary`, `gold_gender_mart`, `gold_outcome_mart`).
   - Access to system catalogs (`sqlite_master`, `information_schema`) or internal operational tables is blocked.
3. **Resource Protection & Clamping**:
   - Queries without an explicit `LIMIT` clause have `LIMIT 100` injected into the AST.
   - Queries with excessively large limits (> 500 rows) are clamped down to the system ceiling.
4. **Adversarial Injection Defense**:
   - Tautologies (`'1'='1'`), stacked semicolons, union extractions, and comment delimiters (`--`) trigger immediate security refusal responses.

---

## 5. Security & Privacy Controls

- **Encryption at Rest**: AES-256 GCM encryption on all storage accounts and database volumes.
- **Encryption in Transit**: TLS 1.2+ mandatory on all API, streaming, and database connections.
- **PII Pseudonymization**: Natural patient identifiers are pseudonymized with cryptographically secure surrogate keys (`patient_key`) in dimensional models.
- **Audit Logging**: Every query, user interaction, CDC event, and DAG execution writes an immutable trace record.
