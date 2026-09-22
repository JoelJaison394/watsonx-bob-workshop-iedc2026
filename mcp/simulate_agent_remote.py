"""Same conversation as simulate_agent.py, but over streamable HTTP against a DEPLOYED MCP
server, instead of spawning a local stdio subprocess. Use this to verify a real deployment
(Render, OpenShift, ...) end to end, exactly as an Orchestrate agent would reach it.

    python simulate_agent_remote.py <mcp-url>
    python simulate_agent_remote.py https://workshop-mcp.example.com/mcp
"""
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

W = 78


def customer(line):
    print(f"\n\033[1;36m👤 Customer:\033[0m {line}")


def agent_says(line):
    print(f"\033[1;35m🤖 Agent:\033[0m {line}")


def tool_call(name, **args):
    printable = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"   \033[2m→ calling {name}({printable})\033[0m")


def unwrap(res):
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
    if len(sys.argv) < 2:
        print("usage: python simulate_agent_remote.py <mcp-url>")
        sys.exit(2)
    url = sys.argv[1]

    async with streamablehttp_client(url) as (r, w, _get_session_id):
        async with ClientSession(r, w) as session:
            init = await session.initialize()
            tools = (await session.list_tools()).tools
            print("=" * W)
            print(f" Connected over HTTP to: {url}")
            print(f" Server: {init.serverInfo.name} v{init.serverInfo.version}  ({len(tools)} tools live)")
            print(" " + ", ".join(t.name for t in tools))
            print("=" * W)

            async def call(name, **args):
                tool_call(name, **args)
                data, err = unwrap(await session.call_tool(name, args))
                if err:
                    print(f"   \033[1;31m✗ tool error:\033[0m {err}")
                    return None
                return data

            print("\n\033[1m── Scene 1: booking a movie that IS in the current line-up ──\033[0m")
            customer("What's showing right now?")
            movies = await call("browse_now_showing")
            titles = ", ".join(f"{m['title']} ({m['language']})" for m in movies[:6])
            agent_says(f"We have {len(movies)} movies on right now, including: {titles}...")

            pick = movies[0]
            customer(f"Book 2 seats for {pick['title']} tomorrow evening.")
            shows = await call("get_showtimes", movie_id=pick["movie_id"], date="tomorrow")
            if not shows:
                shows = await call("get_showtimes", movie_id=pick["movie_id"])
            show = shows[0]
            agent_says(f"Found it: {show['theatre']} at {show['time']} on {show['date']}, seats from ₹{show['price_from_inr']}.")

            suggestion = await call("suggest_seats", show_id=show["show_id"], count=2)
            agent_says(f"I'd suggest seats {', '.join(suggestion['seats'])}, together, for ₹{suggestion['total_price_inr']} total.")

            customer("Sounds good. My email is remote-test@example.com, phone 9876543210.")
            booking = await call(
                "create_booking", show_id=show["show_id"], seats=suggestion["seats"],
                email="remote-test@example.com", phone="9876543210",
            )
            agent_says(
                f"Holding {', '.join(booking['seats'])} for {booking['movie']} - ₹{booking['total_amount_inr']} total. "
                f"Booking code {booking['booking_code']}. Shall I pay now with your wallet?"
            )

            customer("Yes, go ahead.")
            paid = await call("confirm_payment", booking_code=booking["booking_code"])
            agent_says(f"{paid['message']} Your seats: {', '.join(paid['seats'])}. See you at {paid['time']}!")

            print("\n\033[1m── Scene 2: booking a movie that is NOT in the current line-up ──\033[0m")
            requested_title = "The Godfather"
            customer(f"Can I book 1 ticket for {requested_title} tonight?")
            local_hits = await call("browse_now_showing", query=requested_title)
            if local_hits:
                agent_says(f"Good news, {requested_title} is already showing.")
                new_movie_id = local_hits[0]["movie_id"]
                new_shows = await call("get_showtimes", movie_id=new_movie_id)
            else:
                agent_says("That's not in our current line-up. Let me check if it exists at all.")
                found = await call("find_any_movie", title=requested_title)
                top = found[0]
                agent_says(f"Found \"{top['title']}\" ({top['year']}, {top['language']}). Is that the one?")
                customer("Yes, that's the one.")
                added = await call("add_movie_to_lineup", tmdb_id=top["tmdb_id"])
                agent_says(
                    f"Done - {added['title']} is now showing, with {len(added['showtimes'])} showtimes over the next few days. "
                    f"It's live on the website right now too."
                )
                new_shows = added["showtimes"]

            show2 = new_shows[0]
            seat2 = (await call("suggest_seats", show_id=show2["show_id"], count=1))["seats"][0]
            agent_says(f"Seat {seat2} at {show2['theatre']}, {show2['time']}.")
            b2 = await call(
                "create_booking", show_id=show2["show_id"], seats=[seat2],
                email="remote-test@example.com", phone="9876543210",
            )
            agent_says(f"Held {seat2} - booking code {b2['booking_code']}, ₹{b2['total_amount_inr']}.")
            cancelled = await call("cancel_booking", booking_code=b2["booking_code"])
            agent_says(f"Released it as a demo cleanup (status: {cancelled['status']}).")

            print("\n\033[1m── Scene 3: an error the agent has to recover from ──\033[0m")
            customer(f"Book seat {booking['seats'][0]} for that same {pick['title']} show again please.")
            clash = await call("create_booking", show_id=show["show_id"], seats=[booking["seats"][0]], email="someone-else@example.com", phone="9998887776")
            if clash is None:
                agent_says("That seat's already taken - let me find you another one.")
                alt = await call("suggest_seats", show_id=show["show_id"], count=1)
                agent_says(f"How about {alt['seats'][0]} instead, for ₹{alt['total_price_inr']}?")

            print("\n\033[1m── Wrapping up ──\033[0m")
            mine = await call("list_bookings", email="remote-test@example.com")
            for b in mine:
                agent_says(f"  {b['booking_code']}: {b['movie']}, {b['seats']}, {b['status']}, ₹{b['total_amount_inr']}")

            # tidy up: cancel the confirmed booking this run made
            await call("cancel_booking", booking_code=booking["booking_code"])

            print("\n" + "=" * W)
            print(" Simulation complete - every step above was a REAL call to the REAL deployed server.")
            print("=" * W)


asyncio.run(main())
