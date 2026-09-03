"""
P0 Migration: 为 reasoning_trace 加 UNIQUE(prediction_id) 约束

执行方式（rebuild 后一次性运行）：
  docker exec macro-scan-tianji-1 python3 migrate_p0_unique_trace.py

幂等：重复运行安全（约束已存在则跳过）。
"""
import sys
from tianji_db import get_connection


def run():
    conn = get_connection()
    try:
        # Step 1: 检查重复数据
        dups = conn.execute("""
            SELECT prediction_id, COUNT(*) AS cnt
            FROM reasoning_trace
            GROUP BY prediction_id
            HAVING COUNT(*) > 1
        """).fetchall()

        if dups:
            print(f"[migrate] 发现 {len(dups)} 个 prediction_id 有重复 trace，去重中...")
            for dup in dups:
                pid = dup["prediction_id"]
                # 保留 ctid 最小的一行（最早写入），删除其余
                conn.execute("""
                    DELETE FROM reasoning_trace
                    WHERE prediction_id = %s
                      AND ctid NOT IN (
                          SELECT min(ctid)
                          FROM reasoning_trace
                          WHERE prediction_id = %s
                      )
                """, (pid, pid))
                print(f"  去重: prediction_id={pid}")
            conn.commit()
            print("[migrate] 去重完成")
        else:
            print("[migrate] reasoning_trace 无重复数据")

        # Step 2: 验证去重结果
        remaining = conn.execute("""
            SELECT COUNT(*) AS cnt FROM reasoning_trace
        """).fetchone()
        print(f"[migrate] reasoning_trace 当前行数: {remaining['cnt']}")

        # Step 3: 加 UNIQUE 约束
        conn.execute("""
            ALTER TABLE reasoning_trace
            ADD CONSTRAINT uq_reasoning_trace_prediction
            UNIQUE (prediction_id)
        """)
        conn.commit()
        print("[migrate] UNIQUE(prediction_id) 约束已加入 reasoning_trace")

    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "uq_reasoning_trace_prediction" in msg:
            print(f"[migrate] 约束已存在，跳过: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        else:
            print(f"[migrate] 失败: {e}", file=sys.stderr)
            try:
                conn.rollback()
            except Exception:
                pass
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("[migrate] P0: reasoning_trace UNIQUE 约束迁移")
    run()
    print("[migrate] 完成")
