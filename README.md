# PubMed MCP Server

A **Model Context Protocol (MCP)** server that provides tools to search and retrieve biomedical literature from [PubMed/NCBI](https://pubmed.ncbi.nlm.nih.gov/) for use with ChatGPT and other AI assistants.

## Features

- **search_pubmed** — Search PubMed with full query syntax support (Boolean operators, field tags, date filters)
- **get_article_details** — Retrieve complete article information by PMID(s)
- **search_and_summarize** — Get a quick literature overview on any topic
- **get_related_articles** — Discover similar articles using NCBI eLink

## Requirements

- Python 3.10+
- `mcp>=1.0.0`

## Installation

```bash
# Clone the repository
git clone https://github.com/kazcocoayacht-ai/pubmed-mcp-server.git
cd pubmed-mcp-server

# Install dependencies
pip install -r requirements.txt
```

### Optional: NCBI API Key

Register for a free NCBI API key at https://www.ncbi.nlm.nih.gov/account/ to increase rate limits from 3 to 10 requests/second.

```bash
export NCBI_API_KEY="your_api_key_here"
```

## Usage with ChatGPT (Custom GPT / OpenAI API)

This server uses the **stdio transport** of the MCP protocol. To use it with ChatGPT or other MCP-compatible clients:

### Claude Desktop / MCP Client Configuration

Add to your MCP client configuration (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pubmed": {
      "command": "python",
      "args": ["/path/to/pubmed-mcp-server/server.py"],
      "env": {
        "NCBI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Running the Server

```bash
python server.py
```

The server communicates via stdin/stdout using the MCP protocol.

## Available Tools

### `search_pubmed`

Search PubMed for biomedical literature.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | PubMed search query |
| `max_results` | integer | 5 | Number of results (1-20) |
| `sort` | string | "relevance" | "relevance" or "date" |

**Query syntax examples:**
- `diabetes AND insulin[Title]`
- `Smith J[Author] AND cancer`
- `COVID-19 vaccine AND 2023[PDAT]`
- `hypertension[MeSH Terms] AND clinical trial[PT]`

### `get_article_details`

Retrieve full details for specific articles by PMID.

| Parameter | Type | Description |
|-----------|------|-------------|
| `pmids` | array | List of PubMed IDs (max 10) |

### `search_and_summarize`

Search and get a concise overview of top results.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Research topic or query |
| `max_results` | integer | 5 | Articles to summarize (1-10) |
| `sort` | string | "relevance" | "relevance" or "date" |

### `get_related_articles`

Find articles related to a given PMID using NCBI eLink.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pmid` | string | required | Source article PMID |
| `max_results` | integer | 5 | Related articles (1-10) |

## Example Queries

```
# Search for recent COVID-19 vaccine studies
search_pubmed(query="COVID-19 mRNA vaccine efficacy", max_results=5, sort="date")

# Get details for specific articles
get_article_details(pmids=["36738517", "34583260"])

# Quick literature overview
search_and_summarize(query="CRISPR cancer therapy", max_results=5)

# Find related articles
get_related_articles(pmid="33745712", max_results=5)
```

## Data Source

All data is retrieved in real-time from the [NCBI E-utilities API](https://www.ncbi.nlm.nih.gov/home/develop/api/) (PubMed database). No local database or caching is used.

## License

MIT License — see [LICENSE](LICENSE) for details.
