#!/usr/bin/env python3
"""
PubMed MCP Server
A Model Context Protocol (MCP) server that provides tools to search and retrieve
biomedical literature from PubMed/NCBI for use with ChatGPT and other AI assistants.
"""

import asyncio
import json
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# NCBI E-utilities base URL
ENTREZ_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Optional: Set NCBI_API_KEY env var for higher rate limits (10 req/s vs 3 req/s)
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")

app = Server("pubmed-mcp-server")


def build_url(endpoint: str, params: dict) -> str:
    """Build an E-utilities URL with the given parameters."""
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return f"{ENTREZ_BASE_URL}/{endpoint}?{urlencode(params)}"


def fetch_url(url: str) -> str:
    """Fetch content from a URL and return as string."""
    req = Request(url, headers={"User-Agent": "pubmed-mcp-server/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def search_pubmed(query: str, max_results: int = 10, sort: str = "relevance") -> dict:
    """Search PubMed using ESearch and return PMIDs."""
    max_results = min(max(1, max_results), 100)
    sort_param = "relevance" if sort == "relevance" else "pub+date"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": sort_param,
        "usehistory": "y",
    }
    url = build_url("esearch.fcgi", params)
    try:
        response = fetch_url(url)
        data = json.loads(response)
        result = data.get("esearchresult", {})
        return {
            "query": query,
            "total_count": int(result.get("count", 0)),
            "returned_count": len(result.get("idlist", [])),
            "pmids": result.get("idlist", []),
            "query_translation": result.get("querytranslation", ""),
        }
    except (URLError, json.JSONDecodeError, KeyError) as e:
        return {"error": str(e), "query": query, "pmids": []}


def fetch_article_details(pmids: list, max_articles: int = 5) -> list:
    """Fetch detailed information for a list of PMIDs using EFetch."""
    if not pmids:
        return []
    pmids_to_fetch = pmids[:max_articles]
    params = {
        "db": "pubmed",
        "id": ",".join(pmids_to_fetch),
        "retmode": "xml",
        "rettype": "abstract",
    }
    url = build_url("efetch.fcgi", params)
    try:
        response = fetch_url(url)
        return parse_pubmed_xml(response)
    except (URLError, ET.ParseError) as e:
        return [{"error": str(e)}]


def parse_pubmed_xml(xml_content: str) -> list:
    """Parse PubMed XML response and extract article information."""
    articles = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return [{"error": "Failed to parse XML response"}]

    for article_elem in root.findall(".//PubmedArticle"):
        article = {}

        pmid_elem = article_elem.find(".//PMID")
        if pmid_elem is not None:
            article["pmid"] = pmid_elem.text
            article["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid_elem.text}/"

        title_elem = article_elem.find(".//ArticleTitle")
        if title_elem is not None:
            article["title"] = "".join(title_elem.itertext()).strip()

        abstract_texts = article_elem.findall(".//AbstractText")
        if abstract_texts:
            abstract_parts = []
            for at in abstract_texts:
                label = at.get("Label", "")
                text = "".join(at.itertext()).strip()
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            article["abstract"] = " ".join(abstract_parts)
        else:
            article["abstract"] = "No abstract available."

        authors = []
        for author_elem in article_elem.findall(".//Author"):
            last_name = author_elem.findtext("LastName", "")
            fore_name = author_elem.findtext("ForeName", "")
            collective = author_elem.findtext("CollectiveName", "")
            if collective:
                authors.append(collective)
            elif last_name:
                authors.append(f"{last_name} {fore_name}".strip())
        article["authors"] = authors[:10]
        if len(authors) > 10:
            article["authors"].append(f"... and {len(authors) - 10} more")

        journal_elem = article_elem.find(".//Journal")
        if journal_elem is not None:
            article["journal"] = journal_elem.findtext("Title", "")
            article["iso_abbreviation"] = journal_elem.findtext("ISOAbbreviation", "")
            pub_date = journal_elem.find(".//PubDate")
            if pub_date is not None:
                year = pub_date.findtext("Year", "")
                month = pub_date.findtext("Month", "")
                day = pub_date.findtext("Day", "")
                medline_date = pub_date.findtext("MedlineDate", "")
                if medline_date:
                    article["pub_date"] = medline_date
                else:
                    article["pub_date"] = " ".join(filter(None, [year, month, day]))

        keywords = []
        for kw_elem in article_elem.findall(".//Keyword"):
            if kw_elem.text:
                keywords.append(kw_elem.text.strip())
        article["keywords"] = keywords[:20]

        mesh_terms = []
        for mesh_elem in article_elem.findall(".//MeshHeading"):
            descriptor = mesh_elem.findtext("DescriptorName", "")
            if descriptor:
                mesh_terms.append(descriptor)
        article["mesh_terms"] = mesh_terms[:20]

        for id_elem in article_elem.findall(".//ArticleId"):
            if id_elem.get("IdType") == "doi":
                article["doi"] = id_elem.text
                break

        pub_types = []
        for pt_elem in article_elem.findall(".//PublicationType"):
            if pt_elem.text:
                pub_types.append(pt_elem.text)
        article["publication_types"] = pub_types

        articles.append(article)

    return articles


def format_article(article: dict, include_abstract: bool = True) -> str:
    """Format a single article as a readable string."""
    if "error" in article:
        return f"Error: {article['error']}"
    lines = []
    if "pmid" in article:
        lines.append(f"PMID: {article['pmid']}")
        lines.append(f"URL: {article.get('url', '')}")
    if "title" in article:
        lines.append(f"Title: {article['title']}")
    if "authors" in article and article["authors"]:
        lines.append(f"Authors: {', '.join(article['authors'])}")
    if "journal" in article:
        journal_info = article["journal"]
        if article.get("pub_date"):
            journal_info += f" ({article['pub_date']})"
        lines.append(f"Journal: {journal_info}")
    if "doi" in article:
        lines.append(f"DOI: {article['doi']}")
    if "publication_types" in article and article["publication_types"]:
        lines.append(f"Publication Type: {', '.join(article['publication_types'][:3])}")
    if include_abstract and "abstract" in article:
        lines.append(f"Abstract: {article['abstract']}")
    if "keywords" in article and article["keywords"]:
        lines.append(f"Keywords: {', '.join(article['keywords'])}")
    if "mesh_terms" in article and article["mesh_terms"]:
        lines.append(f"MeSH Terms: {', '.join(article['mesh_terms'][:10])}")
    return "\n".join(lines)


@app.list_tools()
async def list_tools() -> ListToolsResult:
    """List all available PubMed tools."""
    return ListToolsResult(
        tools=[
            Tool(
                name="search_pubmed",
                description=(
                    "Search PubMed for biomedical literature. Returns matching articles "
                    "with titles, authors, abstracts, and metadata. Supports full PubMed "
                    "query syntax including field tags ([Title], [Author], [MeSH Terms]), "
                    "Boolean operators (AND, OR, NOT), and date filters."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "PubMed search query. Examples: "
                                "'diabetes AND insulin[Title]', "
                                "'Smith J[Author] AND cancer', "
                                "'COVID-19 vaccine AND 2023[PDAT]'"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum results to return (1-20, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20,
                        },
                        "sort": {
                            "type": "string",
                            "description": "Sort order: 'relevance' (default) or 'date' (newest first)",
                            "enum": ["relevance", "date"],
                            "default": "relevance",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_article_details",
                description=(
                    "Retrieve full details for PubMed articles by their PMIDs. "
                    "Returns title, abstract, authors, journal, date, keywords, MeSH terms, DOI."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pmids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of PubMed IDs (PMIDs) to retrieve",
                            "minItems": 1,
                            "maxItems": 10,
                        },
                    },
                    "required": ["pmids"],
                },
            ),
            Tool(
                name="search_and_summarize",
                description=(
                    "Search PubMed and return a concise summary of top results. "
                    "Ideal for quick literature overviews on a topic."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Research topic or PubMed search query",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Articles to summarize (1-10, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10,
                        },
                        "sort": {
                            "type": "string",
                            "enum": ["relevance", "date"],
                            "default": "relevance",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_related_articles",
                description=(
                    "Find articles related to a given PubMed article using NCBI eLink. "
                    "Useful for discovering similar research."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pmid": {
                            "type": "string",
                            "description": "PubMed ID of the source article",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Related articles to return (1-10, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10,
                        },
                    },
                    "required": ["pmid"],
                },
            ),
        ]
    )


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    """Handle tool calls."""

    if name == "search_pubmed":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 5)
        sort = arguments.get("sort", "relevance")
        if not query:
            return CallToolResult(content=[TextContent(type="text", text="Error: query is required")])
        search_result = search_pubmed(query, max_results * 2, sort)
        if "error" in search_result:
            return CallToolResult(content=[TextContent(type="text", text=f"Search error: {search_result['error']}")])
        if not search_result["pmids"]:
            return CallToolResult(content=[TextContent(type="text", text=f"No results found for: '{query}'")])
        articles = fetch_article_details(search_result["pmids"], max_results)
        output_parts = [
            "PubMed Search Results",
            f"Query: {query}",
            f"Total matching articles: {search_result['total_count']:,}",
            f"Showing: {len(articles)} articles",
            f"Query translation: {search_result.get('query_translation', 'N/A')}",
            "=" * 60,
        ]
        for i, article in enumerate(articles, 1):
            output_parts.append(f"\n[Article {i}]")
            output_parts.append(format_article(article, include_abstract=True))
            output_parts.append("-" * 40)
        return CallToolResult(content=[TextContent(type="text", text="\n".join(output_parts))])

    elif name == "get_article_details":
        pmids = arguments.get("pmids", [])
        if not pmids:
            return CallToolResult(content=[TextContent(type="text", text="Error: pmids is required")])
        articles = fetch_article_details(pmids, len(pmids))
        output_parts = [
            "PubMed Article Details",
            f"Retrieved: {len(articles)} articles",
            "=" * 60,
        ]
        for i, article in enumerate(articles, 1):
            output_parts.append(f"\n[Article {i}]")
            output_parts.append(format_article(article, include_abstract=True))
            output_parts.append("-" * 40)
        return CallToolResult(content=[TextContent(type="text", text="\n".join(output_parts))])

    elif name == "search_and_summarize":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 5)
        sort = arguments.get("sort", "relevance")
        if not query:
            return CallToolResult(content=[TextContent(type="text", text="Error: query is required")])
        search_result = search_pubmed(query, max_results, sort)
        if "error" in search_result:
            return CallToolResult(content=[TextContent(type="text", text=f"Search error: {search_result['error']}")])
        if not search_result["pmids"]:
            return CallToolResult(content=[TextContent(type="text", text=f"No results found for: '{query}'")])
        articles = fetch_article_details(search_result["pmids"], max_results)
        output_parts = [
            f"Literature Summary: {query}",
            f"Found {search_result['total_count']:,} total articles, showing top {len(articles)}",
            "=" * 60,
        ]
        for i, article in enumerate(articles, 1):
            lines = [f"\n{i}. {article.get('title', 'No title')}"]
            authors = article.get("authors", [])
            if authors:
                author_str = authors[0] if len(authors) == 1 else f"{authors[0]} et al."
                lines.append(f"   Authors: {author_str}")
            journal = article.get("journal", "")
            pub_date = article.get("pub_date", "")
            if journal or pub_date:
                journal_info = journal + (f" ({pub_date})" if pub_date else "")
                lines.append(f"   Journal: {journal_info}")
            pmid = article.get("pmid", "")
            if pmid:
                lines.append(f"   PMID: {pmid} | URL: https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
            abstract = article.get("abstract", "")
            if abstract and abstract != "No abstract available.":
                if len(abstract) > 300:
                    abstract = abstract[:300] + "..."
                lines.append(f"   Abstract: {abstract}")
            output_parts.append("\n".join(lines))
        return CallToolResult(content=[TextContent(type="text", text="\n".join(output_parts))])

    elif name == "get_related_articles":
        pmid = arguments.get("pmid", "")
        max_results = arguments.get("max_results", 5)
        if not pmid:
            return CallToolResult(content=[TextContent(type="text", text="Error: pmid is required")])
        params = {
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "cmd": "neighbor_score",
            "retmode": "json",
        }
        url = build_url("elink.fcgi", params)
        try:
            response = fetch_url(url)
            data = json.loads(response)
            related_pmids = []
            for linkset in data.get("linksets", []):
                for linksetdb in linkset.get("linksetdbs", []):
                    if linksetdb.get("linkname") == "pubmed_pubmed":
                        related_pmids = [
                            str(link["id"])
                            for link in linksetdb.get("links", [])
                            if str(link["id"]) != pmid
                        ][:max_results]
                        break
            if not related_pmids:
                return CallToolResult(content=[TextContent(type="text", text=f"No related articles found for PMID: {pmid}")])
            articles = fetch_article_details(related_pmids, max_results)
            output_parts = [
                f"Articles Related to PMID: {pmid}",
                f"Found {len(articles)} related articles",
                "=" * 60,
            ]
            for i, article in enumerate(articles, 1):
                output_parts.append(f"\n[Related Article {i}]")
                output_parts.append(format_article(article, include_abstract=False))
                output_parts.append("-" * 40)
            return CallToolResult(content=[TextContent(type="text", text="\n".join(output_parts))])
        except (URLError, json.JSONDecodeError, KeyError) as e:
            return CallToolResult(content=[TextContent(type="text", text=f"Error: {str(e)}")])

    else:
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])


async def main():
    """Main entry point for the MCP server."""
    async with stdio_server() as streams:
        await app.run(
            streams[0],
            streams[1],
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
