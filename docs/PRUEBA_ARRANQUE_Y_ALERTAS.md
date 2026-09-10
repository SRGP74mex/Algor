# Alertas y arranque autónomo del LCD

## Implementado y probado sin hardware

- Temperatura CPU y GPU con disponibilidad explícita; CPU siempre supervisada,
  GPU supervisada una vez detectada su temperatura durante la sesión.
- Aviso tras 2 segundos, crítica inmediata y recuperación con histéresis de 3 °C.
  Umbrales editables en Ajustes. Los valores iniciales son configurables, no una
  certificación térmica para todos los procesadores.
- Pérdida de telemetría, temperatura no disponible y error LCD persistente.
  El temporizador de UI detecta si el trabajador deja de entregar muestras.
- No se da por recuperada una alarma térmica cuando desaparece la lectura.
- Notificación por cambio de estado, sin repetición en cada muestra; aviso de
  recuperación, indicador persistente en la ventana e historial JSONL rotatorio.
- La supervisión funciona mientras Algor se ejecuta, incluso en bandeja.
  No vigila mientras el equipo está suspendido o Algor está cerrado.
- No se infieren fallos de bomba o ventiladores a partir de canales sin mapear.
- El inicio automático usa el intérprete de la aplicación; sin bandeja disponible
  se abre la ventana para evitar un proceso invisible.
- Al detectar una pausa de más de 8 s (CLOCK_BOOTTIME incluye suspensión), la
  sesión suelta la interfaz y reenvía contenido y brillo al reconectar. Conserva
  los reintentos acotados en frecuencia y no repite escrituras de memoria.

## Prueba de notificación

Abre Ajustes y pulsa **Probar notificación**. Debe aparecer un aviso de prueba y
una entrada en **Abrir historial de eventos**. Las preferencias del escritorio,
como No molestar, pueden ocultar la notificación; el historial permanece.
No hace falta calentar el procesador para probar el aviso.

## Procedimiento de arranque en frío

1. Cierra iCUE y la VM; deja el LCD disponible para Linux.
2. Selecciona una imagen reconocible distinta de la almacenada y brillo conocido.
   Activa **Iniciar el LCD al abrir Algor** y en Ajustes activa **Iniciar
   automáticamente al iniciar sesión en Linux**.
3. Apaga Linux normalmente. Una vez apagado, corta la alimentación de la fuente
   hasta que se apague el LCD; el USB en espera impide considerar un apagado
   normal como pérdida total de alimentación del LCD.
4. Restablece alimentación e inicia directamente Linux sin abrir Windows/iCUE.
5. Comprueba la imagen seleccionada y el brillo. Si usas sensores, verifica que
   se actualicen. El estado «activo» acredita transferencia, no contenido visible.
6. Si falla, conserva el historial y anota lo que se ve. No añadir secuencias de
   inicialización desconocidas ni repetir guardados para resolver un fallo de sesión.

## Prueba física confirmada por el usuario: suspensión

Guarda tu trabajo, deja la sesión LCD activa, suspende y reanuda. Comprueba imagen,
brillo y valores actualizados. Repite con LCD detenido: debe seguir detenido.
El historial debe registrar el restablecimiento de una sesión tras la pausa.
No desconectes cables USB internos con el equipo encendido. La desconexión y
reaparición USB se han probado con transporte simulado; la verificación física
puede hacerse posteriormente mediante asignación/liberación en VMware.

## Evidencia y límites

Las pruebas automatizadas cubren estados de alertas, pérdida de lecturas,
histéresis, recuperación, rotación de historial, ausencia USB inicial y reanudación.
El usuario confirmó funcionamiento de notificaciones, apertura del historial,
arranque autónomo, colores y giro en su equipo. Esta es evidencia física reportada
por el usuario, adicional a las pruebas automatizadas. No detalló si retiró toda
la alimentación USB: no se da por verificado ese caso específico. Tras la prueba solicitada de suspensión y reanudación, el usuario informó que
carga sin problemas y el LCD recupera el contenido instantáneamente. Queda
confirmada esa recuperación en su equipo; no se midió la latencia ni se confirmó
por separado el caso de suspender con la sesión LCD detenida.
Historial: `~/.local/state/algor/events/events.jsonl` y hasta tres respaldos de
aproximadamente 1 MiB cada uno. No contiene imágenes ni volcados USB.
