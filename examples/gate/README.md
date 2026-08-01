# `airs gate` — worked example

Enforcement, using the same two ESCI samples as `examples/probe/`. No agent, no
ground truth, no model call, no API key. Exit status 0 = admitted, 1 = refused.

## A healthy pipeline is admitted

```bash
python -m airsbench.gate --records examples/probe/healthy.jsonl \
    --source examples/probe/source.jsonl --policy examples/gate/retrieval.json
```

```
  freshness           100.0   mean age 0.40s over 60 of 60 records
  latency             100.0   mean 45ms over 60 of 60 records
  consistency         100.0   60 of 60 records matched by id
  semantic            100.0   context present on 60 of 60 records

  AIRS 100.0 over 100% of the calibrated weight

  ADMITTED — the batch satisfies every declared rule.
```

## A degraded one is refused before the agent is asked

```bash
python -m airsbench.gate --records examples/probe/degraded.jsonl \
    --source examples/probe/source.jsonl --policy examples/gate/retrieval.json
```

```
  ✗ min_dimension.consistency: consistency is 23.2, floor is 90
  ✗ min_dimension.semantic: semantic is 20.4, floor is 50

  REFUSED — the agent was not asked.
```

The refusal names the rule and the observed value. That is the whole point: a
refused batch is an operations problem with an owner, which is exactly what a
silent failure is not.

## "We did not look" is not "it is fine"

Drop `--source` and consistency becomes unmeasurable. A permissive gate would
admit; this one refuses, and says why:

```bash
python -m airsbench.gate --records examples/probe/degraded.jsonl \
    --policy examples/gate/retrieval.json
```

```
  ✗ min_dimension.consistency: consistency could not be measured,
      so the floor of 90 cannot be shown to hold
```

Set `"unmeasured_is_violation": false` only when a dimension is genuinely
inapplicable — never to quiet a check you have not wired up.

## Shadow mode — price a policy before enforcing it

```bash
python -m airsbench.gate --records examples/probe/degraded.jsonl \
    --source examples/probe/source.jsonl \
    --policy examples/gate/retrieval.json --shadow
```

Always admits, always exits 0, still reports every violation. Necessary because
a gate is not free: `docs/gate_findings.md` measures the cost at **7–21 correct
answers forfeited per silent failure genuinely prevented.**

## The two policies here

| file | rule | when |
|---|---|---|
| `retrieval.json` | consistency ≥ 90, semantic ≥ 50 | Retrieval-like tasks. Consistency carries 70% of the calibrated weight and is the cheapest gate measured (7.0). |
| `staleness-budget.json` | age ≤ 5.05 s | Classification-like tasks. The threshold is the one the freshness sweep located. **On retrieval this is close to a no-op with a real price** — see `docs/gate_findings.md` §2. |

Which one you want is a property of your task, not of your pipeline. The two
orderings invert (RQ5), so a policy copied from the other task family is worse
than no policy at all — it costs correct answers and prevents little.
