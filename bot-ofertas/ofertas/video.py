"""Gera o vídeo vertical (1080x1920) de uma oferta: 3 telas com zoom suave + narração."""
import io
import json
import logging
import random
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import texto, voz

log = logging.getLogger(__name__)

LARGURA, ALTURA = 1080, 1920
FPS = 30
MARGEM = 90  # a interface do TikTok/Reels cobre as bordas; o conteúdo fica no centro

AMARELO = (255, 214, 10)
VERDE = (46, 229, 157)
VERMELHO = (230, 57, 70)
BRANCO = (255, 255, 255)
CINZA = (190, 196, 210)
ESCURO = (16, 19, 28)

FONTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def fonte(tamanho):
    for caminho in FONTES:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default(tamanho)


def baixar_imagem(url):
    resposta = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resposta.raise_for_status()
    return Image.open(io.BytesIO(resposta.content)).convert("RGB")


# --- desenho -----------------------------------------------------------------

def _fundo(produto):
    escala = max(LARGURA / produto.width, ALTURA / produto.height)
    fundo = produto.resize((int(produto.width * escala) + 1, int(produto.height * escala) + 1))
    esquerda, topo = (fundo.width - LARGURA) // 2, (fundo.height - ALTURA) // 2
    fundo = fundo.crop((esquerda, topo, esquerda + LARGURA, topo + ALTURA))
    fundo = fundo.filter(ImageFilter.GaussianBlur(40))
    return ImageEnhance.Brightness(fundo).enhance(0.35)


