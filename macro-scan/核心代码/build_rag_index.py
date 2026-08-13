"""
build_rag_index.py — 知识库向量索引构建脚本（pgvector 后端，E0-B）

通过 docker exec 运行：
    docker exec macro-scan-macro-scan-1 python /app/build_rag_index.py

Embedding 走硅基流动 BAAI/bge-m3，需 SILICONFLOW_API_KEY 环境变量。
向量库为 worldsim-pg 的 rag.embeddings 表（pgvector）。知识库有重大更新时
重新运行即可，会自动 TRUNCATE + 原子重建。

E0-B（2026-08-13）：ChromaDB 已退役，本脚本不再依赖 chromadb，验证改为直查
worldsim-pg.rag.embeddings。
"""

import os
import sys
import time

# 路径与 run_macro_analysis.py 保持一致
# 容器内：OPENCLAW_WORKSPACE=/workspace；本地调试用脚本父级目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))       # /app（容器内）
WORKSPACE  = os.environ.get("OPENCLAW_WORKSPACE",
             os.path.dirname(SCRIPT_DIR))                      # /workspace 或本地父级
KB_DIR     = os.path.join(WORKSPACE, "知识库", "财经知识库")   # /workspace/知识库/财经知识库
COLLECTION_NAME = "macro_kb"


if __name__ == "__main__":
    print("=" * 60)
    print("世界推演系统 · RAG 知识库索引构建（pgvector 后端）")
    print("=" * 60)
    print(f"知识库路径: {KB_DIR}")
    print(f"向量库:     worldsim-pg.rag.embeddings（collection={COLLECTION_NAME}）")
    print(f"Embedding:  硅基流动 BAAI/bge-m3")
    print()

    # 1. 检查知识库
    if not os.path.exists(KB_DIR):
        print(f"✗ 知识库目录不存在: {KB_DIR}")
        sys.exit(1)

    # 2. 检查 psycopg（pgvector 后端驱动）
    try:
        import psycopg
        print("✓  psycopg 已安装（pgvector 后端）")
    except ImportError:
        print("✗  psycopg 未安装，无法写入 worldsim-pg")
        sys.exit(1)

    # 3. 检查 SiliconFlow API key
    if not os.getenv("SILICONFLOW_API_KEY"):
        print("✗  SILICONFLOW_API_KEY 未设置")
        sys.exit(1)
    print("✓  SILICONFLOW_API_KEY 已配置")

    # 4. 建索引（原子重建：TRUNCATE + INSERT 同事务）
    print("\n[1/2] 开始构建向量索引（pgvector）...")
    from rag_engine import build_index
    t0 = time.time()
    count = build_index(KB_DIR)
    elapsed = time.time() - t0

    if count == 0:
        print("✗ 索引构建失败，未写入任何数据")
        sys.exit(1)

    # 5. 验证（直查 worldsim-pg，不再依赖 chroma）
    print("\n[2/2] 验证索引（worldsim-pg.rag.embeddings）...")
    try:
        conn = psycopg.connect(
            host="worldsim-pg", port=5432, dbname="worldsim", user="worldsim_app",
            password=os.environ.get("WORLDSIM_APP_PW"),
            options="-c search_path=rag,public",
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM rag.embeddings WHERE collection_name=%s",
                (COLLECTION_NAME,),
            )
            stored = cur.fetchone()[0]
        conn.close()
        print(f"  ✓  rag.embeddings 共存储 {stored} 个向量块")
    except Exception as e:
        print(f"  ⚠  无法直连 worldsim-pg 验证（索引可能已写入，需容器侧复核）: {e}")

    print(f"\n✅ 完成！耗时 {elapsed:.0f}s，向量块入库: {count}")
    print("   容器推演系统将自动使用 pgvector 检索。")
