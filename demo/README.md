# AIST — Agentic Infrastructure Stress Test

Companion demo for *Detectability Determines Danger*. Next.js (App Router,
static export). **No API key, no model calls, no server at runtime.**

```bash
npm --prefix demo install
npm --prefix demo run data     # bake src/data/aist.json from results/runs/
npm --prefix demo run dev      # http://localhost:3000
npm --prefix demo run build    # static site in demo/out/
```

> ⚠️ Do not run `next build` while `next dev` is running — they share `.next/`
> and the dev server will 500 with `__webpack_modules__[moduleId] is not a
> function`. Stop the dev server and `rm -rf .next` first.

## It is an argument, not a dashboard

The page is four acts that build one claim, then an appendix for readers who
want to poke at the data. Each act asks the reader to *do* something, because
the finding is much more convincing when you walk into it yourself than when
you read it as a statistic.

| | | |
|---|---|---|
| **Act 1** | *You be the agent* | A real query and the real catalog records an agent was served. Pick the cheapest in-stock product. You pick what the agent picked, and you are both wrong — the catalog was 5.05 s behind the world and nothing in the record says so. |
| **Act 2** | *Could you have known?* | The same record under four faults. Judge each by eye, then see how often the agent declined. Your instinct and its abstention rate are the same ordering — 1%, 0%, 1%, **18%**. That is the thesis title, earned. |
| **Act 3** | *So ask the agent how sure it is* | The obvious defence, measured. Guess how well its confidence predicts its own silent failures, then meet **0.501**. |
| **Act 4** | *Probe your own pipeline* | Paste your own JSONL; scored in-browser. Clear the upstream box and consistency goes `UNMEASURED`, never 100. |

Appendix: a severity dial over real measured conditions, and the cross-model
ranking table.

## Why the data is pre-baked

Every figure is exported from the run artifacts by
`airsbench.analysis.export_demo_data` at build time, each tagged with the run
id it came from. Act 1's cases are *reconstructed exactly* — `sample_seed`
regenerates the query and its timestamp, and the catalog time machine replays
the update stream to recover both the served and the true state. The page must
open years from now, from a file server, without the artifacts or a Python
environment, and archive alongside the Zenodo DOI.

## What this replaces

A Streamlit app built around a two-way contrast — the same stale record with
and without its age, *one lying and one declining*. **That contrast does not
exist:** the detectability arm returned a null, and both lie at confidence 1.00.
Act 1 shows the lie; Act 3 shows why you cannot ask the agent about it.
