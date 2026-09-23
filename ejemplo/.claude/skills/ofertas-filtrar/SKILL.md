---
name: ofertas-filtrar
description: Puntúa ofertas de la carpeta ofertas/ contra el perfil del usuario, decide cuáles merecen una postulación completa y mueve cada oferta según su puntaje. Úsala cuando el usuario pida evaluar, filtrar, puntuar o priorizar ofertas antes de adaptar el CV, o cuando se invoque en modo automático.
---

# Filtrado previo de ofertas

Decides qué ofertas justifican el trabajo de una postulación completa.
Es un filtro, no una evaluación. Salida corta y comparable.

Idioma de trabajo: español.

## Fuentes
- `ofertas/*.txt` — las ofertas descargadas
- `CLAUDE.md` — perfil, geografía, disponibilidad, exclusiones
- `contexto/` — experiencia documentada
- `contexto/anekdoten.md` — episodios disponibles para el Anschreiben
- `referencia/gehalt_nrw.md` — ¡IMPORTANTE!:rangos salariales. Solo se lee en el paso
  Gehalt, nunca antes de puntuar.

## Antes de puntuar

Leer, en este orden, antes de abrir ninguna oferta:
1. `CLAUDE.md`
2. Todos los archivos de `contexto/`
3. `contexto/anekdoten.md`

Confirmar que se leyeron indicando en una línea qué puestos y qué
episodios hay disponibles. Sin ese paso, no empezar a puntuar:
una evaluación hecha sin el material de origen es adivinación.

Con lotes sucesivos en la misma sesión, no hace falta releer.

## Escala

| Puntos | Veredicto | Acción |
|---|---|---|
| 0–2 | ELIMINAR | Se mueve a `ofertas/descartadas/` |
| 3–5 | DUDOSO | Se mueve a `ofertas/standby/`, sin postular por ahora |
| 6–8 | POSTULAR | Se crea su carpeta en `salidas/` para `cv-adaptar-oferta` |

Ocho es el máximo. No existe la oferta perfecta; reservar la parte
alta de la escala mantiene el orden útil.

## Cómo se calcula

Primero los techos, después la puntuación. Nunca al revés.

1. Revisar todos los criterios que imponen techo. Si alguno se activa,
   ese es el máximo posible y **anula cualquier señal positiva**.
   Si se activan varios, manda el más bajo.
2. Solo si ningún techo se activa, puntuar por encaje.

Un techo no se promedia ni se compensa. Una oferta con encaje excelente
y un techo de 2 vale 2. Si la puntuación por encaje da 7 y hay un techo
de 2, el resultado es 2.

## Puntuación cuando no hay techos

- **6–8**: las tareas principales corresponden a experiencia documentada
  en `contexto/`, y existe episodio aplicable en `anekdoten.md`.
  8 solo si además el nivel del puesto calza exacto.
- **3–5**: encaje parcial. El sector o las herramientas coinciden, pero
  las tareas centrales no están respaldadas.
- **0–2**: sin encaje real, aunque ningún techo se haya activado.

## Criterios de puntuación

**Nivel del puesto (lo que más pesa).**
Una oferta que exige más años de experiencia profesional en Alemania
de los que el usuario puede acreditar no sube de 2, por bien que
encaje en lo demás. Lo mismo si pide experiencia de estudiante o
prácticas: está sobrecualificado y no lo van a llamar.

**Encaje sustantivo.**
Qué proporción de las tareas principales corresponde a experiencia
documentada en `contexto/`. No basta con que el sector coincida.

**Requisitos excluyentes.**
Certificaciones, licencias, conocimiento del marco regulatorio alemán,
títulos específicos. Si hay uno que el usuario no cumple y el anuncio
lo marca como obligatorio, el techo es 2.

**Herramientas de terceros (SAP, ERP, CRM, suites BI).**
Primero, cuánto pesa en la oferta:
- En el título del puesto, en el nombre del equipo o área, o como eje
  de las tareas principales: techo 2. No se compensa con herramientas
  de otro dominio, aunque compartan la etiqueta de "digital".
- Mencionada entre varios requisitos, o como parte del entorno de
  trabajo: sigue el criterio del verbo.

Después, el verbo:
- **Usar** el sistema en el trabajo diario: no penaliza.
- **Diseñar, configurar, migrar o administrar**: techo 2. Señales:
  Architect, Implementierung, Customizing, Migration, Modulbetreuung,
  Berater, Einführung.

