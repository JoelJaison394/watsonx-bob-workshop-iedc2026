"""TicketTown MCP server.

Wraps the TicketTown REST API as MCP tools so an AI agent (for example one
built in watsonx Orchestrate) can browse movies and book tickets. Every
booking made here is tagged source="agent", so the website's live feed shows
it with a robot badge.

Run it:
    python server.py                       # stdio  -> what Orchestrate imports
    python server.py --transport http      # streamable HTTP on :8000/mcp
"""
import argparse
import asyncio
import os
import time
from typing import Annotated, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

# Where the TicketTown backend lives. Set the TICKETTOWN_API_URL env var, or
# just edit this default to your deployed URL (no trailing slash).
API_URL = os.environ.get("TICKETTOWN_API_URL", "http://localhost:3000").rstrip("/")

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

mcp = FastMCP(
    "TicketTown",
    log_level="WARNING",  # keep stdout/stderr quiet; stdio servers must not print noise
    instructions=(
        "Tools for TicketTown, a movie ticket booking service. Typical flow: "
        "search_movies -> get_showtimes -> suggest_seats -> create_booking -> "
        "confirm_payment. Always confirm the movie, showtime, seats, price and "
        "the customer's email and phone with the user before create_booking, "
        "and get an explicit yes before confirm_payment."
    ),
)


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------
async def _call(method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    """Call the TicketTown API and turn failures into readable tool errors."""
    last_err: Exception | None = None
    async with httpx.AsyncClient(base_url=API_URL, timeout=45.0) as client:
        for attempt in range(2):  # a sleeping free-tier host can need a second try
            try:
                res = await client.request(method, path, params=params, json=body)
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as err:
                last_err = err
                await asyncio.sleep(2)
        else:
            raise ToolError(f"Could not reach the TicketTown API at {API_URL}. Is the backend running? ({last_err})")

    try:
        data = res.json()
    except ValueError:
        raise ToolError(f"TicketTown API returned a non-JSON response (HTTP {res.status_code}).")
    if res.status_code >= 400:
        raise ToolError(data.get("error") or f"TicketTown API error (HTTP {res.status_code}).")
    return data


def _booking_summary(b: dict) -> dict:
    """Trim a booking down to what an agent needs to talk about it."""
    out = {
        "booking_code": b["code"],
        "status": b["status"],
        "movie": b["show"]["movie_title"],
        "theatre": b["show"]["theatre"],
        "screen": b["show"]["screen"],
        "date": b["show"]["date"],
        "time": b["show"]["time"],
        "seats": b["seats"],
        "total_amount_inr": b["amount"],
        "email": b["email"],
        "phone": b["phone"],
    }
    if b.get("hold_expires_at"):
        out["hold_expires_in_minutes"] = max(0, round((b["hold_expires_at"] / 1000 - time.time()) / 60, 1))
    if b.get("payment"):
        out["payment_method"] = b["payment"]["method"]
        out["payment_reference"] = b["payment"]["reference"]
    return out


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(annotations=READ_ONLY)
async def search_movies(
    query: Annotated[str | None, Field(description="Part of a movie title, e.g. 'agent'. Leave empty to list everything.")] = None,
    genre: Annotated[str | None, Field(description="Genre filter such as Comedy, Thriller, Sports, Drama, Animation, Romance, Action or Sci-Fi.")] = None,
) -> list[dict]:
    """List the movies currently showing at TicketTown, optionally filtered by title text or genre.
    Returns each movie's id (needed for get_showtimes), title, genres, language, duration, certificate, audience score out of 10 and starting price in INR."""
    movies = (await _call("GET", "/api/movies"))["movies"]
    if query:
        movies = [m for m in movies if query.lower() in m["title"].lower()]
    if genre:
        movies = [m for m in movies if genre.lower() in [g.lower() for g in m["genres"]]]
    return [
        {
            "movie_id": m["id"],
            "title": m["title"],
            "genres": m["genres"],
            "language": m["language"],
            "duration_minutes": m["duration_min"],
            "certificate": m["rating"],
            "audience_score_out_of_10": m["score"],
            "release_date": m["release_date"],
            "description": m["description"],
            "tickets_from_inr": m["from_price"],
        }
        for m in movies
    ]


@mcp.tool(annotations=READ_ONLY)
async def get_showtimes(
    movie_id: Annotated[int, Field(description="Movie id from search_movies.")],
    date: Annotated[str | None, Field(description="'today', 'tomorrow' or a YYYY-MM-DD date. Leave empty for all upcoming shows.")] = None,
) -> list[dict]:
    """List upcoming showtimes for a movie: theatre, screen, date, 24-hour time, seat prices in INR (three tiers: Silver, Gold, Platinum) and how many seats are still free.
    Returns each show's show_id, which is needed to pick seats and book. Shows that already started are never returned."""
    params: dict = {"movie_id": movie_id}
    if date:
        params["date"] = date
    shows = (await _call("GET", "/api/shows", params=params))["shows"]
    return [
        {
            "show_id": s["id"],
            "movie": s["movie_title"],
            "theatre": s["theatre"],
            "screen": s["screen"],
            "date": s["date"],
            "time": s["time"],
            "price_from_inr": s["price"],
            "price_by_tier_inr": {t["name"]: t["price"] for t in s["tiers"]},
            "seats_available": s["seats_available"],
        }
        for s in shows
    ][:24]


@mcp.tool(annotations=READ_ONLY)
async def suggest_seats(
    show_id: Annotated[int, Field(description="Show id from get_showtimes.")],
    count: Annotated[int, Field(description="How many seats are needed (1 to 6).", ge=1, le=6)],
) -> dict:
    """Find the best available seats for a show, kept together in one row whenever possible and centred in the hall.
    Use this when the user has no specific seats in mind. The price depends on the row (Silver A-C, Gold D-F, Platinum G-H); total_price_inr already adds it up.
    It does not reserve anything; pass the returned seats to create_booking."""
    r = await _call("GET", f"/api/shows/{show_id}/suggest", params={"count": count})
    return {
        "show_id": r["show_id"],
        "seats": r["seats"],
        "seated_together": r["together"],
        "total_price_inr": r["total"],
    }


@mcp.tool(annotations=READ_ONLY)
async def get_seat_map(
    show_id: Annotated[int, Field(description="Show id from get_showtimes.")],
) -> dict:
    """Show which seats are free for one show, grouped by row, plus the price of each tier. Rows are lettered from A (nearest the screen) and seats are numbered from 1.
    Use this when the user asks for specific seats, e.g. 'row F, seats 5 and 6'."""
    r = await _call("GET", f"/api/shows/{show_id}")
    show, seats = r["show"], r["seats"]
    unavailable = set(seats["booked"]) | set(seats["held"])
    free_by_row: dict[str, list[str]] = {}
    for row in range(show["rows"]):
        letter = chr(65 + row)
        free = [f"{letter}{c}" for c in range(1, show["cols"] + 1) if f"{letter}{c}" not in unavailable]
        if free:
            free_by_row[letter] = free
    return {
        "show_id": show["id"],
        "movie": show["movie_title"],
        "theatre": show["theatre"],
        "date": show["date"],
        "time": show["time"],
        "price_by_tier_inr": {t["name"]: {"rows": t["rows"], "price": t["price"]} for t in show["tiers"]},
        "seats_available": show["seats_available"],
        "free_seats_by_row": free_by_row,
        "aisle_after_seat_number": show["aisle_after"],
    }


@mcp.tool(annotations=WRITE)
async def create_booking(
    show_id: Annotated[int, Field(description="Show id from get_showtimes.")],
    seats: Annotated[list[str], Field(description="Seat labels such as ['D4', 'D5']. Between 1 and 6 seats.")],
    email: Annotated[str, Field(description="Customer's email address.")],
    phone: Annotated[str, Field(description="Customer's phone number, 10 to 13 digits.")],
    name: Annotated[str | None, Field(description="Customer's name, if they gave one.")] = None,
) -> dict:
    """Reserve seats for a customer. This holds the seats for about 10 minutes, returns a booking_code and the total (each seat is priced by its row tier), but the booking is NOT complete until confirm_payment is called.
    Only call this after the user has confirmed the movie, showtime, seats and given their email and phone number.
    Fails with a clear message if any seat is already taken."""
    r = await _call(
        "POST",
        "/api/bookings",
        body={"show_id": show_id, "seats": seats, "email": email, "phone": phone, "name": name, "source": "agent"},
    )
    return {
        **_booking_summary(r["booking"]),
        "next_step": "Ask the user to confirm payment, then call confirm_payment with this booking_code.",
    }


@mcp.tool(annotations=WRITE)
async def confirm_payment(
    booking_code: Annotated[str, Field(description="Booking code from create_booking, e.g. TT-AB12CD.")],
    method: Annotated[Literal["wallet", "upi"], Field(description="'wallet' (default, instant) or 'upi'. Card payments are not available to the assistant.")] = "wallet",
    upi_id: Annotated[str | None, Field(description="UPI id like name@bank. Required when method='upi'.")] = None,
) -> dict:
    """Pay for a held booking using the (mock) TicketTown wallet and confirm the tickets. Nothing real is charged.
    Only call this after the user has explicitly agreed to pay the total. Fails if the 10-minute seat hold has expired."""
    body: dict = {"method": method}
    if upi_id:
        body["upi_id"] = upi_id
    r = await _call("POST", f"/api/bookings/{booking_code}/pay", body=body)
    return {**_booking_summary(r["booking"]), "message": "Payment successful. The booking is confirmed."}


@mcp.tool(annotations=READ_ONLY)
async def get_booking(
    booking_code: Annotated[str, Field(description="Booking code, e.g. TT-AB12CD.")],
) -> dict:
    """Look up one booking by its code: status (PENDING_PAYMENT, CONFIRMED, CANCELLED or EXPIRED), movie, showtime, seats and amount."""
    r = await _call("GET", f"/api/bookings/{booking_code}")
    return _booking_summary(r["booking"])


@mcp.tool(annotations=READ_ONLY)
async def list_bookings(
    email: Annotated[str, Field(description="The customer's email address.")],
) -> list[dict]:
    """List the most recent bookings made with an email address, newest first."""
    r = await _call("GET", "/api/bookings", params={"email": email})
    return [_booking_summary(b) for b in r["bookings"]]


@mcp.tool(annotations=DESTRUCTIVE)
async def cancel_booking(
    booking_code: Annotated[str, Field(description="Booking code to cancel, e.g. TT-AB12CD.")],
) -> dict:
    """Cancel a booking and release its seats. A paid booking is refunded in full (demo). Confirm with the user before calling this."""
    r = await _call("POST", f"/api/bookings/{booking_code}/cancel")
    return {**_booking_summary(r["booking"]), "refund_amount_inr": r["refund_amount"]}


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TicketTown MCP server")
    parser.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http" if args.transport == "http" else "sse")
