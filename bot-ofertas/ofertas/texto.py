"""Textos das postagens, do roteiro narrado e das legendas dos vídeos."""
import html
import random
import re

NOMES_LOJA = {"shopee": "Shopee", "ml": "Mercado Livre"}

GANCHOS = [
    "Olha esse preço!",
    "Corre que baixou!",
    "Achei essa promoção absurda!",
    "Para tudo e olha isso!",
    "Esse preço não vai durar!",
]

GANCHOS_TELA = ["BAIXOU O PREÇO!", "CORRE QUE BAIXOU!", "PROMOÇÃO ABSURDA!", "OLHA ESSE PREÇO!"]


def moeda(valor):
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def preco_falado(valor):
    reais = int(valor)
    centavos = round((valor - reais) * 100)
    if centavos == 100:
        reais, centavos = reais + 1, 0
    texto = f"{reais} reais" if reais != 1 else "1 real"
    if centavos:
        texto += f" e {centavos} centavos"
    return texto


def titulo_curto(titulo, limite=60):
    # Títulos de marketplace vêm cheios de lixo: corta em separadores e no limite de caracteres.
    titulo = re.split(r"\s[|/–-]\s|【|\[", titulo)[0].strip()
    titulo = re.sub(r"\s+", " ", titulo)
    if len(titulo) <= limite:
        return titulo
    cortado = titulo[:limite].rsplit(" ", 1)[0]
    return cortado.rstrip(",.;:-") + "…"


def _linha_preco(oferta, negrito, riscado):
    novo = negrito(moeda(oferta["preco"]))
    if oferta["preco_antigo"] and oferta["preco_antigo"] > oferta["preco"]:
        return f"💰 De {riscado(moeda(oferta['preco_antigo']))} por {novo} ({oferta['desconto']:.0f}% OFF)"
    return f"💰 Por {novo}"


def mensagem_telegram(oferta):
    loja = NOMES_LOJA.get(oferta["loja"], oferta["loja"])
    linhas = [
        f"🔥 <b>{html.escape(titulo_curto(oferta['titulo'], 120))}</b>",
        "",
        _linha_preco(oferta, lambda t: f"<b>{t}</b>", lambda t: f"<s>{t}</s>"),
    ]
    if oferta["nota"]:
        linhas.append(f"⭐ {oferta['nota']:.1f}" + (f" · {oferta['vendas']} vendidos" if oferta["vendas"] else ""))
    linhas += [
        f"🛒 {loja}: {html.escape(oferta['link'])}",
        "",
        "<i>Preço sujeito a alteração. Link de afiliado.</i>",
    ]
    return "\n".join(linhas)


def mensagem_whatsapp(oferta, cfg):
    linhas = [
        f"🔥 *{titulo_curto(oferta['titulo'], 120)}*",
        "",
        _linha_preco(oferta, lambda t: f"*{t}*", lambda t: f"~{t}~"),
        f"🛒 {oferta['link']}",
        "",
        "_Preço sujeito a alteração. Link de afiliado._",
    ]
    if cfg.link_telegram:
        linhas += ["", f"⚡ Ofertas relâmpago saem primeiro no Telegram 👉 {cfg.link_telegram}"]
    return "\n".join(linhas)


def roteiro_video(oferta, aleatorio=random):
    nome = titulo_curto(oferta["titulo"], 45).rstrip("…")
    partes = [aleatorio.choice(GANCHOS)]
    if oferta["preco_antigo"] and oferta["preco_antigo"] > oferta["preco"]:
        partes.append(f"{nome}, de {preco_falado(oferta['preco_antigo'])} "
                      f"por só {preco_falado(oferta['preco'])}.")
        partes.append(f"São {oferta['desconto']:.0f} por cento de desconto.")
    else:
        partes.append(f"{nome} por só {preco_falado(oferta['preco'])}.")
    partes.append("O link tá no meu perfil. Corre antes que acabe!")
    return " ".join(partes)


def legenda_video(oferta, cfg):
    linhas = [
        f"🔥 {titulo_curto(oferta['titulo'], 80)}",
        _linha_preco(oferta, lambda t: t, lambda t: t),
        "",
        "🔗 Link na bio! Todo dia tem oferta nova de eletro.",
        "Preço sujeito a alteração.",
        "",
        cfg.hashtags,
    ]
    return "\n".join(linhas)
