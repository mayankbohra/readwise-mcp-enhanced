"""
Comprehensive test script for all Readwise MCP tools.
Tests against locally running server at http://0.0.0.0:8000
"""

import asyncio
import sys
from readwise_client import ReadwiseClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def log_test(test_name: str):
    """Log test start"""
    print(f"\n{BLUE}[TEST]{RESET} {test_name}")

def log_success(message: str):
    """Log success"""
    print(f"{GREEN}✓{RESET} {message}")

def log_error(message: str):
    """Log error"""
    print(f"{RED}✗{RESET} {message}")

def log_warning(message: str):
    """Log warning"""
    print(f"{YELLOW}⚠{RESET} {message}")


async def test_reader_api_tools(client: ReadwiseClient):
    """Test all Reader API (v3) tools"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Testing Reader API (v3) Tools{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    # Test 1: List documents (basic)
    log_test("list_documents - basic (limit=5)")
    try:
        docs = await client.list_documents(limit=5)
        log_success(f"Returned {len(docs)} documents")
        if len(docs) > 0:
            log_success(f"Sample: {docs[0].get('title', 'No title')[:50]}")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 2: List documents with filters
    log_test("list_documents - with location filter")
    try:
        docs = await client.list_documents(location="new", limit=3)
        log_success(f"Returned {len(docs)} documents from 'new' location")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 3: List documents unlimited
    log_test("list_documents - unlimited (limit=None)")
    try:
        docs = await client.list_documents(limit=None)
        log_success(f"Returned {len(docs)} documents (all pages)")
        log_warning(f"This fetched ALL documents across all pages")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 4: List tags
    log_test("list_tags")
    try:
        tags = await client.list_tags()
        log_success(f"Returned {len(tags)} tags")
        if tags:
            log_success(f"Sample tags: {tags[:5]}")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_highlights_api_tools(client: ReadwiseClient):
    """Test all Highlights API (v2) tools"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Testing Highlights API (v2) Tools{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    # Test 1: List highlights (basic)
    log_test("list_highlights - basic (page_size=5)")
    try:
        result = await client.list_highlights(page_size=5, page=1, fetch_all=False)
        highlights = result.get("results", [])
        log_success(f"Returned {len(highlights)} highlights")
        if highlights:
            log_success(f"Sample: {highlights[0].get('text', '')[:50]}...")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 2: List highlights - fetch_all
    log_test("list_highlights - fetch_all=True")
    try:
        result = await client.list_highlights(page_size=100, fetch_all=True)
        highlights = result.get("results", [])
        count = result.get("count", len(highlights))
        log_success(f"Returned {count} highlights (all pages)")
        log_warning(f"This fetched ALL highlights across all pages")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 3: Get daily review
    log_test("get_daily_review")
    try:
        result = await client.get_daily_review()
        highlights = result.get("highlights", [])
        log_success(f"Returned {len(highlights)} daily review highlights")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 4: Search highlights
    log_test("search_highlights - query='AI' (basic)")
    try:
        result = await client.search_highlights(query="AI", page_size=5, fetch_all=False)
        highlights = result.get("results", [])
        log_success(f"Returned {len(highlights)} matching highlights")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 5: Search highlights - fetch_all
    log_test("search_highlights - fetch_all=True")
    try:
        result = await client.search_highlights(query="python", page_size=10, fetch_all=True)
        highlights = result.get("results", [])
        count = result.get("count", len(highlights))
        log_success(f"Returned {count} matching highlights (all pages)")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 6: List books
    log_test("list_books - basic (page_size=5)")
    try:
        result = await client.list_books(page_size=5, fetch_all=False)
        books = result.get("results", [])
        log_success(f"Returned {len(books)} books")
        if books:
            log_success(f"Sample: {books[0].get('title', 'No title')[:50]}")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 7: List books - fetch_all
    log_test("list_books - fetch_all=True")
    try:
        result = await client.list_books(page_size=100, fetch_all=True)
        books = result.get("results", [])
        count = result.get("count", len(books))
        log_success(f"Returned {count} books (all pages)")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 8: Export highlights (small sample)
    log_test("export_highlights - no filters (this may take time)")
    try:
        highlights = await client.export_highlights()
        log_success(f"Exported {len(highlights)} highlights (all time)")
        log_warning(f"Export always fetches all pages by design")
    except Exception as e:
        log_error(f"Failed: {e}")

    # Test 9: Get book highlights (if we have a book ID)
    log_test("get_book_highlights - testing with first book ID if available")
    try:
        # First get a book ID
        result = await client.list_books(page_size=1, fetch_all=False)
        books = result.get("results", [])
        if books and len(books) > 0:
            book_id = books[0].get("id")
            log_success(f"Testing with book_id={book_id}")

            result = await client.get_book_highlights(book_id=book_id)
            highlights = result.get("results", [])
            count = result.get("count", len(highlights))
            log_success(f"Returned {count} highlights for book {book_id}")
        else:
            log_warning("No books found to test get_book_highlights")
    except Exception as e:
        log_error(f"Failed: {e}")


async def main():
    """Run all tests"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Readwise MCP Server - Comprehensive Tool Testing{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    # Check for token
    token = os.getenv("READWISE_TOKEN")
    if not token:
        log_error("READWISE_TOKEN not found in environment variables")
        log_error("Please set READWISE_TOKEN in your .env file")
        sys.exit(1)

    log_success(f"Token loaded: {token[:10]}...{token[-4:]}")

    # Initialize client
    client = ReadwiseClient(token)
    log_success("Client initialized")

    # Run tests
    try:
        await test_reader_api_tools(client)
        await test_highlights_api_tools(client)

        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{GREEN}All tests completed!{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")

    except Exception as e:
        log_error(f"Fatal error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
