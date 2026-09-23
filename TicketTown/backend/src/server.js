// TicketTown API - Express + SQLite.
// Every route here is also exposed to the AI agent through the MCP server.
import './env.js'; // must stay first: loads backend/.env before other modules read process.env
import express from 'express';
import cors from 'cors';
import crypto from 'node:crypto';
import { db, tx } from './db.js';
import { ensureCatalog, ensureShows, ensureShowsForMovie, localNow, seatLabels } from './seed.js';
import { seatTotal, tiersFor } from './catalog.js';
import { syncMovies, tmdbEnabled, searchMovie, activateMovie } from './tmdb.js';
import { sseHandler, broadcast, clientCount, lastSeq, eventsSince } from './events.js';

const PORT = Number(process.env.PORT) || 3000;
const HOLD_MINUTES = Number(process.env.HOLD_MINUTES) || 10;
const ADMIN_KEY = process.env.ADMIN_KEY || 'tickettown';
const MAX_SEATS = 6;
const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O/1/I to avoid mix-ups

const app = express();
// Accept requests from any origin (Replit preview, localhost, Orchestrate...).
app.use(cors());
app.use(express.json({ limit: '50kb' }));

// ---------- helpers ----------------------------------------------------------

class ApiError extends Error {
  constructor(status, code, message, extra = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}
const fail = (status, code, message, extra) => {
  throw new ApiError(status, code, message, extra);
};

const randomCode = (prefix, len) =>
  prefix + Array.from({ length: len }, () => CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)]).join('');

const seatSort = (a, b) => a[0].localeCompare(b[0]) || Number(a.slice(1)) - Number(b.slice(1));
const isStarted = (show) => {
  const now = localNow();
  return show.show_date < now.date || (show.show_date === now.date && show.show_time <= now.time);
};

const maskEmail = (email) => {
  const [user, domain = ''] = email.split('@');
  return `${user.slice(0, 1)}${'*'.repeat(Math.max(user.length - 1, 2))}@${domain}`;
};

const SHOW_SQL = `
  SELECT s.*, m.title AS movie_title, m.genre, m.language, m.rating, m.duration_min,
         m.emoji, m.color1, m.color2, m.poster_url,
         (SELECT COUNT(*) FROM booking_seats bs WHERE bs.show_id = s.id) AS taken
  FROM shows s JOIN movies m ON m.id = s.movie_id`;

const showDto = (r) => ({
  id: r.id,
  movie_id: r.movie_id,
  movie_title: r.movie_title,
  genre: r.genre,
  language: r.language,
  rating: r.rating,
  duration_min: r.duration_min,
  emoji: r.emoji,
  color1: r.color1,
  color2: r.color2,
  poster_url: r.poster_url,
  theatre: r.theatre,
  screen: r.screen,
  date: r.show_date,
  time: r.show_time,
  price: r.price, // the cheapest (Silver) seat; see tiers for the rest
  tiers: tiersFor(r.price),
  currency: 'INR',
  rows: r.seat_rows,
  cols: r.seat_cols,
  aisle_after: Math.floor(r.seat_cols / 2),
  total_seats: r.seat_rows * r.seat_cols,
  seats_available: r.seat_rows * r.seat_cols - r.taken,
  started: isStarted(r),
});

function getShow(id) {
  const row = db.prepare(`${SHOW_SQL} WHERE s.id = ?`).get(id);
  if (!row) fail(404, 'SHOW_NOT_FOUND', `Show ${id} does not exist.`);
  return row;
}

function seatState(showId) {
  const rows = db
    .prepare(
      `SELECT bs.seat, b.status FROM booking_seats bs
       JOIN bookings b ON b.id = bs.booking_id WHERE bs.show_id = ?`,
    )
    .all(showId);
  return {
    booked: rows.filter((r) => r.status === 'CONFIRMED').map((r) => r.seat).sort(seatSort),
    held: rows.filter((r) => r.status === 'PENDING_PAYMENT').map((r) => r.seat).sort(seatSort),
  };
}

