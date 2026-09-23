#!/usr/bin/env python3
"""
Muestra en qué etapa está cada postulación de salidas/.

No modifica nada. Solo lee y reporta.

Es la entrada de todo el ciclo de envío: las skills que trabajan sobre
salidas/ empiezan corriendo `python cola.py --rutas` y actúan solo
sobre las carpetas del estado que les toca. Calcular el estado aquí es
gratis; que lo redescubra un agente carpeta por carpeta cuesta tokens.

El estado sale de lo que hay en disco, sin archivo de control:
  - cv_fallido.txt                             -> el CV automatico fallo
  - CV o carta sin compilar                    -> falta generarlos
  - stellenanzeige.txt sin el bloque de datos  -> falta el captcha
  - CV sin carta y sin GEHALTSVORSTELLUNG      -> falta el sueldo
  - segun BEWERBUNG VIA / KONTAKT / BEWERBUNG URL, la postulacion va
    por correo, por portal, o no tiene via -> hay que buscarla a mano
  - bewerbung_gesendet.txt con GESENDET AM: -
      sin ANHANG AM                            -> borrador sin adjuntos
      con ANHANG AM                            -> borrador listo
  - con fecha                                  -> enviada
  - con NACHGEFASST AM                         -> ya se insistio una vez

Los documentos se revisan antes que el captcha: ofertas-filtrar crea la
carpeta solo con stellenanzeige.txt, el CV se genera de noche y el captcha
se resuelve por la mañana, sobre carpetas que ya tienen CV.

ANHANG AM lo escribe solo adjuntar_borradores.py, despues de releer el
borrador en Gmail y confirmar que los adjuntos estan. Por eso cola.py
puede fiarse de el sin consultar Gmail.

Uso:
    python cola.py
    python cola.py --rutas     # una linea por carpeta, para encadenar

Requiere:
    solo libreria estandar
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path


CARPETA_SALIDAS = "salidas"
MARCA = "# ── Datos verificados a mano ──"
REGISTRO = "bewerbung_gesendet.txt"
FALLIDO_CV = "cv_fallido.txt"
CORREO = "correo.txt"
FALLIDO_CARTA = "anschreiben_fallido.txt"

# Dias tras los cuales una postulacion enviada se marca para revisar.
DIAS_SEGUIMIENTO = 14


# ══════════════════════════════════════════════════════════════════
#  Lectura
# ══════════════════════════════════════════════════════════════════

def campo(texto, nombre):
    m = re.search(rf"^{re.escape(nombre)}:\s*(.+)$", texto, re.M)
    if not m:
        return ""
    valor = m.group(1).strip()
    return "" if valor == "-" else valor

def pide_gehalt(texto):
    """
    El anuncio o el formulario de contacto piden la expectativa salarial.

    Se busca en el cuerpo del anuncio y en ANLAGEN, nunca en todo el
    archivo: la linea GEHALTSVORSTELLUNG del bloque Gehalt contiene la
    misma palabra y haria creer que siempre la piden.
    """
    cuerpo = texto.split("=" * 70, 1)[-1]
    patron = r"gehaltsvorstellung|gehaltswunsch|salary expectation"
    return bool(re.search(patron, cuerpo, re.I) or
                re.search(patron, campo(texto, "ANLAGEN"), re.I))

def es_correo(valor):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", valor or ""))


def dias_desde(texto_fecha):
    """Dias transcurridos desde una fecha AAAA.MM.DD o AAAA-MM-DD."""
    for fmt in ("%Y.%m.%d", "%Y-%m-%d"):
        try:
            d = datetime.strptime(texto_fecha, fmt).date()
            return (date.today() - d).days
        except ValueError:
            continue
    return None


# ══════════════════════════════════════════════════════════════════
#  Clasificacion
# ══════════════════════════════════════════════════════════════════

def clasificar(carpeta):
    """Devuelve (estado, detalle) para una carpeta de postulacion."""
    anuncio = carpeta / "stellenanzeige.txt"
    if not anuncio.is_file():
        return "SIN ANUNCIO", "falta stellenanzeige.txt"

    texto = anuncio.read_text(encoding="utf-8", errors="replace")

    # ── Documentos, antes que el captcha ─────────────────────────
    hay_cv = any(carpeta.glob("lebenslauf_*.pdf"))
    hay_carta = any(carpeta.glob("Anschreiben_*.pdf"))

    fallido = carpeta / FALLIDO_CV
    if fallido.is_file():
        lineas = fallido.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return "CV FALLIDO", lineas[0] if lineas else "sin motivo"

    if not hay_cv and not hay_carta:
        return "SIN DOCUMENTOS", campo(texto, "EMPRESA")

    if hay_carta and not hay_cv:
        return "FALTA CV", "el .typ no compiló"

    # ── Captcha ──────────────────────────────────────────────────
    if MARCA not in texto:
        return "PENDIENTE CAPTCHA", ""

    via = campo(texto, "BEWERBUNG VIA")
    kontakt = campo(texto, "KONTAKT")
    url = campo(texto, "BEWERBUNG URL")

    if "nicht mehr" in via.lower():
        return "CADUCADA", "el anuncio ya no existe"

    # ── Registro de envio ────────────────────────────────────────
    registro = carpeta / REGISTRO
    if registro.is_file():
        reg = registro.read_text(encoding="utf-8", errors="replace")
        fecha = campo(reg, "GESENDET AM")

        if not fecha:
            anhang = campo(reg, "ANHANG AM")
            if not anhang:
                return "BORRADOR SIN ANHANG", kontakt or "sin contacto"
            return "BORRADOR LISTO", f"adjuntos verificados {anhang}"

        d = dias_desde(fecha)
        canal = campo(reg, "VIA")
        nachgefasst = campo(reg, "NACHGEFASST AM")

        detalle = fecha
        if canal:
            detalle += f" · {canal}"
        if d is not None:
            detalle += f" · hace {d}d"

        # En Alemania se insiste una vez, no dos. Si ya hay
        # NACHGEFASST AM, la carpeta no vuelve a pedir accion.
        if nachgefasst:
            return "ENVIADA · NACHGEFASST", detalle + f" · insistido {nachgefasst}"

        if d is not None and d >= DIAS_SEGUIMIENTO:
            return "ENVIADA · REVISAR", detalle

        return "ENVIADA", detalle

    if hay_cv and not hay_carta:
        fallida = carpeta / FALLIDO_CARTA
        if fallida.is_file():
            lineas = fallida.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            return "ANSCHREIBEN FALLIDO", lineas[0] if lineas else "sin motivo"
        return "LISTA PARA ANSCHREIBEN", kontakt or "sin contacto"

    # ── Sueldo: solo si el anuncio lo pide. Va en el correo o en el
    #    portal, no en la carta, así que el freno está aquí. ────────
    if pide_gehalt(texto) and not campo(texto, "GEHALTSVORSTELLUNG"):
        return "FALTA GEHALT", campo(texto, "GEHALT QUELLE") or "el anuncio lo pide y no hay cifra"

    # ── Con CV y carta: por dónde se postula ─────────────────────
    redactado = (carpeta / CORREO).is_file()

    if es_correo(kontakt) and ("mail" in via.lower() or not via):
        return ("CORREO LISTO" if redactado else "ENVIAR POR CORREO"), kontakt

    if url:
        return "POSTULAR POR PORTAL", url

    if es_correo(kontakt):
        return ("CORREO LISTO" if redactado else "ENVIAR POR CORREO"), f"{kontakt} (vía: {via or '?'})"

    if url:
        return "POSTULAR POR PORTAL", url

    if es_correo(kontakt):
        return "ENVIAR POR CORREO", f"{kontakt} (vía: {via or '?'})"

    return "SIN VÍA", f"ni correo ni URL · {via or 'vía desconocida'}"


# ══════════════════════════════════════════════════════════════════
#  Salida
# ══════════════════════════════════════════════════════════════════

ORDEN = [
    "PENDIENTE CAPTCHA",
    "FALTA GEHALT",
    "LISTA PARA ANSCHREIBEN",
    "ANSCHREIBEN FALLIDO",
    "FALTA CV",
    "SIN DOCUMENTOS",
    "CV FALLIDO",
    "ENVIAR POR CORREO",
    "CORREO LISTO",
    "POSTULAR POR PORTAL",
    "SIN VÍA",
    "BORRADOR SIN ANHANG",
    "BORRADOR LISTO",
    "ENVIADA · REVISAR",
    "ENVIADA",
    "ENVIADA · NACHGEFASST",
    "CADUCADA",
    "SIN ANUNCIO",
]

# Los estados hasta ENVIADA · REVISAR, incluido, esperan accion de
# Usuario o de una skill. Los de mas abajo no. Se calcula desde la
# lista para que agregar un estado arriba no lo descuadre.
ACCIONABLES = ORDEN.index("ENVIADA · REVISAR") + 1

SIGUIENTE = {
    "PENDIENTE CAPTCHA":
        "python extraer_kontakt.py --todas --aplicar",
    "FALTA GEHALT":
        "escribir GEHALTSVORSTELLUNG a mano en stellenanzeige.txt",
    "LISTA PARA ANSCHREIBEN":
        "skill creacion_anschreiben (de noche, en modo automático)",
    "ANSCHREIBEN FALLIDO":
        "leer anschreiben_fallido.txt, hacer la carta a mano y borrar anschreiben_fallido.txt",
    "FALTA CV":
        "recompilar: typst compile --root ..\\.. lebenslauf_*.typ",
    "SIN DOCUMENTOS":
        "skill cv-adaptar-oferta (de noche, en modo automático)",
    "CV FALLIDO":
        "leer cv_fallido.txt, hacer el CV a mano y borrar cv_fallido.txt",
    "ENVIAR POR CORREO":
        "skill enviar-postulacion, modo A",
    "CORREO LISTO":
        "python crear_borrador.py --aplicar",
    "POSTULAR POR PORTAL":
        "postular a mano en la URL y escribir bewerbung_gesendet.txt",
    "SIN VÍA":
        "abrir el anuncio y buscar cómo se postula",
    "BORRADOR SIN ANHANG":
        "python adjuntar_borradores.py --aplicar",
    "BORRADOR LISTO":
        "revisar el borrador en Gmail y enviarlo · luego modo B",
    "ENVIADA · REVISAR":
        "skill enviar-postulacion, modo D (Nachfassen)",
    "ENVIADA":
        "nada, esperar",
    "ENVIADA · NACHGEFASST":
        "nada, ya se insistió una vez",
    "CADUCADA":
        "archivar o borrar la carpeta",
    "SIN ANUNCIO":
        "copiar la oferta de ofertas/ como stellenanzeige.txt",
}


def main():
    solo_rutas = "--rutas" in sys.argv

    raiz = Path(__file__).parent / CARPETA_SALIDAS
    if not raiz.is_dir():
        print(f"No existe la carpeta {CARPETA_SALIDAS}/")
        return 1

    carpetas = sorted(p for p in raiz.iterdir() if p.is_dir())
    if not carpetas:
        print(f"No hay postulaciones en {CARPETA_SALIDAS}/")
        return 0

    grupos = {}
    for c in carpetas:
        estado, detalle = clasificar(c)
        grupos.setdefault(estado, []).append((c, detalle))

    if solo_rutas:
        for estado in ORDEN:
            for c, _ in grupos.get(estado, []):
                print(f"{estado}\t{c}")
        for estado, items in grupos.items():
            if estado not in ORDEN:
                for c, _ in items:
                    print(f"{estado}\t{c}")
        return 0

    print()
    for estado in ORDEN:
        items = grupos.get(estado)
        if not items:
            continue
        print(f"{estado} ({len(items)})")
        print(f"  → {SIGUIENTE[estado]}")
        for c, detalle in items:
            linea = f"    {c.name}"
            if detalle:
                linea += f"\n        {detalle[:66]}"
            print(linea)
        print()

    # Estados que no estan en ORDEN (por si aparece alguno nuevo)
    for estado, items in grupos.items():
        if estado in ORDEN:
            continue
        print(f"{estado} ({len(items)})  ← estado no previsto")
        for c, detalle in items:
            print(f"    {c.name}   {detalle}")
        print()

    pendientes = sum(len(grupos.get(e, [])) for e in ORDEN[:ACCIONABLES])
    print(f"Total: {len(carpetas)} postulaciones · {pendientes} esperan acción\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
