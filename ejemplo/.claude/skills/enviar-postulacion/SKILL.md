---
name: enviar-postulacion
description: Prepara el borrador de correo de una postulación, confirma si salió y redacta el Nachfassen cuando no hay respuesta. Usa el MCP de Gmail y arranca siempre desde cola.py. Úsala cuando el usuario pida preparar el envío, mandar una postulación por correo, confirmar envíos, o hacer seguimiento de postulaciones sin respuesta.
---

# Envío y seguimiento de postulaciones por correo

## Principio rector

El envío final lo hace el usuario, nunca este agente. Esta skill deja un
**borrador** listo en Gmail — nunca lo envía, responde, reenvía ni borra
nada. Las herramientas que harían eso están bloqueadas a nivel de
permisos del proyecto (`.claude/settings.json`); si en algún momento
parecen no estar disponibles, es la restricción funcionando, no un error
que haya que sortear.

`bewerbung_gesendet.txt` es el único registro de si una postulación
salió. Ninguna otra parte del sistema lo sabe: no hay base de datos
aparte.

## Paso 0 — Obligatorio en todos los modos

Antes de tocar ninguna carpeta:

```
python cola.py --rutas
```

Devuelve una línea por postulación con el formato `ESTADO<tab>ruta`.
**Trabajar solo sobre las carpetas del estado que corresponde al modo.**

- Modo A → `ENVIAR POR CORREO`
- Modo B → `BORRADOR LISTO`
- Modo D → `ENVIADA · REVISAR`

Nunca recorrer `salidas/` a mano ni abrir carpetas de otros estados.
`cola.py` ya calculó el estado leyendo archivos, gratis; redescubrirlo
carpeta por carpeta cuesta tokens y da el mismo resultado.

Si el estado buscado no aparece en la salida, no hay trabajo: decirlo en
una línea y terminar.

---

## Modo A — Preparar el borrador

Sobre las carpetas en `ENVIAR POR CORREO`.

### Paso 1 — Leer `stellenanzeige.txt`

Del bloque `# ── Datos verificados a mano ──`: `KONTAKT`,
`ANSPRECHPARTNER`, `CHIFFRE`, `ANLAGEN`.
Del bloque general: `TITULO`, `EMPRESA`, `REFERENCIA`.

`cola.py` ya validó que hay un correo utilizable, así que no hace falta
repetir esa comprobación. Sí detenerse si no existen los PDF de CV y
carta en la carpeta.

### Paso 2 — Destinatario y asunto

- `to`: el valor exacto de `KONTAKT`.
- Asunto: `Bewerbung als {TITULO}`, con el título tal como está escrito
  en el anuncio, con todos sus caracteres alemanes.
- Si existe `CHIFFRE`, añadir `, {CHIFFRE}` — es el número interno que la
  empresa pide citar y sin él no pueden asociar la candidatura.
- Si no hay `CHIFFRE` pero sí `REFERENCIA`, usar
  `, Referenznummer {REFERENCIA}`.

### Paso 3 — Cuerpo del correo

El Anschreiben ya va adjunto en PDF. **El cuerpo no lo repite.** Un
reclutador alemán que abre un correo con la carta entera pegada y la
misma carta en PDF ve duplicación, no esfuerzo.

El cuerpo tiene un trabajo distinto: que el adjunto se abra. Cinco a
ocho líneas, en alemán, con esta estructura:

- Saludo con `ANSPRECHPARTNER` si hay nombre; si no, `Sehr geehrte Damen
  und Herren`.
- Una frase que diga a qué puesto se postula, con `CHIFFRE` o
  `REFERENCIA` si existen.
- **Una frase de gancho**: el dato más fuerte del Anschreiben para esta
  oferta concreta. La cifra del episodio principal, o lo que conecta
  directo con la exigencia que la empresa repite. No un resumen de la
  carta: la única línea que hace que valga la pena abrir el PDF.
- Una línea remitiendo a los adjuntos.
- Si `ANLAGEN` exige un dato que no está en la carta (fecha de
  incorporación, certificados concretos), va aquí, en una línea.
- Cierre estándar y nombre completo. Sin imagen de firma.

Leer el `.typ` del Anschreiben para sacar el gancho, no para copiarlo.

**Si falta contexto para escribir el gancho** —no se identifica cuál es
el episodio principal, o la carta no tiene una cifra utilizable—
detenerse y preguntarle al usuario antes de escribir algo genérico. Un
gancho vago es peor que ninguno: ocupa la línea que iba a hacer el
trabajo.

**Expectativa salarial:** solo si el anuncio o `ANLAGEN` la piden. La cifra
es la de `GEHALTSVORSTELLUNG` en `stellenanzeige.txt`, tal cual, en una
línea del cuerpo. Nunca calcularla ni estimarla: `cola.py` no deja llegar
aquí una carpeta que la pida sin cifra.

