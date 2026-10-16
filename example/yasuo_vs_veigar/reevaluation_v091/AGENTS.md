# A/B scoring reproducibility

- For A/B level 1 to 3 scoring, use `AB_1到3级评分区间.md` and frozen version `AB-L1-L3-interval-1.0` as the current reference.
- Recompute with `python example/yasuo_vs_veigar/reevaluation_v091/score_intervals.py` from the workspace root.
- Do not invent new grades in conversation, silently replace interval endpoints, or present exploratory point scores as authoritative player rankings.
- Files in `interval_v1` are frozen snapshots. Evidence, rules, or code changes require a separate version and an explicit explanation to the user. Preserve prior results.
- The intervals cover common observed items (63 percent of original weight), not full-model scores, statistical confidence, or overall rank.
- Do not insert revision history or change reports into the publishable main model. Explain changes in chat.
