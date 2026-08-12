-- 01_indicators.sql — worldsim 统一采集库 · indicators 宽表（A1-min）
-- 对应 contracts.py:IndicatorPoint.to_row() 的 11 列展平；UNIQUE 五元组 = §6.2 身份键。
-- 只 INSERT，不 UPDATE/DELETE（契约层 to_row 语义：新 data_vintage = 新行，冲突走唯一约束拒/upsert）。
-- 执行：worldsim_app 角色（读写）；created_at 用 timestamptz 存 UTC aware（时区契约）。

CREATE TABLE IF NOT EXISTS indicators (
    indicator_key  VARCHAR(64)  NOT NULL,   -- snake_case 键，如 fci_revised
    as_of          DATE         NOT NULL,   -- 观测/决策日
    data_vintage   DATE         NOT NULL,   -- 上游数据新鲜度下界
    horizon        VARCHAR(8)   NOT NULL,   -- nowcast | \d+[DWMQY]
    value          DOUBLE PRECISION,         -- status=ok 时有限实数；否则 NULL
    ci_low         DOUBLE PRECISION,         -- 与 ci_high 成对出现
    ci_high        DOUBLE PRECISION,
    model_ver      VARCHAR(32)  NOT NULL,   -- 算法版本，如 fci-1.1 / probit-1.0
    created_at     TIMESTAMPTZ  NOT NULL,   -- 写入时间，必须 tz-aware（UTC）
    schema_version VARCHAR(8)   NOT NULL,   -- 契约形状版本，当前 "1.0"
    status         VARCHAR(16)  NOT NULL,   -- ok/missing/degraded/suppressed

    -- §6.2 UNIQUE(indicator_key, as_of, horizon, model_ver, data_vintage) = identity_key()
    CONSTRAINT uq_indicators_identity UNIQUE (indicator_key, as_of, horizon, model_ver, data_vintage)
);

-- 配套索引：按指标键 + 时间范围查询（日报/仪表盘/回测常用路径）
CREATE INDEX IF NOT EXISTS idx_indicators_key_asof
    ON indicators (indicator_key, as_of DESC);
