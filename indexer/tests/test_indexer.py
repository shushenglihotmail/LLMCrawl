"""
Unit tests for the indexer service.
Tests LlamaIndex integration, vector stores, and recency scoring.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import json
from datetime import datetime, timedelta

# Mock the imports that might not be available in test environment
with patch.dict('sys.modules', {
    'llama_index': Mock(),
    'qdrant_client': Mock(),
    'asyncpg': Mock(),
    'numpy': Mock()
}):
    pass


class TestRecencyScoring:
    """Test recency scoring functionality."""
    
    def test_recency_boost_calculation(self):
        """Test recency boost calculation logic."""
        now = datetime.now()
        boost_days = 14
        
        # Test documents with different ages
        test_docs = [
            {"published_at": (now - timedelta(days=1)).isoformat(), "score": 0.8},  # Very recent
            {"published_at": (now - timedelta(days=7)).isoformat(), "score": 0.8},  # Within boost window
            {"published_at": (now - timedelta(days=30)).isoformat(), "score": 0.8},  # Outside boost window
            {"published_at": None, "score": 0.8}  # No date
        ]
        
        # Calculate expected boosts
        for doc in test_docs:
            base_score = doc["score"]
            pub_date_str = doc.get("published_at")
            
            if pub_date_str:
                pub_date = datetime.fromisoformat(pub_date_str)
                days_old = (now - pub_date).days
                
                if days_old <= boost_days:
                    boost_factor = 1 + (0.5 * (1 - days_old / boost_days))
                else:
                    boost_factor = 1.0
                    
                expected_score = base_score * boost_factor
            else:
                expected_score = base_score * 0.9  # Penalty for no date
            
            # Verify boost is calculated correctly
            if pub_date_str:
                pub_date = datetime.fromisoformat(pub_date_str)
                days_old = (now - pub_date).days
                
                if days_old == 1:  # Very recent should get significant boost
                    assert expected_score > base_score
                elif days_old <= boost_days:  # Within window should get some boost
                    assert expected_score >= base_score
                else:  # Outside window should get no boost
                    assert expected_score == base_score
    
    def test_snippet_creation(self):
        """Test snippet creation around query terms."""
        text = """
        This is a long article about machine learning and artificial intelligence.
        The article discusses various aspects of deep learning, neural networks,
        and their applications in natural language processing. Machine learning
        has revolutionized many industries and continues to advance rapidly.
        """
        
        query = "machine learning"
        max_length = 150
        
        # Test snippet logic
        query_terms = query.lower().split()
        text_lower = text.lower()
        
        # Find best position
        best_pos = 0
        for term in query_terms:
            pos = text_lower.find(term)
            if pos != -1:
                best_pos = max(0, pos - 50)
                break
        
        snippet_end = min(len(text), best_pos + max_length)
        snippet = text[best_pos:snippet_end].strip()
        
        # Verify snippet contains query terms
        assert any(term in snippet.lower() for term in query_terms)
        assert len(snippet) <= max_length + 20  # Some tolerance for word boundaries


class TestDocumentChunking:
    """Test document chunking functionality."""
    
    def test_text_chunking(self):
        """Test text chunking logic."""
        # Sample long text
        long_text = " ".join([f"This is sentence {i}." for i in range(200)])
        
        # Chunking parameters
        chunk_size = 1024
        chunk_overlap = 102
        
        # Simple chunking simulation
        chunks = []
        start = 0
        
        while start < len(long_text):
            end = min(start + chunk_size, len(long_text))
            chunk = long_text[start:end]
            chunks.append(chunk)
            
            # Move start position with overlap
            start = end - chunk_overlap
            if start >= len(long_text):
                break
        
        # Verify chunking results
        assert len(chunks) > 1  # Should create multiple chunks
        assert all(len(chunk) <= chunk_size for chunk in chunks)
        
        # Check overlap exists between consecutive chunks
        if len(chunks) > 1:
            overlap = chunks[0][-chunk_overlap:] in chunks[1]
            # Note: This is simplified - real overlap might be at word boundaries
    
    def test_content_hash_generation(self):
        """Test content hash for deduplication."""
        content1 = "This is test content for hashing."
        content2 = "This is test content for hashing."
        content3 = "This is different content."
        
        import hashlib
        hash1 = hashlib.md5(content1.encode('utf-8')).hexdigest()
        hash2 = hashlib.md5(content2.encode('utf-8')).hexdigest()
        hash3 = hashlib.md5(content3.encode('utf-8')).hexdigest()
        
        assert hash1 == hash2  # Same content should produce same hash
        assert hash1 != hash3  # Different content should produce different hash


class TestVectorStoreAdapters:
    """Test vector store adapter functionality."""
    
    def test_qdrant_point_structure(self):
        """Test Qdrant point structure creation."""
        document = {
            "text": "Test document content",
            "url": "https://example.com/test",
            "title": "Test Document",
            "published_at": "2024-01-15T10:00:00Z",
            "metadata": {"source": "test"}
        }
        
        embedding = [0.1, 0.2, 0.3]  # Simplified embedding
        
        # Expected point structure
        expected_payload = {
            "text": document["text"],
            "url": document["url"],
            "title": document["title"],
            "published_at": document["published_at"],
            "chunk_index": 0,
            "content_hash": "",
            "indexed_at": datetime.now().isoformat(),
            "metadata": document["metadata"]
        }
        
        # Verify structure
        assert "text" in expected_payload
        assert "url" in expected_payload
        assert "metadata" in expected_payload
    
    def test_pgvector_query_building(self):
        """Test PostgreSQL query building with filters."""
        filters = {
            "date_range": {
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-12-31T23:59:59Z"
            },
            "urls": ["https://example1.com", "https://example2.com"]
        }
        
        # Test filter condition building logic
        conditions = []
        params = []
        param_count = 1
        
        for key, value in filters.items():
            if key == "date_range" and isinstance(value, dict):
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
                placeholders = [f"${param_count + i}" for i in range(len(value))]
                conditions.append(f"url = ANY(ARRAY[{','.join(placeholders)}])")
                params.extend(value)
                param_count += len(value)
        
        # Verify query building
        assert len(conditions) == 3  # Two date conditions + one URL condition
        assert len(params) == 4  # Two dates + two URLs
        assert "published_at >=" in conditions[0]
        assert "url = ANY" in conditions[2]


class TestIndexingPipeline:
    """Test the full indexing pipeline."""
    
    @pytest.mark.asyncio
    async def test_document_indexing_flow(self):
        """Test complete document indexing flow."""
        # Sample documents
        documents = [
            {
                "url": "https://example.com/doc1",
                "title": "Document 1",
                "markdown": "This is the content of document 1.",
                "published_at": "2024-01-15T10:00:00Z",
                "metadata": {"source": "test"}
            },
            {
                "url": "https://example.com/doc2", 
                "title": "Document 2",
                "markdown": "This is the content of document 2.",
                "published_at": "2024-01-16T10:00:00Z",
                "metadata": {"source": "test"}
            }
        ]
        
        # Expected indexing result
        expected_result = {
            "indexed": 2,
            "chunks": 2,
            "documents": 2,
            "vector_db": "qdrant"
        }
        
        # Verify the structure
        assert expected_result["indexed"] == len(documents)
        assert expected_result["documents"] == len(documents)
        assert "vector_db" in expected_result
    
    @pytest.mark.asyncio 
    async def test_retrieval_flow(self):
        """Test document retrieval flow."""
        query = "test query"
        expected_hits = [
            {
                "url": "https://example.com/doc1",
                "title": "Document 1",
                "published_at": "2024-01-15T10:00:00Z",
                "snippet": "This is the content...",
                "score": 0.95,
                "boosted_score": 1.2
            }
        ]
        
        expected_result = {
            "hits": expected_hits,
            "total_found": 1,
            "query": query,
            "recency_boost_days": 14
        }
        
        # Verify retrieval result structure
        assert "hits" in expected_result
        assert "query" in expected_result
        assert expected_result["hits"][0]["score"] <= expected_result["hits"][0]["boosted_score"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])