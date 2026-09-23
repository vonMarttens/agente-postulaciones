#!/usr/bin/env python3
"""
Extrae el bloque "Informationen zur Bewerbung" de los anuncios de la
Bundesagentur y lo escribe al principio de stellenanzeige.txt.

Abre UN navegador para todas las carpetas del lote. El captcha viaja
como cookie de sesion y se pierde al cerrar Chromium, asi que una
ejecucion por carpeta significa un captcha por carpeta.

Uso:
    python extraer_kontakt.py salidas\\CarpetaA salidas\\CarpetaB
    python extraer_kontakt.py salidas\\CarpetaA --aplicar
    python extraer_kontakt.py --todas --aplicar

Opciones:
    --todas      todas las carpetas de salidas/ sin bloque extraido
    --pausa N    segundos entre ofertas (por defecto 4)
    --aplicar    escribe en stellenanzeige.txt. Sin esto, solo muestra.

Estado por oferta:
    OK           datos extraidos
    EXTERNO      el anuncio redirige a un portal externo
    CADUCADA     la oferta ya no esta publicada
    SIN BLOQUE   no aparecio el bloque de contacto

Los tres primeros no detienen el lote. Si el bloque no aparece se pide
resolver el captcha; a la segunda vez seguida, el lote se detiene. Si
el bloque aparece pero no se lee ningun campo, el lote se detiene de
inmediato: la estructura de la pagina cambio.

Codigos de salida:
    0  termino bien
    1  error de argumentos o de archivos
    3  el bloque no aparecio dos veces seguidas -> lote detenido
    4  el bloque existe pero no se pudo leer -> estructura cambiada
    5  no se pudo escribir en un stellenanzeige.txt

Requiere:
    pip install playwright
    playwright install chromium
"""

import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit("Falta playwright. Instalalo con:\n"
             "  pip install playwright\n"
             "  playwright install chromium")


# ══════════════════════════════════════════════════════════════════
#  CONFIGURACION
# ══════════════════════════════════════════════════════════════════

CARPETA_SALIDAS = "salidas"
PERFIL = "perfil_arbeitsagentur"

PAUSA = 4              # segundos entre ofertas
ESPERA_CORTA = 15000    # ms antes de pedir el captcha
ESPERA_LARGA = 15000   # ms despues del captcha
ESPERA_CAPTCHA = 180000  # ms para resolver el captcha cuando no hay terminal

# Los IDs son semanticos y estables. Los atributos _ngcontent-ng-cXXX
# son hashes de compilacion de Angular: cambian en cada despliegue de
# la Bundesagentur. Nunca seleccionar por ellos.
SELECTORES = {
    "contenedor":     "#detail-bewerbung-container",
    "direccion":      "#detail-bewerbung-adresse",
    "email":          "#detail-bewerbung-mail",
    "telefono":       "[id^='detail-bewerbung-telefon']",
    "metodos":        ".bewerbungsarten li",
    "anlagen":        "#detail-bewerbung-anlagen",
    "url_bewerbung":  "#detail-bewerbung-url",
    "chiffre":        "#detail-bewerbung-chiffre",
    "externo":        "#detail-beschreibung-extern",
    "externo_url":    "#detail-beschreibung-externe-url-btn",
    "caducado":       "#jobdetails-not-found",
}

MARCA_INICIO = "# ── Datos verificados a mano ──"
MARCA_FIN = "# ── Fin datos verificados ──"

# Para distinguir una linea de persona de una de empresa o de calle
# dentro del bloque de direccion.
SUFIJOS_EMPRESA = (r"\b(GmbH|AG|KG|KGaA|SE|mbH|OHG|gGmbH|UG|PartG|e\.?\s?K"
                   r"|Co\.|Holding|Gruppe|Group|Stiftung|Verband|Verein)\b")
PALABRAS_CALLE = (r"(stra[ßs]se|str\.|weg|platz|allee|gasse|ring|damm"
                  r"|ufer|chaussee|hof|markt)")