const BOOKING_SQL = `
  SELECT b.*, s.movie_id, s.theatre, s.screen, s.show_date, s.show_time, s.price, m.title AS movie_title
  FROM bookings b
  JOIN shows s ON s.id = b.show_id
  JOIN movies m ON m.id = s.movie_id`;

function getBooking(code) {
  const row = db.prepare(`${BOOKING_SQL} WHERE b.code = ?`).get(String(code).toUpperCase());
  if (!row) fail(404, 'BOOKING_NOT_FOUND', `No booking found with code ${code}.`);
  return row;
}

const bookingDto = (r) => ({
  code: r.code,
  status: r.status,
  source: r.source,
  seats: r.seats.split(',').filter(Boolean),
  seat_count: r.seats.split(',').filter(Boolean).length,
  amount: r.amount,
  currency: 'INR',
  name: r.name,
  email: r.email,
  phone: r.phone,
  payment: r.payment_ref ? { method: r.payment_method, reference: r.payment_ref } : null,
  hold_expires_at: r.status === 'PENDING_PAYMENT' ? r.hold_expires_at : null,
  created_at: new Date(r.created_at).toISOString(),
  show: {
    id: r.show_id,
    movie_id: r.movie_id,
    movie_title: r.movie_title,
    theatre: r.theatre,
    screen: r.screen,
    date: r.show_date,
    time: r.show_time,
    price: r.price,
  },
});

// What goes out on the public live feed: no phone, masked email.
const publicDto = (r) => {
  const { phone, email, name, ...rest } = bookingDto(r);
  return { ...rest, email_masked: maskEmail(email) };
};

const announce = (type, code) => broadcast(type, { booking: publicDto(getBooking(code)) });

function expireHolds() {
  const stale = db
    .prepare(`SELECT id, code FROM bookings WHERE status = 'PENDING_PAYMENT' AND hold_expires_at < ?`)
    .all(Date.now());
  for (const b of stale) {
    tx(() => {
      db.prepare(`UPDATE bookings SET status = 'EXPIRED', updated_at = ? WHERE id = ?`).run(Date.now(), b.id);
      db.prepare(`DELETE FROM booking_seats WHERE booking_id = ?`).run(b.id);
    });
    announce('booking.expired', b.code);
  }
}
setInterval(expireHolds, 10_000).unref();
setInterval(ensureShows, 60 * 60 * 1000).unref(); // keep the 4-day window of showtimes rolling

async function refreshMovies() {
  try {
    const r = await syncMovies();
    if (r.synced) console.log(`🎬 TMDB: ${r.synced} movies synced`);
    else if (r.skipped) console.log(`🎬 TMDB off: ${r.reason}. Using the built-in demo movies.`);
  } catch (err) {
    console.warn(`⚠️  TMDB sync failed (${err.message}). Keeping the current movies.`);
  }
  ensureShows();
}
setInterval(refreshMovies, 12 * 60 * 60 * 1000).unref();

// ---------- routes -----------------------------------------------------------

app.get('/', (req, res) => {
  res.json({
    name: 'TicketTown API',
    docs: 'See README.md. Try GET /api/movies',
    endpoints: [
      'GET  /api/health',
      'GET  /api/movies',
      'GET  /api/movies/search?q=  (all of TMDB, not just the current line-up)',
      'POST /api/movies/activate  ({tmdb_id}: bring a movie onto the site + generate showtimes)',
      'GET  /api/movies/:id',
      'GET  /api/shows?movie_id=&date=',
      'GET  /api/shows/:id',
      'GET  /api/shows/:id/suggest?count=2',
      'POST /api/bookings',
      'GET  /api/bookings?email=',
      'GET  /api/bookings/:code',
      'POST /api/bookings/:code/pay',
      'POST /api/bookings/:code/cancel',
      'GET  /api/activity',
      'GET  /api/events  (Server-Sent Events)',
      'GET  /api/events/poll?since=  (same events, for clients that cannot stream)',
    ],
  });
});

app.get('/api/health', (req, res) => {
  res.json({ ok: true, time: new Date().toISOString(), live_clients: clientCount() });
});

app.get('/api/events', sseHandler);

