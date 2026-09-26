# Creating and Deploying an Agent in watsonx Orchestrate (No-Code)

This walkthrough guides you through creating an AI agent directly inside the **watsonx Orchestrate** UI — no code, no IDE. You'll build a movie-booking assistant, connect it to the TicketTown MCP server, and deploy it live.

---

## Step 1 — Navigate to the Home Dashboard

When you open **watsonx Orchestrate**, you land on the **Chat** page by default.

- Click the **hamburger menu** (☰) in the top-left corner.
- Select **Home**.

This is the **control plane** — a dashboard that shows your active agents, messages, deployments, evaluations, and more.

- Click the **Create agent** button in the top-right corner.

![Home Dashboard](images/image-01.png)

---

## Step 2 — Create From Scratch

The **Create an agent** modal opens. You can build with Bob, start from a template, or import a LangGraph agent — but for this walkthrough we'll build it manually.

- Click **Create from scratch**.

![Create an Agent Modal](images/image-02.png)

---

## Step 3 — Name Your Agent

You're now in the **Agent Builder**, on the **Build → Behavior** tab.

- Dismiss the **Legal Notice** after reading it.
- Enter an **Agent name** — use your team name (e.g. `my-team-name-goes-here`).
- Leave the **Model** as the default, or pick another one from the dropdown.

> The **Draft Preview** panel on the right lets you chat with your agent at any time while you build it.

![Agent Name](images/image-03.png)

---

## Step 4 — Add a Description

Fill in the **Description** field. This tells watsonx Orchestrate (and other agents) what your agent does.

Write your own — a short sentence or two describing who your agent is and what it helps with. For example, give it a name and say that it helps customers find movies and book tickets on TicketTown.

![Agent Description](images/image-04.png)

---

## Step 5 — Add Instructions

Fill in the **Instructions** field. Instructions tell the agent *how* to behave — the steps to follow, the rules to respect, and the tone to use.

Copy the instructions below into the field. Feel free to **modify them and experiment** — try changing a rule, adding a new one, or adjusting the tone, then test the result in the **Draft Preview** panel.

```
Rules:
1. For "what's showing for <movie>?", call get_showtimes_for_movie with the title directly.
   Use browse_now_showing instead when the customer wants to browse (e.g. "what's on today?").
2. If a movie isn't currently showing, call find_any_movie to search for it. Confirm the
   exact title and year with the customer, then call add_movie_to_lineup with its tmdb_id
   before doing anything else with it.
3. If the customer doesn't name specific seats, call suggest_seats. If they name seats,
   call get_seat_map to check them first.
4. Before create_booking you MUST have the showtime, the seats, and the customer's email
   AND phone number. Ask for anything missing - never invent contact details.
5. After create_booking, state the movie, time, seats and total price in rupees (₹), and
   ask whether to pay now. Only call confirm_payment after an explicit yes.
6. Ask for confirmation before cancel_booking.
7. Never answer a seat, showtime or availability question from something said earlier in
   the conversation - other customers are booking in real time, so call the tool again
   every time, even for a question that looks identical to one already asked.
8. If a tool returns an error, explain it in plain words and offer an alternative.
```

![Agent Instructions](images/image-05.png)

---

## Step 6 — Open the Tools Tab

- Switch to the **Tools** tab.
- Click **Add Tool**.

![Tools Tab](images/image-06.png)

---

## Step 7 — Choose MCP Server

The **Add a tool** modal shows several ways to give your agent tools.

- Under **Add from**, select **MCP server**.

> MCP (Model Context Protocol) tools let your agent connect to external services through a standardised protocol — so it can take real actions, like booking a movie ticket.

![Add a Tool](images/image-07.png)

---

## Step 8 — Add a New MCP Server

No MCP servers are connected yet.

- Click **Add MCP server**.

![Add Tools and Manage MCP Servers](images/image-08.png)

---

## Step 9 — Select Remote MCP Server

