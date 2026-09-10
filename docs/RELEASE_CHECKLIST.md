# Preparación de la primera publicación

## Contenido preparado

- README con instalación en venv, alcance y límites de compatibilidad.
- `.gitignore` para capturas, registros, medios locales y metadatos de herramientas.
- Icono propio separado de los GIF personales; ninguna captura requerida para uso.
- Pruebas sintéticas de memoria y ejecutor con configuración aislada.
- CI Python 3.10/3.12/3.13 y prueba gráfica sin hardware.
- Formularios de errores/compatibilidad y diagnóstico revisable.
- Instalador de escritorio que conserva el intérprete del entorno virtual.

## Copia pública revisable

Desde la raíz del proyecto:

```bash
python scripts/export_source.py local/release/candidate
```

El destino debe ser nuevo. Se usa una lista explícita de archivos permitidos y
se excluyen enlaces, capturas, medios personales y notas específicas de la sesión.
Revisa esa copia antes de inicializar el repositorio público. No uses `git add -f`
para incluir los originales excluidos. La exportación no crea remotos ni publica.

Dentro de la copia exportada, ejecuta el procedimiento de instalación del README
y ambas pruebas. El caso de comparación contra una captura privada se omite;
los otros casos de memoria no necesitan archivos privados.

## Antes de publicar

- ~~Elegir el nombre público definitivo~~ — decidido: **Algor**.
- Elegir cuenta/repositorio y revisar los archivos que se van a compartir.
- Ejecutar CI en GitHub; el archivo preparado no equivale a una ejecución exitosa.
- Crear una versión preliminar con la matriz de compatibilidad, sin prometer
  soporte universal ni control físico de ventiladores.

La instalación limpia local significa un venv nuevo con dependencias descargadas,
una copia pública sin capturas y configuración temporal. No sustituye una prueba
sobre una instalación nueva del sistema operativo ni en otras distribuciones.
