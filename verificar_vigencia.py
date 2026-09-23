#!/usr/bin/env python3
"""
Borra de ofertas/ las ofertas que ya no estan publicadas.

Uso:
    python verificar_vigencia.py
    python verificar_vigencia.py --aplicar
"""

import re
import sys
import time
from pathlib import Path

import requests

CABECERAS = {"X-API-Key": "jobboerse-jobsuche"}
URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"


def main():
    aplicar = "--aplicar" in sys.argv
    carpeta = Path(__file__).parent / "ofertas"
    archivos = [p for p in sorted(carpeta.glob("*.txt"))
                if not p.name.startswith("_")]
    archivos = [p for p in archivos
                if p.stat().st_mtime < time.time() - 7*86400]

    muertas = []
    for i, ruta in enumerate(archivos, 1):
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^REFERENCIA:\s*(\S+)", texto, re.M)
        if not m:
            continue

        import base64
        codigo = base64.b64encode(m.group(1).encode()).decode()

        try:
            r = requests.get(URL + codigo, headers=CABECERAS, timeout=20)
        except Exception:
            continue

        if r.status_code == 404:
            muertas.append(ruta)
            print(f"  [{i}/{len(archivos)}] 404  {ruta.name[:60]}")

        time.sleep(0.3)

    print(f"\n{len(muertas)} caducadas de {len(archivos)}")

    if not aplicar:
        print("Usa --aplicar para borrarlas.\n")
        return

    for ruta in muertas:
        ruta.unlink()
    print(f"{len(muertas)} borradas.\n")


if __name__ == "__main__":
    main()