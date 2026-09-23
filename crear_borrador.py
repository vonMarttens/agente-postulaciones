#!/usr/bin/env python3
"""
Crea en Gmail el borrador completo de una postulacion: destinatario,
asunto, cuerpo y los tres PDF adjuntos. Nunca envia nada.

La skill enviar-postulacion (modo A) solo redacta: deja correo.txt en la
carpeta. Este script hace lo mecanico, que el modelo no puede hacer bien:
mover los bytes de los PDF.

Por cada carpeta de salidas/ en estado CORREO LISTO:
  - lee correo.txt
  - adjunta Anschreiben_*.pdf, lebenslauf_*.pdf (de la carpeta) y
    anlagen_[apellido].pdf o anlagen_[apellido]_vollstaendig.pdf (raiz)
  - crea el borrador y lo relee: destinatario y los tres adjuntos
  - solo si todo calza, escribe bewerbung_gesendet.txt con ANHANG AM,
    y la carpeta pasa a BORRADOR LISTO

Formato de correo.txt:
    PARA:    bewerbung@empresa.de
    ASUNTO:  Bewerbung als ..., Referenznummer ...
    ANEXOS:  estandar | vollstaendig
    ---
    Sehr geehrte Damen und Herren,
    ...

Uso:
    python crear_borrador.py              # simulacion, no crea nada
    python crear_borrador.py --aplicar

Requiere:
    google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""

import io
import re
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from cola import CARPETA_SALIDAS, REGISTRO, clasificar
import perfil

RAIZ = Path(__file__).parent
CREDENCIALES = RAIZ / "credentials.json"
TOKEN = RAIZ / "token.json"
CORREO = "correo.txt"
ANEXOS = {
    "estandar": perfil.ANLAGEN_ESTANDAR,
    "vollstaendig": perfil.ANLAGEN_COMPLETO,
}
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

# Limite de Gmail para un mensaje completo.
LIMITE_BYTES = 25 * 1024 * 1024


def conectar():
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
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def leer_correo(ruta):
    """Devuelve (para, asunto, anexos, cuerpo) o lanza ValueError con el motivo."""
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    if "\n---" not in texto:
        raise ValueError("correo.txt sin la línea --- que separa cabecera y cuerpo")
    cabecera, cuerpo = texto.split("\n---", 1)
    cuerpo = cuerpo.lstrip("-").strip("\n")

    def dato(nombre):
        m = re.search(rf"^{nombre}:\s*(.+)$", cabecera, re.M)
        return m.group(1).strip() if m else ""

    para, asunto = dato("PARA"), dato("ASUNTO")
    anexos = (dato("ANEXOS") or "estandar").lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", para):
        raise ValueError(f"PARA no es un correo válido: {para or '(vacío)'}")
    if not asunto:
        raise ValueError("falta ASUNTO")
    if anexos not in ANEXOS:
        raise ValueError(f"ANEXOS debe ser estandar o vollstaendig, no {anexos}")
    if len(cuerpo.split()) < 20:
        raise ValueError("el cuerpo tiene menos de 20 palabras")
    return para, asunto, anexos, cuerpo


def uno(carpeta, patron):
    encontrados = sorted(carpeta.glob(patron))
    return encontrados[0] if len(encontrados) == 1 else None


def armar(carpeta):
    """Devuelve (mensaje, para, nombres_esperados) o lanza ValueError."""
    para, asunto, anexos, cuerpo = leer_correo(carpeta / CORREO)

    carta = uno(carpeta, "Anschreiben_*.pdf")
    cv = uno(carpeta, "lebenslauf_*.pdf")
    if not carta or not cv:
        raise ValueError("no hay exactamente un Anschreiben y un lebenslauf .pdf")
    anlagen = ANEXOS[anexos]
    if not anlagen.is_file():
        raise ValueError(f"no existe {anlagen.name}")

    msg = EmailMessage()
    msg["To"] = para
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    # Orden habitual en Alemania: carta, CV, anexos.
    for pdf in (carta, cv, anlagen):
        msg.add_attachment(pdf.read_bytes(), maintype="application",
                           subtype="pdf", filename=pdf.name)

    if len(msg.as_bytes()) > LIMITE_BYTES:
        raise ValueError("el mensaje supera el límite de 25 MB de Gmail")
    return msg, para, [carta.name, cv.name, anlagen.name]


def partes(payload):
    nombres, cabeceras, pendientes = [], {}, [payload]
    for h in payload.get("headers", []):
        cabeceras[h["name"].lower()] = h["value"]
    while pendientes:
        p = pendientes.pop()
        if p.get("filename"):
            nombres.append(p["filename"])
        pendientes.extend(p.get("parts", []))
    return nombres, cabeceras


def registrar(carpeta, draft_id, thread_id):
    (carpeta / REGISTRO).write_text(
        "GESENDET AM: -\n"
        "VIA:         E-Mail\n"
        "# metadatos internos, no editar a mano\n"
        f"DRAFT_ID:    {draft_id}\n"
        f"THREAD_ID:   {thread_id}\n"
        f"ANHANG AM: {date.today():%Y.%m.%d}\n",
        encoding="utf-8",
    )


def procesar(servicio, carpeta, aplicar):
    if (carpeta / REGISTRO).is_file():
        return "SALTADA", "ya tiene bewerbung_gesendet.txt: nunca un segundo borrador"
    try:
        msg, para, esperados = armar(carpeta)
    except ValueError as e:
        return "SALTADA", str(e)

    if not aplicar:
        return "HARÍA", f"{para} · " + ", ".join(esperados)

    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(msg.as_bytes()),
                              mimetype="message/rfc822", resumable=True)
    draft = servicio.users().drafts().create(
        userId="me", body={}, media_body=media).execute()

    v = servicio.users().drafts().get(userId="me", id=draft["id"], format="full").execute()
    nombres, cabeceras = partes(v["message"]["payload"])
    faltan = [n for n in esperados if n not in nombres]
    if faltan or para not in cabeceras.get("to", ""):
        motivo = ("faltan " + ", ".join(faltan)) if faltan else "el destinatario no calza"
        return "FALLO", f"borrador {draft['id']} creado pero {motivo}: revisar en Gmail"

    registrar(carpeta, draft["id"], v["message"].get("threadId", ""))
    return "OK", f"{para} · 3 adjuntos"


def main():
    aplicar = "--aplicar" in sys.argv
    raiz = RAIZ / CARPETA_SALIDAS
    carpetas = [c for c in sorted(raiz.iterdir())
                if c.is_dir() and clasificar(c)[0] == "CORREO LISTO"]
    if not carpetas:
        print("No hay carpetas en CORREO LISTO")
        return 0

    servicio = conectar() if aplicar else None
    fallos = 0
    for c in carpetas:
        estado, detalle = procesar(servicio, c, aplicar)
        if estado == "FALLO":
            fallos += 1
        print(f"{estado:8} {c.name}\n         {detalle}")

    if not aplicar:
        print("\nNada cambió. Para crear los borradores: python crear_borrador.py --aplicar")
    return 2 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())