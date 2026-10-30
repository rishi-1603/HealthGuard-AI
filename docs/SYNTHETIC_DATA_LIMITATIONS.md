# Synthetic Data Realism & Methodological Honesty Audit
**Author:** Rishi Dappu, Data Analyst  
**Key Principle:** Evidence-Based Integrity over Inflated ML Claims

---

## 1. Why a 0.99 ROC-AUC is a Synthetic Artifact, Not Clinical Magic

In healthcare machine learning, achieving an ROC-AUC of 0.99 for all-cause 30-day readmissions on real-world electronic health records (EHR) is statistically impossible due to unobserved social determinants, outpatient compliance variability, and behavioral factors. High real-world EHR models typically achieve AUCs between **0.68 and 0.76**.

In this project, an apparent 0.99 AUC was observed under Random Forest modeling. A rigorous audit revealed:
1. **Deterministic Generator Rules:** The synthetic data generation process mapped medical conditions, procedure types, and readmission probabilities using strong programmatic rules.
2. **Procedure-Condition Confounding:** Certain synthetic procedures mapped almost 1-to-1 with high-readmission conditions, providing an artificial predictive shortcut.
3. **No-ML Baseline Benchmark:** A simple condition-only empirical lookup table achieved **0.929 ROC-AUC** with zero machine learning.

> **Methodological Conclusion:** The ML model merely memorized the programmatic generator's synthetic logic. Documenting this limitation candidly is a hallmark of senior analytical maturity.
