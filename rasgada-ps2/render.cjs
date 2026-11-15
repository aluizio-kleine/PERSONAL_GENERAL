// Renderiza a animação quadro a quadro no Chromium headless e codifica com ffmpeg.
// Uso:
//   node render.cjs preview 1.0 5.2 20      -> PNGs desses segundos em out/preview
//   node render.cjs video                   -> out/video_sem_audio.mp4 (1080x1920, 30fps)
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { chromium } = require('playwright');

const ROOT = __dirname;
const OUT = path.join(ROOT, 'out');
fs.mkdirSync(OUT, { recursive: true });
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.woff2': 'font/woff2', '.json': 'application/json' };

function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const p = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
      if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { rsp.writeHead(404); return rsp.end(); }
      rsp.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' });
      fs.createReadStream(p).pipe(rsp);
    });
    srv.listen(0, '127.0.0.1', () => res(srv));
  });
}

(async () => {
  const [mode = 'preview', ...rest] = process.argv.slice(2);
  const srv = await serve();
  const port = srv.address().port;
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 540, height: 960 } });
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.text()); });
  page.on('pageerror', e => console.log('[pageerror]', e.message));
  await page.goto(`http://127.0.0.1:${port}/src/index.html`);
  await page.waitForFunction(() => window.READY === true, null, { timeout: 120000 });
  const fps = await page.evaluate(() => window.FPS);
  const dur = await page.evaluate(() => window.DURATION);

  if (mode === 'preview') {
    const dir = path.join(OUT, 'preview'); fs.mkdirSync(dir, { recursive: true });
    for (const s of rest.map(Number)) {
      const b64 = await page.evaluate(f => window.renderFrame(f), Math.round(s * fps));
      const file = path.join(dir, `t${s.toFixed(2)}.png`);
      fs.writeFileSync(file, Buffer.from(b64.split(',')[1], 'base64'));
      console.log(file);
    }
  } else {
    const total = Math.round(dur * fps);
    const outFile = path.join(OUT, 'video_sem_audio.mp4');
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
      '-vf', 'scale=1080:1920:flags=neighbor', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', outFile], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let f = 0; f < total; f++) {
      const b64 = await page.evaluate(n => window.renderFrame(n), f);
      const buf = Buffer.from(b64.split(',')[1], 'base64');
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (f % 60 === 0) console.log(`frame ${f}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
    console.log('ok', outFile);
  }
  await browser.close(); srv.close();
})();
