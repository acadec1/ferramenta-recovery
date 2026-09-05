"""Integridade dos ficheiros recuperados atraves de SHA-256.

O hash de cada ficheiro recuperado permite provar, na cadeia de custodia, que o
conteudo nao foi alterado depois da extraccao.
"""

from __future__ import annotations

import hashlib

CHUNK_SIZE = 1024 * 1024


def compute_hash(file_path: str) -> str:
    """Devolve o SHA-256 do ficheiro, em hexadecimal minusculo."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_integrity(original_hash: str, recovered_file_path: str) -> bool:
    """Compara o SHA-256 do ficheiro recuperado com o hash de referencia."""
    if not original_hash:
        return False
    return compute_hash(recovered_file_path) == original_hash.strip().lower()
