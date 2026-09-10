# Imágenes, recursos y archivos locales

No copies tus GIF a `assets` para usarlos: impórtalos desde **Pantalla LCD Cap**.
La app mantiene su propia copia en `~/.local/share/algor/media/` y puede optimizar
los originales sin modificarlos.

## Espacio de trabajo del autor

| Carpeta | Uso | Publicación |
|---|---|---|
| `local/media/originals/` | Nautilus1.GIF, Nautilus2.GIF, Tux.GIF y otros originales | Excluida |
| `local/media/optimized/` | Versiones preparadas y validaciones | Excluida |
| `local/design/` | Variantes de diseño y exportaciones antiguas | Excluida |
| `local/tools/` | Herramientas auxiliares descargadas | Excluida |
| `captures/` | Evidencia USB e informes privados | Excluida |
| `img/` y `bin/` | Enlaces de compatibilidad a las ubicaciones nuevas | Excluidos |
| `algor/assets/icons/Algor.svg` | Icono propio usado por la aplicación | Incluido |
| `algor/assets/memory/` | Muestras A/B/C capturadas durante investigación | Excluidas |

Los enlaces mantienen funcionando rutas antiguas guardadas en la app y comandos
locales. No borramos los originales. La copia pública funciona sin esas carpetas:
la memoria ofrece **Archivo propio** y las pruebas usan medios sintéticos.

Un nuevo GIF puede guardarse en `local/media/originals/` y después importarse desde
la GUI. Que un GIF esté excluido de Git no impide usarlo ni guardarlo en el LCD.
Los GIF grandes se mantienen separados para no aumentar cada clon del repositorio.

El autor confirmó que creó sus iconos y medios. Tux tiene una referencia de autoría
independiente; su GIF no se distribuye en esta versión. Ver THIRD_PARTY_NOTICES.md.
