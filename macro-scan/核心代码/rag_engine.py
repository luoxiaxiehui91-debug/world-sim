"""
rag_engine.py — 向量检索引擎（pgvector + SiliconFlow bge-m3 embeddings）

对外接口：
    rag_query_vec(query, n_results, chroma_dir=None) -> List[str]   # chroma_dir 为兼容形参，已弃用（忽略）
    build_index(kb_dir, chroma_dir=None, _unused="") -> int          # 同上

依赖：psycopg 3.x（macro-scan 镜像 v8 已装）；向量库为 worldsim-pg rag schema（pgvector）。

E0-B（2026-08-13）：ChromaDB 后端正式退役。RAG_BACKEND 开关、全部 chroma 分支、
chroma 连接缓存已从本模块移除，读路径统一只读 worldsim-pg（D0 已独立验证正确）。
chroma_dir / _unused 形参仅作历史兼容保留，调用方传入将被忽略。
"""

import os
import json
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import psycopg
except ImportError:
    psycopg = None

COLLECTION_NAME = "macro_kb"
EMBED_MODEL     = os.environ.get("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")
SILICONFLOW_EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
CHUNK_SIZE      = 600
CHUNK_OVERLAP   = 150
MIN_CHUNK_LEN   = 80
SCORE_THRESHOLD = 0.5   # cosine distance；越小越相似，超过此值丢弃

# pgvector 连接（mirror b0_migrate.py）
_PG_HOST = "worldsim-pg"
_PG_PORT = 5432
_PG_DB = "worldsim"
_PG_USER = "worldsim_app"

SKIP_FILES   = {"README.md", "readme.md", "数据字典.md"}
SKIP_PREFIX  = ("00_知识库", "00_快速参考", "README")
SKIP_DIRS    = {"_update_tmp", "__pycache__", "_raw", "07_分析报告"}

_RAG_FAIL_COUNT = 0  # C9 静默降级致盲修复：PG 查询失败计数


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_embedding(text: str) -> Optional[List[float]]:
    """调用 SiliconFlow /v1/embeddings 获取单条向量。失败返回 None。"""
    results = _get_embeddings_batch([text])
    return results[0] if results else None


def _get_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """批量获取向量，一次 API 调用处理多条文本。失败返回空列表。
    08-16：优先走 llm_usage 配置（rag_embedding 使用点——平台/模型/API key
    开阳控制台可改），未配置 fallback env SILICONFLOW_API_KEY + 常量。"""
    embed_url = SILICONFLOW_EMBED_URL
    embed_model = EMBED_MODEL
    try:
        from llm_usage import get_secret
        api_key = get_secret("SILICONFLOW_API_KEY") or ""
    except Exception:
        api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    try:
        from llm_usage import resolve_embedding
        r = resolve_embedding()
        if r and r.get("embed_url"):
            embed_url = r["embed_url"]
            embed_model = r.get("model") or embed_model
            if r.get("api_key"):
                api_key = r["api_key"]
    except Exception:
        pass
    if not api_key:
        print("    [RAG] SILICONFLOW_API_KEY 未设置，跳过向量检索")
        return []
    payload = json.dumps({"model": embed_model, "input": texts, "encoding_format": "float"}).encode("utf-8")
    req = urllib.request.Request(
        embed_url,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            # 按 index 排序确保顺序正确
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]
    except Exception as e:
        print(f"    [RAG] batch embedding 失败: {e}")
        return []


