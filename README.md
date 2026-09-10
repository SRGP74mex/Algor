# Algor

Aplicación de escritorio para Linux: monitoreo de sensores y personalización del
**Corsair Nautilus LCD Cap (`1b1c:0c57`)**. Proyecto independiente, sin afiliación
con Corsair.

**Versión preliminar para validación comunitaria.** La compatibilidad física confirmada
se limita al equipo indicado abajo; detectar un chip no equivale a validar todos sus conectores.

## Funciones y alcance

- Temperatura y carga de CPU, telemetría GPU y sensores disponibles en Linux.
- Panel personalizable, ventana y preferencias persistentes, exportación CSV.
- LCD: temperatura/carga, imágenes, GIF, color, brillo y rotación.
- Importación y optimización de archivos propios; guardado en memoria del LCD.
- Alertas de temperatura, pérdida de lecturas y errores LCD, con historial.
- Asistente para identificar bomba/ventiladores y habilitar alertas RPM por canal.

**Bomba y ventiladores permanecen controlados por BIOS por defecto.** Las curvas
de la app son una simulación: no escriben PWM salvo que actives explícitamente
el modo opt-in **Reactivo** (Ajustes → Control real de PWM) sobre un canal que
hayas probado y confirmado tú mismo — la bomba nunca es candidata, en ningún
modo, y Reactivo nunca se recuerda entre reinicios. No cambia voltajes. No
existe modo Cero RPM. Ver [docs/PWM_REAL_CONTROL.md](docs/PWM_REAL_CONTROL.md).
**La temperatura del líquido no está identificada** y se muestra como no disponible;
no se sustituye por una estimación ni por una temperatura de placa.

## Compatibilidad

El usuario probó el LCD Cap con Gigabyte X99 UD5, Xeon E5-2680 v4 y Debian 13:
imágenes/GIF guardados, persistencia al salir, brillo, giro, colores, notificaciones,
arranque autónomo y recuperación tras suspensión. La prueba de retirada total de
alimentación USB y la validación física completa del asistente RPM siguen pendientes.
Otros modelos de LCD no están admitidos por el transporte actual.

Hay lectores de sensores Intel/AMD y GPU NVIDIA/AMD; su disponibilidad depende del
kernel, drivers y equipo. Consulta [la matriz y guía de pruebas](docs/COMPATIBILITY.md).

## Instalación desde el código fuente

Requisitos: Linux de escritorio, Python **3.10–3.13**, entorno virtual, libusb y
bibliotecas gráficas Qt. La validación local de instalación se hizo con Python 3.13;
la matriz de CI comprueba 3.10, 3.12 y 3.13 cuando se ejecute en GitHub.

Descarga el ZIP desde **Code → Download ZIP**, extráelo y abre una terminal en
la carpeta que contiene este README. También puedes clonar la URL real que muestra
el botón Code del repositorio; no se necesita una URL de ejemplo.

En Debian 13 / Ubuntu, instala los requisitos del sistema:

```bash
sudo apt update
sudo apt install python3-venv libusb-1.0-0 libegl1 libopengl0 libxcb-cursor0
```

