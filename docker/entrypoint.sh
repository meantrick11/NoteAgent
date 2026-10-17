#!/bin/sh
set -e

mkdir -p notes var/logs chromadb_persist uploads
alembic upgrade head
exec python main.py
