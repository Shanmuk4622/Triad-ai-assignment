"""Start the Docker app. A standalone container can run its own local MongoDB."""

import os
import secrets
import subprocess
import time
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure


def start_local_mongo():
    data_dir = Path(os.environ.get("MONGO_DATA_DIR", "/home/dms/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    mongo = subprocess.Popen(["mongod", "--bind_ip", "127.0.0.1", "--dbpath", str(data_dir)])
    os.environ["MONGO_URI"] = "mongodb://127.0.0.1:27017"
    with MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=1000) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and mongo.poll() is None:
            try:
                client.admin.command("ping")
                return
            except ConnectionFailure:
                time.sleep(0.25)
    if mongo.poll() is None:
        mongo.terminate()
        mongo.wait(timeout=10)
    raise SystemExit("Local MongoDB failed to start.")


def main():
    if not os.environ.get("SECRET_KEY"):
        os.environ["SECRET_KEY"] = secrets.token_hex(32)
    if not os.environ.get("MONGO_URI"):
        start_local_mongo()
    os.execvp("gunicorn", ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "450", "dms:create_app()"])


if __name__ == "__main__":
    main()
