"""Cliente mínimo da Bot API do Telegram."""
import json
import logging
import time

import requests

log = logging.getLogger(__name__)


class ErroTelegram(Exception):
    pass


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"

    def chamar(self, metodo, arquivos=None, tempo_limite=60, **dados):
        dados = {k: (json.dumps(v) if isinstance(v, (dict, list, bool)) else v)
                 for k, v in dados.items() if v is not None}
        for _ in range(3):
            for arquivo in (arquivos or {}).values():
                arquivo.seek(0)
            resposta = requests.post(f"{self.base}/{metodo}", data=dados, files=arquivos, timeout=tempo_limite)
            corpo = resposta.json()
            if corpo.get("ok"):
                return corpo["result"]
            espera = corpo.get("parameters", {}).get("retry_after")
            if not espera:
                break
            log.info("Telegram pediu para esperar %ss", espera)
            time.sleep(espera)
        raise ErroTelegram(f"{metodo}: {corpo.get('description')}")

    def enviar_mensagem(self, chat, texto, teclado=None):
        return self.chamar("sendMessage", chat_id=chat, text=texto, parse_mode="HTML",
                           reply_markup=teclado)

    def enviar_foto(self, chat, foto, legenda):
        if foto:
            try:
                return self.chamar("sendPhoto", chat_id=chat, photo=foto, caption=legenda[:1024],
                                   parse_mode="HTML")
            except ErroTelegram as erro:
                log.warning("Foto recusada (%s); enviando só o texto", erro)
        return self.enviar_mensagem(chat, legenda)

    def enviar_video(self, chat, caminho, legenda, teclado=None):
        with open(caminho, "rb") as arquivo:
            return self.chamar("sendVideo", arquivos={"video": arquivo}, tempo_limite=300, chat_id=chat,
                               caption=legenda[:1024], parse_mode="HTML", reply_markup=teclado,
                               supports_streaming=True)

    def atualizacoes(self, offset, espera=50):
        return self.chamar("getUpdates", tempo_limite=espera + 10, offset=offset, timeout=espera,
                           allowed_updates=["message", "callback_query"])

    def responder_botao(self, callback_id, texto=""):
        return self.chamar("answerCallbackQuery", callback_query_id=callback_id, text=texto)

    def remover_botoes(self, chat, mensagem_id):
        return self.chamar("editMessageReplyMarkup", chat_id=chat, message_id=mensagem_id,
                           reply_markup={"inline_keyboard": []})

    def criar_convite(self, chat, nome):
        return self.chamar("createChatInviteLink", chat_id=chat, name=nome[:32])["invite_link"]
