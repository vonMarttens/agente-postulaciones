"""Lee perfil.json: los datos de la persona que el codigo no lleva escritos."""
import json
from pathlib import Path

RAIZ = Path(__file__).parent
_ARCHIVO = RAIZ / "perfil.json"

if not _ARCHIVO.is_file():
    raise SystemExit("Falta perfil.json en la raiz. Copia ejemplo/perfil.json y editalo.")
_datos = json.loads(_ARCHIVO.read_text(encoding="utf-8-sig"))

APELLIDO = _datos["apellido_archivo"]
ANLAGEN_ESTANDAR = RAIZ / f"anlagen_{APELLIDO}.pdf"
ANLAGEN_COMPLETO = RAIZ / f"anlagen_{APELLIDO}_vollstaendig.pdf"
CIUDAD = _datos["ciudad"]