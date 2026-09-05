r"""Reconstrucao de ficheiros apagados a partir dos clusters/sectores no disco.

Le directamente o dispositivo (\\.\PhysicalDriveN ou imagem .dd) nas posicoes
indicadas pelos runs de uma entrada produzida por src/filesystem_parser.py e
escreve o conteudo em disco. As leituras sao alinhadas ao sector porque o
Windows recusa leituras nao alinhadas em dispositivos fisicos.
"""

from __future__ import annotations

import os

DEFAULT_SECTOR_SIZE = 512
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def sanitize_filename(name: str, fallback: str = "recuperado.bin") -> str:
    """Converte um nome de ficheiro apagado num nome valido no Windows."""
    if not name:
        return fallback
    cleaned = "".join(
        "_" if (character in INVALID_FILENAME_CHARS or ord(character) < 32) else character
        for character in name
    )
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def _unique_output_path(output_dir: str, filename: str) -> str:
    """Caminho que nao colide com ficheiros ja recuperados na mesma pasta."""
    candidate = os.path.join(output_dir, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, extension = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(output_dir, f"{stem}_{counter}{extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _read_aligned(device, offset: int, length: int, sector_size: int) -> bytes:
    """Le ``length`` bytes a partir de ``offset`` com leituras alinhadas ao sector."""
    if length <= 0:
        return b""
    aligned_offset = offset - (offset % sector_size)
    padding = offset - aligned_offset
    total = padding + length
    if total % sector_size:
        total += sector_size - (total % sector_size)
    device.seek(aligned_offset)
    buffer = bytearray()
    while len(buffer) < total:
        chunk = device.read(total - len(buffer))
        if not chunk:
            break  # fim do dispositivo
        buffer.extend(chunk)
    return bytes(buffer[padding:padding + length])


def recover_file(device_path: str, entry: dict, output_dir: str) -> str:
    """Reconstroi o ficheiro descrito por ``entry`` dentro de ``output_dir``.

    Devolve o caminho do ficheiro escrito. Levanta ``ValueError`` se a entrada
    nao tiver clusters associados (por exemplo, dados residentes no MFT ou
    registo ja reutilizado).
    """
    runs = entry.get("runs") or []
    if not runs:
        raise ValueError(
            "entrada sem clusters associados: nao e possivel reconstruir '%s'"
            % (entry.get("name") or entry.get("path") or "?")
        )

    block_size = int(entry.get("block_size") or DEFAULT_SECTOR_SIZE)
    sector_size = int(entry.get("sector_size") or DEFAULT_SECTOR_SIZE)
    partition_offset = int(entry.get("partition_offset") or 0)
    size = int(entry.get("size") or 0)
    if size <= 0:  # tamanho desconhecido: escreve todos os clusters alocados
        size = sum(int(run["count"]) for run in runs) * block_size

    os.makedirs(output_dir, exist_ok=True)
    destination = _unique_output_path(
        output_dir, sanitize_filename(entry.get("name", ""))
    )

    remaining = size
    with open(device_path, "rb", buffering=0) as device:
        with open(destination, "wb") as output:
            for run in runs:
                if remaining <= 0:
                    break
                offset = partition_offset + int(run["block"]) * block_size
                length = min(int(run["count"]) * block_size, remaining)
                data = _read_aligned(device, offset, length, sector_size)
                if not data:
                    break  # posicao fora do dispositivo
                output.write(data)
                remaining -= len(data)

    return destination
