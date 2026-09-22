// Demo data: fallback movies and a rolling window of showtimes.
// Everything here is safe to run repeatedly. It only inserts what is missing.
import { db, tx } from './db.js';
import { MOVIES, THEATRES, seatTotal } from './catalog.js';

const TZ = process.env.TZ_NAME || 'Asia/Kolkata';
const SLOTS = ['10:30', '13:45', '16:30', '19:15', '22:00'];
const DAYS_AHEAD = 3; // today + 3 more days

/** Current date/time in the theatre's timezone. */
export function localNow(offsetDays = 0) {
  const d = new Date(Date.now() + offsetDays * 86400000);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(d).map((p) => [p.type, p.value]),
  );
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function seatLabels(rows, cols) {
  const out = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 1; c <= cols; c++) out.push(String.fromCharCode(65 + r) + c);
  }
  return out;
}

/** Insert the built-in fictional movies if they are missing. */
export function ensureCatalog() {
  const ins = db.prepare(
    `INSERT OR IGNORE INTO movies (id,title,genre,genres_json,language,duration_min,rating,description,emoji,color1,color2)
     VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
  );
  tx(() => {
    for (const m of MOVIES) {
      ins.run(m.id, m.title, m.genre, JSON.stringify([m.genre]), m.language, m.duration_min, m.rating, m.description, m.emoji, m.color1, m.color2);
    }
  });
}

/** Fisher-Yates, driven by a seeded RNG so the same movie gets the same-shaped schedule each call. */
function shuffled(arr, rand) {
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/**
 * Generate a believable set of upcoming shows for ONE movie right now, instead of waiting for
 * the next hourly ensureShows() sweep. Used when a movie is brought onto the site on demand
 * (see tmdb.js activateMovie()) so it's immediately bookable. Safe to call more than once -
 * INSERT OR IGNORE means it only ever adds what's missing.
 */
export function ensureShowsForMovie(movieId) {
  const insShow = db.prepare(
    `INSERT OR IGNORE INTO shows (movie_id,theatre,screen,show_date,show_time,price) VALUES (?,?,?,?,?,?)`,
  );
  const rand = mulberry32(movieId * 104729); // stable per movie: re-activating doesn't reshuffle
  const now = localNow();
  let created = 0;

  tx(() => {
    for (let d = 0; d <= DAYS_AHEAD; d++) {
      const { date } = localNow(d);
      const slotIdxs = shuffled([...SLOTS.keys()], rand).slice(0, 3);
      slotIdxs.forEach((slotIdx) => {
        const time = SLOTS[slotIdx];
        if (date === now.date && time <= now.time) return; // already started today
        const theatre = THEATRES[Math.floor(rand() * THEATRES.length)];
        const screen = `Screen ${1 + Math.floor(rand() * 4)}`;
        const price = 150 + Math.floor(rand() * 4) * 50 + (slotIdx >= 3 ? 50 : 0);
        const res = insShow.run(movieId, theatre, screen, date, time, price);
        if (res.changes === 1) created++;
      });
    }
  });
  return created;
}

/** Make sure every listed movie has shows for today + the next few days. */
export function ensureShows() {
  const insShow = db.prepare(
    `INSERT OR IGNORE INTO shows (movie_id,theatre,screen,show_date,show_time,price) VALUES (?,?,?,?,?,?)`,
  );
  const insBooking = db.prepare(
    `INSERT INTO bookings (code,show_id,name,email,phone,seats,amount,status,source,created_at,updated_at)
     VALUES (?,?,?,?,?,?,?,'CONFIRMED','seed',?,?)`,
  );
  const insSeat = db.prepare(`INSERT OR IGNORE INTO booking_seats (booking_id,show_id,seat) VALUES (?,?,?)`);

  const movies = db.prepare(`SELECT id FROM movies WHERE active = 1 ORDER BY id`).all();
  const now = localNow();

  tx(() => {
    for (let d = 0; d <= DAYS_AHEAD; d++) {
      const { date } = localNow(d);
      movies.forEach((m, i) => {
        [0, 2, 3].forEach((offset, k) => {
          const slotIdx = (i + offset) % SLOTS.length;
          const time = SLOTS[slotIdx];
          if (date === now.date && time <= now.time) return; // already started today
          const theatre = THEATRES[(i + d + k) % THEATRES.length];
          const screen = `Screen ${((i + k) % 4) + 1}`;
          const price = 150 + (i % 4) * 50 + (slotIdx >= 3 ? 50 : 0); // Silver price; Gold/Platinum add on top
          const res = insShow.run(m.id, theatre, screen, date, time, price);
          if (res.changes === 1) {
            // Make the theatre look lived-in: pre-sell 15-45% of the seats.
            const showId = Number(res.lastInsertRowid);
            const rand = mulberry32(showId * 7919);
            const fraction = 0.15 + rand() * 0.3;
            const taken = seatLabels(8, 10).filter(() => rand() < fraction);
            if (taken.length) {
              const ts = Date.now();
              const b = insBooking.run(`SEED-${showId}`, showId, 'Walk-in', 'walkin@tickettown.local', '0000000000', taken.join(','), seatTotal(price, taken), ts, ts);
              for (const s of taken) insSeat.run(Number(b.lastInsertRowid), showId, s);
            }
          }
        });
      });
    }
  });
}
