import threading
import time
import logging

logger = logging.getLogger(__name__)


class SimpleCache:
    def __init__(self, default_ttl=300):
        self.cache = {}
        self.default_ttl = default_ttl
        self.lock = threading.RLock()
        self.stats = {"hits": 0, "misses": 0}

    def _is_expired(self, entry):
        return time.time() - entry["timestamp"] > entry["ttl"]

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                self.stats["misses"] += 1
                return None

            entry = self.cache[key]
            if self._is_expired(entry):
                del self.cache[key]
                self.stats["misses"] += 1
                return None

            self.stats["hits"] += 1
            return entry["data"]

    def set(self, key, value, ttl=None):
        with self.lock:
            self.cache[key] = {
                "data": value,
                "timestamp": time.time(),
                "ttl": ttl or self.default_ttl,
            }

    def delete(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def clear_pattern(self, pattern):
        with self.lock:
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self.cache[key]
            return len(keys_to_delete)

    def get_stats(self):
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
        return {
            "size": len(self.cache),
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
        }


# Global cache instance
task_cache = SimpleCache(default_ttl=300)


def get_cached_tasks(username, page=1, limit=10):
    cache_key = f"tasks:{username}:{page}:{limit}"
    cached_data = task_cache.get(cache_key)
    if cached_data:
        logger.info(f"Cache hit for {cache_key} - Stats: {task_cache.get_stats()}")
    else:
        logger.info(f"Cache miss for {cache_key} - Stats: {task_cache.get_stats()}")
    return cached_data


def set_cached_tasks(username, tasks_data, total_count, page=1, limit=10, ttl=300):
    cache_key = f"tasks:{username}:{page}:{limit}"
    cache_data = {"tasks": tasks_data, "total_count": total_count}
    task_cache.set(cache_key, cache_data, ttl)
    logger.info(
        f"Cache set for {cache_key} with {len(tasks_data)} tasks, total: {total_count}"
    )


def clear_cached_tasks(username):
    pattern = f"tasks:{username}:"
    count = task_cache.clear_pattern(pattern)
    logger.info(f"Cleared {count} cache entries for user {username}")


def get_cached_user(username):
    cache_key = f"user:{username}"
    return task_cache.get(cache_key)


def set_cached_user(username, user_data, ttl=600):
    cache_key = f"user:{username}"
    task_cache.set(cache_key, user_data, ttl)
