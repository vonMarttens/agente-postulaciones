#!/usr/bin/env python3
"""
Ejecutor del agente de postulaciones.

Corre los pasos del proceso, uno por uno o todos juntos, y deja el avance
en logs/ para que el panel lo muestre. Reemplaza a modo_automatico.ps1:
hace lo mismo, pero desde Python, avisando en que carpeta va y con la
posibilidad de pausar entre una carpeta y la siguiente.

Que corre y cuanto sale de config_automatico.json, que el panel edita.
Nunca envia nada: deja borradores en Gmail.

Uso:
    python ejecutor.py                          # la corrida guardada en la config
    python ejecutor.py --desatendido            # igual, sin pasos que necesiten a Usuario
    python ejecutor.py --paso "SIN DOCUMENTOS" --cantidad 3

Pausar: crear el archivo logs/.pausar (el panel lo hace con su boton).
La corrida termina la carpeta en curso y se detiene.

Requiere:
    solo libreria estandar, y claude en el PATH
"""

import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).parent
LOGS = RAIZ / "logs"
CONFIG = RAIZ / "config_automatico.json"
PROGRESO = LOGS / ".progreso.json"
PAUSA = LOGS / ".pausar"
CANDADO = LOGS / ".ejecutando"
USO = LOGS / "uso.jsonl"
PID = LOGS / ".pid"
MARCAS = LOGS / "_ultimas_corridas.json"

CANDADO_VENCE_HORAS = 6
# Se pone en True cuando se corre un solo paso: ahi el intervalo no manda.
FORZAR = {"valor": False}

LIMITE_CUPO = re.compile(r"hit your .*limit|usage limit|limit reached", re.I)

GMAIL_LECTURA = ("mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_thread,"
                 "mcp__claude_ai_Gmail__get_message")
PERMISOS = {
    "filtrar": "Skill,Read,Write,Edit,Glob,Grep,Bash(mkdir:*),Bash(mv:*)",
    "cv": "Skill,Read,Write,Edit,Glob,Grep,Bash(typst compile:*),Bash(python contar_paginas.py:*)",
    "carta": "Skill,Read,Write,Edit,Glob,Grep,Bash(typst compile:*),Bash(python contar_paginas.py:*)",
    "correo": "Skill,Read,Write,Glob,Grep,Bash(python cola.py:*)",
    "nachfassen": "Skill,Read,Write,Edit,Glob,Grep,Bash(python cola.py:*),"
                  + GMAIL_LECTURA + ",mcp__claude_ai_Gmail__create_draft",
}

# Orden de una corrida completa: lo mas cercano a terminar va primero.
# Si se acaba el cupo, lo que queda sin hacer es lo menos avanzado.
# El captcha va antes que las cartas porque las desbloquea.
ORDEN = [
    "BUSCAR OFERTAS",
    "VERIFICAR VIGENCIA",
    "FILTRAR MECANICO",
    "PENDIENTE CAPTCHA",
    "LISTA PARA ANSCHREIBEN",
    "ENVIAR POR CORREO",
    "BORRADOR SIN ANHANG",
    "ENVIADA · REVISAR",
    "POR FILTRAR",
    "SIN DOCUMENTOS",
    "POSTULAR POR PORTAL",
    "SIN VÍA",
    "SIN ANUNCIO",
]

# Pasos que necesitan a Usuario frente al PC: no corren desatendidos.
INTERACTIVOS = {"PENDIENTE CAPTCHA", "POSTULAR POR PORTAL", "SIN VÍA", "SIN ANUNCIO"}

CONFIG_INICIAL = {
    "buscar_cada_horas": 24,
    "vigencia_cada_horas": 24,
    "pasos": {
        "BUSCAR OFERTAS": {"activo": True, "cantidad": 0},
        "VERIFICAR VIGENCIA": {"activo": True, "cantidad": 0},
        "FILTRAR MECANICO": {"activo": True, "cantidad": 0},
        "PENDIENTE CAPTCHA": {"activo": False, "cantidad": 5},
        "LISTA PARA ANSCHREIBEN": {"activo": True, "cantidad": 5},
        "ENVIAR POR CORREO": {"activo": True, "cantidad": 5},
        "BORRADOR SIN ANHANG": {"activo": True, "cantidad": 5},
        "ENVIADA · REVISAR": {"activo": False, "cantidad": 5},
        "POR FILTRAR": {"activo": True, "cantidad": 30},
        "SIN DOCUMENTOS": {"activo": True, "cantidad": 5},
        "POSTULAR POR PORTAL": {"activo": False, "cantidad": 5},
        "SIN VÍA": {"activo": False, "cantidad": 5},
        "SIN ANUNCIO": {"activo": False, "cantidad": 5},
    },
}


