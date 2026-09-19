"""Trabalhos em segundo plano, para a janela nao ficar parada.

A analise de um disco e a recuperacao de ficheiros demoram, por vezes minutos.
Correm aqui numa linha de execucao propria, comunicando por sinais: assim a
barra de progresso avanca e a interface continua a responder. A logica em si
esta em src/operacao.py — estas classes so a transportam.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from src import operacao


class TrabalhoDeAnalise(QThread):
    """Analisa o dispositivo pelo metodo escolhido."""

    progresso = Signal(int, int)  # feitos, total (0 quando o total e desconhecido)
    concluido = Signal(list, dict)  # entradas encontradas, diagnostico
    falhou = Signal(str)

    def __init__(self, device_path: str, metodo: str, parent=None):
        super().__init__(parent)
        self.device_path = device_path
        self.metodo = metodo

    def _avancar(self, feitos, total) -> None:
        self.progresso.emit(int(feitos or 0), int(total or 0))

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            entradas, diagnostico = operacao.analisar(
                self.device_path, self.metodo, self._avancar
            )
        except Exception as erro:
            self.falhou.emit(str(erro))
            return
        self.concluido.emit(entradas, diagnostico)


class TrabalhoDeRecuperacao(QThread):
    """Recupera as entradas seleccionadas para a pasta de destino."""

    progresso = Signal(int, int)  # ficheiros tratados, total
    concluido = Signal(list)  # um resultado por ficheiro
    falhou = Signal(str)

    def __init__(self, device_path: str, entradas: list[dict], destino: str,
                 parent=None):
        super().__init__(parent)
        self.device_path = device_path
        self.entradas = list(entradas)
        self.destino = destino

    def _avancar(self, feitos, total) -> None:
        self.progresso.emit(int(feitos or 0), int(total or 0))

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            resultados = operacao.recuperar(
                self.device_path, self.entradas, self.destino, self._avancar
            )
        except Exception as erro:
            self.falhou.emit(str(erro))
            return
        self.concluido.emit(resultados)
