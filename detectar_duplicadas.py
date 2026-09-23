#!/usr/bin/env python3
"""
Detecta ofertas repetidas comparando el texto del anuncio.

Compara lo que viene DESPUES de la linea de ====== : la descripcion.
No los titulos, que se repiten entre puestos distintos, ni las primeras
lineas, que suelen ser la presentacion de la empresa y son iguales en
todos sus avisos.

Busca en cuatro lugares:
    ofertas/                 las que faltan por puntuar
    ofertas/standby/         3-5 puntos
    ofertas/descartadas/     0-2 puntos y descartes mecanicos
    salidas/*/               las que ya tienen postulacion

Solo mueve archivos de la raiz de ofertas/. Lo demas se lee, no se toca.
Nada se borra: los duplicados van a ofertas/descartadas/.

Uso:
    python detectar_duplicadas.py                  # simulacion
    python detectar_duplicadas.py --aplicar
    python detectar_duplicadas.py --similar 0.95   # ademas, casi identicas

Requiere:
    solo libreria estandar
"""

import hashlib
import re
import shutil
import sys
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).parent
OFERTAS = RAIZ / "ofertas"
STANDBY = OFERTAS / "standby"
DESCARTADAS = OFERTAS / "descartadas"
SALIDAS = RAIZ / "salidas"
SEPARADOR = "=" * 70
LOG = OFERTAS / "_duplicados_log.txt"

# Cuanto texto se compara al buscar parecidos. Suficiente para decidir
# y corto para que no se demore.
TOPE = 4000


def leer(p):
    return p.read_text(encoding="utf-8", errors="replace")


def cuerpo(texto):
    """La descripcion del anuncio, normalizada."""
    partes = texto.split(SEPARADOR, 1)
    cuerpo = partes[1] if len(partes) > 1 else texto
    return " ".join(re.sub(r"[^a-z0-9äöüß ]+", " ", cuerpo.lower()).split())


def huella(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def campo(texto, nombre):
    m = re.search(rf"^{nombre}:\s*(.+)$", texto, re.M)
    return m.group(1).strip() if m else ""


def anuncios_de(carpeta, patron="*.txt"):
    if not carpeta.is_dir():
        return []
    return [p for p in sorted(carpeta.glob(patron)) if not p.name.startswith("_")]


def ficha(ruta, origen):
    texto = leer(ruta)
    cuerpo_norm = cuerpo(texto)
    return {
        "ruta": ruta,
        "origen": origen,
        "empresa": campo(texto, "EMPRESA").lower(),
        "cuerpo": cuerpo_norm,
        "huella": huella(cuerpo_norm),
    }


def main():
    aplicar = "--aplicar" in sys.argv
    umbral = None
    if "--similar" in sys.argv:
        umbral = float(sys.argv[sys.argv.index("--similar") + 1])

    if not OFERTAS.is_dir():
        print(f"No existe {OFERTAS}")
        return 1

    # ── Catalogo: lo que ya fue visto, fuera de la raiz ──────────
    catalogo = []
    for carpeta, origen in ((STANDBY, "standby"), (DESCARTADAS, "descartadas")):
        catalogo += [ficha(p, origen) for p in anuncios_de(carpeta)]
    for p in sorted(SALIDAS.glob("*/stellenanzeige.txt")):
        catalogo.append(ficha(p, f"salidas/{p.parent.name}"))

    # ── La raiz: mas reciente primero, por la fecha del nombre ───
    en_raiz = [p for p in anuncios_de(OFERTAS)
               if re.match(r"^\d{4}-\d{2}-\d{2}", p.name)]
    en_raiz.sort(key=lambda p: p.name, reverse=True)

    por_huella = {f["huella"]: f for f in catalogo}
    duplicadas = []
    conservadas = []

    for ruta in en_raiz:
        f = ficha(ruta, "ofertas")
        gemela = por_huella.get(f["huella"])

        if gemela is None and umbral:
            for otra in conservadas + catalogo:
                if otra["empresa"] != f["empresa"] or not f["empresa"]:
                    continue
                r = SequenceMatcher(None, f["cuerpo"][:TOPE],
                                    otra["cuerpo"][:TOPE]).ratio()
                if r >= umbral:
                    gemela = otra
                    break

        if gemela is None:
            por_huella[f["huella"]] = f
            conservadas.append(f)
        else:
            duplicadas.append((f, gemela))

    # ── Informe ──────────────────────────────────────────────────
    print(f"\n{len(en_raiz)} en la raíz · {len(catalogo)} ya vistas en otras carpetas")
    print(f"{len(duplicadas)} duplicadas\n")

    lineas = []
    for f, gemela in duplicadas:
        donde = gemela["origen"]
        if donde == "ofertas":
            donde = f"ofertas/{gemela['ruta'].name}"
        print(f"  {f['ruta'].name[:70]}\n      = {donde}")
        lineas.append(f"{f['ruta'].name}  |  duplicada de  |  {donde}")

    if not aplicar:
        print("\nNada cambió. Para aplicar: python detectar_duplicadas.py --aplicar\n")
        return 0

    if duplicadas:
        DESCARTADAS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as g:
            g.write("\n".join(lineas) + "\n")
        for f, _ in duplicadas:
            shutil.move(str(f["ruta"]), str(DESCARTADAS / f["ruta"].name))
        print(f"\n{len(duplicadas)} movidas a ofertas/descartadas/\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())