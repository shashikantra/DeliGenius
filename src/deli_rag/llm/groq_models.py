"""Validate configured Groq model IDs against the live /models endpoint.
Unverified IDs are disabled at boot; the app will never route to a model Groq doesn't offer."""
import logging

import httpx

from deli_rag.config.settings import get_config, get_env

log = logging.getLogger(__name__)


def validate_and_filter_llms() -> list[str]:
    cfg = get_config()
    env = get_env()
    enabled: list[str] = []

    try:
        r = httpx.get(
            env.groq_models_endpoint,
            headers={"Authorization": f"Bearer {env.groq_api_key}"},
            timeout=10,
        )
        r.raise_for_status()
        live = {m["id"] for m in r.json().get("data", [])}
    except Exception as e:  # network/auth down — be conservative, disable unverified
        log.warning("Groq /models check failed (%s); only verified=true entries enabled", e)
        live = set()

    for entry in (cfg.llm.primary, cfg.llm.fallback_1, cfg.llm.fallback_2):
        ok = entry.id in live
        if ok:
            enabled.append(entry.id)
        elif entry.verified:
            log.warning("Configured model %s marked verified but NOT in Groq live list", entry.id)
        else:
            log.info("Skipping unverified model %s (not in Groq live list)", entry.id)
    return enabled