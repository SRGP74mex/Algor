# Compatibilidad y validación comunitaria

| Entorno / función | Evidencia | Estado |
|---|---|---|
| Debian 13, X99 UD5, Xeon E5-2680 v4, LCD `1b1c:0c57` | Confirmación del usuario | LCD, brillo, giro, colores, imágenes/GIF en memoria y persistencia al salir |
| Mismo equipo: inicio autónomo y suspensión/reanudación | Confirmación del usuario | Funciona |
| Mismo equipo: notificaciones e historial | Confirmación del usuario | Funciona |
| Asistente de asignaciones y alertas RPM | Pruebas automatizadas y GUI simulada | Pendiente validación física completa |
| Encendido después de retirar toda alimentación USB | No confirmado por separado | Pendiente |
| Otras placas/distribuciones con el mismo LCD | Lectores implementados; sin confirmación comunitaria | Pendiente |
| Otros modelos de LCD Corsair | Sin transporte validado | No admitidos |
| Temperatura del líquido | Sin fuente verificada | No disponible |
| Control de velocidad desde la app | Simulación únicamente | BIOS gobierna bomba y ventiladores |

## Cómo reportar un equipo

1. Instala desde una copia del proyecto y anota versión/commit y cualquier paquete
   adicional necesario. No cambies voltajes ni curvas para probar el LCD.
2. Ejecuta `python scripts/diagnostics.py` desde el entorno virtual y revisa el JSON.
   No incluye configuración, hostname, números de serie ni imágenes.
3. Comprueba sensores, notificación de prueba y LCD: imagen, color, brillo y giro.
4. Si pruebas guardado, usa un archivo propio y confirma visualmente persistencia
   al salir. El guardado reemplaza el contenido previo de respaldo.
5. Prueba inicio autónomo y, después de guardar tu trabajo, suspensión/reanudación.
   No desconectes cables internos con el equipo encendido.
6. Abre un Issue **Resultado de compatibilidad** indicando Funciona / Falla /
   No probado por función. Adjunta solo registros pertinentes y revisados.

No deducimos compatibilidad universal por una sola prueba ni temperatura de líquido
por coincidencia numérica. Asignar una bomba requiere conocer el canal físico.
