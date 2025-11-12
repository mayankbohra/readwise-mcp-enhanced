"""FastMCP Server for Readwise Reader + Highlights Integration"""

import os
import json
import traceback
import asyncio
from typing import Optional, List, Dict, Any
from fastmcp import FastMCP
from readwise_client import ReadwiseClient
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("Readwise MCP Enhanced")

# Get configuration from environment
READWISE_TOKEN = os.getenv("READWISE_TOKEN")
MCP_API_KEY = os.getenv("MCP_API_KEY")

if not READWISE_TOKEN:
    raise ValueError("READWISE_TOKEN environment variable is required")

if not MCP_API_KEY:
    logger.warning("MCP_API_KEY not set - server will run without authentication")

# Initialize Readwise client
client = ReadwiseClient(READWISE_TOKEN)

# Response size limit (100KB)
MAX_RESPONSE_SIZE = 100 * 1024


def format_json_response(data: Dict[str, Any], max_size: int = MAX_RESPONSE_SIZE) -> str:
    """
    Format response data as JSON string with size limits.
    
    Args:
        data: Dictionary to serialize
        max_size: Maximum response size in bytes (default: 100KB)
    
    Returns:
        JSON string, truncated if necessary
    """
    try:
        json_str = json.dumps(data, ensure_ascii=False)
        json_bytes = json_str.encode('utf-8')
        
        # Truncate if too large
        if len(json_bytes) > max_size:
            # Try to truncate the data array if it exists
            if 'results' in data and isinstance(data['results'], list):
                # Calculate how many items we can fit
                base_data = {k: v for k, v in data.items() if k != 'results'}
                base_json = json.dumps(base_data, ensure_ascii=False).encode('utf-8')
                available_size = max_size - len(base_json) - 200  # Reserve space for JSON structure and truncation metadata
                
                if available_size > 0:
                    # Binary search for optimal truncation
                    items = data['results']
                    low, high = 0, len(items)
                    while low < high:
                        mid = (low + high + 1) // 2
                        test_data = {**base_data, 'results': items[:mid]}
                        test_json = json.dumps(test_data, ensure_ascii=False).encode('utf-8')
                        if len(test_json) <= available_size:
                            low = mid
                        else:
                            high = mid - 1
                    
                    if low < len(items):
                        data['results'] = items[:low]
                        data['truncated'] = True
                        data['total_count'] = len(items)
                        json_str = json.dumps(data, ensure_ascii=False)
            else:
                # No results array to truncate, return error message
                json_str = json.dumps({"error": "Response too large", "truncated": True, "message": "Response exceeds maximum size limit"})
        
        return json_str
    except Exception as e:
        logger.error(f"Error formatting JSON response: {e}")
        logger.error(traceback.format_exc())
        # Fallback to simple error response
        try:
            return json.dumps({"error": str(e), "message": "Failed to format response"})
        except:
            return '{"error": "Failed to format response"}'


# ==================== Relevance Scoring and Parallel Fetching ====================

def calculate_relevance_score(item: Dict[str, Any], query_terms: List[str], query_lower: str) -> float:
    """
    Fast relevance scoring function optimized for performance.
    
    Args:
        item: Dictionary containing highlight/document data
        query_terms: Pre-processed query terms (lowercased, split)
        query_lower: Full query string (lowercased)
    
    Returns:
        Relevance score (0.0 to 1.0+)
    """
    score = 0.0
    
    # Get text fields (pre-lowercase for efficiency)
    text = (item.get("text") or "").lower()
    title = (item.get("title") or "").lower()
    note = (item.get("note") or "").lower()
    
    # Check for exact phrase match first (highest priority, early exit optimization)
    if query_lower in text:
        score += 5.0  # Exact phrase match in text
    if query_lower in title:
        score += 15.0  # Exact phrase match in title (3x weight)
    if query_lower in note:
        score += 10.0  # Exact phrase match in note (2x weight)
    
    # Count query term frequency
    for term in query_terms:
        if not term:
            continue
        
        # Term frequency in text (weighted by position - earlier is better)
        text_count = text.count(term)
        if text_count > 0:
            # Weight by position (first 100 chars get 2x, next 200 get 1.5x)
            position_weight = 1.0
            if len(text) > 0:
                first_occurrence = text.find(term)
                if first_occurrence < 100:
                    position_weight = 2.0
                elif first_occurrence < 300:
                    position_weight = 1.5
            score += text_count * position_weight
        
        # Term frequency in title (3x weight)
        title_count = title.count(term)
        if title_count > 0:
            score += title_count * 3.0
        
        # Term frequency in notes (2x weight)
        note_count = note.count(term)
        if note_count > 0:
            score += note_count * 2.0
    
    # Bonus for having all query terms present
    terms_found = sum(1 for term in query_terms if term and (term in text or term in title or term in note))
    if terms_found == len(query_terms) and len(query_terms) > 1:
        score += 2.0  # All terms present bonus
    
    # Normalize score (cap at reasonable maximum)
    return min(score / 10.0, 10.0)  # Normalize and cap


