# REVIEW: Como dar uma rasgada (PS2), versão HyperFrames

## Decisões criativas
- Port da versão anterior (`../rasgada-ps2`) para HyperFrames, mantendo o roteiro e os 5 passos. Não
  escrevi três roteiros alternativos (story.md): a história já estava escolhida e aprovada no vídeo anterior.
- A cena 3D (Three.js) virou uma composição desenhada a partir do tempo (`hf-seek`) em
  `compositions/surf.html`; todo texto virou HTML editável em uma composição por cena, com variáveis
  (título do passo, linhas da dica, erros comuns, chamada final).
- Mudanças pedidas pelas regras de vídeo vertical da skill:
  - quadro 0 = gancho (título + surfista na onda), sem o flash branco que abria a versão anterior;
  - todo texto entre 168 e 1330 px; "PÉ DE TRÁS", "II PAUSE" e "+5000" saíram da zona da legenda do app;
  - cortes extras de câmera em P1 (6,0 s), P2 (11,5 s) e no replay (31,0 s e 33,0 s) para um beat novo a cada 2 a 4 s;
  - dicas encurtadas em P3 e P5 para caber no tempo de leitura (0,5 s + 0,3 s por palavra);
  - legendas da pausa empilhadas à esquerda, longe do rail de botões da direita;
  - textos que piscavam (PRESS START, MAX!, II PAUSE, CONTINUE?) agora ficam fixos ou pulsam sem sumir.
- Exceções conscientes à lista BANNED da skill, porque o pedido é "estilo PS2": bloom leve, caixas de
  diálogo em degradê azul e HUD de jogo. A mira e a linha pontilhada não são decoração: marcam o alvo
  real e a trajetória real da manobra.

## O que foi medido e o que só foi olhado
- `npx hyperframes check`: ok, 0 erros.
- Avisos mantidos de propósito:
  - `contrast_aa_failure` (16): o checador mede a camada de contorno preto ou o branco contra o céu sem
    contar o contorno de 8 a 22 px. Na tela o texto lê bem (conferido na folha de 360 px).
  - `canvas_content_at_edge`: o canvas 3D é tela cheia de propósito.
  - `escaped_container` em `#replay-tag`: só durante a entrada deslizando.
  - `console_warning` do WebGL (GPU stall em ReadPixels): desempenho do render por software, não visual.
- Folhas `snapshot --review` (beats, cortes e largura de celular) olhadas por mim.
- Som: os efeitos foram posicionados pelos picos medidos (`hyperframes audio`), mas ninguém ouviu a mixagem.
  A trilha é a mesma sintetizada da primeira versão; a skill prefere música de catálogo (HeyGen, precisa de login).

## Ponto mais fraco
- A câmera da pausa (21 a 23,5 s) deixa o surfista baixo no quadro e as linhas 1 e 2 quase paralelas.
  Com mais tempo: subir o alvo da câmera uns 0,4 m e apontar a linha 2 para os olhos, não para o topo da cabeça.

## Narração (versão de teste)
- Voz local Kokoro `pm_alex` em pt-br: grátis, mas soa sintética. A HeyGen (plano Free) e o Runway
  (plano Free) recusaram gerar voz; para a versão final, troque os mp3 em `assets/audio/voz/` por uma voz
  melhor ou pela sua própria gravação, com os mesmos nomes.
- Cada fala começa ~0,2 s depois do corte da sua cena; "Rasgada perfeita!" cai junto do popup do replay.
- A música desce para 40% sob a voz (lane de volume em `#trilha`) e a voz tem highpass, presença em 3 kHz,
  compressor e limiter (`data-fx-chain`). Falas normalizadas para ~-16 LUFS e música a 28% sob a voz.
- Arquivo final normalizado para -13,8 LUFS integrado com pico de -1,3 dBTP (faixa de redes sociais).
  Medido com ffmpeg ebur128, não ouvido.
