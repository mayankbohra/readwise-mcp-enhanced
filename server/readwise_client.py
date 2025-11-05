"""Readwise API Client with dual API support (v2 Highlights + v3 Reader)"""

import httpx
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ReadwiseClient:
    """Client for interacting with Readwise APIs (v2 and v3)"""

    def __init__(self, token: str):
        self.token = token
        self.v2_base_url = "https://readwise.io/api/v2"
        self.v3_base_url = "https://readwise.io/api/v3"
        self.headers = {"Authorization": f"Token {token}"}

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        api_version: str = "v3"
    ) -> Dict[str, Any]:
        """Make HTTP request to Readwise API"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                raise Exception(f"Readwise API error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                logger.error(f"Request error: {str(e)}")
                raise

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
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List documents from Reader with efficient filtering.

        Args:
            location: Filter by location (new, later, archive, feed)
            category: Filter by category
            limit: Maximum documents to return. Set to None for unlimited.
            updated_after: ISO 8601 timestamp - only fetch documents updated after this time
                          Example: "2025-11-01T00:00:00Z"
                          Useful for incremental syncs

        Returns:
            List of documents
        """
        params = {"pageCursor": None}
        if location:
            params["location"] = location
        if category:
            params["category"] = category
        if updated_after:
            params["updatedAfter"] = updated_after

        all_results = []
        fetch_all = limit is None

        while True:
            response = await self._request("GET", f"{self.v3_base_url}/list", params=params)
            results = response.get("results", [])

            if not results:
                break

            all_results.extend(results)

            # Stop if we've reached the limit
            if not fetch_all and len(all_results) >= limit:
                return all_results[:limit]

            next_cursor = response.get("nextPageCursor")
            if not next_cursor:
                break

            params["pageCursor"] = next_cursor

        return all_results if fetch_all else all_results[:limit]

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
        **filters
    ) -> Dict[str, Any]:
        """
        List highlights with filtering.

        Args:
            page_size: Number of highlights per page (max 1000)
            page: Page number to fetch (ignored if fetch_all=True)
            book_id: Filter by specific book ID
            fetch_all: If True, fetches all pages and returns all results
            **filters: Additional filters (highlighted_at__gt, highlighted_at__lt, etc.)

        Returns:
            Dict with 'results', 'count', and pagination info if fetch_all=False
            Dict with 'results' containing all highlights if fetch_all=True
        """
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

        # Fetch all pages
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
        fetch_all: bool = False
    ) -> Dict[str, Any]:
        """
        Search highlights by text query.

        Args:
            query: Search term (searches highlight text and notes)
            page_size: Number of results per page (ignored if fetch_all=True)
            page: Page number (ignored if fetch_all=True)
            fetch_all: If True, fetches all matching highlights across all pages

        Returns:
            Dict with 'results' list and 'count'
        """
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

        # Fetch all matching results
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

            # Check if there's a next page
            if not response.get("next"):
                break

            current_page += 1

        return {
            "results": all_results,
            "count": len(all_results)
        }

    async def list_books(
        self,
        page_size: int = 100,
        page: int = 1,
        category: Optional[str] = None,
        fetch_all: bool = False,
        **filters
    ) -> Dict[str, Any]:
        """
        List books with metadata.

        Args:
            page_size: Number of books per page
            page: Page number (ignored if fetch_all=True)
            category: Filter by category (books, articles, tweets, podcasts)
            fetch_all: If True, fetches all pages and returns all results
            **filters: Additional filters (last_highlight_at__gt, etc.)

        Returns:
            Dict with 'results', 'count', and pagination info
        """
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

        # Fetch all pages
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

            # Check if there's a next page
            if not response.get("next"):
                break

            current_page += 1

        return {
            "results": all_results,
            "count": len(all_results)
        }

    async def get_book_highlights(self, book_id: int) -> Dict[str, Any]:
        """
        Get ALL highlights from a specific book.

        Args:
            book_id: The ID of the book

        Returns:
            Dict with 'results' list containing all highlights and 'count'
        """
        return await self.list_highlights(book_id=book_id, fetch_all=True)

    async def export_highlights(
        self,
        updated_after: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Export highlights for backup/analysis"""
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

            if not response.get("next"):
                break

            page += 1

        return all_highlights

    async def create_highlight(self, highlights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Manually create highlights"""
        return await self._request("POST", f"{self.v2_base_url}/highlights", json={"highlights": highlights}, api_version="v2")
