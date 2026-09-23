---
name: cv-adaptar-oferta
description: Adapta el CV del usuario a una oferta concreta optimizando para ATS y compila el PDF final desde Typst. Úsala cuando el usuario pegue un anuncio de trabajo y pida adaptar el CV, redactar los bullets de experiencia o seleccionar las Fähigkeiten del sidebar, cuando cola.py muestre carpetas en SIN DOCUMENTOS, o cuando se invoque en modo automático.
---

# Adaptación de CV por oferta

## Principio rector
Reescribir con libertad, mentir nunca. Cada afirmación debe corresponder a algo
documentado en `contexto/`. Dentro de ese límite, buscar la formulación más
fuerte posible para el ATS y para el lector humano.

Idioma de trabajo: español. Idioma de salida: alemán.

## Estructura intocable
`Lebenslauf.typ` es la única fuente de verdad estructural. Nunca se modifican:
- Títulos de puesto, empleadores, ubicaciones, fechas
- Orden, nombre y existencia de las secciones
- Qué entradas existen; no se añaden ni se eliminan puestos
- Contacto, foto, sección Ausbildung
- Las entradas de Zertifikate & Nachweise
- Porcentajes de los idiomas

Lo único que se escribe: los bullets de Berufserfahrung y las entradas de
`sidebar_skills`.

## Paso 0 — De dónde sale la oferta
Hay dos entradas:

- **Carpeta ya creada.** `ofertas-filtrar` crea la carpeta en `salidas/` con
  su `stellenanzeige.txt` para cada oferta de 6–8 puntos. Correr
  `python cola.py --rutas` y trabajar sobre las carpetas en `SIN DOCUMENTOS`,
  una por vez. El anuncio es el `stellenanzeige.txt` de esa carpeta.
- **Anuncio pegado a mano** (StepStone, LinkedIn): no hay carpeta. Se crea
  en el Paso 5.

## Paso 1 — Extracción de keywords
Del anuncio, extraer: competencias técnicas, herramientas nombradas,
certificaciones, títulos exigidos, verbos de la descripción de tareas,
términos del sector.

Clasificar contra el material de `contexto/` y mostrar antes de continuar:
- (a) Respaldadas por experiencia documentada
- (b) Parcialmente respaldadas — indicar cómo se matizaría
- (c) Sin respaldo

Si (c) contiene requisitos excluyentes, advertirlo antes de seguir.

## Paso 2 — Reparto de peso entre puestos
Antes de redactar, decidir cuánto espacio recibe cada entrada según su
relevancia para esta oferta, y declararlo:
- Puesto central: 4–5 bullets
- Puesto de apoyo: 2–3 bullets
- Puesto marginal: 1 bullet

## Paso 3 — Bullets de experiencia
Redactar en alemán, extrayendo únicamente de `contexto/`.
- Formato: verbo de acción + qué + resultado medible cuando exista.
- Priorizar bullets con cifras verificables.
- Ordenar de mayor a menor relevancia dentro de cada entrada.
- Nunca inventar cifras. Si un dato figura como no disponible en `contexto/`,
  no se estima ni se aproxima.
- Respetar las prohibiciones de terminología definidas en CLAUDE.md.
- Una competencia que aparece en el sidebar de Fähigkeiten pero no en
  ningún bullet de Berufserfahrung no está acreditada. Si el anuncio la
  pide de forma destacada, debe aparecer en un bullet con contexto de uso
  —qué se hizo, en qué marco, con qué alcance— si no hay datos se deja en sidebar,
  pero entremedio de la lista para evitar preguntas.

## Paso 4 — Fähigkeiten del sidebar
Seleccionar de las tablas de skills en `contexto/`.
- Formato Typst exacto: `skill("Nombre")`. Un solo argumento.
  **La función no acepta nivel.** No existe, no se inventa, y esta
  instrucción no se modifica.
- Entre 3 y 9 entradas; verificar tras compilar que caben en el bloque.
- Ordenar por relevancia para el anuncio.
- Respetar las exclusiones absolutas de CLAUDE.md.

## Paso 5 — Generar el archivo
**Carpeta ya creada:** no se crea otra ni se toca `stellenanzeige.txt`.
Trae los bloques que escribió `ofertas-filtrar` y tiene que quedar íntegro.

**Anuncio pegado a mano:** crear la carpeta
`salidas/[AAAA.MM.DD]_[Empresa]_[Puesto]/` y guardar ahí el texto íntegro
del anuncio como `stellenanzeige.txt`.

En los dos casos, dentro de la carpeta:
- Copiar `Lebenslauf.typ` como
  `lebenslauf_‹apellido›_[Empresa]_[Puesto].typ` y edita la copia. **Nunca modificar el maestro.**
  `‹apellido›` es el valor de `apellido_archivo` en `perfil.json`.
Si la plantilla usa `Bewerbungsfoto.jpg`, la copia necesita acceso a ella: ajusta la ruta de la imagen.

Sustituir los `‹placeholders›` y `sidebar_skills`. Nada más.

## Paso 6 — Compilar y verificar
`typst compile lebenslauf_‹apellido›_[Empresa]_[Puesto].typ`

Verificaciones obligatorias:
1. **Máximo 2 páginas.** Ajustar la cantidad de bullets hasta cuadrar.
2. **Prueba ATS:** abrir el PDF, seleccionar todo el texto, pegarlo en un
   archivo plano. Comprobar que el texto de Fähigkeiten y Sprachen aparece completo y en
   orden coherente.
3. Ninguna keyword del grupo (a) quedó fuera del documento.

## Paso 7 — Verificación ATS y de veracidad (obligatorio)
- ¿Qué keywords del grupo (a) quedaron fuera del documento?
- ¿Alguna afirmación no tiene respaldo en `contexto/`?
- ¿Alguna cifra se estimó en lugar de citarse?

No emitir juicio sobre la candidatura. De eso se encarga
`revisor-postulacion`.

## Paso 8 — Traspaso
Al cerrar, dejar disponible para la skill de Anschreiben:
- Las keywords de los grupos (a) y (b)
- Qué puesto se trató como central y con qué bullets
- Las objeciones detectadas en la autoevaluación

Ofrecer continuar con `creacion_anschreiben` para la misma oferta.

## Modo automático (headless)

Se activa cuando la instrucción dice "modo automático" y trae la ruta de
una carpeta de `salidas/`.

- Trabajar solo esa carpeta. No correr `cola.py` ni buscar otras.
- Pasos 1, 2 y 7: se hacen igual, pero no se muestran ni se declaran.
- Paso 8: no hay traspaso ni se ofrece continuar.
- No esperar confirmación en ningún punto.
- Compilar desde la raíz del proyecto, sin `cd`:
  `typst compile --root . salidas/‹carpeta›/lebenslauf_‹apellido›_‹Empresa›_‹Puesto›.typ`
- Contar las páginas con `python contar_paginas.py salidas/‹carpeta›/‹archivo›.pdf`.
  Es el único verificador permitido: no escribir scripts propios para esto.