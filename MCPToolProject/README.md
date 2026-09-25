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

## Connect Deep Wiki it in watsonx Orchestrate.

#### Step 1: You are in chat screen.

This is where you interact with the Agent once deployed.

<img width="4112" height="2342" alt="image" src="https://github.com/user-attachments/assets/7184678f-aa26-4a2a-a4fe-452579c3823e" />

#### Step 2: Find Agent Option in Active inventory.

2a : Expand Hamburger menu in the left, click it.
2b : Find Active inventory,
2c : Select Agents Tab, Click.


<img width="4112" height="2338" alt="image" src="https://github.com/user-attachments/assets/5b4628d3-fc84-41d1-ae1f-e2467c7f82ca" />

#### Step 3: Manage your agents here

You can choose your agent from here or create your agents

<img width="4106" height="2300" alt="image" src="https://github.com/user-attachments/assets/517e593c-bb0c-47c9-87f3-2afe0544cc35" />

#### Step 4: Create Your Agent From Scratch

4a : Find Create agent Button click to create your own agent

<img width="239" height="116" alt="image" src="https://github.com/user-attachments/assets/65b45142-527e-4797-9699-d8de3a4874ad" />

<img width="4112" height="2334" alt="image" src="https://github.com/user-attachments/assets/7a9a8774-cc8a-4588-9ec2-ca739811eac9" />

4b : Create an agent from scratch

<img width="492" height="98" alt="image" src="https://github.com/user-attachments/assets/1ee8f363-08b7-4c7f-8db4-b32a2c4ce3a2" />

#### Step 5: Create Git wiki Agent

<img width="4112" height="2336" alt="image" src="https://github.com/user-attachments/assets/28ab9cbb-f224-466b-89c7-c67ccf306989" />

##### Suggested agent instructions

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

#### Step 6: Tools for Agent

here you can add tools for agent

<img width="4112" height="2338" alt="image" src="https://github.com/user-attachments/assets/74f95c7e-23f8-4f0b-9865-89691d3b63b3" />

#### Step 7: Choose MCP server

<img width="4112" height="2336" alt="image" src="https://github.com/user-attachments/assets/e928f4fe-50ae-4e57-8580-e83ba61013f2" />

#### Step 8: Choose MCP server

click on add MCP server

<img width="245" height="128" alt="image" src="https://github.com/user-attachments/assets/6958c634-2f59-4722-9bcc-5369d48500bb" />

<img width="4112" height="2336" alt="image" src="https://github.com/user-attachments/assets/43d72042-0dbe-4734-9767-84de0606be21" />

#### Step 9: Choose MCP server

9a : choose Remote MCP server

9b : Click Next

<img width="4112" height="2336" alt="image" src="https://github.com/user-attachments/assets/eab3c609-e668-415e-932c-e32576db5a56" />


#### Step 10: Choose MCP server

Add your deep wiki server 

url : https://mcp.deepwiki.com/mcp

<img width="4112" height="2334" alt="image" src="https://github.com/user-attachments/assets/fd6e8b7d-a60c-4f3b-b340-87ef4100095a" />


#### Step 11: Choose the MCP tools

choose all MCP tools and add to agent.

<img width="4112" height="2338" alt="image" src="https://github.com/user-attachments/assets/92cde82f-0cf3-4de8-b4bb-a05c474a7006" />


#### Step 12: Agent have tools

BINGO!!, the agent has access to the tools

<img width="4112" height="2332" alt="image" src="https://github.com/user-attachments/assets/94209882-f4f1-4b1d-b2b5-e8e8b3319653" />


#### Step 13: Invoke tools 


13a : use utterance 

"can you help me understand project https://github.com/IBM/mcp-context-forge?"

<img width="4112" height="2330" alt="image" src="https://github.com/user-attachments/assets/aeb4a63b-1c56-42ba-b9a0-cc70a6cdc511" />

13b : use utterance 

"does https://github.com/IBM/mcp-context-forge support A2A?"

<img width="4110" height="2334" alt="image" src="https://github.com/user-attachments/assets/fd57d9e0-db6b-4663-b247-dcc49e7252b1" />


Example questions: *"What does the facebook/react repository do?"*, *"How does authentication work in modelcontextprotocol/servers?"*

## Stretch goals

- Point the agent at [`this repository`](https://github.com/JoelJaison394/watsonx-bob-workshop-iedc2026/blob/main/TicketTown/README.md) and ask it to explain how TicketTown's MCP server works, as a comparison between the two approaches.
- Add a second remote MCP server and give the agent both, so it can choose which one answers a given question.
- Look at how DeepWiki's own tool descriptions are written (returned when the server is first connected) and compare that style to the descriptions used in [`../TicketTown/mcp/server.py`](../TicketTown/mcp/server.py).
