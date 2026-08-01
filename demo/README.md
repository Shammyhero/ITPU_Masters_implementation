# AIST — Agentic Infrastructure Stress Test

Companion demo for *Detectability Determines Danger*. Next.js (App Router,
static export). **No API key, no model calls, no server at runtime.**

```bash
npm --prefix demo install
npm --prefix demo run data     # bake src/data/aist.json from results/runs/
npm --prefix demo run dev      # http://localhost:3000
npm --prefix demo run build    # static site in demo/out/
```

## Why the data is pre-baked

Every figure is exported from the 248 run artifacts by
`airsbench.analysis.export_demo_data` at build time, each carrying the run id
it came from. The page must open years from now, from a file server or GitHub
Pages, without the artifacts, a Python environment, or an API key — and archive
alongside the Zenodo DOI.

## The three-way panel

The Streamlit version this replaces was built around a two-way contrast: the
same stale record with and without its age, *one lying and one declining*.
**That contrast does not exist.** The detectability arm returned a null — both
lie, at confidence 1.00, on the same query. Columns 1 and 2 are real logged
decisions; column 3 is the recommendation the null implies, and is labelled as
not an experimental condition.

## Interactive, not just readable

Two panels are driven by the reader, which is what makes this a stress test
rather than a report:

- **Stress the pipeline** — pick a fault, drag severity, watch accuracy,
  abstention and silent failure move. Every stop is a *measured* condition with
  its own decision count; nothing is interpolated and nothing between two stops
  is claimed. AIRS is recomputed live from the dimension scores.
- **Probe your own pipeline** — paste your own JSONL and it is scored in the
  browser (`ProbeLive.tsx` is a port of `airsbench.probe`). Nothing is uploaded.
  Clearing the upstream box demonstrates the guard: consistency goes
  `UNMEASURED`, never 100.
