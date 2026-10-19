"""Tarefas do robô (coleta, postagens, vídeos) e o bot de aprovação no Telegram."""
import html
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import filtro, redes, texto
from .db import Banco, agora
from .fontes import Coletor
from .telegram import ErroTelegram, Telegram
from .video import gerar_video
from .whatsapp import WhatsApp

log = logging.getLogger(__name__)

AJUDA = """<b>Comandos</b>
/status – resumo do dia
/rodada – gerar um vídeo agora
/convite nome – criar link de convite do canal (ex.: /convite anuncio-a)
/id – mostrar seu chat id"""


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        cfg.pasta_dados.mkdir(parents=True, exist_ok=True)
        self.banco = Banco(cfg.caminho_banco)
        self.coletor = Coletor(cfg, self.banco)
        self.telegram = Telegram(cfg.telegram_token)
        self.whatsapp = WhatsApp(cfg) if cfg.whatsapp_configurado else None

    def horario_ativo(self, momento=None):
        momento = momento or agora()
        return self.cfg.hora_inicio <= momento.hour < self.cfg.hora_fim

    # --- tarefas agendadas -------------------------------------------------

    def coletar(self):
        return self.coletor.coletar()

    def postar_telegram(self, forcar=False):
        if not forcar and not self.horario_ativo():
            return None
        oferta = filtro.proxima_para_telegram(self.banco, self.cfg, agora())
        if not oferta:
            log.info("Nenhuma oferta nova aprovada pelo filtro")
            return None
        self._enviar_ao_canal(oferta)
        return oferta

    def _enviar_ao_canal(self, oferta):
        self.telegram.enviar_foto(self.cfg.telegram_canal, oferta["imagem"], texto.mensagem_telegram(oferta))
        self.banco.marcar(oferta["id"], "telegram_em", preco=oferta["preco"])
        log.info("Telegram: %s", oferta["titulo"][:60])

    def postar_whatsapp(self):
        if not self.whatsapp:
            return None
        momento = agora()
        # Só vai para o WhatsApp o que já saiu no Telegram há algum tempo (o Telegram sai primeiro).
        candidatas = self.banco.postadas_no_telegram(
            desde=momento - timedelta(hours=24),
            ate=momento - timedelta(minutes=self.cfg.whatsapp_atraso_min))
        # "postada recentemente" se refere ao Telegram; aqui só importa que a oferta continue boa.
        candidatas = [o for o in candidatas if filtro.avaliar(self.banco, self.cfg, o, momento)[1]
                      in ("ok", "postada recentemente")]
        if not candidatas:
            return None
        oferta = max(candidatas, key=filtro.pontuacao)
        self.whatsapp.enviar_oferta(oferta["imagem"], texto.mensagem_whatsapp(oferta, self.cfg))
        self.banco.marcar(oferta["id"], "whatsapp_em")
        log.info("WhatsApp: %s", oferta["titulo"][:60])
        return oferta

    def rodada_videos(self):
        if not self.cfg.telegram_admin:
            log.warning("TELEGRAM_ADMIN_ID vazio: não há para quem mandar os vídeos")
            return
        for _ in range(self.cfg.videos_por_rodada):
            self.enviar_novo_video()

    def enviar_novo_video(self, ignorar=()):
        ignorar, ultimo_erro = set(ignorar), None
        for _ in range(3):  # se a foto de uma oferta não baixar, tenta a próxima
            escolhidas = filtro.melhores_para_video(self.banco, self.cfg, agora(), 1, ignorar)
            if not escolhidas and ultimo_erro:
                break
            if not escolhidas:
                self.telegram.enviar_mensagem(self.cfg.telegram_admin,
                                              "Sem ofertas boas para vídeo agora. Tento na próxima rodada.")
                return None
            oferta = escolhidas[0]
            try:
                caminho, legenda = gerar_video(self.cfg, oferta)
            except Exception as erro:
                log.exception("Falha ao gerar vídeo de %s", oferta["id"])
                ignorar.add(oferta["id"])
                ultimo_erro = erro
                continue
            self.banco.marcar(oferta["id"], "video_em")
            video_id = self.banco.criar_video(oferta["id"], caminho, legenda)
            teclado = {"inline_keyboard": [
                [{"text": "✅ Aprovar", "callback_data": f"aprovar:{video_id}"},
                 {"text": "❌ Rejeitar", "callback_data": f"rejeitar:{video_id}"}],
                [{"text": "🔄 Trocar oferta", "callback_data": f"trocar:{video_id}"}],
            ]}
            previa = f"🎬 <b>Vídeo para aprovar</b>\n\n{html.escape(legenda)}"
            self.telegram.enviar_video(self.cfg.telegram_admin, caminho, previa, teclado)
            return video_id
        self.telegram.enviar_mensagem(
            self.cfg.telegram_admin,
            f"⚠️ Não consegui gerar o vídeo desta rodada: {html.escape(str(ultimo_erro))[:300]}\n"
            "Se o erro for na voz, configure a ElevenLabs no .env.")
        return None

    # --- aprovação ---------------------------------------------------------

    def aprovar(self, video_id):
        video = self.banco.video(video_id)
        oferta = self.banco.oferta(video["oferta_id"])
        self.banco.mudar_status_video(video_id, "aprovado")
        resultados = []

        # Quem vier pelo vídeo precisa achar a oferta no canal.
        postada = oferta["telegram_em"]
        if not postada or agora() - datetime.fromisoformat(postada) > timedelta(days=1):
            try:
                self._enviar_ao_canal(oferta)
                resultados.append("✅ Oferta postada no canal do Telegram")
            except ErroTelegram as erro:
                resultados.append(f"⚠️ Canal do Telegram: {erro}")

        caminho = Path(video["caminho"])
        if self.cfg.instagram_ativo:
            try:
                redes.publicar_reels(self.cfg, caminho, video["legenda"])
                resultados.append("✅ Publicado no Instagram Reels")
            except Exception as erro:
                log.exception("Erro no Instagram")
                resultados.append(f"⚠️ Instagram: {erro}")
        if self.cfg.youtube_ativo:
            try:
                redes.publicar_shorts(self.cfg, caminho, texto.titulo_curto(oferta["titulo"], 80),
                                      video["legenda"])
                resultados.append(f"✅ Enviado ao YouTube Shorts ({self.cfg.youtube_privacidade})")
            except Exception as erro:
                log.exception("Erro no YouTube")
                resultados.append(f"⚠️ YouTube: {erro}")

        resultados += [
            "",
            "📱 <b>Agora o TikTok:</b> salve o vídeo acima, poste com um som em alta e cole a legenda:",
            f"<pre>{html.escape(video['legenda'])}</pre>",
        ]
        self.telegram.enviar_mensagem(self.cfg.telegram_admin, "\n".join(resultados))

    def status(self):
        momento = agora()
        inicio_dia = momento.replace(hour=0, minute=0, second=0)
        lojas = ", ".join(nome for nome, _ in self.coletor.lojas) or "nenhuma (configure o .env)"
        return "\n".join([
            "<b>Resumo de hoje</b>",
            f"Lojas ativas: {lojas}",
            f"Ofertas vistas nas últimas 6h: {len(self.banco.ofertas_recentes(6))}",
            f"Prontas para postar agora: {len(filtro.ranking(self.banco, self.cfg, momento))}",
            f"Postadas no Telegram hoje: {self.banco.contar_postagens('telegram_em', inicio_dia)}",
            "Postadas no WhatsApp hoje: "
            + (str(self.banco.contar_postagens('whatsapp_em', inicio_dia)) if self.whatsapp else "desligado"),
            f"Vídeos hoje: {self.banco.contar_postagens('video_em', inicio_dia)}",
        ])

    # --- bot ---------------------------------------------------------------

    def tratar_mensagem(self, mensagem):
        chat = str(mensagem["chat"]["id"])
        comando, _, argumento = (mensagem.get("text") or "").strip().partition(" ")
        comando = comando.split("@")[0].lower()

        if comando in ("/start", "/id"):
            self.telegram.enviar_mensagem(chat, f"Seu chat id é <code>{chat}</code>.\n"
                                                "Coloque-o em TELEGRAM_ADMIN_ID no arquivo .env.")
            return
        if chat != self.cfg.telegram_admin:
            return  # o bot só obedece ao dono
        if comando == "/status":
            self.telegram.enviar_mensagem(chat, self.status())
        elif comando == "/rodada":
            self.telegram.enviar_mensagem(chat, "Gerando vídeo…")
            self.enviar_novo_video()
        elif comando == "/convite":
            nome = argumento.strip() or "geral"
            link = self.telegram.criar_convite(self.cfg.telegram_canal, nome)
            self.telegram.enviar_mensagem(chat, f"Link <b>{html.escape(nome)}</b>: {link}\n"
                                                "Use um link diferente para cada origem de tráfego.")
        else:
            self.telegram.enviar_mensagem(chat, AJUDA)

    def tratar_botao(self, botao):
        chat = str(botao["message"]["chat"]["id"])
        if chat != self.cfg.telegram_admin:
            return
        acao, _, video_id = botao["data"].partition(":")
        video = self.banco.video(int(video_id))
        if not video or video["status"] != "pendente":
            self.telegram.responder_botao(botao["id"], "Esse vídeo já foi resolvido.")
            return
        self.telegram.remover_botoes(chat, botao["message"]["message_id"])
        if acao == "aprovar":
            self.telegram.responder_botao(botao["id"], "Publicando…")
            self.aprovar(video["id"])
        elif acao == "rejeitar":
            self.banco.mudar_status_video(video["id"], "rejeitado")
            self.telegram.responder_botao(botao["id"], "Rejeitado")
        elif acao == "trocar":
            self.banco.mudar_status_video(video["id"], "rejeitado")
            self.telegram.responder_botao(botao["id"], "Gerando outro vídeo…")
            self.enviar_novo_video(ignorar={video["oferta_id"]})

    def ouvir_bot(self):
        offset = int(self.banco.ler_estado("telegram_offset", 0))
        while True:
            try:
                atualizacoes = self.telegram.atualizacoes(offset)
            except Exception as erro:
                log.warning("Bot: %s", erro)
                time.sleep(10)
                continue
            for atualizacao in atualizacoes:
                offset = atualizacao["update_id"] + 1
                self.banco.gravar_estado("telegram_offset", offset)
                try:
                    if "callback_query" in atualizacao:
                        self.tratar_botao(atualizacao["callback_query"])
                    elif "message" in atualizacao:
                        self.tratar_mensagem(atualizacao["message"])
                except Exception:
                    log.exception("Erro ao tratar atualização do bot")
