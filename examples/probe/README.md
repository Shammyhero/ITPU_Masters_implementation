# `airs probe` — worked example

Two samples drawn from the real ESCI catalog, scored with no agent and no model
calls. Regenerate with `python -m airsbench.probe --help` for the input schema.

| file | what it is |
|---|---|
| `source.jsonl` | the records as they exist upstream — the consistency reference |
| `healthy.jsonl` | delivered fresh (0.4 s), fast (45 ms), intact |
| `degraded.jsonl` | delivered stale (6.5 s), slow (1800 ms), 25% schema drift, 80% semantic stripping |

```bash
python -m airsbench.probe --records examples/probe/healthy.jsonl \
    --source examples/probe/source.jsonl --task retrieval     # AIRS 100.0  READY
python -m airsbench.probe --records examples/probe/degraded.jsonl \
    --source examples/probe/source.jsonl --task retrieval     # AIRS  21.7  AT RISK
```

Drop `--source` on the degraded sample to see the honesty guard: consistency
becomes `UNMEASURED` (not 100), and the report warns that the composite now
rests on 30% of the calibrated weight.
