#!/usr/bin/env python3
"""
Confirma en Gmail que los borradores de postulacion se enviaron.

Por cada carpeta de salidas/ en estado BORRADOR LISTO, revisa el hilo
guardado en bewerbung_gesendet.txt (THREAD_ID):
  - hay un mensaje con la etiqueta SENT: escribe GESENDET AM con la
    fecha de ese mensaje. La carpeta pasa a ENVIADA.
  - el borrador sigue ahi: no se ha enviado. No toca nada.
  - no hay borrador ni mensaje enviado: se borro sin enviar. Escribe
    DESCARTADA AM. La carpeta pasa a POSTULACION ELIMINADA.

Usa solo el permiso gmail.metadata: cabeceras y etiquetas, nunca el
texto de un correo. Y solo pide los hilos guardados en las carpetas.
Tiene su propio token, separado del de crear_borrador.py.

Uso:
    python confirmar_envio.py                   # simulacion, no escribe nada
    python confirmar_envio.py --aplicar
    python confirmar_envio.py --aplicar --sin-navegador   # desde ejecutor.py

La primera vez correr sin --sin-navegador para autorizar en el navegador.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from cola import CARPETA_SALIDAS, REGISTRO, campo, clasificar

RAIZ = Path(__file__).parent
SECRETOS = Path.home() / ".agente-postulaciones"
CREDENCIALES = SECRETOS / "credentials.json"
TOKEN = SECRETOS / "token_metadata.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.metadata"]


def conectar(sin_navegador):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  # permiso vencido: pedir de nuevo
        if not creds or not creds.valid:
            if sin_navegador:
                sys.exit("Falta autorizar Gmail. Corre una vez: python confirmar_envio.py")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def revisar(servicio, carpeta):
    """Devuelve (estado, detalle, fecha de envio o None)."""
    from googleapiclient.errors import HttpError

    reg = (carpeta / REGISTRO).read_text(encoding="utf-8", errors="replace")
    thread_id = campo(reg, "THREAD_ID")
    if not thread_id:
        return "SALTADA", "sin THREAD_ID en bewerbung_gesendet.txt", None

    try:
        hilo = servicio.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["To"]).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return "BORRADO", "el hilo no existe: el borrador se borró sin enviar", None
        return "ERROR", f"Gmail respondió {e.resp.status}", None

    mensajes = hilo.get("messages", [])
    enviados = [m for m in mensajes if "SENT" in m.get("labelIds", [])]
    if enviados:
        primero = min(enviados, key=lambda m: int(m["internalDate"]))
        fecha = datetime.fromtimestamp(int(primero["internalDate"]) / 1000)
        para = next((h["value"] for h in primero["payload"].get("headers", [])
                     if h["name"].lower() == "to"), "?")
        return "ENVIADA", f"{fecha:%Y.%m.%d} · a {para}", fecha

    if any("DRAFT" in m.get("labelIds", []) for m in mensajes):
        return "PENDIENTE", "el borrador sigue sin enviar", None
    return "BORRADO", "no hay borrador ni mensaje enviado en el hilo", None


def marcar_enviada(carpeta, fecha):
    """Cambia solo la linea GESENDET AM. El resto del registro no se toca."""
    reg = carpeta / REGISTRO
    texto = reg.read_text(encoding="utf-8", errors="replace")
    texto = re.sub(r"^GESENDET AM:.*$", f"GESENDET AM: {fecha:%Y.%m.%d}",
                   texto, count=1, flags=re.M)
    reg.write_text(texto, encoding="utf-8")


def marcar_descartada(carpeta):
    """Agrega DESCARTADA AM al registro. El resto no se toca."""
    reg = carpeta / REGISTRO
    texto = reg.read_text(encoding="utf-8", errors="replace").rstrip("\n")
    reg.write_text(texto + f"\nDESCARTADA AM: {datetime.now():%Y.%m.%d}\n", encoding="utf-8")


def main():
    aplicar = "--aplicar" in sys.argv
    raiz = RAIZ / CARPETA_SALIDAS
    carpetas = [c for c in sorted(raiz.iterdir())
                if c.is_dir() and clasificar(c)[0] == "BORRADOR LISTO"]
    if not carpetas:
        print("No hay carpetas en BORRADOR LISTO")
        return 0

    servicio = conectar("--sin-navegador" in sys.argv)
    errores = 0
    for c in carpetas:
        estado, detalle, fecha = revisar(servicio, c)
        if estado == "ENVIADA" and aplicar:
            marcar_enviada(c, fecha)
        if estado == "BORRADO" and aplicar:
            marcar_descartada(c)
        if estado == "ERROR":
            errores += 1
        print(f"{estado:9} {c.name}\n          {detalle}")

    if not aplicar:
        print("\nNada cambió. Para registrar los envíos: python confirmar_envio.py --aplicar")
    return 2 if errores else 0


if __name__ == "__main__":
    sys.exit(main())