def _chunk_text(text: str) -> List[str]:
    """
    分块：按段落（\\n\\n）聚合到 CHUNK_SIZE；单段超长时才字符切分（带重叠）。
    保持 Markdown 表格、列表等结构化内容在同一块内，避免从句子/行中间截断。
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
        else:
            if len(current) >= MIN_CHUNK_LEN:
                chunks.append(current)
            if len(para) > CHUNK_SIZE:
                # 单段超长 → 字符切分兜底
                start = 0
                while start < len(para):
                    c = para[start: start + CHUNK_SIZE]
                    if len(c) >= MIN_CHUNK_LEN:
                        chunks.append(c)
                    start += CHUNK_SIZE - CHUNK_OVERLAP
                current = ""
            else:
                current = para

    if len(current) >= MIN_CHUNK_LEN:
        chunks.append(current)
    return chunks


def _load_kb_docs(kb_dir: str) -> Tuple[List[str], List[dict]]:
    """
    递归扫描知识库目录，返回 (chunks, metadatas)。
    跳过 _update_tmp、_raw、README 等低价值内容。
    """
    all_chunks, all_metas = [], []
    for root, dirs, files in os.walk(kb_dir):
        # 跳过无用目录
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = os.path.relpath(root, kb_dir)

        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname in SKIP_FILES:
                continue
            if any(fname.startswith(p) for p in SKIP_PREFIX):
                continue

            fpath = os.path.join(root, fname)
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="ignore").strip()
                if len(content) < 200:
                    continue
                rel_path = os.path.join(rel_root, fname).replace("\\", "/")
                for i, chunk in enumerate(_chunk_text(content)):
                    all_chunks.append(chunk)
                    all_metas.append({"source": rel_path, "chunk": i})
            except Exception:
                pass

    return all_chunks, all_metas


def _get_pg_conn():
    """返回 worldsim-pg 连接（rag schema 优先）。psycopg 未装时抛错。"""
    if psycopg is None:
        raise RuntimeError("psycopg 未安装，无法使用 pgvector 后端")
    return psycopg.connect(
        host=_PG_HOST, port=_PG_PORT, dbname=_PG_DB, user=_PG_USER,
        password=os.environ.get("WORLDSIM_APP_PW"),
        options="-c search_path=rag,public",
    )


def _vec_str(emb) -> str:
    """numpy array / list → json string for `::vector` cast (容器未装 pgvector 包)。"""
    if hasattr(emb, "tolist"):
        emb = emb.tolist()
    return json.dumps([float(x) for x in emb])


# ── 建索引 ────────────────────────────────────────────────────────────────────

def build_index(kb_dir: str, chroma_dir: str = None, _unused: str = "") -> int:
    """
    从 kb_dir 读取所有 .md 文件，向量化后存入 worldsim-pg rag.embeddings（pgvector）。
    返回入库的文本块数量。每次调用会清空旧索引重建（TRUNCATE + INSERT 同事务，
    原子重建，杜绝旧毁新残）。chroma_dir / _unused 仅为历史兼容形参，已弃用，忽略。
    """
    print(f"[RAG] 扫描知识库: {kb_dir}")
    chunks, metas = _load_kb_docs(kb_dir)
    print(f"[RAG] 共 {len(chunks)} 个文本块，开始向量化（硅基流动 {EMBED_MODEL}）...")
    return _build_index_pg(chunks, metas)


def _build_index_pg(chunks, metas):
    """PG 原子重建：TRUNCATE + INSERT 同事务（C6 修复，杜绝旧毁新残）。"""
    BATCH = 50
    ok_count = 0
    try:
        with _get_pg_conn() as pg:
            with pg.transaction():
                with pg.cursor() as cur:
                    cur.execute(
                        "TRUNCATE rag.embeddings WHERE collection_name = %s",
                        (COLLECTION_NAME,),
                    )
                    for batch_start in range(0, len(chunks), BATCH):
                        bchs = chunks[batch_start: batch_start + BATCH]
                        bmet = metas[batch_start: batch_start + BATCH]
                        embeddings = _get_embeddings_batch(bchs)
                        if not embeddings:
                            continue
                        for i, (chunk, meta, emb) in enumerate(zip(bchs, bmet, embeddings)):
                            if emb is None:
                                continue
                            gi = batch_start + i
                            cur.execute(
                                """INSERT INTO rag.embeddings
                                      (collection_name, id, document, metadata, embedding)
                                   VALUES (%s, %s, %s, %s::jsonb, %s::vector)""",
                                (COLLECTION_NAME, f"c{gi}", chunk,
                                 json.dumps(meta), _vec_str(emb)),
                            )
                            ok_count += 1
                        print(f"  [{ok_count}/{len(chunks)}] 已入库...")
    except Exception as e:
        print(f"  [RAG] PG 建索引失败（事务已回滚）: {e}")
        return 0
    print(f"[RAG] PG 索引完成：{ok_count} 块入库，跳过 {len(chunks)-ok_count} 块（embedding失败）")
    return ok_count


# ── 查询 ──────────────────────────────────────────────────────────────────────

def rag_query_vec(query: str, n_results: int = 5,
                  chroma_dir: str = None) -> List[str]:
    """
    用向量相似度检索知识库（pgvector 后端）。
    返回格式与 TF-IDF rag_query() 相同：List["【文件名】\n片段"]。
    索引不存在或 embedding 失败时返回空列表，由 TF-IDF 兜底。
    chroma_dir 仅为历史兼容形参，已弃用，忽略。
    """
    query_emb = _get_embedding(query)
    if query_emb is None:
        return []
    return _rag_query_pg(query_emb, n_results)


def _rag_query_pg(query_emb, n_results):
    # pgvector 查询（cosine `<=>`），失败计数后转 TF-IDF（C9 静默降级致盲修复）
    global _RAG_FAIL_COUNT
    try:
        with _get_pg_conn() as pg:
            with pg.cursor() as cur:
                cur.execute(
                    """SELECT document, metadata->>'source' AS source,
                              embedding <=> %s::vector AS dist
                       FROM rag.embeddings
                       WHERE collection_name = %s
                       ORDER BY embedding <=> %s::vector, id
                       LIMIT %s""",
                    (_vec_str(query_emb), COLLECTION_NAME, _vec_str(query_emb), n_results),
                )
                rows = cur.fetchall()
    except Exception as e:
        _RAG_FAIL_COUNT += 1
        print(f"  [RAG] PG 向量检索失败 (累计 {_RAG_FAIL_COUNT} 次): {e}")
        return []

    results = []
    for doc, source, dist in rows:
        if dist > SCORE_THRESHOLD:
            continue
        results.append(f"【{source or 'unknown'}】\n{doc.strip()}")
        if len(results) >= n_results:
            break

    print(f"  [RAG-VEC-PG] 检索到 {len(results)} 个相关段落（距离阈值 {SCORE_THRESHOLD}）")
    return results

# ── 统一入口（向量优先 + TF-IDF fallback） ────────────────────────────────────

_TFIDF_CACHE: dict = {"vectorizer": None, "matrix": None, "docs": None,
                      "doc_names": None, "dir_hash": None}

SKIP_DIRS_TFIDF = SKIP_DIRS  # 复用同一排除集（含 07_分析报告）


def _kb_dir_hash(kb_dir: str) -> str:
    """计算知识库目录内容哈希，用于 TF-IDF 缓存失效检测。"""
    import hashlib
    h = hashlib.md5()
    for root, dirs, files in os.walk(kb_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS_TFIDF)
        for fname in sorted(files):
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                try:
                    h.update(str(os.path.getmtime(fpath)).encode())
                    h.update(fname.encode())
                except OSError:
                    pass
    return h.hexdigest()


def rag_query(query: str, n_results: int = 5,
              kb_dir: str = None,
              chroma_dir: str = None) -> List[str]:
    """
    统一 RAG 入口：向量检索优先（pgvector + SiliconFlow bge-m3），
    不可用或无结果时降级 TF-IDF。
    RAG 返回为空时打印警告，便于区分"KB无匹配"与"调用失败"。

    kb_dir:    知识库根目录（TF-IDF 用）
    chroma_dir: 历史兼容形参，已弃用，忽略（向量库为 worldsim-pg rag schema）。
    两者均可不传，函数会从环境变量 OPENCLAW_WORKSPACE 推断 kb_dir。
    """
    workspace = os.environ.get("OPENCLAW_WORKSPACE", "")
    if kb_dir is None:
        kb_dir = os.path.join(workspace, "知识库", "财经知识库") if workspace else ""

    # ── 1. 向量检索 ──────────────────────────────────────────────────────────
    vec_results = rag_query_vec(query, n_results, chroma_dir or None)
    if vec_results:
        return vec_results

    # ── 2. TF-IDF fallback ───────────────────────────────────────────────────
    if not kb_dir or not os.path.exists(kb_dir):
        print(f"  ⚠️ [RAG] 向量检索无结果，知识库目录不存在: {kb_dir}")
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        _SKIP_FILES   = {"README.md", "readme.md", "数据字典.md"}
        _SKIP_PREFIX  = ("00_知识库", "00_快速参考", "README")

        dir_hash = _kb_dir_hash(kb_dir)
        if (_TFIDF_CACHE["dir_hash"] == dir_hash
                and _TFIDF_CACHE["vectorizer"] is not None):
            docs      = _TFIDF_CACHE["docs"]
            doc_names = _TFIDF_CACHE["doc_names"]
            vectorizer   = _TFIDF_CACHE["vectorizer"]
            tfidf_matrix = _TFIDF_CACHE["matrix"]
        else:
            docs, doc_names = [], []
            for root, dirs, files in os.walk(kb_dir):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS_TFIDF)
                for fname in sorted(files):
                    if not fname.endswith(".md"):
                        continue
                    if fname in _SKIP_FILES or any(fname.startswith(p) for p in _SKIP_PREFIX):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            content = f.read().strip()
                        if len(content) > 200:
                            docs.append(content[:5000])
                            doc_names.append(fpath)
                    except Exception:
                        pass

            if not docs:
                print("  ⚠️ [RAG] 向量检索无结果，TF-IDF 也未找到知识库文档")
                return []

            vectorizer   = TfidfVectorizer(analyzer="char", ngram_range=(1, 3),
                                           max_features=60000, sublinear_tf=True)
            tfidf_matrix = vectorizer.fit_transform(docs)
            _TFIDF_CACHE.update({"vectorizer": vectorizer, "matrix": tfidf_matrix,
                                  "docs": docs, "doc_names": doc_names, "dir_hash": dir_hash})

        query_vec = vectorizer.transform([query])
        scores    = cosine_similarity(query_vec, tfidf_matrix)[0]
        top_idx   = np.argsort(scores)[-n_results:][::-1]

        results = []
        for idx in top_idx:
            if scores[idx] < 0.05:
                continue
            name = os.path.relpath(doc_names[idx], kb_dir)
            full_text = docs[idx]
            best_snippet = full_text[:800]
            if len(full_text) > 800:
                w, step = 800, 400
                wvecs = vectorizer.transform([full_text[i:i+w]
                                              for i in range(0, len(full_text)-w, step)])
                ws = cosine_similarity(query_vec, wvecs)[0]
                bi = int(np.argmax(ws))
                if ws[bi] > 0:
                    best_snippet = full_text[bi*step: bi*step+w]
            results.append(f"【{name}】\n{best_snippet.replace(chr(10)*3, chr(10)*2).strip()}")

        if not results:
            print(f"  ⚠️ [RAG] 向量和TF-IDF均无匹配（查询：{query[:40]}…）")
        else:
            print(f"  [TF-IDF RAG] 检索到 {len(results)} 个相关段落（fallback）")
        return results

    except Exception as e:
        print(f"  [RAG] TF-IDF fallback 失败: {e}")
        return []
