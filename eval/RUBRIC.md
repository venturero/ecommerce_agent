# Human evaluation rubric (Day 8)

Score each response **1–5** (1 = poor, 5 = excellent). Review the saved JSON under `eval/results/<run_id>/responses/<id>.json` or the summary row for that prompt.

| Criterion | What to look for |
|-----------|------------------|
| **Relevance** | Shortlist matches the query constraints (product type, budget, brand, retailer). |
| **Clarity** | `message` and per-item `explanation` are easy to understand; no jargon overload. |
| **Usefulness** | A real shopper could act on the shortlist (real URLs, sensible titles, trade-offs visible). |
| **Diversity** | Multiple viable options when appropriate; not five near-duplicates unless query is narrow. |
| **Trust** | No invented reviews, ratings, stock guarantees, or prices not supported by title/snippet/metadata. |

## Optional notes

- Record scores in `eval/results/<run_id>/human_scores.csv` (create if needed):

```csv
prompt_id,relevance,clarity,usefulness,diversity,trust,notes
c01,4,4,4,3,5,""
```

## Comparing runs

After two automated runs, use:

```bash
python -m shopping_search_agent.eval_runner compare eval/results/RUN_A eval/results/RUN_B
```

Re-score only prompts where the shortlist or explanations changed.
