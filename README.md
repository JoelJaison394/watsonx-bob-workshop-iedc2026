# 🎟️ TicketTown

TicketTown is a movie ticket booking web app — a website, its backend server, and an **MCP server** that lets an AI agent (built in **IBM watsonx Orchestrate**) book tickets through the exact same system a customer uses. Book a seat on the website, then ask the agent for your bookings — it's the same data, live.

## Try it yourself

The easiest way to see it running, with nothing to install:

1. Open **[stackblitz.com/edit/web-platform](https://stackblitz.com/edit/web-platform)** — a free, blank HTML/CSS/JS project in your browser.
2. In this repo, open the frontend code: **[`frontend/index.html`](frontend/index.html)**.
3. Copy its contents and paste them over StackBlitz's `index.html`, replacing everything in that file.
4. It runs immediately — it already points at a live, working backend, so you can browse movies, pick seats, and book a ticket right away.

That's the whole app in one file: no build step, no install.

## Connect it to watsonx Orchestrate

The MCP server that lets an agent use this same system is already deployed here:

```
https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp
```

In watsonx Orchestrate, attach this as a **remote MCP server by URL** (the exact steps depend on your Orchestrate version — check its docs for attaching a remote MCP toolkit). Once it's attached, give your agent these instructions so it behaves the way this demo expects:

```
You are TickyBot, the booking assistant for TicketTown, a movie ticket service.

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

Once that's set up, try asking your agent things like *"what's showing today?"*, *"book me 2 seats for tonight"*, or *"can I get tickets for a movie that isn't listed?"* — and watch the seat you book disappear live on the website you opened in StackBlitz.

## Want to go deeper?

For the architecture, the folder structure, running everything on your own machine, deploying your own copy, and the test suite — see **[DOCS.md](DOCS.md)**.
