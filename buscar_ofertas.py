#!/usr/bin/env python3
"""
Busca ofertas en la Jobboerse de la Bundesagentur fuer Arbeit,
descarta las que no cumplen los criterios, descarga la descripcion
completa de las que quedan y las guarda listas para que Claude Code
las evalue.

Guarda registro de lo ya visto: en cada ejecucion solo procesa
ofertas nuevas.

Uso:
    python buscar_ofertas.py

Requiere:
    pip install requests
"""

import base64
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
import perfil

try:
    import requests
except ImportError:
    sys.exit("Falta requests. Instalalo con:  pip install requests")


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION — esto es lo unico que necesitas editar
# ══════════════════════════════════════════════════════════════════

_datos = json.loads(
    (Path(__file__).parent / "terminos.json").read_text(encoding="utf-8")
)
BUSQUEDAS = [t for grupo in _datos.values() for t in grupo]

CIUDAD = perfil.CIUDAD
RADIO_KM = 50          # cubre Essen, Duisburg, Neuss, Koeln, Wuppertal...
DIAS = 4              # solo ofertas publicadas en los ultimos N dias
SOLO_VOLLZEIT = True   # False si tambien quieres Teilzeit

# Zeitarbeit = empresas de trabajo temporal (DIS AG, simplecon, Randstad...)
# Publican mucho volumen. True las incluye, False las descarta.
INCLUIR_ZEITARBEIT = False

_exclusiones = json.loads(
    (Path(__file__).parent / "exclusiones.json").read_text(encoding="utf-8")
)
EMPRESAS_EXCLUIDAS = _exclusiones["empresas"]
TITULOS_EXCLUIDOS = [
    t for clave, lista in _exclusiones.items()
    if clave.startswith("titulos_") for t in lista
]

# Siglas cortas que viven dentro de otras palabras: se comparan por
# inicio de palabra, no por substring. La clave NO empieza por
# "titulos_" a proposito, para que no entre en el aplanado de arriba.
SIGLAS_EXCLUIDAS = _exclusiones.get("siglas_titulo", [])

CARPETA_SALIDA = "ofertas"


# ══════════════════════════════════════════════════════════════════
#  Constantes de la API — no tocar
# ══════════════════════════════════════════════════════════════════

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
URL_BUSQUEDA = f"{BASE}/pc/v6/jobs"
URL_DETALLE = f"{BASE}/pc/v4/jobdetails"
CABECERAS = {"X-API-Key": "jobboerse-jobsuche"}

UMLAUTE = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
}


# ══════════════════════════════════════════════════════════════════
#  Funciones
# ══════════════════════════════════════════════════════════════════

def a_ascii(texto):
    """Convierte a nombre de archivo seguro, sin umlaute ni espacios."""
    for original, reemplazo in UMLAUTE.items():
        texto = texto.replace(original, reemplazo)
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto)
    return texto.strip("_")[:60]


def coincide_substring(texto, patrones):
    """
    Busca el patron en cualquier parte del texto.
    Necesario porque el aleman compone al reves: 'Buchhaltung'
    tiene que encontrar 'Finanzbuchhaltung'.
    """
    t = (texto or "").lower()
    for p in patrones:
        if p.lower() in t:
            return p
    return None


def coincide_palabra(texto, patrones):
    """
    Busca el patron solo si empieza una palabra.
    'SEA' encuentra 'SEA Manager' pero no salta dentro de 'reSEArch'.
    El final queda libre: 'SEA' tambien encuentra 'SEA-Kampagnen'.
    """
    if not texto:
        return None
    for p in patrones:
        if re.search(r"\b" + re.escape(p), texto, re.IGNORECASE):
            return p
    return None


def motivo_exclusion(oferta):
    """Devuelve por que se descarta la oferta, o None si sobrevive."""
    empresa = oferta.get("firma", "")
    titulo = oferta.get("stellenangebotsTitel", "")

    hit = coincide_palabra(empresa, EMPRESAS_EXCLUIDAS)
    if hit:
        return f"empresa: {hit}"

    hit = coincide_substring(titulo, TITULOS_EXCLUIDOS)
    if hit:
        return f"titulo: {hit}"

    hit = coincide_palabra(titulo, SIGLAS_EXCLUIDAS)
    if hit:
        return f"sigla: {hit}"

    return None


def buscar(termino):
    """Pide a la API todas las ofertas que coinciden con un termino."""
    resultados = []
    pagina = 1

    while True:
        params = {
            "was": termino,
            "wo": CIUDAD,
            "umkreis": RADIO_KM,
            "veroeffentlichtseit": DIAS,
            "angebotsart": 1,          # 1 = puesto de trabajo
            "size": 100,
            "page": pagina,
        }
        if SOLO_VOLLZEIT:
            params["arbeitszeit"] = "vz"
        if not INCLUIR_ZEITARBEIT:
            params["zeitarbeit"] = "false"

        try:
            r = requests.get(URL_BUSQUEDA, headers=CABECERAS,
                             params=params, timeout=30)
            r.raise_for_status()
            datos = r.json()
        except Exception as e:
            print(f"  ! Error buscando '{termino}': {e}")
            return resultados

        lote = datos.get("ergebnisliste", [])
        resultados.extend(lote)

        total = datos.get("maxErgebnisse", 0)
        if len(resultados) >= total or not lote:
            break

        pagina += 1
        time.sleep(0.3)     # no saturar el servidor

    return resultados


