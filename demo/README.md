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
