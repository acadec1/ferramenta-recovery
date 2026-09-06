"""Relatorio pericial em PDF (ReportLab) a partir dos eventos de auditoria."""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.audit_log import ACTION_RECOVER, ACTION_VERIFY_FAILED, ACTION_VERIFY_OK

TITULO = "FRDA — Relatorio de Recuperacao de Dados"
COLUNAS = (
    "Data/Hora",
    "Dispositivo",
    "Accao",
    "Ficheiro",
    "SHA-256",
    "Utilizador SO",
    "Perito",
)
LARGURAS = (32 * mm, 28 * mm, 22 * mm, 58 * mm, 66 * mm, 22 * mm, 22 * mm)


def _ficheiros_por_accao(events: list[dict], action: str) -> set:
    return {
        event.get("file_path")
        for event in events
        if event.get("action") == action and event.get("file_path")
    }


def summarize_events(events: list[dict]) -> dict:
    """Totais do relatorio: ficheiros recuperados, verificados e falhados."""
    timestamps = sorted(str(event["timestamp"]) for event in events if event.get("timestamp"))
    dispositivos = sorted(
        {event["device_path"] for event in events if event.get("device_path")}
    )
    peritos = sorted({event["app_user"] for event in events if event.get("app_user")})
    return {
        "total_eventos": len(events),
        "dispositivos": dispositivos,
        "peritos": peritos,
        "ficheiros_recuperados": len(_ficheiros_por_accao(events, ACTION_RECOVER)),
        "verificados_com_sucesso": len(_ficheiros_por_accao(events, ACTION_VERIFY_OK)),
        "verificacoes_falhadas": len(_ficheiros_por_accao(events, ACTION_VERIFY_FAILED)),
        "primeiro_evento": timestamps[0] if timestamps else None,
        "ultimo_evento": timestamps[-1] if timestamps else None,
    }


def _celula(valor, estilo) -> Paragraph:
    return Paragraph("" if valor is None else str(valor), estilo)


def _tabela_de_eventos(events: list[dict], estilo) -> Table:
    linhas = [[Paragraph("<b>%s</b>" % coluna, estilo) for coluna in COLUNAS]]
    for event in events:
        linhas.append(
            [
                _celula(event.get("timestamp"), estilo),
                _celula(event.get("device_path"), estilo),
                _celula(event.get("action"), estilo),
                _celula(event.get("file_path"), estilo),
                _celula(event.get("file_hash"), estilo),
                _celula(event.get("os_user"), estilo),
                _celula(event.get("app_user"), estilo),
            ]
        )
    tabela = Table(linhas, colWidths=LARGURAS, repeatRows=1)
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


def generate_report(events: list[dict], output_path: str) -> None:
    """Gera o relatorio PDF com a tabela de eventos e o resumo de totais."""
    pasta = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(pasta, exist_ok=True)

    estilos = getSampleStyleSheet()
    estilo_celula = ParagraphStyle(
        "celula", parent=estilos["BodyText"], fontSize=7, leading=8.5
    )

    resumo = summarize_events(events)
    documento = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        title=TITULO,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    elementos = [Paragraph(TITULO, estilos["Title"]), Spacer(1, 6 * mm)]

    elementos.append(Paragraph("<b>Resumo</b>", estilos["Heading2"]))
    linhas_resumo = [
        ("Total de eventos registados", resumo["total_eventos"]),
        ("Ficheiros recuperados", resumo["ficheiros_recuperados"]),
        ("Verificados com sucesso (SHA-256)", resumo["verificados_com_sucesso"]),
        ("Verificacoes falhadas", resumo["verificacoes_falhadas"]),
        ("Dispositivos analisados", ", ".join(resumo["dispositivos"]) or "-"),
        ("Peritos intervenientes", ", ".join(resumo["peritos"]) or "-"),
        ("Primeiro evento", resumo["primeiro_evento"] or "-"),
        ("Ultimo evento", resumo["ultimo_evento"] or "-"),
    ]
    tabela_resumo = Table(
        [[Paragraph("<b>%s</b>" % rotulo, estilo_celula), _celula(valor, estilo_celula)]
         for rotulo, valor in linhas_resumo],
        colWidths=(70 * mm, 120 * mm),
    )
    tabela_resumo.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elementos.append(tabela_resumo)
    elementos.append(Spacer(1, 8 * mm))

    elementos.append(Paragraph("<b>Eventos</b>", estilos["Heading2"]))
    if events:
        elementos.append(_tabela_de_eventos(events, estilo_celula))
    else:
        elementos.append(Paragraph("Sem eventos registados.", estilos["BodyText"]))

    documento.build(elementos)