**Nivel de alemán exigido.**
Un requisito de C1 no descarta por sí solo. Distinguir para qué:
- **Uso interno**: documentación, comunicación con el equipo, informes,
  trabajo con sistemas. No penaliza.
- **Cara al cliente en situaciones de riesgo**: negociación, cierre de
  acuerdos, presentaciones a cliente externo, asesoría con
  responsabilidad legal. Resta fuerte, techo 2.

Señales del caso malo en el anuncio: *verhandlungssicher*,
*Mandantengespräche*, *Kundenverhandlungen*, *Präsentation beim Kunden*,
*muttersprachliches Niveau*. Si solo dice "sehr gute Deutschkenntnisse"
sin contexto de cliente, tratarlo como uso interno.

**Geografía y fechas.**
Fuera del radio de CLAUDE.md o con inicio anterior a la disponibilidad
sin margen de negociación: resta.

**Exclusiones declaradas.**
Si la función principal está entre las exclusiones de `CLAUDE.md`: 0.

**Munición para el Anschreiben.**
Si existe un episodio en `anekdoten.md` que responda directamente a la
exigencia central del anuncio, suma. Sin eso, la carta será genérica.

## Salida

Una línea por oferta, nada más:

```
[7] POSTULAR   Kreditanalyst · Sparkasse Krefeld · 24 km
    Cartera de crédito corporativo. Episodio A1 aplica directo.

[4] DUDOSO     Business Analyst · Vodafone · 12 km
    Encaje parcial: analítica sí, telecomunicaciones no.

[2] ELIMINAR   Business Analyst ERP · Deloitte · 3 km
    TECHO herramienta: ERP en título y nombre del equipo.

[2] ELIMINAR   Consultant Banking · BearingPoint · 8 km
    TECHO idioma: presentaciones a cliente en alemán.
```

Sin párrafos, sin recomendaciones, sin sugerencias de mejora.
El motivo cabe en una línea o no es un motivo claro.

Cuando se activa un techo, la línea de motivo empieza por `TECHO`
seguido de cuál: `TECHO nivel`, `TECHO herramienta`, `TECHO idioma`,
`TECHO viaje`, `TECHO requisito`. Así queda auditable si el techo
se aplicó o se ignoró.

## Gehalt (solo POSTULAR)

Después de puntuar el lote, y solo para las ofertas con 6–8 puntos.
Las de 0–5 no llevan bloque. Si el `.txt` ya tiene bloque, no tocarlo.
Se escribe **antes** de mover la oferta a `salidas/`.

### Nivel del usuario para el puesto
Según las áreas y niveles (junior | professional) definidos en `CLAUDE.md`.

### 1. Buscar el sueldo en el anuncio
Señales: Gehalt, Vergütung, Jahresgehalt, Monatsgehalt, brutto, €, EUR,
Entgeltgruppe, TVöD, TV-L, Tarifvertrag.

- Cifra anual única: usarla.
- Rango: junior toma mínimo + 25 % del ancho; professional, el punto medio.
- Cifra mensual: ×12, o ×13 si el anuncio nombra un 13. Gehalt.
- Convenio sin cifra ("TVöD E9b"): no calcular.

### 2. Si el anuncio no trae sueldo
Recién entonces leer `referencia/gehalt_nrw.md`, una vez por lote.

1. Elegir la fila que corresponde al puesto.
2. Percentil: junior → P25; professional → P50.
   Si la fila ya es de nivel junior (Junior Controller): P50.
3. Aplicar los multiplicadores de tamaño, ubicación y sector.
   Como máximo dos multiplicadores extremos a la vez.
4. Redondear a 1.000 €.

No calcular cuando:
- ninguna fila corresponde al puesto
- el puesto está bajo convenio
- la fila es Treasury Analyst / Junior Treasurer (cifras de nivel manager)
  o Konzerncontroller (fuentes discrepan)

### 3. Escribir el bloque
Anteponerlo al `.txt`. Nada más cambia en el archivo.

```
# ── Gehalt ──
GEHALTSVORSTELLUNG: 52.000 € brutto/Jahr
GEHALT QUELLE:      anuncio | calculado
GEHALT NIVEL:       junior | professional
GEHALT BASIS:       Kreditanalyst · P25 × konzern 1,12
# ── Fin Gehalt ──
```

Si no se calcula: `GEHALTSVORSTELLUNG: -` y en `GEHALT QUELLE` el motivo,
por ejemplo `- · tarif TVöD E9b` o `- · sin fila`.

## Registro

