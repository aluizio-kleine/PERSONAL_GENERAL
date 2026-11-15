# Rasgada PS2 (HyperFrames)

Tutorial de surf em 3D estilo PlayStation 2, vertical 1080x1920, 30 fps, 42 s, feito com
[HyperFrames](https://hyperframes.heygen.com) (HTML renderizado em vídeo).

- `renders/rasgada-ps2-sem-narracao.mp4`: o vídeo final (trilha + efeitos, sem voz)
- `SPEC.md`: o roteiro em números (planos, tempos, cores, fontes); `REVIEW.md`: a revisão

## Estrutura
- `index.html`: composição raiz (cenas + trilha + efeitos sonoros)
- `compositions/surf.html`: a cena 3D (canvas desenhado a cada `hf-seek`)
- `compositions/intro.html`, `p1.html` ... `p5.html`, `replay.html`, `outro.html`: textos e animações GSAP
- `src/engine.js`: onda, surfista, câmeras e pós PS2 (fonte); `build-engine.mjs` gera `assets/lib/surf-engine.js`
- `music.py`: gera `assets/audio/trilha.mp3`; efeitos em `assets/audio/sfx` (Pixabay, ver CREDITS.md)

## Editar e renderizar
```
npm install
npx hyperframes preview          # editor no navegador; textos são variáveis editáveis
node build-engine.mjs            # depois de mexer em src/engine.js
npx hyperframes check            # lint, layout, contraste, tempo de leitura
npx hyperframes render --quality delivery -o renders/rasgada-ps2.mp4
```
Neste ambiente o navegador usado foi o headless shell já instalado:
`HYPERFRAMES_BROWSER_PATH=/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell`.
Telemetria desligada com `HYPERFRAMES_NO_TELEMETRY=1`.
