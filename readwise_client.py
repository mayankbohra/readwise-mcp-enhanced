"""Readwise API Client with dual API support (v2 Highlights + v3 Reader)"""

import httpx
from typing import Optional, Dict, Any, List
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

# Configuration from environment variables
RATE_LIMIT_DELAY = float(os.getenv("READWISE_RATE_LIMIT_DELAY", "0.2"))  # Default 0.2 seconds
MAX_FETCH_LIMIT = int(os.getenv("READWISE_MAX_FETCH_LIMIT", "5000"))  # Default 5000 items


class ReadwiseClient:
    """Client for interacting with Readwise APIs (v2 and v3)"""

    def __init__(self, token: str, rate_limit_delay: float = None, max_fetch_limit: int = None):
        self.token = token
        self.v2_base_url = "https://readwise.io/api/v2"
        self.v3_base_url = "https://readwise.io/api/v3"
        self.headers = {"Authorization": f"Token {token}"}
        self.rate_limit_delay = rate_limit_delay if rate_limit_delay is not None else RATE_LIMIT_DELAY
        self.max_fetch_limit = max_fetch_limit if max_fetch_limit is not None else MAX_FETCH_LIMIT

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        api_version: str = "v3"
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Readwise API with rate limit retry logic.
        
        Implements exponential backoff for 429 (rate limit) errors.
        """
        max_retries = 3
        retry_count = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while retry_count <= max_retries:
                try:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        params=params,
                        json=json
                    )
                    
                    # Handle rate limit (429) with exponential backoff
                    if response.status_code == 429:
                        if retry_count < max_retries:
                            wait_time = (2 ** retry_count) * self.rate_limit_delay  # Exponential backoff
                            logger.warning(f"Rate limit hit (429). Retrying in {wait_time:.2f}s (attempt {retry_count + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            retry_count += 1
                            continue
                        else:
                            logger.error(f"Rate limit exceeded after {max_retries} retries")
                            raise Exception(f"Readwise API rate limit exceeded. Please try again later.")
                    
                    response.raise_for_status()
                    return response.json()
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # This shouldn't happen due to the check above, but handle it anyway
                        if retry_count < max_retries:
                            wait_time = (2 ** retry_count) * self.rate_limit_delay
                            logger.warning(f"Rate limit hit (429). Retrying in {wait_time:.2f}s (attempt {retry_count + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            retry_count += 1
                            continue
                    logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                    raise Exception(f"Readwise API error: {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    logger.error(f"Request error: {str(e)}")
                    raise
            
            # Should never reach here, but just in case
            raise Exception("Request failed after retries")

    # ==================== Reader API (v3) ====================

    async def save_document(self, url: str, **kwargs) -> Dict[str, Any]:
        """Save a document to Reader"""
        data = {"url": url, **kwargs}
        return await self._request("POST", f"{self.v3_base_url}/save", json=data)

    async def list_documents(
        self,
        location: Optional[str] = None,
        category: Optional[str] = None,
        limit: Optional[int] = 20,
        updated_after: Optional[str] = None,
        max_limit: Optional[int] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List documents from Reader with efficient filtering.

        Args:
            location: Filter by location (new, later, archive, feed)
            category: Filter by category
            limit: Maximum documents to return. Set to None for unlimited (respects max_limit).
            updated_after: ISO 8601 timestamp - only fetch documents updated after this time
                          Example: "2025-11-01T00:00:00Z"
                          Useful for incremental syncs
            max_limit: Maximum documents to fetch even if limit=None (default: 1000)

        Returns:
            List of documents
        """
        if max_limit is None:
            max_limit = 1000  # Default max limit for documents
        
        params = {"pageCursor": None}
        if location:
            params["location"] = location
        if category:
            params["category"] = category
        if updated_after:
            params["updatedAfter"] = updated_after

        all_results = []
        fetch_all = limit is None
        effective_limit = limit if limit is not None else max_limit

        while True:
            response = await self._request("GET", f"{self.v3_base_url}/list", params=params)
            results = response.get("results", [])

            if not results:
                break

            all_results.extend(results)

            # Stop if we've reached the effective limit
            if len(all_results) >= effective_limit:
                return all_results[:effective_limit]

            # Add delay between pagination requests
            await asyncio.sleep(self.rate_limit_delay)

            next_cursor = response.get("nextPageCursor")
            if not next_cursor:
                break

            params["pageCursor"] = next_cursor

        return all_results[:effective_limit] if effective_limit else all_results

    async def update_document(self, document_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a document in Reader"""
        return await self._request("PATCH", f"{self.v3_base_url}/documents/{document_id}", json=updates)

    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """Delete a document from Reader"""
        return await self._request("DELETE", f"{self.v3_base_url}/documents/{document_id}")

    async def list_tags(self) -> List[str]:
        """Get all tags from Reader"""
        response = await self._request("GET", f"{self.v3_base_url}/tags")
        return response.get("tags", [])

    # ==================== Highlights API (v2) ====================

    async def list_highlights(
        self,
        page_size: int = 100,
        page: int = 1,
        book_id: Optional[int] = None,
        fetch_all: bool = False,
        max_limit: Optional[int] = None,
        **filters
    ) -> Dict[str, Any]:
        """
        List highlights with filtering.

        Args:
            page_size: Number of highlights per page (max 1000)
            page: Page number to fetch (ignored if fetch_all=True)
            book_id: Filter by specific book ID
            fetch_all: If True, fetches all pages up to max_limit
            max_limit: Maximum highlights to fetch even if fetch_all=True (default: 5000)
            **filters: Additional filters (highlighted_at__gt, highlighted_at__lt, etc.)

        Returns:
            Dict with 'results', 'count', and pagination info if fetch_all=False
            Dict with 'results' containing highlights (up to max_limit) if fetch_all=True
        """
        if max_limit is None:
            max_limit = 5000  # Default max limit for highlights
        
        if not fetch_all:
            # Single page fetch
            params = {
                "page_size": page_size,
                "page": page
            }
            if book_id:
                params["book_id"] = book_id
            params.update(filters)
            return await self._request("GET", f"{self.v2_base_url}/highlights", params=params, api_version="v2")

        # Fetch all pages up to max_limit
        all_results = []
        current_page = 1
        while True:
            params = {
                "page_size": 1000,  # Max page size
                "page": current_page
            }
            if book_id:
                params["book_id"] = book_id
            params.update(filters)

            response = await self._request("GET", f"{self.v2_base_url}/highlights", params=params, api_version="v2")
            results = response.get("results", [])

            if not results:
                break

            all_results.extend(results)

            # Stop if we've reached the max limit
            if len(all_results) >= max_limit:
                all_results = all_results[:max_limit]
                break

            # Add delay between pagination requests
            await asyncio.sleep(self.rate_limit_delay)

            # Check if there's a next page
            if not response.get("next"):
                break

            current_page += 1

        return {
            "results": all_results,
            "count": len(all_results)
        }

    async def get_daily_review(self) -> Dict[str, Any]:
        """Get daily review highlights (spaced repetition)"""
        return await self._request("GET", f"{self.v2_base_url}/review", api_version="v2")

    async def search_highlights(
        self,
        query: str,
        page_size: int = 100,
        page: int = 1,
        fetch_all: bool = False,
        max_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Search highlights by text query.

        Args:
            query: Search term (searches highlight text and notes)
            page_size: Number of results per page (ignored if fetch_all=True)
            page: Page number (ignored if fetch_all=True)
            fetch_all: If True, fetches all matching highlights up to max_limit
            max_limit: Maximum highlights to fetch even if fetch_all=True (default: 5000)

        Returns:
            Dict with 'results' list and 'count'
        """
        if max_limit is None:
            max_limit = 5000  # Default max limit for highlights
        
        if not fetch_all:
            # Single page search
            params = {
                "q": query,
                "page_size": page_size,
                "page": page
            }
            response = await self._request("GET", f"{self.v2_base_url}/highlights", params=params, api_version="v2")
            return {
                "results": response.get("results", []),
                "count": len(response.get("results", []))
            }

        # Fetch all matching results up to max_limit
        all_results = []
        current_page = 1
        while True:
            params = {
                "q": query,
                "page_size": 1000,  # Max page size
                "page": current_page
            }
            response = await self._request("GET", f"{self.v2_base_url}/highlights", params=params, api_version="v2")
            results = response.get("results", [])

            if not results:
                break

            all_results.extend(results)

            # Stop if we've reached the max limit
            if len(all_results) >= max_limit:
                all_results = all_results[:max_limit]
                break

            # Add delay between pagination requests
            await asyncio.sleep(self.rate_limit_delay)

            # Check if there's a next page
            if not response.get("next"):
                break

            current_page += 1

        return {
            "results": all_results,
            "count": len(all_results)
        }

    async def _mcp_request(
        self,
        method: str,
        url: str,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Readwise MCP API endpoint with X-Access-Token header.
        
        MCP endpoints use X-Access-Token instead of Authorization header.
        
        Args:
            method: HTTP method (POST, GET, etc.)
            url: Full URL to request
            json: JSON payload for POST requests
            
        Returns:
            Response JSON data
        """
        max_retries = 3
        retry_count = 0
        
        # MCP endpoints use X-Access-Token header
        mcp_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Access-Token": self.token
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while retry_count <= max_retries:
                try:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=mcp_headers,
                        json=json
                    )
                    
                    # Handle rate limit (429) with exponential backoff
                    if response.status_code == 429:
                        if retry_count < max_retries:
                            wait_time = (2 ** retry_count) * self.rate_limit_delay
                            logger.warning(f"Rate limit hit (429). Retrying in {wait_time:.2f}s (attempt {retry_count + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            retry_count += 1
                            continue
                        else:
                            logger.error(f"Rate limit exceeded after {max_retries} retries")
                            raise Exception(f"Readwise API rate limit exceeded. Please try again later.")
                    
                    response.raise_for_status()
                    return response.json()
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        if retry_count < max_retries:
                            wait_time = (2 ** retry_count) * self.rate_limit_delay
                            logger.warning(f"Rate limit hit (429). Retrying in {wait_time:.2f}s (attempt {retry_count + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            retry_count += 1
                            continue
                    logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                    raise Exception(f"Readwise MCP API error: {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    logger.error(f"Request error: {str(e)}")
                    raise
            
            raise Exception("Request failed after retries")

    async def search_highlights_mcp(
        self,
        vector_search_term: str,
        full_text_queries: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Search highlights using Readwise MCP endpoint with vector and full-text search.
        
        This method uses the specialized MCP endpoint that supports:
        - Vector/semantic search via vector_search_term
        - Field-specific full-text search via full_text_queries
        
        Args:
            vector_search_term: String for vector/semantic search
            full_text_queries: Optional list of query objects, each with:
                - field_name: One of document_author, document_title, highlight_note, 
                              highlight_plaintext, highlight_tags
                - search_term: The search term for that field
                Maximum 8 queries allowed.
        
        Returns:
            Dict with 'results' list containing highlight matches
        """
        if full_text_queries is None:
            full_text_queries = []
        
        if len(full_text_queries) > 8:
            raise ValueError("full_text_queries cannot exceed 8 items")
        
        # Validate field names
        valid_fields = {
            "document_author",
            "document_title", 
            "highlight_note",
            "highlight_plaintext",
            "highlight_tags"
        }
        
        for query in full_text_queries:
            field_name = query.get("field_name")
            if field_name not in valid_fields:
                raise ValueError(f"Invalid field_name: {field_name}. Must be one of {valid_fields}")
        
        payload = {
            "vector_search_term": vector_search_term,
            "full_text_queries": full_text_queries
        }
        
        # MCP endpoint uses base URL without version
        base_url = "https://readwise.io"
        response = await self._mcp_request(
            "POST",
            f"{base_url}/api/mcp/highlights",
            json=payload
        )
        
        return response

    async def list_books(
        self,
        page_size: int = 100,
        page: int = 1,
        category: Optional[str] = None,
        fetch_all: bool = False,
        max_limit: Optional[int] = None,
        **filters
    ) -> Dict[str, Any]:
        """
        List books with metadata.

        Args:
            page_size: Number of books per page
            page: Page number (ignored if fetch_all=True)
            category: Filter by category (books, articles, tweets, podcasts)
            fetch_all: If True, fetches all pages up to max_limit
            max_limit: Maximum books to fetch even if fetch_all=True (default: 1000)
            **filters: Additional filters (last_highlight_at__gt, etc.)

        Returns:
            Dict with 'results', 'count', and pagination info
        """
        if max_limit is None:
            max_limit = 1000  # Default max limit for books
        
        if not fetch_all:
            # Single page fetch
            params = {
                "page_size": page_size,
                "page": page
            }
            if category:
                params["category"] = category
            params.update(filters)
            return await self._request("GET", f"{self.v2_base_url}/books", params=params, api_version="v2")

        # Fetch all pages up to max_limit
        all_results = []
        current_page = 1
        while True:
            params = {
                "page_size": 1000,  # Max page size
                "page": current_page
            }
            if category:
                params["category"] = category
            params.update(filters)

            response = await self._request("GET", f"{self.v2_base_url}/books", params=params, api_version="v2")
            results = response.get("results", [])

            if not results:
                break

            all_results.extend(results)

            # Stop if we've reached the max limit
            if len(all_results) >= max_limit:
                all_results = all_results[:max_limit]
                break

            # Add delay between pagination requests
            await asyncio.sleep(self.rate_limit_delay)

            # Check if there's a next page
            if not response.get("next"):
                break

            current_page += 1

        return {
            "results": all_results,
            "count": len(all_results)
        }

    async def get_book_highlights(self, book_id: int, max_limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Get highlights from a specific book.

        Args:
            book_id: The ID of the book
            max_limit: Maximum highlights to fetch (default: 5000)

        Returns:
            Dict with 'results' list containing highlights and 'count'
        """
        return await self.list_highlights(book_id=book_id, fetch_all=True, max_limit=max_limit)

    async def export_highlights(
        self,
        updated_after: Optional[str] = None,
        include_deleted: bool = False,
        max_limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Export highlights for backup/analysis.
        
        Args:
            updated_after: Only export highlights updated after this date (ISO 8601)
            include_deleted: Include deleted highlights in export
            max_limit: Maximum highlights to export (default: 10000)
        
        Returns:
            List of highlight dictionaries
        """
        if max_limit is None:
            max_limit = 10000  # Default max limit for exports
        
        params = {}
        if updated_after:
            params["updatedAfter"] = updated_after
        if include_deleted:
            params["deleted"] = "true"

        all_highlights = []
        page = 1

        while True:
            params["page"] = page
            params["page_size"] = 1000
            response = await self._request("GET", f"{self.v2_base_url}/export", params=params, api_version="v2")

            results = response.get("results", [])
            if not results:
                break

            all_highlights.extend(results)

            # Stop if we've reached the max limit
            if len(all_highlights) >= max_limit:
                all_highlights = all_highlights[:max_limit]
                break

            # Add delay between pagination requests
            await asyncio.sleep(self.rate_limit_delay)

            if not response.get("next"):
                break

            page += 1

        return all_highlights

    async def create_highlight(self, highlights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Manually create highlights"""
        return await self._request("POST", f"{self.v2_base_url}/highlights", json={"highlights": highlights}, api_version="v2")
