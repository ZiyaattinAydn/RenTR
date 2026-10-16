# Phase 2.6.1 — Native Base LLM Batch Inference

The previous parallel-request experiment showed essentially no throughput gain on the target
machine: two concurrent requests still took about 30.8 seconds for the deterministic ten-unit
pilot. The next performance lever is reducing request count rather than adding concurrent work.

## Base batching

For TranslateGemma, RenTR can now send multiple independent protected sources in one Ollama
request. Every item carries an immutable `id`, source text and placeholder layout contract.
The model must return one structured translation for every id in the same order.

The pipeline still validates each returned translation independently. Token restoration, Ren'Py
QC, semantic risk analysis, repair routing and candidate judging remain per-unit decisions.

## Fail-safe fallback

Batching is an optimization, not a correctness dependency. If the model returns malformed JSON,
changes/reorders ids, omits an item, or the batch provider errors, RenTR automatically retries the
affected units through the existing single-unit path.

## Translation-memory boundary

Native batching is disabled when fuzzy memory suggestions are enabled. Sequential providers may
use a just-produced translation as a suggestion for the next unit, and batching must not silently
change that behavior. The current TranslateGemma hybrid path already disables fuzzy suggestions,
so it is eligible for native batching.

## CLI telemetry

`pilot-translate` now records:

- `llm_batch_size`
- `base_batch_calls`
- `base_batch_units`
- `base_batch_fallback_units`
- existing elapsed time / units-per-minute metrics

Start with batch size 5. If quality and structure remain stable, benchmark 8 or 10 before choosing
a production default for the full game.
