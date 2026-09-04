import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess  # nosec B404 - fixed local commands only
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .integration_contract import contract as integration_contract
from .integrations import get_integration, snapshot as integrations_snapshot, valid_registration_token
from .key_store import consume, create_key, delete_key, list_keys, set_active, update_limits, valid_key
from .metrics import snapshot
from .model_manager import ModelManager, ModelProfile
from .phobos_api import router as phobos_router
from .provider_registry import providers as vpn_providers
from .providers import complete, configured_providers, detect_provider_key, test_provider_key
from .vps_manager import add_vps, audit, delete_vps, detect, list_vps, safe_restart

ADMIN_KEY = os.getenv("XFI_AI_ADMIN_KEY", "")
ADMIN_SESSION_TTL = 15 * 60
ADMIN_LOGIN_WINDOW = 60.0
ADMIN_LOGIN_MAX_ATTEMPTS = 5

# Keep the model manager at the gateway boundary. Provider calls remain behind
# app.providers, so existing provider configuration and /api/keys semantics stay intact.
MODEL_MANAGER = ModelManager()


def _configured_model_profiles() -> tuple[ModelProfile, ...]:
    profiles: list[ModelProfile] = []
    for provider in configured_providers():
        profiles.append(ModelProfile(provider.name, provider.model, ("ai", "support"), max(1, 100 - provider.priority * 5)))
    return tuple(profiles)


def _model_snapshot() -> list[dict]:
    profiles = _configured_model_profiles()
    manager = ModelManager(profiles or MODEL_MANAGER.profiles)
    return manager.snapshot()
