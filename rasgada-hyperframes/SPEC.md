# SPEC: Como dar uma rasgada (PS2)

GOAL:    a surfer who watches once knows the 5 steps of a rasgada (snap) and saves the clip to practise.
OUTPUT:  HyperFrames, 1080 x 1920 (TikTok / Reels), 30 fps.
TIME:    42 s x 30 fps = 1260 frames. Music bed 120 BPM = 15 frames per beat, a bar every 2 s.

LOOK:    the medium is a 2002 PlayStation 2 surf game, and every rule comes from it.
         - 3D: flat-shaded low-poly, 64 px nearest-filtered water texture, no anti-aliasing,
           rendered at 540 x 960 and doubled with nearest neighbour (each texel = 2 x 2 px).
         - Ground: sky #2a6bdb at the zenith to #b8dbf5 at the horizon; water #1e6b8a at the trough to
           #3db8b8 near the lip; whitewater #eef8ff. Fog from 70 m to 420 m, horizon colour.
         - Console post: 32% screen bloom with a 6 px blur (PS2 trademark, kept because the reference
           asks for it), 4x4 ordered dither at 7%, scanlines at 10% on every other line, 45% vignette.
         - Ink: Press Start 2P only. Step label 32 px #7fe0ff; step title 64 px gold gradient
           #fffbd0 > #ffd21f > #ff6a00 with a 14 px #000814 outline and a 6 px hard drop shadow;
           body 32 px white with an 8 px outline. Accent red #ff2a1a only on "ALVO", the X marks of the
           common mistakes and the REPLAY tag.
         - Panels: the game's dialog box, navy #122878 to #050a1e at 80%, 3 px #bee6ff border,
           1 px inner line at 30% white, 16% white sheen on the top 45%.
OBJECTS: the surfer (red competition lycra with a white bib, black boardshorts, tan skin, dark hair,
         blocky face texture), a 6'1" white thruster with a red and a blue stripe, a black tail pad and
         three fins; a right-to-left peeling wave whose lip pitches and throws a whitewater curtain;
         the spray fan off the tail (2200 square sprites); low-poly hills, palms and sand on the coast.
MOTION:  text enters with back.out(1.9) over 14 frames (step titles slide from x = -840 px);
         tip lines type with steps(chars) at 38 characters per second; popups scale 0 > 1 over 10 frames
         with back.out(1.9), hold, fade over 15 frames; panels open on scaleY over 9 frames.
         Camera cuts are hard, with a 7-frame white flash; no flash on frame 0.
         The surf itself is a pure function of time t (keyframed path, Hermite splines).
SHOTS:
  0-105      INTRO. Frame 0 already shows the surfer on the wave and "COMO DAR UMA / RASGADA" (the hook).
             Camera flies from wide and high down to the line. "TUTORIAL DE SURF" at 27, PRESS START at 42.
  105-180    P1 VELOCIDADE, cam behind the surfer. Tip types; speed bar fills from 132.
  180-255    P1, cut to the shoulder cam in front; bar reaches MAX! at 222.
  255-345    P2 CAVADA, wide from the shoulder: the curl, the reticle "ALVO" on the lip, the dotted line.
  345-435    P2, cut closer from the side, slow motion 0.33x through the bottom turn.
  435-555    P3 SUBA NA PAREDE, low from the flats, 0.2x, reticle and the line still on.
  555-765    P4 RASGA! 555-615 slow 0.1x; 615-705 freeze (PAUSE) with the camera orbiting 85 deg and three
             labels with leader lines: 1 OMBROS GIRAM, 2 OLHAR NA BASE, 3 PE DE TRAS; 705-765 release
             0.2x, flash at 711 and RASGADA! +2500 at 712 (the payoff, the one riser into impact).
  765-885    P5 RECUPERA, back down to the bottom at 0.5x.
  885-930    REPLAY real speed, front cam. 930-990 close side cam, snap at 954, RASGADA PERFEITA at 957.
  990-1065   REPLAY wide; +5000 lands at 969 and holds to 1032.
  1065-1260  OUTRO. Drone shot under a 50% dim; ERROS COMUNS panel, four X lines every 16 frames from
             1080; SALVA E VAI TREINAR! at 1161; MANDA PRO PARCEIRO at 1182; CONTINUE? countdown from 1203.
SOUND:   music bed (the synthesised track from the first version, 120 BPM, low-passed during the freeze);
         effects only on causes: whoosh on each cut (three takes rotated), pop on each step title and
         popup, riser into impact-bass on the payoff, impact-bass on the replay snap, click on each X.
SAFE:    every word between y = 168 and y = 1330 px, nothing readable under the right-hand rail
         (x > 940 px below y = 900 px).
BANNED:  a white or black first frame; text below 1330 px; corner brackets or HUD as decoration (the
         reticle marks the real target and the line is the real path); floating particles that are not
         water; everything fading in at once; text that moves while it is read; synthesised dings.
QA:      0.0 (hook readable), 6.0, 10.0, 13.0, 16.5, 21.0, 22.5 (all three labels), 23.9 (payoff),
         27.0, 31.9, 33.5, 38.5, 41.5.
