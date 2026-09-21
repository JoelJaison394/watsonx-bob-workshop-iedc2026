// SQLite setup. Uses Node's built-in `node:sqlite` (Node 22.13+), so there is
// nothing native to compile and nothing extra to install.
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

const dbPath = process.env.DB_PATH || path.join(process.cwd(), 'data', 'tickettown.db');
fs.mkdirSync(path.dirname(dbPath), { recursive: true });

export const db = new DatabaseSync(dbPath);

db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  CREATE TABLE IF NOT EXISTS movies (
    id           INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    genre        TEXT NOT NULL,
    language     TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    rating       TEXT NOT NULL,
    description  TEXT NOT NULL,
    emoji        TEXT NOT NULL,
    color1       TEXT NOT NULL,
    color2       TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS shows (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id  INTEGER NOT NULL REFERENCES movies(id),
    theatre   TEXT NOT NULL,
    screen    TEXT NOT NULL,
    show_date TEXT NOT NULL,           -- YYYY-MM-DD (theatre local time)
    show_time TEXT NOT NULL,           -- HH:MM      (theatre local time)
    price     INTEGER NOT NULL,        -- INR per seat
    seat_rows INTEGER NOT NULL DEFAULT 8,
    seat_cols INTEGER NOT NULL DEFAULT 10,
    UNIQUE (movie_id, theatre, show_date, show_time)
  );

  CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    show_id         INTEGER NOT NULL REFERENCES shows(id),
    name            TEXT,
    email           TEXT NOT NULL,
    phone           TEXT NOT NULL,
    seats           TEXT NOT NULL,                  -- comma separated, kept for history after cancel
    amount          INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING_PAYMENT','CONFIRMED','CANCELLED','EXPIRED')),
    source          TEXT NOT NULL DEFAULT 'web',   -- web | agent | seed
    payment_method  TEXT,
    payment_ref     TEXT,
    hold_expires_at INTEGER,                        -- epoch ms, only while PENDING_PAYMENT
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
  );

  -- One row per seat that is currently held or sold. The composite primary key
  -- is what makes double-booking impossible, even under concurrent requests.
  CREATE TABLE IF NOT EXISTS booking_seats (
    booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    show_id    INTEGER NOT NULL REFERENCES shows(id),
    seat       TEXT NOT NULL,
    PRIMARY KEY (show_id, seat)
  );

  CREATE INDEX IF NOT EXISTS idx_bookings_email  ON bookings(email);
  CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status, hold_expires_at);
  CREATE INDEX IF NOT EXISTS idx_shows_date      ON shows(show_date, movie_id);
`);

// Columns added after the first version. Adding them here (instead of editing
// CREATE TABLE) means an older tickettown.db upgrades itself on boot.
const movieCols = new Set(db.prepare('PRAGMA table_info(movies)').all().map((c) => c.name));
for (const [name, ddl] of [
  ['tmdb_id', 'tmdb_id INTEGER'],
  ['active', 'active INTEGER NOT NULL DEFAULT 1'],      // 1 = listed on the site
  ['tagline', 'tagline TEXT'],
  ['genres_json', 'genres_json TEXT'],
  ['poster_url', 'poster_url TEXT'],
  ['backdrop_url', 'backdrop_url TEXT'],
  ['release_date', 'release_date TEXT'],
  ['vote_average', 'vote_average REAL'],
  ['vote_count', 'vote_count INTEGER'],
  ['cast_json', 'cast_json TEXT'],
  ['trailer_key', 'trailer_key TEXT'],
]) {
  if (!movieCols.has(name)) db.exec(`ALTER TABLE movies ADD COLUMN ${ddl}`);
}
db.exec('CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_tmdb ON movies(tmdb_id) WHERE tmdb_id IS NOT NULL');

/** Run `fn` inside a transaction. Rolls back if it throws. */
export function tx(fn) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const result = fn();
    db.exec('COMMIT');
    return result;
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }
}
