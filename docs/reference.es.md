# Referencia: contratos, insights, imagen y operación

[English](reference.md) · Volver al [README](../README.es.md)

## Contratos de esquema

```bash
python app.py sample.csv --infer-schema schema.yaml   # escribe el contrato a partir de un archivo que sabes que está bien
python app.py new_export.csv --schema schema.yaml     # valida contra él cada archivo nuevo
```

El contrato inferido fija las columnas, sus tipos y si admiten vacíos, y nada más. El `infer_schema` de pandera también convierte el mínimo y el máximo del archivo de referencia en reglas de rango, y eso rechazaría casi cualquier archivo nuevo válido; `write_schema` las quita. Las reglas de negocio se agregan editando el YAML, por ejemplo `checks: {greater_than_or_equal_to: 0}` debajo de una columna.

Un archivo que rompe el contrato termina con código `3` y una línea legible por problema, no con un traceback de pandera:

```text
Error: missing column 'revenue'
Error: column 'units': expected int64 values, found 'twelve' (line 3)
```

`describe_failures` agrupa la tabla de fallas por columna y problema, muestra máximo 3 ejemplos y no repite errores en cadena: una celda que falló la validación de tipo no se reporta otra vez como falla de rango.

## Insights con IA (opcional)

`--insights` le pide a Google Gemini que lea las estadísticas que la herramienta acaba de imprimir y las explique en lenguaje sencillo. Sin esa opción la herramienta no hace ninguna llamada de red.

```bash
GEMINI_API_KEY=... python app.py sample.csv --insights
GEMINI_API_KEY=... python app.py sample.csv --insights --insights-anonymize   # oculta también los nombres de columna

docker run --rm -e GEMINI_API_KEY -v "$PWD:/data" data-tool python app.py /data/your.csv --insights
```

| Se envía a Google | Nunca se envía |
|---|---|
| Número de filas y columnas | Ninguna celda de ninguna fila |
| Nombres de columna, salvo con `--insights-anonymize` | El archivo ni su ruta |
| Tipos y cantidad de vacíos por columna | Los valores más frecuentes de las columnas de texto |
| La tabla numérica de `describe()` | La API key en la URL o en el cuerpo: viaja en un header |

Las columnas de texto se reportan solo con su tipo y su conteo de vacíos. El `describe()` de pandas pondría su **valor real** más frecuente en la fila `top`, y eso es dato de verdad. El payload tiene un tope de 6.000 caracteres para que un archivo muy ancho no se vuelva una subida sin límite.

La key se lee solo del entorno: nunca se guarda en el repo, nunca queda dentro de la imagen (`-e GEMINI_API_KEY` pasa la que ya tienes en tu shell) y nunca se imprime, ni siquiera en un mensaje de error. Una key gratis se saca en <https://aistudio.google.com/apikey>.

## Tags de la imagen y verificación

| Tag | Qué es |
|---|---|
| `latest`, `1`, `1.2`, `1.2.3` | Versiones estables, salen de tags de Git `vX.Y.Z` |
| `edge` | El último commit de `main`; puede cambiar en cualquier momento |
| `build-linux-amd64`, `build-linux-arm64` | Tags internos de paso que necesita el workflow porque `docker push` no sube un manifiesto sin tag. No usarlos |

En scripts fija una versión completa o un digest. El contenedor corre con UID `10001`, así que la carpeta montada tiene que poder leerla ese usuario.

```bash
docker buildx imagetools inspect ghcr.io/juanberrio0399/dockerized-data-tool:latest   # las dos plataformas
docker pull --platform linux/arm64 ghcr.io/juanberrio0399/dockerized-data-tool:latest # forzar una
gh attestation verify --owner juanberrio0399 \
  oci://ghcr.io/juanberrio0399/dockerized-data-tool:latest                            # procedencia
```

## Decisiones y límites

**Un contenedor y no un paquete de PyPI.** Un wheel fija las librerías de Python y nada más: ni el intérprete ni las librerías del sistema que usa pandas. La imagen fija las tres cosas, así que la herramienta que corre en el portátil de un compañero es la misma que corre en un job de CI.

