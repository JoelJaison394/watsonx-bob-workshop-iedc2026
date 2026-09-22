"""Thorough test of the TicketTown MCP server, driven like a real MCP client would.

    python test_tools.py

Environment:
    TICKETTOWN_API_URL   backend to test against (default http://localhost:3000)
    EXPIRY_API_URL       optional second backend started with a tiny hold time, e.g.
                         HOLD_MINUTES=0.05 DB_PATH=/tmp/x.db PORT=3100 USE_TMDB=false node src/server.js
                         Enables the "unpaid hold expires" test.

It creates and cancels a few bookings on the backend (the seats are released again at the end).
Exit code is 0 only if every check passes.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.environ.get("MCP_SERVER", os.path.join(HERE, "server.py"))  # override to test another copy
API = os.environ.get("TICKETTOWN_API_URL", "http://localhost:3000").rstrip("/")
EXPIRY_API = os.environ.get("EXPIRY_API_URL", "").rstrip("/")

EXPECTED_TOOLS = {
    "browse_now_showing": [], "find_any_movie": ["title"], "add_movie_to_lineup": ["tmdb_id"],
    "get_showtimes": ["movie_id"], "suggest_seats": ["show_id", "count"],
    "get_seat_map": ["show_id"], "create_booking": ["show_id", "seats", "email", "phone"],
    "confirm_payment": ["booking_code"], "get_booking": ["booking_code"],
    "list_bookings": ["email"], "cancel_booking": ["booking_code"],
}
READ_ONLY = {"browse_now_showing", "find_any_movie", "get_showtimes", "suggest_seats", "get_seat_map", "get_booking", "list_bookings"}

results: list[tuple[str, bool]] = []
active_codes: set[str] = set()  # bookings we made and haven't cancelled; cleaned up at the end


def check(name: str, ok, detail: str = ""):
    ok = bool(ok)
    results.append((name, ok))
    print(f"  {'✅' if ok else '❌'} {name}" + ("" if ok or not detail else f"\n       → {detail}"))
    return ok


def section(title: str):
    print(f"\n── {title}")


class Result:
    """A tool call result, normalised: .error (str|None) and .data (parsed JSON)."""

    def __init__(self, res):
        self.error = None
        self.data = None
        text = res.content[0].text if res.content else ""
        if res.isError:
            self.error = text
        elif res.structuredContent is not None:
            sc = res.structuredContent
            self.data = sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
        elif text:
            self.data = json.loads(text)
        else:
            self.data = []

    @property
    def ok(self):
        return self.error is None


async def call(session, tool, **args) -> Result:
    return Result(await session.call_tool(tool, args))


def http_json(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as r:
        return json.load(r)


def seat_price(tiers, seat):
    return next(t["price"] for t in tiers.values() if seat[0] in t["rows"])


def stdio_params(api_url):
    return StdioServerParameters(command=sys.executable, args=[SERVER], env={**os.environ, "TICKETTOWN_API_URL": api_url})


async def free_seats(session, show_id):
    m = (await call(session, "get_seat_map", show_id=show_id)).data
    return m, [s for row in m["free_seats_by_row"].values() for s in row]


# ─────────────────────────────────────────────────────────────────────────────
async def test_discovery(session, init):
    section("1. Discovery: server, tool list, schemas")
    check("server identifies itself as TicketTown", init.serverInfo.name == "TicketTown", init.serverInfo.name)
    check("server sends usage instructions for the agent", bool(init.instructions) and "create_booking" in init.instructions)

    tools = {t.name: t for t in (await session.list_tools()).tools}
    check(f"exactly the {len(EXPECTED_TOOLS)} expected tools are exposed", set(tools) == set(EXPECTED_TOOLS),
          f"missing={set(EXPECTED_TOOLS) - set(tools)} extra={set(tools) - set(EXPECTED_TOOLS)}")

    for name, required in EXPECTED_TOOLS.items():
        t = tools.get(name)
        if not t:
            continue
        props = t.inputSchema.get("properties", {})
        check(f"{name}: description is meaningful", len(t.description or "") > 60, f"{len(t.description or '')} chars")
        check(f"{name}: required parameters are {required or 'none'}", set(t.inputSchema.get("required", [])) == set(required),
              str(t.inputSchema.get("required")))
        check(f"{name}: every parameter has a description", all(p.get("description") for p in props.values()),
              str([k for k, p in props.items() if not p.get("description")]))
        ann = t.annotations
        if name in READ_ONLY:
            check(f"{name}: marked read-only", ann and ann.readOnlyHint is True)
        else:
            check(f"{name}: marked as a write tool", ann and ann.readOnlyHint is False)
    if "cancel_booking" in tools:
        check("cancel_booking: marked destructive", tools["cancel_booking"].annotations.destructiveHint is True)
    if "confirm_payment" in tools:
        method = json.dumps(tools["confirm_payment"].inputSchema["properties"]["method"])
        check("confirm_payment: only wallet/upi offered (no card)", "wallet" in method and "upi" in method and "card" not in method.replace("Card payments", ""), method)
    return tools


async def test_browse(session):
    section("2. browse_now_showing")
    r = await call(session, "browse_now_showing")
    check("lists movies with no filter", r.ok and len(r.data) >= 2, r.error or "")
    movies = r.data
    need = {"movie_id", "title", "genres", "language", "duration_minutes", "certificate", "audience_score_out_of_10", "tickets_from_inr"}
    check("each movie has all the fields the agent needs", all(need <= set(m) for m in movies))
    check("movie ids are unique", len({m["movie_id"] for m in movies}) == len(movies))
    check("the workshop movie 'Agent 404' is present", any(m["title"] == "Agent 404" for m in movies))
    check("genres come back as lists", all(isinstance(m["genres"], list) and m["genres"] for m in movies))

    r = await call(session, "browse_now_showing", query="AGENT")
    check("title search is case-insensitive", r.ok and any(m["title"] == "Agent 404" for m in r.data) and all("agent" in m["title"].lower() for m in r.data))
    genre = movies[0]["genres"][0]
    r = await call(session, "browse_now_showing", genre=genre.upper())
    check(f"genre filter '{genre}' works (case-insensitive)", r.ok and r.data and all(genre.lower() in [g.lower() for g in m["genres"]] for m in r.data))
    r = await call(session, "browse_now_showing", language="ENGLISH")
    check("language filter works (case-insensitive)", r.ok and r.data and all(m["language"].lower() == "english" for m in r.data), r.error or "")
    r = await call(session, "browse_now_showing", query="zzzz-no-such-movie")
    check("no match returns an empty list, not an error", r.ok and r.data == [])
    return movies


async def test_discover_and_activate(session, movies):
    section("3. find_any_movie -> add_movie_to_lineup (booking a title that isn't currently listed)")
    active_ids = {m["movie_id"] for m in movies}
    r = await call(session, "find_any_movie", title="The Godfather")
    check("finds a well-known movie that predates any current release window", r.ok and len(r.data) >= 1, r.error or "")
    if not r.ok or not r.data:
        return None
    candidates = r.data
    check("each result has what's needed to confirm + activate it", all({"tmdb_id", "title", "year", "language"} <= set(c) for c in candidates))
    pick = next((c for c in candidates if c["title"] == "The Godfather"), candidates[0])
    check("the classic isn't already sitting in the current line-up", pick["tmdb_id"] not in {m.get("tmdb_id") for m in movies} | set())

    added = await call(session, "add_movie_to_lineup", tmdb_id=pick["tmdb_id"])
    check("adds it with showtimes ready to book", added.ok and added.data["showtimes"], added.error or "")
    if not added.ok:
        return None
    check("it's brand new this call (not already in the lineup)", added.data["was_already_in_lineup"] is False)
    new_movie_id = added.data["movie_id"]

    again = await call(session, "add_movie_to_lineup", tmdb_id=pick["tmdb_id"])
    check("activating the same movie again is idempotent (same id, flagged already-listed)",
          again.ok and again.data["movie_id"] == new_movie_id and again.data["was_already_in_lineup"] is True, again.error or "")

    listing = await call(session, "browse_now_showing")
    check("it now shows up in browse_now_showing, in sync with the site", listing.ok and any(m["movie_id"] == new_movie_id for m in listing.data), listing.error or "")

    shows = await call(session, "get_showtimes", movie_id=new_movie_id)
    check("get_showtimes finds real, bookable showtimes for it", shows.ok and len(shows.data) > 0, shows.error or "")
    return new_movie_id, shows.data[0] if shows.ok and shows.data else None


async def test_book_discovered_movie(session, show_id):
    section("3b. Full booking cycle on a movie that was NOT in the original line-up")
    m, free = await free_seats(session, show_id)
    seat = free[0]
    b = await call(session, "create_booking", show_id=show_id, seats=[seat], email="found-it@example.com", phone="9876543210")
    check("a movie brought in via add_movie_to_lineup can be booked like any other", b.ok, b.error or "")
    if not b.ok:
        return
    active_codes.add(b.data["booking_code"])
    p = await call(session, "confirm_payment", booking_code=b.data["booking_code"])
    check("...and paid for", p.ok and p.data["status"] == "CONFIRMED", p.error or "")
    c = await call(session, "cancel_booking", booking_code=b.data["booking_code"])
    check("...and cancelled, same as any other booking", c.ok, c.error or "")
    active_codes.discard(b.data["booking_code"])


async def test_showtimes(session):
    section("4. get_showtimes")
    r = await call(session, "get_showtimes", movie_id=1)
    check("returns upcoming shows for Agent 404", r.ok and len(r.data) > 0, r.error or "")
    shows = r.data
    need = {"show_id", "movie", "theatre", "screen", "date", "time", "price_from_inr", "price_by_tier_inr", "seats_available"}
    check("each show has all fields", all(need <= set(s) for s in shows))
    check("dates/times are formatted YYYY-MM-DD and HH:MM", all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["date"]) and re.fullmatch(r"\d{2}:\d{2}", s["time"]) for s in shows))
    check("shows are in chronological order", [(s["date"], s["time"]) for s in shows] == sorted((s["date"], s["time"]) for s in shows))
    check("three price tiers, Silver < Gold < Platinum",
          all(list(s["price_by_tier_inr"]) == ["Silver", "Gold", "Platinum"] and s["price_by_tier_inr"]["Silver"] < s["price_by_tier_inr"]["Gold"] < s["price_by_tier_inr"]["Platinum"] for s in shows))
    check("price_from equals the Silver price", all(s["price_from_inr"] == s["price_by_tier_inr"]["Silver"] for s in shows))

    tomorrow = (await call(session, "get_showtimes", movie_id=1, date="tomorrow")).data
    check("date='tomorrow' returns shows all on one single date", tomorrow and len({s["date"] for s in tomorrow}) == 1)
    by_iso = (await call(session, "get_showtimes", movie_id=1, date=tomorrow[0]["date"])).data
    check("date='YYYY-MM-DD' gives the same shows as 'tomorrow'", [s["show_id"] for s in by_iso] == [s["show_id"] for s in tomorrow])
    today = await call(session, "get_showtimes", movie_id=1, date="today")
    check("date='today' works (may be empty late in the day)", today.ok and len({s["date"] for s in today.data}) <= 1)

    bad = await call(session, "get_showtimes", movie_id=1, date="next friday")
    check("a bad date is rejected with a clear message", not bad.ok and "date" in bad.error.lower(), bad.error or "")
    r = await call(session, "get_showtimes", movie_id=999999)
    check("unknown movie id returns an empty list", r.ok and r.data == [])
    r = await call(session, "get_showtimes", movie_id="abc")
    check("non-numeric movie id is rejected", not r.ok)
    return tomorrow


async def test_seats(session, show):
    section("5. suggest_seats and get_seat_map")
    sid = show["show_id"]
    m = (await call(session, "get_seat_map", show_id=sid)).data
    need = {"show_id", "movie", "theatre", "date", "time", "price_by_tier_inr", "seats_available", "free_seats_by_row", "aisle_after_seat_number"}
    check("seat map has all fields", need <= set(m), str(need - set(m)))
    check("free seats add up to seats_available", sum(len(v) for v in m["free_seats_by_row"].values()) == m["seats_available"])
    check("rows are lettered within A-H", set(m["free_seats_by_row"]) <= set("ABCDEFGH"))
    check("every seat label belongs to its row", all(s[0] == row for row, seats in m["free_seats_by_row"].items() for s in seats))
    check("tier map covers rows A-H", {r for t in m["price_by_tier_inr"].values() for r in t["rows"]} == set("ABCDEFGH"))

    for n in range(1, 7):
        r = await call(session, "suggest_seats", show_id=sid, count=n)
        ok = r.ok and len(r.data["seats"]) == n and len(set(r.data["seats"])) == n
        expected_total = sum(seat_price(m["price_by_tier_inr"], s) for s in r.data["seats"]) if r.ok else None
        check(f"suggest_seats count={n}: {n} distinct seats, correct tier total", ok and r.data["total_price_inr"] == expected_total, r.error or str(r.data))
    r = await call(session, "suggest_seats", show_id=sid, count=3)
    rows = {s[0] for s in r.data["seats"]}
    nums = sorted(int(s[1:]) for s in r.data["seats"])
    check("3 suggested seats are together in one row", r.data["seated_together"] and len(rows) == 1 and nums == list(range(nums[0], nums[0] + 3)), str(r.data))
    m2 = (await call(session, "get_seat_map", show_id=sid)).data
    check("suggesting does NOT reserve anything", m2["seats_available"] == m["seats_available"])

    check("count=0 is rejected", not (await call(session, "suggest_seats", show_id=sid, count=0)).ok)
    check("count=7 is rejected", not (await call(session, "suggest_seats", show_id=sid, count=7)).ok)
    r = await call(session, "suggest_seats", show_id=999999, count=2)
    check("suggest_seats on an unknown show gives a clear error", not r.ok and "not exist" in r.error, r.error or "")
    r = await call(session, "get_seat_map", show_id=999999)
    check("get_seat_map on an unknown show gives a clear error", not r.ok and "not exist" in r.error, r.error or "")
    check("missing required argument is rejected", not (await call(session, "suggest_seats", show_id=sid)).ok)


async def test_booking_lifecycle(session, show):
    section("6. create_booking (validation, holds, conflicts)")
    sid = show["show_id"]
    email = "MCP.Tester@Example.com"
    m, free = await free_seats(session, sid)
    tiers = m["price_by_tier_inr"]
    before = m["seats_available"]
    sg = (await call(session, "suggest_seats", show_id=sid, count=2)).data["seats"]

    b = await call(session, "create_booking", show_id=sid, seats=sg, email=email, phone="98765 43210", name="MCP Tester")
    check("holds the seats and returns a booking", b.ok, b.error or "")
    b = b.data
    active_codes.add(b["booking_code"])
    check("booking code looks like TT-XXXXXX", re.fullmatch(r"TT-[A-Z0-9]{6}", b["booking_code"]), b["booking_code"])
    check("status is PENDING_PAYMENT until paid", b["status"] == "PENDING_PAYMENT")
    check("seats match what was asked", sorted(b["seats"]) == sorted(sg))
    check("total = sum of each seat's tier price", b["total_amount_inr"] == sum(seat_price(tiers, s) for s in sg), f"{b['total_amount_inr']}")
    check("email is normalised to lower-case", b["email"] == email.lower(), b["email"])
    check("phone is normalised (spaces removed)", b["phone"] == "9876543210", b["phone"])
    check("hold expires in about 10 minutes", 9 <= b.get("hold_expires_in_minutes", 0) <= 10.1, str(b.get("hold_expires_in_minutes")))
    check("response tells the agent the next step", "confirm_payment" in b.get("next_step", ""))

    m2, free2 = await free_seats(session, sid)
    check("held seats disappear from the seat map", not (set(sg) & set(free2)))
    check("seats_available dropped by exactly 2", m2["seats_available"] == before - 2, f"{before} -> {m2['seats_available']}")

    dup = await call(session, "create_booking", show_id=sid, seats=sg, email="other@example.com", phone="9876543210")
    check("booking the same seats again fails: 'already taken'", not dup.ok and "already taken" in dup.error, dup.error or "")

    spare = next(s for s in free2 if s not in sg)
    mixed = await call(session, "create_booking", show_id=sid, seats=[sg[0], spare], email="other@example.com", phone="9876543210")
    _, free3 = await free_seats(session, sid)
    check("a booking with one taken seat is rejected as a whole", not mixed.ok)
    check("...and the free seat in it was NOT held (all or nothing)", spare in free3)

    bad = {
        "invalid email": dict(seats=[spare], email="nope", phone="9876543210"),
        "invalid phone": dict(seats=[spare], email="a@b.co", phone="123"),
        "7 seats": dict(seats=[f"A{i}" for i in range(1, 8)], email="a@b.co", phone="9876543210"),
        "no seats": dict(seats=[], email="a@b.co", phone="9876543210"),
        "unknown seat Z99": dict(seats=["Z99"], email="a@b.co", phone="9876543210"),
    }
    for label, args in bad.items():
        r = await call(session, "create_booking", show_id=sid, **args)
        check(f"rejects {label}", not r.ok and bool(r.error), r.error or "was accepted")
    check("rejects an unknown show", not (await call(session, "create_booking", show_id=999999, seats=["A1"], email="a@b.co", phone="9876543210")).ok)
    check("rejects a missing required argument", not (await call(session, "create_booking", show_id=sid, seats=[spare])).ok)

    lo = await call(session, "create_booking", show_id=sid, seats=[spare.lower(), spare], email="dedupe@example.com", phone="9876543210")
    if lo.ok:
        active_codes.add(lo.data["booking_code"])
    check("lower-case and repeated seat labels are normalised and de-duplicated", lo.ok and lo.data["seats"] == [spare], lo.error or str(lo.data))
    return b, lo.data if lo.ok else None, email.lower(), sid, tiers


async def test_payment(session, b, b_extra, sid):
    section("7. confirm_payment")
    code = b["booking_code"]
    p = await call(session, "confirm_payment", booking_code=code)
    check("wallet payment confirms the booking", p.ok and p.data["status"] == "CONFIRMED", p.error or "")
    p = p.data
    check("payment has a PAY- reference and method 'wallet'", str(p.get("payment_reference", "")).startswith("PAY-") and p.get("payment_method") == "wallet")
    check("no hold timer once paid", "hold_expires_in_minutes" not in p)
    again = await call(session, "confirm_payment", booking_code=code)
    check("paying twice is safe (same booking, same reference)", again.ok and again.data["payment_reference"] == p["payment_reference"], again.error or "")
    check("get_booking now reports CONFIRMED", (await call(session, "get_booking", booking_code=code)).data["status"] == "CONFIRMED")

    x = b_extra["booking_code"]
    r = await call(session, "confirm_payment", booking_code=x, method="upi")
    check("UPI without a upi_id is rejected", not r.ok, r.error or "")
    r = await call(session, "confirm_payment", booking_code=x, method="upi", upi_id="not-a-upi")
    check("malformed UPI id is rejected", not r.ok, r.error or "")
    r = await call(session, "confirm_payment", booking_code=x.lower(), method="upi", upi_id="tester@okbank")
    check("valid UPI id pays (booking code is case-insensitive)", r.ok and r.data["status"] == "CONFIRMED" and r.data["payment_method"] == "upi", r.error or "")
    check("method='bitcoin' is rejected by the schema", not (await call(session, "confirm_payment", booking_code=x, method="bitcoin")).ok)
    check("method='card' is not offered", not (await call(session, "confirm_payment", booking_code=x, method="card")).ok)
    r = await call(session, "confirm_payment", booking_code="TT-NOPE00")
    check("unknown booking code gives a clear error", not r.ok and "no booking" in r.error.lower(), r.error or "")


async def test_lookup(session, email, created):
    section("8. get_booking and list_bookings")
    r = await call(session, "get_booking", booking_code=created[0])
    need = {"booking_code", "status", "movie", "theatre", "screen", "date", "time", "seats", "total_amount_inr", "email", "phone"}
    check("get_booking returns every field", r.ok and need <= set(r.data), r.error or "")
    check("get_booking on an unknown code is a clear error", not (await call(session, "get_booking", booking_code="TT-ZZZZZZ")).ok)
    lst = await call(session, "list_bookings", email=email.upper())
    check("list_bookings finds bookings (email is case-insensitive)", lst.ok and len(lst.data) >= len(created), lst.error or "")
    check("only that customer's bookings are returned", all(x["email"] == email for x in lst.data))
    ours = [x["booking_code"] for x in lst.data if x["booking_code"] in created]
    check("newest bookings come first", ours == list(reversed(created)), f"{ours} vs {list(reversed(created))}")
    r = await call(session, "list_bookings", email="nobody-here@example.com")
    check("unknown email returns an empty list", r.ok and r.data == [])
    check("missing email is rejected", not (await call(session, "list_bookings")).ok)


async def test_cancel(session, confirmed_code, sid):
    section("9. cancel_booking")
    m_before, _ = await free_seats(session, sid)
    seats = (await call(session, "get_booking", booking_code=confirmed_code)).data["seats"]
    total = (await call(session, "get_booking", booking_code=confirmed_code)).data["total_amount_inr"]
    r = await call(session, "cancel_booking", booking_code=confirmed_code)
    check("cancelling a paid booking works", r.ok and r.data["status"] == "CANCELLED", r.error or "")
    check("full refund equals the amount paid", r.ok and r.data["refund_amount_inr"] == total, str(r.data))
    active_codes.discard(confirmed_code)
    m_after, free_after = await free_seats(session, sid)
    check("its seats are released back to the seat map", set(seats) <= set(free_after) and m_after["seats_available"] == m_before["seats_available"] + len(seats))
    check("cancelling again fails clearly", not (await call(session, "cancel_booking", booking_code=confirmed_code)).ok)
    r = await call(session, "confirm_payment", booking_code=confirmed_code)
    check("paying a cancelled booking is refused", not r.ok and "cancelled" in r.error.lower(), r.error or "")
    check("cancelling an unknown code fails clearly", not (await call(session, "cancel_booking", booking_code="TT-ZZZZZZ")).ok)


async def test_pending_cancel_and_tiers(session, sid, tiers):
    section("10. Tier pricing and cancelling an unpaid hold")
    m, free = await free_seats(session, sid)
    pick = [next(s for s in free if s[0] in t["rows"]) for t in tiers.values()]  # one seat in each tier
    r = await call(session, "create_booking", show_id=sid, seats=pick, email="tiers@example.com", phone="9876543210")
    expected = sum(seat_price(tiers, s) for s in pick)
    check(f"one seat per tier {pick} totals {expected}", r.ok and r.data["total_amount_inr"] == expected, r.error or str(r.data))
    if r.ok:
        c = await call(session, "cancel_booking", booking_code=r.data["booking_code"])
        check("cancelling an UNPAID hold refunds nothing", c.ok and c.data["refund_amount_inr"] == 0, c.error or str(c.data))
        _, free_after = await free_seats(session, sid)
        check("and releases the held seats", set(pick) <= set(free_after))


async def test_live_events(session, sid):
    section("11. The agent's actions produce live events for the website")
    start = http_json(API, "/api/events/poll")["last"]
    _, free = await free_seats(session, sid)
    seat = free[len(free) // 2]
    b = (await call(session, "create_booking", show_id=sid, seats=[seat], email="events@example.com", phone="9876543210")).data
    await call(session, "confirm_payment", booking_code=b["booking_code"])
    await call(session, "cancel_booking", booking_code=b["booking_code"])
    evs = [e for e in http_json(API, f"/api/events/poll?since={start}")["events"] if e["booking"]["code"] == b["booking_code"]]
    check("created → confirmed → cancelled events were broadcast", [e["type"] for e in evs] == ["booking.created", "booking.confirmed", "booking.cancelled"], str([e["type"] for e in evs]))
    check("every event is tagged source='agent' (drives the 🤖 badge)", evs and all(e["booking"]["source"] == "agent" for e in evs))
    check("events never contain the customer's phone or full email", all("phone" not in e["booking"] and "events@example.com" not in json.dumps(e) for e in evs))


async def test_expiry():
    section("12. An unpaid hold expires")
    if not EXPIRY_API:
        print("  ⏭  skipped (set EXPIRY_API_URL to a backend started with HOLD_MINUTES=0.05)")
        return
    async with stdio_client(stdio_params(EXPIRY_API)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            shows = (await call(s, "get_showtimes", movie_id=1, date="tomorrow")).data
            sid = shows[0]["show_id"]
            seats = (await call(s, "suggest_seats", show_id=sid, count=2)).data["seats"]
            b = (await call(s, "create_booking", show_id=sid, seats=seats, email="expiry@example.com", phone="9876543210")).data
            await asyncio.sleep(5)
            p = await call(s, "confirm_payment", booking_code=b["booking_code"])
            check("paying after the hold ran out is refused: 'expired'", not p.ok and "expired" in p.error.lower(), p.error or "")
            check("the booking is marked EXPIRED", (await call(s, "get_booking", booking_code=b["booking_code"])).data["status"] == "EXPIRED")
            _, free = await free_seats(s, sid)
            check("and its seats are free again", set(seats) <= set(free))


async def test_backend_down():
    section("13. Backend unreachable")
    async with stdio_client(stdio_params("http://127.0.0.1:9")) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await call(s, "browse_now_showing")
            check("agent gets a readable error, not a crash", not res.ok and "could not reach" in res.error.lower(), res.error or "")
            check("the server is still alive afterwards", len((await s.list_tools()).tools) == len(EXPECTED_TOOLS))


async def test_http_transport():
    section("14. Same server over streamable HTTP (remote MCP)")
    port = 8011
    proc = subprocess.Popen([sys.executable, SERVER, "--transport", "http", "--port", str(port)],
                            env={**os.environ, "TICKETTOWN_API_URL": API}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (r, w, _g):
                    async with ClientSession(r, w) as s:
                        await s.initialize()
                        tools = {t.name for t in (await s.list_tools()).tools}
                        check("all 9 tools are listed over HTTP", tools == set(EXPECTED_TOOLS), str(tools))
                        movies = await call(s, "browse_now_showing", query="agent")
                        check("search works over HTTP", movies.ok and movies.data and movies.data[0]["title"] == "Agent 404")
                        shows = (await call(s, "get_showtimes", movie_id=1, date="tomorrow")).data
                        seats = (await call(s, "suggest_seats", show_id=shows[-1]["show_id"], count=1)).data["seats"]
                        b = await call(s, "create_booking", show_id=shows[-1]["show_id"], seats=seats, email="http@example.com", phone="9876543210")
                        check("book + cancel round trip works over HTTP", b.ok and (await call(s, "cancel_booking", booking_code=b.data["booking_code"])).ok, b.error or "")
                return
            except Exception as e:  # server still starting
                last = e
                await asyncio.sleep(0.5)
        check("HTTP transport starts and answers", False, repr(last))
    finally:
        proc.terminate()


# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print(f"Testing the MCP server at {SERVER}\nBackend: {API}")
    try:
        http_json(API, "/api/health")
    except Exception as e:
        print(f"\n❌ Backend not reachable at {API}: {e}")
        sys.exit(2)

    async with stdio_client(stdio_params(API)) as (r, w):
        async with ClientSession(r, w) as session:
            init = await session.initialize()
            await test_discovery(session, init)
            movies = await test_browse(session)
            discovered = await test_discover_and_activate(session, movies)
            tomorrow = await test_showtimes(session)
            show = next((s for s in tomorrow if s["seats_available"] >= 40), tomorrow[0])
            await test_seats(session, show)
            b, extra, email, sid, tiers = await test_booking_lifecycle(session, show)
            if extra is None:
                extra = b
            await test_payment(session, b, extra, sid)
            await test_lookup(session, email, [b["booking_code"]])
            await test_cancel(session, b["booking_code"], sid)
            await test_pending_cancel_and_tiers(session, sid, tiers)
            await test_live_events(session, sid)
            if discovered and discovered[1]:
                await test_book_discovered_movie(session, discovered[1]["show_id"])
            # tidy up anything we left behind
            for code in list(active_codes):
                await call(session, "cancel_booking", booking_code=code)
    await test_expiry()
    await test_backend_down()
    await test_http_transport()

    failed = [n for n, ok in results if not ok]
    print(f"\n{'═' * 60}\n{len(results) - len(failed)}/{len(results)} checks passed")
    for n in failed:
        print(f"  ❌ {n}")
    sys.exit(1 if failed else 0)


asyncio.run(main())
