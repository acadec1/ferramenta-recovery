"""Execucao de uma operacao de recuperacao, do inicio ao fim.

Encadeia os modulos de analise e de recuperacao conforme o metodo escolhido:

- ``metadados``: usa src/filesystem_parser.py para ler as estruturas do sistema
  de ficheiros e src/recovery.py para reconstruir a partir dos clusters;
- ``carving``: usa src/carving.py para procurar assinaturas nos dados em bruto,
  localizando primeiro e extraindo depois.

Devolve sempre a mesma forma de entrada, venha ela de que metodo vier, para que
a interface nao precise de saber a diferenca. As funcoes aceitam uma funcao de
progresso, para poderem correr fora da linha de execucao da interface.
"""

from __future__ import annotations

import os

from src import carving, device_reader, filesystem_parser, integrity, recovery
from src.historico import (
    ESTADO_FALHADO,
    ESTADO_RECUPERADO,
    METODO_CARVING,
    METODO_METADADOS,
)

PREFIXO_DE_DISPOSITIVO = "\\\\.\\"  # \\.\ — prefixo dos dispositivos do Windows
PREFIXO_DE_DISCO_FISICO = PREFIXO_DE_DISPOSITIVO + "PHYSICALDRIVE"

ERRO_MESMO_DISPOSITIVO = (
    "A pasta de destino (%s) esta no dispositivo em analise (%s). Escolha outro "
    "disco: gravar no suporte analisado destroi a prova."
)


def tipo_do_ficheiro(nome: str) -> str:
    """Extensao em maiusculas, usada como tipo na lista de ficheiros."""
    extensao = os.path.splitext(nome or "")[1].lstrip(".")
    return extensao.upper() if extensao else "?"


def _normalizar(entrada: dict, metodo: str) -> dict:
    """Forma comum das entradas, independente do metodo que as encontrou."""
    nome = entrada.get("name") or ""
    return {
        **entrada,
        "metodo": metodo,
        "nome": nome,
        "tipo": tipo_do_ficheiro(nome),
        "tamanho": int(entrada.get("size") or 0),
    }


def analisar(device_path: str, metodo: str, progresso=None,
             ao_encontrar=None) -> tuple[list[dict], dict]:
    """Analisa o dispositivo pelo metodo indicado.

    Devolve as entradas encontradas e um diagnostico com o que foi examinado.
    Se ``ao_encontrar`` for indicado, cada entrada e entregue assim que e
    localizada, ja normalizada, para a lista se ir preenchendo durante a
    analise em vez de aparecer toda no fim.
    """
    if metodo == METODO_METADADOS:
        return _analisar_por_metadados(device_path, progresso, ao_encontrar)
    if metodo == METODO_CARVING:
        return _analisar_por_assinaturas(device_path, progresso, ao_encontrar)
    raise ValueError("metodo desconhecido: %r" % metodo)


def _entregar(metodo, ao_encontrar):
    """Normaliza a entrada em bruto e entrega-a a quem esta a acompanhar."""
    if ao_encontrar is None:
        return None

    def entregar(entrada):
        ao_encontrar(_normalizar(entrada, metodo))

    return entregar


def _analisar_por_metadados(device_path: str, progresso,
                            ao_encontrar=None) -> tuple[list[dict], dict]:
    diagnostico: dict = {}
    entradas = filesystem_parser.scan_deleted_entries(
        device_path, diagnostico, progresso, _entregar(METODO_METADADOS, ao_encontrar)
    )
    diagnostico["metodo"] = METODO_METADADOS
    return [_normalizar(e, METODO_METADADOS) for e in entradas], diagnostico


def _analisar_por_assinaturas(device_path: str, progresso,
                              ao_encontrar=None) -> tuple[list[dict], dict]:
    tipos = carving.supported_types()
    entradas: list[dict] = []
    entregar = _entregar(METODO_CARVING, ao_encontrar)
    for posicao, tipo in enumerate(tipos):
        def avanco(lidos, total, posicao=posicao):
            """Junta o progresso dos varios tipos numa so barra."""
            if progresso is None:
                return
            if not total:
                progresso(lidos, 0)
                return
            progresso(posicao * total + lidos, len(tipos) * total)

        for candidato in carving.find_by_signature(
            device_path, tipo, avanco, entregar
        ):
            entradas.append(_normalizar(candidato, METODO_CARVING))

    diagnostico = {
        "metodo": METODO_CARVING,
        "tipos": tipos,
        "particoes": 0,
        "sistemas_de_ficheiros": 0,
        "registos_examinados": 0,
    }
    return entradas, diagnostico


