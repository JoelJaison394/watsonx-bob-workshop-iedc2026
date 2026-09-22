# 🎟️ TicketTown

TicketTown is a small, fully working movie-ticket booking system built to demonstrate **IBM watsonx Orchestrate + MCP** to a live audience: a human books a ticket through a normal website, then an **AI agent books a ticket through the exact same system using MCP tools**, and the website updates **live** while everyone watches.

It's a real three-part application, not a mockup:

- A **website** where people can browse movies, pick seats and pay (mock payment - nothing real is charged).
- A **backend API** with a real SQLite database, real seat-locking, and a live event stream. It syncs real "now playing" movies from TMDB.
- An **MCP server** that exposes that same API as tools an AI agent can call - search movies, check showtimes, hold seats, pay, cancel.

Book a seat on the website and ask the agent for your bookings - it's the same data. Ask the agent to book a movie that isn't listed yet, and watch it appear live on the website a second later.

## Contents

- [Architecture](#architecture)
- [What's in this repo](#whats-in-this-repo)
- [Try the live deployment](#try-the-live-deployment)
- [Quickstart: run everything locally](#quickstart-run-everything-locally)
- [1. Frontend](#1-frontend)
- [2. Backend](#2-backend)
- [3. MCP server](#3-mcp-server)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Architecture

```
┌──────────────┐   REST + SSE    ┌────────────────────┐   REST    ┌───────────────┐
│  frontend/   │ ──────────────▶ │      backend/       │ ◀──────── │     mcp/      │
│  index.html  │ ◀── live feed ─ │  Node + Express     │           │ Python FastMCP │
│  (static)    │                 │  + SQLite + TMDB    │           │  12 tools     │
└──────────────┘                 └────────────────────┘           └───────┬───────┘
                                                                           │ MCP
                                                                 ┌─────────▼─────────┐
                                                                 │ watsonx Orchestrate │
                                                                 │       agent         │
                                                                 └─────────────────────┘
```

Both the website and the agent talk to the **same backend and the same database**. There is no separate "agent data" - a seat the agent holds is a seat the website can no longer sell, in real time, and a movie the agent adds is a movie the website's home page shows.

## What's in this repo

| Folder | What it is | Stack | Key files |
|---|---|---|---|
| [`frontend/`](frontend/index.html) | The website: hero carousel, poster rails, showtimes, a tiered seat map, mock checkout, and a live "⚡ activity" feed. **One self-contained file** - all HTML, CSS and JS inline. | Plain HTML/CSS/JS, no build step | [`index.html`](frontend/index.html), [`logo.svg`](frontend/logo.svg) |
| [`backend/`](backend/src/server.js) | The REST API: movies, showtimes, seat holds, mock payment, Server-Sent Events, TMDB sync. | Node 22 · Express · `node:sqlite` | [`src/server.js`](backend/src/server.js) (routes), [`src/tmdb.js`](backend/src/tmdb.js) (movie sync), [`src/seed.js`](backend/src/seed.js) (demo data + showtimes) |
| [`mcp/`](mcp/server.py) | The MCP server: wraps the backend's API as 12 tools an AI agent can call. | Python · FastMCP | [`server.py`](mcp/server.py) |

Also at the repo root:

| File | Purpose |
|---|---|
| [`start-local.sh`](start-local.sh) | One command to run the backend and a static server for the frontend, together |
| [`tunnel.sh`](tunnel.sh) | Puts your local backend on the public internet (free Cloudflare tunnel, no account needed) - for testing the frontend from an online editor, or the MCP server before you deploy it |
| [`render.yaml`](render.yaml) | One-click backend deploy blueprint for [Render](https://render.com) |
| `backend/Dockerfile`, `mcp/Dockerfile` | Container images for the backend and MCP server (used for the OpenShift deployment below; work with any container platform) |

## Try the live deployment

A live copy is already deployed and running:

- **Website:** ask whoever's running the workshop for the current frontend URL (the deployed backend below is what it points at).
- **Backend API:** <https://workshop-backend.apps.wo-dp-005.p75g.p1.openshiftapps.com>
  - Health check: `GET /api/health`
- **MCP server (streamable HTTP):** `https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp`

Point an Orchestrate agent (or [`mcp/simulate_agent_remote.py`](mcp/simulate_agent_remote.py), see [Testing](#testing)) at that MCP URL to try it immediately, with nothing to install.

## Quickstart: run everything locally

Needs **Node 22.13+** and **Python 3.10+**.

```bash
./start-local.sh
```

Open <http://localhost:5173> for the website. The backend is on <http://localhost:3000>.

Then, in another terminal, run the agent's tools against it for real:

```bash
cd mcp
python3 -m venv .venv && . .venv/bin/activate      # or: uv venv && source .venv/bin/activate
pip install -r requirements.txt
python simulate_agent.py                            # a full, readable customer-agent conversation
```

You'll see the booking appear live in the website's **⚡ Live** drawer with a 🤖 badge, in real time.

---

## 1. Frontend

A single file, [`frontend/index.html`](frontend/index.html) - open it anywhere, or serve it with any static host.

**Configure the backend it talks to** near the top of the `<script>` tag:

```js
const TICKETTOWN_API_URL = 'https://your-backend.example.com';
```

*…or* leave it and click the **⚙** icon in the page header at runtime - it saves the URL in that browser's `localStorage`, handy for switching backends without editing code.

### Deploy the frontend

Since it's a single static file, any static host works:

- **Cloudflare Pages / Netlify:** point it at this repo with the frontend folder as the publish directory, no build command.
- **Replit:** create an HTML/CSS/JS template and paste in `index.html`.
- **StackBlitz** (or any online editor): **open [stackblitz.com/edit/web-platform](https://stackblitz.com/edit/web-platform)**, replace its `index.html` with [`frontend/index.html`](frontend/index.html), and it runs immediately - no account needed. It runs in the browser and can't reach `localhost`, so put your local backend on the internet first:
  ```bash
  ./start-local.sh        # terminal 1: the backend
  ./tunnel.sh             # terminal 2: prints https://<random-words>.trycloudflare.com
  ```
  Then set `TICKETTOWN_API_URL` (or use **⚙**) to that address.

**Notes:**

- **https matters.** A page served over `https` can't call a plain `http` backend (browsers block it, except for `localhost`). Make sure both sides match.
- **Live updates degrade gracefully.** The site normally gets live updates via Server-Sent Events. If a host or tunnel buffers streaming responses (Cloudflare quick tunnels do), the page notices within ~4 seconds and falls back to polling `GET /api/events/poll` every 2 seconds - it still shows "Live," just hover the pill to see which mode is active. Force a mode while testing with `?sse=fetch` or `?sse=off` on the page URL.
- **ngrok instead of Cloudflare?** `ngrok config add-authtoken <token>` then `ngrok http 3000` (free account needed). The frontend already sends `ngrok-skip-browser-warning` and reads the live stream with `fetch` for ngrok URLs, since ngrok's free plan otherwise shows browsers an interstitial page with no CORS headers.

## 2. Backend

```bash
cd backend
npm install
npm start          # http://localhost:3000
```

A SQLite database is created at `backend/data/tickettown.db` and seeded on first boot (8 built-in movies, 4 days of showtimes, some seats pre-sold so the theatre doesn't look empty). CORS is open to all origins, needed since the frontend can be hosted anywhere.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `TMDB_API_KEY` | *(empty)* | Turns on real movies from TMDB - see below |
| `USE_TMDB` | `true` | Set `false` to force the built-in demo movies even when a key is set |
| `TMDB_REGION` | `IN` | Which region's "now playing" list to pull |
| `TMDB_LIMIT` | `16` | How many movies to keep in the line-up |
| `PORT` | `3000` | HTTP port |
| `DB_PATH` | `./data/tickettown.db` | SQLite file location |
| `HOLD_MINUTES` | `10` | How long an unpaid seat hold lasts before it's released |
| `ADMIN_KEY` | `tickettown` | Header `x-admin-key` required by the `/api/admin/*` routes below - **change this before a public deploy** |
| `TZ_NAME` | `Asia/Kolkata` | Timezone the showtimes are generated in |

Copy `.env.example` to `.env` to set these locally (git-ignored, loaded automatically):

```bash
cd backend && cp .env.example .env
```

### Real movies from TMDB

Without a key, the site shows 8 built-in fictional movies. With a key, it lists what's really playing - posters, backdrops, cast, trailers, audience scores - and the fictional titles are hidden (except the built-in *Agent 404*, which always stays in the line-up).

1. Get a free key at <https://www.themoviedb.org/settings/api> - either the **API Key (v3)** or the **API Read Access Token (v4)** works.
2. Put it in `backend/.env` as `TMDB_API_KEY=...`. **Never put it in the frontend** - it stays server-side.
3. Restart the backend. The log says `🎬 TMDB: N movies synced`. It re-syncs every 12 hours; force it any time with:
   ```bash
   curl -X POST http://localhost:3000/api/admin/sync-movies -H "x-admin-key: tickettown"
   ```

The line-up is curated for an Indian audience: it reserves several slots for trending Malayalam releases from the current month, then fills the rest with trending English and other Indian-language titles (Tamil, Telugu, Hindi, ...), so it's never Malayalam-only and never empty in a month with no new Malayalam release.

If TMDB is unreachable, the backend logs a warning and keeps serving whatever movies it already has - it never fails to start over this.

> **Attribution:** TMDB's terms require crediting them; the site's footer shows the required sentence whenever TMDB data is in use. Their terms also ask for their logo next to it - add it from <https://www.themoviedb.org/about/logos-attribution> if you take this beyond a demo.

**No TMDB key handy, or bad Wi-Fi?** `npm run mock-tmdb` starts a fake TMDB on port 4010 with generated posters, and `npm run demo-offline` runs the backend against it - a good offline rehearsal.

### Seat pricing

Every show has a base ("Silver") price, and rows are priced by tier:

| Rows | Tier | Price |
|---|---|---|
| A–C | Silver | base |
| D–F | Gold | base + ₹50 |
| G–H | Platinum | base + ₹100 |

`GET /api/shows/:id` returns the tier breakdown, and a booking's total is the sum of each seat's tier price.

### API reference

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/movies` · `/api/movies/:id` | List, or one movie with full cast and trailer key |
| GET | `/api/movies/search?q=` | Searches all of TMDB, not just the current line-up (for an older or unlisted title) |
| POST | `/api/movies/activate` | `{tmdb_id}` → brings that movie onto the site with real showtimes immediately. Idempotent. Broadcasts `movie.activated`. |
| GET | `/api/shows?movie_id=&date=` | `date` is `today`, `tomorrow` or `YYYY-MM-DD`. Never returns shows that already started. |
| GET | `/api/shows/:id` | One show, plus its seat map (`booked`, `held`) |
| GET | `/api/shows/:id/suggest?count=N` | Best N seats together |
| POST | `/api/bookings` | `{show_id, seats[], email, phone, name?, source?}` → holds the seats |
| GET | `/api/bookings/:code` · `/api/bookings?email=` | |
| POST | `/api/bookings/:code/pay` | Mock payment. `{method: card\|upi\|wallet}`. A card ending `0002` is declined, on purpose, for testing that path. |
| POST | `/api/bookings/:code/cancel` | |
| GET | `/api/activity` | Recent bookings, for the website's live drawer |
| GET | `/api/events` | Server-Sent Events: `booking.created/confirmed/cancelled/expired`, `movie.activated`, `reset` |
| GET | `/api/events/poll?since=` | The same events, for clients that can't hold a stream open. First call with no `since` to get the current position, then poll with `since=<last>`. |
| POST | `/api/admin/reset` | Wipes non-seed bookings. Needs `x-admin-key`. |
| POST | `/api/admin/sync-movies` | Re-pulls the line-up from TMDB right now. Needs `x-admin-key`. |

Double-booking is structurally impossible: `booking_seats` has `PRIMARY KEY (show_id, seat)`, so the database itself rejects a second claim on an already-held seat.

### Deploying the backend

It needs to be reachable from the public internet - Orchestrate runs in the cloud and can't reach your laptop.

- **Docker / OpenShift:** `backend/Dockerfile` builds a UBI9 Node 22 image; `EXPOSE 3000`, reads all the env vars above.
- **Render:** push this repo to GitHub → *New → Blueprint* → it reads [`render.yaml`](render.yaml). The free tier sleeps after ~15 min idle (wakes on the next request, ~1 min) and has no persistent disk, so the database resets on redeploy - fine here, since it re-seeds itself.
- **Any other Node host:** root directory `backend`, start command `node src/server.js`, Node **22.13+** required (it uses the built-in `node:sqlite` module).
- **No hosting, just a quick test:** run it locally and expose it with `./tunnel.sh` or `ngrok http 3000`.

## 3. MCP server

12 tools, thin wrappers over the backend API above. Every booking made through them is tagged `source: "agent"`, so the website's live feed shows it with a 🤖 badge.

| Tool | Type | What it does |
|---|---|---|
| `browse_now_showing` | read | Lists what's actually on the site right now - exactly what the home page shows |
| `find_any_movie` | read | Searches *all* of TMDB, for a title `browse_now_showing` doesn't have |
| `add_movie_to_lineup` | write | Brings a movie found via `find_any_movie` onto the live site with real showtimes, in sync with the database and the frontend |
| `get_showtimes_for_movie` | read | "What are the showtimes for *X*?" in one call - resolves the title itself |
| `get_showtimes` | read | Showtimes for a known `movie_id` |
| `suggest_seats` | read | Best N seats together for a show |
| `get_seat_map` | read | Full seat-by-seat availability for a show |
| `create_booking` | write | Holds seats for ~10 minutes (not yet paid) |
| `confirm_payment` | write | Pays a held booking (mock wallet/UPI) and confirms it |
| `get_booking` | read | Look up one booking by its code |
| `list_bookings` | read | A customer's recent bookings by email |
| `cancel_booking` | write, destructive | Cancels a booking and releases its seats |

Movie discovery is deliberately two-tier: `browse_now_showing` only ever returns what's genuinely bookable, so it can never suggest a movie that isn't actually on the site. When a customer asks for something outside that list, the flow is `find_any_movie` → confirm the exact title with the customer → `add_movie_to_lineup`, which is the only step that writes anything - it's the same pattern the backend itself uses to keep the site and the database in sync.

### Running it

```bash
cd mcp
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python server.py                          # stdio - what Orchestrate imports as a local toolkit
python server.py --transport http         # streamable HTTP at http://localhost:8000/mcp
```

Point it at your backend with `TICKETTOWN_API_URL=<url>` (default `http://localhost:3000`), or edit `API_URL` directly in [`server.py`](mcp/server.py).

`requirements.txt` pins `mcp<2` - MCP SDK 2.x renamed `FastMCP` to `MCPServer`; the pin keeps the code in the form most current tutorials and docs use.

**Docker:** `mcp/Dockerfile` builds a UBI9 Python 3.11 image that serves streamable HTTP on port 8000 by default - this is what the live OpenShift deployment above runs.

### Attaching it to watsonx Orchestrate

**If a copy is already deployed** (like the OpenShift one above), the simplest path is attaching it as a **remote MCP server by URL** - check your Orchestrate version's docs for the exact steps, since this UI/CLI changes between releases.

**To import your own copy as a local toolkit**, with the ADK installed and your environment active:

```bash
orchestrate toolkits import \
  --kind mcp \
  --name tickettown \
  --description "Browse movies and book TicketTown tickets" \
  --package-root ./mcp \
  --language python \
  --command '["python", "server.py"]' \
  --tools "*"
```

Then add the `tickettown` toolkit to your agent (in the UI, or under `tools:` in the agent's YAML).

> ⚠️ These CLI flags are written from documentation, not verified against a live Orchestrate tenant, and change between releases - check `orchestrate toolkits import --help` for your installed version.

**Suggested agent instructions**, as a starting point:

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

## Testing

| Script | What it proves | Run it |
|---|---|---|
| [`mcp/test_client.py`](mcp/test_client.py) | A quick smoke test - one booking, start to finish | `python test_client.py` |
| [`mcp/test_tools.py`](mcp/test_tools.py) | Thorough: every tool's success and failure paths, tier pricing, that a rejected booking holds nothing, that agent actions produce live events, the HTTP transport, and behaviour when the backend is down | `python test_tools.py` |
| [`mcp/simulate_agent.py`](mcp/simulate_agent.py) | A readable transcript of a real customer conversation against a local server - good for a sanity check or screen-share, not for CI | `python simulate_agent.py` |
| [`mcp/simulate_agent_remote.py`](mcp/simulate_agent_remote.py) | The same conversation, over HTTP against a **deployed** MCP server - exactly how Orchestrate would reach it | `python simulate_agent_remote.py <mcp-url>` |

All four talk to a real backend and make real bookings; the automated ones clean up after themselves. Point any of them at a different backend with `TICKETTOWN_API_URL=<url>`.

To also exercise the "unpaid hold expires" path in `test_tools.py`, start a second backend with a short hold time and point the test at both:

```bash
cd backend && HOLD_MINUTES=0.05 DB_PATH=/tmp/expiry.db PORT=3100 USE_TMDB=false npm start
EXPIRY_API_URL=http://localhost:3100 python test_tools.py
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Website says **"Can't reach the backend"** | Open **⚙**, set the URL, press *Test connection*. Check `https` vs `http` matches on both sides. |
| Live pill stuck on **"Reconnecting…"** | Backend asleep (free-tier hosts) or unreachable - hit `/api/health` directly and reload. A buffering proxy is handled automatically via the polling fallback. |
| First agent call is slow or times out | Same cold-start issue as above - the MCP server retries automatically and waits up to 45s. |
| `node:sqlite` import error | Node is older than 22.13 - upgrade. |
| A seat looks taken when it shouldn't | Someone else is holding it (`HOLD_MINUTES`), or it expired but the page hasn't refreshed - reload, or reset the demo with the admin endpoint. |
| Agent repeats an identical seat/showtime answer, even after a booking changed it | It's answering from conversation memory instead of calling the tool again - check the real data directly with `curl <backend>/api/shows/<id>` to confirm the backend is correct. The agent instructions above (rule 7) exist specifically to prevent this. |
| Agent can't find a tool you just added, after redeploying the MCP server | Some agent builders snapshot the tool list when a toolkit is first attached rather than re-querying it live - re-sync or re-add the MCP toolkit inside Orchestrate after a redeploy. |
