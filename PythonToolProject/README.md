# Python Tool Project — Issue Tracker Agent

A guided project: build an AI agent in **watsonx Orchestrate** backed by **Python tools** — plain Python functions registered directly with Orchestrate, instead of an OpenAPI specification or an MCP server.

**Compared to the other projects:**

| Project | Where the "tool" comes from |
| --- | --- |
| [`../TicketTown`](../TicketTown) | A custom MCP server, built and hosted for this workshop |
| [`../OpenAPIToolProject`](../OpenAPIToolProject) | An existing API, described by an OpenAPI specification |
| [`../MCPToolProject`](../MCPToolProject) | An existing MCP server, run and maintained by someone else |
| **This project** | Plain Python functions, imported straight from source with the `orchestrate` CLI — no server to run, no spec to write |

## The example: Issue Tracker Agent

[`issue_tracker/`](issue_tracker/README.md) is a conversational support-ticket system: an agent that can greet a user, create an account, file an issue (auto-creating the account if one doesn't exist), check an issue's status, list a reporter's issues, and update an issue's status — all backed by Supabase PostgreSQL, with tables created automatically on first use.

Unlike the other two projects, which are built by clicking through the Orchestrate web UI, this one is imported from the command line: six Python tools plus the agent, registered in one shot by [`issue_tracker/import-all.sh`](issue_tracker/import-all.sh).

## Build it

1. Install the [watsonx Orchestrate CLI](https://www.ibm.com/docs/en/watsonx/watson-orchestrate) and activate your environment:

   ```bash
   orchestrate env activate <your-env-name>
   ```

2. Set `DATABASE_URL` to a Supabase (or any Postgres) connection string — or leave it unset and the script will prompt for it securely:

   ```bash
   export DATABASE_URL="postgresql://postgres:<password>@<host>:5432/postgres"
   ```

3. Run the import script from the `issue_tracker` directory:

   ```bash
   cd issue_tracker
   chmod +x import-all.sh
   ./import-all.sh
   ```

   This registers the connection, all six Python tools, and the agent in one shot.

Full architecture, the tool reference, and sample prompts are in [`issue_tracker/README.md`](issue_tracker/README.md).

## Stretch goals

- Swap the backend: point the `_conn()` function in the tool files at MySQL, MongoDB, the Jira REST API, or GitHub Issues instead of Postgres.
- Add a tool that emails the reporter when their issue's status changes.
- Combine it with TicketTown: automatically file a support issue when a booking fails.
