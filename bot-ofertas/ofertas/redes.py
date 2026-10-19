"""Publicação automática dos vídeos aprovados no Instagram (Reels) e no YouTube (Shorts)."""
import logging
import time

import requests

log = logging.getLogger(__name__)


def publicar_reels(cfg, caminho, legenda):
    """Envia o vídeo direto para a Graph API (upload resumível), sem precisar hospedá-lo."""
    base = f"https://graph.facebook.com/{cfg.graph_versao}"
    criacao = requests.post(f"{base}/{cfg.instagram_id}/media", timeout=60, data={
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": legenda,
        "share_to_feed": "true",
        "access_token": cfg.instagram_token,
    })
    criacao.raise_for_status()
    container = criacao.json()["id"]

    dados = caminho.read_bytes()
    envio = requests.post(
        f"https://rupload.facebook.com/ig-api-upload/{cfg.graph_versao}/{container}", timeout=300,
        headers={"Authorization": f"OAuth {cfg.instagram_token}", "offset": "0",
                 "file_size": str(len(dados))},
        data=dados,
    )
    envio.raise_for_status()

    for _ in range(60):  # o Instagram processa o vídeo antes de deixar publicar
        status = requests.get(f"{base}/{container}", timeout=30, params={
            "fields": "status_code", "access_token": cfg.instagram_token}).json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram não conseguiu processar o vídeo")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram demorou demais para processar o vídeo")

    publicado = requests.post(f"{base}/{cfg.instagram_id}/media_publish", timeout=60, data={
        "creation_id": container, "access_token": cfg.instagram_token})
    publicado.raise_for_status()
    return publicado.json()["id"]


def publicar_shorts(cfg, caminho, titulo, legenda):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credenciais = Credentials(
        None,
        refresh_token=cfg.youtube_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg.youtube_client_id,
        client_secret=cfg.youtube_client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=credenciais, cache_discovery=False)
    pedido = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": f"{titulo[:88]} #Shorts", "description": legenda, "categoryId": "26"},
            "status": {"privacyStatus": cfg.youtube_privacidade, "selfDeclaredMadeForKids": False},
        },
        media_body=MediaFileUpload(str(caminho), mimetype="video/mp4", resumable=True),
    )
    resposta = None
    while resposta is None:
        _, resposta = pedido.next_chunk()
    return resposta["id"]
