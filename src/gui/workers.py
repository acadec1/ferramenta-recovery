"""Trabalhos em segundo plano, para a janela nao ficar parada.

A analise de um disco e a recuperacao de ficheiros demoram, por vezes minutos.
Correm aqui numa linha de execucao propria, comunicando por sinais: assim a
barra de progresso avanca e a interface continua a responder. A logica em si
esta em src/operacao.py — estas classes so a transportam.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from src import operacao

# Entradas acumuladas antes de cada aviso a interface. Enviar uma a uma tornaria
# a analise mais lenta do que o varrimento em si quando ha milhares de
# ficheiros; um lote pequeno mantem a sensacao de tempo real.
TAMANHO_DO_LOTE = 25


class TrabalhoDeAnalise(QThread):
    """Analisa o dispositivo pelo metodo escolhido."""

    progresso = Signal(int, int)  # feitos, total (0 quando o total e desconhecido)
    encontrados = Signal(list)  # lote de entradas, durante a analise
    concluido = Signal(list, dict)  # entradas encontradas, diagnostico
    interrompido = Signal(list, dict)  # o mesmo, mas parado pelo utilizador
    falhou = Signal(str)

    def __init__(self, device_path: str, metodo: str, parent=None):
        super().__init__(parent)
        self.device_path = device_path
        self.metodo = metodo
        self._lote: list[dict] = []
        self._parar = False

    def parar(self) -> None:
        """Pede a paragem; o varrimento devolve o que ja encontrou."""
        self._parar = True

    def foi_parado(self) -> bool:
        return self._parar

    def _avancar(self, feitos, total) -> None:
        self.progresso.emit(int(feitos or 0), int(total or 0))

    def _encontrada(self, entrada: dict) -> None:
        self._lote.append(entrada)
        if len(self._lote) >= TAMANHO_DO_LOTE:
            self._despachar_lote()

    def _despachar_lote(self) -> None:
        if self._lote:
            self.encontrados.emit(self._lote)
            self._lote = []

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            entradas, diagnostico = operacao.analisar(
                self.device_path, self.metodo, self._avancar, self._encontrada,
                self.foi_parado,
            )
        except Exception as erro:
            self._despachar_lote()
            self.falhou.emit(str(erro))
            return
        self._despachar_lote()
        if self._parar:
            self.interrompido.emit(entradas, diagnostico)
            return
        self.concluido.emit(entradas, diagnostico)


class TrabalhoDeRecuperacao(QThread):
    """Recupera as entradas seleccionadas para a pasta de destino."""

    progresso = Signal(int, int)  # ficheiros tratados, total
    concluido = Signal(list)  # um resultado por ficheiro
    interrompido = Signal(list)  # o mesmo, mas parado pelo utilizador
    falhou = Signal(str)

    def __init__(self, device_path: str, entradas: list[dict], destino: str,
                 parent=None):
        super().__init__(parent)
        self.device_path = device_path
        self.entradas = list(entradas)
        self.destino = destino
        self._parar = False

    def parar(self) -> None:
        """Pede a paragem; os ficheiros ja recuperados mantem-se."""
        self._parar = True

    def foi_parado(self) -> bool:
        return self._parar

    def _avancar(self, feitos, total) -> None:
        self.progresso.emit(int(feitos or 0), int(total or 0))

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            resultados = operacao.recuperar(
                self.device_path, self.entradas, self.destino, self._avancar,
                self.foi_parado,
            )
        except Exception as erro:
            self.falhou.emit(str(erro))
            return
        if self._parar:
            self.interrompido.emit(resultados)
            return
        self.concluido.emit(resultados)
