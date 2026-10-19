"""Linha de comando.

    python -m ofertas                 roda tudo (coleta, postagens, vídeos e bot)
    python -m ofertas coletar         uma coleta e mostra as 10 melhores ofertas
    python -m ofertas teste-telegram  posta a melhor oferta no canal agora
    python -m ofertas teste-whatsapp  manda a melhor oferta já postada para o grupo agora
    python -m ofertas teste-video     gera um vídeo e manda para você aprovar
    python -m ofertas ml-token CODIGO troca o código do Mercado Livre por um refresh token
"""
import logging
import sys
import threading
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler

from . import filtro, texto
from .app import App
from .config import Config
from .db import agora


def agendar(app, cfg):
    agenda = BackgroundScheduler(timezone=cfg.fuso, job_defaults={"coalesce": True, "max_instances": 1,
                                                                  "misfire_grace_time": 600})
    agenda.add_job(app.coletar, "interval", minutes=cfg.intervalo_coleta_min, next_run_time=agora())
    agenda.add_job(app.postar_telegram, "interval", minutes=cfg.intervalo_telegram_min)
    for hora, minuto in cfg.whatsapp_horarios:
        agenda.add_job(app.postar_whatsapp, "cron", hour=hora, minute=minuto)
    for hora, minuto in cfg.rodadas_video:
        agenda.add_job(app.rodada_videos, "cron", hour=hora, minute=minuto)
    agenda.start()
    return agenda


def rodar(app, cfg):
    agendar(app, cfg)
    logging.info("Robô no ar. Canal: %s | WhatsApp: %s | Instagram: %s | YouTube: %s",
                 cfg.telegram_canal, "ligado" if app.whatsapp else "desligado",
                 "ligado" if cfg.instagram_ativo else "desligado",
                 "ligado" if cfg.youtube_ativo else "desligado")
    bot = threading.Thread(target=app.ouvir_bot, daemon=True)
    bot.start()
    while True:
        time.sleep(3600)


def mostrar_ranking(app, cfg):
    app.coletar()
    melhores = filtro.ranking(app.banco, cfg, agora())
    print(f"\n{len(melhores)} ofertas passaram no filtro. As 10 melhores:\n")
    for oferta in melhores[:10]:
        print(f"{oferta['desconto']:>4.0f}%  {texto.moeda(oferta['preco']):>12}  "
              f"[{oferta['loja']}] {texto.titulo_curto(oferta['titulo'], 70)}")


def trocar_codigo_ml(cfg, codigo):
    resposta = requests.post("https://api.mercadolibre.com/oauth/token", timeout=30, data={
        "grant_type": "authorization_code",
        "client_id": cfg.ml_client_id,
        "client_secret": cfg.ml_client_secret,
        "code": codigo,
        "redirect_uri": cfg.ml_redirect_uri,
    })
    resposta.raise_for_status()
    print("Coloque no .env:\nML_REFRESH_TOKEN=" + resposta.json()["refresh_token"])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    cfg = Config()
    comando = sys.argv[1] if len(sys.argv) > 1 else "rodar"

    if comando == "ml-token":
        trocar_codigo_ml(cfg, sys.argv[2])
        return
    if not cfg.telegram_token or not cfg.telegram_canal:
        sys.exit("Preencha TELEGRAM_TOKEN e TELEGRAM_CANAL no arquivo .env")

    app = App(cfg)
    if comando == "rodar":
        rodar(app, cfg)
    elif comando == "coletar":
        mostrar_ranking(app, cfg)
    elif comando == "teste-telegram":
        app.coletar()
        oferta = app.postar_telegram(forcar=True)
        print("Postado:" if oferta else "Nenhuma oferta passou no filtro.", oferta and oferta["titulo"])
    elif comando == "teste-whatsapp":
        cfg.whatsapp_atraso_min = 0
        oferta = app.postar_whatsapp()
        print("Enviado:" if oferta else "Nada enviado (WhatsApp desligado ou nada postado no Telegram nas "
                                        "últimas 24h).", oferta and oferta["titulo"])
    elif comando == "teste-video":
        app.coletar()
        app.enviar_novo_video()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
