"""Lokal serverga HTTPS manzil ochish (tunnel).

Nega kerak: Telegram Mini App'ni FAQAT HTTPS manzildan ocha oladi. Sizning
kompyuteringizda esa http://localhost turadi. Tunnel shu localhost ga
tashqaridan ochiladigan `https://...` manzil beradi.

Ikki variant:
  cloudflared — hisob (account) kerak emas, manzil har safar yangilanadi;
  ngrok       — o'rnatilgan va sozlangan bo'lsa ishlatiladi.

Ishlab chiqarishda (production) tunnel kerak emas — doimiy domeningizni
.env dagi WEBAPP_URL ga yozing va TUNNEL=none qiling.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import shutil
from pathlib import Path

import httpx

from app import config

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

_CLOUDFLARED_ASSETS = {
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
    ("Windows", "ARM64"): "cloudflared-windows-arm64.exe",
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
    ("Darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
    ("Darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
}
_RELEASE = "https://github.com/cloudflare/cloudflared/releases/latest/download"


class TunnelError(Exception):
    pass


# --------------------------------------------------------------------------
# cloudflared
# --------------------------------------------------------------------------

def _cloudflared_path() -> Path | None:
    """Tizimda o'rnatilgan yoki .tools/ ga yuklab olingan cloudflared."""
    found = shutil.which("cloudflared")
    if found:
        return Path(found)

    local = config.TOOLS_DIR / ("cloudflared.exe" if platform.system() == "Windows" else "cloudflared")
    return local if local.exists() else None


async def ensure_cloudflared() -> Path:
    """cloudflared ni topadi, bo'lmasa .tools/ ga yuklab oladi (~55 MB)."""
    existing = _cloudflared_path()
    if existing:
        return existing

    key = (platform.system(), platform.machine())
    asset = _CLOUDFLARED_ASSETS.get(key)
    if asset is None:
        raise TunnelError(
            f"Bu platforma uchun cloudflared avtomatik yuklanmaydi ({key}). "
            "Uni qo'lda o'rnating yoki .env da TUNNEL=none qilib WEBAPP_URL yozing."
        )
    if asset.endswith(".tgz"):
        raise TunnelError(
            "macOS uchun: `brew install cloudflared` buyrug'i bilan o'rnating, "
            "keyin run.py ni qayta ishga tushiring."
        )

    config.TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    target = config.TOOLS_DIR / ("cloudflared.exe" if platform.system() == "Windows" else "cloudflared")

    log.info("cloudflared yuklab olinmoqda (~55 MB), bu FAQAT bir marta bo'ladi…")
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        async with client.stream("GET", f"{_RELEASE}/{asset}") as resp:
            resp.raise_for_status()
            tmp = target.with_suffix(".part")
            with open(tmp, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    f.write(chunk)
    tmp.replace(target)
    target.chmod(0o755)
    log.info("cloudflared saqlandi: %s", target)
    return target


async def _start_cloudflared(port: int) -> tuple[asyncio.subprocess.Process, str]:
    exe = await ensure_cloudflared()
    proc = await asyncio.create_subprocess_exec(
        str(exe),
        "tunnel",
        "--url",
        f"http://127.0.0.1:{port}",
        "--no-autoupdate",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def read_url() -> str:
        # cloudflared manzilni loglariga chiqaradi — o'shani ushlaymiz.
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise TunnelError("cloudflared manzil bermay to'xtadi")
            match = _URL_RE.search(line.decode(errors="replace"))
            if match:
                return match.group(0)

    try:
        url = await asyncio.wait_for(read_url(), timeout=60)
    except (asyncio.TimeoutError, TunnelError):
        proc.terminate()
        raise TunnelError("cloudflared 60 soniyada manzil bermadi (internet aloqasini tekshiring)")

    # Qolgan loglarni fonda yutib turamiz, aks holda quvur (pipe) to'lib qoladi.
    asyncio.create_task(_drain(proc))
    return proc, url


async def _drain(proc: asyncio.subprocess.Process) -> None:
    assert proc.stdout is not None
    try:
        while await proc.stdout.readline():
            pass
    except Exception:  # noqa: BLE001 — jarayon yopilganda muhim emas
        pass


# --------------------------------------------------------------------------
# ngrok
# --------------------------------------------------------------------------

async def _start_ngrok(port: int) -> tuple[asyncio.subprocess.Process, str]:
    exe = shutil.which("ngrok")
    if not exe:
        raise TunnelError("ngrok topilmadi. O'rnating yoki .env da TUNNEL=cloudflared qiling.")

    proc = await asyncio.create_subprocess_exec(
        exe, "http", str(port), "--log", "stdout",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    asyncio.create_task(_drain(proc))

    # ngrok manzilni lokal API sida e'lon qiladi.
    for _ in range(30):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                data = (await client.get("http://127.0.0.1:4040/api/tunnels")).json()
            for t in data.get("tunnels", []):
                if t.get("public_url", "").startswith("https://"):
                    return proc, t["public_url"]
        except (httpx.HTTPError, ValueError):
            continue

    proc.terminate()
    raise TunnelError("ngrok manzil bermadi")


# --------------------------------------------------------------------------

async def open_tunnel(port: int) -> tuple[asyncio.subprocess.Process | None, str | None]:
    """Tunnel ochadi. (jarayon, https_url) qaytaradi.

    TUNNEL=none bo'lsa yoki WEBAPP_URL allaqachon to'ldirilgan bo'lsa —
    hech narsa qilmaydi.
    """
    if config.TUNNEL in {"none", "off", ""}:
        return None, None
    if config.TUNNEL == "ngrok":
        return await _start_ngrok(port)
    return await _start_cloudflared(port)
