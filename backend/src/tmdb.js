// TMDB integration: pulls "now playing" movies (posters, cast, trailers, scores)
// into SQLite. The key stays on the server and is never sent to the browser.
//
//   TMDB_API_KEY     v3 API key, OR a v4 "Read Access Token" (starts with "eyJ")
//   USE_TMDB=false   force the built-in fictional movies
//   TMDB_REGION      default IN
//   TMDB_LIMIT       how many movies to list, default 12
import { db, tx } from './db.js';
import { WORKSHOP_MOVIE_ID } from './catalog.js';

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
  const genres = (d.genres ?? []).map((g) => g.name);
  return {
    tmdb_id: d.id,
    title: d.title,
    genre: genres[0] ?? 'Drama',
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

export async function fetchNowPlaying() {
  const limit = Number(process.env.TMDB_LIMIT) || 12;
  const region = process.env.TMDB_REGION || 'IN';
  const list = await tmdb('/movie/now_playing', { region, language: 'en-US', page: 1 });
  const candidates = (list.results ?? []).filter((m) => m.poster_path).slice(0, limit);
  const details = await mapLimit(candidates, 4, (m) =>
    tmdb(`/movie/${m.id}`, { append_to_response: 'credits,videos,release_dates', language: 'en-US' }).catch(() => null),
  );
  return details.filter(Boolean).map(mapMovie);
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
    db.prepare(
      `UPDATE movies SET active = 0
       WHERE id != ? AND (tmdb_id IS NULL OR tmdb_id NOT IN (${keep.map(() => '?').join(',')}))`,
    ).run(WORKSHOP_MOVIE_ID, ...keep);
    db.prepare('UPDATE movies SET active = 1 WHERE id = ?').run(WORKSHOP_MOVIE_ID);
  });
  return { synced: movies.length, titles: movies.map((m) => m.title) };
}
