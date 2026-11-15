// Empacota src/engine.js + three.js num script clássico (assets/lib/surf-engine.js).
// O three.js traz Math.random() (UUIDs, Vector.random) e um loop com requestAnimationFrame
// (setAnimationLoop) que este projeto não usa. Para o render ser 100% determinístico, o build
// troca Math.random por um PRNG com semente fixa e desliga o loop de animação.
import { build } from 'esbuild';
import { readFile } from 'node:fs/promises';

const deterministicThree = {
  name: 'deterministic-three',
  setup(b) {
    b.onLoad({ filter: /three[\\/]build[\\/]three\.module\.js$/ }, async (args) => {
      let code = await readFile(args.path, 'utf8');
      code = code.replaceAll('Math.random()', '__hfRandom()')
                 .replaceAll('requestAnimationFrame', '__hfNoAnimationLoop')
                 .replaceAll('cancelAnimationFrame', '__hfNoAnimationLoop');
      return { contents: code, loader: 'js' };
    });
  },
};

await build({
  entryPoints: ['src/engine.js'],
  bundle: true,
  format: 'iife',
  globalName: 'SurfEngine',
  minify: true,
  legalComments: 'none',
  outfile: 'assets/lib/surf-engine.js',
  banner: { js: 'var __hfRandom=(function(){var a=20261115;return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};})();' },
  plugins: [deterministicThree],
});
console.log('assets/lib/surf-engine.js');
