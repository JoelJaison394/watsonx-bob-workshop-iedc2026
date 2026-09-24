# OpenAPI Tool Project — Weather Assistant

A guided project: build an AI agent in **watsonx Orchestrate** that answers weather questions using an **OpenAPI tool**, instead of MCP. An OpenAPI tool lets Orchestrate call an external API directly from its specification, with no server to write.

**Compared to [`../TicketTown`](../TicketTown):** TicketTown required a custom MCP server because it exposes a purpose-built backend. Here, the API already exists and is public, so Orchestrate can call it directly once given its OpenAPI specification.

## The API: Open-Meteo

[Open-Meteo](https://open-meteo.com) provides free, real-time weather data for any location worldwide. No API key or signup is required.

Example request — this is the exact call the tool makes:

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

`latitude`/`longitude` locate the place; `weathercode` is a [WMO code](https://open-meteo.com/en/docs#weathervariables) (0 = clear sky, 61–67 = rain, 95–99 = thunderstorm, etc.).

## The spec: [`weather-openapi.yaml`](weather-openapi.yaml)

Open-Meteo does not publish its own OpenAPI specification. This file describes the current-weather endpoint above, based on the public API documentation, and is a valid OpenAPI 3.0.3 document.

An OpenAPI tool does not require the API provider to supply the specification — any accurate description of an existing API can be used.

## Build it: import into watsonx Orchestrate

1. In Orchestrate, choose to add a tool from an **OpenAPI specification**.
2. Upload [`weather-openapi.yaml`](weather-openapi.yaml) (or paste its contents).
3. Orchestrate reads the spec and creates a tool from the `getCurrentWeather` operation, using the parameter descriptions in the file.
4. No authentication is required — Open-Meteo's endpoint is public.
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

Example questions: *"what's the weather in Bengaluru right now?"*, *"is it raining in Kochi?"*

## Stretch goals

- Add the `hourly` or `daily` parameters (see [Open-Meteo's docs](https://open-meteo.com/en/docs)) and extend the spec to cover a forecast, not just current conditions.
- Add a second operation for a different Open-Meteo endpoint (e.g. its [geocoding API](https://open-meteo.com/en/docs/geocoding-api), also free and keyless) so the agent can resolve a city name to coordinates itself.
- Combine it with TicketTown: an agent that checks the weather before suggesting an outdoor or indoor plan, or mentions the forecast alongside a booking.
