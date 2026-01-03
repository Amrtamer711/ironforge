"""Cache backends."""

from .memory import MemoryCacheBackend

__all__ = ["MemoryCacheBackend"]

# Redis backend is optional - import only if redis is installed
try:
    from .redis import RedisCacheBackend

    __all__.append("RedisCacheBackend")
except ImportError:
    pass
