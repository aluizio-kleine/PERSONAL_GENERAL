import hashlib
from datetime import datetime, timedelta

import pytest

from ofertas import filtro, texto
from ofertas.config import Config
from ofertas.db import Banco, Oferta
from ofertas.fontes import shopee
from ofertas.fontes.mercadolivre import MercadoLivre

AGORA = datetime(2026, 10, 19, 12, 0, 0)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for chave in ("DESCONTO_MINIMO", "PRECO_MINIMO", "NOTA_MINIMA", "QUEDA_MINIMA_HISTORICO",
                  "DIAS_SEM_REPETIR", "ML_PARAMETROS_AFILIADO", "LINK_TELEGRAM"):
        monkeypatch.delenv(chave, raising=False)
    config = Config()
    config.pasta_dados = tmp_path
    config.link_telegram = "https://t.me/canal"
    return config


@pytest.fixture
def banco(cfg):
    return Banco(cfg.caminho_banco)


def oferta(**campos):
    padrao = dict(id="shopee:1", loja="shopee", titulo="Air Fryer Mondial 4L", link="https://s.shopee.com.br/x",
                  imagem="https://img/1.jpg", preco=189.9, preco_antigo=399.9, desconto=52.5, nota=4.8,
                  vendas=1200, palavra_chave="air fryer")
    padrao.update(campos)
    return Oferta(**padrao)


def salvar(banco, item, momento=AGORA):
    banco.salvar_oferta(item, momento)
    return banco.oferta(item.id)


# --- filtro -----------------------------------------------------------------

def test_oferta_boa_sem_historico_e_aprovada(banco, cfg):
    linha = salvar(banco, oferta())
    assert filtro.avaliar(banco, cfg, linha, AGORA)[:2] == (True, "ok")


@pytest.mark.parametrize("campos, motivo", [
    ({"desconto": 10}, "desconto pequeno"),
    ({"preco": 9.9}, "preço abaixo do mínimo"),
    ({"nota": 3.9}, "nota baixa"),
])
def test_rejeita_ofertas_fracas(banco, cfg, campos, motivo):
    linha = salvar(banco, oferta(**campos))
    assert filtro.avaliar(banco, cfg, linha, AGORA)[:2] == (False, motivo)


def test_detecta_desconto_falso_pelo_historico(banco, cfg):
    # Mesmo preço há 5 dias, sempre anunciado com "52% OFF".
    for dias in range(5, 0, -1):
        banco.salvar_oferta(oferta(), AGORA - timedelta(days=dias))
    linha = salvar(banco, oferta())
    aprovada, motivo, queda = filtro.avaliar(banco, cfg, linha, AGORA)
    assert not aprovada and "falso" in motivo and queda == 0


def test_aprova_queda_real_no_historico(banco, cfg):
    for dias in range(5, 0, -1):
        banco.salvar_oferta(oferta(preco=299.9), AGORA - timedelta(days=dias))
    linha = salvar(banco, oferta(preco=189.9))
    aprovada, _, queda = filtro.avaliar(banco, cfg, linha, AGORA)
    assert aprovada and queda == pytest.approx(36.7, abs=0.1)


def test_nao_repete_oferta_recente_salvo_nova_queda(banco, cfg):
    salvar(banco, oferta())
    banco.marcar("shopee:1", "telegram_em", AGORA - timedelta(days=2), preco=189.9)
    assert filtro.avaliar(banco, cfg, banco.oferta("shopee:1"), AGORA)[1] == "postada recentemente"

    linha = salvar(banco, oferta(preco=169.9))
    assert filtro.avaliar(banco, cfg, linha, AGORA)[0]


def test_ranking_prefere_maior_desconto_e_mais_vendas(banco, cfg):
    salvar(banco, oferta(id="shopee:1", desconto=25, vendas=10))
    salvar(banco, oferta(id="shopee:2", desconto=50, vendas=5000))
    salvar(banco, oferta(id="shopee:3", desconto=5))
    ids = [linha["id"] for linha in filtro.ranking(banco, cfg, AGORA)]
    assert ids == ["shopee:2", "shopee:1"]


def test_video_nao_repete_oferta(banco, cfg):
    salvar(banco, oferta(id="shopee:1"))
    salvar(banco, oferta(id="shopee:2", desconto=30))
    banco.marcar("shopee:1", "video_em", AGORA - timedelta(hours=1))
    escolhidas = filtro.melhores_para_video(banco, cfg, AGORA, 5)
    assert [linha["id"] for linha in escolhidas] == ["shopee:2"]


