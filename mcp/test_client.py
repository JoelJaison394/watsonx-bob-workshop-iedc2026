"""Smoke test: talks to server.py exactly like an MCP client (stdio) and books tickets.

    python test_client.py                 # uses TICKETTOWN_API_URL or localhost:3000
    python test_client.py --http URL      # test a running `server.py --transport http`
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def unwrap(result):
    if result.isError:
        return {"ERROR": result.content[0].text}
    if result.structuredContent:
        return result.structuredContent.get("result", result.structuredContent)
    return json.loads(result.content[0].text)


async def run(session: ClientSession):
    await session.initialize()
    tools = (await session.list_tools()).tools
    print(f"{len(tools)} tools:", ", ".join(t.name for t in tools), "\n")

    async def call(tool, /, **args):
        out = unwrap(await session.call_tool(tool, args))
        print(f"→ {tool}({json.dumps(args)})\n  {json.dumps(out)[:260]}\n")
        return out

    movies = await call("search_movies", query="agent")
    shows = await call("get_showtimes", movie_id=movies[0]["movie_id"], date="tomorrow")
    show_id = shows[0]["show_id"]
    suggestion = await call("suggest_seats", show_id=show_id, count=2)
    await call("get_seat_map", show_id=show_id)
    booking = await call("create_booking", show_id=show_id, seats=suggestion["seats"],
                         email="workshop@example.com", phone="9876543210", name="Workshop Demo")
    await call("create_booking", show_id=show_id, seats=suggestion["seats"],
               email="other@example.com", phone="9876543210")  # should fail: seats taken
    paid = await call("confirm_payment", booking_code=booking["booking_code"], method="wallet")
    await call("get_booking", booking_code=paid["booking_code"])
    await call("list_bookings", email="workshop@example.com")
    await call("cancel_booking", booking_code=paid["booking_code"])


async def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--http":
        async with streamablehttp_client(sys.argv[2]) as (r, w, _):
            async with ClientSession(r, w) as session:
                await run(session)
    else:
        params = StdioServerParameters(command=sys.executable, args=["server.py"])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await run(session)


asyncio.run(main())