def obtener_detalle(refnr):
    """Descarga el texto completo del anuncio a partir de su referencia."""
    # La API pide la referencia codificada en base64
    codigo = base64.b64encode(refnr.encode()).decode()

    try:
        r = requests.get(f"{URL_DETALLE}/{codigo}",
                         headers=CABECERAS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ! No se pudo obtener detalle de {refnr}: {e}")
        return None


def limpiar_html(texto):
    """Quita etiquetas HTML y espacios sobrantes."""
    if not texto:
        return ""
    texto = re.sub(r"<br\s*/?>", "\n", texto)
    texto = re.sub(r"</p>", "\n\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def escribir_oferta(carpeta, oferta, detalle):
    """Guarda una oferta como archivo de texto plano."""
    titulo = oferta.get("stellenangebotsTitel", "sin_titulo")
    empresa = oferta.get("firma", "sin_empresa")
    fecha = oferta.get("datumErsteVeroeffentlichung", "")
    refnr = oferta.get("referenznummer", "")

    nombre = f"{fecha}_{a_ascii(empresa)}_{a_ascii(titulo)}.txt"
    ruta = carpeta / nombre

    salario = "no indicado"
    if oferta.get("gehaltsspanneVon"):
        desde = oferta["gehaltsspanneVon"]
        hasta = oferta.get("gehaltsspanneBis", "?")
        salario = f"{desde} - {hasta} EUR ({oferta.get('verguetungsangabe', '')})"

    descripcion = ""
    if detalle:
        descripcion = limpiar_html(detalle.get("stellenangebotsBeschreibung"))

    contenido = f"""TITULO:      {titulo}
EMPRESA:     {empresa}
DISTANCIA:   {oferta.get('entfernung', '?')} km
CONTRATO:    {oferta.get('vertragsdauer', '?')}
SALARIO:     {salario}
PUBLICADA:   {fecha}
PROFESION:   {oferta.get('hauptberuf', '')}
REFERENCIA:  {refnr}
ENLACE:      https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}

{'=' * 70}

{descripcion or '[Sin descripcion disponible]'}
"""

    ruta.write_text(contenido, encoding="utf-8")
    return nombre


# ══════════════════════════════════════════════════════════════════
#  Programa principal
# ══════════════════════════════════════════════════════════════════

def main():
    base_dir = Path(__file__).parent
    carpeta = base_dir / CARPETA_SALIDA
    carpeta.mkdir(exist_ok=True)

    registro = carpeta / "_vistas.json"
    vistas = set()
    if registro.is_file():
        vistas = set(json.loads(registro.read_text(encoding="utf-8")))

    print(f"\nBuscando en {RADIO_KM} km de {CIUDAD}, ultimos {DIAS} dias\n")

    # ── 1. Buscar y juntar sin duplicados ────────────────────────
    encontradas = {}
    for termino in BUSQUEDAS:
        lote = buscar(termino)
        nuevas_del_termino = 0
        for oferta in lote:
            ref = oferta.get("referenznummer")
            if ref and ref not in encontradas:
                encontradas[ref] = oferta
                nuevas_del_termino += 1
        print(f"  {termino:.<30} {len(lote):>3} resultados, "
              f"{nuevas_del_termino:>3} nuevos")

    # ── 1b. Aplicar exclusiones antes de bajar descripciones ─────
    total_bruto = len(encontradas)
    descartadas = []
    supervivientes = {}

    for ref, oferta in encontradas.items():
        motivo = motivo_exclusion(oferta)
        if motivo:
            descartadas.append((oferta, motivo))
        else:
            supervivientes[ref] = oferta

    encontradas = supervivientes

    if descartadas:
        print(f"\n{len(descartadas)} descartadas por exclusiones:")
        for oferta, motivo in descartadas[:15]:
            titulo = oferta.get("stellenangebotsTitel", "?")[:45]
            print(f"  - {titulo:<45} [{motivo}]")
        if len(descartadas) > 15:
            print(f"  ... y {len(descartadas) - 15} mas")

    # ── 2. Quedarse solo con lo que no se ha visto antes ─────────
    pendientes = {r: o for r, o in encontradas.items() if r not in vistas}

    print(f"\n{total_bruto} distintas · {len(descartadas)} excluidas · "
          f"{len(pendientes)} sin revisar\n")

    if not pendientes:
        print("Nada nuevo desde la ultima ejecucion.\n")
        return

    # ── 3. Bajar descripcion completa y guardar ──────────────────
    guardadas = []
    for i, (ref, oferta) in enumerate(pendientes.items(), 1):
        detalle = obtener_detalle(ref)
        nombre = escribir_oferta(carpeta, oferta, detalle)
        guardadas.append(nombre)
        print(f"  [{i}/{len(pendientes)}] {nombre}")
        time.sleep(0.3)

    # ── 4. Actualizar el registro ────────────────────────────────
    vistas.update(pendientes.keys())
    registro.write_text(json.dumps(sorted(vistas), indent=2),
                        encoding="utf-8")

    print(f"\n{len(guardadas)} ofertas guardadas en {CARPETA_SALIDA}/")
    print("Listas para evaluar con Claude Code.\n")


if __name__ == "__main__":
    main()
