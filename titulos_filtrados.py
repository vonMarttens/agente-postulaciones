#!/usr/bin/env python3
"""
Segundo filtro mecanico sobre las ofertas YA descargadas en ofertas/.

buscar_ofertas.py filtra antes de bajar, con criterios amplios.
Este script filtra despues, con criterios finos, para que la IA
solo lea lo que vale la pena leer.

NO borra nada: mueve los descartes a ofertas/descartadas/ y escribe
un log con el motivo de cada uno.

NO toca _vistas.json: lo descartado no vuelve a bajarse.

Uso:
    python titulos_filtrados.py              # simulacion, no mueve nada
    python titulos_filtrados.py --aplicar    # mueve de verdad

Requiere:
    solo libreria estandar
"""

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════

CARPETA_OFERTAS = "ofertas"
CARPETA_DESCARTES = "ofertas/descartadas"
ARCHIVO_REGLAS = "exclusiones2.json"


# ══════════════════════════════════════════════════════════════════
#  Carga de reglas
# ══════════════════════════════════════════════════════════════════

def cargar_reglas(base_dir):
    """Lee exclusiones2.json y separa los grupos por tipo de match."""
    ruta = base_dir / ARCHIVO_REGLAS
    if not ruta.is_file():
        sys.exit(f"Falta {ARCHIVO_REGLAS} en {base_dir}")

    datos = json.loads(ruta.read_text(encoding="utf-8"))

    # Cualquier clave que empiece por titulos_ se aplana automaticamente.
    # Agregar un grupo nuevo al JSON no requiere tocar este script.
    titulos = {}
    for clave, lista in datos.items():
        if clave.startswith("titulos_"):
            for termino in lista:
                titulos[termino] = clave

    return {
        "empresas": datos.get("empresas", []),
        "titulos": titulos,
        "siglas": datos.get("siglas_titulo", []),
        "excepciones": datos.get("excepciones_titulo", []),
    }


# ══════════════════════════════════════════════════════════════════
#  Comparacion
# ══════════════════════════════════════════════════════════════════

def coincide_substring(texto, patrones):
    """Busca en cualquier parte. Para compuestos alemanes."""
    t = (texto or "").lower()
    for p in patrones:
        if p.lower() in t:
            return p
    return None


def coincide_palabra(texto, patrones):
    """
    Busca solo si el patron empieza una palabra.
    'YER' encuentra 'YER GmbH' pero no salta dentro de 'Bayer'.
    'MRP' encuentra 'MRP Controller' pero no dentro de otra palabra.
    """
    if not texto:
        return None
    for p in patrones:
        if re.search(r"\b" + re.escape(p), texto, re.IGNORECASE):
            return p
    return None

def normalizar(titulo):
    """
    Quita marcas de genero y ruido para comparar titulos.
    'Controller (m/w/d)' y 'Controller (gn)' cuentan como el mismo.
    Misma logica que muestrear_titulos.py.
    """
    t = titulo or ""
    t = re.sub(r"\(\s*[mwdxa][/\s|,-]*[mwdxa][/\s|,-]*[mwdxa]?\s*\)", "", t, flags=re.I)
    t = re.sub(r"\(\s*all\s+genders?\s*\)", "", t, flags=re.I)
    t = re.sub(r"\(\s*gn\s*\)", "", t, flags=re.I)
    t = re.sub(r"\bm/w/d\b", "", t, flags=re.I)
    t = re.sub(r"[:*/]\s*in\b", "", t)
    t = re.sub(r"[^a-zäöüß0-9]+", " ", t.lower())
    return " ".join(t.split())

def motivo_descarte(titulo, empresa, reglas):
    """Devuelve (motivo, grupo) o (None, None) si la oferta sobrevive."""

    # 1. Empresa. Por palabra, no substring: 'YER' no debe pegar
    #    dentro de 'Bayer'. No admite rescate por excepcion.
    hit = coincide_palabra(empresa, reglas["empresas"])
    if hit:
        return f"empresa: {hit}", "empresas"

    # 2. Rescate. Un titulo en excepciones no se evalua contra las
    #    exclusiones de titulo. Salva compuestos que contienen una
    #    palabra prohibida pero son otro puesto.
    hit = coincide_substring(titulo, reglas["excepciones"])
    if hit:
        return None, None

    # 3. Titulos, por substring.
    hit = coincide_substring(titulo, list(reglas["titulos"].keys()))
    if hit:
        return f"titulo: {hit}", reglas["titulos"][hit]

    # 4. Siglas cortas, por palabra.
    hit = coincide_palabra(titulo, reglas["siglas"])
    if hit:
        return f"sigla: {hit}", "siglas_titulo"

    return None, None


# ══════════════════════════════════════════════════════════════════
#  Lectura de ofertas
# ══════════════════════════════════════════════════════════════════

