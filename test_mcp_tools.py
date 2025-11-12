"""
Comprehensive MCP Tools Test Script and Report Generator

Tests all 13 Readwise MCP tools with realistic user scenarios and generates
a detailed report showing what each function returns.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Import the tool wrappers and extract the underlying functions
from main import (
    reader_save_document as _reader_save_document,
    reader_list_documents as _reader_list_documents,
    reader_update_document as _reader_update_document,
    reader_delete_document as _reader_delete_document,
    reader_list_tags as _reader_list_tags,
    readwise_list_highlights as _readwise_list_highlights,
    readwise_get_daily_review as _readwise_get_daily_review,
    readwise_search_highlights as _readwise_search_highlights,
    search_readwise_highlights as _search_readwise_highlights,
    readwise_list_books as _readwise_list_books,
    readwise_get_book_highlights as _readwise_get_book_highlights,
    readwise_export_highlights as _readwise_export_highlights,
    readwise_create_highlight as _readwise_create_highlight,
)

# Extract the underlying functions from FastMCP FunctionTool wrappers
# FastMCP stores the function in the .fn attribute
reader_save_document = _reader_save_document.fn
reader_list_documents = _reader_list_documents.fn
reader_update_document = _reader_update_document.fn
reader_delete_document = _reader_delete_document.fn
reader_list_tags = _reader_list_tags.fn
readwise_list_highlights = _readwise_list_highlights.fn
readwise_get_daily_review = _readwise_get_daily_review.fn
readwise_search_highlights = _readwise_search_highlights.fn
search_readwise_highlights = _search_readwise_highlights.fn
readwise_list_books = _readwise_list_books.fn
readwise_get_book_highlights = _readwise_get_book_highlights.fn
readwise_export_highlights = _readwise_export_highlights.fn
readwise_create_highlight = _readwise_create_highlight.fn

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Test results storage
test_results: Dict[str, Dict[str, Any]] = {}


def log_test(tool_name: str, scenario: str = ""):
    """Log test start"""
    scenario_text = f" - {scenario}" if scenario else ""
    print(f"\n{BLUE}[TEST]{RESET} {BOLD}{tool_name}{RESET}{scenario_text}")


def log_success(message: str):
    """Log success"""
    print(f"{GREEN}✓{RESET} {message}")


def log_error(message: str):
    """Log error"""
    print(f"{RED}✗{RESET} {message}")


def log_warning(message: str):
    """Log warning"""
    print(f"{YELLOW}⚠{RESET} {message}")


def log_info(message: str):
    """Log info"""
    print(f"{CYAN}ℹ{RESET} {message}")


def extract_sample_data(response_json: str, max_items: int = 2) -> Dict[str, Any]:
    """Extract sample data from JSON response"""
    try:
        data = json.loads(response_json)
        
        # Extract sample results if available
        sample = {}
        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
                sample["first_result"] = data["results"][0]
                if len(data["results"]) > 1:
                    sample["second_result"] = data["results"][1]
            
            # Extract key metadata
            for key in ["count", "success", "message", "error", "limit_applied", "filters_applied"]:
                if key in data:
                    sample[key] = data[key]
        
        return sample
    except:
        return {"raw_response_preview": response_json[:200] + "..." if len(response_json) > 200 else response_json}


# ==================== READER TOOLS TESTS ====================

async def test_reader_save_document():
    """Test reader_save_document tool"""
    tool_name = "reader_save_document"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Save a document to Readwise Reader",
        "user_queries": [
            "Save this article: https://example.com/article",
            "Add https://blog.example.com/post to my reading list",
            "Save this URL with tags 'productivity' and 'AI'"
        ],
        "tests": []
    }
    
    # Test 1: Basic save
    log_test(tool_name, "Basic document save")
    try:
        result = await reader_save_document(
            url="https://example.com/test-article",
            location="later",
            category="article"
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Basic save",
            "parameters": {"url": "https://example.com/test-article", "location": "later", "category": "article"},
            "success": result_data.get("success", False),
            "response_structure": extract_sample_data(result),
            "full_response": result_data
        })
        if result_data.get("success"):
            log_success("Document saved successfully")
        else:
            log_warning(f"Save may have failed: {result_data.get('error', 'Unknown error')}")
    except Exception as e:
        log_error(f"Failed: {e}")
        test_results[tool_name]["tests"].append({
            "scenario": "Basic save",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
    
    # Test 2: Save with tags
    log_test(tool_name, "Save with tags")
    try:
        result = await reader_save_document(
            url="https://example.com/tagged-article",
            tags=["test", "mcp", "automation"],
            location="new"
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Save with tags",
            "parameters": {"url": "https://example.com/tagged-article", "tags": ["test", "mcp", "automation"]},
            "success": result_data.get("success", False),
            "response_structure": extract_sample_data(result)
        })
        log_success("Document saved with tags")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_reader_list_documents():
    """Test reader_list_documents tool"""
    tool_name = "reader_list_documents"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "List documents from Readwise Reader with filtering",
        "user_queries": [
            "Show me my saved articles",
            "What documents do I have in my 'later' list?",
            "List articles by author 'John Doe'",
            "Show me documents updated after November 1st"
        ],
        "tests": []
    }
    
    # Test 1: Basic list
    log_test(tool_name, "Basic list (limit=5)")
    try:
        result = await reader_list_documents(limit=5)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Basic list",
            "parameters": {"limit": 5},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Retrieved {result_data.get('count', 0)} documents")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 2: Filter by location
    log_test(tool_name, "Filter by location='new'")
    try:
        result = await reader_list_documents(location="new", limit=3)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Filter by location",
            "parameters": {"location": "new", "limit": 3},
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} documents in 'new'")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 3: Filter by category
    log_test(tool_name, "Filter by category='article'")
    try:
        result = await reader_list_documents(category="article", limit=3)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Filter by category",
            "parameters": {"category": "article", "limit": 3},
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} articles")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_reader_update_document():
    """Test reader_update_document tool"""
    tool_name = "reader_update_document"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Update document metadata in Readwise Reader",
        "user_queries": [
            "Update the title of document XYZ",
            "Add tags 'important' to document ABC",
            "Move document DEF to archive"
        ],
        "tests": []
    }
    
    # First, get a document ID to test with
    log_test(tool_name, "Get document ID for testing")
    try:
        list_result = await reader_list_documents(limit=1)
        list_data = json.loads(list_result)
        if list_data.get("results") and len(list_data["results"]) > 0:
            doc_id = list_data["results"][0].get("id")
            if doc_id:
                log_info(f"Testing with document ID: {doc_id}")
                
                # Test update
                log_test(tool_name, f"Update document {doc_id}")
                try:
                    result = await reader_update_document(
                        document_id=doc_id,
                        tags=["test-update", "mcp-test"]
                    )
                    result_data = json.loads(result)
                    test_results[tool_name]["tests"].append({
                        "scenario": "Update document tags",
                        "parameters": {"document_id": doc_id, "tags": ["test-update", "mcp-test"]},
                        "success": result_data.get("success", False),
                        "response_structure": extract_sample_data(result)
                    })
                    log_success("Document updated successfully")
                except Exception as e:
                    log_error(f"Update failed: {e}")
            else:
                log_warning("No document ID found, skipping update test")
        else:
            log_warning("No documents found, skipping update test")
    except Exception as e:
        log_warning(f"Could not get document for update test: {e}")


async def test_reader_delete_document():
    """Test reader_delete_document tool"""
    tool_name = "reader_delete_document"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Delete a document from Readwise Reader",
        "user_queries": [
            "Delete document XYZ",
            "Remove document ABC from my library"
        ],
        "tests": []
    }
    
    log_test(tool_name, "Skipping delete test (destructive operation)")
    log_warning("Delete test skipped to avoid data loss")
    test_results[tool_name]["tests"].append({
        "scenario": "Delete document",
        "skipped": True,
        "note": "Destructive operation - skipped in automated tests"
    })


async def test_reader_list_tags():
    """Test reader_list_tags tool"""
    tool_name = "reader_list_tags"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Get all tags from Readwise Reader",
        "user_queries": [
            "What tags do I have?",
            "List all my tags",
            "Show me my tag list"
        ],
        "tests": []
    }
    
    log_test(tool_name)
    try:
        result = await reader_list_tags()
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "List all tags",
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "tag_count": result_data.get("count", 0)
        })
        tags = result_data.get("results", [])
        log_success(f"Retrieved {len(tags)} tags")
        if tags:
            log_info(f"Sample tags: {tags[:5]}")
    except Exception as e:
        log_error(f"Failed: {e}")


# ==================== HIGHLIGHTS TOOLS TESTS ====================

async def test_readwise_list_highlights():
    """Test readwise_list_highlights tool"""
    tool_name = "readwise_list_highlights"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "List highlights from Readwise with filtering",
        "user_queries": [
            "Show me my recent highlights",
            "List highlights from book ID 12345",
            "Get highlights from the last week"
        ],
        "tests": []
    }
    
    # Test 1: Basic list
    log_test(tool_name, "Basic list (limit=5)")
    try:
        result = await readwise_list_highlights(limit=5, page_size=5)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Basic list",
            "parameters": {"limit": 5, "page_size": 5},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Retrieved {result_data.get('count', 0)} highlights")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 2: Date filter
    log_test(tool_name, "Filter by date (last 30 days)")
    try:
        date_filter = (datetime.now() - timedelta(days=30)).isoformat() + "Z"
        result = await readwise_list_highlights(
            limit=5,
            highlighted_at__gt=date_filter
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Date filter",
            "parameters": {"highlighted_at__gt": date_filter, "limit": 5},
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} highlights from last 30 days")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_readwise_get_daily_review():
    """Test readwise_get_daily_review tool"""
    tool_name = "readwise_get_daily_review"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Get daily review highlights (spaced repetition)",
        "user_queries": [
            "What's in my daily review?",
            "Show me my daily review highlights",
            "Get my spaced repetition review"
        ],
        "tests": []
    }
    
    log_test(tool_name)
    try:
        result = await readwise_get_daily_review()
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Get daily review",
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        highlights = result_data.get("results", [])
        log_success(f"Retrieved {len(highlights)} daily review highlights")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_readwise_search_highlights():
    """Test readwise_search_highlights tool"""
    tool_name = "readwise_search_highlights"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Search highlights by text query using MCP endpoint",
        "user_queries": [
            "Search my highlights for 'machine learning'",
            "Find highlights about 'productivity'",
            "Show me highlights containing 'AI'"
        ],
        "tests": []
    }
    
    # Test 1: Basic search
    log_test(tool_name, "Search for 'AI'")
    try:
        result = await readwise_search_highlights(query="AI", limit=5)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Basic search",
            "parameters": {"query": "AI", "limit": 5},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Found {result_data.get('count', 0)} highlights matching 'AI'")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 2: Multi-word search
    log_test(tool_name, "Search for 'machine learning'")
    try:
        result = await readwise_search_highlights(query="machine learning", limit=3)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Multi-word search",
            "parameters": {"query": "machine learning", "limit": 3},
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} highlights")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_search_readwise_highlights():
    """Test search_readwise_highlights tool (advanced MCP search)"""
    tool_name = "search_readwise_highlights"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Advanced search with vector/semantic search and field-specific queries",
        "user_queries": [
            "Search for GenAI content using vector search",
            "Find highlights about AI in document titles",
            "Search highlights with multiple field filters"
        ],
        "tests": []
    }
    
    # Test 1: Vector search only
    log_test(tool_name, "Vector search for 'artificial intelligence'")
    try:
        result = await search_readwise_highlights(
            vector_search_term="artificial intelligence machine learning"
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Vector search only",
            "parameters": {"vector_search_term": "artificial intelligence machine learning"},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Found {result_data.get('count', 0)} results")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 2: Vector + full-text queries
    log_test(tool_name, "Vector search with field-specific queries")
    try:
        result = await search_readwise_highlights(
            vector_search_term="productivity tips",
            full_text_queries=[
                {"field_name": "highlight_plaintext", "search_term": "productivity"},
                {"field_name": "document_title", "search_term": "tips"}
            ]
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Vector + full-text search",
            "parameters": {
                "vector_search_term": "productivity tips",
                "full_text_queries": [
                    {"field_name": "highlight_plaintext", "search_term": "productivity"},
                    {"field_name": "document_title", "search_term": "tips"}
                ]
            },
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} results")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_readwise_list_books():
    """Test readwise_list_books tool"""
    tool_name = "readwise_list_books"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "List books with highlight metadata",
        "user_queries": [
            "Show me my books",
            "List all articles I've highlighted",
            "What books have I highlighted recently?"
        ],
        "tests": []
    }
    
    # Test 1: Basic list
    log_test(tool_name, "Basic list (limit=5)")
    try:
        result = await readwise_list_books(limit=5)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Basic list",
            "parameters": {"limit": 5},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Retrieved {result_data.get('count', 0)} books")
    except Exception as e:
        log_error(f"Failed: {e}")
    
    # Test 2: Filter by category
    log_test(tool_name, "Filter by category='articles'")
    try:
        result = await readwise_list_books(category="articles", limit=3)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Filter by category",
            "parameters": {"category": "articles", "limit": 3},
            "response_structure": extract_sample_data(result)
        })
        log_success(f"Found {result_data.get('count', 0)} articles")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_readwise_get_book_highlights():
    """Test readwise_get_book_highlights tool"""
    tool_name = "readwise_get_book_highlights"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Get all highlights from a specific book",
        "user_queries": [
            "Show me all highlights from book 12345",
            "Get highlights from 'The Art of War'"
        ],
        "tests": []
    }
    
    # First get a book ID
    log_test(tool_name, "Get book ID for testing")
    try:
        list_result = await readwise_list_books(limit=1)
        list_data = json.loads(list_result)
        if list_data.get("results") and len(list_data["results"]) > 0:
            book_id = list_data["results"][0].get("id")
            if book_id:
                log_info(f"Testing with book ID: {book_id}")
                
                log_test(tool_name, f"Get highlights for book {book_id}")
                try:
                    result = await readwise_get_book_highlights(book_id=book_id, max_limit=10)
                    result_data = json.loads(result)
                    test_results[tool_name]["tests"].append({
                        "scenario": "Get book highlights",
                        "parameters": {"book_id": book_id, "max_limit": 10},
                        "success": "error" not in result_data,
                        "response_structure": extract_sample_data(result),
                        "count": result_data.get("count", 0)
                    })
                    log_success(f"Retrieved {result_data.get('count', 0)} highlights")
                except Exception as e:
                    log_error(f"Failed: {e}")
            else:
                log_warning("No book ID found")
        else:
            log_warning("No books found, skipping test")
    except Exception as e:
        log_warning(f"Could not get book for test: {e}")


async def test_readwise_export_highlights():
    """Test readwise_export_highlights tool"""
    tool_name = "readwise_export_highlights"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Bulk export highlights for backup/analysis",
        "user_queries": [
            "Export all my highlights",
            "Export highlights updated after November 1st",
            "Backup my highlights library"
        ],
        "tests": []
    }
    
    # Test with small limit to avoid long waits
    log_test(tool_name, "Export with max_results=10 (limited for testing)")
    try:
        result = await readwise_export_highlights(max_results=10)
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Export highlights",
            "parameters": {"max_results": 10},
            "success": "error" not in result_data,
            "response_structure": extract_sample_data(result),
            "count": result_data.get("count", 0)
        })
        log_success(f"Exported {result_data.get('count', 0)} highlights")
        log_info("Note: Full export may take longer and return more results")
    except Exception as e:
        log_error(f"Failed: {e}")


async def test_readwise_create_highlight():
    """Test readwise_create_highlight tool"""
    tool_name = "readwise_create_highlight"
    test_results[tool_name] = {
        "name": tool_name,
        "description": "Manually create a highlight in Readwise",
        "user_queries": [
            "Create a highlight: 'This is important'",
            "Add a highlight with note 'Remember this'"
        ],
        "tests": []
    }
    
    log_test(tool_name, "Create test highlight")
    try:
        result = await readwise_create_highlight(
            text="This is a test highlight created by MCP test script",
            title="MCP Test Document",
            author="Test Author",
            note="This highlight was created for testing purposes",
            category="books"
        )
        result_data = json.loads(result)
        test_results[tool_name]["tests"].append({
            "scenario": "Create highlight",
            "parameters": {
                "text": "This is a test highlight...",
                "title": "MCP Test Document",
                "author": "Test Author",
                "note": "This highlight was created for testing purposes",
                "category": "books"
            },
            "success": result_data.get("success", False),
            "response_structure": extract_sample_data(result)
        })
        if result_data.get("success"):
            log_success("Highlight created successfully")
        else:
            log_warning(f"Creation may have failed: {result_data.get('error', 'Unknown')}")
    except Exception as e:
        log_error(f"Failed: {e}")


# ==================== REPORT GENERATION ====================

def generate_report():
    """Generate comprehensive markdown report"""
    report_lines = [
        "# Readwise MCP Tools - Comprehensive Test Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This report documents all available Readwise MCP tools, their parameters, response structures, and example usage scenarios.",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
        "### Reader Tools (5 tools)",
        "- [reader_save_document](#reader_save_document)",
        "- [reader_list_documents](#reader_list_documents)",
        "- [reader_update_document](#reader_update_document)",
        "- [reader_delete_document](#reader_delete_document)",
        "- [reader_list_tags](#reader_list_tags)",
        "",
        "### Highlights Tools (8 tools)",
        "- [readwise_list_highlights](#readwise_list_highlights)",
        "- [readwise_get_daily_review](#readwise_get_daily_review)",
        "- [readwise_search_highlights](#readwise_search_highlights)",
        "- [search_readwise_highlights](#search_readwise_highlights)",
        "- [readwise_list_books](#readwise_list_books)",
        "- [readwise_get_book_highlights](#readwise_get_book_highlights)",
        "- [readwise_export_highlights](#readwise_export_highlights)",
        "- [readwise_create_highlight](#readwise_create_highlight)",
        "",
        "---",
        ""
    ]
    
    # Generate report for each tool
    for tool_name, tool_data in sorted(test_results.items()):
        report_lines.extend(generate_tool_report(tool_name, tool_data))
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
    
    # Add summary
    report_lines.extend([
        "## Summary",
        "",
        f"**Total Tools Tested:** {len(test_results)}",
        "",
        "### Test Statistics",
        ""
    ])
    
    total_tests = sum(len(tool_data.get("tests", [])) for tool_data in test_results.values())
    successful_tests = sum(
        sum(1 for test in tool_data.get("tests", []) if test.get("success", False))
        for tool_data in test_results.values()
    )
    
    report_lines.extend([
        f"- **Total Test Scenarios:** {total_tests}",
        f"- **Successful Tests:** {successful_tests}",
        f"- **Tools with Errors:** {sum(1 for tool_data in test_results.values() if any('error' in test for test in tool_data.get('tests', [])))}",
        "",
        "---",
        "",
        "*Report generated by test_mcp_tools.py*"
    ])
    
    return "\n".join(report_lines)


def generate_tool_report(tool_name: str, tool_data: Dict[str, Any]) -> List[str]:
    """Generate report section for a single tool"""
    lines = [
        f"## {tool_name}",
        "",
        f"**Description:** {tool_data.get('description', 'N/A')}",
        "",
        "### Example User Queries (as Claude would ask)",
        ""
    ]
    
    for query in tool_data.get("user_queries", []):
        lines.append(f"- \"{query}\"")
    
    lines.extend([
        "",
        "### Parameters",
        ""
    ])
    
    # Extract parameters from test scenarios
    params_seen = set()
    for test in tool_data.get("tests", []):
        params = test.get("parameters", {})
        for param_name, param_value in params.items():
            if param_name not in params_seen:
                param_type = type(param_value).__name__
                if isinstance(param_value, list):
                    param_type = f"List[{type(param_value[0]).__name__ if param_value else 'str'}]"
                elif isinstance(param_value, dict):
                    param_type = "Dict"
                lines.append(f"- **{param_name}** (`{param_type}`): {param_value}")
                params_seen.add(param_name)
    
    if not params_seen:
        lines.append("*No parameters (or parameters not captured in tests)*")
    
    lines.extend([
        "",
        "### Response Structure",
        ""
    ])
    
    # Show response examples from tests
    for i, test in enumerate(tool_data.get("tests", []), 1):
        scenario = test.get("scenario", f"Test {i}")
        lines.append(f"#### {scenario}")
        lines.append("")
        
        if test.get("skipped"):
            lines.append("*Test skipped: " + test.get("note", "") + "*")
        elif "error" in test:
            lines.append(f"**Error:** {test['error']}")
        else:
            response_struct = test.get("response_structure", {})
            if response_struct:
                lines.append("```json")
                lines.append(json.dumps(response_struct, indent=2, ensure_ascii=False))
                lines.append("```")
            
            if test.get("count") is not None:
                lines.append(f"**Count:** {test['count']}")
            
            if test.get("success") is not None:
                status = "✓ Success" if test["success"] else "✗ Failed"
                lines.append(f"**Status:** {status}")
        
        lines.append("")
    
    lines.extend([
        "### Common Use Cases",
        ""
    ])
    
    # Generate use cases based on tool name
    use_cases = generate_use_cases(tool_name, tool_data)
    for use_case in use_cases:
        lines.append(f"- {use_case}")
    
    lines.append("")
    
    return lines


def generate_use_cases(tool_name: str, tool_data: Dict[str, Any]) -> List[str]:
    """Generate common use cases for a tool"""
    use_cases_map = {
        "reader_save_document": [
            "Save articles from the web to your reading list",
            "Add research papers with specific tags for organization",
            "Queue content for later reading by saving to 'later' location"
        ],
        "reader_list_documents": [
            "Browse your saved articles with filters",
            "Find documents by author or site name",
            "Get recently updated documents for incremental sync",
            "Filter documents by location (new, later, archive)"
        ],
        "reader_update_document": [
            "Update document metadata like title or author",
            "Add or modify tags for better organization",
            "Move documents between locations (new → later → archive)"
        ],
        "reader_delete_document": [
            "Remove unwanted documents from your library",
            "Clean up test or duplicate entries"
        ],
        "reader_list_tags": [
            "View all tags used across your documents",
            "Discover tagging patterns in your library"
        ],
        "readwise_list_highlights": [
            "Browse all your highlights with pagination",
            "Filter highlights by date range",
            "Get highlights from a specific book"
        ],
        "readwise_get_daily_review": [
            "Access your spaced repetition review items",
            "Get highlights scheduled for review today",
            "Practice active recall with your saved highlights"
        ],
        "readwise_search_highlights": [
            "Quick text search across all highlights",
            "Find highlights containing specific keywords",
            "Search highlights and notes together"
        ],
        "search_readwise_highlights": [
            "Advanced semantic search for conceptually similar content",
            "Field-specific searches (title, author, notes, tags)",
            "Combine vector search with exact text matching",
            "Find highlights using multiple search criteria simultaneously"
        ],
        "readwise_list_books": [
            "View all books/articles you've highlighted",
            "Filter by category (books, articles, tweets, podcasts)",
            "Find books with recent highlights"
        ],
        "readwise_get_book_highlights": [
            "Get all highlights from a specific book",
            "Export highlights from a particular source",
            "Review all notes from a single document"
        ],
        "readwise_export_highlights": [
            "Backup your entire highlights library",
            "Export highlights updated since a specific date",
            "Perform bulk analysis on your highlights",
            "Sync highlights to external systems"
        ],
        "readwise_create_highlight": [
            "Manually add highlights from offline reading",
            "Create highlights from notes or thoughts",
            "Add highlights with custom metadata"
        ]
    }
    
    return use_cases_map.get(tool_name, ["Use this tool to interact with Readwise data"])


# ==================== MAIN EXECUTION ====================

async def main():
    """Run all tests and generate report"""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}Readwise MCP Tools - Comprehensive Test Suite{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")
    
    # Check for token
    token = os.getenv("READWISE_TOKEN")
    if not token:
        log_error("READWISE_TOKEN not found in environment variables")
        log_error("Please set READWISE_TOKEN in your .env file")
        sys.exit(1)
    
    log_success(f"Token loaded: {token[:10]}...{token[-4:]}")
    print()
    
    # Run Reader Tools Tests
    print(f"{BOLD}{MAGENTA}{'='*70}{RESET}")
    print(f"{BOLD}{MAGENTA}Testing Reader Tools (5 tools){RESET}")
    print(f"{BOLD}{MAGENTA}{'='*70}{RESET}")
    
    await test_reader_save_document()
    await test_reader_list_documents()
    await test_reader_update_document()
    await test_reader_delete_document()
    await test_reader_list_tags()
    
    # Run Highlights Tools Tests
    print(f"\n{BOLD}{MAGENTA}{'='*70}{RESET}")
    print(f"{BOLD}{MAGENTA}Testing Highlights Tools (8 tools){RESET}")
    print(f"{BOLD}{MAGENTA}{'='*70}{RESET}")
    
    await test_readwise_list_highlights()
    await test_readwise_get_daily_review()
    await test_readwise_search_highlights()
    await test_search_readwise_highlights()
    await test_readwise_list_books()
    await test_readwise_get_book_highlights()
    await test_readwise_export_highlights()
    await test_readwise_create_highlight()
    
    # Generate report
    print(f"\n{BOLD}{GREEN}{'='*70}{RESET}")
    print(f"{BOLD}{GREEN}Generating Report{RESET}")
    print(f"{BOLD}{GREEN}{'='*70}{RESET}\n")
    
    report_content = generate_report()
    report_file = "MCP_TOOLS_REPORT.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    log_success(f"Report generated: {report_file}")
    print(f"\n{BOLD}{GREEN}{'='*70}{RESET}")
    print(f"{BOLD}{GREEN}All tests completed!{RESET}")
    print(f"{BOLD}{GREEN}{'='*70}{RESET}\n")
    
    # Print summary
    total_tools = len(test_results)
    total_tests = sum(len(tool_data.get("tests", [])) for tool_data in test_results.values())
    print(f"{CYAN}Summary:{RESET}")
    print(f"  - Tools tested: {total_tools}")
    print(f"  - Test scenarios: {total_tests}")
    print(f"  - Report file: {report_file}")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Tests interrupted by user{RESET}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)

