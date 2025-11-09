"""
PostgreSQL with pgvector adapter for LlamaIndex integration.
Handles document storage, embedding, and similarity search with PostgreSQL + pgvector.
"""

import os
import uuid
import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

try:
    import asyncpg
    import numpy as np
except ImportError:
    asyncpg = None
    np = None

logger = logging.getLogger(__name__)

class PgVectorStore:
    """PostgreSQL + pgvector adapter with async support."""
    
    def __init__(self, table_name: str = "web_rag_docs"):
        self.table_name = table_name
        self.dsn = os.getenv("PG_DSN", "postgresql://postgres:password@postgres:5432/rag_db")
        self.embedding_dim = 3072  # text-embedding-3-large dimension
        
        if not asyncpg:
            logger.error("asyncpg not available")
            raise ImportError("asyncpg not installed")
        
        self._pool = None
        logger.info(f"Initialized PgVector store: {table_name}")
    
    async def initialize(self):
        """Initialize database connection and create table if needed."""
        try:
            # Create connection pool
            self._pool = await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=10,
                command_timeout=30
            )
            
            # Create table and enable pgvector
            async with self._pool.acquire() as conn:
                # Enable pgvector extension
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Create table with vector column
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        text TEXT NOT NULL,
                        url TEXT,
                        title TEXT,
                        published_at TIMESTAMP,
                        chunk_index INTEGER DEFAULT 0,
                        content_hash TEXT,
                        indexed_at TIMESTAMP DEFAULT NOW(),
                        metadata JSONB DEFAULT '{{}}',
                        embedding vector({self.embedding_dim})
                    );
                """)
                
                # Create indexes for better performance
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx 
                    ON {self.table_name} USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_url_idx 
                    ON {self.table_name} (url);
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_published_at_idx 
                    ON {self.table_name} (published_at DESC);
                """)
                
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_metadata_idx 
                    ON {self.table_name} USING GIN (metadata);
                """)
                
            logger.info(f"Initialized PostgreSQL table: {self.table_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
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
            async with self._pool.acquire() as conn:
                # Prepare data for batch insert
                records = []
                for doc, embedding in zip(documents, embeddings):
                    # Convert embedding to pgvector format
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                    
                    record = (
                        doc.get("text", ""),
                        doc.get("url", ""),
                        doc.get("title", ""),
                        doc.get("published_at"),
                        doc.get("chunk_index", 0),
                        doc.get("content_hash", ""),
                        json.dumps(doc.get("metadata", {})),
                        embedding_str
                    )
                    records.append(record)
                
                # Batch insert
                query = f"""
                    INSERT INTO {self.table_name} 
                    (text, url, title, published_at, chunk_index, content_hash, metadata, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """
                
                await conn.executemany(query, records)
                
            logger.info(f"Added {len(records)} documents to PostgreSQL")
            return len(records)
            
        except Exception as e:
            logger.error(f"Failed to add documents to PostgreSQL: {e}")
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
            # Convert query embedding to pgvector format
            query_vector = f"[{','.join(map(str, query_embedding))}]"
            
            # Build base query
            base_query = f"""
                SELECT 
                    id, text, url, title, published_at, chunk_index, metadata,
                    1 - (embedding <=> '{query_vector}') as similarity_score
                FROM {self.table_name}
            """
            
            # Add filters
            where_conditions = []
            params = []
            
            if score_threshold > 0:
                where_conditions.append(f"1 - (embedding <=> '{query_vector}') >= ${len(params) + 1}")
                params.append(score_threshold)
            
            if filters:
                filter_sql, filter_params = self._build_filter_conditions(filters, len(params) + 1)
                if filter_sql:
                    where_conditions.extend(filter_sql)
                    params.extend(filter_params)
            
            # Combine query
            if where_conditions:
                query = base_query + " WHERE " + " AND ".join(where_conditions)
            else:
                query = base_query
            
            query += f" ORDER BY similarity_score DESC LIMIT {limit}"
            
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                
                documents = []
                for row in rows:
                    doc = {
                        "id": str(row["id"]),
                        "score": float(row["similarity_score"]),
                        "text": row["text"],
                        "url": row["url"],
                        "title": row["title"],
                        "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                        "chunk_index": row["chunk_index"],
                        "metadata": row["metadata"] or {}
                    }
                    documents.append(doc)
                
                return documents
                
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            raise
    
    def _build_filter_conditions(self, filters: Dict[str, Any], param_offset: int = 1) -> Tuple[List[str], List[Any]]:
        """Build SQL filter conditions from filter dict."""
        conditions = []
        params = []
        param_count = param_offset
        
        for key, value in filters.items():
            if key == "date_range" and isinstance(value, dict):
                # Date range filter
                start_date = value.get("start")
                end_date = value.get("end")
                
                if start_date:
                    conditions.append(f"published_at >= ${param_count}")
                    params.append(start_date)
                    param_count += 1
                
                if end_date:
                    conditions.append(f"published_at <= ${param_count}")
                    params.append(end_date)
                    param_count += 1
            
            elif key == "urls" and isinstance(value, list):
                # URL filter
                placeholders = [f"${param_count + i}" for i in range(len(value))]
                conditions.append(f"url = ANY(ARRAY[{','.join(placeholders)}])")
                params.extend(value)
                param_count += len(value)
            
            elif key == "metadata_filter" and isinstance(value, dict):
                # JSON metadata filter
                for meta_key, meta_value in value.items():
                    conditions.append(f"metadata ->> ${param_count} = ${param_count + 1}")
                    params.extend([meta_key, str(meta_value)])
                    param_count += 2
            
            elif isinstance(value, (str, int, float)):
                # Simple field filter
                if key in ["url", "title", "content_hash"]:
                    conditions.append(f"{key} = ${param_count}")
                    params.append(value)
                    param_count += 1
        
        return conditions, params
    
    async def delete_documents(self, filter_conditions: Dict[str, Any]) -> int:
        """Delete documents matching filter conditions."""
        try:
            conditions, params = self._build_filter_conditions(filter_conditions)
            
            if not conditions:
                raise ValueError("No filter conditions provided for deletion")
            
            query = f"DELETE FROM {self.table_name} WHERE {' AND '.join(conditions)}"
            
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, *params)
                
                # Parse the result to get deleted count
                deleted_count = int(result.split()[-1]) if result else 0
                
            logger.info(f"Deleted {deleted_count} documents from PostgreSQL")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete documents: {e}")
            raise
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the table."""
        try:
            async with self._pool.acquire() as conn:
                # Get table statistics
                stats_query = f"""
                    SELECT 
                        COUNT(*) as total_docs,
                        COUNT(DISTINCT url) as unique_urls,
                        MIN(indexed_at) as first_indexed,
                        MAX(indexed_at) as last_indexed
                    FROM {self.table_name}
                """
                
                stats = await conn.fetchrow(stats_query)
                
                # Get table size
                size_query = f"""
                    SELECT pg_total_relation_size('{self.table_name}') as table_size_bytes
                """
                
                size_info = await conn.fetchrow(size_query)
                
                return {
                    "table_name": self.table_name,
                    "total_documents": stats["total_docs"],
                    "unique_urls": stats["unique_urls"],
                    "first_indexed": stats["first_indexed"].isoformat() if stats["first_indexed"] else None,
                    "last_indexed": stats["last_indexed"].isoformat() if stats["last_indexed"] else None,
                    "table_size_bytes": size_info["table_size_bytes"],
                    "embedding_dimension": self.embedding_dim
                }
                
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if PostgreSQL is healthy and accessible."""
        try:
            async with self._pool.acquire() as conn:
                # Test basic connectivity and pgvector
                await conn.fetchval("SELECT 1")
                
                # Check if pgvector extension is available
                pgvector_check = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                
                return {
                    "status": "healthy",
                    "service": "pgvector",
                    "dsn": self.dsn.split("@")[-1],  # Hide credentials
                    "table": self.table_name,
                    "pgvector_enabled": pgvector_check
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "pgvector",
                "dsn": self.dsn.split("@")[-1],  # Hide credentials
                "error": str(e)
            }
    
    async def close(self):
        """Close the connection pool."""
        try:
            if self._pool:
                await self._pool.close()
                self._pool = None
        except Exception as e:
            logger.error(f"Error closing PostgreSQL pool: {e}")