def leer_cabecera(ruta):
    """
    Extrae TITULO: y EMPRESA: de la cabecera del .txt: todo lo que va
    antes de la linea de ======.

    Se lee del contenido y no del nombre de archivo porque el nombre
    reemplaza espacios y umlaute: 'Michael Page' se guarda como
    'Michael_Page' y ningun patron de dos palabras coincidiria.

    No basta con las primeras lineas: ofertas-filtrar antepone bloques
    (Filtro, Gehalt) que empujan la cabecera hacia abajo.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ! No se pudo leer {ruta.name}: {e}")
        return None, None

    cabecera = texto.split("=" * 70, 1)[0]
    titulo = re.search(r"^TITULO:\s*(.+)$", cabecera, re.M)
    empresa = re.search(r"^EMPRESA:\s*(.+)$", cabecera, re.M)

    return (titulo.group(1).strip() if titulo else "",
            empresa.group(1).strip() if empresa else "")

# ══════════════════════════════════════════════════════════════════
#  Programa principal
# ══════════════════════════════════════════════════════════════════

def main():
    aplicar = "--aplicar" in sys.argv

    base_dir = Path(__file__).parent
    carpeta = base_dir / CARPETA_OFERTAS
    if not carpeta.is_dir():
        sys.exit(f"No existe la carpeta {CARPETA_OFERTAS}/")

    reglas = cargar_reglas(base_dir)
    archivos = sorted(p for p in carpeta.glob("*.txt"))

    if not archivos:
        print(f"\nNo hay .txt en {CARPETA_OFERTAS}/\n")
        return

    modo = "APLICANDO" if aplicar else "SIMULACION (nada se mueve)"
    print(f"\n{len(archivos)} ofertas · {modo}\n")

    descartes = []
    sobreviven = []

    for ruta in archivos:
        titulo, empresa = leer_cabecera(ruta)
        if titulo is None:
            continue

        motivo, grupo = motivo_descarte(titulo, empresa, reglas)
        if motivo:
            descartes.append((ruta, titulo, empresa, motivo, grupo))
        else:
            sobreviven.append((ruta, titulo, empresa))
    
    # ── Deduplicar: misma empresa, mismo titulo normalizado ──────
    vistos = {}
    unicos = []
    for ruta, titulo, empresa in sobreviven:
        if not titulo:  # sin cabecera: nunca se deduplica
            unicos.append((ruta, titulo, empresa))
            continue
        clave = (empresa.lower().strip(), normalizar(titulo))
        if clave in vistos:
            # El nombre empieza por la fecha: el mayor es el mas nuevo
            previa = vistos[clave]
            viejo = min(previa, ruta, key=lambda p: p.name)
            nuevo = max(previa, ruta, key=lambda p: p.name)
            descartes.append((viejo, titulo, empresa,
                              f"duplicado de {nuevo.name}", "duplicados"))
            vistos[clave] = nuevo
            unicos = [x for x in unicos if x[0] != viejo]
            if nuevo not in [x[0] for x in unicos]:
                unicos.append((nuevo, titulo, empresa))
        else:
            vistos[clave] = ruta
            unicos.append((ruta, titulo, empresa))

    sobreviven = unicos

    # ── Resumen por grupo ────────────────────────────────────────
    por_grupo = {}
    for _, _, _, _, grupo in descartes:
        por_grupo[grupo] = por_grupo.get(grupo, 0) + 1

    print("Descartes por grupo:")
    for grupo, n in sorted(por_grupo.items(), key=lambda x: -x[1]):
        print(f"  {grupo:<28} {n:>4}")

    print(f"\n  {'DESCARTADAS':<28} {len(descartes):>4}")
    print(f"  {'SOBREVIVEN':<28} {len(sobreviven):>4}\n")

    # ── Log ──────────────────────────────────────────────────────
    sello = datetime.now().strftime("%Y-%m-%d %H:%M")
    lineas = [f"=== {sello} · {modo} ==="]
    for ruta, titulo, empresa, motivo, _ in descartes:
        lineas.append(f"{titulo}  |  {empresa}  |  {motivo}")
    lineas.append("")

    log = carpeta / "_descartes_log.txt"
    with log.open("a", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    # ── Mover ────────────────────────────────────────────────────
    if not aplicar:
        print("Revisa ofertas/_descartes_log.txt antes de aplicar.")
        print("Para mover de verdad:  python titulos_filtrados.py --aplicar\n")
        return

    destino = base_dir / CARPETA_DESCARTES
    destino.mkdir(parents=True, exist_ok=True)

    for ruta, _, _, _, _ in descartes:
        try:
            shutil.move(str(ruta), str(destino / ruta.name))
        except Exception as e:
            print(f"  ! No se pudo mover {ruta.name}: {e}")

    print(f"{len(descartes)} movidas a {CARPETA_DESCARTES}/")
    print(f"{len(sobreviven)} quedan en {CARPETA_OFERTAS}/ para evaluar.\n")


if __name__ == "__main__":
    main()
