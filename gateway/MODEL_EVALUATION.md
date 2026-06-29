    # CogniGuard — Model Evaluation Report (Phase A)

    > **Purpose:** comprehensive model bake-off to validate the chosen production
    > architecture and provide evidence of rigorous model selection.
    > This is a **validation report**, not a selection decision — the production stack
    > is locked (see below). Approve this report to unblock Phases B–F.

    ---

    ## Production Architecture Decision

    The following stack is locked and is **not subject to change by this benchmark**:

    | Role | Model | Status |
    | --- | --- | --- |
    | Primary behavioral model | **LSTM Autoencoder** | Production (ONNX + TFLite) |
    | Fallback / cold-start behavioral model | **Isolation Forest** | Production (shadow always-on) |
    | Decision / stacking model | **XGBoost** | Production (stacked on Behavior\_Score) |
    | Research / benchmark only | Transformer Encoder | Staging — never auto-promoted |

    The **TransformerEncoder** is included in this bake-off to:
    - Provide technical evidence that the Transformer architecture was evaluated
    - Quantify whether it offers a meaningful advantage over the LSTM AE
    - Establish a baseline for future re-evaluation

    It will **not** replace the LSTM Autoencoder unless a human reviewer explicitly
    approves promotion after verifying simultaneous improvement in EER, FAR/FRR,
    latency, memory footprint, and on-device (TFLite) deployment suitability.

    ---

    ## Track 1 — Behavioral Biometrics (all candidates)

    **Protocol:** Killourhy–Maxion per-subject on CMU keystroke dataset (flat models);
    80/20 subject-level split on CMU + HMOG pooled windows (sequence models).
    **Primary metric:** EER ↓ (G6 target ≤ 0.10) · ROC-AUC ↑.

    | model | eer | far | frr | roc_auc | pr_auc | accuracy | f1 | single_p50_ms | single_p95_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RandomForest | 0.2330 | 0.2329 | 0.2330 | 0.8386 | 0.4109 | 0.7670 | 0.5684 | 36.3077 | 53.1748 |
| OneClassSVM | 0.2533 | 0.2533 | 0.2533 | 0.8202 | 0.6639 | 0.7467 | 0.5411 | 0.1497 | 0.1671 |
| IsolationForest | 0.2953 | 0.2953 | 0.2953 | 0.7798 | 0.5462 | 0.7047 | 0.4884 | 5.6872 | 6.9025 |
| LightGBM | 0.3785 | 0.3784 | 0.3785 | 0.6627 | 0.2599 | 0.6215 | 0.3964 | 0.7818 | 1.4836 |
| LSTMAutoencoder | 0.4480 | 0.4480 | 0.4480 | 0.5777 | 0.5888 | 0.5520 | 0.5520 | 0.4318 | 0.4806 |
| XGBoost | 0.4686 | 0.4686 | 0.4686 | 0.5446 | 0.2101 | 0.5314 | 0.3120 | 0.2227 | 0.6019 |
| TransformerEncoder | 0.5000 | 0.5000 | 0.5000 | 0.5119 | 0.4964 | 0.5000 | 0.5000 | 0.1656 | 0.1915 |
| LogisticRegression | 0.5435 | 0.5435 | 0.5435 | 0.4304 | 0.1695 | 0.4565 | 0.2515 | 0.0618 | 0.0878 |

    ### Production Stack Confirmation (Track 1)

    **Production stack is fixed:** LSTMAutoencoder (primary) + IsolationForest (shadow/fallback). LSTMAutoencoder achieved EER=0.4480 (G6 target ≤ 0.10: FAIL). IsolationForest (shadow/fallback) achieved EER=0.2953. Benchmark winner by EER: **RandomForest** — included as evaluation evidence only. The TransformerEncoder is a research model; see the Transformer Validation section below.

    ### TransformerEncoder Validation

    | Metric | LSTMAutoencoder (production) | TransformerEncoder (research) |
| --- | --- | --- |
| EER ↓ | 0.4480 | 0.5000 |
| ROC-AUC ↑ | 0.5777 | 0.5119 |
| p95 latency (single row) | 0.5 ms | 0.2 ms |
| FAR | 0.4480 | 0.5000 |
| FRR | 0.4480 | 0.5000 |

The TransformerEncoder **meets neither threshold** for production consideration.

    ---

    ## Track 2 — Transaction Fraud (all candidates)

    **Data:** `TXN_HISTORY_UPI_FIN` (heuristic label: new-payee ∧ amount-z>2 ∧ odd-time).
    **Primary metric:** PR-AUC ↑ · recall@FPR=0.05 (fraud is severely class-imbalanced).

    | model | roc_auc | pr_auc | recall_at_fpr05 | precision | recall | f1 | single_p50_ms | single_p95_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| XGBoost | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.1874 | 0.3000 |
| LightGBM | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.5840 | 0.6646 |
| RandomForest | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 37.6074 | 42.0284 |
| LogisticRegression | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.5000 | 0.6667 | 0.0633 | 0.1534 |

    ### Production Stack Confirmation (Track 2)

    **Production model is fixed:** XGBoost (stacked on Behavior_Score). XGBoost achieved PR-AUC=1.0000, recall@FPR=0.05=1.0000. Benchmark winner by PR-AUC: **XGBoost** — included as evaluation evidence. PR-AUC is the primary metric due to class imbalance in fraud labels.

    ---

    ## Latency vs Accuracy Trade-off

    Login decision p95 budget: **< 300 ms**. Payment decision p95 budget: **< 500 ms**.
    `single_p95_ms` is the hard gate — any model exceeding 300 ms on a single row is
    disqualified from the real-time hot path regardless of accuracy.
    Sequence models (AE, Transformer) operate on (16, 9) windows via onnxruntime;
    flat models operate on 4-dim or 9-dim rows.

    ---

    ## ROC / PR Curves

    ![track1_roc.png](training/reports/track1_roc.png)
![track1_pr.png](training/reports/track1_pr.png)
![track2_roc.png](training/reports/track2_roc.png)
![track2_pr.png](training/reports/track2_pr.png)

    ---

    ## Approval Gate

    Review the tables, Transformer Validation section, and curves above, then either:

    - **Approve** → Phase B–F work may begin; production stack remains as declared.
    - **Override** → Provide explicit written justification to promote the Transformer
      (must show improvement on EER, FAR/FRR, latency, and deployment suitability
      simultaneously). Phase F's champion-challenger flow handles the actual promotion.
