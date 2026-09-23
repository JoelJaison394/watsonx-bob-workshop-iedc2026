// Static demo data: the fictional fallback movies, theatres and seat pricing.
// No database import here on purpose, so scripts can use it freely.

export const MOVIES = [
  { id: 1, title: 'Agent 404', genre: 'Comedy', language: 'English', duration_min: 112, rating: 'UA', emoji: '🤖', color1: '#7c3aed', color2: '#ec4899',
    description: 'A rookie AI agent keeps getting lost between tools, until she discovers the one orchestration that finally connects everything.' },
  { id: 2, title: 'Neon Monsoon', genre: 'Thriller', language: 'Hindi', duration_min: 138, rating: 'UA', emoji: '🌃', color1: '#0ea5e9', color2: '#1e1b4b',
    description: 'One rainy night in Mumbai, a cab driver picks up a passenger carrying a secret that half the city is chasing.' },
  { id: 3, title: 'Quantum Kabaddi', genre: 'Sports', language: 'Hindi', duration_min: 149, rating: 'U', emoji: '🌀', color1: '#f97316', color2: '#dc2626',
    description: 'A village kabaddi team discovers that their raider can be in two places at once. The league is not ready.' },
  { id: 4, title: 'The Last Chai Stall', genre: 'Drama', language: 'Hindi', duration_min: 121, rating: 'U', emoji: '☕', color1: '#b45309', color2: '#f59e0b',
    description: 'As a tech park swallows the old neighbourhood, one chai seller and his regulars fight to keep a small corner of the world.' },
  { id: 5, title: 'Paws & Planets', genre: 'Animation', language: 'English', duration_min: 96, rating: 'U', emoji: '🐶', color1: '#06b6d4', color2: '#8b5cf6',
    description: 'A very brave street dog and a very small astronaut cross the galaxy to bring the last bone home.' },
  { id: 6, title: 'Whispers of Hampi', genre: 'Romance', language: 'Kannada', duration_min: 132, rating: 'UA', emoji: '🏛️', color1: '#db2777', color2: '#f59e0b',
    description: 'Two archaeologists, five hundred years apart, leave letters in the same stone pillar. One of them starts replying.' },
  { id: 7, title: 'Code Red: Bengaluru', genre: 'Action', language: 'English', duration_min: 127, rating: 'UA', emoji: '💻', color1: '#16a34a', color2: '#052e16',
    description: 'A city-wide outage, a rogue deployment, and one on-call engineer who has exactly ninety minutes before sunrise.' },
  { id: 8, title: 'The Robot Who Loved Rain', genre: 'Sci-Fi', language: 'English', duration_min: 118, rating: 'U', emoji: '🦾', color1: '#64748b', color2: '#0f172a',
    description: 'In a world that never stops working, one maintenance robot stops to watch the rain and starts a quiet revolution.' },
];

export const THEATRES = [
  'Starlight Cinemas, Orion Mall',
  'Grand Rex Multiplex, MG Road',
  'Cine Loft, Indiranagar',
];

// The workshop's own movie stays in the catalogue even when TMDB is on.
export const WORKSHOP_MOVIE_ID = 1;

// Seat price tiers. `add` is on top of the show's base (Silver) price.
export const TIERS = [
  { name: 'Silver', rows: 'ABC', add: 0 },
  { name: 'Gold', rows: 'DEF', add: 50 },
  { name: 'Platinum', rows: 'GH', add: 100 },
];
const tierForRow = (letter) => TIERS.find((t) => t.rows.includes(letter)) ?? TIERS[TIERS.length - 1];
export const seatPrice = (basePrice, seat) => basePrice + tierForRow(seat[0]).add;
export const seatTotal = (basePrice, seats) => seats.reduce((sum, s) => sum + seatPrice(basePrice, s), 0);
export const tiersFor = (basePrice) => TIERS.map((t) => ({ name: t.name, rows: [...t.rows], price: basePrice + t.add }));