def validar_destino(device_path: str, destino: str) -> None:
    """Garante que o destino nao fica no dispositivo que esta a ser analisado.

    Levanta ``ValueError`` quando a pasta escolhida pertence ao volume em
    analise ou a um volume do mesmo disco fisico.
    """
    if not destino:
        raise ValueError("nenhuma pasta de destino escolhida")
    letra_do_destino = os.path.splitdrive(os.path.abspath(destino))[0].rstrip(":")
    if not letra_do_destino:
        return

    letra_do_destino = letra_do_destino.lstrip("\\").upper()[:1]
    for volume in _volumes_do_dispositivo(device_path):
        if volume.upper() == letra_do_destino:
            raise ValueError(ERRO_MESMO_DISPOSITIVO % (destino, device_path))


def _volumes_do_dispositivo(device_path: str) -> list[str]:
    """Letras de unidade que pertencem ao dispositivo em analise."""
    caminho = (device_path or "").upper()
    if caminho.startswith(PREFIXO_DE_DISCO_FISICO):
        try:
            indice = int(caminho[len(PREFIXO_DE_DISCO_FISICO):])
        except ValueError:
            return []
        return [
            volume["letter"]
            for volume in device_reader.list_logical_volumes()
            if volume["disk_index"] == indice
        ]
    if caminho.startswith(PREFIXO_DE_DISPOSITIVO) and caminho.endswith(":"):
        return [caminho[len(PREFIXO_DE_DISPOSITIVO):][:1]]
    return []  # imagem de disco: o destino pode ser qualquer pasta


def recuperar_entrada(device_path: str, entrada: dict, destino: str) -> dict:
    """Recupera uma entrada e devolve o resultado, pronto para o historico."""
    resultado = {
        "nome": entrada.get("nome") or entrada.get("name") or "?",
        "tipo": entrada.get("tipo") or tipo_do_ficheiro(entrada.get("name", "")),
        "tamanho": entrada.get("tamanho") or entrada.get("size") or 0,
        "estado": ESTADO_FALHADO,
        "caminho": None,
        "file_hash": None,
        "erro": None,
    }
    try:
        if entrada.get("metodo") == METODO_CARVING:
            caminho = carving.extract_candidate(device_path, entrada, destino)
        else:
            caminho = recovery.recover_file(device_path, entrada, destino)
        hash_sha256 = integrity.compute_hash(caminho)
        if not integrity.verify_integrity(hash_sha256, caminho):
            raise ValueError("a verificacao de integridade falhou")
        resultado.update(
            estado=ESTADO_RECUPERADO, caminho=caminho, file_hash=hash_sha256
        )
    except Exception as erro:
        resultado["erro"] = str(erro)
    return resultado


def recuperar(device_path: str, entradas: list[dict], destino: str,
              progresso=None) -> list[dict]:
    """Recupera as entradas indicadas para ``destino``.

    Devolve um resultado por ficheiro, com estado, hash e eventual erro. Um
    ficheiro que falhe nao interrompe os restantes.
    """
    validar_destino(device_path, destino)
    os.makedirs(destino, exist_ok=True)

    resultados = []
    total = len(entradas)
    for posicao, entrada in enumerate(entradas, start=1):
        resultados.append(recuperar_entrada(device_path, entrada, destino))
        if progresso is not None:
            progresso(posicao, total)
    return resultados


def resumo(encontrados: int, resultados: list[dict]) -> dict:
    """Totais da operacao, para os cartoes de estatisticas e para o relatorio."""
    recuperados = sum(1 for r in resultados if r["estado"] == ESTADO_RECUPERADO)
    return {
        "encontrados": encontrados,
        "seleccionados": len(resultados),
        "recuperados": recuperados,
        "nao_recuperados": len(resultados) - recuperados,
    }
