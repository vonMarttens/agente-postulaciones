#!/usr/bin/env python3
"""
Panel del agente de postulaciones.

Abre en el navegador el estado de cada postulacion (lo calcula cola.py) y
permite lanzar el trabajo:

  - Solo un paso: el boton "Solo este" de cada linea.
  - Varios pasos: se marcan en la linea y se corre la seleccion.
  - A una hora: la misma seleccion, programada en Windows para mas tarde.

El trabajo lo hace ejecutor.py. El panel solo lo lanza, lo pausa y lee su
avance en logs/.progreso.json. Si cierras el panel, la corrida sigue.

Todo corre en tu PC (127.0.0.1). Nadie mas puede abrir el panel.

Uso:
    python panel.py
    Ctrl+C en la terminal para cerrarlo.

Requiere:
    solo libreria estandar
"""

import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ejecutor

RAIZ = Path(__file__).parent
PAGINA = RAIZ / "panel.html"
PUERTO = 8765
TAREA_UNA_VEZ = "agente-postulaciones-una-vez"
PROGRAMADA = ejecutor.LOGS / ".programada.json"
ES_WINDOWS = os.name == "nt"


# ══════════════════════════════════════════════════════════════════
#  Lectura
# ══════════════════════════════════════════════════════════════════

def leer_cola():
    """Corre cola.py --rutas y agrupa las carpetas por estado."""
    try:
        r = subprocess.run([sys.executable, "cola.py", "--rutas"], cwd=RAIZ,
                           capture_output=True, env=ejecutor.ENTORNO, timeout=120)
    except subprocess.TimeoutExpired:
        return {}, "cola.py tardó más de 2 minutos y se detuvo."
    estados = {}
    for linea in r.stdout.decode("utf-8", errors="replace").splitlines():
        if "\t" in linea:
            estado, ruta = linea.split("\t", 1)
            estados.setdefault(estado.strip(), []).append(Path(ruta.strip()).name)
    error = ""
    if r.returncode != 0:
        error = r.stderr.decode("utf-8", errors="replace").strip() or \
            f"cola.py terminó con código {r.returncode}."
    return estados, error


def leer_uso(dias=90):
    """Las llamadas a Claude registradas por ejecutor.py, una por línea."""
    if not ejecutor.USO.is_file():
        return []
    corte = datetime.now() - timedelta(days=dias)
    filas = []
    for linea in ejecutor.USO.read_text(encoding="utf-8-sig",
                                        errors="replace").splitlines():
        try:
            fila = json.loads(linea)
            if datetime.fromisoformat(fila["cuando"]) >= corte:
                filas.append(fila)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return filas


def leer_json(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def programada():
    datos = leer_json(PROGRAMADA)
    if not datos:
        return None
    if datetime.fromisoformat(datos["cuando"]) < datetime.now() - timedelta(minutes=5):
        PROGRAMADA.unlink(missing_ok=True)
        return None
    return datos


# ══════════════════════════════════════════════════════════════════
#  Acciones
# ══════════════════════════════════════════════════════════════════

def lanzar(*args):
    """Lanza ejecutor.py aparte: sigue aunque se cierre el panel."""
    if ejecutor.CANDADO.is_file():
        return {"ok": False, "mensaje": "Ya hay una corrida en marcha."}
    banderas = 0
    if ES_WINDOWS:
        banderas = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen([sys.executable, "ejecutor.py", *args], cwd=RAIZ,
                     env=ejecutor.ENTORNO, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=banderas)
    return {"ok": True, "mensaje": "Corrida iniciada."}


def guardar_pasos(pasos):
    cfg = ejecutor.leer_config()
    for paso, valores in (pasos or {}).items():
        if paso in cfg["pasos"]:
            cfg["pasos"][paso]["activo"] = bool(valores.get("activo"))
            cfg["pasos"][paso]["cantidad"] = max(0, int(valores.get("cantidad") or 0))
    ejecutor.guardar_config(cfg)


def powershell(comando):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def programar(hora):
    m = re.match(r"^(\d{1,2}):(\d{2})$", hora or "")
    if not m:
        return {"ok": False, "mensaje": "Escribe la hora como HH:MM."}
    ahora = datetime.now()
    cuando = ahora.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                           second=0, microsecond=0)
    if cuando <= ahora:
        cuando += timedelta(days=1)
    if not ES_WINDOWS:
        return {"ok": False, "mensaje": "Programar solo funciona en Windows."}

    def q(texto):  # comillas simples de PowerShell
        return "'" + str(texto).replace("'", "''") + "'"
    ok, error = powershell(
        f"$a = New-ScheduledTaskAction -Execute {q(sys.executable)} "
        f"-Argument {q(chr(34) + str(RAIZ / 'ejecutor.py') + chr(34) + ' --desatendido')} "
        f"-WorkingDirectory {q(RAIZ)}; "
        f"$t = New-ScheduledTaskTrigger -Once -At ([datetime]{q(cuando.isoformat())}); "
        f"$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable; "
        f"Register-ScheduledTask -TaskName {q(TAREA_UNA_VEZ)} -Action $a -Trigger $t "
        f"-Settings $s -Force | Out-Null")
    if not ok:
        return {"ok": False, "mensaje": f"Windows no aceptó la tarea: {error}"}
    PROGRAMADA.write_text(json.dumps({"cuando": cuando.isoformat()}), encoding="utf-8")
    dia = "hoy" if cuando.date() == ahora.date() else "mañana"
    return {"ok": True, "mensaje": f"Programada para {dia} a las {cuando:%H:%M}."}


