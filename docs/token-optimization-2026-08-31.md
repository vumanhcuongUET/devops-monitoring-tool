# Token Optimization — AI Analysis Input (2026-08-31)

Closes the remaining Phase 6 goal (60% input reduction) that earlier passes
left open. Four commits, each independently measurable through the
`llm_*_tokens_total` Prometheus series.

## Baseline: what was already lean

Prompt caching (system + agent prompts, ephemeral), 5-field ES log fetches,
severity-quota log sampling (~30 kept), compact JSON, pre-aggregated
K8s/APM/metrics contexts, per-agent pre-digestion, model tiering (haiku for
simple-stream/health), ai_assistant OutputOptimizer.

## What this batch changed

| # | Change | Where | Effect |
|---|--------|-------|--------|
| 1 | `llm_cache_read_tokens_total` / `llm_cache_creation_tokens_total` counters | `app/llm_metrics.py` | Cache discount is now observable — baseline for everything below |
| 2 | Log `message` head-truncated at 400 chars (`[truncated N chars]` marker + prompt note) | `app/services/llm_input.py`, `llm_client.py`, `log_agent.py` | A 2KB stack trace used to ship whole; 30 logs could carry 10-15k tokens. Worst case now bounded |
| 2 | Alert storms deduped per (rule_name, severity), `occurrences` count, latest message kept, 300-char cap, max 10 groups | `llm_input.dedupe_alerts` via `analyze.py` | 20 repeating alerts → a few lines |
| 3 | Hard output budget in the triage system prompt: ≤5 findings, ≤3 recommendations, ≤2-sentence descriptions, ≤200-char evidence, ≤5-sentence summary | `llm_client.SYSTEM_PROMPT` | Output tokens bill ~5× input — typically the biggest single saving |
| 4 | `AI_INPUT_BUDGET_TOKENS` (default 12000): prompt estimates itself (~4 chars/token); logs shrink down a quota ladder (info → warning → critical/error) before being dropped with a note; other sections survive | `config.py`, `llm_client._fit_logs_section` | No prompt can blow past the ceiling regardless of input |
| 4 | `analyze_simple_streaming` runs its context through the same slimming (`slim_context`) | `llm_client.py` | The one path that still shipped raw blobs |

## Expected effect

Typical triage input ~5-8k tokens → ~2-3k; storm scenarios (stack traces +
alert floods) bounded by the budget instead of unbounded. Output typically
-30-50% from the prompt constraints. Verify with:

```
rate(llm_input_tokens_total[1h]) / rate(llm_api_requests_total[1h])
rate(llm_output_tokens_total[1h]) / rate(llm_api_requests_total[1h])
rate(llm_cache_read_tokens_total[1h]) / rate(llm_api_requests_total[1h])
```

per `path`/`model`, before vs after rollout.

## Still open (deliberately)

- Multi-agent N× input: each agent receives the full context dict; all of
  them pre-digest, so the duplication is bounded — a shared pre-digest would
  only pay off if orchestrate() traffic grows.
- Full-tokenizer budget check: the ~4 chars/token estimate is intentionally
  crude; a tokenizer round-trip per request costs more than it saves.
- Timestamps ship as full ISO strings (~10 tokens each) — shortening to
  HH:MM:SS would save ~300 tokens/prompt at some clarity cost.
