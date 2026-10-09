const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const out = process.argv[2];
  const views = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage();
  p.on('console', m => console.log('console:', m.text()));
  p.on('pageerror', e => console.log('pageerror:', e.message));
  await p.goto('http://localhost:8765/scene.html');
  await p.waitForFunction('window.ready === true', null, { timeout: 120000 });
  console.log(JSON.stringify(await p.evaluate('window.info')));
  const pts = {};
  for (const [name, v] of Object.entries(views)) {
    const r = await p.evaluate(v => window.renderView(v), v);
    fs.writeFileSync(`${out}/${name}.png`, Buffer.from(r.png.split(',')[1], 'base64'));
    pts[name] = r.pts;
    console.log('rendered', name);
  }
  fs.writeFileSync(`${out}/points.json`, JSON.stringify(pts, null, 1));
  await b.close();
})();
