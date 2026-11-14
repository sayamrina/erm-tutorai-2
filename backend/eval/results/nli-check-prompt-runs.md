# NLI check of cited statements (cross-encoder/nli-deberta-v3-base)

Premise: the cited lecture passage. Hypothesis: the statement without its citation marker. A statement with several citations counts as supported if one passage entails it. Automatic check; the model is independent of GPT-4o, but NLI on terse slide text is strict, so neutral often means 'implied, not stated'.

| Run | Cited statements | Entailment | Neutral | Contradiction |
|---|---|---|---|---|
| 2026-11-03-v1-prompt | 44 | 34% | 59% | 7% |
| 2026-11-03-v2-prompt | 71 | 48% | 51% | 1% |
