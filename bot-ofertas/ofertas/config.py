"""Configuração lida das variáveis de ambiente (arquivo .env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PALAVRAS_PADRAO = [
    "air fryer", "fritadeira elétrica", "liquidificador", "batedeira", "cafeteira",
    "micro-ondas", "aspirador de pó", "robô aspirador", "ventilador", "ferro de passar",
    "mixer", "sanduicheira", "panela elétrica", "processador de alimentos",
    "purificador de água", "forno elétrico", "geladeira", "máquina de lavar",
]


def _texto(nome, padrao=""):
    return os.getenv(nome, padrao).strip()


def _inteiro(nome, padrao):
    valor = _texto(nome)
    return int(valor) if valor else padrao


def _decimal(nome, padrao):
    valor = _texto(nome)
    return float(valor) if valor else padrao


def _booleano(nome, padrao=False):
    valor = _texto(nome).lower()
    if not valor:
        return padrao
    return valor in ("1", "true", "sim", "yes", "on")


def _lista(nome, padrao):
    valor = _texto(nome)
    if not valor:
        return list(padrao)
    return [item.strip() for item in valor.split(",") if item.strip()]


def _horarios(nome, padrao):
    """'07:00,12:00,19:00' -> [(7, 0), (12, 0), (19, 0)]"""
    resultado = []
    for item in _lista(nome, padrao):
        hora, _, minuto = item.partition(":")
        resultado.append((int(hora), int(minuto or 0)))
    return resultado


@dataclass
class Config:
    # Canal
    nome_canal: str = field(default_factory=lambda: _texto("NOME_CANAL", "Ofertas de Eletro"))
    link_telegram: str = field(default_factory=lambda: _texto("LINK_TELEGRAM"))
    fuso: str = field(default_factory=lambda: _texto("FUSO", "America/Sao_Paulo"))
    pasta_dados: Path = field(default_factory=lambda: Path(_texto("PASTA_DADOS", "dados")))

    # Telegram
    telegram_token: str = field(default_factory=lambda: _texto("TELEGRAM_TOKEN"))
    telegram_canal: str = field(default_factory=lambda: _texto("TELEGRAM_CANAL"))
    telegram_admin: str = field(default_factory=lambda: _texto("TELEGRAM_ADMIN_ID"))
    intervalo_telegram_min: int = field(default_factory=lambda: _inteiro("INTERVALO_TELEGRAM_MIN", 20))

    # Horário de funcionamento das postagens (silêncio fora dele)
    hora_inicio: int = field(default_factory=lambda: _inteiro("HORA_INICIO", 8))
    hora_fim: int = field(default_factory=lambda: _inteiro("HORA_FIM", 23))

    # Coleta e filtro
    palavras_chave: list = field(default_factory=lambda: _lista("PALAVRAS_CHAVE", PALAVRAS_PADRAO))
    intervalo_coleta_min: int = field(default_factory=lambda: _inteiro("INTERVALO_COLETA_MIN", 30))
    desconto_minimo: float = field(default_factory=lambda: _decimal("DESCONTO_MINIMO", 20))
    preco_minimo: float = field(default_factory=lambda: _decimal("PRECO_MINIMO", 30))
    nota_minima: float = field(default_factory=lambda: _decimal("NOTA_MINIMA", 4.5))
    queda_minima_historico: float = field(default_factory=lambda: _decimal("QUEDA_MINIMA_HISTORICO", 8))
    dias_sem_repetir: int = field(default_factory=lambda: _inteiro("DIAS_SEM_REPETIR", 7))

    # Shopee
    shopee_app_id: str = field(default_factory=lambda: _texto("SHOPEE_APP_ID"))
    shopee_secret: str = field(default_factory=lambda: _texto("SHOPEE_SECRET"))

    # Mercado Livre
    ml_client_id: str = field(default_factory=lambda: _texto("ML_CLIENT_ID"))
    ml_client_secret: str = field(default_factory=lambda: _texto("ML_CLIENT_SECRET"))
    ml_redirect_uri: str = field(default_factory=lambda: _texto("ML_REDIRECT_URI", "https://www.google.com"))
    ml_refresh_token: str = field(default_factory=lambda: _texto("ML_REFRESH_TOKEN"))
    ml_categoria: str = field(default_factory=lambda: _texto("ML_CATEGORIA", "MLB5726"))  # Eletrodomésticos
    ml_parametros_afiliado: str = field(default_factory=lambda: _texto("ML_PARAMETROS_AFILIADO"))

    # WhatsApp (Evolution API)
    whatsapp_ativo: bool = field(default_factory=lambda: _booleano("WHATSAPP_ATIVO"))
    evolution_url: str = field(default_factory=lambda: _texto("EVOLUTION_URL").rstrip("/"))
    evolution_key: str = field(default_factory=lambda: _texto("EVOLUTION_KEY"))
    evolution_instancia: str = field(default_factory=lambda: _texto("EVOLUTION_INSTANCIA"))
    whatsapp_grupo: str = field(default_factory=lambda: _texto("WHATSAPP_GRUPO"))
    whatsapp_horarios: list = field(default_factory=lambda: _horarios(
        "WHATSAPP_HORARIOS", ["09:00", "11:30", "14:00", "17:00", "19:30", "21:00"]))
    whatsapp_atraso_min: int = field(default_factory=lambda: _inteiro("WHATSAPP_ATRASO_MIN", 60))

    # Vídeos
    rodadas_video: list = field(default_factory=lambda: _horarios("RODADAS_VIDEO", ["07:00", "12:00", "19:00"]))
    videos_por_rodada: int = field(default_factory=lambda: _inteiro("VIDEOS_POR_RODADA", 1))
    voz_edge: str = field(default_factory=lambda: _texto("VOZ_EDGE", "pt-BR-FranciscaNeural"))
    elevenlabs_key: str = field(default_factory=lambda: _texto("ELEVENLABS_KEY"))
    elevenlabs_voz: str = field(default_factory=lambda: _texto("ELEVENLABS_VOZ"))
    musica_fundo: str = field(default_factory=lambda: _texto("MUSICA_FUNDO"))
    hashtags: str = field(default_factory=lambda: _texto(
        "HASHTAGS", "#achadinhos #eletrodomesticos #promocao #ofertas #casa"))

    # Instagram (Reels)
    instagram_id: str = field(default_factory=lambda: _texto("INSTAGRAM_ID"))
    instagram_token: str = field(default_factory=lambda: _texto("INSTAGRAM_TOKEN"))
    graph_versao: str = field(default_factory=lambda: _texto("GRAPH_VERSAO", "v23.0"))

    # YouTube (Shorts)
    youtube_client_id: str = field(default_factory=lambda: _texto("YOUTUBE_CLIENT_ID"))
    youtube_client_secret: str = field(default_factory=lambda: _texto("YOUTUBE_CLIENT_SECRET"))
    youtube_refresh_token: str = field(default_factory=lambda: _texto("YOUTUBE_REFRESH_TOKEN"))
    youtube_privacidade: str = field(default_factory=lambda: _texto("YOUTUBE_PRIVACIDADE", "private"))

    @property
    def caminho_banco(self):
        return self.pasta_dados / "ofertas.db"

    @property
    def pasta_videos(self):
        return self.pasta_dados / "videos"

    @property
    def shopee_ativa(self):
        return bool(self.shopee_app_id and self.shopee_secret)

    @property
    def ml_ativo(self):
        return bool(self.ml_client_id and self.ml_client_secret and self.ml_refresh_token)

    @property
    def instagram_ativo(self):
        return bool(self.instagram_id and self.instagram_token)

    @property
    def youtube_ativo(self):
        return bool(self.youtube_client_id and self.youtube_client_secret and self.youtube_refresh_token)

    @property
    def whatsapp_configurado(self):
        return bool(self.whatsapp_ativo and self.evolution_url and self.evolution_key
                    and self.evolution_instancia and self.whatsapp_grupo)
