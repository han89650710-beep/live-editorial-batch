import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

function parseArgs(argv) {
  const args = { jobs: '', only: '' };
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
const selected = args.only ? jobs.filter(job => job.id === args.only) : jobs;
if (!selected.length) throw new Error(`No jobs matched --only ${args.only}`);

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
  args: ['--allow-file-access-from-files', '--hide-scrollbars', '--font-render-hinting=none'],
});

try {
  const first = selected[0];
  const width = first.width || 1080;
  const height = first.height || 1920;
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  for (const job of selected) {
    const jobWidth = job.width || width;
    const jobHeight = job.height || height;
    if (jobWidth !== width || jobHeight !== height) await page.setViewportSize({ width: jobWidth, height: jobHeight });
    const htmlPath = path.resolve(root, job.html);
    const outDir = path.resolve(root, job.out);
    fs.mkdirSync(outDir, { recursive: true });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map(image => image.complete ? image.decode().catch(() => {}) : new Promise(resolve => {
        image.addEventListener('load', resolve, { once: true });
        image.addEventListener('error', resolve, { once: true });
      })));
    });
    const environment = await page.evaluate(() => ({
      ready: window.__WEB_MOTION_READY__ === true,
      renderAt: typeof window.renderAt === 'function',
      yaHei: document.fonts.check('700 96px "Microsoft YaHei"'),
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
    }));
    if (!environment.ready || !environment.renderAt) throw new Error(`${job.id}: renderAt(t) stage did not initialize`);
    if (environment.width !== jobWidth || environment.height !== jobHeight) throw new Error(`${job.id}: unexpected stage dimensions ${JSON.stringify(environment)}`);

    const rendered = [];
    for (let offset = 0; offset < job.count; offset += 1) {
      const frame = offset;
      const time = job.startTime + frame / job.fps;
      const filename = `frame_${String(frame).padStart(5, '0')}.png`;
      const destination = path.join(outDir, filename);
      const skipped = fs.existsSync(destination);
      if (!skipped) {
        await page.evaluate(t => window.renderAt(t), time);
        await page.screenshot({ path: destination, type: 'png', omitBackground: true, animations: 'disabled' });
      }
      rendered.push({ frame, time: Number(time.toFixed(6)), file: filename, skipped });
      if ((offset + 1) % 60 === 0 || offset + 1 === job.count) process.stdout.write(`[${job.id}] captured ${offset + 1}/${job.count}\n`);
    }
    const manifest = { id: job.id, html: htmlPath, chrome: chromePath, fps: job.fps, startTime: job.startTime, count: job.count, environment, frames: rendered };
    fs.writeFileSync(path.join(outDir, 'capture_manifest.json'), JSON.stringify(manifest, null, 2));
    process.stdout.write(`[${job.id}] done ${job.count} frames -> ${outDir}\n`);
  }
} finally {
  await browser.close();
}
