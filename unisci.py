#!/usr/bin/env python3
"""Aggiorna playlist M3U e verifica i link senza cancellare canali incerti."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import urllib.error
import urllib.request

SOURCES = [
    "https://forgejo.it/peppenamir/iptv_italia/raw/branch/main/lista.m3u",
    "https://iptv-org.github.io/iptv/countries/it.m3u",
]
OUTPUT = Path("italia-unificata.m3u")
REPORT = Path("controllo-canali.txt")
HEADERS = {"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1023"}

def entries(content):
    meta, extras = None, []
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            meta, extras = line, []
        elif meta is not None and line.startswith("#"):
            extras.append(line)
        elif meta is not None and line:
            yield (meta, extras, line)
            meta, extras = None, []

def key(meta):
    match = re.search(r'tvg-id="([^"]+)"', meta)
    if match and match.group(1).strip():
        return "id:" + match.group(1).strip().casefold()
    return "name:" + re.sub(r"\s+", " ", meta.split(",", 1)[-1].strip().casefold())

def is_sport(meta):
    group = re.search(r'group-title="([^"]*)"', meta, re.I)
    label = (group.group(1) if group else "").casefold()
    return any(word in label for word in ("sport", "calcio", "football", "tennis", "basket"))

def sport_meta(meta):
    if re.search(r'group-title="[^"]*"', meta):
        return re.sub(r'group-title="[^"]*"', 'group-title="Sport"', meta, count=1)
    return meta.replace("#EXTINF:", '#EXTINF: group-title="Sport" ', 1)

def name(meta):
    return meta.split(",", 1)[-1].strip()

def probe(url):
    if not url.startswith(("https://", "http://")):
        return "unknown"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=7) as response:
            status = response.status
            sample = response.read(512)
            if status not in (200, 206):
                return "unknown"
            # Alcuni server restituiscono una pagina HTML invece del flusso.
            if sample.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                return "unknown"
            return "reachable"
    except urllib.error.HTTPError as error:
        # 403, 401 e 429 possono dipendere da token, IP o limiti del server.
        return "missing" if error.code in (404, 410) else "unknown"
    except Exception:
        return "unknown"

def main():
    grouped = defaultdict(list)
    successful = 0
    errors = []
    for source in SOURCES:
        try:
            req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=35) as response:
                body = response.read().decode("utf-8-sig", errors="replace")
            found = list(entries(body))
            if not found:
                raise ValueError("playlist vuota")
            for item in found:
                grouped[key(item[0])].append(item)
            successful += 1
            print(f"Caricati {len(found)} canali da {source}")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    if successful == 0:
        raise RuntimeError("Fonti non disponibili: conservato il file precedente")

    urls = {item[2] for variants in grouped.values() for item in variants}
    results = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(probe, url): url for url in urls}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    output = ["#EXTM3U"]
    sport_extra = 0
    switched, suspected, reachable = [], [], 0
    for variants in grouped.values():
        # Per lo sport preferiamo la classificazione Sport quando disponibile.
        sport_variants = [v for v in variants if is_sport(v[0])]
        primary = sport_variants[0] if sport_variants else variants[0]
        chosen = primary
        state = results.get(primary[2], "unknown")
        if state == "missing":
            replacement = next((v for v in variants[1:]
                                if results.get(v[2]) == "reachable"), None)
            if replacement:
                chosen = replacement
                switched.append(name(primary[0]))
            else:
                suspected.append(name(primary[0]))
        elif state == "unknown":
            suspected.append(name(primary[0]))
        if results.get(chosen[2]) == "reachable":
            reachable += 1
        output.extend([sport_meta(chosen[0]) if sport_variants else chosen[0], *chosen[1], chosen[2]])
        # Mantieni anche flussi sportivi alternativi con URL diversi.
        if sport_variants:
            used = {chosen[2]}
            for alternate in variants:
                if alternate[2] in used:
                    continue
                used.add(alternate[2])
                alt_meta = sport_meta(alternate[0])
                alt_meta = alt_meta.rsplit(",", 1)[0] + "," + name(alternate[0]) + " (alternativa)"
                output.extend([alt_meta, *alternate[1], alternate[2]])
                sport_extra += 1

    OUTPUT.write_text("\n".join(output) + "\n", encoding="utf-8")
    report = [
        "Controllo indicativo dei collegamenti M3U",
        f"Canali pubblicati: {len(grouped) + sport_extra}",
        f"Flussi sportivi alternativi aggiunti: {sport_extra}",
        f"Link che rispondono al test: {reachable}",
        f"Link da verificare nel player: {len(suspected)}",
        f"Link sostituiti con alternativa raggiungibile: {len(switched)}",
        "",
        "Nota: un link che risponde non garantisce la riproduzione; un link",
        "non verificabile può comunque funzionare in APTV.",
        "",
        "Sostituzioni:",
        *(switched or ["Nessuna"]),
        "",
        "Da verificare in APTV:",
        *(suspected or ["Nessuno"]),
        "",
        "Errori delle fonti:",
        *(errors or ["Nessuno"]),
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Pubblicati {len(grouped) + sport_extra} canali, {sport_extra} flussi sportivi aggiuntivi")

if __name__ == "__main__":
    main()
