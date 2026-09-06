"""Iconografia da aplicacao.

Os icones sao desenhados em SVG e compostos aqui mesmo (sem ficheiros externos
nem dependencias novas), o que garante tracos consistentes, enquadramento igual
numa grelha de 24x24 e cor definida por quem os usa.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.gui import theme

# Traco de cada icone, numa grelha normalizada de 24x24.
DESENHOS = {
    "disco": (
        '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/>'
        '<circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/>'
        '<path d="M17.5 16.5v.01"/>'
    ),
    "volume": (
        '<rect x="3" y="4.5" width="18" height="12" rx="2"/>'
        '<path d="M8 20h8M12 16.5V20"/>'
    ),
    "removivel": (
        '<path d="M5 8.5 8.5 4.5H19a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7"/>'
        '<path d="M10.5 4.5v3M13.5 4.5v3M16.5 4.5v3"/>'
    ),
    "imagem": (
        '<ellipse cx="12" cy="6" rx="7.5" ry="3"/>'
        '<path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6"/>'
        '<path d="M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6"/>'
    ),
    "lupa": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.9-4.9"/>',
    "ficheiro": (
        '<path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3.5V8h4.5"/><path d="M9 13h6M9 16.5h4"/>'
    ),
    "carving": (
        '<path d="M3.5 7.5V5a1.5 1.5 0 0 1 1.5-1.5h2.5M16.5 3.5H19A1.5 1.5 0 0 1 20.5 5v2.5"/>'
        '<path d="M20.5 16.5V19a1.5 1.5 0 0 1-1.5 1.5h-2.5M7.5 20.5H5A1.5 1.5 0 0 1 3.5 19v-2.5"/>'
        '<path d="M3.5 12h17"/>'
    ),
    "auditoria": (
        '<path d="M8 4.5H6.5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-12a2 2 0 0 0-2-2H16"/>'
        '<rect x="8" y="2.5" width="8" height="4" rx="1.2"/>'
        '<path d="M8.5 11.5h7M8.5 15.5h4.5"/>'
    ),
    "contas": (
        '<circle cx="9" cy="8.5" r="3.5"/>'
        '<path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
        '<path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M17.5 20a6.4 6.4 0 0 0-2-4.6"/>'
    ),
    "escudo": (
        '<path d="M12 3 5 6v5.5c0 4.3 2.9 8.2 7 9.5 4.1-1.3 7-5.2 7-9.5V6z"/>'
        '<path d="m9.2 12 2 2 3.6-3.8"/>'
    ),
    "administrador": (
        '<path d="M12 3 5 6v5.5c0 4.3 2.9 8.2 7 9.5 4.1-1.3 7-5.2 7-9.5V6z"/>'
        '<circle cx="12" cy="10.5" r="1.8"/><path d="M12 12.3V15"/>'
    ),
    "actualizar": (
        '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4v4h-4"/>'
    ),
    "recuperar": (
        '<path d="M12 16V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/>'
        '<path d="M4 15v3.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V15"/>'
    ),
    "pasta": (
        '<path d="M3.5 7a2 2 0 0 1 2-2h3.2l2 2.5H18.5a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>'
    ),
    "aviso": (
        '<path d="M10.3 4.3 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z"/>'
        '<path d="M12 9v4.5M12 17.2v.01"/>'
    ),
    "logotipo": (
        '<path d="M12 2.5 4 6v6c0 5 3.4 9.4 8 10.5 4.6-1.1 8-5.5 8-10.5V6z"/>'
        '<path d="M9 12.5h6M12 9.5v6"/>'
    ),
}

# Cores dos "chips" (quadrado colorido atras do icone), como na barra lateral e
# nos cartoes de dispositivo.
CHIPS = {
    "azul": (theme.CORES["primaria"], theme.CORES["primaria_clara"]),
    "verde": (theme.CORES["sucesso"], theme.CORES["sucesso_clara"]),
    "laranja": (theme.CORES["aviso"], theme.CORES["aviso_clara"]),
    "roxo": (theme.CORES["roxo"], theme.CORES["roxo_claro"]),
    "vermelho": (theme.CORES["erro"], theme.CORES["erro_clara"]),
    "cinzento": (theme.CORES["texto_suave"], theme.CORES["lateral"]),
}

_cache: dict = {}


def _svg(nome: str, cor: str, espessura: float = 1.7) -> bytes:
    if nome not in DESENHOS:
        raise KeyError("icone desconhecido: %r" % nome)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round">'
        "%s</svg>" % (cor, espessura, DESENHOS[nome])
    ).encode("utf-8")


def pixmap(nome: str, tamanho: int = 20, cor: str | None = None,
           escala: int = 2) -> QPixmap:
    """Desenha o icone num QPixmap quadrado, pronto a colocar num QLabel."""
    cor = cor or theme.CORES["texto"]
    chave = ("pixmap", nome, tamanho, cor, escala)
    if chave in _cache:
        return _cache[chave]

    desenho = _svg(nome, cor)  # valida o nome antes de abrir o pintor
    imagem = QPixmap(tamanho * escala, tamanho * escala)
    imagem.fill(Qt.transparent)
    pintor = QPainter(imagem)
    try:
        pintor.setRenderHint(QPainter.Antialiasing, True)
        QSvgRenderer(desenho).render(pintor)
    finally:
        pintor.end()  # um pintor aberto sobre o pixmap faz o Qt abortar
    imagem.setDevicePixelRatio(escala)
    _cache[chave] = imagem
    return imagem


def icone(nome: str, tamanho: int = 20, cor: str | None = None) -> QIcon:
    """Icone para botoes e itens de lista."""
    return QIcon(pixmap(nome, tamanho, cor))


def chip(nome: str, cor: str = "azul", tamanho: int = 44, escala: int = 2) -> QPixmap:
    """Icone dentro de um quadrado arredondado colorido."""
    traco, fundo = CHIPS.get(cor, CHIPS["azul"])
    chave = ("chip", nome, cor, tamanho, escala)
    if chave in _cache:
        return _cache[chave]

    desenho = _svg(nome, traco, espessura=1.8)  # valida o nome antes do pintor
    imagem = QPixmap(tamanho * escala, tamanho * escala)
    imagem.fill(Qt.transparent)
    pintor = QPainter(imagem)
    try:
        pintor.setRenderHint(QPainter.Antialiasing, True)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(QColor(fundo))
        lado = tamanho * escala
        raio = lado * 0.27
        pintor.drawRoundedRect(QRectF(0, 0, lado, lado), raio, raio)
        margem = lado * 0.24
        QSvgRenderer(desenho).render(
            pintor, QRectF(margem, margem, lado - 2 * margem, lado - 2 * margem)
        )
    finally:
        pintor.end()
    imagem.setDevicePixelRatio(escala)
    _cache[chave] = imagem
    return imagem


def limpar_cache() -> None:
    """Esquece os icones ja desenhados (usado nos testes)."""
    _cache.clear()
