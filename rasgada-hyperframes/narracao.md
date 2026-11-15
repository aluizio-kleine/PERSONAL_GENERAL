# Narração (voz única, tom de criador de TikTok: rápido, empolgado, com pausas de efeito)

Versão de teste: voz local Kokoro `pm_alex` (pt-br, velocidade 1.1), arquivos em `assets/audio/voz/`.
Para gerar de novo: `npx hyperframes tts "<fala>" -v pm_alex --lang pt-br -s 1.1 -o assets/audio/voz/<cena>.wav`
(precisa de `pip install kokoro-onnx soundfile`), depois cortar o silêncio e converter para mp3.
Para trocar por uma voz melhor (HeyGen, Runway ou a sua própria), basta substituir os mp3 com o mesmo nome.

Cada fala entra no início da sua cena e precisa caber na janela indicada.

| Cena | Janela | Fala |
| --- | --- | --- |
| intro | 0,0–3,5 s | Quer dar uma rasgada igual os pros? Bora! |
| p1 | 3,5–8,5 s | Passo um: velocidade. Bombeia na parede, porque sem velocidade… não tem rasgada. |
| p2 | 8,5–14,5 s | Passo dois: a cavada. Desce até a base, joelho flexionado, e olho no lip. Ele é o alvo! |
| p3 | 14,5–18,5 s | Passo três: sobe firme, quase na vertical, direto no lip. |
| p4 | 18,5–25,5 s | E agora… rasga! Gira ombro e cabeça pra base, pé de trás pressiona… e joga a rabeta! |
| p5 | 25,5–29,5 s | Passo cinco: flexiona, centraliza o peso e volta pra base. |
| replay | 29,9–35,5 s | Olha de novo, na velocidade real. Rasgada perfeita! |
| outro | 35,5–42,0 s | Erro clássico: pouca velocidade, ombro travado e peso no pé da frente. Salva e manda pro parceiro! |
