
import json
import re
import logging
import os
import redis

logging.basicConfig(level=logging.INFO)

redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, db=0)


def sanitize_key(key_str):

    key_str = key_str.replace(" ", "_")  # Replace spaces
    key_str = re.sub(r"[^\w:\-\.]", "_", key_str)  # Keep alphanumerics, :, -, _
    return key_str


def cache_key(func_name: str, **kwargs) -> str:
    """Build a stable Redis key from an explicit function name and arguments."""
    param_str = ",".join(f"{name}={value}" for name, value in kwargs.items())
    return sanitize_key(f"{func_name}:{param_str}")


def get_from_cache(key: str):
    val = redis_client.get(key)
    if val:
        return json.loads(val)
    return None


def set_to_cache(key: str, data, ttl=600):
    """
        Default ttl is 600 seconds = 10 minutes
    """

    try:
        value = json.dumps(data)
        redis_client.set(key, value, ex=ttl)
    except redis.RedisError as e:
        logging.error(f"Redis error: {e}")
    except (TypeError, ValueError) as e:
        logging.error(f"Serialization error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
