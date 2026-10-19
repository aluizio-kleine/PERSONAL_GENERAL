"""Banco SQLite: ofertas, histórico de preços, postagens e vídeos."""
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    id TEXT PRIMARY KEY,              -- 'shopee:123' / 'ml:MLB123'
    loja TEXT NOT NULL,
    titulo TEXT NOT NULL,
    link TEXT NOT NULL,               -- link de afiliado
    imagem TEXT,
    preco REAL NOT NULL,
    preco_antigo REAL,
    desconto REAL NOT NULL,           -- % informado pela loja
    nota REAL,
    vendas INTEGER,
    palavra_chave TEXT,
    visto_primeiro TEXT NOT NULL,
    visto_ultimo TEXT NOT NULL,
    telegram_em TEXT,
    telegram_preco REAL,
    whatsapp_em TEXT,
    video_em TEXT
);
CREATE TABLE IF NOT EXISTS historico (
    oferta_id TEXT NOT NULL,
    preco REAL NOT NULL,
    visto_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_historico ON historico (oferta_id, visto_em);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id TEXT NOT NULL,
    caminho TEXT NOT NULL,
    legenda TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',  -- pendente / aprovado / rejeitado
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS estado (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""


@dataclass
class Oferta:
    id: str
    loja: str
    titulo: str
    link: str
    imagem: str
    preco: float
    preco_antigo: float
    desconto: float
    nota: float = None
    vendas: int = None
    palavra_chave: str = ""


def agora():
    """Hora local do canal (FUSO), sem fuso no objeto, seja qual for o fuso do servidor."""
    fuso = ZoneInfo(os.getenv("FUSO") or "America/Sao_Paulo")
    return datetime.now(fuso).replace(tzinfo=None, microsecond=0)


def _iso(momento):
    return momento.isoformat(sep=" ")


class Banco:
    def __init__(self, caminho):
        self.caminho = str(caminho)
        with self._conexao() as con:
            con.executescript(ESQUEMA)

    @contextmanager
    def _conexao(self):
        # Uma conexão por operação: o bot e o agendador rodam em threads diferentes.
        con = sqlite3.connect(self.caminho, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- ofertas -----------------------------------------------------------

    def salvar_oferta(self, oferta, momento=None):
        momento = _iso(momento or agora())
        with self._conexao() as con:
            con.execute(
                """INSERT INTO ofertas (id, loja, titulo, link, imagem, preco, preco_antigo, desconto,
                                        nota, vendas, palavra_chave, visto_primeiro, visto_ultimo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       titulo=excluded.titulo, link=excluded.link, imagem=excluded.imagem,
                       preco=excluded.preco, preco_antigo=excluded.preco_antigo,
                       desconto=excluded.desconto, nota=excluded.nota, vendas=excluded.vendas,
                       visto_ultimo=excluded.visto_ultimo""",
                (oferta.id, oferta.loja, oferta.titulo, oferta.link, oferta.imagem, oferta.preco,
                 oferta.preco_antigo, oferta.desconto, oferta.nota, oferta.vendas,
                 oferta.palavra_chave, momento, momento),
            )
            con.execute("INSERT INTO historico (oferta_id, preco, visto_em) VALUES (?, ?, ?)",
                        (oferta.id, oferta.preco, momento))

    def oferta(self, oferta_id):
        with self._conexao() as con:
            return con.execute("SELECT * FROM ofertas WHERE id = ?", (oferta_id,)).fetchone()

    def ofertas_recentes(self, horas=6):
        limite = _iso(agora() - timedelta(hours=horas))
        with self._conexao() as con:
            return con.execute("SELECT * FROM ofertas WHERE visto_ultimo >= ?", (limite,)).fetchall()

    def precos_por_dia(self, oferta_id, dias=30, antes_de=None):
        """Menor preço de cada dia nos últimos `dias`, sem contar o dia de `antes_de`."""
        antes_de = antes_de or agora()
        inicio = _iso(antes_de - timedelta(days=dias))
        hoje = antes_de.date().isoformat()
        with self._conexao() as con:
            linhas = con.execute(
                """SELECT substr(visto_em, 1, 10) AS dia, MIN(preco) AS preco FROM historico
                   WHERE oferta_id = ? AND visto_em >= ? AND substr(visto_em, 1, 10) < ?
                   GROUP BY dia ORDER BY dia""",
                (oferta_id, inicio, hoje),
            ).fetchall()
        return [linha["preco"] for linha in linhas]

    def marcar(self, oferta_id, coluna, momento=None, preco=None):
        assert coluna in ("telegram_em", "whatsapp_em", "video_em")
        with self._conexao() as con:
            con.execute(f"UPDATE ofertas SET {coluna} = ? WHERE id = ?",
                        (_iso(momento or agora()), oferta_id))
            if coluna == "telegram_em" and preco is not None:
                con.execute("UPDATE ofertas SET telegram_preco = ? WHERE id = ?", (preco, oferta_id))

    def postadas_no_telegram(self, desde, ate):
        with self._conexao() as con:
            return con.execute(
                """SELECT * FROM ofertas WHERE telegram_em BETWEEN ? AND ?
                   AND (whatsapp_em IS NULL OR whatsapp_em < telegram_em)""",
                (_iso(desde), _iso(ate)),
            ).fetchall()

    def contar_postagens(self, coluna, desde):
        assert coluna in ("telegram_em", "whatsapp_em", "video_em")
        with self._conexao() as con:
            return con.execute(f"SELECT COUNT(*) FROM ofertas WHERE {coluna} >= ?",
                               (_iso(desde),)).fetchone()[0]

    # --- vídeos ------------------------------------------------------------

    def criar_video(self, oferta_id, caminho, legenda):
        with self._conexao() as con:
            cursor = con.execute(
                "INSERT INTO videos (oferta_id, caminho, legenda, criado_em) VALUES (?, ?, ?, ?)",
                (oferta_id, str(caminho), legenda, _iso(agora())),
            )
            return cursor.lastrowid

    def video(self, video_id):
        with self._conexao() as con:
            return con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()

    def mudar_status_video(self, video_id, status):
        with self._conexao() as con:
            con.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))

    # --- estado (offset do bot etc.) ---------------------------------------

    def ler_estado(self, chave, padrao=None):
        with self._conexao() as con:
            linha = con.execute("SELECT valor FROM estado WHERE chave = ?", (chave,)).fetchone()
        return linha["valor"] if linha else padrao

    def gravar_estado(self, chave, valor):
        with self._conexao() as con:
            con.execute("INSERT INTO estado (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (chave, str(valor)))
