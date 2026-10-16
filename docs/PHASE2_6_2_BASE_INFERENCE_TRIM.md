# Phase 2.6.2 — Base Inference Trim + Safe Base Reuse

This phase does not batch multiple translations into one LLM output. The failed
native-batch experiment stays disabled in the recommended production settings.

## Fast path

For TranslateGemma, the base model does not consume narrative context. Therefore
an exact repeated protected source can safely reuse the same raw BASE inference.
RenTR still evaluates each occurrence independently afterward using its own
scene context. Risk analysis, semantic repair and candidate judging are not
shared.

This is deliberately different from blind final-translation deduplication.

## Per-call trimming

The single-line TranslateGemma prompt is compact and has a stable prefix. Normal
VN lines use `num_ctx=1024`; long lines fall back to 2048. `num_predict` scales
with source length and is clamped between 96 and 512.

## Recommended settings

- `--parallel-workers 1`
- `--llm-batch-size 1`
- keep model-grouped hybrid batches

Pilot JSON now reports `base_provider_calls` and `base_reused_units` so the gain
can be measured instead of inferred.
