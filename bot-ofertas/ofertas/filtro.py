"""Decide quais ofertas valem a pena e em que ordem postar."""
import math
from datetime import datetime, timedelta
from statistics import median

DIAS_MINIMOS_HISTORICO = 3


def _data(texto):
    return datetime.fromisoformat(texto) if texto else None


def queda_no_historico(banco, oferta, momento):
    """% abaixo do preço mediano dos últimos 30 dias, ou None se ainda não há histórico suficiente."""
    precos = banco.precos_por_dia(oferta["id"], dias=30, antes_de=momento)
    if len(precos) < DIAS_MINIMOS_HISTORICO:
        return None
    referencia = median(precos)
    return (referencia - oferta["preco"]) / referencia * 100


def avaliar(banco, cfg, oferta, momento):
    """Retorna (aprovada, motivo, queda_historico)."""
    if oferta["preco"] < cfg.preco_minimo:
        return False, "preço abaixo do mínimo", None
    if oferta["desconto"] < cfg.desconto_minimo:
        return False, "desconto pequeno", None
    if oferta["nota"] and oferta["nota"] < cfg.nota_minima:
        return False, "nota baixa", None

    postada = _data(oferta["telegram_em"])
    if postada and momento - postada < timedelta(days=cfg.dias_sem_repetir):
        # Só repete dentro do prazo se o preço caiu de novo pelo menos 5%.
        if not oferta["telegram_preco"] or oferta["preco"] > oferta["telegram_preco"] * 0.95:
            return False, "postada recentemente", None

    queda = queda_no_historico(banco, oferta, momento)
    if queda is not None and queda < cfg.queda_minima_historico:
        # A loja diz que tem desconto, mas o preço é o mesmo de sempre.
        return False, "desconto falso (preço normal no histórico)", queda
    return True, "ok", queda


def pontuacao(oferta, queda=None):
    vendas = oferta["vendas"] or 0
    nota = oferta["nota"] / 5 if oferta["nota"] else 0.9
    pontos = oferta["desconto"] * (1 + math.log10(1 + vendas)) * nota
    if queda:
        pontos *= 1 + queda / 100
    return pontos


def ranking(banco, cfg, momento, horas=6, filtro_extra=None):
    candidatas = []
    for oferta in banco.ofertas_recentes(horas=horas):
        if filtro_extra and not filtro_extra(oferta):
            continue
        aprovada, _, queda = avaliar(banco, cfg, oferta, momento)
        if aprovada:
            candidatas.append((pontuacao(oferta, queda), oferta))
    candidatas.sort(key=lambda par: par[0], reverse=True)
    return [oferta for _, oferta in candidatas]


def proxima_para_telegram(banco, cfg, momento):
    melhores = ranking(banco, cfg, momento)
    return melhores[0] if melhores else None


def melhores_para_video(banco, cfg, momento, quantidade, ignorar=()):
    def sem_video_recente(oferta):
        if oferta["id"] in ignorar or not oferta["imagem"]:
            return False
        feito = _data(oferta["video_em"])
        return not feito or momento - feito > timedelta(days=14)

    return ranking(banco, cfg, momento, horas=24, filtro_extra=sem_video_recente)[:quantidade]
