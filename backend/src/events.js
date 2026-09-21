// Server-Sent Events hub. The frontend subscribes to /api/events and gets a
// message every time a booking changes, so the UI updates live even when the
// booking was made by an AI agent through the MCP server.
const clients = new Set();

export function sseHandler(req, res) {
  res.set({
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no', // stop nginx-style proxies from buffering the stream
  });
  res.flushHeaders();
  res.write('retry: 2000\n\n');
  res.write(`event: hello\ndata: ${JSON.stringify({ ok: true })}\n\n`);
  clients.add(res);
  req.on('close', () => clients.delete(res));
}

// Recent events, kept so clients that can't hold a stream open (some tunnels and
// proxies buffer it) can poll instead: GET /api/events/poll?since=<seq>.
const RECENT_MAX = 200;
const recent = [];
let seq = 0;

export function broadcast(type, data) {
  const event = { type, ...data, at: Date.now(), seq: ++seq };
  recent.push(event);
  if (recent.length > RECENT_MAX) recent.shift();
  const payload = `event: ${type}\ndata: ${JSON.stringify(event)}\n\n`;
  for (const res of clients) res.write(payload);
}

export const lastSeq = () => seq;
export const eventsSince = (since) => recent.filter((e) => e.seq > since);

// Heartbeat so hosting proxies don't close idle connections.
setInterval(() => {
  for (const res of clients) res.write(': ping\n\n');
}, 20000).unref();

export const clientCount = () => clients.size;
