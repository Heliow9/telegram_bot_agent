from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


@contextmanager
def locked_json(path: Path, default_factory: Callable[[], Any]):
    """Abre/atualiza JSON com lock de arquivo entre processos.

    Necessário porque APScheduler pode estar rodando em mais de um processo
    (web + worker, ou dois workers). Sem lock, dois processos podem ler a
    mesma lista de enviados antes de qualquer um gravar, causando duplicidade.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default_factory(), ensure_ascii=False), encoding="utf-8")

    with path.open("r+", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            raw = fh.read().strip()
            try:
                data = json.loads(raw) if raw else default_factory()
            except json.JSONDecodeError:
                data = default_factory()

            if data is None or not isinstance(data, type(default_factory())):
                data = default_factory()

            yield data

            fh.seek(0)
            fh.truncate()
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
