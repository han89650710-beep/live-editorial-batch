import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

function parseArgs(argv) {
  const args = { jobs: '' };
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i]?.replace(/^--/, '');
    const value = argv[i + 1];
    if (!key || value === undefined) throw new Error('Arguments must use --key value pairs');
    args[key] = value;
  }
  if (!args.jobs) throw new Error('--jobs jobs.json is required');
  return args;
}

const args = parseArgs(process.argv);
const root = path.dirname(fileURLToPath(import.meta.url));
function findChrome() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const local = process.env.LOCALAPPDATA || '';
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    local ? path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  throw new Error('Chrome not found. Install Chrome or set CHROME_PATH.');
}

const chromePath = findChrome();
const jobs = JSON.parse(fs.readFileSync(path.resolve(root, args.jobs), 'utf8'));

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ['--allow-file-access-from-files', '--hide-scrollbars', '--font-render-hinting=none'],
});

try {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1440 }, deviceScaleFactor: 1 });
  for (const job of jobs) {
    const width = job.width || 1080;
    const height = job.height || 1440;
    await page.setViewportSize({ width, height });
    const htmlPath = path.resolve(root, job.html);
    const outPath = path.resolve(root, job.out);
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map(image => image.complete ? image.decode().catch(() => {}) : new Promise(resolve => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      })));
    });
    const ready = await page.evaluate(() => ({
      ready: window.__COVER_READY__ === true,
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
      bg: document.querySelector('.bg')?.naturalWidth || 0,
    }));
    if (!ready.ready) throw new Error(`${job.id}: cover stage did not initialize`);
    if (ready.width !== width || ready.height !== height) throw new Error(`${job.id}: unexpected cover size ${JSON.stringify(ready)}`);
    if (!ready.bg) throw new Error(`${job.id}: cover background image failed to load`);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    await page.screenshot({ path: outPath, type: 'png', animations: 'disabled' });
    process.stdout.write(`[${job.id}] cover -> ${outPath}\n`);
  }
} finally {
  await browser.close();
}
