# Asistente de identificación y alertas RPM

Acceso: **Ajustes → Identificar bomba y ventiladores…**.

**Desde 2026-09-09 el asistente también lista canales de temperatura**, no solo
ventiladores — cualquier `temp*_input` de hwmon, de cualquier chip. La lista
se filtra a lo que responde de verdad: RPM>0 para ventiladores, 0–125°C para
temperatura (descarta lecturas de diodo desconectado, p. ej. un canal leyendo
-55°C, que no es "cero real"). Un canal ya guardado sigue apareciendo aunque
momentáneamente no responda. Esto permite vincular empíricamente una lectura
de temperatura sin etiqueta clara del fabricante al rol **Líquido /
Refrigerante** — igual que ya se hace con la bomba, nunca se adivina entre
varios candidatos confirmados. Ver [PWM_REAL_CONTROL.md](PWM_REAL_CONTROL.md)
para el resto de la filosofía de "nunca inventar datos".

1. Selecciona un canal y observa su lectura en vivo (RPM o °C). El
   identificador muestra chip, ruta física y entrada. No representa
   automáticamente un conector PWM.
2. Según el tipo de canal, asigna Bomba/Radiador/Chasis/Sin identificar/Sin
   conectar (ventiladores) o Líquido-Refrigerante/Sin identificar/Sin conectar
   (temperatura), y un nombre. Las alertas RPM (mínimo, duración) no aplican a
   canales de temperatura en esta versión.
3. Confirma la relación después de contrastar cableado/BIOS. Revisa cables con
   el equipo apagado. La aplicación no cambia velocidades para identificar.
4. Opcionalmente activa el aviso, configura mínimo y duración y pulsa Guardar
   asignación. Guarda cada canal antes de cambiar de selección.

Las asignaciones persisten en `fan_mappings` dentro de la configuración. No se
precargan asociaciones de este equipo en instalaciones de otros usuarios.
Los canales desconocidos, sin confirmar o sin conectar no producen alertas RPM.
Los canales identificados aparecen en Personalizar Panel y en el catálogo CSV.
Si hay exactamente una bomba confirmada, alimenta también el medidor Bomba AIO.
Si se confirman varias, ese medidor permanece no disponible para evitar elegir
una arbitrariamente; sus canales individuales siguen disponibles. Igual para
temperatura: exactamente un canal confirmado con rol Líquido/Refrigerante
alimenta el medidor Líquido AIO del Panel General; cero o varios lo dejan en
"sin verificar".

## Alertas

El mínimo inicial de 300 RPM es una propuesta editable, no un límite seguro
certificado para el componente. No hay alarmas habilitadas por defecto.
La duración se configura entre 3 y 60 segundos (5 inicial). Una bomba por debajo
del mínimo genera nivel crítico; otros ventiladores, aviso. Una lectura ausente
se notifica como desconocida, sin afirmar que el motor se haya detenido. El
margen de recuperación tras RPM bajas es 10 % del mínimo, al menos 50 RPM.
Cambios de estado y recuperaciones usan las notificaciones e historial existentes.
Desactivar una regla elimina su alarma sin fingir una recuperación física.
La supervisión global de Ajustes también debe estar activa.

## Identidad y límites

Los canales usan la ruta física de sysfs y no `hwmonN`, que puede variar entre
reinicios. Se redescubren en cada muestreo; un dispositivo ausente conserva su
asignación y muestra N/D. Cambiar de puerto o topología puede exigir una nueva
asociación. Los dispositivos virtuales sin identidad física diferenciable no se
asignan automáticamente. El catálogo antiguo de lecturas sigue disponible.
Un distribuidor puede entregar RPM de un solo ventilador de un grupo: la app no
puede comprobar individualmente los demás usando esa única lectura.

El control físico permanece en BIOS por defecto. Este asistente en sí mismo no
escribe PWM/DC ni prueba velocidades — solo identifica y alerta. El botón
«🧪 Probar control PWM real (avanzado)…» abre un flujo aparte, opt-in, que sí
puede escribir PWM sobre el canal seleccionado con permiso explícito instalado
por separado; nunca se habilita para la bomba. Ver
[PWM_REAL_CONTROL.md](PWM_REAL_CONTROL.md). Para este usuario, los conectores
4 y 5 vacíos deben quedar sin alarmas; no se infiere su correspondencia con
tacómetros por el número. La asociación ambigua de `it8620/fan2` queda a
elección explícita del usuario.

Validación: pruebas automatizadas de identidad, persistencia, confirmación,
canales vacíos, RPM bajas, histéresis, telemetría ausente y eliminación de reglas;
prueba GUI con datos simulados, sin escrituras al hardware.
