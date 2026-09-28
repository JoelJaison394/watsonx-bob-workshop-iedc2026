# Creating an Agent through the ADK CLI

This walkthrough guides you through creating an AI agent using the **watsonx Orchestrate ADK CLI** — no UI required. You'll build and deploy your agent entirely from the terminal.

---

## Step 1 — Verify the Orchestrate ADK Installation

Before building anything, confirm that the **Orchestrate ADK CLI** is installed and check which version you're running.

Run the following command in your terminal:

```bash
orchestrate --version
```

You should see the installed version printed to the terminal, confirming the ADK is ready to use.

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 11 03 27 PM" src="https://github.com/user-attachments/assets/8c5edd82-1620-4ab5-9818-a02a4035365b" />


## Step 2 — Configure Your Environment in the ADK

Configure your **watsonx Orchestrate** environment in the ADK. Use this environment to create your agents.

> **Note:** In this step, you need access to specific credentials for your environment. If you don't know the type of environment you have, see [Logging in to IBM watsonx Orchestrate]

**To find your service instance URL:**

1. Log in to your watsonx Orchestrate tenant.
2. Click your **profile icon** in the top-right corner.
3. Select **Settings**.



4. Click on the **API Details** tab.
5. Copy the **Instance URL** shown on that tab.

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 21 37 PM" src="https://github.com/user-attachments/assets/b6c24f56-a4b1-45b3-a73d-6f3aaf7b0c9a" />


To add your environment, run the following command, replacing `<service-instance-url>` with the URL you just copied:

```bash
orchestrate env add -n <environment-name> -u <service-instance-url>
```

Replace the placeholders with your actual values:

| Placeholder | Description |
|---|---|
| `<environment-name>` | A name you choose to identify this environment (e.g. `my-wxo-env`) |
| `<service-instance-url>` | The Instance URL copied from the API Details tab |

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 21 37 PM" src="https://github.com/user-attachments/assets/9f32d23a-a842-4847-aa9e-d93dd33655fb" />


## Step 3 — Activate Your Environment

Run the following command to activate the environment you created:

```bash
orchestrate env activate <environment-name> -a <api key>
```

Replace `<environment-name>` with the name you used in Step 2.
Replace `<api key>` with the api key you have created from access management page.


<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 21 53 PM" src="https://github.com/user-attachments/assets/f29467f5-c9a3-4a1a-81cd-6c09f57967a7" />


## Step 4 — Import and Connect to an MCP Server

Import the TicketTown MCP server into your environment using the ADK toolkit. This makes all the server's tools available to agents you create.

Run the following command:

```bash
orchestrate toolkits add --kind mcp \
  --name movieticketbookingserver \
  --description "Movie Ticket Booking server" \
  --url "https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp" \
  --transport "streamable_http" \
  --tools "*"
```

Here's what each flag does:

| Flag | Value | Description |
|---|---|---|
| `--kind` | `mcp` | Specifies this is an MCP server toolkit |
| `--name` | `movieticketbookingserver` | The name you give the server in your environment |
| `--description` | `"Movie Ticket Booking server"` | A short description of the toolkit |
| `--url` | `https://workshop-mcp.apps...` | The URL of the remote MCP server |
| `--transport` | `streamable_http` | The transport protocol used to connect |
| `--tools` | `*` | Import **all** available tools from the server |

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 23 31 PM" src="https://github.com/user-attachments/assets/e59ac87e-a68f-42e6-8d8e-b736ea9a3150" />


## Step 5 — Verify the Imported Toolkit

To confirm the MCP server was imported successfully, list all toolkits in your environment:

```bash
orchestrate toolkits list
```

You should see `movieticketbookingserver` listed along with all the individual tools imported from the MCP server. **Take note of the tool names** — you will need them when defining your agent's YAML file in the next step.

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 37 12 PM" src="https://github.com/user-attachments/assets/6e03c5da-60ff-4742-a566-c7c5b659207a" />


## Step 6 — Define the Agent YAML

Create a YAML file that defines your agent. The `tools` section must list every tool you want your agent to use — use the exact tool names returned by `orchestrate toolkits list` in Step 5.

Below is a sample agent YAML file with all 12 tools from the `movieticketbookingserver` MCP server:

```yaml
spec_version: v1
kind: agent
name: moviebookingagent
description: A movie ticket booking assistant powered by the TicketTown MCP server.
llm: watsonx/meta-llama/llama-3-1-70b-instruct
instructions: |
  You are a helpful movie ticket booking assistant. Help users search for movies,
  check showtimes, suggest seats, and manage their bookings using the available tools.
  Always confirm details with the user before completing a booking.
tools:
  - movieticketbookingserver/get_showtimes
  - movieticketbookingserver/get_showtimes_for_movie
  - movieticketbookingserver/list_bookings
  - movieticketbookingserver/suggest_seats
  - movieticketbookingserver/book_ticket
  - movieticketbookingserver/cancel_booking
  - movieticketbookingserver/get_booking_details
  - movieticketbookingserver/list_movies
  - movieticketbookingserver/get_movie_details
  - movieticketbookingserver/list_cinemas
  - movieticketbookingserver/get_seat_map
  - movieticketbookingserver/confirm_booking
```

> **Tip:** The tool names follow the format `<toolkit-name>/<tool-name>`. Always prefix each tool with the toolkit name you used in Step 4 (e.g. `movieticketbookingserver`).

refer to the yaml file attached.
<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 37 35 PM" src="https://github.com/user-attachments/assets/3e2fb9dd-8f1d-4415-87ff-6a0cad532149" />


---

## Step 7 — Import the Agent

Once your YAML file is ready, import it into your environment:

```bash
orchestrate agents import -f hello-world-agent.yaml
```

Replace `hello-world-agent.yaml` with the path to your YAML file.



## Step 8 — Verify the Agent in the Orchestrate UI

Once the import is complete, navigate to your **watsonx Orchestrate** tenant and confirm the agent was created successfully.

1. Open your watsonx Orchestrate tenant in the browser.
2. Go to the **Agents** section from the left navigation menu.
3. Look for `moviebookingagent` (or the name you used in your YAML) in the list.
4. Click on the agent and verify that all 12 tools from `movieticketbookingserver` are listed under its **Tools** tab.

<img width="1728" height="1117" alt="Screenshot 2026-09-27 at 10 31 25 PM" src="https://github.com/user-attachments/assets/b0b8c5c2-df7e-45f7-b7cb-3a37c2a54949" />

---

## 🎉 All Done!

Your agent is now live and ready to use. You built and deployed a fully functional AI agent entirely from the terminal — no UI required.

Go ahead and interact with it through the **Chat** page in your watsonx Orchestrate tenant — test its tools, explore its capabilities, and see it in action.

---

_Happy building!_


