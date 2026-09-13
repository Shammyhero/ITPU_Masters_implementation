# The AIRS console — web source

The browser half of `airs serve`, and the companion argument for *Detectability
Determines Danger*. Next.js (App Router, static export), served from the Python
package by `airs serve`. **No API key and no model calls.**

| Route | Page |
|---|---|
| `/` | **Check my pipeline** — paste or drop a sample of records as the pipeline delivers them. Every number shown comes back from `/api/score`, which runs `airsbench.probe` on the same machine. |
| `/evidence/` | **Why trust the score** — the argument below, pre-baked from the benchmark runs. It needs no server and opens from any static file host. |

```bash
make web                        # from the repo root: build into src/airsbench/web/, where airs serve
                                # and the wheel pick it up
npm --prefix demo install
npm --prefix demo run dev       # http://localhost:3000 — run `airs serve --dev` beside it for the API
npm --prefix demo run data      # re-bake src/data/aist.json from results/runs/ (needs data/ecommerce)
```

In development, `.env.development` points the page at `airs serve --dev` on
:8000, whose `--dev` flag admits the :3000 origin. A production build leaves
`NEXT_PUBLIC_API_BASE` unset, so the exported page calls whichever server served it.

> ⚠️ Do not run `next build` while `next dev` is running — they share `.next/`
> and the dev server will 500 with `__webpack_modules__[moduleId] is not a
> function`. `make web` refuses to build while `next dev` runs.

## Why the page computes no score

The first version of Act 4 scored pasted records in TypeScript. By the time it
was reviewed, that port already disagreed with `airs probe` — nested payloads
compared by key order, clock skew scored instead of refused — and no test could
see it. So the scoring rules exist once, in Python. `src/lib/api.ts` describes
what the API returns and computes nothing.

## The evidence page is an argument, not a dashboard

Four acts that build one claim, then an appendix for readers who want to poke at
the data. Each act asks the reader to *do* something, because the finding is
much more convincing when you walk into it yourself than when you read it as a
statistic.

| | | |
|---|---|---|
| **Act 1** | *You be the agent* | A real query and the real catalog records an agent was served. Pick the cheapest in-stock product. You pick what the agent picked, and you are both wrong — the catalog was 5.05 s behind the world and nothing in the record says so. |
| **Act 2** | *Could you have known?* | The same record under four faults. Judge each by eye, then see how often the agent declined. Your instinct and its abstention rate are the same ordering — 1%, 0%, 1%, **18%**. That is the thesis title, earned. |
| **Act 3** | *So ask the agent how sure it is* | The obvious defence, measured. Guess how well its confidence predicts its own silent failures, then meet **0.501**. |
| **Act 4** | *So measure the pipeline instead* | If the consumer cannot tell you when it is failing, score what you feed it — a link to `/`, where you score your own records. |

Appendix: a severity dial over real measured conditions, and the cross-model
ranking table.

## Why the evidence is pre-baked

Every figure is exported from the run artifacts by
`airsbench.analysis.export_demo_data`, each tagged with the run id it came from,
into `src/data/aist.json` — which is committed, so a clone builds the console
without the datasets. Act 1's cases are *reconstructed exactly* — `sample_seed`
regenerates the query and its timestamp, and the catalog time machine replays
the update stream to recover both the served and the true state. The page must
open years from now, from a file server, without the artifacts or a Python
environment, and archive alongside the Zenodo DOI. Some panels are still
hand-typed constants rather than generated; replacing them is scheduled in W5
(`docs/plan.md`).

## What this replaces

A Streamlit app built around a two-way contrast — the same stale record with
and without its age, *one lying and one declining*. **That contrast does not
exist:** the detectability arm returned a null, and both lie at confidence 1.00.
Act 1 shows the lie; Act 3 shows why you cannot ask the agent about it.
