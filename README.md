# 🎟️ TicketTown

A small movie-booking app built for the **watsonx Orchestrate workshop**. Attendees book tickets on a website; then an AI agent books tickets through an **MCP server**, and the website updates **live** while the audience watches.

```
┌──────────────┐   REST + SSE    ┌───────────────────┐   REST    ┌──────────────┐
│  frontend/   │ ──────────────▶ │     backend/      │ ◀──────── │    mcp/      │
│  index.html  │ ◀── live feed ─ │ Node + Express    │           │ Python FastMCP│
│  (Replit)    │                 │ + SQLite          │           │ 12 tools     │
└──────────────┘                 └───────────────────┘           └──────┬───────┘
                                                                        │ MCP
                                                              ┌─────────▼────────┐
                                                              │ watsonx          │
                                                              │ Orchestrate agent│
                                                              └──────────────────┘
```

| Folder | What it is | Stack |
|---|---|---|
| [`frontend/`](frontend/index.html) | The website, in a light, ticketing-site layout: hero carousel, poster rails, showtimes, tiered seat map. **One self-contained `index.html`** (HTML + CSS + JS inline) plus `logo.svg`. | Plain HTML/CSS/JS |
| [`backend/`](backend/src/server.js) | REST API, mock payment, live event stream, SQLite database, TMDB movie sync. | Node 22 · Express · `node:sqlite` |
| [`mcp/`](mcp/server.py) | MCP server exposing the API as agent tools. | Python · FastMCP |

The speaker guide with demo script, agent instructions and sample prompts is in **[WORKSHOP-GUIDE.md](WORKSHOP-GUIDE.md)**.

---

## 🚀 Deployed OpenShift (OCP) Endpoints

- **Backend API:** <https://workshop-backend.apps.wo-dp-005.p75g.p1.openshiftapps.com>
  - Health endpoint: `https://workshop-backend.apps.wo-dp-005.p75g.p1.openshiftapps.com/api/health`
- **MCP Server (Streamable HTTP):** <https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com>
  - MCP endpoint: `https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp`

---

## Run everything locally

Needs **Node 22.13+** and Python 3.10+.

```bash
./start-local.sh
```

Open <http://localhost:5173>. The backend is on <http://localhost:3000>.

Test the MCP server against it (Python):

```bash
cd mcp
python3 -m venv .venv && . .venv/bin/activate      # or: uv venv && source .venv/bin/activate
pip install -r requirements.txt
python test_client.py                               # runs a full agent-style booking
```

You should see the booking appear live in the website's **⚡ Live** drawer with a 🤖 badge.

---

## 1 · Frontend on Replit

1. Create a new Replit → **HTML, CSS, JS** template.
2. Replace the contents of `index.html` with [`frontend/index.html`](frontend/index.html). Nothing else is needed.
3. Set your backend URL near the top of the `<script>`:
   ```js
   const TICKETTOWN_API_URL = 'https://your-backend.onrender.com';
   ```
   *…or* skip editing and click the **⚙** button in the page header. It saves the URL in that browser, which is handy on stage.
4. Press Run.

### Test it from StackBlitz (or any online editor) with a tunnel

The online editor's page is on the public internet, so it can't reach `localhost`. Put your local backend on the internet with a free **Cloudflare quick tunnel** (no account needed):

```bash
./start-local.sh        # terminal 1: the backend
./tunnel.sh             # terminal 2: prints  https://<random-words>.trycloudflare.com
```

Then in StackBlitz: create a plain HTML/JS project, paste [`frontend/index.html`](frontend/index.html), and either set `TICKETTOWN_API_URL` to that address or click **⚙**, paste it, and press *Test connection*. Use the same address for the MCP server: `TICKETTOWN_API_URL=<address> python server.py`.

- **Live updates still work.** Cloudflare quick tunnels buffer streaming responses, so the normal live stream (Server-Sent Events) gets nothing through. The page notices after ~4 seconds and switches to polling `GET /api/events/poll` every 2 seconds. It shows "Live" either way, and hovering the pill tells you which mode is active. Force a mode for testing with `?sse=fetch` or `?sse=off` on the page URL.
- **The address changes every time you restart the tunnel**, so update ⚙ (and the MCP setting) each time. For a permanent address, use a named Cloudflare tunnel with your own domain, or deploy the backend (Render etc.) instead.
- **Give a new address ~30 seconds** before opening it in a browser. If your machine looks it up before it exists in DNS, it can cache a "not found" answer and keep failing for a while. `tunnel.sh` already waits for this.
- Quick tunnels are for demos and testing. Cloudflare provides them without any guarantee.

**ngrok instead?** `ngrok config add-authtoken <token>` then `ngrok http 3000` (free account needed). The frontend already sends `ngrok-skip-browser-warning` and reads the stream with `fetch` for ngrok URLs, because ngrok's free plan otherwise answers browsers with a warning page that has no CORS headers.

> **https matters.** Replit serves over `https`, so the backend must be `https` too. Browsers block `https` pages from calling plain `http` servers (except `localhost`).

## 2 · Backend

```bash
cd backend
npm install
npm start          # http://localhost:3000
```

