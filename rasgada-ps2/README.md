# Rasgada PS2

Animação 3D low-poly estilo PlayStation 2 explicando como dar uma rasgada (snap) no surf.
Vertical 1080x1920, 30 fps, 42 s, pronta para TikTok / Instagram Reels.

- `rasgada-ps2.mp4`: com trilha e efeitos sonoros
- `rasgada-ps2-sem-audio.mp4`: sem som, para usar um áudio em alta do app

## Roteiro
1. Abertura: "COMO DAR UMA RASGADA"
2. Passo 1, VELOCIDADE: bombear na parede
3. Passo 2, CAVADA: descer até a base, joelhos flexionados, olho no lip (mira + linha da manobra)
4. Passo 3, SUBA NA PAREDE: subir quase vertical até a parte crítica
5. Passo 4, RASGA!: câmera lenta, pausa com câmera girando e indicações (ombros, olhar, pé de trás), spray
6. Passo 5, RECUPERA: centralizar o peso e voltar pra base
7. Replay em velocidade normal
8. Erros comuns + chamada para salvar e mandar pro parceiro

## Como gerar de novo
```
npm install
python3 music.py              # out/audio.wav (precisa de numpy e scipy)
node render.cjs video         # out/video_sem_audio.mp4 (Chromium + Playwright + ffmpeg)
ffmpeg -i out/video_sem_audio.mp4 -i out/audio.wav -c:v libx264 -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest -movflags +faststart rasgada-ps2.mp4
node render.cjs preview 5 12 22   # PNGs de quadros soltos em out/preview
```
Textos e linha do tempo ficam em `src/main.js` (`SCENES`, `drawHUD`).
