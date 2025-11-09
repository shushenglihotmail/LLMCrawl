"""
Robots.txt parsing and respect utilities.
Handles robots.txt compliance and crawling permissions.
"""

import os
import logging
from typing import Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import asyncio

try:
    from urllib.robotparser import RobotFileParser
except ImportError:
    RobotFileParser = None

import httpx

logger = logging.getLogger(__name__)

class RobotsChecker:
    """Robots.txt compliance checker with caching."""
    
    def __init__(self):
        self.respect_robots = os.getenv("RESPECT_ROBOTS", "true").lower() == "true"
        self.user_agent = os.getenv("USER_AGENT", "WebRAG/1.0")
        self.cache_duration = timedelta(hours=24)  # Cache robots.txt for 24 hours
        self.timeout = 10.0
        
        # Cache for robots.txt content
        self._robots_cache: Dict[str, Dict[str, Any]] = {}
        self._blocked_domains: Set[str] = set()
        
        logger.info(f"Robots checker initialized (respect_robots={self.respect_robots})")
    
    async def can_crawl(self, url: str) -> bool:
        """
        Check if a URL can be crawled according to robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if crawling is allowed, False otherwise
        """
        if not self.respect_robots:
            return True
            
        try:
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            
            # Check if domain is known to be blocked
            if domain in self._blocked_domains:
                return False
            
            # Get robots.txt for this domain
            robots_parser = await self._get_robots_parser(domain)
            
            if not robots_parser:
                # If we can't fetch robots.txt, assume crawling is allowed
                return True
            
            # Check if the specific URL is allowed
            can_fetch = robots_parser.can_fetch(self.user_agent, url)
            
            if not can_fetch:
                logger.info(f"Crawling blocked by robots.txt: {url}")
                
            return can_fetch
            
        except Exception as e:
            logger.error(f"Error checking robots.txt for {url}: {e}")
            # In case of error, err on the side of caution and allow crawling
            return True
    
    async def filter_allowed_urls(self, urls: list[str]) -> list[str]:
        """
        Filter a list of URLs to only include those allowed by robots.txt.
        
        Args:
            urls: List of URLs to filter
            
        Returns:
            Filtered list of allowed URLs
        """
        if not self.respect_robots:
            return urls
        
        allowed_urls = []
        
        # Group URLs by domain for efficient checking
        domain_urls: Dict[str, list[str]] = {}
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = f"{parsed.scheme}://{parsed.netloc}"
                
                if domain not in domain_urls:
                    domain_urls[domain] = []
                domain_urls[domain].append(url)
            except:
                # If URL parsing fails, skip it
                continue
        
        # Check each domain
        for domain, domain_url_list in domain_urls.items():
            if domain in self._blocked_domains:
                continue
                
            robots_parser = await self._get_robots_parser(domain)
            
            if not robots_parser:
                # If no robots.txt, allow all URLs from this domain
                allowed_urls.extend(domain_url_list)
                continue
            
            # Check each URL from this domain
            for url in domain_url_list:
                try:
                    if robots_parser.can_fetch(self.user_agent, url):
                        allowed_urls.append(url)
                except:
                    # In case of error, include the URL
                    allowed_urls.append(url)
        
        logger.info(f"Filtered {len(urls)} URLs to {len(allowed_urls)} allowed URLs")
        return allowed_urls
    
    async def _get_robots_parser(self, domain: str) -> Optional[RobotFileParser]:
        """Get cached or fetch robots.txt parser for a domain."""
        if not RobotFileParser:
            logger.warning("urllib.robotparser not available")
            return None
            
        # Check cache first
        if domain in self._robots_cache:
            cache_entry = self._robots_cache[domain]
            if datetime.now() - cache_entry["cached_at"] < self.cache_duration:
                return cache_entry["parser"]
        
        # Fetch robots.txt
        robots_url = urljoin(domain, "/robots.txt")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(robots_url)
                
                if response.status_code == 200:
                    robots_content = response.text
                    
                    # Parse robots.txt
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    
                    # Set content directly instead of reading from URL
                    parser_lines = robots_content.splitlines()
                    for line in parser_lines:
                        parser.modified()  # Mark as modified so it doesn't try to read from URL
                    
                    # Manually parse the content
                    try:
                        parser.read()
                    except:
                        # If reading fails, create a simple parser
                        parser = self._create_simple_parser(robots_content)
                    
                    # Cache the result
                    self._robots_cache[domain] = {
                        "parser": parser,
                        "cached_at": datetime.now()
                    }
                    
                    return parser
                    
                elif response.status_code == 404:
                    # No robots.txt file - allow everything
                    logger.debug(f"No robots.txt found for {domain}")
                    return None
                    
                else:
                    logger.warning(f"Failed to fetch robots.txt for {domain}: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching robots.txt for {domain}: {e}")
            return None
    
    def _create_simple_parser(self, robots_content: str) -> Optional[RobotFileParser]:
        """Create a simple robots parser from content."""
        try:
            # Create a minimal parser that respects basic disallow rules
            parser = RobotFileParser()
            
            # Simple parsing logic for critical rules
            lines = robots_content.splitlines()
            user_agent_section = False
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                if line.lower().startswith('user-agent:'):
                    ua = line.split(':', 1)[1].strip()
                    user_agent_section = (ua == '*' or ua.lower() == self.user_agent.lower())
                    
                elif user_agent_section and line.lower().startswith('disallow:'):
                    path = line.split(':', 1)[1].strip()
                    if path == '/':
                        # Complete disallow - mark domain as blocked
                        return None
            
            return parser
            
        except Exception as e:
            logger.error(f"Error creating simple parser: {e}")
            return None
    
    def get_crawl_delay(self, domain: str) -> float:
        """Get the crawl delay for a domain from robots.txt."""
        if not self.respect_robots or domain not in self._robots_cache:
            return 0.0
            
        try:
            parser = self._robots_cache[domain]["parser"]
            if parser:
                delay = parser.crawl_delay(self.user_agent)
                return float(delay) if delay else 0.0
        except:
            pass
            
        return 0.0
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if robots checker is working properly."""
        return {
            "status": "healthy",
            "service": "robots_checker",
            "respect_robots": self.respect_robots,
            "user_agent": self.user_agent,
            "cached_domains": len(self._robots_cache),
            "blocked_domains": len(self._blocked_domains),
            "robotparser_available": RobotFileParser is not None
        }

# Global robots checker
_robots_checker = None

def get_robots_checker() -> RobotsChecker:
    """Get or create the global robots checker."""
    global _robots_checker
    if _robots_checker is None:
        _robots_checker = RobotsChecker()
    return _robots_checker