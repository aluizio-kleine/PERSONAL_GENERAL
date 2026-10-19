"""Narração dos vídeos: ElevenLabs (paga) se houver chave, senão a voz neural gratuita do Edge."""
import asyncio

import edge_tts
import requests


def narrar(cfg, texto, destino):
    if cfg.elevenlabs_key and cfg.elevenlabs_voz:
        resposta = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.elevenlabs_voz}",
            headers={"xi-api-key": cfg.elevenlabs_key, "Accept": "audio/mpeg"},
            json={"text": texto, "model_id": "eleven_multilingual_v2"},
            timeout=120,
        )
        resposta.raise_for_status()
        destino.write_bytes(resposta.content)
    else:
        asyncio.run(edge_tts.Communicate(texto, cfg.voz_edge, rate="+10%").save(str(destino)))
    return destino
