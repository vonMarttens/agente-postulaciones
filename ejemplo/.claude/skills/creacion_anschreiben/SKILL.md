---
name: creacion_anschreiben
description: Redacta el Anschreiben en alemán para una oferta concreta y compila el PDF desde Typst. Úsala cuando el usuario pida una carta de motivación, un Anschreiben o una carta de presentación para una vacante.
---

# Generación de Anschreiben

## Principio rector
La carta no repite el CV: le da contexto. El CV dice qué hizo el usuario;
la carta cuenta una o dos veces cómo lo hizo y por qué importa aquí.

Todo lo afirmado debe estar documentado en `contexto/`. No se inventa nada.

Idioma de trabajo: español. Idioma de salida: alemán.

## Fuentes
- `contexto/` — datos duros por puesto
- `contexto/anekdoten.md` — episodios narrativos (situación → acción → resultado)
- `CLAUDE.md` — perfil, restricciones y terminología prohibida

Si `contexto/anekdoten.md` no contiene ningún episodio
utilizable para esta oferta, **detenerse y preguntar al usuario**.
Nunca compensar la falta de material con frases genéricas.

## Paso 0 — Obligatorio en todos los modos

Antes de tocar ninguna carpeta:

```
python cola.py --rutas
```

Devuelve una línea por postulación con el formato `ESTADO<tab>ruta`.
**Trabajar solo sobre las carpetas del estado que corresponde al modo.**

- Modo → `LISTA PARA ANSCHREIBEN`

En modo automático la ruta de la carpeta viene en la instrucción: no correr
`cola.py` ni buscar otras carpetas.

Nunca recorrer `salidas/` a mano ni abrir carpetas de otros estados.
`cola.py` ya calculó el estado leyendo archivos, gratis; redescubrirlo
carpeta por carpeta cuesta tokens y da el mismo resultado.

Si el estado buscado no aparece en la salida, no hay trabajo: decirlo en
una línea y terminar.

---

## Paso 1 — Leer la oferta
Extraer y mostrar antes de redactar:
- Denominación exacta del puesto y número de referencia si existe
- Nombre de la persona de contacto si aparece
- Las tres exigencias que la empresa repite o pone primero
- Qué hace la empresa: modelo de negocio, mercado, producto

Si la carta sigue a una adaptación de CV, reutilizar las keywords ya
clasificadas y las objeciones detectadas en la autoevaluación.

## Paso 2 — Seleccionar el material
Elegir y declarar antes de escribir:
- **Un episodio principal** de `anekdoten.md` que responda a la exigencia
  más importante del anuncio
- **Una objeción a desactivar**: la duda previsible del reclutador
- **Un elemento de transferencia (obligatorio)**: la trayectoria que
  conecta la experiencia previa con este puesto. De dónde viene,
  por qué el cambio, por qué ahora. Nunca se omite: sin él, el lector
  construye su propia hipótesis sobre los saltos del CV.

Esperar validación del usuario antes de redactar.

## Paso 3 — Redactar
Rellenar los placeholders de `Anschreiben.typ`. Una página, sin excepción.

**Einstieg** (2–3 líneas)
Empezar por lo que conecta con el puesto, no por el acto de postular.
Prohibido: "hiermit bewerbe ich mich", "mit großem Interesse habe ich
Ihre Stellenanzeige gelesen".

**Fachliche Passung** (el bloque más largo)
El episodio principal contado de forma comprimida: situación, qué hizo,
resultado con cifra. Ligado explícitamente a lo que pide el anuncio.

Si el anuncio nombra herramientas concretas como ejemplos de una categoría
más amplia (p. ej. "CMS (z. B. TYPO3)") y la herramienta real del usuario
en esa categoría es otra (p. ej. Shopify), nombrarla explícitamente en vez
de esconderse detrás de la categoría genérica. No comparar niveles ni
escala entre su herramienta y las que nombra el anuncio — solo nombrar la
propia.

