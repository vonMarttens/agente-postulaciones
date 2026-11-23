#!/usr/bin/env python3
"""
Mide cuantas ofertas trae cada termino candidato ANTES de agregarlo a
terminos.json.

Usa la misma busqueda y las mismas exclusiones que buscar_ofertas.py,
pero con una ventana de 30 dias para que la muestra sea representativa.
No descarga descripciones, no escribe en ofertas/ ni toca _vistas.json.
Solo imprime.

Por cada termino muestra:
  - cuantas ofertas trae en 30 dias
  - cuantas caen por exclusiones, y por cual exclusion
  - cuantas son nuevas: pasan las exclusiones y su titulo no contiene
    ya un termino de terminos.json (aproximado: la API busca tambien
    fuera del titulo)
  - hasta 5 titulos de ejemplo de las nuevas

Uso:
    python sondear_terminos.py "KI-Manager" "Prozessmanager"
    python sondear_terminos.py --archivo candidatos.txt
"""

import sys
from collections import Counter

import buscar_ofertas as bo

bo.DIAS = 30  # ventana de sondeo, no la de la busqueda diaria


def leer_terminos(args):
    if args[:1] == ["--archivo"] and len(args) > 1:
        with open(args[1], encoding="utf-8-sig") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    return args


def ya_cubierta(oferta):
    titulo = oferta.get("stellenangebotsTitel", "").lower()
    return any(t.lower() in titulo for t in bo.BUSQUEDAS)


def main():
    terminos = leer_terminos(sys.argv[1:])
    if not terminos:
        sys.exit(__doc__)

    print(f"\nSondeo · {bo.RADIO_KM} km de {bo.CIUDAD} · ultimos {bo.DIAS} dias\n")
    for termino in terminos:
        unicas = {o.get("referenznummer"): o for o in bo.buscar(termino)}.values()
        motivos = Counter()
        nuevas = []
        for o in unicas:
            motivo = bo.motivo_exclusion(o)
            if motivo:
                motivos[motivo] += 1
            elif not ya_cubierta(o):
                nuevas.append(o)

        excluidas = sum(motivos.values())
        print(f"{termino:.<32} {len(unicas):>4} en total · "
              f"{excluidas:>3} excluidas · {len(nuevas):>3} nuevas")
        if motivos:
            top = ", ".join(f"{m} ({n})" for m, n in motivos.most_common(3))
            print(f"    excluidas por: {top}")
        for o in nuevas[:5]:
            titulo = o.get("stellenangebotsTitel", "?")
            firma = o.get("firma", "?")
            print(f"    · {titulo} · {firma}")
        print()


if __name__ == "__main__":
    main()