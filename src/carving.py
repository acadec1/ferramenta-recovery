"""Carving por assinatura binaria (header/footer) para JPEG, PDF e DOCX.

Varre o dispositivo sequencialmente, sem consultar qualquer sistema de
ficheiros: e por isso independente de src/filesystem_parser.py e recupera dados
que ja nao tem entrada de directorio (espaco nao alocado). Como nao ha metadados
a delimitar os ficheiros, o varrimento percorre todo o dispositivo, incluindo as
areas ainda alocadas.

Limitacoes conhecidas da tecnica: ficheiros fragmentados sao reconstruidos
apenas ate ao ponto em que a fragmentacao ocorre; um JPEG cuja miniatura EXIF
contenha FFD9 e cortado nesse ponto; e num PDF com actualizacoes incrementais o
corte da-se no primeiro %%EOF.
"""

from __future__ import annotations

import os

from src.device_reader import device_size, read_aligned

CHUNK_SIZE = 1024 * 1024
OVERLAP = 64  # >= maior assinatura, para apanhar padroes entre blocos

SIGNATURES: dict[str, dict] = {
    "jpeg": {
        "header": b"\xff\xd8\xff",
        "footer": b"\xff\xd9",
        "trailer": 0,
        "extension": ".jpg",
        "min_size": 1024,
        "max_size": 32 * 1024 * 1024,
        "marker": None,
    },
    "pdf": {
        "header": b"%PDF-",
        "footer": b"%%EOF",
        "trailer": 0,
        "extension": ".pdf",
        "min_size": 1024,
        "max_size": 128 * 1024 * 1024,
        "marker": None,
    },
    "docx": {
        "header": b"PK\x03\x04",
        "footer": b"PK\x05\x06",
        "trailer": 18,  # restante do End Of Central Directory
        "extension": ".docx",
        "min_size": 1024,
        "max_size": 64 * 1024 * 1024,
        # distingue um DOCX de outro contentor ZIP qualquer
        "marker": b"word/",
    },
}

ALIASES = {"jpg": "jpeg", "jpe": "jpeg", "jfif": "jpeg"}


def supported_types() -> list[str]:
    """Tipos de ficheiro suportados pelo carving."""
    return sorted(SIGNATURES)


def _signature(file_type: str) -> dict:
    key = ALIASES.get(file_type.strip().lower().lstrip("."), file_type.strip().lower().lstrip("."))
    if key not in SIGNATURES:
        raise ValueError(
            "tipo de ficheiro nao suportado: %r (suportados: %s)"
            % (file_type, ", ".join(supported_types()))
        )
    return {"type": key, **SIGNATURES[key]}


def _read_chunk(device, size: int) -> bytes:
    """Le ate ``size`` bytes, juntando leituras curtas do dispositivo."""
    buffer = bytearray()
    while len(buffer) < size:
        data = device.read(size - len(buffer))
        if not data:
            break
        buffer.extend(data)
    return bytes(buffer)


def _candidato_valido(data: bytes, signature: dict) -> bool:
    """Um candidato so conta se tiver tamanho plausivel e o marcador do tipo."""
    if not signature["min_size"] <= len(data) <= signature["max_size"]:
        return False
    if signature["marker"] and signature["marker"] not in data:
        return False
    return True


def _nome_do_candidato(signature: dict, indice: int, inicio: int) -> str:
    return "%s_%05d_offset_%d%s" % (
        signature["type"], indice, inicio, signature["extension"],
    )


def find_by_signature(device_path: str, file_type: str, progresso=None,
                      ao_encontrar=None) -> list[dict]:
    """Localiza (sem extrair) os ficheiros do tipo indicado em ``device_path``.

    Percorre o dispositivo do principio ao fim a procura do par
    cabecalho/rodape do tipo escolhido. Devolve, por ordem de aparecimento, um
    dicionario por candidato com ``name``, ``offset``, ``size``, ``type`` e
    ``extension`` — o conteudo so e lido do disco quando se extrai, o que
    permite escolher a pasta de destino depois da analise.

    ``progresso`` e chamado com ``(bytes_lidos, total_ou_None)`` a cada bloco e
    ``ao_encontrar`` com cada candidato assim que e localizado.
    """
    signature = _signature(file_type)
    header = signature["header"]
    footer = signature["footer"]
    trailer = signature["trailer"]
    max_size = signature["max_size"]

    candidatos: list[dict] = []
    carry = b""
    carry_offset = 0
    in_file = False
    buffer = bytearray()
    file_start = 0

    with open(device_path, "rb", buffering=0) as device:
        total = device_size(device)
        lidos = 0
        while True:
            chunk = _read_chunk(device, CHUNK_SIZE)
            final = len(chunk) < CHUNK_SIZE
            lidos += len(chunk)
            if progresso is not None:
                progresso(lidos, total)
            window = carry + chunk
            base = carry_offset
            if not window:
                break

            limit = len(window) if final else max(0, len(window) - OVERLAP)
            position = 0

            while position < limit:
                if not in_file:
                    index = window.find(header, position)
                    if index == -1 or index >= limit:
                        position = limit
                        break
                    in_file = True
                    file_start = base + index
                    buffer = bytearray(header)
                    position = index + len(header)
                    continue

                found = window.find(footer, position)
                if found == -1 or found + len(footer) + trailer > len(window):
                    if found != -1 and not final:
                        break  # assinatura de fim truncada: espera pelo bloco seguinte
                    buffer.extend(window[position:limit])
                    position = limit
                    if len(buffer) > max_size:
                        in_file = False  # candidato demasiado grande: abandonado
                        buffer = bytearray()
                    continue

                end = found + len(footer) + trailer
                buffer.extend(window[position:end])
                if _candidato_valido(bytes(buffer), signature):
                    candidato = {
                        "name": _nome_do_candidato(
                            signature, len(candidatos) + 1, file_start
                        ),
                        "offset": file_start,
                        "size": len(buffer),
                        "type": signature["type"],
                        "extension": signature["extension"],
                    }
                    candidatos.append(candidato)
                    if ao_encontrar is not None:
                        ao_encontrar(candidato)
                in_file = False
                buffer = bytearray()
                position = end

            carry = window[position:]
            carry_offset = base + position
            if final:
                break

    return candidatos


def extract_candidate(device_path: str, candidato: dict, output_dir: str) -> str:
    """Le do dispositivo o candidato localizado e grava-o em ``output_dir``."""
    os.makedirs(output_dir, exist_ok=True)
    destino = os.path.join(output_dir, candidato["name"])
    with open(device_path, "rb", buffering=0) as device:
        dados = read_aligned(device, int(candidato["offset"]), int(candidato["size"]))
    if not dados:
        raise ValueError(
            "nao foi possivel ler o candidato na posicao %s" % candidato.get("offset")
        )
    with open(destino, "wb") as saida:
        saida.write(dados)
    return destino


def carve_by_signature(device_path: str, file_type: str, output_dir: str,
                       progresso=None) -> list[str]:
    """Varre ``device_path`` por ficheiros do tipo indicado e grava-os.

    E a juncao das duas fases: localizar os candidatos e extrair todos.
    Devolve a lista de caminhos dos ficheiros extraidos, por ordem de
    aparecimento no dispositivo.
    """
    os.makedirs(output_dir, exist_ok=True)
    extraidos = []
    for candidato in find_by_signature(device_path, file_type, progresso):
        extraidos.append(extract_candidate(device_path, candidato, output_dir))
    return extraidos
