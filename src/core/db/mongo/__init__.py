"""MongoDB: подключение (``client``) и хранилище лотов (``storage``)."""

from core.db.mongo.client import create_client
from core.db.mongo.storage import MongoStorage, new_run_id

__all__ = ["MongoStorage", "create_client", "new_run_id"]