**Build en dos etapas, sin root, UID fijo.** Las dependencias se instalan en `/opt/venv` en una etapa de build y solo se copia el venv terminado, así que ni la caché de pip ni restos del build llegan a la capa final. `apt-get upgrade` corre en la etapa final porque la base `python:3.14-slim` va atrasada en parches de seguridad de Debian: Trivy encontró CVE CRITICAL/HIGH con arreglo disponible en `perl-base`, `gzip`, `pcre2` y `sqlite` sobre una base sin actualizar. Los archivos de la app son de root, así que el proceso, que corre como `appuser`, no puede reescribir su propio código. pip, setuptools y wheel se eliminan del venv y del Python del sistema de la imagen base: nada los importa en tiempo de ejecución y un paquete que no está no puede ser vulnerable (quitarlos eliminó cuatro hallazgos HIGH). El UID `10001` es numérico y fijo para que Kubernetes lo acepte con `runAsNonRoot`.

**Trivy bloquea con `ignore-unfixed`.** Fallar por CVE de la base que todavía no tienen parche dejaría el check en rojo para siempre, y entonces nadie lo miraría. Fallar solo por CRITICAL/HIGH que ya tienen arreglo hace que cada build en rojo tenga algo que hacer.

**Sin caché de build entre corridas.** Cada build vuelve a correr `apt-get upgrade` para que una versión siempre lleve los últimos parches. Una caché podría servir una capa de actualización vieja, y como las dos plataformas compilan de forma nativa en un par de minutos, ahorraría poco.

**Gemini recibe agregados, nunca filas.** La alternativa, mandar una muestra de los datos, da una explicación mucho mejor y vuelve la herramienta inservible para cualquier cosa privada. El límite de lo que sale del equipo se aplica en `stats_payload`, no en el prompt.

**Los contratos de pandera son estructurales por defecto.** Un contrato que también guardara los rangos del archivo de referencia fallaría con los datos del mes siguiente y le enseñaría a todo el mundo a no volver a usar `--schema`.

Lo que no hace, a propósito:

- **No escribe archivos de salida.** El resumen va a stdout; no hay `--output`. `--infer-schema` es lo único que escribe.
- **Sin gráficas ni reporte de perfilado.** Solo `describe()`.
- **Solo CSV.** Ni Parquet, ni Excel, ni JSON.
- **Lee el archivo completo.** `pd.read_csv` lo carga en memoria; no hay modo por lotes ni streaming, así que un archivo más grande que la RAM va a fallar.
- **Sin archivo de configuración.** Todo es una opción o una variable de entorno.
- **Sin trucos de entrypoint en la imagen.** `CMD` corre `python app.py sample.csv`; cualquier otra cosa se pasa como comando completo.

## Operación

| Qué corre solo | Cuándo | Dónde queda el resultado |
|---|---|---|
| `tests.yml`: Ruff, pytest, build de la imagen, Trivy, revisiones de no-root y de códigos de salida | cada push a `main`, cada PR, lunes 12:00 UTC | Checks de Actions |
| `publish.yml`: build y escaneo de las dos plataformas | cada PR (nunca publica), cada push a `main`, cada tag `v*.*.*` | Checks de Actions; un resumen del job con cada digest |
| `publish.yml`: publicación | push a `main` → `:edge`; tag `vX.Y.Z` → `:X.Y.Z`, `:X.Y`, `:X` y `:latest` | Paquete en GHCR, con sus atestaciones |
| `codeql.yml`: SAST, `security-extended` | cada push a `main`, cada PR, lunes 06:00 UTC | Security → Code scanning |
| Dependabot: Actions, pip y Docker, agrupados | semanal, los martes | un PR con la etiqueta `dependencies` |

El cron semanal de `tests.yml` existe porque aparecen CVE nuevos en la imagen base aunque no haya commits; una corrida programada en rojo quiere decir que hay que reconstruir la imagen base, no que se dañó el código.

Para sacar una versión: crea el tag `vX.Y.Z` sobre `main` y súbelo. Para ensayar la publicación sin sacar versión, corre `publish.yml` a mano con el input `test_tag` (por ejemplo `citest`) y después borra esa versión del paquete.

Cuando algo falla:

- **Trivy tumba el job.** Apareció un CVE CRITICAL/HIGH con arreglo en la imagen base. Volver a correrlo casi siempre lo resuelve porque el build repite `apt-get upgrade`; si no, hay que mover la base `python:3.14-slim`.
- **Falla "Verify the pushed image is the scanned image".** El registro devolvió algo distinto a lo que se construyó. No lo rodees con otro tag; vuelve a correr el job.
- **Falla la verificación del manifest list.** El índice recogió una entrada que no es ninguno de los dos digests escaneados. Puede que otra corrida simultánea movió los tags de paso; el grupo `concurrency` debería evitarlo, así que investiga antes de volver a publicar.
- **`gh attestation verify` falla para un tag.** La procedencia se atestigua contra digests. Primero resuelve el tag con `docker buildx imagetools inspect` y verifica el digest.
