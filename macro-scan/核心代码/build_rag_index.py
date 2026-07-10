"""
build_rag_index.py — 知识库向量索引构建脚本

通过 docker exec 运行：
    docker exec macro-scan-macro-scan-1 python /app/build_rag_index.py

Embedding 走硅基流动 BAAI/bge-m3，需 SILICONFLOW_API_KEY 环境变量。
知识库有重大更新时重新运行即可，会自动清空旧索引重建。
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
CHROMA_DIR = os.path.normpath(os.path.join(WORKSPACE, "data", "chroma_db"))  # /workspace/data/chroma_db


if __name__ == "__main__":
    print("=" * 60)
    print("世界推演系统 · RAG 知识库索引构建")
    print("=" * 60)
    print(f"知识库路径: {KB_DIR}")
    print(f"向量库路径: {CHROMA_DIR}")
    print(f"Embedding:  硅基流动 BAAI/bge-m3")
    print()

    # 1. 检查知识库
    if not os.path.exists(KB_DIR):
        print(f"✗ 知识库目录不存在: {KB_DIR}")
        sys.exit(1)

    # 2. 检查 chromadb
    try:
        import chromadb
        print(f"✓  chromadb {chromadb.__version__} 已安装")
    except ImportError:
        print("✗  chromadb 未安装，请先：pip install chromadb")
        sys.exit(1)

    # 3. 检查 SiliconFlow API key
    if not os.getenv("SILICONFLOW_API_KEY"):
        print("✗  SILICONFLOW_API_KEY 未设置")
        sys.exit(1)
    print("✓  SILICONFLOW_API_KEY 已配置")

    # 4. 建索引
    print("\n[1/2] 开始构建向量索引...")
    os.makedirs(CHROMA_DIR, exist_ok=True)

    from rag_engine import build_index
    t0 = time.time()
    count = build_index(KB_DIR, CHROMA_DIR, "")
    elapsed = time.time() - t0

    if count == 0:
        print("✗ 索引构建失败，未写入任何数据")
        sys.exit(1)

    # 5. 验证
    print("\n[3/3] 验证索引...")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection("macro_kb")
    stored = collection.count()
    print(f"  ✓  ChromaDB 共存储 {stored} 个向量块")

    print(f"\n✅ 完成！耗时 {elapsed:.0f}s，索引路径: {CHROMA_DIR}")
    print("   重启容器后推演系统将自动使用向量检索。")