// Polling twin of /api/events, for networks that buffer streams.
// First call without `since` just returns the current position; then poll with since=<last>.
app.get('/api/events/poll', (req, res) => {
  const since = Number(req.query.since);
  const last = lastSeq();
  if (!Number.isFinite(since)) return res.json({ events: [], last });
  res.json({ events: since > last ? [] : eventsSince(since), last, reset: since > last }); // reset: server restarted
});

const parseJson = (text, fallback) => {
  try {
    return text ? JSON.parse(text) : fallback;
  } catch {
    return fallback;
  }
};

const movieDto = (m, { full = false } = {}) => ({
  id: m.id,
  tmdb_id: m.tmdb_id,
  title: m.title,
  genre: m.genre,
  genres: parseJson(m.genres_json, [m.genre]),
  language: m.language,
  duration_min: m.duration_min,
  rating: m.rating,
  description: m.description,
  tagline: m.tagline,
  emoji: m.emoji,
  color1: m.color1,
  color2: m.color2,
  poster_url: m.poster_url,
  backdrop_url: m.backdrop_url,
  release_date: m.release_date,
  score: m.vote_average,
  votes: m.vote_count,
  from_price: m.from_price ?? null,
  upcoming_shows: m.upcoming_shows ?? 0,
  ...(full ? { cast: parseJson(m.cast_json, []), trailer_key: m.trailer_key } : {}),
});

const MOVIE_SQL = `
  SELECT m.*, MIN(s.price) AS from_price, COUNT(s.id) AS upcoming_shows
  FROM movies m LEFT JOIN shows s ON s.movie_id = m.id AND (s.show_date > ? OR (s.show_date = ? AND s.show_time > ?))`;

app.get('/api/movies', (req, res) => {
  const now = localNow();
  const rows = db
    .prepare(`${MOVIE_SQL} WHERE m.active = 1 GROUP BY m.id ORDER BY (m.tmdb_id IS NULL) DESC, m.vote_count DESC, m.id`)
    .all(now.date, now.date, now.time);
  res.json({ movies: rows.map((m) => movieDto(m)), source: rows.some((m) => m.tmdb_id) ? 'tmdb' : 'demo' });
});

// Search ALL of TMDB (not just what's currently active) - for a movie the customer wants that
// isn't in the current line-up. Read-only; doesn't touch the database.
// Registered before /api/movies/:id, otherwise Express would match ":id" = "search" first.
app.get('/api/movies/search', async (req, res) => {
  const q = String(req.query.q ?? '').trim();
  if (!q) fail(400, 'BAD_QUERY', 'q is required.');
  if (!tmdbEnabled()) return res.json({ results: [], tmdb_enabled: false });
  try {
    res.json({ results: await searchMovie(q), tmdb_enabled: true });
  } catch (err) {
    fail(502, 'TMDB_FAILED', err.message);
  }
});

// Bring one TMDB movie onto the site: mark it active, generate showtimes for it right now, and
// tell everyone watching (the website's home page updates live). Idempotent.
app.post('/api/movies/activate', async (req, res) => {
  const tmdbId = Number(req.body?.tmdb_id);
  if (!Number.isInteger(tmdbId)) fail(400, 'BAD_TMDB_ID', 'tmdb_id is required.');
  if (!tmdbEnabled()) fail(409, 'TMDB_DISABLED', 'TMDB is not configured on this server.');

  let result;
  try {
    result = await activateMovie(tmdbId);
  } catch (err) {
    if (/TMDB 404/.test(err.message)) fail(404, 'MOVIE_NOT_FOUND', `No TMDB movie with id ${tmdbId}.`);
    fail(502, 'TMDB_FAILED', err.message);
  }
  const showsCreated = ensureShowsForMovie(result.movieId);
  const now = localNow();
  const row = db.prepare(`${MOVIE_SQL} WHERE m.id = ? GROUP BY m.id`).get(now.date, now.date, now.time, result.movieId);
  const movie = movieDto(row, { full: true });
  broadcast('movie.activated', { movie });
  res.status(result.alreadyKnown ? 200 : 201).json({ movie, shows_created: showsCreated, was_already_listed: result.alreadyKnown });
});

