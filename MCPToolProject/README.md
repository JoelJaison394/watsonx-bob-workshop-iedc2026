# MCP Tool Project — Ask a GitHub Repo

A guided project: connect an agent in **watsonx Orchestrate** to a third-party MCP server that already exists, instead of writing one.

**Compared to the other two projects:**

| Project | Where the "tool" comes from |
|---|---|
| [`../TicketTown`](../TicketTown) | A custom MCP server, built and hosted for this workshop |
| [`../OpenAPIToolProject`](../OpenAPIToolProject) | An existing API, described by an OpenAPI specification |
| **This project** | An existing MCP server, run and maintained by someone else - only a URL is needed |

## The server: DeepWiki

[DeepWiki](https://deepwiki.com) generates AI-readable documentation for public GitHub repositories. Its MCP server lets an agent ask questions about any public repository's codebase - architecture, purpose, how a feature works - without cloning it or reading the source directly.

```
https://mcp.deepwiki.com/mcp
```

No API key, account, or local server is required. This is a **remote** MCP server: Orchestrate connects to the URL above directly over streamable HTTP.

### Available tools

| Tool | What it does |
|---|---|
| `read_wiki_structure` | Lists the documentation topics available for a repository |
| `read_wiki_contents` | Returns the documentation for a repository |
| `ask_wiki_question` | Answers a specific question about a repository's codebase |

Example request, made directly to the server:

```bash
curl -X POST https://mcp.deepwiki.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
    "params": {
      "name": "ask_wiki_question",
      "arguments": {
        "repoName": "modelcontextprotocol/servers",
        "question": "What is this repository for?"
      }
    }
  }'
```

## Build it: connect it in watsonx Orchestrate

1. In Orchestrate, add a tool from a **remote MCP server**.
2. Enter the URL: `https://mcp.deepwiki.com/mcp`.
3. Orchestrate lists the three tools above.
4. No authentication step is needed.
5. Attach the tools to an agent.

*(Exact menu names vary by Orchestrate version — look for "Add tool" or "Import" and an MCP or remote-server option.)*

### Suggested agent instructions

```
You are an assistant that can answer questions about public GitHub repositories using
DeepWiki.

Rules:
1. You need the repository's owner/name (e.g. "facebook/react") to answer anything.
   If the customer only gives a repository name or a URL, work out the owner/name
   from it before calling a tool.
2. For a specific question about how something works, call ask_wiki_question directly.
3. For a general overview, call read_wiki_structure first to see what topics exist,
   then read_wiki_contents for the ones that matter.
4. If a repository has no DeepWiki documentation, say so plainly rather than guessing
   at an answer.
5. Answer in your own words - do not just paste the tool's raw output.
```

Example questions: *"What does the facebook/react repository do?"*, *"How does authentication work in modelcontextprotocol/servers?"*

## Stretch goals

- Point the agent at [`this repository`](https://github.com/JoelJaison394/watsonx-bob-workshop-iedc2026/blob/main/TicketTown/README.md) and ask it to explain how TicketTown's MCP server works, as a comparison between the two approaches.
- Add a second remote MCP server and give the agent both, so it can choose which one answers a given question.
- Look at how DeepWiki's own tool descriptions are written (returned when the server is first connected) and compare that style to the descriptions used in [`../TicketTown/mcp/server.py`](../TicketTown/mcp/server.py).
