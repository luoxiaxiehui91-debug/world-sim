
-- news schema ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS news AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA news TO worldsim_app;

CREATE TABLE IF NOT EXISTS news.scan_contexts (
    id              BIGSERIAL PRIMARY KEY,
    scan_time       TIMESTAMPTZ,
    vix             DOUBLE PRECISION,
    t10y2y          DOUBLE PRECISION,
    baa10y          DOUBLE PRECISION,
    dff             DOUBLE PRECISION,
    regime          TEXT,
    vix_regime      TEXT,
    data_quality    TEXT
);

CREATE TABLE IF NOT EXISTS news.articles (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT,
    content_hash    TEXT,
    title           TEXT,
    source          TEXT,
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ,
    country_tag     TEXT,
    ingest_ctx_id   BIGINT,
    pub_ctx_id      BIGINT
);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON news.articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON news.articles (source);
CREATE UNIQUE INDEX IF NOT EXISTS news_uq_articles_hash ON news.articles (content_hash) WHERE content_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS news_uq_articles_url ON news.articles (url) WHERE url IS NOT NULL;

CREATE TABLE IF NOT EXISTS news.article_categories (
    article_id      BIGINT NOT NULL,
    category        TEXT NOT NULL,
    PRIMARY KEY (article_id, category)
);
CREATE INDEX IF NOT EXISTS idx_article_categories_category ON news.article_categories (category);

CREATE TABLE IF NOT EXISTS news.signal_episodes (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT,
    triggered_at    TIMESTAMPTZ,
    ratio           DOUBLE PRECISION,
    level           TEXT,
    scan_ctx_id     BIGINT
);
CREATE INDEX IF NOT EXISTS idx_signal_episodes_triggered ON news.signal_episodes (triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_episodes_category ON news.signal_episodes (category);

CREATE TABLE IF NOT EXISTS news.episode_articles (
    episode_id      BIGINT NOT NULL,
    article_id      BIGINT NOT NULL,
    PRIMARY KEY (episode_id, article_id)
);

CREATE TABLE IF NOT EXISTS news.signal_outcomes (
    id              BIGSERIAL PRIMARY KEY,
    episode_id      BIGINT,
    check_date      TIMESTAMPTZ,
    check_horizon   TEXT,
    spx_return      DOUBLE PRECISION,
    dgs10_change    DOUBLE PRECISION,
    vix_change      DOUBLE PRECISION,
    usdx_change     DOUBLE PRECISION,
    outcome_regime  TEXT
);

CREATE TABLE IF NOT EXISTS news.synthesis_log (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         TEXT,
    triggered_at    TIMESTAMPTZ,
    scan_ctx_id     BIGINT,
    trigger_summary TEXT,
    hypothesis_text TEXT,
    llm_success     INTEGER,
    ntfy_success    INTEGER,
    suppress_reason TEXT,
    report_excerpt  TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_synthesis_log_triggered ON news.synthesis_log (triggered_at DESC);

-- forecast schema --------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS forecast AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA forecast TO worldsim_app;

CREATE TABLE IF NOT EXISTS forecast.forecasts (
    id                  TEXT PRIMARY KEY,
    created_at          TIMESTAMPTZ,
    scenario            TEXT,
    horizon_months      INTEGER,
    verify_after        TIMESTAMPTZ,
    country             TEXT,
    status              TEXT,
    regime              TEXT,
    stress_signals      INTEGER,
    prob_recession      DOUBLE PRECISION,
    prob_deep_recession DOUBLE PRECISION,
    prob_soft_landing   DOUBLE PRECISION,
    prob_stagflation    DOUBLE PRECISION,
    prob_crisis_vix     DOUBLE PRECISION,
    gdp_p10             DOUBLE PRECISION,
    gdp_p50             DOUBLE PRECISION,
    gdp_p90             DOUBLE PRECISION,
    unrate_p50          DOUBLE PRECISION,
    cpi_yoy_p50         DOUBLE PRECISION,
    input_json          TEXT,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS forecast.actuals (
    period          TEXT PRIMARY KEY,
    actual_regime   TEXT,
    gdp_growth      DOUBLE PRECISION,
    unemployment    DOUBLE PRECISION,
    cpi_yoy         DOUBLE PRECISION,
    labeled_at      TIMESTAMPTZ,
    label_source    TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS forecast.evaluations (
    id                  BIGSERIAL PRIMARY KEY,
    eval_date           TIMESTAMPTZ,
    horizon_months      INTEGER,
    n_samples           INTEGER,
    brier_score         DOUBLE PRECISION,
    brier_skill         DOUBLE PRECISION,
    recession_brier     DOUBLE PRECISION,
    soft_landing_brier  DOUBLE PRECISION,
    notes               TEXT
);

-- tianji schema ----------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS tianji AUTHORIZATION worldsim_app;
GRANT ALL ON SCHEMA tianji TO worldsim_app;

CREATE TABLE IF NOT EXISTS tianji.predictions (
    id                      TEXT PRIMARY KEY,
    created_at              TIMESTAMPTZ,
    due_at                  TIMESTAMPTZ,
    scenario_id             TEXT,
    type                    TEXT,
    prediction_target_type  TEXT,
    content                 TEXT,
    outcome_definition      TEXT,
    target_metric           TEXT,
    target_direction        TEXT,
    target_threshold        DOUBLE PRECISION,
    b_prob                  DOUBLE PRECISION,
    b_sample_count          INTEGER,
    b_max_similarity        DOUBLE PRECISION,
    llm_adj                 DOUBLE PRECISION,
    final_prob              DOUBLE PRECISION,
    prob_low                DOUBLE PRECISION,
    prob_high               DOUBLE PRECISION,
    confidence_tier         TEXT,
    time_horizon            TEXT,
    status                  TEXT,
    outcome_value           DOUBLE PRECISION,
    brier_score             DOUBLE PRECISION,
    brier_skill_score       DOUBLE PRECISION,
    verified_at             TIMESTAMPTZ,
    verified_by             TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.reasoning_trace (
    id                  BIGSERIAL PRIMARY KEY,
    prediction_id       TEXT,
    agent_id            TEXT,
    input_signals       TEXT,
    historical_match    TEXT,
    confidence_basis    TEXT,
    llm_adjustment      DOUBLE PRECISION,
    causal_chains       TEXT,
    reasoning           TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.weight_update_log (
    id                  BIGSERIAL PRIMARY KEY,
    updated_at          TIMESTAMPTZ,
    prediction_id       TEXT,
    signal_name         TEXT,
    target_type         TEXT,
    weight_before       DOUBLE PRECISION,
    weight_after        DOUBLE PRECISION,
    reason              TEXT,
    notes               TEXT,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());

CREATE TABLE IF NOT EXISTS tianji.narrative_chunks (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT,
    source_type         TEXT,
    primary_dimension   TEXT,
    secondary_dimension TEXT,
    timestamp           TIMESTAMPTZ,
    content             TEXT,
    token_count         INTEGER,
    staleness_tau       INTEGER,
    embedding           BYTEA,
    created_at          TIMESTAMPTZ,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_narrative_chunks_dim ON tianji.narrative_chunks (primary_dimension, secondary_dimension);

CREATE TABLE IF NOT EXISTS tianji.narrative_density_flags (
    dimension       TEXT PRIMARY KEY,
    flagged_at      TIMESTAMPTZ,
    z_score         DOUBLE PRECISION,
    consumed        INTEGER,
    pg_synced_at    TIMESTAMPTZ DEFAULT now());
