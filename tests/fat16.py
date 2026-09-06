"""Construtor de imagens FAT16 sinteticas para os testes de integracao.

Gera uma imagem de disco valida, com um ficheiro alocado e outro apagado (nome
com 0xE5 e cadeia da FAT libertada), tal como acontece depois de uma eliminacao
real. Permite exercitar o pytsk3 verdadeiro sem dispositivo fisico nem
privilegios de Administrador.
"""

from __future__ import annotations

import struct

BYTES_POR_SECTOR = 512
SECTORES_POR_CLUSTER = 4
SECTORES_RESERVADOS = 1
NUMERO_DE_FATS = 2
ENTRADAS_RAIZ = 512
SECTORES_POR_FAT = 64
TOTAL_DE_SECTORES = 65536  # 32 MB: dentro do intervalo de clusters do FAT16

TAMANHO_DO_CLUSTER = BYTES_POR_SECTOR * SECTORES_POR_CLUSTER
SECTORES_DA_RAIZ = ENTRADAS_RAIZ * 32 // BYTES_POR_SECTOR
INICIO_DA_FAT = SECTORES_RESERVADOS * BYTES_POR_SECTOR
INICIO_DA_RAIZ = (
    SECTORES_RESERVADOS + NUMERO_DE_FATS * SECTORES_POR_FAT
) * BYTES_POR_SECTOR
INICIO_DOS_DADOS = INICIO_DA_RAIZ + SECTORES_DA_RAIZ * BYTES_POR_SECTOR

CLUSTER_DO_ACTIVO = 2
CLUSTER_DO_APAGADO = 3


def _sector_de_arranque() -> bytes:
    bs = bytearray(BYTES_POR_SECTOR)
    bs[0:3] = b"\xeb\x3c\x90"
    bs[3:11] = b"FRDATEST"
    struct.pack_into("<H", bs, 11, BYTES_POR_SECTOR)
    bs[13] = SECTORES_POR_CLUSTER
    struct.pack_into("<H", bs, 14, SECTORES_RESERVADOS)
    bs[16] = NUMERO_DE_FATS
    struct.pack_into("<H", bs, 17, ENTRADAS_RAIZ)
    struct.pack_into("<H", bs, 19, 0)  # total de sectores fica no campo de 32 bits
    bs[21] = 0xF8  # disco fixo
    struct.pack_into("<H", bs, 22, SECTORES_POR_FAT)
    struct.pack_into("<H", bs, 24, 63)  # sectores por pista
    struct.pack_into("<H", bs, 26, 255)  # cabecas
    struct.pack_into("<I", bs, 28, 0)  # sectores escondidos
    struct.pack_into("<I", bs, 32, TOTAL_DE_SECTORES)
    bs[36] = 0x80  # numero da unidade
    bs[38] = 0x29  # assinatura estendida
    struct.pack_into("<I", bs, 39, 0x12345678)
    bs[43:54] = b"FRDA VOLUME"
    bs[54:62] = b"FAT16   "
    bs[510:512] = b"\x55\xaa"
    return bytes(bs)


def _entrada_de_directorio(nome: str, extensao: str, cluster: int, tamanho: int,
                           apagado: bool = False) -> bytes:
    entrada = bytearray(32)
    entrada[0:8] = nome.ljust(8).encode()
    entrada[8:11] = extensao.ljust(3).encode()
    if apagado:
        entrada[0] = 0xE5  # marca de entrada eliminada
    entrada[11] = 0x20  # atributo de arquivo
    struct.pack_into("<H", entrada, 22, 0x8000)  # hora
    struct.pack_into("<H", entrada, 24, 0x5A21)  # data
    struct.pack_into("<H", entrada, 26, cluster)
    struct.pack_into("<I", entrada, 28, tamanho)
    return bytes(entrada)


def construir_imagem(caminho: str, conteudo_apagado: bytes = b"",
                     conteudo_activo: bytes = b"ficheiro activo\n",
                     com_ficheiro_apagado: bool = True) -> str:
    """Escreve a imagem FAT16 e devolve o caminho.

    Com ``com_ficheiro_apagado=False`` a imagem fica apenas com o ficheiro
    alocado, sem qualquer entrada eliminada.
    """
    imagem = bytearray(TOTAL_DE_SECTORES * BYTES_POR_SECTOR)
    imagem[0:BYTES_POR_SECTOR] = _sector_de_arranque()

    # Na FAT so o cluster do ficheiro activo continua ocupado; o do ficheiro
    # apagado foi libertado, mas os dados permanecem no disco.
    fat = bytearray(SECTORES_POR_FAT * BYTES_POR_SECTOR)
    struct.pack_into("<H", fat, 0, 0xFFF8)
    struct.pack_into("<H", fat, 2, 0xFFFF)
    struct.pack_into("<H", fat, CLUSTER_DO_ACTIVO * 2, 0xFFFF)
    for numero in range(NUMERO_DE_FATS):
        inicio = INICIO_DA_FAT + numero * SECTORES_POR_FAT * BYTES_POR_SECTOR
        imagem[inicio:inicio + len(fat)] = fat

    raiz = bytearray()
    raiz += _entrada_de_directorio(
        "ACTIVO", "TXT", CLUSTER_DO_ACTIVO, len(conteudo_activo)
    )
    if com_ficheiro_apagado:
        raiz += _entrada_de_directorio(
            "PROVA", "TXT", CLUSTER_DO_APAGADO, len(conteudo_apagado), apagado=True
        )
    imagem[INICIO_DA_RAIZ:INICIO_DA_RAIZ + len(raiz)] = raiz

    for cluster, conteudo in (
        (CLUSTER_DO_ACTIVO, conteudo_activo),
        (CLUSTER_DO_APAGADO, conteudo_apagado),
    ):
        inicio = INICIO_DOS_DADOS + (cluster - 2) * TAMANHO_DO_CLUSTER
        imagem[inicio:inicio + len(conteudo)] = conteudo

    with open(caminho, "wb") as ficheiro:
        ficheiro.write(bytes(imagem))
    return caminho