async def fetch_pages_parallel(
    fetch_func,
    query: Optional[str] = None,
    num_pages: int = 5,
    page_size: int = 100,
    batch_size: int = 3,
    rate_limit_delay: float = 0.2,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Fetch multiple pages in parallel with rate limiting.
    
    Args:
        fetch_func: Async function that fetches a single page (takes page, page_size, **kwargs)
        query: Optional query string for relevance scoring
        num_pages: Number of pages to fetch
        page_size: Results per page
        batch_size: Number of pages to fetch concurrently (default: 3)
        rate_limit_delay: Delay between batches (default: 0.2 seconds)
        **kwargs: Additional arguments to pass to fetch_func
    
    Returns:
        List of all results from all pages
    """
    all_results = []
    query_terms = []
    query_lower = ""
    
    # Pre-process query if provided
    if query:
        query_lower = query.lower().strip()
        query_terms = [t.strip() for t in query_lower.split() if t.strip()]
    
    # Fetch pages in batches
    for batch_start in range(1, num_pages + 1, batch_size):
        batch_end = min(batch_start + batch_size, num_pages + 1)
        batch_pages = list(range(batch_start, batch_end))
        
        # Fetch batch pages concurrently
        tasks = [
            fetch_func(page=page, page_size=page_size, **kwargs)
            for page in batch_pages
        ]
        
        try:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process batch results
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning(f"Error fetching page: {result}")
                    continue
                
                if isinstance(result, dict):
                    results = result.get("results", [])
                elif isinstance(result, list):
                    results = result
                else:
                    continue
                
                if not results:
                    continue
                
                all_results.extend(results)
            
            # Rate limiting: delay between batches (not between individual requests)
            if batch_end <= num_pages:
                await asyncio.sleep(rate_limit_delay)
        
        except Exception as e:
            logger.error(f"Error in parallel fetch batch: {e}")
            break
    
    # Score and sort by relevance if query provided
    if query and query_terms and all_results:
        scored_results = [
            (item, calculate_relevance_score(item, query_terms, query_lower))
            for item in all_results
        ]
        # Sort by score descending
        scored_results.sort(key=lambda x: x[1], reverse=True)
        all_results = [item for item, score in scored_results]
    # If no query, results are returned in API order (which may already be by relevance)
    
    return all_results


# ==================== Custom Authentication ====================
# Note: FastMCP 2.0+ handles auth differently
# We'll implement API key validation in the app setup below


# ==================== READER TOOLS (5) ====================

@mcp.tool()
async def reader_save_document(
    url: str,
    tags: Optional[List[str]] = None,
    location: Optional[str] = "later",
    category: Optional[str] = "article"
) -> str:
    """
    Save a document to Readwise Reader.

    Args:
        url: The URL of the document to save
        tags: Optional list of tags to apply
        location: Where to save (new, later, archive, feed)
        category: Document category (article, email, rss, highlight, note, pdf, epub, tweet, video)

    Returns:
        JSON string with save result
    """
    try:
        kwargs = {}
        if tags:
            kwargs["tags"] = tags
        if location:
            kwargs["location"] = location
        if category:
            kwargs["category"] = category

        result = await client.save_document(url, **kwargs)
        return format_json_response({
            "success": True,
            "message": "Document saved successfully",
            "result": result
        })
    except Exception as e:
        logger.error(f"Error saving document: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to save document"})


@mcp.tool()
async def reader_list_documents(
    location: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    site_name: Optional[str] = None,
    limit: int = 20,
    fetch_all: bool = False,
    updated_after: Optional[str] = None,
    with_full_content: bool = False,
    content_max_length: Optional[int] = None,
    max_limit: Optional[int] = 50
) -> str:
    """
    List documents from Readwise Reader with advanced filtering. Returns limited results for context efficiency.

    Args:
        location: Filter by location (new, later, archive, feed)
        category: Filter by category (article, email, rss, etc.)
        author: Filter by author name (case-insensitive partial match)
        site_name: Filter by site name (case-insensitive partial match)
        limit: Maximum documents to return (default: 20). Recommended: 10-30 for context efficiency.
        fetch_all: If True, fetches documents up to max_limit (default: False, not recommended for context efficiency)
        updated_after: ISO 8601 timestamp - only documents updated after this time
                      Example: "2025-11-01T00:00:00Z"
                      Useful for incremental syncs (fetch only new/updated docs)
        with_full_content: Include full document content (warning: uses significant context, not recommended)
        content_max_length: Limit content length per document
        max_limit: Maximum documents to fetch when fetch_all=True (default: 50, use sparingly)

    Returns:
        JSON string with filtered document list (limited to 'limit' for context efficiency)

    Examples:
        - Get recent documents: limit=20
        - Get documents by author: author="sukhad anand", limit=30
        - Get recent articles: updated_after="2025-11-01T00:00:00Z", category="article", limit=20
    """
    try:
        # Parameter validation
        if limit <= 0 or limit > 1000:
            return format_json_response({"error": "limit must be between 1 and 1000"})
        if max_limit is not None and max_limit <= 0:
            return format_json_response({"error": "max_limit must be a positive integer"})
        
        # Determine fetch strategy: fetch more than limit to find best matches
        # For cursor-based pagination, we fetch sequentially but get more results
        if fetch_all and max_limit:
            target_results = min(max_limit, limit * 10)
        else:
            target_results = limit * 5  # Fetch 5x to find best matches
        
        # Fetch documents from API - fetch more than limit for relevance ranking
        documents = await client.list_documents(
            location=location,
            category=category,
            limit=target_results if not fetch_all else None,
            updated_after=updated_after,
            max_limit=target_results if fetch_all else None
        )
        
        # Apply client-side filtering first
        if author:
            author_lower = author.lower()
            documents = [
                doc for doc in documents
                if doc.get("author") and author_lower in doc["author"].lower()
            ]

        if site_name:
            site_lower = site_name.lower()
            documents = [
                doc for doc in documents
                if doc.get("site_name") and site_lower in doc["site_name"].lower()
            ]
        
        # Build query string from filters for relevance scoring (after filtering)
        query_parts = []
        if author:
            query_parts.append(author)
        if site_name:
            query_parts.append(site_name)
        query_str = " ".join(query_parts) if query_parts else None
        
        # Score by relevance if we have filters (helps rank filtered results)
        if query_str and documents:
            query_lower = query_str.lower()
            query_terms = [t.strip() for t in query_lower.split() if t.strip()]
            
            # Score all filtered documents
            scored_docs = [
                (doc, calculate_relevance_score(doc, query_terms, query_lower))
                for doc in documents
            ]
            # Sort by relevance
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            documents = [doc for doc, score in scored_docs]
        
        # Take top N (either most relevant or first N if no scoring)
        documents = documents[:limit]

        # Process content if requested
        if not with_full_content:
            for doc in documents:
                doc.pop("content", None)
        elif content_max_length:
            for doc in documents:
                if "content" in doc and len(doc["content"]) > content_max_length:
                    doc["content"] = doc["content"][:content_max_length] + "..."

        # Build response
        filters_applied = []
        if location:
            filters_applied.append(f"location={location}")
        if category:
            filters_applied.append(f"category={category}")
        if author:
            filters_applied.append(f"author contains '{author}'")
        if site_name:
            filters_applied.append(f"site contains '{site_name}'")
        if updated_after:
            filters_applied.append(f"updated after {updated_after}")

        return format_json_response({
            "count": len(documents),
            "results": documents,
            "filters_applied": filters_applied,
            "limit_applied": limit,
            "fetch_mode": "all" if fetch_all else "paginated"
        })
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to list documents"})


@mcp.tool()
async def reader_update_document(
    document_id: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    summary: Optional[str] = None,
    location: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> str:
    """
    Update document metadata in Readwise Reader.

    Args:
        document_id: The ID of the document to update
        title: New title
        author: New author
        summary: New summary
        location: New location (new, later, archive, feed)
        tags: New tags list

    Returns:
        JSON string with update result
    """
    try:
        updates = {}
        if title:
            updates["title"] = title
        if author:
            updates["author"] = author
        if summary:
            updates["summary"] = summary
        if location:
            updates["location"] = location
        if tags:
            updates["tags"] = tags

        result = await client.update_document(document_id, updates)
        return format_json_response({
            "success": True,
            "message": "Document updated successfully",
            "document_id": document_id,
            "result": result
        })
    except Exception as e:
        logger.error(f"Error updating document: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to update document"})


@mcp.tool()
async def reader_delete_document(document_id: str) -> str:
    """
    Delete a document from Readwise Reader.

    Args:
        document_id: The ID of the document to delete

    Returns:
        Success or error message
    """
    try:
        await client.delete_document(document_id)
        return format_json_response({
            "success": True,
            "message": f"Document {document_id} deleted successfully",
            "document_id": document_id
        })
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to delete document"})


@mcp.tool()
async def reader_list_tags() -> str:
    """
    Get all tags from Readwise Reader.

    Returns:
        JSON string with list of tags
    """
    try:
        tags = await client.list_tags()
        return format_json_response({
            "count": len(tags),
            "results": tags,
            "type": "tags"
        })
    except Exception as e:
        logger.error(f"Error listing tags: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to list tags"})


# ==================== HIGHLIGHTS TOOLS (7) ====================

@mcp.tool()
async def readwise_list_highlights(
    book_id: Optional[int] = None,
    limit: int = 20,
    page_size: int = 20,
    page: int = 1,
    fetch_all: bool = False,
    highlighted_at__gt: Optional[str] = None,
    highlighted_at__lt: Optional[str] = None,
    max_limit: Optional[int] = 50
) -> str:
    """
    List highlights from Readwise with advanced filtering. Returns limited results for context efficiency.

    Args:
        book_id: Filter by specific book ID
        limit: Maximum number of highlights to return (default: 20). Recommended: 10-30 for context efficiency.
        page_size: Number of highlights per page when paginating (default: 20, max 1000, ignored if fetch_all=True)
        page: Page number when paginating (default: 1, ignored if fetch_all=True)
        fetch_all: If True, fetches highlights up to max_limit (default: False, not recommended for context efficiency)
        highlighted_at__gt: Filter highlights after this date (ISO 8601)
        highlighted_at__lt: Filter highlights before this date (ISO 8601)
        max_limit: Maximum highlights to fetch when fetch_all=True (default: 50, use sparingly)

    Returns:
        JSON string with highlights (limited to 'limit' for context efficiency)

    Examples:
        - Get recent highlights: limit=20
        - Get highlights from specific book: book_id=12345, limit=30
        - Get highlights from last week: highlighted_at__gt="2025-11-01T00:00:00Z", limit=20
    """
    try:
        # Parameter validation
        if limit <= 0 or limit > 1000:
            return format_json_response({"error": "limit must be between 1 and 1000"})
        if max_limit is not None and max_limit <= 0:
            return format_json_response({"error": "max_limit must be a positive integer"})
        if page_size <= 0 or page_size > 1000:
            return format_json_response({"error": "page_size must be between 1 and 1000"})
        if page <= 0:
            return format_json_response({"error": "page must be a positive integer"})
        
        filters = {}
        if highlighted_at__gt:
            filters["highlighted_at__gt"] = highlighted_at__gt
        if highlighted_at__lt:
            filters["highlighted_at__lt"] = highlighted_at__lt

        # Determine how many pages to fetch for relevance ranking
        if fetch_all and max_limit:
            target_results = min(max_limit, limit * 10)
        else:
            target_results = limit * 5  # Fetch 5x to find best matches
        
        num_pages = max(3, min(10, (target_results + page_size - 1) // page_size))
        
        # Create fetch function wrapper
        async def fetch_page(page: int, page_size: int, **kwargs):
            result = await client.list_highlights(
                page_size=page_size,
                page=page,
                book_id=book_id,
                fetch_all=False,
                max_limit=None,
                **kwargs
            )
            return result
        
        # Fetch pages in parallel (no query for relevance scoring, just parallel fetch)
        all_highlights = await fetch_pages_parallel(
            fetch_func=fetch_page,
            query=None,  # No query for list_highlights
            num_pages=num_pages,
            page_size=page_size,
            batch_size=3,
            rate_limit_delay=client.rate_limit_delay,
            **filters
        )
        
        # Take top N (already sorted by API relevance, or just take first N)
        highlights = all_highlights[:limit]

        # Optimize response - only return essential fields
        optimized = [
            {
                "id": h.get("id"),
                "text": h.get("text"),
                "note": h.get("note"),
                "book_id": h.get("book_id"),
                "highlighted_at": h.get("highlighted_at")
            }
            for h in highlights
        ]

        return format_json_response({
            "count": len(optimized),
            "results": optimized,
            "limit_applied": limit,
            "book_id": book_id,
            "pages_searched": num_pages if 'num_pages' in locals() else 1,
            "total_fetched": len(all_highlights) if 'all_highlights' in locals() else len(optimized)
        })
    except Exception as e:
        logger.error(f"Error listing highlights: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to list highlights"})


@mcp.tool()
async def readwise_get_daily_review() -> str:
    """
    Get daily review highlights (spaced repetition learning system).

    Returns:
        JSON string with daily review highlights
    """
    try:
        result = await client.get_daily_review()

        # Optimize response
        highlights = result.get("highlights", [])
        optimized = [
            {
                "id": h.get("id"),
                "text": h.get("text"),
                "title": h.get("title"),
                "author": h.get("author"),
                "note": h.get("note")
            }
            for h in highlights
        ]

        return format_json_response({
            "count": len(optimized),
            "results": optimized,
            "type": "daily_review"
        })
    except Exception as e:
        logger.error(f"Error getting daily review: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to get daily review"})


@mcp.tool()
async def readwise_search_highlights(
    query: str,
    limit: int = 20,
    page_size: int = 100,
    fetch_all: bool = False,
    max_limit: Optional[int] = 500
) -> str:
    """
    Search highlights by text query using the MCP endpoint (matches official Readwise MCP behavior).
    
    This tool uses the same MCP endpoint as the official Readwise MCP implementation,
    providing vector/semantic search capabilities for better results.

    Args:
        query: Search term (searches highlight text and notes using vector search)
        limit: Maximum number of results to return (default: 20). Recommended: 10-30 for context efficiency.
        page_size: Not used with MCP endpoint (kept for compatibility)
        fetch_all: Not used with MCP endpoint (kept for compatibility)
        max_limit: Not used with MCP endpoint (kept for compatibility)

    Returns:
        JSON string with matching highlights (results are already ranked by relevance from MCP endpoint)

    Examples:
        - Quick search: query="machine learning", limit=20
        - More results: query="python", limit=50
        - AI search: query="AI artificial intelligence machine learning LLM", limit=30
    """
    try:
        # Parameter validation
        if not query or not query.strip():
            return format_json_response({"error": "query cannot be empty"})
        if limit <= 0 or limit > 1000:
            return format_json_response({"error": "limit must be between 1 and 1000"})
        
        query_clean = query.strip()
        
        # Use MCP endpoint for search (matches official Readwise MCP)
        # Convert simple query to vector search term and add full-text queries for better matching
        result = await client.search_highlights_mcp(
            vector_search_term=query_clean,
            full_text_queries=[
                {"field_name": "highlight_plaintext", "search_term": query_clean},
                {"field_name": "document_title", "search_term": query_clean}
            ]
        )
        
        # Extract results from MCP response
        mcp_results = result.get("results", [])
        
        # Apply limit
        highlights = mcp_results[:limit]
        
        # Format results to match expected structure
        # MCP results have different structure: they include 'id', 'score', and 'attributes'
        formatted_results = []
        for item in highlights:
            # MCP results structure: {id, score, attributes: {highlight_plaintext, document_title, etc.}}
            attrs = item.get("attributes", {})
            formatted_results.append({
                "id": item.get("id"),
                "score": item.get("score"),
                "text": attrs.get("highlight_plaintext", ""),
                "note": attrs.get("highlight_note", ""),
                "title": attrs.get("document_title", ""),
                "author": attrs.get("document_author", ""),
                "category": attrs.get("document_category", ""),
                "highlight_tags": attrs.get("highlight_tags", []),
                "document_tags": attrs.get("document_tags", [])
            })

        return format_json_response({
            "count": len(formatted_results),
            "results": formatted_results,
            "query": query_clean,
            "limit_applied": limit,
            "total_fetched": len(mcp_results),
            "note": f"Used MCP endpoint with vector search, returned top {len(formatted_results)} most relevant results."
        })
    except Exception as e:
        logger.error(f"Error searching highlights: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to search highlights"})


@mcp.tool()
async def search_readwise_highlights(
    vector_search_term: str,
    full_text_queries: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Search Readwise highlights using the MCP endpoint with vector and field-specific full-text search.
    
    This tool matches the official Readwise MCP implementation and provides advanced search capabilities:
    - Vector/semantic search for finding conceptually similar content
    - Field-specific full-text search across document metadata and highlight content
    
    Args:
        vector_search_term: String for vector/semantic search (searches for conceptually similar content)
        full_text_queries: Optional list of field-specific queries (max 8). Each query object should have:
            - field_name: One of "document_author", "document_title", "highlight_note", 
                          "highlight_plaintext", "highlight_tags"
            - search_term: The search term for that specific field
    
    Returns:
        JSON string with results array containing matching highlights with scores and attributes
    
    Examples:
        - Search for GenAI content:
          vector_search_term="generative AI GenAI artificial intelligence"
          full_text_queries=[
            {"field_name": "highlight_plaintext", "search_term": "GenAI"},
            {"field_name": "highlight_plaintext", "search_term": "generative AI"},
            {"field_name": "document_title", "search_term": "AI"}
          ]
    """
    try:
        # Parameter validation
        if not vector_search_term or not vector_search_term.strip():
            return format_json_response({"error": "vector_search_term cannot be empty"})
        
        if full_text_queries is None:
            full_text_queries = []
        
        # Handle case where full_text_queries is passed as a JSON string instead of a list
        if isinstance(full_text_queries, str):
            try:
                full_text_queries = json.loads(full_text_queries)
            except json.JSONDecodeError as e:
                return format_json_response({"error": f"full_text_queries must be a valid JSON list: {str(e)}"})
        
        # Ensure it's a list after parsing
        if not isinstance(full_text_queries, list):
            return format_json_response({"error": "full_text_queries must be a list"})
        
        if len(full_text_queries) > 8:
            return format_json_response({"error": "full_text_queries cannot exceed 8 items"})
        
        # Validate field names
        valid_fields = {
            "document_author",
            "document_title",
            "highlight_note",
            "highlight_plaintext",
            "highlight_tags"
        }
        
        for i, query in enumerate(full_text_queries):
            if not isinstance(query, dict):
                return format_json_response({"error": f"full_text_queries[{i}] must be a dictionary"})
            
            field_name = query.get("field_name")
            search_term = query.get("search_term")
            
            if not field_name:
                return format_json_response({"error": f"full_text_queries[{i}] missing 'field_name'"})
            if not search_term:
                return format_json_response({"error": f"full_text_queries[{i}] missing 'search_term'"})
            
            if field_name not in valid_fields:
                return format_json_response({
                    "error": f"Invalid field_name '{field_name}' in full_text_queries[{i}]. Must be one of: {', '.join(valid_fields)}"
                })
        
        # Call the MCP search endpoint
        result = await client.search_highlights_mcp(
            vector_search_term=vector_search_term.strip(),
            full_text_queries=full_text_queries
        )
        
        # The MCP endpoint returns results directly in the response
        # Format matches the official implementation
        return format_json_response({
            "results": result.get("results", []),
            "count": len(result.get("results", []))
        })
        
    except ValueError as e:
        logger.error(f"Validation error in MCP search: {e}")
        return format_json_response({"error": str(e), "message": "Invalid search parameters"})
    except Exception as e:
        logger.error(f"Error in MCP search: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to search highlights via MCP endpoint"})


