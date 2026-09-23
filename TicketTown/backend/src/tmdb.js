// TMDB integration: pulls "now playing" movies (posters, cast, trailers, scores)
// into SQLite. The key stays on the server and is never sent to the browser.
//
//   TMDB_API_KEY     v3 API key, OR a v4 "Read Access Token" (starts with "eyJ")
//   USE_TMDB=false   force the built-in fictional movies
//   TMDB_REGION      default IN
//   TMDB_LIMIT       how many movies to list, default 16
import { db, tx } from './db.js';
import { WORKSHOP_MOVIE_ID } from './catalog.js';
import { localNow } from './seed.js';

const BASE = () => (process.env.TMDB_BASE_URL || 'https://api.themoviedb.org/3').replace(/\/+$/, '');
const IMG = () => (process.env.TMDB_IMAGE_BASE || 'https://image.tmdb.org/t/p').replace(/\/+$/, '');
const KEY = () => (process.env.TMDB_API_KEY || process.env.TMDB_READ_TOKEN || '').trim();

export const tmdbEnabled = () => Boolean(KEY()) && process.env.USE_TMDB !== 'false';

async function tmdb(path, params = {}) {
  const url = new URL(BASE() + path);
  const headers = { accept: 'application/json' };
  // A v4 token is a JWT (has dots); a v3 key is 32 hex characters.
  if (KEY().includes('.')) headers.Authorization = `Bearer ${KEY()}`;
  else url.searchParams.set('api_key', KEY());
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);

  // Retry a few times: connections to TMDB can drop (ECONNRESET) or hit a temporary 5xx/429.
  for (let attempt = 1; ; attempt++) {
    try {
      const res = await fetch(url, { headers, signal: AbortSignal.timeout(15000) });
      if (res.ok) return await res.json();
      if (res.status === 429 || res.status >= 500) throw Object.assign(new Error(`TMDB ${res.status}`), { retry: true });
      const hint = res.status === 401 ? ' (check TMDB_API_KEY)' : '';
      throw new Error(`TMDB ${res.status} for ${path}${hint}`); // 401/404 etc: retrying won't help
    } catch (err) {
      const retryable = err.retry || !/^TMDB \d+ for/.test(err.message);
      if (!retryable || attempt >= 4) {
        // Node's "fetch failed" hides the real reason (DNS, reset, TLS...) in err.cause.
        const why = err.cause?.code || err.cause?.message || err.message;
        throw new Error(/^TMDB \d+ for/.test(err.message) ? err.message : `could not reach TMDB for ${path} (${why})`);
      }
      await new Promise((r) => setTimeout(r, 700 * attempt));
    }
  }
}

const languageName = (code) => {
  try {
    return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) || code;
  } catch {
    return code;
  }
};

// Indian certificates are U / UA / A. Fall back on the US rating, else UA.
function certificate(releaseDates) {
  const pick = (country) =>
    releaseDates?.results?.find((r) => r.iso_3166_1 === country)?.release_dates?.find((x) => x.certification)?.certification;
  const inCert = pick('IN')?.toUpperCase();
  if (inCert) return inCert.startsWith('A') ? 'A' : inCert.startsWith('U/A') || inCert.startsWith('UA') ? 'UA' : 'U';
  const us = pick('US');
  if (us === 'G') return 'U';
  if (us === 'R' || us === 'NC-17') return 'A';
  return 'UA';
}

function mapMovie(d) {
  const trailers = (d.videos?.results ?? []).filter((v) => v.site === 'YouTube' && v.type === 'Trailer');
  const trailer = trailers.find((v) => v.official) ?? trailers[0];
  // A handful of TMDB entries (mostly smaller regional releases) carry no genre tags at all.
  // Fall back to a single genre rather than leaving the movie with an empty genres list -
  // both the UI and the MCP tools promise every movie has at least one.
  const rawGenres = (d.genres ?? []).map((g) => g.name);
  const genre = rawGenres[0] ?? 'Drama';
  const genres = rawGenres.length ? rawGenres : [genre];
  return {
    tmdb_id: d.id,
    title: d.title,
    genre,
    genres,
    language: languageName(d.original_language),
    duration_min: d.runtime || 120,
    rating: certificate(d.release_dates),
    description: d.overview || 'No synopsis available yet.',
    tagline: d.tagline || null,
    poster_url: d.poster_path ? `${IMG()}/w500${d.poster_path}` : null,
    backdrop_url: d.backdrop_path ? `${IMG()}/w1280${d.backdrop_path}` : null,
    release_date: d.release_date || null,
    vote_average: d.vote_average ? Math.round(d.vote_average * 10) / 10 : null,
    vote_count: d.vote_count ?? 0,
    trailer_key: trailer?.key ?? null,
    cast: (d.credits?.cast ?? [])
      .slice(0, 12)
      .map((c) => ({ name: c.name, character: c.character || null, photo_url: c.profile_path ? `${IMG()}/w185${c.profile_path}` : null })),
  };
}

