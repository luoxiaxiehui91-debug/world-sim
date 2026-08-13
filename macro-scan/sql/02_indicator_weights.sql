-- 02_indicator_weights.sql — world-sim 天枢 · C0 加权派生权重表
--
-- 设计（用户拍板方向 A）：
--   grain = (source_id, target_type)
--   source_id    = FRED 序列 id（如 'DGS10'，model_ver='fred-DGS10'）
--   target_type  = GRV 11 维（合法 target_type 词表，取自 source_dimension_map.yaml
--                 primary 集合）：global_composite / japan_monetary / us_china_strategic /
--                 energy_grid_risk / climate_risk / russia_europe / taiwan_strait 等
--   权重由 FRED 数据派生（逆滚动波动率 / 变异系数），经玉衡原生 grain 双写：
--     - indicator_weights（PG 权威表）
--     - grv_weights.yaml 的 weights 子树（由 c0_compute_weights.py 同步）
--
-- 与 c0_compute_weights.py 内嵌的 DDL 保持一致（脚本用它做幂等建表）。
-- 沿用 01_indicators.sql 的 IF NOT EXISTS 惯例。

CREATE TABLE IF NOT EXISTS indicator_weights (
  source_id      VARCHAR(64)  NOT NULL,
  target_type    VARCHAR(64)  NOT NULL,
  weight         DOUBLE PRECISION NOT NULL,
  weight_min     DOUBLE PRECISION NOT NULL DEFAULT 0.05,
  weight_max     DOUBLE PRECISION NOT NULL DEFAULT 5.00,
  effective_from DATE         NOT NULL DEFAULT CURRENT_DATE,
  approved_by    VARCHAR(64),
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
  PRIMARY KEY (source_id, target_type),
  CHECK (weight BETWEEN weight_min AND weight_max)
);

-- 按 target_type 反查派生权重（get_weights_for_target 的 PG 侧等价）
CREATE INDEX IF NOT EXISTS idx_indicator_weights_target
  ON indicator_weights (target_type);
