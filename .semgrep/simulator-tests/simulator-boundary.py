import asyncio
import importlib

import httpx

module_name = "untrusted"
handler = None

# ruleid: tailtag.simulator.forbidden-import
import django

# ruleid: tailtag.simulator.forbidden-import
import django.db

# ruleid: tailtag.simulator.forbidden-import
from django.db import models

# ruleid: tailtag.simulator.forbidden-import
import rest_framework

# ruleid: tailtag.simulator.forbidden-import
from rest_framework import serializers

# ruleid: tailtag.simulator.forbidden-import
import psycopg

# ruleid: tailtag.simulator.forbidden-import
import psycopg2

# ruleid: tailtag.simulator.forbidden-import
import asyncpg

# ruleid: tailtag.simulator.forbidden-import
import sqlalchemy

# ruleid: tailtag.simulator.forbidden-import
from sqlalchemy.orm import Session

# ruleid: tailtag.simulator.forbidden-import
import clerk_backend_api

# ruleid: tailtag.simulator.forbidden-import
from clerk_backend_api import Clerk

# ok: tailtag.simulator.forbidden-import
import httpx

# ok: tailtag.simulator.forbidden-import
import asyncio

# ok: tailtag.simulator.forbidden-import
from httpx import AsyncClient

# ok: tailtag.simulator.forbidden-import
import djangoish

# ruleid: tailtag.simulator.dynamic-import
importlib.import_module(module_name)
# ruleid: tailtag.simulator.dynamic-import
importlib.import_module("json")
# ruleid: tailtag.simulator.dynamic-import
__import__(module_name)
# ok: tailtag.simulator.dynamic-import
importlib.metadata.version("httpx")
# ok: tailtag.simulator.dynamic-import
asyncio.run(handler())

# ruleid: tailtag.simulator.mock-transport
httpx.MockTransport(handler)
# ruleid: tailtag.simulator.mock-transport
httpx.AsyncClient(transport=httpx.MockTransport(handler))
# ok: tailtag.simulator.mock-transport
httpx.AsyncClient(timeout=5.0, follow_redirects=False)
# ok: tailtag.simulator.mock-transport
httpx.AsyncHTTPTransport()