Al terminar el lote, añadir las líneas a `ofertas/ranking.md`,
desplazando las lineas anteriores hacia abajo para hacer espacio para 
la nuevas puntuaciones que quedan arriba. Van ordenadas por puntuación
descendente, bajo un encabezado con la fecha.
No sobrescribir lo anterior.

## Mover las ofertas

Último paso del lote, después del Gehalt y del registro. Cada oferta
evaluada sale de la raíz de `ofertas/`: lo que queda en la raíz es
exactamente lo que falta por puntuar.

Siempre con `mkdir -p` y `mv`. El archivo viaja íntegro, byte por byte.
Nunca `rm`, nunca `cp`, y nunca volver a escribir el anuncio con la
herramienta de escritura: se gastan tokens y el texto puede alterarse.

| Puntos | Comandos |
|---|---|
| 6–8 | `mkdir -p "salidas/‹carpeta›"` y `mv "ofertas/‹archivo›" "salidas/‹carpeta›/stellenanzeige.txt"` |
| 3–5 | `mkdir -p ofertas/standby` y `mv "ofertas/‹archivo›" ofertas/standby/` |
| 0–2 | `mkdir -p ofertas/descartadas` y `mv "ofertas/‹archivo›" ofertas/descartadas/` |

### Carpeta de las 6–8
Nombre según la convención de `CLAUDE.md`: `[AAAA.MM.DD]_[Empresa]_[Puesto]`,
con la fecha del día. Empresa y puesto cortos y reconocibles, no el título
completo del anuncio.

Antes de crearla:
- Buscar la línea `REFERENCIA:` de la oferta en `salidas/*/stellenanzeige.txt`.
  Si ya existe, no crear carpeta: mover la oferta a `ofertas/descartadas/`.
- Si ya existe una carpeta con ese nombre, agregar `_2` al final.

## Procesamiento

Trabajar en lotes de **10 ofertas por vez**, empezando por las más
recientes de la raíz de `ofertas/`. Todas las que siguen en la raíz
están sin analizar: las evaluadas ya se movieron. El nombre de archivo
empieza por la fecha de publicación en formato `AAAA-MM-DD`, así que
ordenar los nombres al revés (descendente) es ordenar por fecha.
Solo cuentan los archivos cuyo nombre empieza por esa fecha.

Al terminar cada lote, entregar el resultado y esperar antes de
seguir. Nunca procesar la carpeta entera de una vez.

**Nunca borrar archivos.** Lo eliminado se mueve a `ofertas/descartadas/`.

## Límites
- No redactar nada de la postulación. Solo puntuar.
- No emitir juicio sobre la candidatura completa: de eso se encarga
  `revisor-postulacion`, después de que los documentos existan.
- Si una oferta no tiene descripción utilizable, marcarla como DUDOSO
  con el motivo, no inventar una evaluación.
- No modificar el contenido de las ofertas. Lo único que se escribe en
  un `.txt` es el bloque Gehalt, antepuesto.

Además, mantener `ofertas/candidatas.md`: la vista corta de trabajo,
solo con las ofertas de 3 puntos o más.

Este archivo **se reescribe entero** en cada actualización, a partir
del estado actual de `ranking.md`. Si una oferta fue reevaluada, vale
la puntuación más reciente. Ordenar por puntuación descendente y, a
igualdad, por distancia ascendente.

Formato de tabla, una fila por oferta:

| Puntaje | Veredicto | Oferta | Empresa | Distancia |
|---|---|---|---|---|
| 7 | POSTULAR | Online Marketing Manager (m/w/d) | VENTURA GmbH | 10 km |
| 4 | DUDOSO | Controller (gn) | Jungwild GmbH | 1 km |

Sin la línea de motivo: para eso está `ranking.md`.
`candidatas.md` es para decidir por dónde empezar.

## Modo automático (headless)

Se activa cuando la instrucción dice "modo automático".

- En modo automatico la skill no funciona por lotes, cada llamado establece
  cuantas ofertas se van a revisar.
- No esperar al terminar el lote.
- No entregar resultados en el chat: todo queda en los archivos.
  La confirmación de lectura no se escribe; la lectura se hace igual.
- Todo lo demás no cambia: techos, Gehalt, registro, `candidatas.md`
  y mover las ofertas.
- Nunca preguntar ni detenerse a consultar. Nadie va a responder.
- Toda oferta en la raíz se puntúa desde cero, aunque aparezca en
  `ranking.md`. No cruzar con el ranking ni reutilizar puntajes anteriores.
- Si algo no calza con estas instrucciones, puntuar igual y seguir.