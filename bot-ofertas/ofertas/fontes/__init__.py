"""Coleta de ofertas em todas as lojas configuradas."""
import logging
import time

from . import shopee
from .mercadolivre import MercadoLivre

log = logging.getLogger(__name__)


class Coletor:
    def __init__(self, cfg, banco):
        self.cfg = cfg
        self.banco = banco
        self.lojas = []
        if cfg.shopee_ativa:
            self.lojas.append(("Shopee", lambda palavra: shopee.buscar(cfg, palavra)))
        if cfg.ml_ativo:
            self.lojas.append(("Mercado Livre", MercadoLivre(cfg, banco).buscar))
        if not self.lojas:
            log.warning("Nenhuma loja configurada: preencha as chaves da Shopee e/ou do Mercado Livre no .env")

    def coletar(self):
        total = 0
        for nome, buscar in self.lojas:
            for palavra in self.cfg.palavras_chave:
                try:
                    ofertas = buscar(palavra)
                except Exception as erro:  # uma loja fora do ar não pode parar as outras
                    log.warning("%s / %s: %s", nome, palavra, erro)
                    continue
                for oferta in ofertas:
                    self.banco.salvar_oferta(oferta)
                total += len(ofertas)
                time.sleep(1)
        log.info("Coleta concluída: %d ofertas vistas", total)
        return total
