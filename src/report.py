"""Relatorio da operacao de recuperacao, em PDF (ReportLab).

Documenta uma operacao completa: identificacao, dispositivo analisado, metodo
utilizado, totais de ficheiros encontrados, seleccionados, recuperados e nao
recuperados, lista dos ficheiros processados, pasta de destino e observacoes.
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.historico import NOMES_DOS_ESTADOS, NOMES_DOS_METODOS


def _celula(valor, estilo) -> Paragraph:
    return Paragraph("" if valor is None else str(valor), estilo)


TITULO_DA_OPERACAO = "FRDA — Relatorio de Operacao de Recuperacao"
COLUNAS_DOS_FICHEIROS = ("Nome", "Tipo", "Tamanho", "Estado", "Observacao")
LARGURAS_DOS_FICHEIROS = (70 * mm, 22 * mm, 26 * mm, 30 * mm, 60 * mm)


def _tamanho_legivel(tamanho) -> str:
    if tamanho in (None, ""):
        return "-"
    valor = float(tamanho)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            return "%.1f %s" % (valor, unidade)
        valor /= 1024
    return "%.1f TB" % valor


def _identificacao_da_operacao(operacao: dict) -> list[tuple]:
    """Linhas do cabecalho do relatorio, na ordem em que sao lidas."""
    metodo = operacao.get("metodo")
    estado = operacao.get("estado")
    return [
        ("Identificacao da operacao", "#%s" % operacao.get("id", "-")),
        ("Inicio", operacao.get("inicio") or "-"),
        ("Fim", operacao.get("fim") or "-"),
        ("Dispositivo analisado", operacao.get("device_path") or "-"),
        ("Tipo de dispositivo", operacao.get("device_type") or "-"),
        ("Capacidade", _tamanho_legivel(operacao.get("device_size"))),
        ("Sistema de ficheiros", operacao.get("filesystem") or "nao identificado"),
        ("Metodo utilizado", NOMES_DOS_METODOS.get(metodo, metodo or "-")),
        ("Estado da operacao", NOMES_DOS_ESTADOS.get(estado, estado or "-")),
        ("Ficheiros encontrados", operacao.get("encontrados", 0)),
        ("Ficheiros seleccionados", operacao.get("seleccionados", 0)),
        ("Ficheiros recuperados", operacao.get("recuperados", 0)),
        ("Ficheiros nao recuperados", operacao.get("nao_recuperados", 0)),
        ("Pasta de destino", operacao.get("pasta_destino") or "-"),
        ("Perito", operacao.get("app_user") or "-"),
        ("Utilizador do sistema", operacao.get("os_user") or "-"),
        ("Observacoes", operacao.get("observacoes") or "sem observacoes"),
    ]


def _tabela_de_ficheiros(ficheiros: list[dict], estilo) -> Table:
    linhas = [[Paragraph("<b>%s</b>" % coluna, estilo)
               for coluna in COLUNAS_DOS_FICHEIROS]]
    for ficheiro in ficheiros:
        linhas.append(
            [
                _celula(ficheiro.get("nome"), estilo),
                _celula(ficheiro.get("tipo"), estilo),
                _celula(_tamanho_legivel(ficheiro.get("tamanho")), estilo),
                _celula(ficheiro.get("estado"), estilo),
                _celula(ficheiro.get("erro") or ficheiro.get("caminho") or "", estilo),
            ]
        )
    tabela = Table(linhas, colWidths=LARGURAS_DOS_FICHEIROS, repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f4f4f4")]),
            ]
        )
    )
    return tabela


def generate_operation_report(operacao: dict, ficheiros: list[dict],
                              output_path: str) -> None:
    """Gera o relatorio PDF de uma operacao de recuperacao.

    Inclui a identificacao da operacao, o dispositivo e o metodo usados, os
    totais de ficheiros encontrados, seleccionados, recuperados e nao
    recuperados, a lista dos ficheiros processados com o respectivo estado, a
    pasta onde foram guardados e as observacoes ou erros.
    """
    pasta = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(pasta, exist_ok=True)

    estilos = getSampleStyleSheet()
    estilo_celula = ParagraphStyle(
        "celula", parent=estilos["BodyText"], fontSize=8, leading=9.5
    )

    documento = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        title=TITULO_DA_OPERACAO,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    elementos = [Paragraph(TITULO_DA_OPERACAO, estilos["Title"]), Spacer(1, 6 * mm)]

    elementos.append(Paragraph("<b>Identificacao</b>", estilos["Heading2"]))
    identificacao = Table(
        [[Paragraph("<b>%s</b>" % rotulo, estilo_celula),
          _celula(valor, estilo_celula)]
         for rotulo, valor in _identificacao_da_operacao(operacao)],
        colWidths=(60 * mm, 140 * mm),
    )
    identificacao.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elementos.append(identificacao)
    elementos.append(Spacer(1, 8 * mm))

    elementos.append(Paragraph("<b>Ficheiros processados</b>", estilos["Heading2"]))
    if ficheiros:
        elementos.append(_tabela_de_ficheiros(ficheiros, estilo_celula))
    else:
        elementos.append(
            Paragraph("Nenhum ficheiro foi processado.", estilos["BodyText"])
        )

    documento.build(elementos)