app.get('/api/movies/:id', (req, res) => {
  const now = localNow();
  const row = db.prepare(`${MOVIE_SQL} WHERE m.id = ? GROUP BY m.id`).get(now.date, now.date, now.time, Number(req.params.id));
  if (!row || row.id === null) fail(404, 'MOVIE_NOT_FOUND', `Movie ${req.params.id} does not exist.`);
  res.json({ movie: movieDto(row, { full: true }) });
});

app.get('/api/shows', (req, res) => {
  expireHolds();
  const now = localNow();
  const where = ['m.active = 1', '(s.show_date > ? OR (s.show_date = ? AND s.show_time > ?))'];
  const args = [now.date, now.date, now.time];
  if (req.query.movie_id) {
    where.push('s.movie_id = ?');
    args.push(Number(req.query.movie_id));
  }
  if (req.query.date) {
    // Accept "today" / "tomorrow" so an AI agent doesn't need to know the calendar date.
    const q = String(req.query.date).toLowerCase();
    const date = q === 'today' ? now.date : q === 'tomorrow' ? localNow(1).date : q;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) fail(400, 'BAD_DATE', 'date must be today, tomorrow or YYYY-MM-DD.');
    where.push('s.show_date = ?');
    args.push(date);
  }
  const rows = db
    .prepare(`${SHOW_SQL} WHERE ${where.join(' AND ')} ORDER BY s.show_date, s.show_time, s.theatre`)
    .all(...args);
  res.json({ shows: rows.map(showDto) });
});

app.get('/api/shows/:id', (req, res) => {
  expireHolds();
  const show = showDto(getShow(Number(req.params.id)));
  res.json({ show, seats: seatState(show.id) });
});

// "Give me N seats together" - handy for humans and even handier for agents.
app.get('/api/shows/:id/suggest', (req, res) => {
  expireHolds();
  const show = showDto(getShow(Number(req.params.id)));
  const count = Number(req.query.count);
  if (!Number.isInteger(count) || count < 1 || count > MAX_SEATS) {
    fail(400, 'BAD_COUNT', `count must be a whole number between 1 and ${MAX_SEATS}.`);
  }
  const { booked, held } = seatState(show.id);
  const unavailable = new Set([...booked, ...held]);
  const free = (r, c) => !unavailable.has(String.fromCharCode(65 + r) + c);

  const targetRow = Math.round((show.rows - 1) * 0.6); // a bit back from the screen
  const centre = (show.cols + 1) / 2;
  let best = null;
  for (let r = 0; r < show.rows; r++) {
    for (let start = 1; start + count - 1 <= show.cols; start++) {
      const end = start + count - 1;
      const crossesAisle = count <= show.aisle_after && start <= show.aisle_after && end > show.aisle_after;
      if (crossesAisle) continue;
      let ok = true;
      for (let c = start; c <= end; c++) if (!free(r, c)) { ok = false; break; }
      if (!ok) continue;
      const score = Math.abs(r - targetRow) * 2 + Math.abs((start + end) / 2 - centre);
      if (!best || score < best.score) best = { score, r, start, end };
    }
  }
  if (best) {
    const seats = Array.from({ length: count }, (_, i) => String.fromCharCode(65 + best.r) + (best.start + i));
    return res.json({ show_id: show.id, together: true, seats, total: seatTotal(show.price, seats), currency: 'INR' });
  }

  // No block big enough: fall back to the best individual seats.
  const singles = seatLabels(show.rows, show.cols)
    .filter((s) => !unavailable.has(s))
    .map((s) => ({ s, score: Math.abs(s.charCodeAt(0) - 65 - targetRow) * 2 + Math.abs(Number(s.slice(1)) - centre) }))
    .sort((a, b) => a.score - b.score)
    .slice(0, count)
    .map((x) => x.s)
    .sort(seatSort);
  if (singles.length < count) {
    fail(409, 'NOT_ENOUGH_SEATS', `Only ${singles.length} seat(s) left for this show.`, { seats_available: singles.length });
  }
  res.json({ show_id: show.id, together: false, seats: singles, total: seatTotal(show.price, singles), currency: 'INR' });
});

