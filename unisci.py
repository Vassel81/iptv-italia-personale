#!/usr/bin/env python3
"""Unisce playlist M3U pubbliche; mantiene il primo canale per nome normalizzato."""
import re
import urllib.request
from pathlib import Path

SOURCES = [
    "https://forgejo.it/peppenamir/iptv_italia/raw/branch/main/lista.m3u",
    "https://iptv-org.github.io/iptv/countries/it.m3u",
]
OUTPUT = Path("italia-unificata.m3u")

def entries(content):
    meta = None
    extras = []
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            meta, extras = line, []
        elif meta and line.startswith("#"):
            extras.append(line)
        elif meta and line and not line.startswith("#"):
            yield meta, extras, line
            meta, extras = None, []

def key(meta):
    match = re.search(r'tvg-id="([^"]+)"', meta)
    if match and match.group(1).strip():
        return "id:" + match.group(1).strip().casefold()
    name = meta.split(",", 1)[-1].strip().casefold()
    return "name:" + re.sub(r"\s+", " ", name)

def main():
    lines = ["#EXTM3U"]
    seen = set()
    success = 0
    for url in SOURCES:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=35) as response:
                content = response.read().decode("utf-8-sig", errors="replace")
            if "#EXTINF:" not in content:
                raise ValueError("nessun canale M3U trovato")
            count = 0
            for meta, extras, stream in entries(content):
                identifier = key(meta)
                if identifier in seen:
                    continue
                seen.add(identifier)
                lines.extend([meta, *extras, stream])
                count += 1
            print(f"OK: {url}: {count} canali aggiunti")
            success += 1
        except Exception as error:
            print(f"ERRORE: {url}: {error}")
    if success == 0 or len(lines) == 1:
        raise RuntimeError("Nessuna playlist valida: file precedente conservato")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Creato {OUTPUT} con {len(seen)} canali")

if __name__ == "__main__":
    main()
