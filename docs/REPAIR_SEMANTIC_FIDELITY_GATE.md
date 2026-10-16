# Repair Semantic Fidelity Gate

Phase 2.5.3 closes the Hybrid v3 escape hatch discovered by the deterministic 10-line ORS smoke test.

The failure mode was:

1. BASE failed technical Ren'Py QC.
2. REPAIR passed technical QC.
3. The selector accepted REPAIR without a semantic judge call because there was no technically valid BASE candidate.
4. A repair could therefore copy/continue scene context into the current line while still looking technically valid.

The new rule is fail-closed:

- A technically invalid BASE can never be selected.
- A technically valid REPAIR is not enough by itself.
- When a judge provider exists, REPAIR must pass a source-fidelity judge gate with decision `repair` and confidence >= 0.85.
- The judge request marks BASE with `base_technical_qc_failed` and REPAIR with `source_only_fidelity_required`.
- `base`, `reject`, low-confidence `repair`, or an unavailable judge all reject the unit because there is no safe fallback candidate.
- If no judge provider is configured, technical-recovery repair is rejected instead of being silently trusted.

This gate is deliberately narrow. It adds an extra judge call only to units where BASE already failed technical QC and REPAIR survived technical + hard semantic checks. Normal clean BASE translations and ordinary pairwise selection are unchanged.

## Regression target

The ORS smoke-test source:

`I was letting myself get dragged into this. I had to keep my cool, I had to-{w=0.5}{nw}`

must no longer accept a repair that invents scene details such as Axel, pushing, or a body position that are absent from the current source line.
