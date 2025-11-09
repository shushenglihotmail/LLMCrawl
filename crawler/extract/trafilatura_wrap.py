"""
Trafilatura wrapper for text extraction and content cleaning.
Converts HTML to clean markdown with metadata preservation.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse

try:
    import trafilatura
    from trafilatura.settings import use_config
    from trafilatura import extract_metadata
except ImportError:
    trafilatura = None

logger = logging.getLogger(__name__)

class TrafilaturaExtractor:
    """Wrapper for Trafilatura text extraction and cleaning."""
    
    def __init__(self):
        self.config = self._setup_config()
        
        if not trafilatura:
            logger.warning("Trafilatura not installed - text extraction unavailable")
        else:
            logger.info("Trafilatura extractor initialized")
    
    def _setup_config(self):
        """Setup Trafilatura configuration."""
        if not trafilatura:
            return None
            
        # Create custom configuration
        config = use_config()
        
        # Configure extraction settings
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")
        config.set("DEFAULT", "MIN_EXTRACTED_SIZE", "200")  # Minimum text length
        config.set("DEFAULT", "MIN_OUTPUT_SIZE", "100")
        config.set("DEFAULT", "MIN_DUPLCHECK_SIZE", "100")
        
        # Language detection
        config.set("DEFAULT", "TARGET_LANGUAGE", "en")
        
        return config
    
    async def extract_content(
        self,
        html: str,
        url: str,
        include_formatting: bool = True,
        include_links: bool = True
    ) -> Dict[str, Any]:
        """
        Extract clean text content from HTML.
        
        Args:
            html: HTML content to extract from
            url: Source URL for context
            include_formatting: Whether to preserve formatting
            include_links: Whether to preserve links
            
        Returns:
            Extracted content with metadata
        """
        if not trafilatura:
            logger.error("Trafilatura not available for extraction")
            return {"error": "Trafilatura not installed"}
        
        try:
            # Extract main content as markdown
            markdown_content = trafilatura.extract(
                html,
                output_format="markdown" if include_formatting else "txt",
                config=self.config,
                include_comments=False,
                include_tables=True,
                include_formatting=include_formatting,
                include_links=include_links,
                url=url
            )
            
            if not markdown_content:
                logger.warning(f"No content extracted from {url}")
                return {"error": "No content extracted"}
            
            # Extract metadata
            metadata = extract_metadata(html, fast=False, url=url)
            
            # Extract additional metadata
            extracted_metadata = {}
            if metadata:
                extracted_metadata = {
                    "title": metadata.title or "",
                    "author": metadata.author or "",
                    "description": metadata.description or "",
                    "sitename": metadata.sitename or "",
                    "date": metadata.date.isoformat() if metadata.date else None,
                    "url": metadata.url or url,
                    "hostname": metadata.hostname or "",
                    "language": metadata.language or "",
                    "tags": list(metadata.tags) if metadata.tags else [],
                    "categories": list(metadata.categories) if metadata.categories else []
                }
            
            # Calculate content statistics
            content_stats = self._calculate_content_stats(markdown_content)
            
            # Determine content quality score
            quality_score = self._calculate_quality_score(
                markdown_content, 
                extracted_metadata,
                content_stats
            )
            
            result = {
                "url": url,
                "title": extracted_metadata.get("title", ""),
                "markdown": markdown_content,
                "metadata": extracted_metadata,
                "published_at": extracted_metadata.get("date"),
                "content_stats": content_stats,
                "quality_score": quality_score,
                "extracted_at": datetime.now().isoformat(),
                "extractor": "trafilatura"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Content extraction failed for {url}: {e}")
            return {"error": f"Extraction failed: {e}"}
    
    def _calculate_content_stats(self, content: str) -> Dict[str, int]:
        """Calculate statistics about the extracted content."""
        if not content:
            return {"char_count": 0, "word_count": 0, "line_count": 0}
        
        lines = content.split('\n')
        words = content.split()
        
        return {
            "char_count": len(content),
            "word_count": len(words),
            "line_count": len(lines),
            "paragraph_count": len([line for line in lines if line.strip()])
        }
    
    def _calculate_quality_score(
        self,
        content: str,
        metadata: Dict[str, Any],
        stats: Dict[str, int]
    ) -> float:
        """
        Calculate a quality score for the extracted content.
        Score ranges from 0.0 to 1.0, higher is better.
        """
        score = 0.0
        
        # Content length score (0-0.3)
        word_count = stats.get("word_count", 0)
        if word_count >= 500:
            score += 0.3
        elif word_count >= 200:
            score += 0.2
        elif word_count >= 50:
            score += 0.1
        
        # Metadata completeness score (0-0.3)
        metadata_fields = ["title", "author", "description", "date"]
        filled_fields = sum(1 for field in metadata_fields if metadata.get(field))
        score += (filled_fields / len(metadata_fields)) * 0.3
        
        # Structure score (0-0.2)
        if "# " in content:  # Has headers
            score += 0.1
        if stats.get("paragraph_count", 0) > 3:  # Multiple paragraphs
            score += 0.1
        
        # Date availability (0-0.2)
        if metadata.get("date"):
            score += 0.2
        
        return min(score, 1.0)
    
    async def extract_multiple(
        self,
        html_documents: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        """
        Extract content from multiple HTML documents.
        
        Args:
            html_documents: List of dicts with 'html' and 'url' keys
            
        Returns:
            List of extracted content documents
        """
        if not trafilatura:
            return [{"error": "Trafilatura not installed"}] * len(html_documents)
        
        results = []
        for doc in html_documents:
            html = doc.get("html", "")
            url = doc.get("url", "")
            
            if not html or not url:
                results.append({"error": "Missing HTML or URL"})
                continue
                
            result = await self.extract_content(html, url)
            results.append(result)
        
        return results
    
    def is_content_substantial(self, content: str, min_words: int = 50) -> bool:
        """Check if extracted content meets minimum quality thresholds."""
        if not content:
            return False
            
        word_count = len(content.split())
        return word_count >= min_words
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Trafilatura is working properly."""
        if not trafilatura:
            return {
                "status": "unavailable",
                "service": "trafilatura",
                "error": "Trafilatura not installed"
            }
        
        try:
            # Test extraction on sample HTML
            sample_html = """
            <html>
            <head><title>Test Article</title></head>
            <body>
                <article>
                    <h1>Sample Article</h1>
                    <p>This is a test paragraph with sample content.</p>
                    <p>Another paragraph to test extraction.</p>
                </article>
            </body>
            </html>
            """
            
            result = await self.extract_content(sample_html, "https://test.example.com")
            
            return {
                "status": "healthy" if not result.get("error") else "unhealthy",
                "service": "trafilatura",
                "test_extraction": bool(result.get("markdown")),
                "version": getattr(trafilatura, "__version__", "unknown")
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "trafilatura",
                "error": str(e)
            }

# Global extractor instance
_extractor = None

def get_trafilatura_extractor() -> TrafilaturaExtractor:
    """Get or create the global Trafilatura extractor."""
    global _extractor
    if _extractor is None:
        _extractor = TrafilaturaExtractor()
    return _extractor