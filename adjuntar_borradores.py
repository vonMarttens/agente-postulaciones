#!/usr/bin/env python3
"""
Agrega los PDF a borradores de Gmail que ya existen sin adjuntos.

Por cada carpeta de salidas/ en estado BORRADOR SIN ANHANG:
  - busca el borrador dirigido al KONTAKT de stellenanzeige.txt
  - si hay exactamente uno y no tiene adjuntos, le agrega:
      Anschreiben_*.pdf y lebenslauf_*.pdf  (de la carpeta)
      anlagen_[apellido].pdf               (de la raiz)
  - conserva destinatario, asunto y cuerpo
  - relee el borrador y confirma que los tres adjuntos quedaron

Sin --aplicar solo muestra lo que haria. No envia nada.

Uso:
    python adjuntar_borradores.py
    python adjuntar_borradores.py --aplicar
"""

import base64
import io
import re
import sys
from datetime import date
from email import message_from_bytes, policy
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from cola import CARPETA_SALIDAS, REGISTRO, campo, clasificar
import perfil

RAIZ = Path(__file__).parent
SECRETOS = Path.home() / ".agente-postulaciones"
CREDENCIALES = SECRETOS / "credentials.json"
TOKEN = SECRETOS / "token.json"
ANLAGEN = perfil.ANLAGEN_ESTANDAR
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

# Limite de Gmail para un mensaje completo.
LIMITE_BYTES = 25 * 1024 * 1024


def conectar():
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
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def nombres_adjuntos(payload):
    nombres, pendientes = [], [payload]
    while pendientes:
        parte = pendientes.pop()
        if parte.get("filename"):
            nombres.append(parte["filename"])
        pendientes.extend(parte.get("parts", []))
    return nombres


def uno(carpeta, patron):
    encontrados = sorted(carpeta.glob(patron))
    return encontrados[0] if len(encontrados) == 1 else None

def marcar_anhang(carpeta):
    """Escribe ANHANG AM en bewerbung_gesendet.txt. Solo esa linea."""
    reg = carpeta / REGISTRO
    texto = reg.read_text(encoding="utf-8", errors="replace")
    linea = f"ANHANG AM: {date.today():%Y.%m.%d}"
    if re.search(r"^ANHANG AM:", texto, re.M):
        texto = re.sub(r"^ANHANG AM:.*$", linea, texto, flags=re.M)
    else:
        texto = texto.rstrip("\n") + "\n" + linea + "\n"
    reg.write_text(texto, encoding="utf-8")

def procesar(servicio, carpeta, aplicar):
    texto = (carpeta / "stellenanzeige.txt").read_text(encoding="utf-8", errors="replace")
    kontakt = campo(texto, "KONTAKT")
    if not kontakt:
        return "SALTADA", "sin KONTAKT en stellenanzeige.txt"

    carta = uno(carpeta, "Anschreiben_*.pdf")
    cv = uno(carpeta, "lebenslauf_*.pdf")
    if not carta or not cv:
        return "SALTADA", "no hay exactamente un Anschreiben y un lebenslauf .pdf"
    esperados = [carta, cv, ANLAGEN]

    borradores = servicio.users().drafts().list(
        userId="me", q=f"to:{kontakt}").execute().get("drafts", [])
    if len(borradores) != 1:
        return "SALTADA", f"{len(borradores)} borradores para {kontakt}, se esperaba 1"
    draft_id = borradores[0]["id"]

    d = servicio.users().drafts().get(userId="me", id=draft_id, format="raw").execute()
    msg = message_from_bytes(base64.urlsafe_b64decode(d["message"]["raw"]),
                             policy=policy.default)

    # Ya tiene adjuntos: si son los tres esperados, solo falta la marca.
    actuales = [p.get_filename() for p in msg.iter_attachments()]
    if actuales:
        if all(p.name in actuales for p in esperados):
            if not aplicar:
                return "HARÍA", f"{kontakt} · ya tiene los 3 adjuntos, solo marcar"
            marcar_anhang(carpeta)
            return "OK", f"{kontakt} · ya tenía los 3 adjuntos, marcado"
        return "SALTADA", "tiene adjuntos, pero no los esperados: " + ", ".join(actuales)

    for pdf in esperados:
        msg.add_attachment(pdf.read_bytes(), maintype="application",
                           subtype="pdf", filename=pdf.name)
    datos = msg.as_bytes()
    if len(datos) > LIMITE_BYTES:
        return "SALTADA", f"el mensaje pesaria {len(datos) // 1024} KB, sobre el limite de Gmail"

    if not aplicar:
        return "HARÍA", f"{kontakt} · + " + ", ".join(p.name for p in esperados)

    media = MediaIoBaseUpload(io.BytesIO(datos), mimetype="message/rfc822", resumable=True)
    servicio.users().drafts().update(
        userId="me", id=draft_id, body={"id": draft_id}, media_body=media).execute()

    v = servicio.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    faltan = [p.name for p in esperados
              if p.name not in nombres_adjuntos(v["message"]["payload"])]
    if faltan:
        return "FALLO", "faltan tras actualizar: " + ", ".join(faltan)

    marcar_anhang(carpeta)
    return "OK", f"{kontakt} · 3 adjuntos, marcado"


def main():
    aplicar = "--aplicar" in sys.argv

    if not ANLAGEN.is_file():
        print(f"No encuentro {ANLAGEN}")
        return 1

    raiz = RAIZ / CARPETA_SALIDAS
    carpetas = [c for c in sorted(raiz.iterdir())
                if c.is_dir() and clasificar(c)[0] == "BORRADOR SIN ANHANG"]
    if not carpetas:
        print("No hay carpetas en BORRADOR LISTO")
        return 0

    servicio = conectar()
    fallos = 0
    for c in carpetas:
        estado, detalle = procesar(servicio, c, aplicar)
        if estado == "FALLO":
            fallos += 1
        print(f"{estado:8} {c.name}\n         {detalle}")

    if not aplicar:
        print("\nNada cambió. Para aplicar: python adjuntar_borradores.py --aplicar")
    return 2 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())