import json
import threading
import time
import uuid
from typing import Any, Optional

from app.config import settings

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


class CacheService:
    """Cache compartilhado com Redis e fallback em memória.

    Além do cache comum, expõe primitivas pequenas para lock, contador e TTL.
    Elas são usadas pelo gateway local da TheSportsDB para que API, scheduler e
    workers respeitem o mesmo limite gratuito, em vez de cada processo possuir
    um limitador independente.
    """

    _memory: dict[str, tuple[float, Any]] = {}
    _memory_lock = threading.RLock()
    _client = None
    _last_connect_attempt = 0.0
    _connect_retry_seconds = 10.0

    def __init__(self):
        self.enabled = bool(getattr(settings, "cache_enabled", True))
        self.prefix = getattr(settings, "cache_prefix", "botbet")
        self.redis_url = getattr(settings, "redis_url", "")
        self.default_ttl = int(getattr(settings, "cache_default_ttl_seconds", 300))
        self._ensure_client()

    def _ensure_client(self):
        if not self.enabled or not self.redis_url or redis is None:
            return None
        if CacheService._client is not None:
            return CacheService._client
        now = time.time()
        if now - CacheService._last_connect_attempt < CacheService._connect_retry_seconds:
            return None
        CacheService._last_connect_attempt = now
        try:
            client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=3,
                health_check_interval=30,
            )
            client.ping()
            CacheService._client = client
        except Exception:
            CacheService._client = None
        return CacheService._client

    @property
    def client(self):
        return self._ensure_client()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str, default: Any = None) -> Any:
        if not self.enabled:
            return default

        full_key = self._key(key)
        client = self.client
        if client:
            try:
                raw = client.get(full_key)
                return json.loads(raw) if raw is not None else default
            except Exception:
                CacheService._client = None

        with self._memory_lock:
            item = CacheService._memory.get(full_key)
            if not item:
                return default
            expires_at, value = item
            if expires_at and expires_at < time.time():
                CacheService._memory.pop(full_key, None)
                return default
            return value

    def get_raw(self, key: str, default: Any = None) -> Any:
        """Obtém string/número sem desserializar JSON."""
        if not self.enabled:
            return default
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                value = client.get(full_key)
                return default if value is None else value
            except Exception:
                CacheService._client = None
        with self._memory_lock:
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
        ttl = max(1, int(ttl_seconds or self.default_ttl))
        client = self.client
        if client:
            try:
                client.setex(full_key, ttl, json.dumps(value, ensure_ascii=False, default=str))
                return True
            except Exception:
                CacheService._client = None

        with self._memory_lock:
            CacheService._memory[full_key] = (time.time() + ttl, value)
        return True

    def set_raw(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        if not self.enabled:
            return False
        full_key = self._key(key)
        ttl = max(1, int(ttl_seconds or self.default_ttl))
        client = self.client
        if client:
            try:
                client.setex(full_key, ttl, str(value))
                return True
            except Exception:
                CacheService._client = None
        with self._memory_lock:
            CacheService._memory[full_key] = (time.time() + ttl, str(value))
        return True

    def delete(self, key: str) -> bool:
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                return bool(client.delete(full_key))
            except Exception:
                CacheService._client = None
        with self._memory_lock:
            return CacheService._memory.pop(full_key, None) is not None

    def ttl(self, key: str) -> int:
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                return int(client.ttl(full_key))
            except Exception:
                CacheService._client = None
        with self._memory_lock:
            item = CacheService._memory.get(full_key)
            if not item:
                return -2
            expires_at, _ = item
            return max(-1, int(expires_at - time.time())) if expires_at else -1

    def remember(self, key: str, factory, ttl_seconds: Optional[int] = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value

    def add_once(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Retorna True somente na primeira gravação da chave."""
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                return bool(client.set(full_key, "1", nx=True, ex=max(1, int(ttl_seconds))))
            except Exception:
                CacheService._client = None
        with self._memory_lock:
            item = CacheService._memory.get(full_key)
            if item and (not item[0] or item[0] >= time.time()):
                return False
            CacheService._memory[full_key] = (time.time() + max(1, int(ttl_seconds)), True)
            return True

    def increment(self, key: str, ttl_seconds: int = 60, amount: int = 1) -> int:
        """Incremento atômico compartilhado, com expiração no primeiro uso."""
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                pipe = client.pipeline()
                pipe.incrby(full_key, int(amount))
                pipe.ttl(full_key)
                value, current_ttl = pipe.execute()
                if int(current_ttl) < 0:
                    client.expire(full_key, max(1, int(ttl_seconds)))
                return int(value)
            except Exception:
                CacheService._client = None

        with self._memory_lock:
            now = time.time()
            item = CacheService._memory.get(full_key)
            if not item or (item[0] and item[0] < now):
                value = int(amount)
                expires_at = now + max(1, int(ttl_seconds))
            else:
                expires_at, old_value = item
                value = int(old_value) + int(amount)
            CacheService._memory[full_key] = (expires_at, value)
            return value

    def acquire_lock(self, key: str, ttl_seconds: int = 15, token: Optional[str] = None) -> Optional[str]:
        """Adquire lock distribuído e retorna token para liberação segura."""
        token = token or uuid.uuid4().hex
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                ok = client.set(full_key, token, nx=True, ex=max(1, int(ttl_seconds)))
                return token if ok else None
            except Exception:
                CacheService._client = None

        with self._memory_lock:
            now = time.time()
            item = CacheService._memory.get(full_key)
            if item and (not item[0] or item[0] >= now):
                return None
            CacheService._memory[full_key] = (now + max(1, int(ttl_seconds)), token)
            return token

    def release_lock(self, key: str, token: str) -> bool:
        full_key = self._key(key)
        client = self.client
        if client:
            try:
                script = """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """
                return bool(client.eval(script, 1, full_key, token))
            except Exception:
                CacheService._client = None

        with self._memory_lock:
            item = CacheService._memory.get(full_key)
            if item and str(item[1]) == str(token):
                CacheService._memory.pop(full_key, None)
                return True
            return False
