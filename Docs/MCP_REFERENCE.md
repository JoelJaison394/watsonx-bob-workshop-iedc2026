# TicketTown MCP Server Reference

## Server URL

```
https://workshop-mcp.apps.wo-dp-005.p75g.p1.openshiftapps.com/mcp
```

> Hosted on Red Hat OpenShift · No API key required · Streamable HTTP (MCP protocol)

### Local / Dev Endpoint

```
http://localhost:8000/mcp
```

Run with:

```bash
python server.py --transport http
```

---

## Transport Modes

| Mode | Command | Use case |
|---|---|---|
| `stdio` (default) | `python server.py` | Imported as a local toolkit in watsonx Orchestrate ADK |
| `streamable-http` | `python server.py --transport http` | Remote deployment; what Orchestrate connects to by URL |
| `sse` | `python server.py --transport sse` | Older SSE-based MCP clients |

---

## Tools

### Movie Discovery

| Tool | Type | Usage |
|---|---|---|
| `browse_now_showing` | read | List movies currently bookable on the site. Accepts optional `query`, `genre`, and `language` filters. **Always the first step** for any movie request. |
| `find_any_movie` | read | Search all of TMDB for any title — older films, unlisted releases. Results are **not yet bookable**; use before `add_movie_to_lineup`. |
| `add_movie_to_lineup` | write | Takes a `tmdb_id` confirmed by the customer and adds the movie to the live site with real showtimes instantly. Idempotent — safe to call twice. |

### Showtimes & Seats

| Tool | Type | Usage |
|---|---|---|
| `get_showtimes_for_movie` | read | Fastest path for "what are the showtimes for X?" — resolves the title and returns its schedule in one call. Returns `currently_showing: false` plus a next-step hint if the movie isn't listed. |
| `get_showtimes` | read | List showtimes for a known `movie_id`. Returns all three pricing tiers (Silver / Gold / Platinum) and live seat availability. Caps at 24 shows when no date is provided. |
| `suggest_seats` | read | Find the best N seats together (centred, same row). Returns seat labels and total price. Does **not** reserve anything. |
| `get_seat_map` | read | Return a full seat-by-seat availability map grouped by row, with tier pricing. Use when a customer requests specific seats (e.g. "row F, seats 5 and 6"). |

### Booking

| Tool | Type | Usage |
|---|---|---|
| `create_booking` | write | Hold 1–6 seats for ~10 minutes. Requires `show_id`, `seats[]`, `email`, and `phone`. Bookings are tagged `source="agent"` (shown as 🤖 on the live feed). **Not confirmed until payment.** |
| `confirm_payment` | write | Pay a held booking via mock wallet or UPI. Only call after explicit user confirmation. Fails if the 10-minute hold has expired. |
| `get_booking` | read | Look up a single booking by its code (e.g. `TT-AB12CD`). Returns status, movie, showtime, seats, and amount. |
| `list_bookings` | read | Return the most recent bookings for a given email address, newest first. |
| `cancel_booking` | destructive | Cancel a booking and release its seats. Issues a full mock refund. **Confirm with the user before calling.** |

---

## Recommended Booking Flow

```
browse_now_showing  (or get_showtimes_for_movie)
        │
        ▼
  [movie not listed?]
        │
   find_any_movie  ──▶  confirm title+year with customer  ──▶  add_movie_to_lineup
        │
        ▼
  get_showtimes_for_movie  (or get_showtimes)
        │
        ▼
  suggest_seats  (or get_seat_map for specific seats)
        │
        ▼
  create_booking  ──▶  confirm movie, time, seats, price, email & phone with customer
        │
        ▼
  confirm_payment  ──▶  explicit "yes" from customer required
```

---

## Tool Type Reference

| Type | `readOnlyHint` | `destructiveHint` | Meaning |
|---|---|---|---|
| **read** | `true` | — | Safe to call freely; never mutates state |
| **write** | `false` | `false` | Mutates state but is safe (idempotent or reversible) |
| **destructive** | `false` | `true` | Irreversible action; requires explicit user confirmation |
