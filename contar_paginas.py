#!/usr/bin/env python3
"""
Cuenta las paginas de un PDF. Sin librerias externas.

Uso:
    python contar_paginas.py salidas/[carpeta]/lebenslauf_....pdf
"""

import re
import sys
from pathlib import Path

ruta = Path(sys.argv[1])
if not ruta.is_file():
    sys.exit(f"No existe {ruta}")

datos = ruta.read_bytes()
m = re.search(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", datos, re.S)
paginas = int(m.group(1)) if m else len(re.findall(rb"/Type\s*/Page\b", datos))
print(paginas)