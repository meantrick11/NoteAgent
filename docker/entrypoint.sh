#!/bin/sh
set -e

mkdir -p notes var/logs chromadb_persist
alembic upgrade head
exec python main.py
