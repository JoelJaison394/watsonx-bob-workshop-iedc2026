// A tiny fake TMDB server, for testing and for offline demos (venue Wi-Fi!).
// It answers the same endpoints the backend uses and generates poster,
// backdrop and cast images on the fly.
//
//   npm run mock-tmdb        (listens on :4010)
//   TMDB_API_KEY=demo TMDB_BASE_URL=http://localhost:4010/3 TMDB_IMAGE_BASE=http://localhost:4010/img npm start
import http from 'node:http';
import { MOVIES } from '../src/catalog.js';

const PORT = Number(process.env.MOCK_TMDB_PORT) || 4010;
const LANG = { English: 'en', Hindi: 'hi', Kannada: 'kn' };
const NAMES = ['Aarav Mehta', 'Diya Nair', 'Kabir Rao', 'Meera Iyer', 'Rohan Das', 'Ishita Sen', 'Vikram Shah', 'Anaya Roy', 'Neel Kapoor', 'Tara Menon'];
const TEXT = { English: 'en', Hindi: 'hi', Kannada: 'kn' };

// Every fictional movie except the workshop's own "Agent 404" plays TMDB's part.
const movies = MOVIES.filter((m) => m.id !== 1).map((m, i) => ({
  ...m,
  tmdb_id: 900000 + m.id,
  score: [8.4, 7.9, 8.1, 7.4, 8.7, 7.7, 8.0][i % 7],
  votes: [12840, 8420, 15310, 3980, 21500, 5240, 9870][i % 7],
}));

const send = (res, status, body, type = 'application/json') => {
  res.writeHead(status, { 'content-type': type, 'access-control-allow-origin': '*', 'cache-control': 'max-age=60' });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
};

const wrap = (title, max = 14) => {
  const lines = [];
  let line = '';
  for (const w of title.split(' ')) {
    if ((line + ' ' + w).trim().length > max) { lines.push(line); line = w; } else line = (line + ' ' + w).trim();
  }
  return [...lines, line].filter(Boolean);
};
const esc = (t) => t.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

function posterSvg(m, w, h) {
  const lines = wrap(m.title);
  const text = lines.map((l, i) => `<text x="${w / 2}" y="${h * 0.78 + i * (w * 0.09)}" font-family="Arial,sans-serif" font-weight="700" font-size="${w * 0.08}" fill="#fff" text-anchor="middle">${esc(l)}</text>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${m.color1}"/><stop offset="1" stop-color="${m.color2}"/></linearGradient>
    <linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset=".5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".7"/></linearGradient></defs>
    <rect width="100%" height="100%" fill="url(#g)"/><text x="${w / 2}" y="${h * 0.5}" font-size="${w * 0.3}" text-anchor="middle">${m.emoji}</text><rect width="100%" height="100%" fill="url(#s)"/>${text}</svg>`;
}

function backdropSvg(m, w, h) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${m.color1}"/><stop offset="1" stop-color="${m.color2}"/></linearGradient></defs>
    <rect width="100%" height="100%" fill="url(#g)"/><text x="${w * 0.72}" y="${h * 0.62}" font-size="${h * 0.6}" text-anchor="middle" opacity=".55">${m.emoji}</text></svg>`;
}

function avatarSvg(seed) {
  const name = NAMES[seed % NAMES.length];
  const initials = name.split(' ').map((p) => p[0]).join('');
  const hue = (seed * 47) % 360;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="185" height="185"><rect width="100%" height="100%" fill="hsl(${hue} 45% 45%)"/><text x="92" y="115" font-family="Arial" font-size="72" font-weight="700" fill="#fff" text-anchor="middle">${initials}</text></svg>`;
}

const detail = (m) => ({
  id: m.tmdb_id,
  title: m.title,
  overview: m.description,
  tagline: m.id % 2 ? 'Some stories are worth the ticket.' : '',
  original_language: LANG[m.language] ?? 'en',
  runtime: m.duration_min,
  genres: [{ id: 1, name: m.genre }, { id: 2, name: m.id % 2 ? 'Adventure' : 'Mystery' }],
  poster_path: `/p${m.tmdb_id}.svg`,
  backdrop_path: `/b${m.tmdb_id}.svg`,
  release_date: '2026-09-04',
  vote_average: m.score,
  vote_count: m.votes,
  credits: { cast: NAMES.map((name, i) => ({ name, character: `Role ${i + 1}`, profile_path: `/c${(m.id * 3 + i) % 10}.svg` })) },
  videos: { results: [{ site: 'YouTube', type: 'Trailer', official: true, key: 'dQw4w9WgXcQ' }] },
  release_dates: { results: [{ iso_3166_1: 'IN', release_dates: [{ certification: m.rating }] }] },
});

http
  .createServer((req, res) => {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const p = url.pathname;
    let hit;
    if (p === '/3/movie/now_playing') {
      return send(res, 200, { page: 1, results: movies.map((m) => ({ id: m.tmdb_id, title: m.title, poster_path: `/p${m.tmdb_id}.svg` })) });
    }
    if ((hit = p.match(/^\/3\/movie\/(\d+)$/))) {
      const m = movies.find((x) => x.tmdb_id === Number(hit[1]));
      return m ? send(res, 200, detail(m)) : send(res, 404, { status_message: 'Not found' });
    }
    if ((hit = p.match(/^\/img\/w500\/p(\d+)\.svg$/))) return send(res, 200, posterSvg(movies.find((x) => x.tmdb_id === Number(hit[1])) ?? movies[0], 500, 750), 'image/svg+xml');
    if ((hit = p.match(/^\/img\/w1280\/b(\d+)\.svg$/))) return send(res, 200, backdropSvg(movies.find((x) => x.tmdb_id === Number(hit[1])) ?? movies[0], 1280, 720), 'image/svg+xml');
    if ((hit = p.match(/^\/img\/w185\/c(\d+)\.svg$/))) return send(res, 200, avatarSvg(Number(hit[1])), 'image/svg+xml');
    send(res, 404, { status_message: 'Not found' });
  })
  .listen(PORT, () => console.log(`Mock TMDB on http://localhost:${PORT}  (${movies.length} movies)`));