def test_whatsapp_so_pega_o_que_saiu_no_telegram_com_atraso(banco, cfg):
    salvar(banco, oferta(id="shopee:1"))
    salvar(banco, oferta(id="shopee:2"))
    banco.marcar("shopee:1", "telegram_em", AGORA - timedelta(hours=2))
    banco.marcar("shopee:2", "telegram_em", AGORA - timedelta(minutes=10))
    linhas = banco.postadas_no_telegram(AGORA - timedelta(hours=24), AGORA - timedelta(hours=1))
    assert [linha["id"] for linha in linhas] == ["shopee:1"]


# --- textos -----------------------------------------------------------------

def test_moeda_e_preco_falado():
    assert texto.moeda(1299.9) == "R$ 1.299,90"
    assert texto.preco_falado(189.9) == "189 reais e 90 centavos"
    assert texto.preco_falado(1.0) == "1 real"
    assert texto.preco_falado(99.999) == "100 reais"


def test_titulo_curto_limpa_lixo_de_marketplace():
    assert texto.titulo_curto("Air Fryer Mondial 4L | Frete Grátis | Original") == "Air Fryer Mondial 4L"
    longo = texto.titulo_curto("Liquidificador " + "Potente " * 20, 40)
    assert len(longo) <= 41 and longo.endswith("…")


def test_mensagens(banco, cfg):
    linha = salvar(banco, oferta(titulo="Air Fryer <Promo> & Cia"))
    telegram = texto.mensagem_telegram(linha)
    assert "&lt;Promo&gt; &amp; Cia" in telegram and "<s>R$ 399,90</s>" in telegram
    assert "52% OFF" in telegram and "Link de afiliado" in telegram

    whatsapp = texto.mensagem_whatsapp(linha, cfg)
    assert "~R$ 399,90~" in whatsapp and "https://t.me/canal" in whatsapp

    roteiro = texto.roteiro_video(linha)
    assert "399 reais e 90 centavos" in roteiro and "189 reais e 90 centavos" in roteiro
    assert "#achadinhos" in texto.legenda_video(linha, cfg)


# --- fontes -----------------------------------------------------------------

def test_shopee_converte_item_da_api():
    item = {"itemId": 99, "productName": " Cafeteira Arno ", "price": "149.9", "priceMin": "139.9",
            "priceDiscountRate": 30, "imageUrl": "https://img", "offerLink": "https://s.shopee.com.br/a",
            "sales": 321, "ratingStar": "4.7"}
    convertida = shopee.converter(item, "cafeteira")
    assert convertida.id == "shopee:99" and convertida.titulo == "Cafeteira Arno"
    assert convertida.preco == 139.9 and convertida.preco_antigo == pytest.approx(199.86, abs=0.01)
    assert convertida.nota == 4.7 and convertida.vendas == 321


def test_shopee_ignora_item_sem_link_e_nota_zero():
    assert shopee.converter({"itemId": 1, "price": "10"}, "x") is None
    item = {"itemId": 2, "price": "50", "offerLink": "https://l", "ratingStar": "0"}
    assert shopee.converter(item, "x").nota is None


def test_shopee_assinatura_segue_o_formato_da_api():
    # Assinatura = sha256(AppId + Timestamp + Payload + Secret)
    esperado = hashlib.sha256(b"app1700000000{}segredo").hexdigest()
    assert shopee._assinatura("app", "segredo", "{}", 1700000000) == esperado


def test_mercado_livre_converte_e_monta_link_de_afiliado(cfg, banco):
    cfg.ml_parametros_afiliado = "?matt_tool=123&matt_word=eu"
    ml = MercadoLivre(cfg, banco)
    item = {"id": "MLB1", "title": "Micro-ondas", "price": 450, "original_price": 600,
            "thumbnail": "http://http2.mlstatic.com/D_1-I.jpg", "permalink": "https://produto.mercadolivre.com.br/MLB-1"}
    convertida = ml.converter(item, "micro-ondas")
    assert convertida.link == "https://produto.mercadolivre.com.br/MLB-1?matt_tool=123&matt_word=eu"
    assert convertida.imagem == "https://http2.mlstatic.com/D_1-O.jpg"
    assert convertida.desconto == 25.0
    assert ml.converter({**item, "original_price": None}, "x") is None
