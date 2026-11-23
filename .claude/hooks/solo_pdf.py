import json, sys

datos = json.load(sys.stdin)
entrada = datos.get("tool_input", {})
nombre = (entrada.get("filename") or "").lower()
tipo = (entrada.get("mimeType") or "").lower()

# Algunos clientes de correo mandan los PDF como octet-stream
TIPOS_OK = {"application/pdf", "application/octet-stream"}

if nombre.endswith(".pdf") and tipo in TIPOS_OK and "attachmentIndex" not in entrada:
    sys.exit(0)

print(f"Bloqueado: solo se descargan adjuntos PDF (filename={nombre or '-'}, "
      f"mimeType={tipo or '-'}).", file=sys.stderr)
sys.exit(2)