The SQLite file is created at `backend/data/tickettown.db` and seeded on first boot (8 fictional movies, 4 days of showtimes, some seats pre-sold). It re-seeds automatically as days roll over.

| Env var | Default | Purpose |
|---|---|---|
| `TMDB_API_KEY` | *(empty)* | Turns on real movies from TMDB. See below. |
| `USE_TMDB` | `true` | Set `false` to force the built-in demo movies even when a key is set |
| `TMDB_REGION` · `TMDB_LIMIT` | `IN` · `12` | Which region's "now playing" list, and how many movies |
| `PORT` | `3000` | HTTP port |
| `DB_PATH` | `./data/tickettown.db` | SQLite file location |
| `HOLD_MINUTES` | `10` | How long unpaid seats stay held |
| `ADMIN_KEY` | `tickettown` | Header `x-admin-key` for `POST /api/admin/reset`. **Change it on a public deploy.** |
| `TZ_NAME` | `Asia/Kolkata` | Timezone the showtimes are in |

CORS is open to **all origins**, as required for Replit.

### Real movies from TMDB

Without a key the site uses 8 built-in fictional movies. With a TMDB key it lists what is really playing (posters, backdrops, cast, trailers, scores), and the fictional ones are hidden. **Agent 404, the workshop's own movie, always stays**, so your demo prompts keep working.

1. Create a free key at <https://www.themoviedb.org/settings/api>. Either the **API Key (v3)** or the **API Read Access Token (v4)** works.
2. Put it in `backend/.env` (it is git-ignored and loaded automatically). Never put it in the frontend.
   ```bash
   cd backend && cp .env.example .env     # then paste the key after TMDB_API_KEY=
   ```
3. Restart the backend. The log says `🎬 TMDB: 12 movies synced`. (Connections to TMDB sometimes drop; the backend retries automatically.) It re-syncs every 12 hours, and you can force it:
   ```bash
   curl -X POST http://localhost:3000/api/admin/sync-movies -H "x-admin-key: tickettown"
   ```
4. On Render/Railway, set `TMDB_API_KEY` in the service's environment variables instead of a `.env` file.

If TMDB is unreachable the backend logs a warning and keeps serving the movies it already has. It never fails to start.

> **Attribution:** TMDB's terms require crediting them. The footer shows the required sentence whenever TMDB data is in use. Their terms also ask for the TMDB logo next to it. Download it from <https://www.themoviedb.org/about/logos-attribution> and add it to the footer if you publish this beyond the workshop.

**Offline / no-key rehearsal:** `npm run mock-tmdb` starts a fake TMDB on :4010 with generated posters, and `npm run demo-offline` runs the backend against it. It's a good fallback if the venue Wi-Fi is bad.

### Seat prices

Each show has a base (Silver) price, and rows are priced by tier:

| Rows | Tier | Price |
|---|---|---|
| A–C | Silver | base |
| D–F | Gold | base + ₹50 |
| G–H | Platinum | base + ₹100 |

`GET /api/shows/:id` returns the `tiers`, and the booking `amount` is the sum of each seat's tier price.

### Deploy it (pick one)

The backend has to be on the public internet: Orchestrate runs in the cloud and can't reach your laptop.

- **Render** (easiest): push this folder to GitHub → *New → Blueprint* → it reads [`render.yaml`](render.yaml).
  - The free tier **sleeps after ~15 min idle** and takes up to a minute to wake. Open `/api/health` a few minutes before you go on stage.
  - The free tier's disk is not persistent, so the DB resets on redeploy or restart. That's fine here, because it re-seeds itself.
- **Railway / Fly.io / any Node host:** root directory `backend`, start command `node src/server.js`, Node **22.13+**.
- **Tunnel from your laptop** (zero-deploy fallback): run the backend locally and expose it with `cloudflared tunnel --url http://localhost:3000` or `ngrok http 3000`.

### API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/movies` · `/api/movies/:id` | List, or one movie with cast and trailer key |
| GET | `/api/movies/search?q=` | Searches all of TMDB, not just the current line-up (for an older/unlisted title) |
| POST | `/api/movies/activate` | `{tmdb_id}` → brings that movie onto the site with real showtimes, right away. Idempotent. Broadcasts `movie.activated`. |
| GET | `/api/shows?movie_id=&date=` | `date` = `today`, `tomorrow` or `YYYY-MM-DD`. Hides shows that already started. |
| GET | `/api/shows/:id` | Show + seat map (`booked`, `held`) |
| GET | `/api/shows/:id/suggest?count=2` | Best seats together |
| POST | `/api/bookings` | `{show_id, seats[], email, phone, name?, source?}` → holds seats |
| GET | `/api/bookings/:code` · `/api/bookings?email=` | |
| POST | `/api/bookings/:code/pay` | Mock. `{method: card\|upi\|wallet}`. Card ending `0002` is declined. |
| POST | `/api/bookings/:code/cancel` | |
| GET | `/api/activity` | Recent bookings for the live drawer |
| GET | `/api/events` | **Server-Sent Events**: `booking.created/confirmed/cancelled/expired`, `movie.activated`, `reset` |
| GET | `/api/events/poll?since=` | The same events for clients that can't stream. Call once without `since` to get the current position, then poll with `since=<last>`. |
| POST | `/api/admin/reset` | Wipes demo bookings. Needs `x-admin-key`. |
| POST | `/api/admin/sync-movies` | Re-pull the line-up from TMDB. Needs `x-admin-key`. |

