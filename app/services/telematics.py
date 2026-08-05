"""Telematics integration (machine hours / fuel from fleet providers).

Supported modes:
- simulator: deterministic demo rows (no external credentials needed)
- komatsu: HTTP adapter for Komatsu/KOMTRAX-style API (env-configured)
"""
import json
import os
import random
from typing import Optional
from urllib import request as url_request


def get_mode() -> str:
    return os.getenv("MIRAI_TELEMATICS_MODE", "disabled").lower()


def fetch_machine_data(
    project_code: str,
    target_month: str,
    supplier: Optional[str] = None,
) -> list[dict]:
    mode = get_mode()
    if mode == "simulator":
        return _simulator(project_code, target_month)
    if mode == "komatsu":
        return _komatsu(project_code, target_month, supplier)
    raise ValueError("Telematics integration is disabled (set MIRAI_TELEMATICS_MODE)")


def _simulator(project_code: str, target_month: str) -> list[dict]:
    rng = random.Random(hash((project_code, target_month)) % (2**32))
    machines = [
        ("油圧ショベル PC200", 180.0),
        ("油圧ショベル PC130", 150.0),
        ("クローラクレーン", 90.0),
    ]
    rows = []
    for name, base in machines:
        hours = round(base * rng.uniform(0.85, 1.15), 1)
        fuel_l = round(hours * rng.uniform(11.0, 15.0), 1)
        rows.append({
            "machine_name": name,
            "hours": hours,
            "fuel_l": fuel_l,
            "unit": "h",
        })
    return rows


def _komatsu(
    project_code: str, target_month: str, supplier: Optional[str]
) -> list[dict]:
    base_url = os.getenv("MIRAI_KOMATSU_BASE_URL", "").rstrip("/")
    api_key = os.getenv("MIRAI_KOMATSU_API_KEY", "")
    if not base_url or not api_key:
        raise ValueError("MIRAI_KOMATSU_BASE_URL / MIRAI_KOMATSU_API_KEY are required")
    url = f"{base_url}/machines/hours"
    payload = json.dumps({
        "project_code": project_code,
        "month": target_month,
        "supplier": supplier,
    }).encode()
    req = url_request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with url_request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("machines", [])