app.post('/api/bookings', (req, res) => {
  expireHolds();
  const body = req.body ?? {};
  const showId = Number(body.show_id);
  if (!Number.isInteger(showId)) fail(400, 'BAD_SHOW', 'show_id is required.');

  const seats = [...new Set((Array.isArray(body.seats) ? body.seats : []).map((s) => String(s).trim().toUpperCase()))];
  if (seats.length < 1 || seats.length > MAX_SEATS) {
    fail(400, 'BAD_SEATS', `Choose between 1 and ${MAX_SEATS} seats.`);
  }

  const email = String(body.email ?? '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) fail(400, 'BAD_EMAIL', 'A valid email address is required.');
  const phone = String(body.phone ?? '').replace(/[\s\-()]/g, '');
  if (!/^\+?\d{10,13}$/.test(phone)) fail(400, 'BAD_PHONE', 'A valid phone number (10-13 digits) is required.');
  const name = body.name ? String(body.name).trim().slice(0, 60) : null;
  const source = body.source === 'agent' ? 'agent' : 'web';

  const showRow = getShow(showId);
  const show = showDto(showRow);
  if (show.started) fail(409, 'SHOW_STARTED', 'This show has already started.');
  const valid = new Set(seatLabels(show.rows, show.cols));
  const invalid = seats.filter((s) => !valid.has(s));
  if (invalid.length) fail(400, 'BAD_SEATS', `Unknown seat(s): ${invalid.join(', ')}. Rows are A-${String.fromCharCode(64 + show.rows)}, seats 1-${show.cols}.`);

  const now = Date.now();
  const code = randomCode('TT-', 6);
  tx(() => {
    const taken = db
      .prepare(`SELECT seat FROM booking_seats WHERE show_id = ? AND seat IN (${seats.map(() => '?').join(',')})`)
      .all(showId, ...seats)
      .map((r) => r.seat);
    if (taken.length) {
      fail(409, 'SEATS_TAKEN', `Seat(s) already taken: ${taken.sort(seatSort).join(', ')}. Pick different seats.`, { taken });
    }
    const b = db
      .prepare(
        `INSERT INTO bookings (code,show_id,name,email,phone,seats,amount,status,source,hold_expires_at,created_at,updated_at)
         VALUES (?,?,?,?,?,?,?,'PENDING_PAYMENT',?,?,?,?)`,
      )
      .run(code, showId, name, email, phone, [...seats].sort(seatSort).join(','), seatTotal(show.price, seats), source, now + HOLD_MINUTES * 60_000, now, now);
    const ins = db.prepare(`INSERT INTO booking_seats (booking_id,show_id,seat) VALUES (?,?,?)`);
    for (const s of seats) ins.run(Number(b.lastInsertRowid), showId, s);
  });

  announce('booking.created', code);
  res.status(201).json({ booking: bookingDto(getBooking(code)), hold_minutes: HOLD_MINUTES });
});

app.get('/api/bookings', (req, res) => {
  expireHolds();
  const email = String(req.query.email ?? '').trim().toLowerCase();
  if (!email) fail(400, 'BAD_EMAIL', 'email query parameter is required.');
  const rows = db.prepare(`${BOOKING_SQL} WHERE b.email = ? ORDER BY b.created_at DESC LIMIT 50`).all(email);
  res.json({ bookings: rows.map(bookingDto) });
});

app.get('/api/bookings/:code', (req, res) => {
  expireHolds();
  res.json({ booking: bookingDto(getBooking(req.params.code)) });
});

// Mock payment. Nothing real is charged - a card ending in 0002 is declined
// so you can show the failure path in the workshop.
app.post('/api/bookings/:code/pay', (req, res) => {
  expireHolds();
  const existing = getBooking(req.params.code);
  if (existing.status === 'CONFIRMED') return res.json({ booking: bookingDto(existing), already_paid: true });
  if (existing.status === 'EXPIRED') fail(410, 'HOLD_EXPIRED', 'The seat hold expired. Please start a new booking.');
  if (existing.status === 'CANCELLED') fail(409, 'BOOKING_CANCELLED', 'This booking was cancelled.');

  const body = req.body ?? {};
  const method = ['card', 'upi', 'wallet'].includes(body.method) ? body.method : 'wallet';
  if (method === 'card') {
    const digits = String(body.card_number ?? '').replace(/\D/g, '');
    if (!/^\d{12,19}$/.test(digits)) fail(400, 'BAD_CARD', 'Enter a valid card number.');
    if (digits.endsWith('0002')) fail(402, 'PAYMENT_DECLINED', 'Card declined by the (mock) bank. Try another card or UPI.');
  }
  if (method === 'upi' && !/^[\w.\-]{2,}@[\w]{2,}$/.test(String(body.upi_id ?? ''))) {
    fail(400, 'BAD_UPI', 'Enter a valid UPI ID, like name@bank.');
  }

  db.prepare(
    `UPDATE bookings SET status='CONFIRMED', payment_method=?, payment_ref=?, hold_expires_at=NULL, updated_at=? WHERE id=?`,
  ).run(method, randomCode('PAY-', 8), Date.now(), existing.id);

  announce('booking.confirmed', existing.code);
  res.json({ booking: bookingDto(getBooking(existing.code)) });
});

app.post('/api/bookings/:code/cancel', (req, res) => {
  const existing = getBooking(req.params.code);
  if (!['PENDING_PAYMENT', 'CONFIRMED'].includes(existing.status)) {
    fail(409, 'NOT_CANCELLABLE', `A ${existing.status.toLowerCase()} booking cannot be cancelled.`);
  }
  const refund = existing.status === 'CONFIRMED' ? existing.amount : 0;
  tx(() => {
    db.prepare(`UPDATE bookings SET status='CANCELLED', updated_at=? WHERE id=?`).run(Date.now(), existing.id);
    db.prepare(`DELETE FROM booking_seats WHERE booking_id = ?`).run(existing.id);
  });
  announce('booking.cancelled', existing.code);
  res.json({ booking: bookingDto(getBooking(existing.code)), refund_amount: refund, currency: 'INR' });
});

// Recent activity for the "Live" panel (seed data and contact details excluded).
app.get('/api/activity', (req, res) => {
  const rows = db
    .prepare(`${BOOKING_SQL} WHERE b.source != 'seed' ORDER BY b.updated_at DESC LIMIT 20`)
    .all();
  res.json({ activity: rows.map(publicDto) });
});

// Re-pull the movie line-up from TMDB right now.
app.post('/api/admin/sync-movies', async (req, res) => {
  if (req.get('x-admin-key') !== ADMIN_KEY) fail(401, 'UNAUTHORIZED', 'Missing or wrong x-admin-key header.');
  try {
    const result = await syncMovies();
    ensureShows();
    res.json({ ok: true, ...result });
  } catch (err) {
    fail(502, 'TMDB_FAILED', err.message);
  }
});

// Wipe demo bookings between workshop runs (seeded walk-in seats are kept).
app.post('/api/admin/reset', (req, res) => {
  if (req.get('x-admin-key') !== ADMIN_KEY) fail(401, 'UNAUTHORIZED', 'Missing or wrong x-admin-key header.');
  const { changes } = db.prepare(`DELETE FROM bookings WHERE source != 'seed'`).run();
  broadcast('reset', { removed: Number(changes) });
  res.json({ ok: true, removed: Number(changes) });
});

// ---------- errors -----------------------------------------------------------

app.use((req, res) => res.status(404).json({ error: `No route for ${req.method} ${req.path}`, code: 'NOT_FOUND' }));

app.use((err, req, res, next) => {
  if (err instanceof ApiError) return res.status(err.status).json({ error: err.message, code: err.code, ...err.extra });
  if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'Request body is not valid JSON.', code: 'BAD_JSON' });
  console.error(err);
  res.status(500).json({ error: 'Something went wrong on the server.', code: 'INTERNAL' });
});

ensureCatalog();
await refreshMovies(); // before listening, so the very first page load already has posters

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n🎟️  TicketTown API running on http://localhost:${PORT}`);
  console.log(`    Movies: ${tmdbEnabled() ? 'TMDB' : 'demo data'} · Hold time: ${HOLD_MINUTES} min · CORS: all origins · DB: ${process.env.DB_PATH || './data/tickettown.db'}\n`);
});