@mcp.tool()
async def readwise_list_books(
    category: Optional[str] = None,
    limit: int = 20,
    page_size: int = 100,
    fetch_all: bool = False,
    last_highlight_at__gt: Optional[str] = None,
    max_limit: Optional[int] = 500
) -> str:
    """
    List books with highlight metadata using parallel fetching for low latency.

    Args:
        category: Filter by category (books, articles, tweets, podcasts)
        limit: Maximum number of books to return (default: 20)
        page_size: Number of books per page (default: 100, max 1000)
        fetch_all: If True, fetches more pages up to max_limit (default: False)
        last_highlight_at__gt: Filter books with highlights after this date
        max_limit: Maximum books to fetch when fetch_all=True (default: 500)

    Returns:
        JSON string with books

    Examples:
        - Get books: limit=20
        - Get all articles: category="articles", limit=50
        - Get books with recent highlights: last_highlight_at__gt="2025-11-01T00:00:00Z", limit=30
    """
    try:
        # Parameter validation
        if limit <= 0 or limit > 1000:
            return format_json_response({"error": "limit must be between 1 and 1000"})
        if max_limit is not None and max_limit <= 0:
            return format_json_response({"error": "max_limit must be a positive integer"})
        if page_size <= 0 or page_size > 1000:
            return format_json_response({"error": "page_size must be between 1 and 1000"})
        
        filters = {}
        if last_highlight_at__gt:
            filters["last_highlight_at__gt"] = last_highlight_at__gt

        # Determine how many pages to fetch
        if fetch_all and max_limit:
            target_results = min(max_limit, limit * 10)
        else:
            target_results = limit * 5  # Fetch 5x to find best matches
        
        num_pages = max(3, min(10, (target_results + page_size - 1) // page_size))
        
        # Create fetch function wrapper
        async def fetch_page(page: int, page_size: int, **kwargs):
            result = await client.list_books(
                page_size=page_size,
                page=page,
                category=category,
                fetch_all=False,
                max_limit=None,
                **kwargs
            )
            return result
        
        # Fetch pages in parallel
        all_books = await fetch_pages_parallel(
            fetch_func=fetch_page,
            query=None,  # No query for list_books
            num_pages=num_pages,
            page_size=page_size,
            batch_size=3,
            rate_limit_delay=client.rate_limit_delay,
            **filters
        )
        
        # Take top N
        books = all_books[:limit]

        # Optimize response
        optimized = [
            {
                "id": b.get("id"),
                "title": b.get("title"),
                "author": b.get("author"),
                "category": b.get("category"),
                "num_highlights": b.get("num_highlights")
            }
            for b in books
        ]

        return format_json_response({
            "count": len(optimized),
            "results": optimized,
            "category": category,
            "limit_applied": limit,
            "pages_searched": num_pages,
            "total_fetched": len(all_books)
        })
    except Exception as e:
        logger.error(f"Error listing books: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to list books"})


@mcp.tool()
async def readwise_get_book_highlights(book_id: int, max_limit: Optional[int] = 5000) -> str:
    """
    Get highlights from a specific book (automatically fetches multiple pages up to limit).

    Args:
        book_id: The ID of the book to get highlights from
        max_limit: Maximum highlights to fetch (default: 5000)

    Returns:
        JSON string with book highlights

    Example:
        - Get highlights from book: book_id=123456, max_limit=1000
    """
    try:
        # Parameter validation
        if book_id <= 0:
            return format_json_response({"error": "book_id must be a positive integer"})
        if max_limit is not None and max_limit <= 0:
            return format_json_response({"error": "max_limit must be a positive integer"})
        
        # This automatically fetches pages up to max_limit
        result = await client.get_book_highlights(book_id, max_limit=max_limit)

        highlights = result.get("results", [])
        optimized = [
            {
                "id": h.get("id"),
                "text": h.get("text"),
                "note": h.get("note"),
                "location": h.get("location"),
                "highlighted_at": h.get("highlighted_at")
            }
            for h in highlights
        ]

        total_count = result.get("count", len(optimized))
        return format_json_response({
            "count": total_count,
            "results": optimized,
            "book_id": book_id,
            "fetch_mode": "all pages"
        })
    except Exception as e:
        logger.error(f"Error getting book highlights: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to get book highlights"})


