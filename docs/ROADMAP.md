# Hoja de ruta — Algor

## Estado actual

- Telemetría Linux y panel general; sensores sin identificar permanecen no disponibles.
- Ventana con tamaño, posición y maximización persistentes.
- LCD Cap USB `1b1c:0c57`: imágenes, GIF, temperatura y carga de CPU,
  controles independientes de sensores, color, brillo y rotación.
- Sesión LCD en segundo plano y guardado de imágenes/GIF en memoria.
- Importación y optimización automática conservando los archivos originales.
- El usuario confirmó ambos GIF optimizados de aproximadamente 10 MiB y su
  persistencia al cerrar Algor. Esto no establece la capacidad física máxima.
- Curvas en simulación por defecto; bomba y ventiladores de este equipo siguen
  bajo BIOS salvo el modo opt-in Reactivo sobre un canal probado y confirmado
  (nunca la bomba). Ver [PWM_REAL_CONTROL.md](PWM_REAL_CONTROL.md).

## Prioridades

1. **Alertas operativas implementadas.** Temperatura CPU/GPU, pérdida de lecturas
   y fallo LCD con histéresis, notificaciones e historial. El usuario confirmó
   notificaciones e historial. Supervisión RPM implementada por canal confirmado;
   pendiente validación del asistente por el usuario.
2. **Arranque autónomo confirmado por el usuario en su equipo.** También confirmó
   colores y giro. Recuperación tras pausas y reconexión probada con transporte
   simulado; el usuario confirmó recuperación inmediata del LCD tras suspensión
   y reanudación. No se detalló
   retirada total de alimentación USB: [procedimiento y evidencia](PRUEBA_ARRANQUE_Y_ALERTAS.md).
3. **Identificación de sensores.** Asistente RPM implementado con asignaciones
   persistentes, roles y exclusión de conectores vacíos. Pendiente confirmar el
   mapa físico en la GUI. La temperatura del líquido sigue sin fuente verificada.
4. **GIF con pausas variables.** Investigar temporización por cuadro; actualmente
   la memoria utiliza un intervalo común y puede alterar pausas individuales.
5. **Distribución.** Validar instalación, permisos y desinstalación en otras
   distribuciones y equipos; ampliar compatibilidad por dispositivo probado.
6. **Experiencia de uso.** Galería con perfiles de pantalla y diagnósticos fáciles
   de exportar para soporte.

El control físico de ventiladores requiere soporte específico, identificación
inequívoca de canales y validación independiente. El USB del LCD no demuestra
que permita controlar bomba o ventiladores conectados a la placa.

## Licencia

Ver [LICENSE](../LICENSE) y [LICENSING.md](LICENSING.md).
