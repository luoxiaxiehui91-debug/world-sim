"""
migrate_p1_calibration_versions.py
====================================
P1 迁移：添加 calibration_versions 表 + predictions FK + 回填历史预测。

运行方式（每次 rebuild 后一次性执行，幂等）：
  docker cp migrate_p1_calibration_versions.py macro-scan-tianji-1:/tmp/
  docker exec macro-scan-tianji-1 python3 /tmp/migrate_p1_calibration_versions.py

环境要求：
  - WORLDSIM_APP_PW 已注入（容器内通常已有）
  - psycopg 3.x 已安装

幂等保证：
  - CREATE TABLE / INDEX 用 IF NOT EXISTS
  - ALTER TABLE 前检查 information_schema
  - INSERT 用 ON CONFLICT (version_tag) DO NOTHING（需 UNIQUE(version_tag) 约束）
  - UPDATE 只回填 IS NULL 行
"""

import os
import sys
import psycopg
from psycopg.rows import dict_row


def get_connection():
    pw = os.environ.get("WORLDSIM_APP_PW")
    if not pw:
        print("[ERROR] 环境变量 WORLDSIM_APP_PW 未设置，脚本终止。")
        sys.exit(1)
    return psycopg.connect(
        host="worldsim-pg",
        port=5432,
        dbname="worldsim",
        user="worldsim_app",
        password=pw,
        row_factory=dict_row,
        options="-c search_path=tianji,public",
    )


def run_migration():
    print("=" * 60)
    print("P1 迁移：calibration_versions 表 + 历史预测回填")
    print("=" * 60)

    with get_connection() as conn:
        with conn.cursor() as cur:

            # ------------------------------------------------------------------
            # Step 1: CREATE TABLE calibration_versions
            # UNIQUE(version_tag) 确保 ON CONFLICT(version_tag) 幂等有效。
            # ------------------------------------------------------------------
            print("\n[Step 1] 创建 calibration_versions 表（如不存在）...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calibration_versions (
                    id              SERIAL      PRIMARY KEY,
                    version_tag     TEXT        NOT NULL UNIQUE,
                    params_snapshot JSONB,
                    is_active       BOOLEAN     NOT NULL DEFAULT FALSE,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    notes           TEXT
                )
            """)
            conn.commit()
            print("    OK — calibration_versions 表已就绪。")

            # ------------------------------------------------------------------
            # Step 2: 唯一活跃版本索引（partial unique：只限 is_active=TRUE）
            # ------------------------------------------------------------------
            print("\n[Step 2] 创建唯一索引 uq_calibration_versions_active（如不存在）...")
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_calibration_versions_active
                    ON calibration_versions (is_active)
                    WHERE (is_active = TRUE)
            """)
            conn.commit()
            print("    OK — 唯一活跃版本索引已就绪。")

            # ------------------------------------------------------------------
            # Step 3: ALTER TABLE predictions ADD COLUMN calibration_version_id
            # ------------------------------------------------------------------
            print("\n[Step 3] 检查并添加 predictions.calibration_version_id 列...")
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'tianji'
                  AND table_name   = 'predictions'
                  AND column_name  = 'calibration_version_id'
            """)
            if cur.fetchone():
                print("    SKIP — 列已存在，跳过 ALTER TABLE。")
            else:
                cur.execute("""
                    ALTER TABLE predictions
                        ADD COLUMN calibration_version_id INTEGER
                            REFERENCES calibration_versions(id)
                """)
                conn.commit()
                print("    OK — calibration_version_id 列已添加（nullable FK）。")

            # ------------------------------------------------------------------
            # Step 4: INSERT baseline v0-baseline（UNIQUE(version_tag) 保障幂等）
            # ------------------------------------------------------------------
            print("\n[Step 4] 插入基线版本 'v0-baseline'（如不存在）...")
            cur.execute("""
                INSERT INTO calibration_versions
                    (version_tag, params_snapshot, is_active, notes)
                VALUES (
                    'v0-baseline',
                    '{}'::jsonb,
                    TRUE,
                    'P1 初始版本：回填历史预测。权重更新日志为空，无历史校准事件。'
                )
                ON CONFLICT (version_tag) DO NOTHING
            """)
            inserted = cur.rowcount
            conn.commit()
            if inserted > 0:
                print("    OK — v0-baseline 已插入。")
            else:
                print("    SKIP — v0-baseline 已存在，无需重复插入。")

            cur.execute("SELECT id FROM calibration_versions WHERE version_tag = 'v0-baseline'")
            row = cur.fetchone()
            if not row:
                print("[ERROR] 无法找到 v0-baseline 记录，迁移中止。")
                sys.exit(1)
            baseline_id = row["id"]
            print(f"    baseline id = {baseline_id}")

            # ------------------------------------------------------------------
            # Step 5: 回填 NULL 行（仅 IS NULL，不覆盖已赋值的行）
            # ------------------------------------------------------------------
            print("\n[Step 5] 回填历史预测 calibration_version_id...")
            cur.execute("""
                SELECT COUNT(*) AS cnt FROM predictions
                WHERE calibration_version_id IS NULL
            """)
            null_count = cur.fetchone()["cnt"]
            print(f"    待回填行数：{null_count}")

            if null_count > 0:
                cur.execute("""
                    UPDATE predictions
                    SET calibration_version_id = %s
                    WHERE calibration_version_id IS NULL
                """, (baseline_id,))
                updated = cur.rowcount
                conn.commit()
                print(f"    OK — 已更新 {updated} 行。")
            else:
                print("    SKIP — 所有行已有 calibration_version_id，无需回填。")

            # 汇总
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM predictions WHERE calibration_version_id = %s",
                (baseline_id,),
            )
            total_assigned = cur.fetchone()["cnt"]
            print("\n" + "=" * 60)
            print("迁移完成。")
            print(f"  calibration_versions 行数：1（v0-baseline, id={baseline_id}）")
            print(f"  predictions 已绑定至 v0-baseline：{total_assigned} 行")
            print("=" * 60)


if __name__ == "__main__":
    run_migration()
