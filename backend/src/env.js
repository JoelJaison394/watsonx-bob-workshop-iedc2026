// Loads backend/.env (if present) before anything else reads process.env.
// Import this first. Real environment variables always win over the file.
import fs from 'node:fs';
import path from 'node:path';

const file = path.join(process.cwd(), '.env');
if (fs.existsSync(file)) process.loadEnvFile(file);
