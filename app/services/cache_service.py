import json
import time
from typing import Any, Optional

from app.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class CacheService:
    """Cache com Redis quando disponível e fallback em memória.

    Uso principal: reduzir chamadas repetidas para APIs de odds/jogos e impedir
    alertas duplicados entre processos.
    """

    _memory: dict[str, tuple[float, Any]] = {}
    _client = None

    def __init__(self):
        self.enabled = bool(getattr(settings, "cache_enabled", True))
        self.prefix = getattr(settings, "cache_prefix", "botbet")
        self.redis_url = getattr(settings, "redis_url", "")
        self.default_ttl = int(getattr(settings, "cache_default_ttl_seconds", 300))

        if self.enabled and self.redis_url and redis and CacheService._client is None:
            try:
                CacheService._client = redis.from_url(self.redis_url, decode_responses=True)
                CacheService._client.ping()
            except Exception:
                CacheService._client = None

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        if not self.enabled:
            return default

        full_key = self._key(key)
        if CacheService._client:
            try:
                raw = CacheService._client.get(full_key)
                return json.loads(raw) if raw is not None else default
            except Exception:
                return default

        item = CacheService._memory.get(full_key)
        if not item:
            return default
        expires_at, value = item
        if expires_at and expires_at < time.time():
            CacheService._memory.pop(full_key, None)
            return default
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        if not self.enabled:
            return False

        full_key = self._key(key)
        ttl = int(ttl_seconds or self.default_ttl)
        if CacheService._client:
            try:
                CacheService._client.setex(full_key, ttl, json.dumps(value, ensure_ascii=False, default=str))
                return True
            except Exception:
                return False

        CacheService._memory[full_key] = (time.time() + ttl, value)
        return True

    def remember(self, key: str, factory, ttl_seconds: Optional[int] = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    def add_once(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Retorna True só na primeira gravação da chave.

        Útil para deduplicar alertas quando há múltiplos processos.
        """
        full_key = self._key(key)
        if CacheService._client:
            try:
                return bool(CacheService._client.set(full_key, "1", nx=True, ex=ttl_seconds))
            except Exception:
                pass
        if self.get(key) is not None:
            return False
        self.set(key, True, ttl_seconds=ttl_seconds)
        return True