@mcp.tool()
async def readwise_export_highlights(
    updated_after: Optional[str] = None,
    include_deleted: bool = False,
    max_results: Optional[int] = 5000
) -> str:
    """
    Bulk export highlights for analysis and backup with rate limiting.

    This tool automatically fetches multiple pages of highlights up to max_results.
    For large libraries, use updated_after for incremental syncs.

    Args:
        updated_after: Export only highlights updated after this date (ISO 8601 format)
                      Example: "2025-11-01T00:00:00Z"
                      Tip: Use this for incremental syncs after initial full export
        include_deleted: Include deleted highlights in export
        max_results: Maximum number of highlights to export (default: 5000)
                    Set higher for larger exports, but be aware of rate limits

    Returns:
        JSON string with exported highlights

    Examples:
        - Export recent highlights: max_results=1000
        - Incremental since Nov 1: updated_after="2025-11-01T00:00:00Z", max_results=10000
        - Last week's changes: updated_after="2025-11-28T00:00:00Z"

    Note: Large exports may take time due to rate limiting delays between API calls
    """
    try:
        # Parameter validation
        if max_results is not None and max_results <= 0:
            return format_json_response({"error": "max_results must be a positive integer"})
        
        # Export fetches pages up to max_results with rate limiting
        highlights = await client.export_highlights(
            updated_after=updated_after,
            include_deleted=include_deleted,
            max_limit=max_results
        )

        # Optimize response - include more useful fields
        optimized = [
            {
                "id": h.get("id"),
                "text": h.get("text"),
                "title": h.get("title"),
                "author": h.get("author"),
                "book_id": h.get("book_id"),
                "note": h.get("note"),
                "highlighted_at": h.get("highlighted_at"),
                "updated": h.get("updated")
            }
            for h in highlights
        ]

        return format_json_response({
            "count": len(optimized),
            "results": optimized,
            "updated_after": updated_after,
            "include_deleted": include_deleted,
            "max_results": max_results
        })
    except Exception as e:
        logger.error(f"Error exporting highlights: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to export highlights"})


