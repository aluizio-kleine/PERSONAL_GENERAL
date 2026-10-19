"""Envio para o grupo do WhatsApp pela Evolution API (não oficial: use um número dedicado)."""
import logging

import requests

log = logging.getLogger(__name__)


class WhatsApp:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base = f"{cfg.evolution_url}/message"
        self.cabecalho = {"apikey": cfg.evolution_key}

    def _post(self, rota, corpo):
        resposta = requests.post(f"{self.base}/{rota}/{self.cfg.evolution_instancia}",
                                 json=corpo, headers=self.cabecalho, timeout=60)
        resposta.raise_for_status()
        return resposta.json()

    def enviar_oferta(self, imagem, texto):
        if imagem:
            try:
                return self._post("sendMedia", {
                    "number": self.cfg.whatsapp_grupo,
                    "mediatype": "image",
                    "mimetype": "image/jpeg",
                    "media": imagem,
                    "caption": texto,
                    "fileName": "oferta.jpg",
                })
            except requests.RequestException as erro:
                log.warning("Imagem recusada pela Evolution API (%s); enviando só o texto", erro)
        return self._post("sendText", {"number": self.cfg.whatsapp_grupo, "text": texto})