# ══════════════════════════════════════════════════════════════════
#  Lectura del anuncio
# ══════════════════════════════════════════════════════════════════

def leer_enlace(anuncio):
    texto = anuncio.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^ENLACE:\s*(\S+)", texto, re.M)
    return m.group(1).strip() if m else None


def ya_procesado(anuncio):
    texto = anuncio.read_text(encoding="utf-8", errors="replace")
    return MARCA_INICIO in texto


def escribir(anuncio, bloque):
    """Antepone el bloque al archivo. True si se pudo."""
    try:
        original = anuncio.read_text(encoding="utf-8")
        anuncio.write_text(bloque + original, encoding="utf-8")
        return True
    except Exception as e:
        print(f"  ! No se pudo escribir en {anuncio}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
#  Extraccion
# ══════════════════════════════════════════════════════════════════

def texto_de(page, selector):
    try:
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else None
    except Exception:
        return None


def atributo_de(page, selector, atributo):
    try:
        el = page.query_selector(selector)
        return el.get_attribute(atributo) if el else None
    except Exception:
        return None


def es_caducado(page):
    """La Bundesagentur devuelve su pagina 404 en lugar del anuncio."""
    return page.query_selector(SELECTORES["caducado"]) is not None


def es_externo(page):
    """
    Algunos anuncios no traen datos de contacto: la Bundesagentur solo
    aloja el aviso y redirige a un portal externo. Devuelve la URL de
    ese portal, o None si el anuncio es normal.
    """
    if not page.query_selector(SELECTORES["externo"]):
        return None
    return atributo_de(page, SELECTORES["externo_url"], "href") or "sin URL"


def parece_persona(linea):
    """
    Heuristica debil para una linea sin tratamiento (Herr/Frau).
    'Jessica Geisel' es persona; 'Rhenus Ports Germany',
    'Am Fernmeldeamt 15' y '45145 Essen, Ruhr' no lo son.
    """
    if re.search(r"\d", linea):
        return False
    if re.search(SUFIJOS_EMPRESA, linea, re.I):
        return False
    if re.search(PALABRAS_CALLE, linea, re.I):
        return False
    if "," in linea:
        return False

    palabras = linea.split()
    if not 2 <= len(palabras) <= 4:
        return False
    return all(p[:1].isupper() for p in palabras)


def partir_direccion(bloque):
    """
    El bloque de direccion viene con <br> entre lineas. Dos formas
    vistas en la Jobboerse:

        Golden Brands GmbH                  Rhenus Ports Germany
        Herr Arash Mokhtari - Personalleiter    Jessica Geisel
        Am Fernmeldeamt 15
        45145 Essen, Ruhr

    La primera linea es la empresa. La persona se busca primero por
    tratamiento aleman en cualquier linea; si no aparece, se aplica la
    heuristica debil SOLO a la segunda linea, que es donde va el
    contacto en este formato. Mas abajo empiezan calle y codigo postal
    y el riesgo de falso positivo sube.
    """
    if not bloque:
        return None, None

    lineas = [l.strip() for l in bloque.splitlines() if l.strip()]
    if not lineas:
        return None, None

    persona = None
    for l in lineas[1:]:
        if re.match(r"^(Herr|Frau|Dr\.|Prof\.)\b", l):
            persona = l
            break

    if not persona and len(lineas) > 1 and parece_persona(lineas[1]):
        persona = lineas[1]

    return lineas[0], persona


def extraer(page):
    empresa, persona = partir_direccion(
        texto_de(page, SELECTORES["direccion"]))

    metodos = []
    try:
        for el in page.query_selector_all(SELECTORES["metodos"]):
            t = el.inner_text().strip()
            if t:
                metodos.append(t)
    except Exception:
        pass

    url = atributo_de(page, SELECTORES["url_bewerbung"], "href")

    # La lista de metodos a veces viene vacia aunque exista el boton
    # "Uber Internetseite des Arbeitgebers". Ese boton es el metodo.
    if metodos:
        via = " · ".join(metodos)
    elif url:
        via = "Internetseite des Arbeitgebers"
    else:
        via = None

    return {
        "empresa": empresa,
        "persona": persona,
        "email": texto_de(page, SELECTORES["email"]),
        "telefono": texto_de(page, SELECTORES["telefono"]),
        "via": via,
        "chiffre": texto_de(page, SELECTORES["chiffre"]),
        "url": url,
        "anlagen": texto_de(page, SELECTORES["anlagen"]),
    }


# ══════════════════════════════════════════════════════════════════
#  Formato
# ══════════════════════════════════════════════════════════════════

def bloque_datos(datos):
    def v(x):
        return x if x else "-"
    return "\n".join([
        MARCA_INICIO,
        f"BEWERBUNG VIA:   {v(datos['via'])}",
        f"KONTAKT:         {v(datos['email'])}",
        f"ANSPRECHPARTNER: {v(datos['persona'])}",
        f"TELEFON:         {v(datos['telefono'])}",
        f"CHIFFRE:         {v(datos['chiffre'])}",
        f"BEWERBUNG URL:   {v(datos['url'])}",
        f"ANLAGEN:         {v(datos['anlagen'])}",
        MARCA_FIN,
        "",
    ])


def bloque_externo(url):
    return "\n".join([
        MARCA_INICIO,
        "BEWERBUNG VIA:   Externes Portal",
        "KONTAKT:         -",
        "ANSPRECHPARTNER: -",
        "TELEFON:         -",
        "CHIFFRE:         -",
        f"BEWERBUNG URL:   {url}",
        "ANLAGEN:         -",
        MARCA_FIN,
        "",
    ])


def bloque_caducado():
    return "\n".join([
        MARCA_INICIO,
        "BEWERBUNG VIA:   Anzeige nicht mehr verfügbar",
        "KONTAKT:         -",
        "ANSPRECHPARTNER: -",
        "TELEFON:         -",
        "CHIFFRE:         -",
        "BEWERBUNG URL:   -",
        "ANLAGEN:         -",
        MARCA_FIN,
        "",
    ])


# ══════════════════════════════════════════════════════════════════
#  Una oferta
# ══════════════════════════════════════════════════════════════════

def procesar(page, anuncio, enlace, aplicar):
    """
    Devuelve (estado, corte).
    'corte' es un codigo de salida si el lote debe detenerse, o None.
    """
    try:
        page.goto(enlace, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        return "SIN CARGA", None

    if es_caducado(page):
        if aplicar and not escribir(anuncio, bloque_caducado()):
            return "ERROR", 5
        return "CADUCADA", None

    url_ext = es_externo(page)
    if url_ext:
        if aplicar and not escribir(anuncio, bloque_externo(url_ext)):
            return "ERROR", 5
        return "EXTERNO", None

    # Bloque de contacto: primero sin intervencion
    try:
        page.wait_for_selector(SELECTORES["contenedor"],
                               timeout=ESPERA_CORTA)
    except PWTimeout:
        print("\n  El bloque de contacto no aparecio.")
        print("  Si hay captcha, resuelvelo en la ventana.")
        try:
            input("  Enter cuando el bloque sea visible (o Enter para saltar)... ")
            espera = ESPERA_LARGA
        except EOFError:
            # Sin teclado (lanzado desde el panel): se vigila la pagina y se
            # sigue en cuanto aparece el bloque. No se pregunta isatty():
            # en Windows el dispositivo NUL dice ser una terminal.
            print(f"\n  Sin teclado: esperando hasta {ESPERA_CAPTCHA // 1000} s "
                  "a que se resuelva el captcha...")
            espera = ESPERA_CAPTCHA

    datos = extraer(page)

    # El contenedor existia pero no se leyo nada: los IDs cambiaron.
    # Eso no se deja pasar: detiene el lote.
    if not any(datos.values()):
        print("\n  El bloque existe pero no se pudo leer ningun campo.")
        print("  La estructura de la pagina cambio.")
        print("  Revisa los IDs del diccionario SELECTORES.")
        return "ESTRUCTURA", 4

    bloque = bloque_datos(datos)
    print(bloque)
    if aplicar and not escribir(anuncio, bloque):
        return "ERROR", 5

    return "OK", None


# ══════════════════════════════════════════════════════════════════
#  Programa principal
# ══════════════════════════════════════════════════════════════════

def main():
    base_dir = Path(__file__).parent
    aplicar = "--aplicar" in sys.argv

    pausa = PAUSA
    if "--pausa" in sys.argv:
        i = sys.argv.index("--pausa")
        if i + 1 < len(sys.argv):
            try:
                pausa = int(sys.argv[i + 1])
            except ValueError:
                pass

    # ── Qué carpetas ─────────────────────────────────────────────
    if "--todas" in sys.argv:
        raiz = base_dir / CARPETA_SALIDAS
        if not raiz.is_dir():
            print(f"No existe la carpeta {CARPETA_SALIDAS}/")
            return 1
        from cola import clasificar
        carpetas = sorted(p for p in raiz.iterdir()
                          if p.is_dir() and clasificar(p)[0] == "PENDIENTE CAPTCHA")
    else:
        rutas = [a for a in sys.argv[1:]
                 if not a.startswith("--") and not a.isdigit()]
        if not rutas:
            print("Falta indicar carpetas.")
            print("  python extraer_kontakt.py salidas\\CarpetaA [CarpetaB ...]")
            print("  python extraer_kontakt.py --todas")
            return 1
        carpetas = [Path(r) for r in rutas]

    # ── Qué carpetas tienen trabajo pendiente ────────────────────
    pendientes = []
    saltadas = 0
    for c in carpetas:
        anuncio = c / "stellenanzeige.txt"
        if not anuncio.is_file():
            print(f"  Sin stellenanzeige.txt: {c.name}")
            continue
        if ya_procesado(anuncio):
            saltadas += 1
            continue
        enlace = leer_enlace(anuncio)
        if not enlace:
            print(f"  Sin linea ENLACE: {c.name}")
            continue
        pendientes.append((c, anuncio, enlace))

    if saltadas:
        print(f"{saltadas} ya tenian el bloque, se saltan.")

    if not pendientes:
        print("Nada que procesar.\n")
        return 0

    modo = "APLICANDO" if aplicar else "SIMULACION (no escribe)"
    print(f"\n{len(pendientes)} ofertas · pausa {pausa}s · {modo}\n")

    resumen = []
    corte = None
    sin_bloque_seguidos = 0

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(base_dir / PERFIL),
            headless=False,              # tiene que verse: hay captcha
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for i, (carpeta, anuncio, enlace) in enumerate(pendientes, 1):
            print(f"[{i}/{len(pendientes)}] {carpeta.name}")

            estado, corte = procesar(page, anuncio, enlace, aplicar)
            resumen.append((carpeta.name, estado))
            print(f"  -> {estado}\n")

            if corte:
                break

            # Dos fallos de bloque seguidos: algo pasa, no seguir
            if estado == "SIN BLOQUE":
                sin_bloque_seguidos += 1
                if sin_bloque_seguidos >= 2:
                    print("Dos ofertas seguidas sin bloque de contacto.")
                    print("Puede ser captcha persistente o un cambio en la")
                    print("pagina. Lote detenido.\n")
                    corte = 3
                    break
            else:
                sin_bloque_seguidos = 0

            if i < len(pendientes):
                time.sleep(pausa)

        ctx.close()

    # ── Resumen ──────────────────────────────────────────────────
    print("Resumen:")
    for nombre, estado in resumen:
        print(f"  {estado:<12} {nombre}")

    faltan = len(pendientes) - len(resumen)
    if faltan > 0:
        print(f"\n{faltan} sin procesar por el corte.")

    if not aplicar:
        print("\nSimulacion. Usa --aplicar para escribir.\n")
    else:
        print()

    return corte or 0


if __name__ == "__main__":
    sys.exit(main())