**Transfer** (un párrafo)
Lo transferible de otra etapa. Aquí se desactiva la objeción prevista
sin nombrarla nunca.

**Nivel de alemán.**
Si la oferta pidió "sehr gute Deutschkenntnisse" o C1 y pasó el filtro
previo, el Anschreiben debe abordarlo sin que parezca una excusa.

Cómo: mencionarlo como hecho dentro de una frase que hable de otra cosa
—de lo que el usuario hace en alemán, no de lo que le falta. El nivel
y los certificados de alemán están en `CLAUDE.md`.

Nunca: pedir disculpas, prometer mejorar, decir "auch wenn mein
Deutsch...", ni dedicarle una frase propia. Una limitación que ocupa
su propia oración se convierte en el tema del párrafo.

Si el idioma no aparece como requisito destacado en el anuncio, no se
menciona en absoluto.

**Motivation** (un párrafo corto)
Por qué esta empresa en concreto. Debe contener algo que solo aplique
a ella: su mercado, su producto, su modelo. Si no hay nada específico
que decir, el párrafo se acorta antes que rellenarse.

## Paso 4 — Reglas de escritura
- Frases cortas. Voz activa. Sin Substantivierungen innecesarias.
- Nada de: "Teamplayer", "Hands-on-Mentalität", "Leidenschaft für",
  "belastbar", "dynamisch" — salvo que el anuncio use el término literalmente.
- Ninguna cifra que no esté en `contexto/`.
- Respetar las prohibiciones de terminología de `CLAUDE.md`.
- Las keywords del anuncio se integran en frases con sentido,
  nunca listadas.

## Paso 5 — Generar y compilar
Localizar la carpeta de esta postulación en `salidas/`. Si ya existe una
del formato `[AAAA.MM.DD]_[Empresa]_[Puesto]` para esta oferta —creada
por `cv-adaptar-oferta`— usar esa. **No crear una segunda.**
Si no existe, crearla con esa misma convención.

Copiar `Anschreiben.typ` a
`salidas/[carpeta]/Anschreiben_‹apellido›_[Empresa]_[Puesto].typ`
y editar la copia. **Nunca modificar el maestro.**
`‹apellido›` es el valor de `apellido_archivo` en `perfil.json`.
Si la plantilla usa `Unterschrift.jpg`, la copia necesita acceso a ella: ajusta la ruta de la imagen.

`typst compile Anschreiben_‹apellido›_[Empresa]_[Puesto].typ`

Verificar: una sola página, Betreffzeile con la denominación exacta del
anuncio, saludo con nombre si lo había.

## Paso 6 — Verificación ATS y de veracidad (obligatorio)
- ¿Qué aporta esta carta que el Lebenslauf no diga ya? Si la respuesta es "nada",
  rehacerla.
- ¿Podría enviarse a otra empresa cambiando el nombre? Si sí, falta
  concreción en Motivation.
- ¿Alguna afirmación carece de respaldo en `anekdoten.md`?

No emitir veredicto sobre la candidatura.

## Modo automático (headless)

Se activa cuando la instrucción dice "modo automático" y trae la ruta de una
carpeta de `salidas/`.

- Trabajar solo esa carpeta. La oferta es su `stellenanzeige.txt`.
- Pasos 1 y 2: se hacen igual, pero no se muestran ni se declaran, y no se
  espera validación.
- Paso 6: se verifica igual, sin informe.
- Compilar desde la raíz del proyecto, sin `cd`:
  `typst compile --root . salidas/‹carpeta›/Anschreiben_‹apellido›_‹Empresa›_‹Puesto›.typ`
- Contar las páginas con `python contar_paginas.py salidas/‹carpeta›/‹archivo›.pdf`.
  Es el único verificador permitido: no escribir scripts propios para esto.
- Si no hay episodio utilizable en `anekdoten.md`, escribir `anschreiben_fallido.txt`
  en la carpeta con una línea de motivo y no redactar.