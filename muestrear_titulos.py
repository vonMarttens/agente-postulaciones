#!/usr/bin/env python3
"""
Muestreo semanal de terminologia del mercado laboral.

Baja TODOS los titulos de ofertas publicadas en los ultimos 7 dias
dentro de 10 km de la ciudad de perfil.json, los normaliza y los ordena por
frecuencia.

NO baja descripciones completas: solo titulos. Eso mantiene el coste
bajo y produce un archivo que el subagente `explorador-terminos`
puede leer entero.

Uso:
    python muestrear_titulos.py

Requiere:
    pip install requests
"""

import json
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
import perfil

try:
    import requests
except ImportError:
    sys.exit("Falta requests. Instalalo con:  pip install requests")


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════

CIUDAD = perfil.CIUDAD
RADIO_KM = 10          # muestreo, no busqueda: radio corto a proposito
DIAS = 7               # una semana
SOLO_VOLLZEIT = True
MAX_PAGINAS = 40       # tope de seguridad

CARPETA_SALIDA = "muestreo"

# Grupos de exclusiones.json que se aplican al muestreo.
# NO se usan titulos_nivel_alto ni titulos_formativos a proposito:
# 'Senior Financial Controller' revela que existe 'Financial
# Controller'. El muestreo descubre terminologia, no filtra ofertas.
GRUPOS_RUIDO = [
    "titulos_fuera_perfil",
    "titulos_tecnicos_ajenos",
    "titulos_otros_ajenos",
    "ruido_muestreo",
]

_exc = json.loads(
    (Path(__file__).parent / "exclusiones.json").read_text(encoding="utf-8")
)
RUIDO = [t for g in GRUPOS_RUIDO for t in _exc.get(g, [])]


# ══════════════════════════════════════════════════════════════════
#  Constantes de la API
# ══════════════════════════════════════════════════════════════════

URL_BUSQUEDA = ("https://rest.arbeitsagentur.de/jobboerse/"
                "jobsuche-service/pc/v6/jobs")
CABECERAS = {"X-API-Key": "jobboerse-jobsuche"}


# ══════════════════════════════════════════════════════════════════
#  Funciones
# ══════════════════════════════════════════════════════════════════

def normalizar(titulo):
    """
    Quita las marcas de genero y variantes para que
    'Kreditanalyst (m/w/d)' y 'Kreditanalyst:in' cuenten como el mismo.
    """
    t = titulo

    # (m/w/d), (w/m/d), (m/w/x), (all genders), (gn)...
    t = re.sub(r"\(\s*[mwdxa][/\s|,-]*[mwdxa][/\s|,-]*[mwdxa]?\s*\)", "", t, flags=re.I)
    t = re.sub(r"\(\s*all\s+genders?\s*\)", "", t, flags=re.I)
    t = re.sub(r"\(\s*gn\s*\)", "", t, flags=re.I)
    t = re.sub(r"\bm/w/d\b", "", t, flags=re.I)

    # Kreditanalyst:in / Kreditanalyst*in / Kreditanalyst/in
    t = re.sub(r"[:*/]\s*in\b", "", t)

    # Limpieza final
    t = re.sub(r"\s{2,}", " ", t)
    t = t.strip(" -–—,;·|")

    return t
    
def es_ruido(titulo):
    """True si el titulo cae en una categoria ajena al perfil."""
    t = titulo.lower()
    return any(p.lower() in t for p in RUIDO)

def bajar_titulos():
    """Recorre todas las paginas y devuelve la lista de ofertas."""
    ofertas = []
    pagina = 1

    while pagina <= MAX_PAGINAS:
        params = {
            "wo": CIUDAD,
            "umkreis": RADIO_KM,
            "veroeffentlichtseit": DIAS,
            "angebotsart": 1,
            "size": 100,
            "page": pagina,
        }
        if SOLO_VOLLZEIT:
            params["arbeitszeit"] = "vz"

        try:
            r = requests.get(URL_BUSQUEDA, headers=CABECERAS,
                             params=params, timeout=30)
            r.raise_for_status()
            datos = r.json()
        except Exception as e:
            print(f"  ! Error en pagina {pagina}: {e}")
            break

        lote = datos.get("ergebnisliste", [])
        if not lote:
            break

        ofertas.extend(lote)
        total = datos.get("maxErgebnisse", 0)

        print(f"  pagina {pagina:>2} · {len(ofertas):>4} / {total}")

        if len(ofertas) >= total:
            break

        pagina += 1
        time.sleep(0.3)

    return ofertas


# ══════════════════════════════════════════════════════════════════
#  Programa principal
# ══════════════════════════════════════════════════════════════════

def main():
    base_dir = Path(__file__).parent
    carpeta = base_dir / CARPETA_SALIDA
    carpeta.mkdir(exist_ok=True)

    hoy = date.today().isoformat()

    print(f"\nMuestreo · {RADIO_KM} km de {CIUDAD} · ultimos {DIAS} dias\n")

    ofertas = bajar_titulos()

    if not ofertas:
        print("\nNo se obtuvo ninguna oferta.\n")
        return

    # Contar titulos normalizados
    conteo = Counter()
    ejemplos = {}          # titulo normalizado -> (empresa, refnr)

    for o in ofertas:
        crudo = o.get("stellenangebotsTitel", "")
        if not crudo:
            continue
        limpio = normalizar(crudo)
        if not limpio:
            continue
        conteo[limpio] += 1
        if limpio not in ejemplos:
            ejemplos[limpio] = (
                o.get("firma", "?"),
                o.get("referenznummer", ""),
            )

    # ── Archivo de titulos ordenado por frecuencia ───────────────
    lineas = [
        f"MUESTREO DE TITULOS · {hoy}",
        f"{RADIO_KM} km de {CIUDAD} · ultimos {DIAS} dias",
        f"{len(ofertas)} ofertas · {len(conteo)} titulos distintos",
        "=" * 70,
        "",
    ]

    for titulo, veces in conteo.most_common():
        empresa, ref = ejemplos[titulo]
        lineas.append(f"{veces:>3}x  {titulo}")
        if veces == 1:
            lineas[-1] += f"   [{empresa}]"

    destino = carpeta / f"titulos_{hoy}.txt"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    
        # ── Archivo corto: solo lo que aparece 2 veces o mas ──────────
    repetidos = [(t, v) for t, v in conteo.most_common()
                 if v >= 2 and not es_ruido(t)]
    if repetidos:
        cortas = [
            f"MUESTREO · TITULOS RECURRENTES · {hoy}",
            f"{len(repetidos)} titulos con 2 o mas apariciones "
            f"de {len(conteo)} distintos",
            "=" * 70,
            "",
        ]
        cortas += [f"{v:>3}x  {t}" for t, v in repetidos]
        (carpeta / f"recurrentes_{hoy}.txt").write_text(
            "\n".join(cortas), encoding="utf-8")
        print(f"Recurrentes en {CARPETA_SALIDA}/recurrentes_{hoy}.txt")

    print(f"\n{len(ofertas)} ofertas · {len(conteo)} titulos distintos")
    print(f"Guardado en {CARPETA_SALIDA}/titulos_{hoy}.txt")
    print("\nSiguiente paso: subagente `explorador-terminos`\n")


if __name__ == "__main__":
    main()
