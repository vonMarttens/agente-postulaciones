#!/usr/bin/env python3
"""
Revisa contra la API si las ofertas siguen publicadas.

  ofertas/   las de mas de 7 dias sin puntuar: borra las caducadas
  salidas/   todas las carpetas sin caducada.txt: nunca borra, escribe
             caducada.txt con la fecha y si caduco antes o despues de postular

Uso:
    python verificar_vigencia.py              # simulacion
    python verificar_vigencia.py --aplicar
"""

import base64
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

from cola import CARPETA_SALIDAS, MARCADOR_CADUCADA, fecha_envio


CABECERAS = {"X-API-Key": "jobboerse-jobsuche"}
URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"


def consultar(texto):
    """Devuelve VIVA, CADUCADA, SIN REFERENCIA o ERROR <motivo>."""
    m = re.search(r"^REFERENCIA:\s*(\S+)", texto, re.M)
    if not m:
        return "SIN REFERENCIA"
    codigo = base64.b64encode(m.group(1).encode()).decode()
    time.sleep(0.3)
    try:
        r = requests.get(URL + codigo, headers=CABECERAS, timeout=20)
    except Exception as e:
        return f"ERROR {type(e).__name__}"
    if r.status_code == 404:
        return "CADUCADA"
    if r.status_code == 200:
        return "VIVA"
    return f"ERROR {r.status_code}"


def momento(carpeta):
    enviada = fecha_envio(carpeta)
    return f"después de postular (enviada {enviada})" if enviada else "antes de postular"


def marcar_caducada(carpeta):
    """Escribe caducada.txt. Devuelve el momento, para mostrarlo."""
    cuando = momento(carpeta)
    (carpeta / MARCADOR_CADUCADA).write_text(
        f"CADUCADA AM: {date.today():%Y.%m.%d}\n"
        f"MOMENTO:     {cuando}\n", encoding="utf-8")
    return cuando


def revisar_ofertas(aplicar, errores):
    carpeta = Path(__file__).parent / "ofertas"
    archivos = [p for p in sorted(carpeta.glob("*.txt"))
                if not p.name.startswith("_")
                and p.stat().st_mtime < time.time() - 7*86400]

    muertas = []
    for i, ruta in enumerate(archivos, 1):
        estado = consultar(ruta.read_text(encoding="utf-8", errors="replace"))
        if estado == "CADUCADA":
            muertas.append(ruta)
            print(f"  [{i}/{len(archivos)}] 404  {ruta.name[:60]}")
        elif estado.startswith("ERROR"):
            errores.append(f"{ruta.name[:60]}: {estado}")

    print(f"\nofertas/: {len(muertas)} caducadas de {len(archivos)}")
    if aplicar:
        for ruta in muertas:
            ruta.unlink()
        print(f"{len(muertas)} borradas.")


def revisar_salidas(aplicar, errores):
    raiz = Path(__file__).parent / CARPETA_SALIDAS
    if not raiz.is_dir():
        return
    carpetas = [c for c in sorted(raiz.iterdir())
                if c.is_dir()
                and (c / "stellenanzeige.txt").is_file()
                and not (c / MARCADOR_CADUCADA).is_file()]

    muertas = 0
    for i, c in enumerate(carpetas, 1):
        estado = consultar((c / "stellenanzeige.txt").read_text(encoding="utf-8", errors="replace"))
        if estado == "CADUCADA":
            muertas += 1
            cuando = marcar_caducada(c) if aplicar else momento(c)
            print(f"  [{i}/{len(carpetas)}] 404  {c.name[:50]} · {cuando}")
        elif estado.startswith("ERROR"):
            errores.append(f"{c.name[:60]}: {estado}")

    print(f"\nsalidas/: {muertas} caducadas de {len(carpetas)}")


def main():
    aplicar = "--aplicar" in sys.argv
    errores = []
    revisar_ofertas(aplicar, errores)
    revisar_salidas(aplicar, errores)

    if errores:
        print(f"\n{len(errores)} sin respuesta clara de la API:")
        for e in errores:
            print(f"  {e}")

    if not aplicar:
        print("\nSimulación. Usa --aplicar para borrar en ofertas/ y marcar en salidas/.\n")


if __name__ == "__main__":
    main()