def cancelar():
    if ES_WINDOWS:
        powershell(f"Unregister-ScheduledTask -TaskName '{TAREA_UNA_VEZ}' -Confirm:$false")
    PROGRAMADA.unlink(missing_ok=True)
    return {"ok": True, "mensaje": "Programación cancelada."}


# ══════════════════════════════════════════════════════════════════
#  Servidor
# ══════════════════════════════════════════════════════════════════

def progreso():
    """Lee el avance. Si la corrida murio sin cerrar, no la da por viva."""
    p = leer_json(ejecutor.PROGRESO)
    if p and p.get("corriendo") and not ejecutor.CANDADO.is_file():
        p["corriendo"] = False
    return p


def detener():
    """Corta la corrida en marcha y todo lo que lanzo: claude, Chromium."""
    try:
        pid = int(ejecutor.PID.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if pid:
        if ES_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True)
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
    for archivo in (ejecutor.CANDADO, ejecutor.PID, ejecutor.PAUSA):
        archivo.unlink(missing_ok=True)
    p = leer_json(ejecutor.PROGRESO) or {}
    if p.get("corriendo"):
        p.update(corriendo=False, fin=datetime.now().strftime("%H:%M"),
                 detalle="Detenida por Usuario.")
        ejecutor.PROGRESO.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "mensaje": "Corrida detenida."}

class Panel(BaseHTTPRequestHandler):
    def responder(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else \
            json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            if not PAGINA.is_file():
                self.responder(500, b"Falta panel.html junto a panel.py",
                               "text/plain; charset=utf-8")
                return
            self.responder(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/estado":
            estados, error = leer_cola()
            self.responder(200, {
                "actualizado": datetime.now().strftime("%H:%M"),
                "por_filtrar": ejecutor.ofertas_en_raiz(),
                "estados": estados,
                "error": error,
                "pasos": ejecutor.leer_config()["pasos"],
                "ejecutables": list(ejecutor.PASOS),
                "interactivos": sorted(ejecutor.INTERACTIVOS),
                "progreso": progreso(),
                "programada": programada(),
            })
        elif self.path.startswith("/api/uso"):
            self.responder(200, {"filas": leer_uso()})
        elif self.path == "/api/progreso":
            self.responder(200, {"progreso": progreso()})
        else:
            self.responder(404, {"error": "no existe"})

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        try:
            pedido = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            self.responder(400, {"ok": False, "mensaje": "Pedido ilegible."})
            return

        if self.path == "/api/pasos":
            guardar_pasos(pedido.get("pasos"))
            resultado = {"ok": True, "mensaje": ""}
        elif self.path == "/api/correr":
            paso = pedido.get("paso")
            if paso:
                if paso not in ejecutor.PASOS:
                    resultado = {"ok": False, "mensaje": "Todavía no hay un programa para este paso."}
                else:
                    resultado = lanzar("--paso", paso, "--cantidad",
                                       str(max(0, int(pedido.get("cantidad") or 0))))
            else:
                guardar_pasos(pedido.get("pasos"))
                resultado = lanzar()
        elif self.path == "/api/pausar":
            ejecutor.LOGS.mkdir(exist_ok=True)
            ejecutor.PAUSA.touch()
            resultado = {"ok": True, "mensaje": "Se detiene al terminar la carpeta en curso."}
        elif self.path == "/api/detener":
            resultado = detener()
        elif self.path == "/api/programar":
            guardar_pasos(pedido.get("pasos"))
            resultado = programar(pedido.get("hora"))
        elif self.path == "/api/cancelar":
            resultado = cancelar()
        else:
            self.responder(404, {"error": "no existe"})
            return
        self.responder(200, resultado)

    def log_message(self, *args):
        pass  # sin ruido en la terminal


def main():
    ejecutor.LOGS.mkdir(exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Panel)
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"Panel abierto en {url}\nCtrl+C para cerrarlo. Las corridas en marcha siguen.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel cerrado.")


if __name__ == "__main__":
    main()
