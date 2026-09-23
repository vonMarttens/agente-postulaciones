#!/usr/bin/env python3
"""
Mide el consumo de tokens de Claude Code en este proyecto, separado
entre sesion principal y cada subagente, y por modelo.

No crea ningun log: lee las transcripciones que Claude Code ya guarda
en ~/.claude/projects/. No modifica nada.

El formato de esas transcripciones no esta documentado oficialmente.
Si una version futura lo cambia, el script dice cuantas lineas no pudo
leer en vez de inventar cifras.

Uso:
    python medir_uso.py              # todo el historial
    python medir_uso.py --dias 7     # solo los ultimos 7 dias

Requiere:
    solo libreria estandar
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROYECTO = "agente-postulaciones"
CARPETA = Path.home() / ".claude" / "projects"
COLUMNAS = ("input_tokens", "cache_creation_input_tokens",
            "cache_read_input_tokens", "output_tokens")


def tipo_de_agente(archivo):
    """Principal, o el tipo de subagente segun su .meta.json si existe."""
    if "subagents" not in archivo.parts:
        return "principal"
    meta = archivo.with_suffix(".meta.json")
    if meta.is_file():
        try:
            datos = json.loads(meta.read_text(encoding="utf-8"))
            for clave in ("agentType", "agent_type", "subagent_type", "subagentType"):
                if datos.get(clave):
                    return f"subagente: {datos[clave]}"
        except (json.JSONDecodeError, OSError):
            pass
    return "subagente: ?"


def fecha_de(linea):
    ts = linea.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def main():
    dias = None
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])
    desde = datetime.now(timezone.utc) - timedelta(days=dias) if dias else None

    carpetas = [c for c in CARPETA.glob("*") if c.is_dir() and PROYECTO in c.name]
    if not carpetas:
        print(f"No encuentro transcripciones de {PROYECTO} en {CARPETA}")
        return 1

    totales = defaultdict(lambda: defaultdict(int))
    vistos = set()
    ilegibles = 0

    for carpeta in carpetas:
        for archivo in carpeta.rglob("*.jsonl"):
            agente = tipo_de_agente(archivo)
            with archivo.open(encoding="utf-8", errors="replace") as f:
                for texto in f:
                    try:
                        linea = json.loads(texto)
                    except json.JSONDecodeError:
                        ilegibles += 1
                        continue
                    msg = linea.get("message")
                    if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                        continue
                    # Una misma respuesta ocupa varias lineas con el mismo
                    # uso: contarla una sola vez.
                    clave = (msg.get("id"), linea.get("requestId"))
                    if msg.get("id") and clave in vistos:
                        continue
                    vistos.add(clave)
                    if desde:
                        f_linea = fecha_de(linea)
                        if f_linea and f_linea < desde:
                            continue
                    grupo = (agente, msg.get("model", "?"))
                    totales[grupo]["peticiones"] += 1
                    for col in COLUMNAS:
                        totales[grupo][col] += msg["usage"].get(col) or 0

    if not totales:
        print("No encontré peticiones con datos de uso.")
        return 0

    def peso(t):  # sin cache_read, que es la parte barata
        return t["input_tokens"] + t["cache_creation_input_tokens"] + t["output_tokens"]

    gran_total = sum(peso(t) for t in totales.values()) or 1
    filas = sorted(totales.items(), key=lambda kv: peso(kv[1]), reverse=True)

    alcance = f"últimos {dias} días" if dias else "todo el historial"
    print(f"\nUso de Claude Code · {PROYECTO} · {alcance}\n")
    print(f"{'agente':34} {'modelo':26} {'pet.':>6} {'input':>10} {'cache+':>10} {'output':>10} {'%':>5} {'cache leído':>12}")
    for (agente, modelo), t in filas:
        print(f"{agente[:34]:34} {modelo[:26]:26} {t['peticiones']:>6} "
              f"{t['input_tokens']:>10,} {t['cache_creation_input_tokens']:>10,} "
              f"{t['output_tokens']:>10,} {100 * peso(t) / gran_total:>4.0f}% "
              f"{t['cache_read_input_tokens']:>12,}")
    print("\n% = input + cache escrito + output. El cache leído va aparte: es la parte barata.")
    if ilegibles:
        print(f"Aviso: {ilegibles} líneas no se pudieron leer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())