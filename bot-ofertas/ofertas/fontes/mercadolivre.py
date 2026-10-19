"""Ofertas do Mercado Livre pela API oficial.

Precisa de um app criado em developers.mercadolivre.com.br (client id/secret) e de um
refresh token. O link de afiliado é montado acrescentando ao link do produto os
parâmetros do seu "Gerador de links" do Programa de Afiliados (ML_PARAMETROS_AFILIADO).
"""
import logging
import time

import requests

from ..db import Oferta

log = logging.getLogger(__name__)

API = "https://api.mercadolibre.com"


class MercadoLivre:
    def __init__(self, cfg, banco):
        self.cfg = cfg
        self.banco = banco
        self._token = None
        self._expira = 0

    def _access_token(self):
        if self._token and time.time() < self._expira - 60:
            return self._token
        # O ML troca o refresh token a cada uso; o mais novo fica guardado no banco.
        refresh = self.banco.ler_estado("ml_refresh_token") or self.cfg.ml_refresh_token
        resposta = requests.post(f"{API}/oauth/token", timeout=30, data={
            "grant_type": "refresh_token",
            "client_id": self.cfg.ml_client_id,
            "client_secret": self.cfg.ml_client_secret,
            "refresh_token": refresh,
        })
        resposta.raise_for_status()
        dados = resposta.json()
        self._token = dados["access_token"]
        self._expira = time.time() + dados.get("expires_in", 21600)
        if dados.get("refresh_token"):
            self.banco.gravar_estado("ml_refresh_token", dados["refresh_token"])
        return self._token

    def link_afiliado(self, permalink):
        parametros = self.cfg.ml_parametros_afiliado.lstrip("?&")
        if not parametros:
            return permalink
        separador = "&" if "?" in permalink else "?"
        return f"{permalink}{separador}{parametros}"

    def converter(self, item, palavra_chave):
        preco = item.get("price")
        antigo = item.get("original_price")
        if not preco or not antigo or antigo <= preco:
            return None
        imagem = (item.get("thumbnail") or "").replace("http://", "https://")
        imagem = imagem.replace("-I.jpg", "-O.jpg")  # versão maior da foto
        return Oferta(
            id=f"ml:{item['id']}",
            loja="ml",
            titulo=item.get("title", "").strip(),
            link=self.link_afiliado(item["permalink"]),
            imagem=imagem,
            preco=float(preco),
            preco_antigo=float(antigo),
            desconto=round((antigo - preco) / antigo * 100, 1),
            vendas=item.get("sold_quantity"),
            palavra_chave=palavra_chave,
        )

    def buscar(self, palavra_chave, limite=30):
        resposta = requests.get(
            f"{API}/sites/MLB/search", timeout=30,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            params={"q": palavra_chave, "limit": limite,
                    **({"category": self.cfg.ml_categoria} if self.cfg.ml_categoria else {})},
        )
        if resposta.status_code == 403:
            raise RuntimeError("Mercado Livre recusou a busca (403). O app pode não ter acesso "
                               "à busca pública; veja a seção do Mercado Livre no README.")
        resposta.raise_for_status()
        itens = resposta.json().get("results", [])
        return [o for o in (self.converter(item, palavra_chave) for item in itens) if o]
