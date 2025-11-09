"""
End-to-end integration test for the Web RAG system.
Tests the complete pipeline from user query to cited response.
"""

import asyncio
import httpx
import json
import time
import os
from typing import Dict, Any

class WebRAGIntegrationTest:
    """Integration test suite for the complete Web RAG system."""
    
    def __init__(self):
        self.gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
        self.crawler_url = os.getenv("CRAWLER_URL", "http://localhost:8001")
        self.indexer_url = os.getenv("INDEXER_URL", "http://localhost:8002")
        
        self.test_results = []
    
    async def run_all_tests(self):
        """Run the complete integration test suite."""
        print("🚀 Starting Web RAG Integration Tests")
        print("=" * 50)
        
        # Test 1: Health checks
        await self.test_health_checks()
        
        # Test 2: Manual crawling
        await self.test_manual_crawling()
        
        # Test 3: Manual indexing
        await self.test_manual_indexing()
        
        # Test 4: Manual retrieval
        await self.test_manual_retrieval()
        
        # Test 5: End-to-end chat with tool calling
        await self.test_end_to_end_chat()
        
        # Test 6: Chat without tool calling
        await self.test_general_chat()
        
        # Print results
        self.print_test_results()
    
    async def test_health_checks(self):
        """Test that all services are healthy."""
        print("\n🏥 Testing Health Checks...")
        
        services = [
            ("Gateway", f"{self.gateway_url}/health"),
            ("Crawler", f"{self.crawler_url}/health"), 
            ("Indexer", f"{self.indexer_url}/health")
        ]
        
        async with httpx.AsyncClient(timeout=30) as client:
            for service_name, health_url in services:
                try:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        health_data = response.json()
                        status = health_data.get("status", "unknown")
                        print(f"  ✅ {service_name}: {status}")
                        self.test_results.append({
                            "test": f"{service_name} Health",
                            "status": "PASS",
                            "details": f"Status: {status}"
                        })
                    else:
                        print(f"  ❌ {service_name}: HTTP {response.status_code}")
                        self.test_results.append({
                            "test": f"{service_name} Health",
                            "status": "FAIL", 
                            "details": f"HTTP {response.status_code}"
                        })
                except Exception as e:
                    print(f"  ❌ {service_name}: {str(e)}")
                    self.test_results.append({
                        "test": f"{service_name} Health",
                        "status": "FAIL",
                        "details": str(e)
                    })
    
    async def test_manual_crawling(self):
        """Test manual crawling functionality."""
        print("\n🕷️ Testing Manual Crawling...")
        
        crawl_request = {
            "query": "Python programming tutorial",
            "seed_urls": ["https://docs.python.org"],
            "freshness_days": 30,
            "max_results": 3
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json=crawl_request
                )
                
                if response.status_code == 200:
                    data = response.json()
                    docs_count = len(data.get("docs", []))
                    print(f"  ✅ Crawled {docs_count} documents")
                    self.test_results.append({
                        "test": "Manual Crawling",
                        "status": "PASS",
                        "details": f"Crawled {docs_count} documents"
                    })
                    return data
                else:
                    print(f"  ❌ Crawling failed: HTTP {response.status_code}")
                    self.test_results.append({
                        "test": "Manual Crawling",
                        "status": "FAIL",
                        "details": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                print(f"  ❌ Crawling error: {str(e)}")
                self.test_results.append({
                    "test": "Manual Crawling", 
                    "status": "FAIL",
                    "details": str(e)
                })
        
        return None
    
    async def test_manual_indexing(self):
        """Test manual indexing functionality."""
        print("\n📚 Testing Manual Indexing...")
        
        # Sample documents for indexing
        sample_docs = [
            {
                "url": "https://example.com/test1",
                "title": "Test Document 1",
                "markdown": "This is a test document about machine learning and AI.",
                "published_at": "2024-01-15T10:00:00Z",
                "metadata": {"source": "test"}
            },
            {
                "url": "https://example.com/test2",
                "title": "Test Document 2", 
                "markdown": "This document discusses natural language processing and transformers.",
                "published_at": "2024-01-16T10:00:00Z",
                "metadata": {"source": "test"}
            }
        ]
        
        index_request = {"docs": sample_docs}
        
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/index",
                    json=index_request
                )
                
                if response.status_code == 200:
                    data = response.json()
                    indexed_count = data.get("indexed", 0)
                    print(f"  ✅ Indexed {indexed_count} document chunks")
                    self.test_results.append({
                        "test": "Manual Indexing",
                        "status": "PASS",
                        "details": f"Indexed {indexed_count} chunks"
                    })
                else:
                    print(f"  ❌ Indexing failed: HTTP {response.status_code}")
                    self.test_results.append({
                        "test": "Manual Indexing",
                        "status": "FAIL",
                        "details": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                print(f"  ❌ Indexing error: {str(e)}")
                self.test_results.append({
                    "test": "Manual Indexing",
                    "status": "FAIL", 
                    "details": str(e)
                })
    
    async def test_manual_retrieval(self):
        """Test manual retrieval functionality."""
        print("\n🔍 Testing Manual Retrieval...")
        
        retrieve_request = {
            "query": "machine learning",
            "k": 5,
            "recency_boost_days": 14
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/retrieve",
                    json=retrieve_request
                )
                
                if response.status_code == 200:
                    data = response.json()
                    hits_count = len(data.get("hits", []))
                    print(f"  ✅ Retrieved {hits_count} relevant documents")
                    self.test_results.append({
                        "test": "Manual Retrieval", 
                        "status": "PASS",
                        "details": f"Retrieved {hits_count} documents"
                    })
                else:
                    print(f"  ❌ Retrieval failed: HTTP {response.status_code}")
                    self.test_results.append({
                        "test": "Manual Retrieval",
                        "status": "FAIL",
                        "details": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                print(f"  ❌ Retrieval error: {str(e)}")
                self.test_results.append({
                    "test": "Manual Retrieval",
                    "status": "FAIL",
                    "details": str(e)
                })
    
    async def test_end_to_end_chat(self):
        """Test end-to-end chat with automatic tool calling."""
        print("\n💬 Testing End-to-End Chat (with tool calling)...")
        
        # Query that should trigger tool calling
        chat_request = {
            "message": "What are the latest developments in NVIDIA AI chips?",
            "stream": False,
            "force_refresh": True
        }
        
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                start_time = time.time()
                response = await client.post(
                    f"{self.gateway_url}/api/v1/chat",
                    json=chat_request
                )
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get("response", "")
                    sources = data.get("sources", [])
                    tool_calls = data.get("tool_calls", [])
                    
                    print(f"  ✅ Chat completed in {duration:.1f}s")
                    print(f"  📝 Response length: {len(response_text)} chars")
                    print(f"  🔧 Tool calls: {len(tool_calls)}")
                    print(f"  📚 Sources found: {len(sources)}")
                    
                    # Verify response quality
                    has_content = len(response_text) > 50
                    has_tool_calls = len(tool_calls) > 0
                    
                    if has_content and has_tool_calls:
                        self.test_results.append({
                            "test": "End-to-End Chat",
                            "status": "PASS",
                            "details": f"Response: {len(response_text)} chars, Tool calls: {len(tool_calls)}, Sources: {len(sources)}"
                        })
                    else:
                        self.test_results.append({
                            "test": "End-to-End Chat",
                            "status": "PARTIAL",
                            "details": f"Missing tool calls or insufficient content"
                        })
                        
                else:
                    print(f"  ❌ Chat failed: HTTP {response.status_code}")
                    self.test_results.append({
                        "test": "End-to-End Chat",
                        "status": "FAIL",
                        "details": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                print(f"  ❌ Chat error: {str(e)}")
                self.test_results.append({
                    "test": "End-to-End Chat",
                    "status": "FAIL",
                    "details": str(e)
                })
    
    async def test_general_chat(self):
        """Test general chat without tool calling."""
        print("\n🗣️ Testing General Chat (no tool calling)...")
        
        # Query that should NOT trigger tool calling
        chat_request = {
            "message": "Explain how neural networks work in general.",
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    f"{self.gateway_url}/api/v1/chat",
                    json=chat_request
                )
                
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get("response", "")
                    tool_calls = data.get("tool_calls", [])
                    
                    print(f"  ✅ General chat completed")
                    print(f"  📝 Response length: {len(response_text)} chars")
                    print(f"  🔧 Tool calls: {len(tool_calls)} (should be 0)")
                    
                    # Verify no tool calls for general knowledge
                    if len(response_text) > 50 and len(tool_calls) == 0:
                        self.test_results.append({
                            "test": "General Chat",
                            "status": "PASS",
                            "details": f"Response: {len(response_text)} chars, No tool calls"
                        })
                    else:
                        self.test_results.append({
                            "test": "General Chat",
                            "status": "PARTIAL",
                            "details": f"Unexpected tool calls or insufficient content"
                        })
                        
                else:
                    print(f"  ❌ General chat failed: HTTP {response.status_code}")
                    self.test_results.append({
                        "test": "General Chat",
                        "status": "FAIL",
                        "details": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                print(f"  ❌ General chat error: {str(e)}")
                self.test_results.append({
                    "test": "General Chat",
                    "status": "FAIL",
                    "details": str(e)
                })
    
    def print_test_results(self):
        """Print a summary of all test results."""
        print("\n" + "=" * 50)
        print("🏁 Integration Test Results")
        print("=" * 50)
        
        passed = 0
        failed = 0
        partial = 0
        
        for result in self.test_results:
            status_emoji = "✅" if result["status"] == "PASS" else "❌" if result["status"] == "FAIL" else "⚠️"
            print(f"{status_emoji} {result['test']}: {result['status']}")
            print(f"   {result['details']}")
            
            if result["status"] == "PASS":
                passed += 1
            elif result["status"] == "FAIL":
                failed += 1
            else:
                partial += 1
        
        print(f"\nSummary: {passed} passed, {failed} failed, {partial} partial")
        
        if failed == 0:
            print("🎉 All critical tests passed!")
        else:
            print("❌ Some tests failed - check service configuration")


async def main():
    """Run the integration tests."""
    test_suite = WebRAGIntegrationTest()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())