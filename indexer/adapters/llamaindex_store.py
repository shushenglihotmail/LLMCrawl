"""
LlamaIndex document store adapter with pluggable vector backends.
Handles chunking, embedding, and retrieval with recency scoring.
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

try:
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.embeddings import BaseEmbedding
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.schema import NodeWithScore, QueryBundle
    from llama_index.core.vector_stores.simple import SimpleVectorStore
    from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
    from llama_index.embeddings.openai import OpenAIEmbedding
except ImportError as e:
    print(f"LlamaIndex import error: {e}")
    Document = None
    VectorStoreIndex = None
    Settings = None

from ..vector.pgvector_store import PgVectorStore
from ..vector.qdrant_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class LlamaIndexStore:
    """LlamaIndex adapter with pluggable vector backends."""

    def __init__(self, vector_db: str = "qdrant"):
        self.vector_db = vector_db.lower()

        if Document is None:
            logger.error("LlamaIndex not available")
            raise ImportError("llama-index not installed")

        # Initialize vector store
        if self.vector_db == "qdrant":
            self.vector_store = QdrantVectorStore()
        elif self.vector_db == "pgvector":
            self.vector_store = PgVectorStore()
        else:
            raise ValueError(f"Unsupported vector database: {vector_db}")

        # Initialize embedding model
        self.embedding_model = self._initialize_embeddings()

        # Configure text splitter
        self.text_splitter = SentenceSplitter(
            chunk_size=1024,  # ~1k tokens
            chunk_overlap=102,  # ~10% overlap
            paragraph_separator="\n\n",
            secondary_chunking_regex="[.!?]+",
        )

        # Configure LlamaIndex settings
        Settings.embed_model = self.embedding_model
        Settings.chunk_size = 1024

        logger.info(f"Initialized LlamaIndex store with {vector_db} backend")

    def _initialize_embeddings(self) -> BaseEmbedding:
        """Initialize the embedding model based on configuration."""
        llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
        embed_model = os.getenv("EMBED_MODEL", "text-embedding-3-large")

        if llm_provider == "azure":
            return AzureOpenAIEmbedding(
                model=embed_model,
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )
        else:
            return OpenAIEmbedding(
                model=embed_model, api_key=os.getenv("OPENAI_API_KEY")
            )

    async def initialize(self):
        """Initialize the vector store backend."""
        await self.vector_store.initialize()

    async def index_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Index a list of documents with chunking and embedding.

        Args:
            documents: List of document dicts with text, url, metadata

        Returns:
            Indexing result summary
        """
        try:
            if not documents:
                return {"indexed": 0, "error": "No documents provided"}

            # Convert to LlamaIndex documents and chunk
            all_chunks = []
            chunk_count = 0

            for doc in documents:
                text = doc.get("markdown", "") or doc.get("text", "")
                if not text.strip():
                    continue

                # Create LlamaIndex document
                llama_doc = Document(
                    text=text,
                    metadata={
                        "url": doc.get("url", ""),
                        "title": doc.get("title", ""),
                        "published_at": doc.get("published_at"),
                        "source": doc.get("source", ""),
                        "content_hash": self._generate_content_hash(text),
                    },
                )

                # Chunk the document
                chunks = self.text_splitter.split_text(text)

                for i, chunk_text in enumerate(chunks):
                    chunk_doc = {
                        "text": chunk_text,
                        "url": doc.get("url", ""),
                        "title": doc.get("title", ""),
                        "published_at": doc.get("published_at"),
                        "chunk_index": i,
                        "content_hash": self._generate_content_hash(chunk_text),
                        "metadata": doc.get("metadata", {}),
                    }
                    all_chunks.append(chunk_doc)
                    chunk_count += 1

            if not all_chunks:
                return {"indexed": 0, "error": "No valid text content found"}

            # Generate embeddings for all chunks
            chunk_texts = [chunk["text"] for chunk in all_chunks]
            embeddings = await self._generate_embeddings(chunk_texts)

            # Store in vector database
            indexed_count = await self.vector_store.add_documents(
                all_chunks, embeddings
            )

            return {
                "indexed": indexed_count,
                "chunks": chunk_count,
                "documents": len(documents),
                "vector_db": self.vector_db,
            }

        except Exception as e:
            logger.error(f"Document indexing failed: {e}")
            return {"indexed": 0, "error": str(e)}

    async def retrieve_documents(
        self,
        query: str,
        k: int = 8,
        recency_boost_days: int = 14,
        score_threshold: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant documents with recency boosting.

        Args:
            query: Search query
            k: Number of results to return
            recency_boost_days: Days for recency boosting
            score_threshold: Minimum similarity score

        Returns:
            Search results with hits and metadata
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embeddings([query])
            if not query_embedding:
                return {"hits": [], "error": "Failed to generate query embedding"}

            # Search vector store
            raw_results = await self.vector_store.similarity_search(
                query_embedding=query_embedding[0],
                limit=k * 2,  # Get more results for reranking
                score_threshold=score_threshold,
            )

            # Apply recency boosting and rerank
            boosted_results = self._apply_recency_boost(raw_results, recency_boost_days)

            # Group by URL and take best chunk per document
            url_groups = {}
            for result in boosted_results:
                url = result["url"]
                if (
                    url not in url_groups
                    or result["boosted_score"] > url_groups[url]["boosted_score"]
                ):
                    url_groups[url] = result

            # Sort by boosted score and limit
            final_results = sorted(
                url_groups.values(), key=lambda x: x["boosted_score"], reverse=True
            )[:k]

            # Format results
            hits = []
            for result in final_results:
                hit = {
                    "url": result["url"],
                    "title": result["title"],
                    "published_at": result["published_at"],
                    "snippet": self._create_snippet(result["text"], query),
                    "score": result["score"],
                    "boosted_score": result["boosted_score"],
                    "chunk_index": result["chunk_index"],
                }
                hits.append(hit)

            return {
                "hits": hits,
                "total_found": len(raw_results),
                "query": query,
                "recency_boost_days": recency_boost_days,
            }

        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            return {"hits": [], "error": str(e)}

    def _apply_recency_boost(
        self, results: List[Dict[str, Any]], boost_days: int
    ) -> List[Dict[str, Any]]:
        """Apply recency boosting to search results."""
        now = datetime.now()
        boosted_results = []

        for result in results:
            base_score = result["score"]

            # Calculate recency boost
            published_at = result.get("published_at")
            if published_at:
                try:
                    # Parse date
                    if isinstance(published_at, str):
                        pub_date = datetime.fromisoformat(
                            published_at.replace("Z", "+00:00")
                        )
                    else:
                        pub_date = published_at

                    # Calculate days since publication
                    days_old = (now - pub_date).days

                    # Apply exponential decay boost
                    if days_old <= boost_days:
                        boost_factor = 1 + (0.5 * (1 - days_old / boost_days))
                    else:
                        boost_factor = 1.0

                    boosted_score = base_score * boost_factor

                except Exception as e:
                    logger.warning(f"Failed to parse date {published_at}: {e}")
                    boosted_score = base_score
            else:
                # No publication date - slight penalty
                boosted_score = base_score * 0.9

            result["boosted_score"] = boosted_score
            boosted_results.append(result)

        return sorted(boosted_results, key=lambda x: x["boosted_score"], reverse=True)

    def _create_snippet(self, text: str, query: str, max_length: int = 300) -> str:
        """Create a snippet around query terms."""
        query_terms = query.lower().split()
        text_lower = text.lower()

        # Find the best position to start the snippet
        best_pos = 0
        best_score = 0

        # Look for query terms in the text
        for term in query_terms:
            pos = text_lower.find(term)
            if pos != -1:
                # Count terms around this position
                window_start = max(0, pos - 100)
                window_end = min(len(text), pos + 100)
                window = text_lower[window_start:window_end]

                score = sum(1 for term in query_terms if term in window)
                if score > best_score:
                    best_score = score
                    best_pos = max(0, pos - 50)

        # Create snippet
        snippet_end = min(len(text), best_pos + max_length)
        snippet = text[best_pos:snippet_end].strip()

        # Add ellipsis if needed
        if best_pos > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    async def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        try:
            # Use LlamaIndex embedding model
            embeddings = await self.embedding_model.aget_text_embedding_batch(texts)
            return embeddings

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return []

    def _generate_content_hash(self, content: str) -> str:
        """Generate a hash for content deduplication."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    async def health_check(self) -> Dict[str, Any]:
        """Check if the indexing system is healthy."""
        try:
            # Check vector store
            vector_health = await self.vector_store.health_check()

            # Test embedding generation
            try:
                test_embedding = await self._generate_embeddings(["test"])
                embedding_healthy = (
                    len(test_embedding) > 0 and len(test_embedding[0]) > 0
                )
            except:
                embedding_healthy = False

            return {
                "status": "healthy"
                if vector_health.get("status") == "healthy" and embedding_healthy
                else "degraded",
                "service": "llamaindex_store",
                "vector_store": vector_health,
                "embedding_model": {
                    "healthy": embedding_healthy,
                    "model": getattr(self.embedding_model, "model_name", "unknown"),
                },
                "vector_db": self.vector_db,
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "llamaindex_store",
                "error": str(e),
            }

    async def close(self):
        """Close connections and cleanup resources."""
        try:
            await self.vector_store.close()
        except Exception as e:
            logger.error(f"Error closing LlamaIndex store: {e}")


# Global store instance
_store = None


async def get_llamaindex_store(vector_db: str = None) -> LlamaIndexStore:
    """Get or create the global LlamaIndex store."""
    global _store
    if _store is None:
        if not vector_db:
            vector_db = os.getenv("VECTOR_DB", "qdrant")
        _store = LlamaIndexStore(vector_db)
        await _store.initialize()
    return _store
