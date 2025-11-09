"""
Qdrant vector store adapter for LlamaIndex integration.
Handles document storage, embedding, and similarity search with Qdrant.
"""

import os
import uuid
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

try:
    from qdrant_client import QdrantClient, AsyncQdrantClient
    from qdrant_client.http import models
    from qdrant_client.http.models import Distance, VectorParams, PointStruct
except ImportError:
    QdrantClient = None
    AsyncQdrantClient = None
    models = None

logger = logging.getLogger(__name__)

class QdrantVectorStore:
    """Qdrant vector store adapter with async support."""
    
    def __init__(self, collection_name: str = "web_rag_docs"):
        self.collection_name = collection_name
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        self.embedding_dim = 3072  # text-embedding-3-large dimension
        
        if not AsyncQdrantClient:
            logger.error("Qdrant client not available")
            raise ImportError("qdrant-client not installed")
        
        self.client = AsyncQdrantClient(url=self.qdrant_url)
        logger.info(f"Initialized Qdrant store: {self.qdrant_url}/{collection_name}")
    
    async def initialize(self):
        """Initialize the collection if it doesn't exist."""
        try:
            collections = await self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"Using existing Qdrant collection: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collection: {e}")
            raise
    
    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> int:
        """
        Add documents with embeddings to the vector store.
        
        Args:
            documents: List of document chunks with metadata
            embeddings: Corresponding embedding vectors
            
        Returns:
            Number of documents successfully added
        """
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")
        
        try:
            points = []
            for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
                point_id = str(uuid.uuid4())
                
                # Prepare metadata for Qdrant
                payload = {
                    "text": doc.get("text", ""),
                    "url": doc.get("url", ""),
                    "title": doc.get("title", ""),
                    "published_at": doc.get("published_at"),
                    "chunk_index": doc.get("chunk_index", 0),
                    "content_hash": doc.get("content_hash", ""),
                    "indexed_at": datetime.now().isoformat(),
                    "metadata": doc.get("metadata", {})
                }
                
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                )
            
            # Batch upsert
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"Added {len(points)} documents to Qdrant")
            return len(points)
            
        except Exception as e:
            logger.error(f"Failed to add documents to Qdrant: {e}")
            raise
    
    async def similarity_search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search with optional filtering.
        
        Args:
            query_embedding: Query vector
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            filters: Optional metadata filters
            
        Returns:
            List of similar documents with scores
        """
        try:
            # Build filter conditions
            filter_conditions = None
            if filters:
                filter_conditions = self._build_filter_conditions(filters)
            
            # Perform search
            results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=filter_conditions
            )
            
            # Format results
            documents = []
            for result in results:
                doc = {
                    "id": result.id,
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "url": result.payload.get("url", ""),
                    "title": result.payload.get("title", ""),
                    "published_at": result.payload.get("published_at"),
                    "chunk_index": result.payload.get("chunk_index", 0),
                    "metadata": result.payload.get("metadata", {})
                }
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            raise
    
    def _build_filter_conditions(self, filters: Dict[str, Any]):
        """Build Qdrant filter conditions from filter dict."""
        if not models:
            return None
            
        conditions = []
        
        for key, value in filters.items():
            if key == "date_range" and isinstance(value, dict):
                # Date range filter
                start_date = value.get("start")
                end_date = value.get("end")
                
                if start_date:
                    conditions.append(
                        models.FieldCondition(
                            key="published_at",
                            range=models.DatetimeRange(gte=start_date)
                        )
                    )
                
                if end_date:
                    conditions.append(
                        models.FieldCondition(
                            key="published_at", 
                            range=models.DatetimeRange(lte=end_date)
                        )
                    )
            
            elif key == "urls" and isinstance(value, list):
                # URL filter
                conditions.append(
                    models.FieldCondition(
                        key="url",
                        match=models.MatchAny(any=value)
                    )
                )
            
            elif isinstance(value, (str, int, float)):
                # Simple field match
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value)
                    )
                )
        
        if conditions:
            return models.Filter(must=conditions)
        
        return None
    
    async def delete_documents(self, filter_conditions: Dict[str, Any]) -> int:
        """Delete documents matching filter conditions."""
        try:
            filter_obj = self._build_filter_conditions(filter_conditions)
            
            result = await self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=filter_obj)
            )
            
            deleted_count = getattr(result, 'operation_id', 0)
            logger.info(f"Deleted documents from Qdrant: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            raise
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        try:
            info = await self.client.get_collection(self.collection_name)
            
            return {
                "name": info.config.params.vectors.size,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance.value,
                "points_count": info.points_count,
                "status": info.status.value
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Qdrant is healthy and accessible."""
        try:
            collections = await self.client.get_collections()
            
            return {
                "status": "healthy",
                "service": "qdrant",
                "url": self.qdrant_url,
                "collections": len(collections.collections),
                "target_collection": self.collection_name
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "qdrant", 
                "url": self.qdrant_url,
                "error": str(e)
            }
    
    async def close(self):
        """Close the client connection."""
        try:
            await self.client.close()
        except:
            pass