def _colar_cartao(tela, produto, lado, topo):
    """Produto inteiro dentro de um cartão branco de cantos arredondados, centralizado."""
    cartao = Image.new("RGB", (lado, lado), BRANCO)
    miolo = produto.copy()
    miolo.thumbnail((lado - 60, lado - 60))
    cartao.paste(miolo, ((lado - miolo.width) // 2, (lado - miolo.height) // 2))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, lado, lado), radius=48, fill=255)
    tela.paste(cartao, ((LARGURA - lado) // 2, topo), mascara)
    return topo + lado


def _quebrar(desenho, frase, fonte_, largura_max):
    linhas, atual = [], ""
    for palavra in frase.split():
        teste = f"{atual} {palavra}".strip()
        if desenho.textlength(teste, font=fonte_) <= largura_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _fonte_que_cabe(desenho, frase, tamanho, largura_max):
    while tamanho > 30 and desenho.textlength(frase, font=fonte(tamanho)) > largura_max:
        tamanho -= 4
    return fonte(tamanho)


def _centralizado(desenho, topo, frase, fonte_, cor, largura_max=LARGURA - 2 * MARGEM,
                  max_linhas=3, espaco=14):
    linhas = _quebrar(desenho, frase, fonte_, largura_max)[:max_linhas]
    for linha in linhas:
        caixa = desenho.textbbox((0, 0), linha, font=fonte_)
        desenho.text(((LARGURA - (caixa[2] - caixa[0])) / 2, topo), linha, font=fonte_, fill=cor)
        topo += caixa[3] + espaco
    return topo


def _faixa(desenho, topo, frase, fonte_, cor_fundo, cor_texto):
    caixa = desenho.textbbox((0, 0), frase, font=fonte_)
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    x = (LARGURA - largura) / 2
    desenho.rounded_rectangle((x - 40, topo - 20, x + largura + 40, topo + altura + 36),
                              radius=30, fill=cor_fundo)
    desenho.text((x, topo - caixa[1] + 8), frase, font=fonte_, fill=cor_texto)
    return topo + altura + 36


def tela_gancho(produto, oferta, gancho):
    tela = _fundo(produto)
    desenho = ImageDraw.Draw(tela)
    _faixa(desenho, 230, gancho, _fonte_que_cabe(desenho, gancho, 84, LARGURA - 2 * MARGEM - 80),
           AMARELO, ESCURO)
    fim = _colar_cartao(tela, produto, 820, 420)
    _centralizado(desenho, fim + 50, texto.titulo_curto(oferta["titulo"], 70), fonte(54), BRANCO)
    return tela


def tela_preco(produto, oferta):
    tela = _fundo(produto)
    desenho = ImageDraw.Draw(tela)
    fim = _colar_cartao(tela, produto, 620, 250)

    if oferta["desconto"]:
        selo = f"-{oferta['desconto']:.0f}%"
        centro_x, centro_y, raio = LARGURA // 2 + 300, 270, 115
        desenho.ellipse((centro_x - raio, centro_y - raio, centro_x + raio, centro_y + raio), fill=VERMELHO)
        fonte_selo = _fonte_que_cabe(desenho, selo, 78, raio * 2 - 30)
        desenho.text((centro_x, centro_y), selo, font=fonte_selo, fill=BRANCO, anchor="mm")

    topo = fim + 80
    if oferta["preco_antigo"] and oferta["preco_antigo"] > oferta["preco"]:
        antigo = f"DE {texto.moeda(oferta['preco_antigo'])}"
        fonte_antigo = fonte(64)
        caixa = desenho.textbbox((0, 0), antigo, font=fonte_antigo)
        x = (LARGURA - caixa[2]) / 2
        desenho.text((x, topo), antigo, font=fonte_antigo, fill=CINZA)
        meio = topo + caixa[3] * 0.6
        desenho.line((x - 10, meio, x + caixa[2] + 10, meio), fill=VERMELHO, width=8)
        topo += caixa[3] + 40
        topo = _centralizado(desenho, topo, "POR", fonte(60), BRANCO)

    novo = texto.moeda(oferta["preco"])
    topo = _centralizado(desenho, topo, novo, _fonte_que_cabe(desenho, novo, 160, LARGURA - 2 * MARGEM),
                         VERDE, max_linhas=1)
    loja = texto.NOMES_LOJA.get(oferta["loja"], oferta["loja"])
    _faixa(desenho, topo + 40, f"na {loja}", fonte(50), BRANCO, ESCURO)
    return tela


def tela_chamada(produto, nome_canal):
    tela = _fundo(produto)
    desenho = ImageDraw.Draw(tela)
    fim = _colar_cartao(tela, produto, 500, 300)
    topo = _centralizado(desenho, fim + 110, "↑ LINK NA BIO ↑", _fonte_que_cabe(
        desenho, "↑ LINK NA BIO ↑", 120, LARGURA - 2 * MARGEM), AMARELO, max_linhas=1)
    topo = _centralizado(desenho, topo + 50, nome_canal, fonte(64), BRANCO)
    _centralizado(desenho, topo + 20, "Eletro com desconto todo dia", fonte(46), CINZA)
    return tela


# --- montagem ----------------------------------------------------------------

def duracao_audio(caminho):
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(caminho)],
        capture_output=True, text=True, check=True)
    return float(json.loads(saida.stdout)["format"]["duration"])


def montar(telas, audio, destino, musica=None):
    total = duracao_audio(audio) + 0.8
    duracoes = [total * 0.30, total * 0.45]
    duracoes.append(total - sum(duracoes))

    comando = ["ffmpeg", "-y", "-loglevel", "error"]
    for tela in telas:
        comando += ["-i", str(tela)]
    comando += ["-i", str(audio)]
    if musica:
        comando += ["-stream_loop", "-1", "-i", str(musica)]

    filtros = []
    for i, duracao in enumerate(duracoes):
        quadros = round(duracao * FPS)
        filtros.append(
            f"[{i}:v]scale={LARGURA * 3 // 2}:{ALTURA * 3 // 2},"
            f"zoompan=z='min(zoom+0.0007,1.08)':d={quadros}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={LARGURA}x{ALTURA}:fps={FPS},setsar=1[v{i}]")
    filtros.append("[v0][v1][v2]concat=n=3:v=1:a=0,format=yuv420p[v]")
    indice_voz = len(telas)
    if musica:
        filtros.append(f"[{indice_voz}:a]apad[voz];[{indice_voz + 1}:a]volume=0.12[fundo];"
                       "[voz][fundo]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        filtros.append(f"[{indice_voz}:a]apad[a]")

    comando += [
        "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(destino),
    ]
    subprocess.run(comando, check=True)
    return destino


def gerar_video(cfg, oferta, produto=None, narrador=voz.narrar):
    """Cria o MP4 da oferta e devolve (caminho, legenda)."""
    cfg.pasta_videos.mkdir(parents=True, exist_ok=True)
    produto = produto or baixar_imagem(oferta["imagem"])
    nome_arquivo = oferta["id"].replace(":", "_")
    destino = cfg.pasta_videos / f"{nome_arquivo}.mp4"

    with tempfile.TemporaryDirectory() as temporaria:
        temporaria = Path(temporaria)
        telas = []
        for i, imagem in enumerate([
            tela_gancho(produto, oferta, random.choice(texto.GANCHOS_TELA)),
            tela_preco(produto, oferta),
            tela_chamada(produto, cfg.nome_canal),
        ]):
            caminho = temporaria / f"tela{i}.png"
            imagem.save(caminho)
            telas.append(caminho)
        audio = narrador(cfg, texto.roteiro_video(oferta), temporaria / "voz.mp3")
        musica = cfg.musica_fundo if cfg.musica_fundo and Path(cfg.musica_fundo).exists() else None
        montar(telas, audio, destino, musica)

    log.info("Vídeo gerado: %s", destino)
    return destino, texto.legenda_video(oferta, cfg)