Double-booking is impossible: `booking_seats` has `PRIMARY KEY (show_id, seat)`, so the database itself rejects a second claim on the same seat.

```bash
# reset the demo between runs
curl -X POST https://your-backend/api/admin/reset -H "x-admin-key: tickettown"
```

## 3 · MCP server

Eleven tools, all thin wrappers over the API. Every booking they make is tagged `source: "agent"`.

Movie discovery is two-tier, matching how the site itself works:

- **`browse_now_showing`** - only what's actually listed and bookable right now. The backend curates this for the workshop's mostly-Malayalam audience: it reserves several slots for trending Malayalam releases from this month, then fills the rest with trending English and other Indian-language titles (Tamil, Telugu, Hindi, ...) so it's never Malayalam-only and never empty if a month happens to have no new Malayalam release. See `TMDB_LIMIT` / the curation logic in [`backend/src/tmdb.js`](backend/src/tmdb.js).
- **`find_any_movie`** - searches *all* of TMDB, for a title that isn't in `browse_now_showing` (an older release, or one outside this month's curated pull). Read-only; returns candidates to confirm, nothing is booked or added yet.
- **`add_movie_to_lineup`** - brings a movie found via `find_any_movie` onto the live site: adds it to the database and generates real showtimes for it immediately, in sync with the frontend - anyone watching the home page sees it appear live. Idempotent. A movie added this way is never silently removed by the periodic TMDB re-sync while a real (non-seed) booking exists for it.
- **`get_showtimes_for_movie`** - "what are the showtimes for *X*?" in one call, instead of `browse_now_showing` + `get_showtimes`. Resolves the title itself; if it isn't currently showing it says so and points at `find_any_movie` instead of a dead end, and if the title matches more than one current movie it returns candidates rather than guessing.

Booking, same as before: `get_showtimes` · `suggest_seats` · `get_seat_map` · `create_booking` · `confirm_payment` · `get_booking` · `list_bookings` · `cancel_booking`

Point it at your backend by editing `API_URL` in [`mcp/server.py`](mcp/server.py) or setting the `TICKETTOWN_API_URL` env var.

```bash
python server.py                          # stdio (what Orchestrate imports)
python server.py --transport http         # streamable HTTP at http://localhost:8000/mcp
python test_client.py                     # end-to-end smoke test (stdio)
python test_client.py --http http://localhost:8000/mcp
```

### Test the MCP server

```bash
cd mcp
python test_client.py     # quick smoke test: one booking, start to finish
python test_tools.py      # thorough: 159 checks across all 11 tools, incl. discovering and
                           # booking a movie that isn't in the current line-up
python simulate_agent.py  # a readable, human transcript of a real customer conversation -
                           # good for a sanity check or a screen-share, not for CI
```

`test_tools.py` connects like a real MCP client and checks the tool list and schemas, every tool's success and failure paths, tier pricing, that a rejected booking holds nothing, and that the agent's actions produce live events for the website. It also checks the HTTP transport and what the agent sees when the backend is down. It cancels what it books. Use `TICKETTOWN_API_URL=<address>` to test through a tunnel.

To include the "unpaid hold expires" check, start a second backend with a short hold time and point the test at it:

```bash
cd backend && HOLD_MINUTES=0.05 DB_PATH=/tmp/expiry.db PORT=3100 USE_TMDB=false npm start
EXPIRY_API_URL=http://localhost:3100 python test_tools.py
```

`requirements.txt` pins `mcp<2`. MCP SDK 2.x renamed `FastMCP` to `MCPServer`; the pin keeps the code in the form most tutorials and docs use.

### Attach it to watsonx Orchestrate

With the ADK installed and your environment active, import the folder as an MCP toolkit:

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

Then add the `tickettown` toolkit to your agent (in the UI, or in the agent's YAML under `tools:`).

> ⚠️ Orchestrate's CLI flags change between releases. I wrote this from memory and **did not run it against a live Orchestrate tenant**. Check `orchestrate toolkits import --help` and your version's MCP docs. If your tenant can attach a **remote** MCP server by URL instead, run `python server.py --transport http` on any public host and use that URL.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page says **"Can't reach the backend"** | Open **⚙**, set the URL, press *Test connection*. Check `https` vs `http`. |
| Live pill stays **"Reconnecting…"** | Backend asleep (Render free tier) or unreachable. Hit `/api/health` and reload. (A buffering proxy is handled: the page falls back to polling.) |
| First agent call is slow or times out | Same cold-start issue. The MCP server retries once and waits up to 45 s. |
| `node:sqlite` import error | Node is older than 22.13. Upgrade. |
| Seats look taken when they shouldn't | Unpaid holds expire after `HOLD_MINUTES`. Or reset with the admin endpoint. |
