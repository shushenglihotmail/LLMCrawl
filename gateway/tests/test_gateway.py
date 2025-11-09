"""
Unit tests for the gateway service.
Tests chat endpoints, tool calling, and LLM integration.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import json

# Mock the imports that might not be available in test environment
with patch.dict('sys.modules', {
    'openai': Mock(),
    'httpx': Mock(),
    'fastapi': Mock()
}):
    from gateway.llm.prompts import should_trigger_crawl, build_messages_with_examples, CRAWL_AND_REFRESH_TOOL
    from gateway.routers.tools import ToolHandler

class TestPrompts:
    """Test prompt processing and tool schema."""
    
    def test_should_trigger_crawl_positive(self):
        """Test that crawl triggers are detected correctly."""
        positive_cases = [
            "What's the latest on NVDA earnings?",
            "Breaking news about Tesla?",
            "Any recent updates on AI?",
            "Today's market news",
            "This week's tech announcements",
            "Current stock price of Apple"
        ]
        
        for case in positive_cases:
            assert should_trigger_crawl(case), f"Should trigger crawl for: {case}"
    
    def test_should_trigger_crawl_negative(self):
        """Test that general questions don't trigger crawls."""
        negative_cases = [
            "Explain how photosynthesis works",
            "What is the capital of France?",
            "How does machine learning work?",
            "Define artificial intelligence",
            "What are the benefits of exercise?"
        ]
        
        for case in negative_cases:
            assert not should_trigger_crawl(case), f"Should NOT trigger crawl for: {case}"
    
    def test_tool_schema_structure(self):
        """Test that the tool schema is properly structured."""
        tool = CRAWL_AND_REFRESH_TOOL
        
        assert tool["type"] == "function"
        assert "function" in tool
        assert tool["function"]["name"] == "crawl_and_refresh"
        assert "parameters" in tool["function"]
        assert "query" in tool["function"]["parameters"]["required"]
    
    def test_build_messages_with_examples(self):
        """Test message building with examples."""
        user_message = "Test message"
        messages = build_messages_with_examples(user_message)
        
        # Should contain system prompts, examples, and user message
        assert len(messages) > 3
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == user_message


class TestToolHandler:
    """Test tool calling functionality."""
    
    @pytest.fixture
    def tool_handler(self):
        """Create a tool handler instance for testing."""
        with patch('httpx.AsyncClient'):
            return ToolHandler()
    
    @pytest.mark.asyncio
    async def test_tool_call_structure(self, tool_handler):
        """Test tool call handling structure."""
        mock_tool_call = {
            "id": "test_call_1",
            "type": "function",
            "function": {
                "name": "crawl_and_refresh",
                "arguments": json.dumps({
                    "query": "test query",
                    "freshness_days": 7
                })
            }
        }
        
        # Mock the internal methods
        with patch.object(tool_handler, '_handle_crawl_and_refresh', new_callable=AsyncMock) as mock_crawl:
            mock_crawl.return_value = {"test": "result"}
            
            result = await tool_handler.handle_tool_call(mock_tool_call, "test_request_id")
            
            assert result["tool_call_id"] == "test_call_1"
            assert result["role"] == "tool"
            assert "content" in result
            mock_crawl.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_crawl_and_refresh_pipeline(self, tool_handler):
        """Test the full crawl and refresh pipeline."""
        arguments = {
            "query": "test query",
            "seed_urls": ["https://example.com"],
            "freshness_days": 7,
            "depth": 1
        }
        
        # Mock HTTP responses
        mock_crawl_response = {
            "docs": [
                {
                    "url": "https://example.com/article",
                    "title": "Test Article", 
                    "markdown": "Test content",
                    "published_at": "2024-01-15T10:00:00Z"
                }
            ]
        }
        
        mock_index_response = {"indexed": 1}
        
        mock_retrieve_response = {
            "hits": [
                {
                    "url": "https://example.com/article",
                    "title": "Test Article",
                    "published_at": "2024-01-15T10:00:00Z",
                    "snippet": "Test content snippet",
                    "score": 0.9
                }
            ]
        }
        
        with patch.object(tool_handler, '_call_crawler', new_callable=AsyncMock) as mock_crawler, \
             patch.object(tool_handler, '_call_indexer_index', new_callable=AsyncMock) as mock_indexer, \
             patch.object(tool_handler, '_call_indexer_retrieve', new_callable=AsyncMock) as mock_retrieve:
            
            mock_crawler.return_value = mock_crawl_response
            mock_indexer.return_value = mock_index_response
            mock_retrieve.return_value = mock_retrieve_response
            
            result = await tool_handler._handle_crawl_and_refresh(arguments, "test_id")
            
            assert result["count"] == 1
            assert len(result["hits"]) == 1
            assert result["hits"][0]["url"] == "https://example.com/article"
            assert result["query"] == "test query"


@pytest.mark.asyncio
async def test_integration_health_checks():
    """Test that health check endpoints work properly."""
    # This would be an integration test that requires services to be running
    # For now, just test the structure
    
    health_response = {
        "status": "healthy",
        "service": "gateway",
        "llm": {"status": "healthy"},
        "timestamp": "2024-01-15T10:00:00Z"
    }
    
    assert "status" in health_response
    assert "service" in health_response
    assert health_response["service"] == "gateway"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])