"""
vector_store.py —— Qdrant + ArkMultimodalEmbeddings

ArkMultimodalEmbeddings：复用自 HydroBridge AI，对接火山引擎 doubao embedding。
Collection  ：codeagent_memories（自动创建，向量维度由首次写入时确定）

存储时机（memory_writer 调用）：
  - 每轮对话后存入 user+assistant 摘要对（type=turn）
  - 压缩后存入 long_term_summary（type=summary）

检索时机（context_loader 调用）：
  - 每次输入前，按用户问题语义检索 Top-3 相关记忆

注意：在 localhost 上需绕过系统代理（Windows 代理会拦截 Python 的本地请求）。
"""
import os
import hashlib
from typing import List

import httpx
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from codeagent.config import settings

COLLECTION = "codeagent_memories"
_VECTOR_DIM: int | None = None   # 延迟初始化，由首次 embed 决定


# ── 绕过代理工具 ──────────────────────────────────────────────────────────────

def _no_proxy_env() -> dict:
    """返回清除代理后的环境变量片段，供 subprocess/httpx 使用"""
    patch = {}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        patch[k] = ""
    return patch


def _apply_no_proxy() -> None:
    """在进程级别清除代理，使 Python 直连 localhost"""
    for k, v in _no_proxy_env().items():
        os.environ[k] = v
    # 追加 NO_PROXY（httpx 会读取）
    existing = os.environ.get("NO_PROXY", "")
    no_proxy_hosts = "localhost,127.0.0.1"
    if no_proxy_hosts not in existing:
        os.environ["NO_PROXY"] = f"{existing},{no_proxy_hosts}".lstrip(",")
        os.environ["no_proxy"] = os.environ["NO_PROXY"]


# ── Embedding 封装（复用 HydroBridge AI 实现）─────────────────────────────────

class ArkMultimodalEmbeddings(Embeddings):
    """火山引擎 Ark multimodal embedding，纯文本场景"""

    def __init__(self):
        self.api_key = settings.embedding_api_key
        self.base_url = settings.EMBEDDING_BASE_URL.rstrip("/")
        self.model = settings.EMBEDDING_MODEL
        self.url = f"{self.base_url}/embeddings/multimodal"

    def _call(self, text: str) -> List[float]:
        resp = httpx.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": [{"type": "text", "text": text[:4000]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["embedding"]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._call(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._call(text)


# ── Qdrant 操作 ───────────────────────────────────────────────────────────────

def _get_client() -> QdrantClient:
    _apply_no_proxy()
    return QdrantClient(url=settings.QDRANT_URL)


def _ensure_collection(client: QdrantClient, dim: int) -> None:
    """确保 collection 存在，向量维度为 dim"""
    existing = {col.name for col in client.get_collections().collections}
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def store_memory(thread_id: str, content: str, doc_type: str = "turn") -> None:
    """
    将内容存入 Qdrant。
    doc_type: "turn"（单轮对话）| "summary"（压缩摘要）
    失败静默，不阻断主流程。
    """
    if not content.strip():
        return
    try:
        emb = ArkMultimodalEmbeddings()
        vector = emb.embed_query(content[:2000])

        client = _get_client()
        _ensure_collection(client, len(vector))

        point_id = int(hashlib.md5(
            f"{thread_id}:{content[:120]}".encode()
        ).hexdigest(), 16) % (2**63)

        client.upsert(
            collection_name=COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={"thread_id": thread_id, "type": doc_type, "text": content[:2000]},
            )],
        )
    except Exception:
        pass  # 向量检索是增强功能，失败不影响主流程


def retrieve_memories(query: str, top_k: int = 3) -> str:
    """
    语义检索最相关的历史记忆，返回拼接文本。
    失败时返回空字符串。
    """
    if not query.strip():
        return ""
    try:
        client = _get_client()
        existing = {col.name for col in client.get_collections().collections}
        if COLLECTION not in existing:
            return ""

        emb = ArkMultimodalEmbeddings()
        query_vector = emb.embed_query(query)

        results = client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )

        points = results.points
        if not points:
            return ""

        return "\n---\n".join(
            p.payload.get("text", "") for p in points if p.payload
        )
    except Exception:
        return ""
