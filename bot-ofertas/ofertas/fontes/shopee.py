"""Ofertas da Shopee pela API de Afiliados (GraphQL).

O acesso à API é liberado no painel do Shopee Afiliados (menu "Open API").
"""
import hashlib
import json
import logging
import time

import requests

from ..db import Oferta

log = logging.getLogger(__name__)

URL = "https://open-api.affiliate.shopee.com.br/graphql"

CONSULTA = """
query {
  productOfferV2(keyword: %s, sortType: 2, page: 1, limit: %d) {
    nodes {
      itemId productName price priceMin priceDiscountRate imageUrl offerLink sales ratingStar
    }
  }
}
"""


def _assinatura(app_id, secret, payload, timestamp):
    base = f"{app_id}{timestamp}{payload}{secret}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def converter(item, palavra_chave):
    preco = _numero(item.get("priceMin")) or _numero(item.get("price"))
    desconto = _numero(item.get("priceDiscountRate")) or 0
    if not preco or not item.get("offerLink"):
        return None
    preco_antigo = round(preco / (1 - desconto / 100), 2) if 0 < desconto < 100 else None
    nota = _numero(item.get("ratingStar")) or None
    return Oferta(
        id=f"shopee:{item['itemId']}",
        loja="shopee",
        titulo=item.get("productName", "").strip(),
        link=item["offerLink"],
        imagem=item.get("imageUrl") or "",
        preco=preco,
        preco_antigo=preco_antigo,
        desconto=desconto,
        nota=nota,
        vendas=int(_numero(item.get("sales")) or 0),
        palavra_chave=palavra_chave,
    )


def buscar(cfg, palavra_chave, limite=30):
    payload = json.dumps({"query": CONSULTA % (json.dumps(palavra_chave, ensure_ascii=False), limite)},
                         ensure_ascii=False)
    timestamp = int(time.time())
    cabecalho = (f"SHA256 Credential={cfg.shopee_app_id}, Timestamp={timestamp}, "
                 f"Signature={_assinatura(cfg.shopee_app_id, cfg.shopee_secret, payload, timestamp)}")
    resposta = requests.post(URL, data=payload.encode("utf-8"), timeout=30,
                             headers={"Authorization": cabecalho, "Content-Type": "application/json"})
    resposta.raise_for_status()
    corpo = resposta.json()
    if corpo.get("errors"):
        raise RuntimeError(f"Shopee: {corpo['errors']}")
    itens = corpo["data"]["productOfferV2"]["nodes"]
    return [o for o in (converter(item, palavra_chave) for item in itens) if o]