// Small pool so we don't hit TMDB with a dozen requests at once.
async function mapLimit(items, limit, fn) {
  const out = [];
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]);
      }
    }),
  );
  return out;
}

const uniqById = (list) => {
  const seen = new Set();
  return list.filter((m) => {
    if (!m.poster_path || seen.has(m.id)) return false;
    seen.add(m.id);
    return true;
  });
};

const discover = (region, params) =>
  tmdb('/discover/movie', { region, sort_by: 'popularity.desc', include_adult: 'false', ...params })
    .then((r) => r.results ?? [])
    .catch(() => []); // one failing source shouldn't sink the whole line-up

// English + the major Indian languages. Keeps the "trending" pool to what an Indian audience
// would actually recognise - TMDB's India-region discover results otherwise pull in unrelated
// festival/streaming titles (French, Spanish, ...) that just happen to have an IN release date logged.
const RELEVANT_LANGS = new Set(['hi', 'ta', 'te', 'kn', 'ml', 'en', 'bn', 'mr', 'pa', 'gu', 'or']);
const RELEVANT_LANGS_PARAM = [...RELEVANT_LANGS].join('|'); // TMDB accepts pipe-separated OR

/**
 * Build the "now showing" line-up for an Indian audience.
 *
 * TMDB's own "now playing" endpoint is Hollywood-heavy even with region=IN, so on its own it
 * under-represents regional cinema. We reserve some slots for popular Malayalam releases from
 * this month (the workshop's own audience is mostly Malayalam-speaking), then fill the rest of
 * the line-up with a broader "trending in India this month" pool (any language, including
 * English and Hindi) plus TMDB's now-playing list - so the page never becomes Malayalam-only,
 * and never drops to zero if a given month happens to have no new Malayalam release.
 */
export async function fetchNowPlaying() {
  const limit = Number(process.env.TMDB_LIMIT) || 16;
  const region = process.env.TMDB_REGION || 'IN';
  const { date: today } = localNow();
  const monthStart = today.slice(0, 8) + '01';
  const thisMonth = { 'primary_release_date.gte': monthStart, 'primary_release_date.lte': today };

  const [nowPlaying, malayalam, trending] = await Promise.all([
    // now_playing has no language filter param, so filter its results after the fact.
    tmdb('/movie/now_playing', { region, language: 'en-US', page: 1 })
      .then((r) => (r.results ?? []).filter((m) => RELEVANT_LANGS.has(m.original_language)))
      .catch(() => []),
    discover(region, { with_original_language: 'ml', ...thisMonth }),
    discover(region, { with_original_language: RELEVANT_LANGS_PARAM, ...thisMonth }),
  ]);

  const malayalamReserve = Math.max(4, Math.ceil(limit / 3));
  const malayalamPicks = uniqById(malayalam).slice(0, malayalamReserve);
  const reserved = new Set(malayalamPicks.map((m) => m.id));
  const restPicks = uniqById([...trending, ...nowPlaying].sort((a, b) => (b.popularity ?? 0) - (a.popularity ?? 0)))
    .filter((m) => !reserved.has(m.id));
  const chosen = [...malayalamPicks, ...restPicks].slice(0, limit);

  const details = await mapLimit(chosen, 4, (m) =>
    tmdb(`/movie/${m.id}`, { append_to_response: 'credits,videos,release_dates', language: 'en-US' }).catch(() => null),
  );
  return details.filter(Boolean).map(mapMovie);
}

/**
 * Free-text search across ALL of TMDB, not just what's currently active on the site. Used when
 * a customer asks for a movie that isn't in the current line-up (an older release, or one that
 * hasn't made this month's cut). Lightweight - no per-result detail fetch - just enough to pick
 * the right one before calling activateMovie().
 */
export async function searchMovie(query) {
  if (!tmdbEnabled()) throw new Error('TMDB is not configured on this server (no TMDB_API_KEY).');
  const list = await tmdb('/search/movie', { query, region: process.env.TMDB_REGION || 'IN', language: 'en-US', include_adult: 'false' });
  return (list.results ?? [])
    .slice(0, 8)
    .map((m) => ({
      tmdb_id: m.id,
      title: m.title,
      release_date: m.release_date || null,
      language: languageName(m.original_language),
      poster_url: m.poster_path ? `${IMG()}/w500${m.poster_path}` : null,
      overview: m.overview || null,
      popularity: m.popularity ?? 0,
    }))
    .sort((a, b) => b.popularity - a.popularity);
}

