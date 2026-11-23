#!/usr/bin/env python3
"""
Comprueba que las keywords de una oferta aparecen literalmente en el texto
del CV o del Anschreiben compilado, tal como lo lee un ATS (texto extraido
del PDF).

Lee `keywords.txt` de la carpeta, con tres grupos:

    [a]
    !Controlling|Controller
    Abweichungsanalyse
    [b]
    Management-Reporting
    [c]
    Power BI

Una linea es una keyword. `|` separa formas alternativas: basta con una.
`!` marca el termino del titulo del puesto: exactamente una linea, en [a]
si esta respaldado, en [b] si es parcial (se escribe matizado), en [c] si no.
La comparacion ignora mayusculas y deja el final abierto ("Forecast"
cubre "Forecasts"). Las siglas de hasta 4 letras exigen inicio de palabra
("SEA" no cuenta dentro de "Research"); las palabras largas cuentan dentro
de un compuesto ("Handel" en "Einzelhandel").

La cobertura se mide contra todo lo que pide el anuncio: [a] + [b] + [c].
[c] cuenta siempre como ausente, porque no se puede escribir. Asi el
porcentaje no sube al mover keywords a [c].

Resultado para el CV (por defecto):
- Falta una de [a]          -> FALTA, codigo de salida 1
- Falta una de [b]          -> AVISO
- Aparece una de [c]        -> REVISAR (posible afirmacion sin respaldo), codigo 1
- Sin linea `!`             -> FALTA, codigo 1
- Titulo en [c] o cobertura
  del anuncio < UMBRAL      -> RIESGO ATS (no se arregla redactando), codigo 2

Resultado para la carta (--carta): una pagina no cubre todo el CV.
- Falta el termino del titulo          -> FALTA, codigo 1
- Menos de la mitad de [a] en la carta -> FALTA, codigo 1
- Resto de [a] y [b] ausentes          -> AVISO
- Aparece una de [c]                   -> REVISAR, codigo 1

Uso:
    python verificar_keywords.py salidas/[carpeta]
    python verificar_keywords.py salidas/[carpeta] --carta
"""

import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("Falta pypdf: pip install pypdf")

UMBRAL = 60  # % minimo de cobertura del anuncio completo

carpeta = Path(sys.argv[1])
carta = "--carta" in sys.argv[2:]
if not carpeta.is_dir():
    sys.exit(f"No existe {carpeta}")

archivo_kw = carpeta / "keywords.txt"
if not archivo_kw.is_file():
    sys.exit(f"No existe {archivo_kw}")

patron = "Anschreiben_*.pdf" if carta else "lebenslauf_*.pdf"
pdfs = sorted(carpeta.glob(patron))
if not pdfs:
    sys.exit(f"No hay {patron} en {carpeta}")

texto = "\n".join(p.extract_text() or "" for p in PdfReader(pdfs[0]).pages)
# Un salto de linea tras guion es corte de linea, no separacion de palabras
texto = re.sub(r"-\s*\n\s*", "-", texto)
texto = re.sub(r"\s+", " ", texto).lower()

grupos = {"a": [], "b": [], "c": []}
titulos = []  # (grupo, keyword) de las lineas marcadas con !
grupo = None
for linea in archivo_kw.read_text(encoding="utf-8").splitlines():
    linea = linea.strip()
    if not linea or linea.startswith("#"):
        continue
    m = re.fullmatch(r"\[([abc])\]", linea.lower())
    if m:
        grupo = m.group(1)
    elif grupo:
        if linea.startswith("!"):
            linea = linea[1:].strip()
            titulos.append((grupo, linea))
        grupos[grupo].append(linea)


def aparece(kw):
    # Siglas cortas: palabra completa ("SEA" no cuenta dentro de
    # "Research" ni de "Search"). Palabras largas: subcadena, porque en
    # aleman el compuesto contiene la palabra ("Handel" en "Einzelhandel").
    for forma in kw.split("|"):
        forma = forma.strip().lower()
        if len(forma) <= 4:
            # Borde a los dos lados ("SEA" no cuenta en "Search"), pero
            # admite el plural en -s ("KPIs", "APIs").
            patron = (r"(?<![a-zäöüß])" + re.escape(forma)
                      + r"(?![a-rt-zäöüß]|s[a-zäöüß])")
        else:
            patron = re.escape(forma)
        if re.search(patron, texto):
            return True
    return False


faltan_a = [k for k in grupos["a"] if not aparece(k)]
faltan_b = [k for k in grupos["b"] if not aparece(k)]
presentes_c = [k for k in grupos["c"] if aparece(k)]

def pct(n, total):
    return round(100 * n / total) if total else 100


n_a, n_b, n_c = len(grupos["a"]), len(grupos["b"]), len(grupos["c"])
en_a = n_a - len(faltan_a)
en_b = n_b - len(faltan_b)
cobertura = pct(en_a + en_b, n_a + n_b + n_c)
print(pdfs[0].name)
print(f"ATS: {cobertura} % del anuncio ({en_a + en_b}/{n_a + n_b + n_c})  "
      f"[a] {en_a}/{n_a} · [b] {en_b}/{n_b} · [c] sin respaldo {n_c}")

error = bool(presentes_c)
titulo = None
if len(titulos) != 1:
    print(f"FALTA   linea ! del titulo del puesto (hay {len(titulos)}, debe haber 1)")
    error = True
else:
    grupo_t, titulo = titulos[0]
    estado = "SIN RESPALDO" if grupo_t == "c" else (
        "en el documento" if aparece(titulo) else "NO aparece")
    print(f"Titulo: {titulo} — {estado}")

if carta:
    minimo = (n_a + 1) // 2
    print(f"Minimo de [a] en la carta: {pct(minimo, n_a)} % ({minimo}/{n_a})")
    if titulo in faltan_a:
        print(f"FALTA   [a] {titulo}  (termino del titulo del puesto)")
        error = True
    if en_a < minimo:
        print(f"FALTA   cobertura de [a] por debajo del minimo")
        error = True
    for k in faltan_a:
        if k != titulo:
            print(f"AVISO   [a] {k}")
else:
    for k in faltan_a:
        print(f"FALTA   [a] {k}")
    error = error or bool(faltan_a)
for k in faltan_b:
    print(f"AVISO   [b] {k}")
for k in presentes_c:
    print(f"REVISAR [c] {k}  (sin respaldo y aparece en el documento)")

riesgo = []
if not carta:
    if titulos and titulos[0][0] == "c":
        riesgo.append("el termino del titulo no tiene respaldo")
    if cobertura < UMBRAL:
        riesgo.append(f"cobertura del anuncio {cobertura} % < {UMBRAL} %")
    if riesgo:
        print("RIESGO ATS: " + "; ".join(riesgo))
        print("            Faltan requisitos, no redaccion: " + ", ".join(grupos["c"]))

sys.exit(1 if error else 2 if riesgo else 0)