- Select **Remote MCP server** (the TicketTown server is hosted online).
- Click **Next**.

![Select MCP Server Type](images/image-09.png)

---

## Step 10 — Enter the MCP Server Details

Fill in the server details:

- **Server name** — your team name + `-mcp` (e.g. `my-team-name-mcp`)
- **Description** — write a short description of your own (e.g. what these tools are for)
- **MCP server URL** — copy the URL below:

```
https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp
```

- **Transport type** — **Streamable HTTP**
- **Select Connection** — `None` (no API key is required)

- Click **Connect**.

![Remote MCP Server Details](images/image-10.png)

---

## Step 11 — Select the Tools and Add Them to the Agent

Once connected, you'll see a message confirming that the MCP server is ready and **12 tools** are available.

- Select **all 12 tools**.
- Click **Add to agent**.

![Select MCP Tools](images/image-11.png)

---

## Step 12 — Review the Added Tools

The **Tools** tab now lists all the TicketTown tools. Each card shows what the tool does, and you can click **Edit details** to change a tool's description.

> This is a good moment to test your agent in the **Draft Preview** panel — try asking *"What movies are showing?"*

![Tools Added](images/image-12.png)

---

## Step 13 — Go to the Deploy Tab

- Click **Deploy** in the top bar (next to **Build** and **Evaluate**).

![Deploy Tab](images/image-13.png)

---

## Step 14 — Review the Draft Summary

The **Draft Summary** page shows the channels where your agent will be available — **Orchestrate chat**, **Embedded agent**, and **Slack**.

- Under **Orchestrate chat**, you can click **Edit** to customise the welcome message and starter prompts.

![Draft Summary](images/image-14.png)

---

## Step 15 — (Optional) Edit the Welcome Message and Starter Prompts

Customise what users see when they first open a chat with your agent:

- **Welcome message** — the greeting shown at the top of the chat.
- **Quick start prompts** — clickable suggestions (e.g. *"What movies are showing tonight?"*).

- Click **Apply** when you're done.

![Edit Home Page](images/image-15.png)

---

## Step 16 — Deploy to Live

- Click **Deploy to Live**.

![Deploy to Live](images/image-16.png)

---

## Step 17 — Create a New Version

No versions exist yet. You can create and manage multiple versions and choose which one to deploy.

- Click **Create new version**.

![Create New Version](images/image-17.png)

---

## Step 18 — Fill in Version Details

Provide the version details:

- **Version name** — anything you like (e.g. `0.9.0 beta`)
- **Description** — optional
- **Version number** — must follow the `x.y.z` format (e.g. `0.9.0`)

You can expand **Profile**, **Tools (12)**, **Behavior**, etc. to review what's included in this version.

- Click **Create**.

![Version Details](images/image-18.png)

---

## Step 19 — Select the Version to Deploy

- Select the version you just created.
- Click **Deploy**.

![Select Version](images/image-19.png)

---

## Step 20 — Review the Pre-deployment Summary

A final summary shows your agent's profile, tools, and connections.

- Review the details.
- Click **Deploy**.

![Pre-deployment Summary](images/image-20.png)

---

## Step 21 — Agent is Live!

Once deployed, a green **Live** badge appears next to your agent's name.

- Open the **hamburger menu** (☰) and click **Chat**.

![Agent is Live](images/image-21.png)

---

## Step 22 — Select Your Agent in Chat

- Open the **Agents** dropdown on the left.
- Select your agent by name (e.g. **my-team-name-goes-here**).

![Select Agent in Chat](images/image-22.png)

---

## Step 23 — Chat With Your Agent

- Type a message and press **Enter**.

Try something like:
- *"What movies are showing right now?"*
- *"Book 2 seats for the next show of Interstellar."*

![Chat with Agent](images/image-23.png)

---

## 🎉 All Done!

Your agent is now live and ready to use — built entirely in the watsonx Orchestrate UI. Go ahead and test its tools, book a ticket, and see it in action.

---

*Happy building!*