Fecha de incorporación: la de `CLAUDE.md`, Disponibilidad.

### Paso 4 — Escribir `correo.txt`

La skill no crea el borrador ni toca los PDF: pasarlos en base64 por el
conector no funciona. Escribe en la carpeta `correo.txt` con este formato
exacto:

```
PARA:    {KONTAKT}
ASUNTO:  {asunto del Paso 2}
ANEXOS:  estandar
---
{cuerpo del Paso 3}
```

`ANEXOS: vollstaendig` solo si el anuncio pide expresamente un documento
que está únicamente en el anexo completo.

### Paso 5 — Borrador y registro

Los hace `python crear_borrador.py --aplicar`: adjunta los tres PDF, crea el
borrador, verifica destinatario y adjuntos, y escribe `bewerbung_gesendet.txt`.
La skill no usa `create_draft` ni escribe `bewerbung_gesendet.txt`.

## Modo B — Confirmar el envío

Sobre las carpetas en `BORRADOR LISTO`.

1. Leer `THREAD_ID` de `bewerbung_gesendet.txt`.
2. `get_thread` con ese `threadId`. Un hilo puede contener un borrador
   sin enviar: solo cuenta como enviado si el mensaje aparece en
   enviados. Si `get_thread` no basta, `search_threads` con
   `in:sent to:{KONTAKT}`.
3. Si se confirma, cambiar la primera línea a
   `GESENDET AM: {fecha AAAA.MM.DD}`, conservando el resto del archivo.
4. Si sigue como borrador, **no tocar el archivo** y avisar de que está
   pendiente de que el usuario lo envíe.

Informe final: una línea por carpeta. Sin párrafos.

---

## Modo D — Nachfassen

Sobre las carpetas en `ENVIADA · REVISAR`: enviadas hace 14 días o más,
sin que se haya insistido todavía.

### Paso 1 — Comprobar si hubo respuesta

`search_threads` con `from:{KONTAKT}`. Si hay respuesta de la empresa,
**no redactar nada**: resumirle al usuario qué dice y de qué
postulación se trata. Una respuesta cambia el juego y la decide él.

### Paso 2 — Redactar el Nachfassen

Solo si no hubo respuesta. Como **borrador**, en el mismo hilo si es
posible.

Cuatro o cinco líneas, en alemán:

- Saludo con `ANSPRECHPARTNER` si hay nombre.
- Referencia a la candidatura: puesto, `CHIFFRE` o `REFERENCIA`, y la
  fecha de envío.
- Una frase que confirme el interés, sin repetir argumentos de la carta.
- Una pregunta sobre el estado del proceso.
- Cierre estándar.

**Lo que no se hace:** reclamar, sugerir que hubo demora, pedir
explicaciones, adjuntar de nuevo los documentos, ni repetir el gancho
del primer correo. Un Nachfassen es una pregunta cortés, no una segunda
postulación.

### Paso 3 — Registrar

Añadir a `bewerbung_gesendet.txt`:

```
NACHGEFASST AM: {fecha AAAA.MM.DD}
```

Con esa línea, `cola.py` deja de pedir acción sobre esa carpeta. **En
Alemania se insiste una vez, no dos.** Si el usuario pide un segundo
Nachfassen, advertírselo antes de redactarlo.

---

## Lectura acotada

Esta skill puede leer respuestas de una empresa, pero **solo** de un
remitente cuyo correo coincida con el `KONTAKT` de alguna carpeta de
`salidas/`. La lista de direcciones permitidas sale de esas carpetas y
de ningún otro sitio.

Nunca una búsqueda abierta de la bandeja de entrada, ni por nombre de
empresa, ni por asunto suelto.

Si una dirección tiene varios hilos —una empresa con dos vacantes y el
mismo contacto— distinguirlos por el asunto, que lleva el título del
puesto y el número de referencia. **Si no se pueden distinguir,
detenerse y preguntar** en lugar de sellar la carpeta equivocada: una
postulación marcada como enviada sin estarlo desaparece de la cola sin
que nadie se entere.

---

## No hacer

- No usar `send_message`, `reply`, `forward`, `trash_*`, `mark_*_spam`,
  ni las herramientas de labels, aunque parezcan disponibles. Si
  el usuario pide "enviar" el correo, recordarle que el envío es manual y
  señalarle el borrador ya creado.
- No recorrer `salidas/` sin pasar por `cola.py --rutas`.
- No leer correos de remitentes que no figuren como `KONTAKT` en alguna
  carpeta.
- No inventar `GESENDET AM` sin haberlo verificado contra Gmail.
- No sobrescribir un `GESENDET AM` que ya tenga fecha. Si hay
  discrepancia con lo encontrado en Gmail, avisar y no tocar nada.