@mcp.tool()
async def readwise_create_highlight(
    text: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    note: Optional[str] = None,
    category: str = "books",
    highlighted_at: Optional[str] = None
) -> str:
    """
    Manually create a highlight in Readwise.

    Args:
        text: The highlight text (required)
        title: Book/article title
        author: Author name
        note: Your note on the highlight
        category: Category (books, articles, tweets, podcasts)
        highlighted_at: When it was highlighted (ISO 8601)

    Returns:
        JSON string with creation result
    """
    try:
        highlight_data = {"text": text}
        if title:
            highlight_data["title"] = title
        if author:
            highlight_data["author"] = author
        if note:
            highlight_data["note"] = note
        if category:
            highlight_data["category"] = category
        if highlighted_at:
            highlight_data["highlighted_at"] = highlighted_at

        result = await client.create_highlight([highlight_data])
        return format_json_response({
            "success": True,
            "message": "Highlight created successfully",
            "result": result
        })
    except Exception as e:
        logger.error(f"Error creating highlight: {e}")
        logger.error(traceback.format_exc())
        return format_json_response({"error": str(e), "message": "Failed to create highlight"})


# ==================== Server Entry Point ====================

def create_app():
    """Create the ASGI app with authentication wrapper"""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import JSONResponse
    from starlette.routing import Route, Mount

    async def health_check(request):
        return JSONResponse({
            "status": "healthy",
            "service": "readwise-mcp-enhanced",
            "version": "1.0.0",
            "authentication": "enabled" if MCP_API_KEY else "disabled"
        })

    async def auth_middleware(request, call_next):
        # Skip auth for health check and OAuth discovery endpoints
        if request.url.path in ["/health", "/.well-known/oauth-protected-resource",
                                "/.well-known/oauth-authorization-server", "/register"]:
            return await call_next(request)

        # Check API key if configured
        if MCP_API_KEY:
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    {"error": "Missing or invalid Authorization header"},
                    status_code=401
                )

            token = auth_header.replace("Bearer ", "")
            if token != MCP_API_KEY:
                return JSONResponse(
                    {"error": "Invalid API key"},
                    status_code=401
                )

        return await call_next(request)

    # Get the FastMCP ASGI app
    mcp_app = mcp.http_app()

    # Create wrapper app with auth and CORS
    # IMPORTANT: Pass the FastMCP app's lifespan to Starlette
    # FastMCP's http_app() expects to handle requests at its root
    # So we mount it at / and it will handle /mcp endpoint internally
    app = Starlette(
        routes=[
            Route("/health", health_check, methods=["GET", "HEAD"]),
            Mount("/", mcp_app)  # FastMCP handles /mcp internally
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["https://claude.ai", "https://claude.com", "https://*.anthropic.com"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ],
        lifespan=mcp_app.lifespan  # Fix: Pass FastMCP's lifespan manager
    )

    # Add auth middleware
    @app.middleware("http")
    async def add_auth(request, call_next):
        return await auth_middleware(request, call_next)

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting Remote Readwise MCP server on {host}:{port}")
    logger.info(f"Authentication: {'Enabled' if MCP_API_KEY else 'Disabled (WARNING: Not secure for production)'}")
    
    # Log registered tools for debugging
    try:
        # FastMCP stores tools in mcp._tools or similar
        # Try to access registered tools
        if hasattr(mcp, '_tools'):
            tool_names = [name for name in mcp._tools.keys()]
            logger.info(f"Registered {len(tool_names)} tools: {', '.join(sorted(tool_names))}")
        elif hasattr(mcp, 'tools'):
            tool_names = [name for name in mcp.tools.keys()]
            logger.info(f"Registered {len(tool_names)} tools: {', '.join(sorted(tool_names))}")
        else:
            # Try to get tools from the app after creation
            logger.info("Tool registration will be verified after app creation")
    except Exception as e:
        logger.warning(f"Could not list registered tools: {e}")

    # Create and run the app
    app = create_app()
    
    # Verify search_readwise_highlights is registered
    try:
        # Check if the function exists and is registered
        if hasattr(mcp, '_tools') and 'search_readwise_highlights' in mcp._tools:
            logger.info("✓ search_readwise_highlights is registered")
        elif hasattr(mcp, 'tools') and 'search_readwise_highlights' in mcp.tools:
            logger.info("✓ search_readwise_highlights is registered")
        else:
            logger.warning("⚠ search_readwise_highlights may not be registered - check tool registration")
    except Exception as e:
        logger.warning(f"Could not verify search_readwise_highlights registration: {e}")
    
    uvicorn.run(app, host=host, port=port)
