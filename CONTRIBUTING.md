# Contribuir

La primera prioridad es validar el mismo LCD `1b1c:0c57` en otras placas y
escritorios Linux. Usa el formulario **Resultado de compatibilidad** y la guía
[COMPATIBILITY.md](docs/COMPATIBILITY.md). Distingue siempre observación física,
pruebas simuladas y funciones todavía no probadas.

## Desarrollo

Instala el entorno indicado en README. Antes de proponer un cambio:

```bash
python scripts/run_tests.py
python scripts/smoke_test.py
```

El primer comando aísla preferencias y datos; evita ejecutar las pruebas antiguas
con `unittest discover` directamente sobre tu configuración habitual. La prueba
GUI no requiere LCD. Una captura privada opcional no debe convertirse en requisito
para que el código público se pruebe.

Los cambios USB deben mantener identificación estricta del dispositivo, tiempos
acotados, propiedad exclusiva de la interfaz y ausencia de reintentos automáticos
de guardado en memoria. No actives control PWM/DC como parte de una prueba de
compatibilidad del LCD. Bomba y ventiladores siguen bajo BIOS por defecto; la
única excepción es el modo opt-in Reactivo sobre un canal probado y confirmado
por el usuario mediante el procedimiento guiado — ver
[docs/PWM_REAL_CONTROL.md](docs/PWM_REAL_CONTROL.md). La bomba nunca es
candidata, en ningún cambio que propongas.

Adjunta a tu PR el problema que resuelve, el comportamiento final, pruebas y
modelos físicamente verificados. No adjuntes configuración personal, medios,
volcados USB completos, números de serie ni registros sin revisar.

## Traducciones

El español es el idioma fuente (el texto que ya está escrito en el código);
no existe un catálogo `es.po` porque no hace falta. Cada texto visible pasa por
`_()` (`from algor.core.i18n import _`), y `gettext` detecta el idioma del
sistema automáticamente (`LANGUAGE`/`LC_ALL`/`LC_MESSAGES`/`LANG`) — sin
selector manual por ahora.

Para agregar un idioma nuevo:

```bash
mkdir -p algor/locale/<código>/LC_MESSAGES
cp algor/locale/algor.pot algor/locale/<código>/LC_MESSAGES/algor.po
# Traduce cada msgstr en el .po (Poedit o un editor de texto sirven)
bash scripts/i18n_compile.sh
```

Si agregas o cambias un texto visible en el código, corre
`bash scripts/i18n_extract.sh` primero — regenera `algor.pot` y fusiona los
cambios en cada `.po` existente sin perder traducciones ya hechas — y después
`bash scripts/i18n_compile.sh` para compilar el `.mo` que la app realmente lee
en tiempo de ejecución. CI valida que cada `.po` compile sin errores.

## CI

[Tests](.github/workflows/tests.yml) instala dependencias y ejecuta la suite y
la interfaz simulada en Python 3.10, 3.12 y 3.13. También prueba una copia pública
sin medios ni capturas locales. Sigue el patrón recomendado de
[GitHub para Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
Los resultados de CI no certifican compatibilidad con un dispositivo físico.