Crea el entorno e instala las dependencias:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python main.py
```

No ejecutes la aplicación con sudo. Otras distribuciones requieren los paquetes
equivalentes; todavía necesitan pruebas comunitarias. Las dependencias nativas
se describen en [Qt para Linux](https://doc.qt.io/qt-6/linux-requirements.html).
`requirements-tested.txt` registra las versiones exactas del ensayo local; para
repetirlo con Python 3.13 puedes instalar ese archivo en un entorno nuevo.

### Acceso USB al LCD

Puedes probar la interfaz y sensores sin conceder acceso al LCD. Para usarlo,
revisa e instala la regla específica:

```bash
bash setup_udev.sh --print-rules
sudo bash setup_udev.sh
```

Reinicia después de instalarla. La regla da acceso únicamente al USB `1b1c:0c57`
a la sesión local activa mediante systemd-logind. No concede permisos PWM/DC ni
acceso general a otros USB. Si usas una VM, libera el LCD para Linux antes de iniciar
la sesión; Windows e iCUE no son requisitos de uso de la app.

### Acceso desde el menú de aplicaciones

```bash
.venv/bin/python scripts/install_desktop.py
```

El acceso usa el intérprete del entorno virtual. Conserva la carpeta del proyecto
y `.venv`; si los mueves, vuelve a ejecutar el instalador desde la nueva ubicación.
En Ajustes puedes habilitar el inicio de Algor al iniciar sesión. Para activar
el LCD automáticamente, marca también **Iniciar el LCD al abrir Algor**.

## Primer uso

1. Revisa los sensores del Panel General; N/D significa que no hay lectura válida.
2. En **Pantalla LCD Cap**, selecciona sensores o importa una imagen/GIF y pulsa
   **Iniciar LCD**. Brillo y giro se aplican a la sesión.
3. Para conservar contenido al salir, detén la sesión, pulsa **Preparar / optimizar
   imagen o GIF…**, revisa el resultado y **Guardar archivo propio**. Esto reemplaza
   el contenido de respaldo. Confirma visualmente la persistencia al salir.
4. En Ajustes, prueba una notificación y configura umbrales adecuados a tu equipo.
5. Usa **Identificar bomba y ventiladores…** para asignar canales confirmados;
   las alertas RPM están desactivadas por defecto. Los canales vacíos quedan excluidos.

La memoria preparada admite hasta **150 cuadros y 12 MiB**, límites de la app,
no una medida de la capacidad física del LCD. La optimización acepta fuentes de
hasta 25 MiB/600 cuadros con límites adicionales de píxeles. Mantiene la duración
aproximada, pero el intervalo común puede alterar pausas individuales de GIF.

Tus medios se importan a `~/.local/share/algor/media/`; no debes copiarlos al
código ni a `assets`. [Organización de medios](docs/MEDIA.md).
Las muestras locales A/B/C de investigación son opcionales y no se distribuyen.

## Pruebas y diagnóstico

```bash
.venv/bin/python scripts/run_tests.py
.venv/bin/python scripts/smoke_test.py
.venv/bin/python scripts/diagnostics.py
```

El ejecutor aísla la configuración en una carpeta temporal. La prueba gráfica usa
trabajadores simulados y no escribe al USB/PWM. Una comparación opcional con captura
USB se omite si no están las capturas privadas; las pruebas de memoria restantes
usan datos sintéticos. CI está definido en [.github/workflows/tests.yml](.github/workflows/tests.yml);
no se presenta como ejecutado hasta que GitHub produzca resultados.

El diagnóstico muestra versiones, placa, identificadores Corsair y canales de
sensores; no exporta configuración, números de serie ni imágenes. Revísalo antes
de adjuntarlo a un reporte. El historial de eventos está en
`~/.local/state/algor/events/`, accesible desde Ajustes.

## Organización

```text
algor/                 Código y recursos de la aplicación
algor/assets/icons/    Icono propio distribuible
scripts/               Pruebas, diagnóstico e instalación
tests/                Pruebas automatizadas
docs/                 Guías y compatibilidad
.github/               CI y plantillas de reportes
```

En el espacio de desarrollo, `local/`, `captures/` e `img/` contienen medios,
archivos históricos o enlaces locales excluidos de Git. No forman parte de la
instalación pública. [Preparación de publicación](docs/RELEASE_CHECKLIST.md).

## Desinstalación

```bash
.venv/bin/python scripts/install_desktop.py --uninstall
```

Retira el acceso y el autoinicio, conservando configuración y medios. Después puedes
borrar manualmente la copia del proyecto y su entorno si ya no los necesitas.
La regla USB se conserva; para retirarla, elimina únicamente
`/etc/udev/rules.d/70-corsair-algor.rules` y reinicia. Los datos personales están
en `~/.config/algor/`, `~/.local/share/algor/media/` y
`~/.local/state/algor/`; no se eliminan automáticamente.

## Contribuir y licencia

Consulta [CONTRIBUTING.md](CONTRIBUTING.md), el [asistente RPM](docs/ASISTENTE_VENTILADORES.md)
y la [hoja de ruta](docs/ROADMAP.md). Los formularios de Issues recogen errores y
resultados de compatibilidad sin exigir capturas USB completas.

Código bajo [GPL-3.0](LICENSE). Recursos y marcas: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