/**
 * Bring one specific TMDB movie onto the site (active=1), fetching full details if we don't
 * already have it. Idempotent: calling it again for the same tmdb_id just re-activates it.
 * Does NOT create showtimes - the caller (server.js) does that, since that logic lives in seed.js.
 */
export async function activateMovie(tmdbId) {
  if (!tmdbEnabled()) throw new Error('TMDB is not configured on this server (no TMDB_API_KEY).');
  const existing = db.prepare('SELECT id, active, title FROM movies WHERE tmdb_id = ?').get(tmdbId);
  if (existing) {
    if (!existing.active) db.prepare('UPDATE movies SET active = 1 WHERE id = ?').run(existing.id);
    return { movieId: existing.id, alreadyKnown: true, title: existing.title };
  }

  const detail = await tmdb(`/movie/${tmdbId}`, { append_to_response: 'credits,videos,release_dates', language: 'en-US' });
  const m = mapMovie(detail);
  const cols = ['tmdb_id', 'title', 'genre', 'genres_json', 'language', 'duration_min', 'rating', 'description', 'tagline',
    'poster_url', 'backdrop_url', 'release_date', 'vote_average', 'vote_count', 'trailer_key', 'cast_json'];
  const values = [m.tmdb_id, m.title, m.genre, JSON.stringify(m.genres), m.language, m.duration_min, m.rating, m.description,
    m.tagline, m.poster_url, m.backdrop_url, m.release_date, m.vote_average, m.vote_count, m.trailer_key, JSON.stringify(m.cast)];
  const res = db
    .prepare(`INSERT INTO movies (${cols.join(',')},emoji,color1,color2,active) VALUES (${cols.map(() => '?').join(',')},'🎬','#333545','#f84464',1)`)
    .run(...values);
  return { movieId: Number(res.lastInsertRowid), alreadyKnown: false, title: m.title };
}

/**
 * Pull the current line-up from TMDB into the database. On success the fictional
 * movies are hidden (except the workshop's "Agent 404"). On failure nothing changes,
 * so the site keeps working with whatever it already had.
 */
export async function syncMovies() {
  if (!tmdbEnabled()) return { skipped: true, reason: 'TMDB_API_KEY not set (or USE_TMDB=false)' };
  const movies = await fetchNowPlaying();
  if (!movies.length) throw new Error('TMDB returned no movies');

  const find = db.prepare('SELECT id FROM movies WHERE tmdb_id = ?');
  const cols = `title,genre,genres_json,language,duration_min,rating,description,tagline,poster_url,backdrop_url,release_date,vote_average,vote_count,trailer_key,cast_json`;
  const insert = db.prepare(
    `INSERT INTO movies (tmdb_id,${cols},emoji,color1,color2,active) VALUES (?,${cols.split(',').map(() => '?').join(',')},'🎬','#333545','#f84464',1)`,
  );
  const update = db.prepare(`UPDATE movies SET ${cols.split(',').map((c) => `${c}=?`).join(',')},active=1 WHERE id=?`);

  tx(() => {
    for (const m of movies) {
      const values = [m.title, m.genre, JSON.stringify(m.genres), m.language, m.duration_min, m.rating, m.description, m.tagline,
        m.poster_url, m.backdrop_url, m.release_date, m.vote_average, m.vote_count, m.trailer_key, JSON.stringify(m.cast)];
      const existing = find.get(m.tmdb_id);
      if (existing) update.run(...values, existing.id);
      else insert.run(m.tmdb_id, ...values);
    }
    const keep = movies.map((m) => m.tmdb_id);
    const now = localNow();
    // Never hide a movie that a REAL customer (web or agent) still has a live booking against
    // for a future show - that would break re-booking or make their own booking hard to find.
    // (Deliberately excludes source='seed' walk-in bookings: ensureShows() pre-sells some seats
    // on almost every show it generates, so "has any booking" would otherwise protect nearly
    // every movie forever and defeat the point of the monthly curation.)
    db.prepare(
      `UPDATE movies SET active = 0
       WHERE id != ? AND (tmdb_id IS NULL OR tmdb_id NOT IN (${keep.map(() => '?').join(',')}))
         AND id NOT IN (
           SELECT DISTINCT s.movie_id FROM bookings b JOIN shows s ON s.id = b.show_id
           WHERE b.source != 'seed' AND b.status IN ('PENDING_PAYMENT', 'CONFIRMED')
             AND (s.show_date > ? OR (s.show_date = ? AND s.show_time > ?))
         )`,
    ).run(WORKSHOP_MOVIE_ID, ...keep, now.date, now.date, now.time);
    db.prepare('UPDATE movies SET active = 1 WHERE id = ?').run(WORKSHOP_MOVIE_ID);
  });
  return { synced: movies.length, titles: movies.map((m) => m.title) };
}