# ══════════════════════════════════════════════════════════════════
#  Configuracion
# ══════════════════════════════════════════════════════════════════

def leer_config():
    cfg = json.loads(json.dumps(CONFIG_INICIAL))
    if CONFIG.is_file():
        try:
            guardada = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            guardada = {}
        for clave in ("buscar_cada_horas", "vigencia_cada_horas"):
            if clave in guardada:
                cfg[clave] = guardada[clave]
        for paso, valores in (guardada.get("pasos") or {}).items():
            if paso in cfg["pasos"]:
                cfg["pasos"][paso].update(valores)
    return cfg


def guardar_config(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
#  Registro y avance
# ══════════════════════════════════════════════════════════════════

class Corrida:
    def __init__(self, descripcion):
        LOGS.mkdir(exist_ok=True)
        self.log = LOGS / f"ejecutor_{datetime.now():%Y-%m-%d}.txt"
        self.estado = {
            "corriendo": True, "descripcion": descripcion,
            "inicio": datetime.now().strftime("%H:%M"), "fin": "",
            "paso": "", "hecho": 0, "total": 0, "detalle": "",
            "mensajes": [], "sin_cupo": "",
        }
        self.sin_cupo = False
        self.guardar()

    def guardar(self):
        PROGRESO.write_text(json.dumps(self.estado, ensure_ascii=False), encoding="utf-8")

    def anotar(self, titulo, texto=""):
        with self.log.open("a", encoding="utf-8") as f:
            f.write(f"=== {datetime.now():%Y-%m-%d %H:%M} - {titulo} ===\n{texto}\n")
        self.estado["mensajes"] = (self.estado["mensajes"] + [titulo])[-12:]
        self.guardar()

    def avance(self, paso, hecho, total, detalle=""):
        self.estado.update(paso=paso, hecho=hecho, total=total, detalle=detalle)
        self.guardar()

    def pausada(self):
        return PAUSA.is_file()

    def cerrar(self, resumen):
        self.anotar("resumen", resumen)
        self.estado.update(corriendo=False, fin=datetime.now().strftime("%H:%M"),
                           detalle=resumen)
        self.guardar()


# ══════════════════════════════════════════════════════════════════
#  Herramientas
# ══════════════════════════════════════════════════════════════════

ENTORNO = {**os.environ, "PYTHONUTF8": "1"}


def python(*args):
    r = subprocess.run([sys.executable, *args], cwd=RAIZ, env=ENTORNO,
                       stdin=subprocess.DEVNULL, capture_output=True)
    return (r.stdout + r.stderr).decode("utf-8", errors="replace")


def anotar_uso(corrida, titulo, datos):
    """Una línea por llamada a Claude en logs/uso.jsonl, para los gráficos."""
    uso = datos.get("usage") or {}
    linea = {
        "cuando": datetime.now().isoformat(timespec="seconds"),
        "paso": corrida.estado.get("paso") or "",
        "detalle": corrida.estado.get("detalle") or "",
        "titulo": titulo,
        "modelo": next(iter(datos.get("modelUsage") or {}), ""),
        "turnos": datos.get("num_turns") or 0,
        "segundos": round((datos.get("duration_ms") or 0) / 1000, 1),
        "costo_usd": datos.get("total_cost_usd") or 0,
        "entrada": uso.get("input_tokens") or 0,
        "cache_escrita": uso.get("cache_creation_input_tokens") or 0,
        "cache_leida": uso.get("cache_read_input_tokens") or 0,
        "salida": uso.get("output_tokens") or 0,
    }
    with USO.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def claude(corrida, titulo, instruccion, permisos):
    """Lanza un claude -p. Devuelve False si no hay cupo: quien llama corta."""
    if corrida.sin_cupo:
        return False
    exe = shutil.which("claude")
    if not exe:
        corrida.anotar(titulo, "No encuentro el comando claude en el PATH.")
        return False
    try:
        r = subprocess.run([exe, "-p", instruccion, "--output-format", "json",
                            "--allowedTools", permisos],
                           cwd=RAIZ, env=ENTORNO, capture_output=True, timeout=3600)
        salida = (r.stdout + r.stderr).decode("utf-8", errors="replace")
        # En json la respuesta trae el texto y, al lado, lo que costó.
        try:
            datos = json.loads(r.stdout.decode("utf-8", errors="replace"))
            salida = datos.get("result") or salida
            anotar_uso(corrida, titulo, datos)
        except (json.JSONDecodeError, AttributeError):
            pass
    except subprocess.TimeoutExpired:
        salida = "claude -p no terminó en una hora y se detuvo."
    corrida.anotar(titulo, salida)
    if LIMITE_CUPO.search(salida):
        corrida.sin_cupo = True
        m = re.search(r"resets ([^\r\n]+)", salida)
        corrida.estado["sin_cupo"] = m.group(1).strip() if m else "sin hora informada"
        corrida.anotar("sin cupo", "Se acabó el cupo de Claude. No se lanza nada más.")
        return False
    return True


def rutas(estado, maximo):
    salida = python("cola.py", "--rutas")
    carpetas = [Path(linea.split("\t", 1)[1].strip())
                for linea in salida.splitlines()
                if linea.startswith(estado + "\t")]
    return carpetas[:maximo]


def ofertas_en_raiz():
    carpeta = RAIZ / "ofertas"
    return sum(1 for p in carpeta.glob("*.txt")
               if re.match(r"^\d{4}-\d{2}-\d{2}", p.name)) if carpeta.is_dir() else 0


def campo(carpeta, nombre):
    anuncio = carpeta / "stellenanzeige.txt"
    if not anuncio.is_file():
        return ""
    m = re.search(rf"^{re.escape(nombre)}:\s*(.+)$",
                  anuncio.read_text(encoding="utf-8", errors="replace"), re.M)
    valor = m.group(1).strip() if m else ""
    return "" if valor == "-" else valor


def fusible(carpeta, nombre):
    archivo = carpeta / nombre
    if not archivo.exists():
        archivo.write_text("el intento automatico no dejo PDF\n", encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
#  Pasos
# ══════════════════════════════════════════════════════════════════

def por_carpeta(corrida, paso, carpetas, hacer):
    """Recorre carpetas una por una, avisando el avance y respetando la pausa."""
    hechas = 0
    for i, carpeta in enumerate(carpetas, 1):
        if corrida.pausada():
            corrida.anotar(paso, "Pausado por Usuario.")
            break
        corrida.avance(paso, i - 1, len(carpetas), carpeta.name)
        if hacer(carpeta) is False:
            break
        hechas += 1
        corrida.avance(paso, i, len(carpetas), carpeta.name)
    return hechas


def paso_filtrar(corrida, n, interactivo):
    antes = ofertas_en_raiz()
    if antes == 0 or n <= 0:
        return "no hay ofertas por filtrar"
    corrida.avance("POR FILTRAR", 0, min(n, antes), "puntuando en una sola sesión")
    claude(corrida, f"filtrar ({antes} en la raíz)",
           f"/ofertas-filtrar modo automatico, {n} ofertas", PERMISOS["filtrar"])
    hechas = antes - ofertas_en_raiz()
    corrida.avance("POR FILTRAR", hechas, min(n, antes))
    return f"{hechas} ofertas puntuadas"


def paso_documento(skill, permisos, patron, archivo_fallo):
    def paso(corrida, n, interactivo, estado):
        ok = fallos = 0

        def hacer(carpeta):
            nonlocal ok, fallos
            if not claude(corrida, f"{skill} {carpeta.name}",
                          f"/{skill} modo automatico con la carpeta {carpeta}", permisos):
                return False
            if any(carpeta.glob(patron)):
                ok += 1
            else:
                fallos += 1
                fusible(carpeta, archivo_fallo)
        por_carpeta(corrida, estado, rutas(estado, n), hacer)
        return f"{ok} listos, {fallos} fallidos"
    return paso


paso_cv = paso_documento("cv-adaptar-oferta", PERMISOS["cv"],
                         "lebenslauf_*.pdf", "cv_fallido.txt")
paso_carta = paso_documento("creacion_anschreiben", PERMISOS["carta"],
                            "Anschreiben_*.pdf", "anschreiben_fallido.txt")


def paso_correo(corrida, n, interactivo, estado):
    por_carpeta(corrida, estado, rutas(estado, n), lambda c: claude(
        corrida, f"correo {c.name}",
        f"/enviar-postulacion modo A con la carpeta {c}", PERMISOS["correo"]))
    args = ["crear_borrador.py", "--aplicar"] + ([] if interactivo else ["--sin-navegador"])
    corrida.anotar("crear_borrador", python(*args))
    return "borradores creados (ver log)"


def paso_nachfassen(corrida, n, interactivo, estado):
    hechas = por_carpeta(corrida, estado, rutas(estado, n), lambda c: claude(
        corrida, f"nachfassen {c.name}",
        f"/enviar-postulacion modo D con la carpeta {c}", PERMISOS["nachfassen"]))
    return f"{hechas} revisadas"


def paso_adjuntar(corrida, n, interactivo, estado):
    corrida.avance(estado, 0, 1, "adjuntar_borradores.py")
    corrida.anotar("adjuntar_borradores", python("adjuntar_borradores.py", "--aplicar"))
    corrida.avance(estado, 1, 1)
    return "adjuntos revisados (ver log)"


def paso_captcha(corrida, n, interactivo, estado):
    carpetas = rutas(estado, n)
    if not carpetas:
        return "no hay captchas pendientes"
    corrida.avance(estado, 0, len(carpetas), "resuelve los captcha en la ventana del navegador")
    corrida.anotar("extraer_kontakt",
                   python("extraer_kontakt.py", *map(str, carpetas), "--aplicar"))
    pendientes = set(rutas(estado, 10**6))
    resueltas = sum(1 for c in carpetas if c not in pendientes)
    corrida.avance(estado, resueltas, len(carpetas))
    return f"{resueltas} de {len(carpetas)} captchas resueltos"


def abrir(campo_nombre, con_carpeta=False):
    def paso(corrida, n, interactivo, estado):
        abiertas = 0

        def hacer(carpeta):
            nonlocal abiertas
            url = campo(carpeta, campo_nombre)
            if url.startswith("http"):
                webbrowser.open(url)
                abiertas += 1
            if con_carpeta and hasattr(os, "startfile"):
                os.startfile(carpeta)  # abre el Explorador de Windows
        por_carpeta(corrida, estado, rutas(estado, n), hacer)
        return f"{abiertas} abiertas en el navegador"
    return paso


def paso_abrir_carpeta(corrida, n, interactivo, estado):
    def hacer(carpeta):
        if hasattr(os, "startfile"):
            os.startfile(carpeta)  # abre el Explorador de Windows
    hechas = por_carpeta(corrida, estado, rutas(estado, n), hacer)
    return f"{hechas} carpetas abiertas"


PASOS = {
    "BUSCAR OFERTAS": lambda c, n, i: paso_buscar(c, n, i),
    "VERIFICAR VIGENCIA": lambda c, n, i: paso_vigencia(c, n, i),
    "FILTRAR MECANICO": lambda c, n, i: paso_filtro_mecanico(c, n, i),
    "POR FILTRAR": lambda c, n, i: paso_filtrar(c, n, i),
    "SIN DOCUMENTOS": lambda c, n, i: paso_cv(c, n, i, "SIN DOCUMENTOS"),
    "PENDIENTE CAPTCHA": lambda c, n, i: paso_captcha(c, n, i, "PENDIENTE CAPTCHA"),
    "LISTA PARA ANSCHREIBEN": lambda c, n, i: paso_carta(c, n, i, "LISTA PARA ANSCHREIBEN"),
    "ENVIAR POR CORREO": lambda c, n, i: paso_correo(c, n, i, "ENVIAR POR CORREO"),
    "POSTULAR POR PORTAL": lambda c, n, i: abrir("BEWERBUNG URL", con_carpeta=True)(c, n, i, "POSTULAR POR PORTAL"),
    "SIN VÍA": lambda c, n, i: abrir("ENLACE")(c, n, i, "SIN VÍA"),
    "BORRADOR SIN ANHANG": lambda c, n, i: paso_adjuntar(c, n, i, "BORRADOR SIN ANHANG"),
    "ENVIADA · REVISAR": lambda c, n, i: paso_nachfassen(c, n, i, "ENVIADA · REVISAR"),
    "SIN ANUNCIO": lambda c, n, i: paso_abrir_carpeta(c, n, i, "SIN ANUNCIO"),
}


# ══════════════════════════════════════════════════════════════════
#  Scripts de descarga, por intervalo
# ══════════════════════════════════════════════════════════════════

def toca(marcas, nombre, cada_horas):
    if cada_horas < 0:
        return False
    if cada_horas == 0 or nombre not in marcas:
        return True
    return datetime.now() - datetime.fromisoformat(marcas[nombre]) >= timedelta(hours=cada_horas)


def marcas_leer():
    return json.loads(MARCAS.read_text(encoding="utf-8-sig")) if MARCAS.is_file() else {}


def marcar(nombre):
    marcas = marcas_leer()
    marcas[nombre] = datetime.now().isoformat(timespec="seconds")
    MARCAS.write_text(json.dumps(marcas, indent=2), encoding="utf-8")


def paso_buscar(corrida, n, interactivo):
    horas = leer_config()["buscar_cada_horas"]
    if not FORZAR["valor"] and not toca(marcas_leer(), "buscar", horas):
        return f"omitido: la última búsqueda fue hace menos de {horas} h"
    corrida.avance("BUSCAR OFERTAS", 0, 1, "consultando la API")
    corrida.anotar("buscar_ofertas", python("buscar_ofertas.py"))
    marcar("buscar")
    corrida.avance("BUSCAR OFERTAS", 1, 1)
    return "ofertas descargadas (ver log)"


def paso_vigencia(corrida, n, interactivo):
    horas = leer_config()["vigencia_cada_horas"]
    if not FORZAR["valor"] and not toca(marcas_leer(), "vigencia", horas):
        return f"omitido: la última revisión fue hace menos de {horas} h"
    corrida.avance("VERIFICAR VIGENCIA", 0, 1, "consultando la API")
    corrida.anotar("verificar_vigencia", python("verificar_vigencia.py", "--aplicar"))
    marcar("vigencia")
    corrida.avance("VERIFICAR VIGENCIA", 1, 1)
    return "vigencia revisada (ver log)"


def paso_filtro_mecanico(corrida, n, interactivo):
    antes = ofertas_en_raiz()
    corrida.avance("FILTRAR MECANICO", 0, 1, "títulos y duplicados")
    corrida.anotar("titulos_filtrados", python("titulos_filtrados.py", "--aplicar"))
    corrida.anotar("detectar_duplicadas", python("detectar_duplicadas.py", "--aplicar"))
    corrida.avance("FILTRAR MECANICO", 1, 1)
    return f"{antes - ofertas_en_raiz()} ofertas descartadas sin leerlas"


# ══════════════════════════════════════════════════════════════════
#  Programa principal
# ══════════════════════════════════════════════════════════════════

def tomar_candado():
    if CANDADO.is_file():
        try:
            inicio = datetime.fromisoformat(CANDADO.read_text(encoding="utf-8").strip())
            if datetime.now() - inicio < timedelta(hours=CANDADO_VENCE_HORAS):
                return False
        except ValueError:
            pass
    CANDADO.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    return True


def main():
    LOGS.mkdir(exist_ok=True)
    desatendido = "--desatendido" in sys.argv
    interactivo = not desatendido
    cfg = leer_config()

    if "--paso" in sys.argv:
        paso = sys.argv[sys.argv.index("--paso") + 1]
        cantidad = int(sys.argv[sys.argv.index("--cantidad") + 1]) \
            if "--cantidad" in sys.argv else cfg["pasos"].get(paso, {}).get("cantidad", 5)
        if paso not in PASOS:
            print(f"No hay un programa para el paso {paso}")
            return 1
        FORZAR["valor"] = True
        plan = [(paso, cantidad)]
        descripcion = f"Solo el paso {paso}"
    else:
        plan = [(p, cfg["pasos"][p]["cantidad"]) for p in ORDEN
                if cfg["pasos"][p]["activo"] and not (desatendido and p in INTERACTIVOS)]
        descripcion = "Corrida desatendida" if desatendido else "Corrida completa"

    if not tomar_candado():
        print("Ya hay una corrida en marcha. Si no es así, borra logs/.ejecutando")
        return 1
    PAUSA.unlink(missing_ok=True)
    PID.write_text(str(os.getpid()), encoding="utf-8")
    corrida = Corrida(descripcion)
    resumen = []
    try:
        for paso, cantidad in plan:
            if corrida.pausada():
                resumen.append("pausada por Usuario")
                break
            if cantidad <= 0:
                continue
            resultado = PASOS[paso](corrida, int(cantidad), interactivo)
            resumen.append(f"{paso}: {resultado}")
        if corrida.sin_cupo:
            resumen.append(f"sin cupo de Claude, se renueva {corrida.estado['sin_cupo']}")
    except Exception:
        import traceback
        corrida.anotar("ERROR", traceback.format_exc())
        resumen.append("cortada por un error, revisa el log")
    finally:
        corrida.cerrar(" · ".join(resumen) or "nada que hacer")
        CANDADO.unlink(missing_ok=True)
        PID.unlink(missing_ok=True)
        PAUSA.unlink(missing_ok=True)
    print(corrida.estado["detalle"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
