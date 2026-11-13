# AGENTS.md — Global Operating Framework for HealthGuard AI
### Active Engine: Ruflo + GSD Core + Ralph + Ponytail + Addy Osmani Skills + CodeRabbit + Awesome Skills

All agentic sessions operating in this repository MUST strictly abide by this unified operating standard.

---

## 1. The Core Operating Loop (Every Task Follows This)

```
[1. Ruflo Memory & Context Recall]
    Search progress.txt / past learnings for schema contracts, invariants, and constraints.
         ↓
[2. Ralph Story & Branch Check]
    Verify active branch from prd.json. Pick highest priority story where passes: false.
         ↓
[3. Addy Osmani Spec & Ponytail Scope Control]
    - Spec-Driven: Define exact input/output contracts and boundaries before writing implementation.
    - Ponytail Simplicity: Smallest complete diff, zero bloat, maximum reuse of existing patterns.
         ↓
[4. TDD / Awesome TDD Implementation]
    Implement unit/integration/E2E tests first (RED), then code to pass (GREEN).
    Maintain strict boundary validation and immutability (return new state).
         ↓
[5. Multi-Layer Verification & CodeRabbit Review Gate]
    Run full test suite (pytest). Inspect git diff against:
    - CodeRabbit quality & security rules
    - Addy Osmani 5-axis review (correctness, security, performance, maintainability, tests)
    - Zero console junk, no unhandled exceptions
         ↓
[6. Commit & Progress Ledger]
    Commit: feat: [Story ID] - [Story Title] (Author: Rishi <rishidappu16@gmail.com>)
    Mark story passes: true in prd.json.
    Append exact technical learnings and benchmark receipts to progress.txt.
```

---

## 2. Invariants & Rules of Engagement

1. **Own the Task End-to-End**:
   Never leave tasks hanging, never output `# TODO` or half-baked stubs. Deliver 100% working, executed, and tested code.
2. **Empirical Proof Over Claims**:
   Every completion statement must be backed by exact terminal test output receipts (e.g., `213 passed in 11.72s`).
3. **The Best Code Is Code Never Written (Ponytail)**:
   Deletion beats addition. Favor standard library and existing patterns over new dependencies.
4. **Security & Zero Secrets**:
   Never commit `.env`, API keys, or raw credentials. All external boundaries must be strictly sanitized and type-validated.
5. **No Regressions**:
   New features must pass 100% of newly added tests while keeping all existing project tests green.
6. **Cloud & Production Ready (Google Cloud / DevTools)**:
   Architect code to be container-friendly, stateless, reproducible, and verifiable via automated CI/CD and telemetry.
