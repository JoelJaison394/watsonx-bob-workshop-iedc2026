"""Simulates a real customer conversation with an agent that uses these MCP tools.

Not an assertion-based test (see test_tools.py for that) - this is a readable transcript
of a plausible session, so you can see with your own eyes that the tools actually do what
their descriptions promise, in the order a real agent would call them.

    python simulate_agent.py
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

W = 78


def customer(line):
    print(f"\n\033[1;36m👤 Customer:\033[0m {line}")


def agent_says(line):
    print(f"\033[1;35m🤖 Agent:\033[0m {line}")


def tool_call(name, **args):
    printable = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"   \033[2m→ calling {name}({printable})\033[0m")


def unwrap(res):
    """FastMCP wraps a list-returning tool's structured output as {"result": [...]} - unwrap that,
    same as test_tools.py's Result class does, so callers just get the plain list or dict back."""
    if res.isError:
        return None, res.content[0].text
    if res.structuredContent is not None:
        sc = res.structuredContent
        return (sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc), None
    text = res.content[0].text if res.content else "{}"
    data = json.loads(text)
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    return data, None


async def main():
    server = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(server) as (r, w):
        async with ClientSession(r, w) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            print("=" * W)
            print(f" Connected to MCP server: {init.serverInfo.name}  ({len(tools)} tools live)")
            print(" " + ", ".join(t.name for t in tools))
            print("=" * W)

            async def call(name, **args):
                tool_call(name, **args)
                data, err = unwrap(await session.call_tool(name, args))
                if err:
                    print(f"   \033[1;31m✗ tool error:\033[0m {err}")
                    return None
                return data

            # ── Scene 1: an ordinary booking for whatever's actually showing ──────────
            print("\n\033[1m── Scene 1: booking a movie that IS in the current line-up ──\033[0m")
            customer("What's showing right now?")
            movies = await call("browse_now_showing")
            titles = ", ".join(f"{m['title']} ({m['language']})" for m in movies[:6])
            agent_says(f"We have {len(movies)} movies on right now, including: {titles}...")

            pick = movies[0]
            customer(f"What are the showtimes for {pick['title']} tomorrow?")
            lookup = await call("get_showtimes_for_movie", title=pick["title"], date="tomorrow")
            shows = lookup["showtimes"] if lookup and lookup.get("currently_showing") else []
            if not shows:
                shows = (await call("get_showtimes", movie_id=pick["movie_id"]))
            show = shows[0]
            agent_says(f"Found it: {show['theatre']} at {show['time']} on {show['date']}, seats from ₹{show['price_from_inr']}.")
            customer("Book 2 seats please.")

            suggestion = await call("suggest_seats", show_id=show["show_id"], count=2)
            agent_says(f"I'd suggest seats {', '.join(suggestion['seats'])}, together, for ₹{suggestion['total_price_inr']} total.")

            customer("Sounds good. My email is priya@example.com, phone 9876543210.")
            booking = await call(
                "create_booking",
                show_id=show["show_id"],
                seats=suggestion["seats"],
                email="priya@example.com",
                phone="9876543210",
            )
            agent_says(
                f"Holding {', '.join(booking['seats'])} for {booking['movie']} - ₹{booking['total_amount_inr']} total. "
                f"Booking code {booking['booking_code']}. Shall I pay now with your wallet?"
            )

            customer("Yes, go ahead.")
            paid = await call("confirm_payment", booking_code=booking["booking_code"])
            agent_says(f"{paid['message']} Your seats: {', '.join(paid['seats'])}. See you at {paid['time']}!")

            # ── Scene 2: a movie that ISN'T listed - the discovery flow ────────────────
            print("\n\033[1m── Scene 2: booking a movie that is NOT in the current line-up ──\033[0m")
            requested_title = "The Matrix"
            customer(f"Can I book 2 tickets for {requested_title} tonight?")
            local_hits = await call("browse_now_showing", query=requested_title)
            if local_hits:
                agent_says(f"Good news, {requested_title} is already showing - let me pull up times.")
            else:
                agent_says(f"That's not in our current line-up. Let me check if it exists at all.")
                found = await call("find_any_movie", title=requested_title)
                if not found:
                    agent_says("Sorry, I couldn't find that title anywhere.")
                else:
                    top = found[0]
                    agent_says(f"Found \"{top['title']}\" ({top['year']}, {top['language']}). Is that the one?")
                    customer("Yes, that's the one.")
                    added = await call("add_movie_to_lineup", tmdb_id=top["tmdb_id"])
                    agent_says(
                        f"Done - {added['title']} is now showing, with {len(added['showtimes'])} showtimes over the next few days. "
                        f"It's live on the website right now too."
                    )
                    show2 = added["showtimes"][0]
                    seats2 = await call("suggest_seats", show_id=show2["show_id"], count=2)
                    agent_says(f"Seats {', '.join(seats2['seats'])} at {show2['theatre']}, {show2['time']} - ₹{seats2['total_price_inr']} total. Confirm?")
                    customer("Actually, let me think about it - cancel that.")
                    b2 = await call(
                        "create_booking", show_id=show2["show_id"], seats=seats2["seats"],
                        email="priya@example.com", phone="9876543210",
                    )
                    cancelled = await call("cancel_booking", booking_code=b2["booking_code"])
                    agent_says(f"No problem, released those seats. (status: {cancelled['status']}, refund ₹{cancelled['refund_amount_inr']})")

            # ── Scene 3: an error the agent has to handle gracefully ────────────────────
            print("\n\033[1m── Scene 3: an error the agent has to recover from ──\033[0m")
            customer(f"Book seat {booking['seats'][0]} for that same {pick['title']} show again please.")
            clash = await call("create_booking", show_id=show["show_id"], seats=[booking["seats"][0]], email="someone-else@example.com", phone="9998887776")
            if clash is None:
                agent_says("That seat's already taken by a previous booking - let me find you another one.")
                alt = await call("suggest_seats", show_id=show["show_id"], count=1)
                agent_says(f"How about {alt['seats'][0]} instead, for ₹{alt['total_price_inr']}?")

            # ── Wrap up ──────────────────────────────────────────────────────────────
            print("\n\033[1m── Wrapping up ──\033[0m")
            customer(f"What have I booked? My email is priya@example.com.")
            mine = await call("list_bookings", email="priya@example.com")
            for b in mine:
                agent_says(f"  {b['booking_code']}: {b['movie']}, {b['seats']}, {b['status']}, ₹{b['total_amount_inr']}")

            # tidy up: cancel the confirmed booking this simulation made, so it doesn't linger
            await call("cancel_booking", booking_code=booking["booking_code"])

            print("\n" + "=" * W)
            print(" Simulation complete - every step above was a REAL call to the REAL backend.")
            print("=" * W)


asyncio.run(main())
