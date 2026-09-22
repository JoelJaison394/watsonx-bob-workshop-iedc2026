# Speaker guide

## The story in one line

> "Same booking system. First a human uses the website. Then an **agent** uses the exact same system through **MCP**, and you watch the website react in real time."

## Before you go on stage (10 min)

- [ ] Backend deployed and `/api/health` returns `{"ok":true}`. **Wake it up now** if it's on a free tier.
- [ ] `TMDB_API_KEY` set on the backend and the home page shows real posters. (No key? It falls back to the demo movies.)
- [ ] Reset the demo: `curl -X POST <backend>/api/admin/reset -H "x-admin-key: <key>"`
- [ ] Replit frontend loads, shows **● Live** (green) in the header.
- [ ] MCP toolkit imported and added to your agent. Send one test message.
- [ ] Orchestrate embed snippet pasted into `index.html` (bottom of the file), and `SHOW_AGENT_HINT = true`.
- [ ] Second browser tab open on **My bookings** with the demo email typed in.
- [ ] Have `<backend>/api/events` ready in a tab as a backup: it streams raw events (great for showing SSE).

## Demo flow (suggested ~12 min)

| # | What you do | What the audience sees | Talking point |
|---|---|---|---|
| 1 | Book a ticket **by hand**: pick *Agent 404*, choose seats, enter email + phone, pay | Full flow, ticket with barcode | "This is a normal app. Note the 10-minute seat hold." |
| 2 | Show the **decline**: pay with card `4000 0000 0000 0002` | ❌ Card declined | "Agents will hit errors too. Watch how they cope." |
| 3 | Open the **⚡ Live** drawer | Your booking in the feed | "Everything goes through one API and streams over SSE." |
| 4 | Open the seat map for a show and **leave it open** on the projector | Seat map | "Keep an eye on this page." |
| 5 | In the embedded chat: *"Book 2 seats for Agent 404 tomorrow morning for me. My email is …, phone …"* | Seats flash amber (held), toast "🤖 AI agent is holding…" | "The agent called `create_booking` through MCP. No UI involved." |
| 6 | Agent asks to confirm payment → say *"yes, pay"* | Seats go dark (booked), toast "🤖 AI agent booked…", feed updates | "`confirm_payment`. The website never refreshed." |
| 7 | Ask for a seat that's already gone, e.g. *"Now book one of the seats I just booked, for the same show"* | Agent recovers and offers other seats | "The error message came from the API through MCP, and the agent used it." |
| 8 | *"Show my bookings"* then *"Cancel the last one"* | Seats free up live | Cancel = destructive tool, so the agent should confirm first |
| 9 | Leave the **home page** open on the projector. Ask the agent for a movie that clearly isn't listed, e.g. *"Book 2 seats for The Dark Knight tonight"* | Agent says it's not currently showing, asks to confirm, then the movie's poster and backdrop appear live on the home page carousel with a toast: "🎬 The Dark Knight just joined the line-up." | "`find_any_movie` searched all of TMDB. `add_movie_to_lineup` just wrote it into our own database and generated real showtimes - that's why it appeared on the projector without anyone touching the website." |

### Prompts that work well

*Agent 404* is always in the catalogue. With a TMDB key the other titles are whatever is playing, so swap in a title you can see on the home page.

- "What comedies are showing today?"
- "Book 3 seats together for *<a movie from the home page>* tonight."
- "Get me the cheapest showing of *<title>* tomorrow, 2 seats, my email is … phone …"
- "What's the highest rated movie showing right now?" (uses the audience score from TMDB)
- "What's the status of booking TT-XXXXXX?"
- "I'd like to sit in row F, seats 5 and 6." (uses `get_seat_map`)
- "Book 2 seats for Inception / The Godfather / any classic tonight." (not in the current line-up → `find_any_movie` → `add_movie_to_lineup`)

## Agent instructions (paste into your Orchestrate agent)

```
You are TickyBot, the booking assistant for TicketTown, a movie ticket service.

Use your TicketTown tools to help customers find movies and book tickets.

Rules:
1. To find a movie, first call browse_now_showing to get the movie_id, then get_showtimes.
   Dates: use "today" or "tomorrow" when the customer says so.
2. If browse_now_showing doesn't have the movie the customer named, call find_any_movie to search
   for it. Read back the title and year to confirm you found the right one (the same title can
   have several versions), then call add_movie_to_lineup with its tmdb_id before doing anything
   else with it - only after that does it have real showtimes to book.
3. If the customer doesn't name specific seats, call suggest_seats. If they name seats, call get_seat_map to check them.
4. Before create_booking you MUST have: the showtime, the seats, and the customer's email AND phone number. Ask for anything missing. Never invent contact details.
5. Seats are priced by tier (Silver, Gold, Platinum). After create_booking, tell the customer the movie, theatre, time, seats and total price in rupees (₹), and ask whether to pay now.
   Only call confirm_payment after they clearly say yes. Unpaid bookings are released after about 10 minutes.
6. Ask for confirmation before cancel_booking.
7. If a tool returns an error (for example seats already taken), explain it in plain words and offer alternatives.
8. Show times in 12-hour format. Keep replies short and friendly.
```

Suggested agent description: *"Books movie tickets at TicketTown: searches movies, checks showtimes and seats, holds seats and confirms payment."*

## Mapping to the workshop agenda

| Agenda item | Where to show it |
|---|---|
| What MCP is | [`mcp/server.py`](mcp/server.py): each `@mcp.tool` is one function plus a docstring. The docstring **is** the tool description the LLM reads. |
| Tools vs APIs | The same operations exist as REST routes in [`backend/src/server.js`](backend/src/server.js). MCP adds names, descriptions and typed parameters for the model. |
| Agent + database in sync | Ask for an unlisted movie (demo beat 9). `add_movie_to_lineup` writes straight into the same SQLite database the website reads from - there's no separate "agent data." |
| Orchestrate agent | The instructions above, plus the toolkit import command in the README. |
| Embedded chat | Bottom of `frontend/index.html`: a marked slot for the embed snippet. |
| Why live UI | `GET /api/events` (SSE) and `onLiveEvent()` in the frontend. |

## Live troubleshooting

- **Agent says it can't find the tool / call fails**: hit `<backend>/api/health` in a tab. If it's asleep, wait ~40 s and retry.
- **"Seats already taken"** during the demo: someone booked them. Ask the agent to suggest others, or reset with the admin endpoint.
- **Screen mirroring is small**: browser zoom out (Ctrl −) on the seat map. It stays crisp and the whole hall fits.
- **Want a clean slate mid-talk**: run the reset `curl`. The page shows a "Demo bookings were reset" toast and clears the feed.

## Fun details you can point out

- The seed data deliberately includes **Agent 404**, a comedy about an AI agent that gets lost between tools.
- Bookings made by the agent carry `source: "agent"`. That's what puts the 🤖 badge and purple highlight in the feed.
- Public feed masks emails (`j***@example.com`) and never includes phone numbers.
