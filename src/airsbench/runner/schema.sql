-- Canonical benchmark results table: one row per experimental run
-- (research plan §4.2 step 5). This table IS the thesis dataset —
-- Prometheus is for live demo observability only, never the source of truth.

CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id            UUID PRIMARY KEY,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    git_sha           TEXT,

    -- independent variables (controlled)
    pipeline          TEXT NOT NULL CHECK (pipeline IN ('batch', 'streaming')),
    fault_type        TEXT NOT NULL CHECK (fault_type IN
                        ('none', 'freshness', 'latency', 'schema_drift', 'semantic_stripping')),
    -- 'sweep_<n>s' labels come from the freshness monotonicity sweep, which
    -- needs more than two levels to distinguish monotonic from non-monotonic
    -- response (Shisher & Sun, MobiHoc 2022).
    severity          TEXT NOT NULL CHECK (
                        severity IN ('none', 'mild', 'severe')
                        OR severity LIKE 'sweep\_%'),
    task              TEXT NOT NULL CHECK (task IN ('retrieval', 'classification')),
    replication       INT  NOT NULL,

    -- held constant (recorded for provenance)
    dataset           TEXT NOT NULL,
    model             TEXT NOT NULL,
    temperature       REAL NOT NULL,
    seed              INT  NOT NULL,
    n_queries         INT  NOT NULL,

    -- dependent variables (measured)
    accuracy          REAL,
    f1_score          REAL,
    auc_roc           REAL,
    latency_ms_p50    REAL,
    latency_ms_p95    REAL,

    -- AIRS components at run time
    airs_freshness    REAL,
    airs_latency      REAL,
    airs_consistency  REAL,
    airs_semantic     REAL,
    airs_total        REAL,

    -- full provenance
    config            JSONB NOT NULL,
    raw_output_path   TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_condition
    ON benchmark_runs (pipeline, fault_type, severity, task);
