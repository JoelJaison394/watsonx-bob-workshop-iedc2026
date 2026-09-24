# OpenAPI Tool Project — Weather Assistant

A guided project: build an AI agent in **watsonx Orchestrate** that can answer weather questions, using an **OpenAPI tool** instead of MCP. This is the other way Orchestrate can call an external API — no server to write, just a spec to import.

**Compare this to [`../TicketTown`](../TicketTown):** TicketTown needed a whole Python MCP server, because *we* built and control that backend. Here, someone else already runs the weather API — Orchestrate can call it directly once it knows the API's shape, which is exactly what an OpenAPI spec describes.

## The API: Open-Meteo

[Open-Meteo](https://open-meteo.com) — free, real-time weather for any location on Earth, **no API key, no signup**. Chosen deliberately for a first OpenAPI-tool project: nothing to register for, nothing that can expire mid-workshop, one clean endpoint to start with.

Try it right now in a terminal or browser — this is the exact request the tool will make:

```bash
curl "https://api.open-meteo.com/v1/forecast?latitude=12.97&longitude=77.59&current_weather=true&timezone=auto"
```

```json
{
  "latitude": 12.97, "longitude": 77.56,
  "timezone": "Asia/Kolkata", "elevation": 914.0,
  "current_weather": {
    "time": "2026-09-24T07:30", "temperature": 20.7,
    "windspeed": 14.8, "winddirection": 252,
    "is_day": 1, "weathercode": 3
  }
}
```

`latitude`/`longitude` locate the place; `weathercode` is a [WMO code](https://open-meteo.com/en/docs#weathervariables) (0 = clear sky, 61-67 = rain, 95-99 = thunderstorm, etc.).

## The spec: [`weather-openapi.yaml`](weather-openapi.yaml)

**Open-Meteo doesn't publish its own OpenAPI/Swagger file** (checked their site, their GitHub, and the usual `/openapi.json` paths — nothing). That's common for smaller or community APIs, and it's a useful thing to know: **an OpenAPI tool doesn't require the API owner to have written a spec.** Anyone can write one that accurately describes an existing API, and that's what this file is — hand-written from Open-Meteo's docs and its real response, covering just the one endpoint above, kept small on purpose for a first project.

It's a real, validated OpenAPI 3.0.3 document — checked with `openapi-spec-validator`, and every field it declares was cross-checked against a live response from the API.

## Build it: import into watsonx Orchestrate

1. In Orchestrate, choose to add a tool from an **OpenAPI specification**.
2. Upload [`weather-openapi.yaml`](weather-openapi.yaml) (or paste its contents).
3. Orchestrate reads the spec and creates a tool from the `getCurrentWeather` operation, using the parameter descriptions in the file.
4. No authentication needed — Open-Meteo's endpoint is public.
5. Attach the new tool to an agent.

*(Exact menu names vary by Orchestrate version — look for "Add tool" or "Import" and an OpenAPI/Swagger option.)*

### Suggested agent instructions

```
You are a friendly weather assistant. You have one tool, getCurrentWeather, which
needs a latitude and longitude.

Rules:
1. If the customer names a city instead of coordinates, use your own knowledge to
   convert it to approximate latitude/longitude before calling the tool - the tool
   itself does not accept city names.
2. Always state the temperature in Celsius and describe the weathercode in plain
   words (e.g. "clear sky", "light rain", "thunderstorm") - never show the raw
   numeric code to the customer.
3. If is_day is 0, mention it's currently night there.
4. If the tool call fails, say so plainly and ask the customer to try again shortly.
```

Try asking it things like *"what's the weather in Bengaluru right now?"* or *"is it raining in Kochi?"*

## Stretch goals

- Add the `hourly` or `daily` parameters (see [Open-Meteo's docs](https://open-meteo.com/en/docs)) and extend the spec to cover a forecast, not just current conditions.
- Add a second operation for a different Open-Meteo endpoint (e.g. their [geocoding API](https://open-meteo.com/en/docs/geocoding-api), also free and keyless) so the agent can resolve a city name to coordinates itself, instead of guessing.
- Combine it with TicketTown: an agent that checks the weather before suggesting an outdoor vs. indoor plan, or simply mentions "it'll be raining, perfect night for a movie" alongside a booking.
