# Nautilus LCD Cap: protocolo de imagen observado

Fecha: 2026-09-08. Análisis offline, sin escrituras al hardware.
Captura: captures/20260908T191736_684579Z_image/lcd.pcapng
SHA-256: a63a45c67caf27be1cdbfa45a82988b24da9b2d6ad9e5dd4fc160d4985e493c6
Emisor: iCUE en Windows/VMware. Versiones comunicadas por el usuario: iCUE
5.49.34; Pump Display 5.46.0 (no identificada como firmware).

## Integridad

- 73,041 registros USB durante 30.229848 segundos; 44,400,852 bytes de archivo.
- Todos los registros son del bus 1, dirección 3, correspondiente a 1b1c:0c57
  según metadatos y descriptor USB capturado. La dirección no cambió al finalizar.
- 0 paquetes truncados, 0 payloads incompletos, 0 descartes según ifdrop de pcapng.
- 36,512 envíos interrupt OUT al endpoint 0x09 de 1,024 bytes; 36,511
  finalizaciones correspondientes con estado 0. El último envío queda pendiente
  al cortar la captura. -115 en los envíos es EINPROGRESS, no un error de terminación.
- 497 cuadros completos decodificados correctamente por Pillow; 417 hashes JPEG
  distintos. Un cuadro adicional queda incompleto al final. No hubo errores de
  secuencia o de formato entre los cuadros reconstruidos.
- Todos los JPEG completos miden 480 × 480. Tamaño comprimido: 33,237–103,858 bytes.
  Promedio observado: 16.44 cuadros completos/s; no es el máximo del dispositivo.

## Transferencia de imagen

Observado para este dispositivo/sesión, no especificación oficial de Corsair.
Cada envío observado tiene 1,024 bytes y contiene una cabecera de 8 bytes:

| Offset | Bytes | Interpretación respaldada por reconstrucción |
| --- | --- | --- |
| 0–1 | 02 05 | ID de reporte 02 y byte 05 observado |
| 2 | 03 inicialmente | Variable tras cambiar brillo; ver tercera captura |
| 3 | 00 / 01 | 01 coincide con el último fragmento de cada JPEG completo |
| 4–5 | uint16 little endian | Índice de fragmento, comienza en cero para cada cuadro |
| 6–7 | uint16 little endian | Cantidad válida de bytes de imagen en este fragmento; máximo 1,016 |
| 8… | datos | Fragmento JPEG; ignorar bytes posteriores a la longitud declarada |

Ejemplo de primer fragmento: `02 05 03 00 00 00 f8 03 ff d8 ff e0 …`.
Los fragmentos intermedios contienen 1,016 bytes. Concatenar exclusivamente los
bytes válidos produce un JPEG con delimitadores FF D8 / FF D9. Los bytes sobrantes
del último paquete pueden contener residuos: no deben incorporarse a la imagen
ni interpretarse automáticamente como comandos.

El descriptor de configuración describe interfaz 0 HID y endpoints interrupt
0x81 IN y 0x09 OUT, wMaxPacketSize=512 para ambos. Los envíos del anfitrión
capturados son de 1,024 bytes: wMaxPacketSize no es el tamaño del reporte completo.
El driver actual de la app confunde estas magnitudes y no envía píxeles.

## Transferencias de control

Se capturaron lecturas estándar de descriptores de dispositivo/configuración y
seis SET_REPORT HID de 32 bytes:

- bmRequestType=0x21, bRequest=0x09, wValue=0x0303, wIndex=0, wLength=32.
- Prefijo de datos observado: 03 19 03 01. Resto variable; función desconocida.
- No atribuir estos reportes a brillo, rotación o keepalive sin más capturas.
- No hay lecturas de temperatura ni RPM identificadas en esta toma. Esto no
  demuestra que el dispositivo nunca pueda ofrecer otras funciones.
- bcdDevice del descriptor: 0x0200. No asumir que sea una versión de firmware
  equivalente a la que muestra iCUE.

## Artefactos reproducibles

Ejecutar, indicando una carpeta de salida nueva:

```bash
python3 scripts/analyze_lcd_capture.py captures/20260908T191736_684579Z_image/lcd.pcapng /tmp/lcd-analysis
```

El analizador solo lee archivos. Comprueba el contenedor pcapng, el tipo USB,
secuencia/longitudes, delimitadores JPEG y decodificación completa de cada cuadro.
Guarda analysis.json con tiempos/hashes/controles y un JPEG de ejemplo cada cinco
segundos, además del último. La cabecera USB se interpreta como little endian,
correspondiente al anfitrión Linux x86-64 de esta captura.

Ejemplos ya extraídos en captures/20260908T191736_684579Z_image/analysis/:
frame_0000.jpg muestra la animación de ondas; last_frame.jpg muestra el logotipo
Corsair. Estos cuadros se inspeccionaron visualmente. No confundir el nombre
"image" de la captura con una toma estática: contiene un flujo animado.

## Siguiente validación

1. Capturar apertura de iCUE con el LCD ya asignado a Windows: iniciar captura
   antes de abrir iCUE. El tráfico aquí analizado ya estaba transmitiendo cuadros
   desde el primer registro, por lo que no demuestra la inicialización completa.
2. Capturar una sola modificación de brillo y una sola rotación en tomas separadas,
   manteniendo una imagen estática asimétrica para poder comparar. La rotación
   podría realizarse en los píxeles del anfitrión o mediante una orden al LCD;
   aún no está determinado.
3. Implementar primero codificación/fragmentación offline y verificar que un JPEG
   reconstruido coincide byte por byte. Luego probar envío físico controlado con
   VMware liberando el LCD y un único proceso Linux poseyendo el USB.
4. Validar reconexión en frío, errores, cierre e inicialización antes de integrar
   transmisión periódica en la GUI. No reproducir comandos desconocidos de forma
   indiscriminada ni usar esta evidencia para habilitar PWM o telemetría de líquido.

## Segunda captura: apertura de iCUE

Archivo: captures/20260908T201854_172582Z_baseline/lcd.pcapng
SHA-256: c05385b498638223c51fee68d43a64ddfc7c274deac0092d434a2ff272dedbbf
Resultado comunicado: «Arranque de iCUE».

89,600 registros, 60.042773 s, 0 descartes reportados, 0 truncamientos y 0 errores
de reconstrucción JPEG. Se reconstruyeron 739 cuadros completos (443 hashes
distintos), todos 480 × 480. Quedó un cuadro parcial al final y tres URB pendientes.
Se observó una finalización IN 0x81 con -108 (ESHUTDOWN) a t=6.886 s, sin envío
correspondiente dentro de la captura. Es consistente con cancelación/desactivación
de una transferencia previa durante la transición; no determina por sí sola la
causa. Después sí hay transmisión de imágenes con finalizaciones satisfactorias.

El primer fragmento JPEG aparece a t=14.218333 s; el primer cuadro finaliza a
14.272106 s. Esta vez se observan órdenes anteriores al flujo de imágenes.
No equivale a una prueba tras desconexión eléctrica ni demuestra cuáles órdenes
son estrictamente necesarias para iniciar la pantalla.

### Descriptor HID validado

Se capturó un descriptor de reportes HID de 381 bytes:
- Output report ID 0x02: 1,023 bytes de datos + ID = 1,024 bytes.
- Input report ID 0x01: 511 bytes de datos + ID = 512 bytes.
- Feature report IDs 0x03–0x16: 31 bytes de datos + ID = 32 bytes.

Esto confirma que el primer 02 de los cuadros es el identificador del reporte.
Los feature reports usan el endpoint de control; no se deben mandar como imágenes
por el endpoint interrupt OUT. Referencia sobre transporte HID:
https://docs.kernel.org/hid/hidraw.html

### Secuencia observada (tiempo relativo)

Además de enumeración estándar, SET_CONFIGURATION y SET_IDLE:

| t (s) | Operación | Datos significativos observados |
| --- | --- | --- |
| 7.5101 | SET_REPORT 0x0303 | 03 1d 01 00… |
| 7.5106 | GET_REPORT 0x0313 | Respuesta 13 01 00… |
| 7.5110 | SET_REPORT 0x0303 | 03 19 00 00… |
| 7.5123 | GET_REPORT 0x0305 | Respuesta incluye ASCII `0.3.0.5` en offsets 6–12 |
| 7.5808 | SET_REPORT 0x0303 | 03 0b 64 01… |
| 7.7448 | GET_REPORT 0x0311 | Respuesta 11 03 00… |
| 8.6160 | GET_REPORT 0x030f | Respuesta 0f 8e e2 8c 0a 00… |
| 14.2098 | SET_REPORT 0x0303 | 03 1b 00… |
| 14.2104 | SET_REPORT 0x0303 | 03 0c 03… |
| 14.2183 | Output report 0x02 | Primer cuadro JPEG |
| 14.2728 | SET_REPORT 0x0303 | 03 19 03 01… |

SET_REPORT: bmRequestType=0x21, bRequest=0x09, wIndex=0, wLength=32.
GET_REPORT: bmRequestType=0xa1, bRequest=0x01, wIndex=0, wLength=32.
Los valores completos y tiempos están guardados en analysis/analysis.json.

### Lo confirmado y lo que aún es hipótesis

- `0.3.0.5` es una cadena real respondida por el dispositivo. Es candidata a
  versión interna/firmware; no se confirmó su significado en iCUE. No confundirla
  con bcdDevice=0x0200 ni con la versión del módulo Pump Display.
- `03 0b 64 01` contiene 0x64=100; podría ser brillo u otro parámetro. Una captura
  con un cambio de brillo conocido debe probarlo antes de implementarlo como tal.
- Los once `03 19 03 01…` durante la transmisión ocurren justo tras un fragmento
  final. Sus bytes 4–31 coinciden exactamente con los del último fragmento de
  imagen anterior. Esto es consistente con reutilización de un búfer por iCUE:
  no interpretar esa cola variable como contraseña, checksum o estado sin evidencia.
- Las colas de otras órdenes también contienen datos de respuestas anteriores.
  No reproducir todos esos bytes como si su función estuviera establecida.
- Sigue sin identificarse temperatura de líquido ni tacómetro de bomba en esta
  captura. No derivar sensores de los números de los reportes.

Siguiente toma: brillo solamente, con imagen estática, anotar valor inicial/final
(por ejemplo 100% → 40%) y confirmar el cambio físico. Después, rotación solamente.
La inicialización ya tiene evidencia suficiente para preparar un prototipo offline,
pero el funcionamiento desde Linux todavía requiere una prueba física independiente.

## Tercera captura: brillo 100 % → 33 %

Archivo: captures/20260908T202626_848196Z_brightness/lcd.pcapng.
Metadatos: «Brillo 100to33»; cambio comunicado por el usuario: 100 % → 33 %.
65,382 registros, 30.247589 s, cero descartes, truncamientos o errores USB de
finalización. Todos los registros corresponden al bus 1, dirección 3.

### Órdenes correlacionadas con brillo

Dos SET_REPORT al endpoint de control, bmRequestType=0x21, bRequest=0x09,
wValue=0x0303, wIndex=0, wLength=32:

| Tiempo relativo | Primeros 4 bytes | Valor del byte 2 |
| --- | --- | --- |
| 4.6173 s | 03 0b 42 01 | 0x42 = 66 |
| 5.0972 s | 03 0b 21 01 | 0x21 = 33 |

Ambas operaciones terminan con estado 0. La primera es consistente con un valor
intermedio del deslizador; la segunda coincide exactamente con el destino
comunicado. En la captura de inicio apareció 03 0b 64 01 (100).

La evidencia respalda que 0x0b selecciona el ajuste de brillo y el byte 2 transporta
el porcentaje. El byte 3 es 01 en estas observaciones; su semántica aún no está
establecida. Las colas variables de 28 bytes siguen conteniendo restos de otros
buffers; no se ha validado físicamente un comando construido con relleno cero.
No se implementó ni ejecutó todavía una escritura de brillo desde Linux.

### Corrección importante del formato de imágenes

Tras cada orden de brillo, el byte 2 de los reportes de imagen cambia:

- Hasta t=4.633453: prefijo 02 05 03.
- Desde t=4.633453: prefijo 02 05 42.
- Desde t=5.113973: prefijo 02 05 21.

Por tanto, 02 05 03 NO es una firma invariable de tres bytes. El analizador
anterior rechazaba las variantes y producía falsos frame_errors. Ahora acepta
02 05 y registra el byte 2 por separado, conservando validación de índices,
longitudes, marcadores JPEG y decodificación completa.

El nuevo análisis reconstruye 541 JPEG válidos de 480 × 480, con cero errores de
cuadro y un cuadro parcial al final. Se guardó en analysis_v2/analysis.json;
el directorio analysis/ contiene el resultado del analizador anterior y queda
superado. La toma comienza con fragmentos de un cuadro ya iniciado, por lo que
ese cuadro inicial no se reconstruye como completo.

También los reportes periódicos 03 19 cambian su byte 2 de 03 a 21. Esto es
compatible con reutilización de buffers entre comandos y cuadros, pero no prueba
si el dispositivo ignora o utiliza ese byte en el flujo de imágenes. No asumir
que sea obligatorio repetir el brillo allí sin una prueba independiente.

Siguiente experimento: rotación con una imagen estática asimétrica, anotando
orientación inicial y final. No modificar brillo simultáneamente.

## Cuarta captura: rotación comunicada de 90°

Archivo: captures/20260908T203058_196098Z_rotation/lcd.pcapng.
Metadatos: «Girar90deg». 45,081 registros en 30.255826 s. Todos corresponden a
bus 1/dirección 3. Cero descartes reportados, paquetes truncados, errores de
reconstrucción o errores USB de finalización. Se reconstruyeron 738 JPEG completos
(607 hashes distintos); queda un cuadro parcial y un envío pendiente al final.

A t=5.5577 s se registra un SET_REPORT de 32 bytes:

- bmRequestType=0x21, bRequest=0x09, wValue=0x0303, wIndex=0, wLength=32.
- Prefijo: `03 0c 00 01`; finalización con estado 0.
- No aparecen órdenes 0x0b de brillo en esta toma.

Esto relaciona el selector 0x0c con el cambio de orientación realizado. El valor
capturado es 00; NO significa que «00 = girar 90°». Puede representar orientación
absoluta. En la captura de arranque se envió `03 0c 03…`; pasar de 03 a 00 es
compatible con un ciclo de cuatro posiciones, pero falta confirmar los ángulos
inicial/final y el sentido para documentar el mapa completo.

Las imágenes reconstruidas antes y después muestran texto horizontal y el logo
Corsair con la misma orientación. Ejemplos inspeccionados: frame_0000.jpg (0 s)
y frame_0244.jpg (10.007 s). Por tanto, la evidencia favorece rotación en el LCD
mediante la orden de control, no rotación de los píxeles JPEG por iCUE en esta toma.
La captura contiene texto/animación cambiante, no una imagen estática idéntica:
no se afirma comparación byte a byte de la misma imagen.

Tras la orden, el byte 2 de las cabeceras de imagen cambia de 0x21 a 0x00. También
los reportes periódicos 03 19 adoptan 00 en esa posición. Como el brillo anterior
33 se sustituye por el valor de orientación, ese byte no puede interpretarse
simplemente como brillo permanente de cada cuadro. Esto refuerza la hipótesis de
reutilización de buffers; aún no prueba si el firmware lo ignora.

Los JPEG muestran «Unavailable Sensor». Es contenido renderizado por iCUE y no
una medición ni respuesta de sensor enviada por el LCD. No usar ese texto para
concluir que el hardware tiene o carece de sensor de líquido.

Resultado: están identificados el transporte de JPEG y los selectores asociados
a brillo (0x0b) y rotación (0x0c), con una secuencia de arranque observada. Pendiente:
validación física desde un proceso Linux, relleno/campos ignorados, inicialización
mínima y mapa de orientaciones. No se enviaron comandos al dispositivo durante
este análisis.

## Quinta captura: ciclo de orientación (cinco pulsaciones)

Archivo: captures/20260908T204340_523963Z_rotation/lcd.pcapng.
Metadatos «giro 360»; el usuario informa que la imagen no cambió visualmente y
que pudo pulsar cinco veces. Archivo de 5,396 bytes, 45 registros, cero descartes,
truncamientos o errores de finalización reportados. Hay un último SET_REPORT
periódico sin finalización capturada. Los registros abarcan 63.141339 s pese a
la duración solicitada de 60 s; no confundir duración configurada con observada.

Se identifican exactamente CINCO órdenes de rotación. Las cinco tienen su
finalización USB correspondiente con estado 0:

| t relativo | Prefijo SET_REPORT | Valor de orientación |
| --- | --- | --- |
| 5.960 s | 03 0c 00 01 | 0 |
| 15.375 s | 03 0c 01 01 | 1 |
| 38.197 s | 03 0c 02 01 | 2 |
| 43.642 s | 03 0c 03 01 | 3 |
| 49.839 s | 03 0c 00 01 | 0 |

El botón de iCUE genera valores cíclicos 0,1,2,3,0. Esto respalda una selección
absoluta de cuatro posiciones en el protocolo, aunque el botón avance de manera
relativa y no muestre una posición por defecto. No establece cuál es la vertical
del gabinete ni asigna un sentido físico a cada valor sin referencia visual.
El montaje comunicado (tubos a la derecha en posición original; tres pulsaciones
para alinear la imagen al usuario) debe guardarse como calibración de instalación,
no como una regla universal para todas las placas/gabinetes.

A diferencia de las tomas previas, NO hay transferencias interrupt OUT 0x09 ni
cuadros JPEG. Solo aparecen descriptores y SET_REPORT: rotación y los periódicos
03 19 (cuyo byte 2 sigue la orientación más reciente). Por tanto, sabemos que las
órdenes llegaron a nivel USB, pero no demostramos que el LCD aplicara el giro a la
imagen visible. Una imagen estática o almacenada podría no requerir flujo continuo;
la ausencia de JPEG no demuestra por sí sola bloqueo de iCUE.

La captura usbmon es pasiva: no genera ni modifica comandos. Su ejecución consume
recursos y no permite excluir cualquier efecto indirecto, pero no se observan
pérdidas ni errores USB que apoyen atribuirle la falta de cambio visual. Posibles
estados de iCUE/pantalla o aplicación del giro al próximo cuadro permanecen sin
verificar; no presentarlos como diagnóstico confirmado.

Ya no hace falta repetir cinco giros para conocer la secuencia de valores. Antes
de probar el driver Linux, comprobar que iCUE puede volver a cambiar una imagen
física. Si hace falta investigar el giro pendiente, una toma corta con UN giro
seguido de UNA imagen distinta, anotando ambos instantes, permite observar si el
nuevo cuadro activa la orientación seleccionada.

## Sexta captura: imagen estática nueva, vertical conservada

Archivo: captures/20260908T205042_899955Z_image/lcd.pcapng.
Metadatos: «cambio img». El usuario confirma cambio de imagen físico y conservación
de su vertical. 120 registros USB; cero descartes, truncamientos, errores de
finalización o transferencias pendientes. Los registros abarcan 28.025400 s dentro
de la ventana solicitada de 30 s (intervalo entre primer y último paquete).

Se envía exactamente UN JPEG completo 480 × 480 de 50,399 bytes, dividido en
50 reportes interrupt OUT 0x09 de 1,024 bytes. El envío empieza a t=9.460073 s y
termina a t=9.492731 s; todas las transferencias tienen finalización satisfactoria.
SHA-256 del JPEG: 36be8e83f74d8d525e62e4a3a2b41a6d07ab4ea2b5953cbfee9fddd84c4fdb3a.
Ejemplo reconstruido: analysis/frame_0000.jpg.

No hay órdenes 0x0c de orientación ni 0x0b de brillo dentro de esta toma. Además
de descriptores y el JPEG, hay siete SET_REPORT periódicos 03 19 03 01…,
aproximadamente cada 4.5 s. El siguiente a la imagen ocurre a t=10.008 s, unos
0.515 s después del último fragmento. No se observó un comando especial de
sincronización inmediatamente después de cada fragmento/cuadro.

Esto demuestra que iCUE no transmite constantemente cuadros idénticos en todas
las circunstancias: en este cambio estático basta un cuadro observado, manteniendo
los reportes periódicos. No demuestra persistencia tras desconexión, cierre de
servicio ni ausencia de necesidad de esos reportes periódicos.

La vertical se conservó sin un nuevo ajuste de orientación dentro de la captura.
No se puede atribuir a un valor específico enviado en la toma anterior: hay un
intervalo no capturado entre ambas y el byte 2 del flujo vuelve a 03. No concluir
que la orientación sea siempre 0 ni que el firmware ignore el comando 0x0c.

No hace falta otra ronda genérica de capturas para construir el primer prototipo
Linux: existe evidencia de inicialización observada, transporte JPEG, brillo y
cuatro valores de orientación. El siguiente hito es probar una imagen estática
con exclusión mutua de VMware y el proceso Linux, limitando cualquier operación al
LCD 1b1c:0c57 y sin activar el backend PWM de la placa.

## Primera transmisión desde Linux (resultado visual pendiente)

Se añadieron algor/core/lcd_protocol.py y scripts/test_lcd_static.py. El primero
valida y fragmenta JPEG 480 × 480 en reportes de 1,024 bytes, con relleno cero.
El segundo genera un patrón «ALGOR / LINUX / PRUEBA USB» con flecha y solo envía
con --send. No importa ni utiliza el antiguo backend Corsair de la GUI.

Verificación offline: los 50 reportes reconstruidos a partir del JPEG de la sexta
captura coinciden con las cabeceras y datos válidos de iCUE byte por byte. El relleno
se limpia, no se reproducen residuos de memoria. Pruebas de reconstrucción,
validación de imagen y restauración de interfaz ante escritura parcial aprobadas.

Tras el usuario indicar Windows cerrado, se comprobó descriptor HID y endpoint
0x09. El proceso vmware-vmx seguía presente, pero no se observó un descriptor
abierto sobre el nodo USB mediante fuser; la interfaz estaba vinculada a usbhid.
El reclamo USB exclusivo por PyUSB se completó correctamente.

Ejecución: `python3 scripts/test_lcd_static.py --send`.
Resultado: captures/linux_static_tests/20260908T205810_717518Z/result.json.
Todas las escrituras del cuadro terminaron con la longitud esperada. Se liberó la
interfaz y se restauró usbhid. No se realizó reset ni set_configuration; tampoco
se enviaron comandos de inicialización, brillo, orientación, PWM o sensores.

Esta prueba usa el estado dejado por iCUE, NO demuestra inicialización en frío ni
persistencia. La respuesta USB satisfactoria no equivale a imagen visible. Falta
la observación del usuario antes de declarar el prototipo funcional físicamente.

## Resultado negativo de la primera prueba y segunda variante

El usuario confirma que el primer envío Linux NO cambió el LCD: conservó la
imagen anterior. El result.json de esa prueba registra ahora physical_display_confirmed=false.
No afirmar que la pantalla funciona por el mero éxito de las transferencias USB.

Se comprobó que el controlador HID asociado es hid-generic. La primera prueba
liberaba la interfaz inmediatamente tras el JPEG y omitía los reportes periódicos
03 19 03 01 que aparecen incluso en las capturas estáticas de iCUE. La falta de
estos reportes, el estado de sesión/inicialización y la interacción al restaurar
HID son hipótesis pendientes, no causas confirmadas.

Segunda variante limitada: un JPEG, seguido del reporte 03 19 03 01 cada 4.5 s,
con interfaz reclamada durante 20 s y posterior restauración de usbhid. Los bytes
4–31 del reporte reproducen el patrón observado: bytes 4–31 de nuestro último
fragmento JPEG. No se envían ajustes de brillo, orientación ni órdenes de arranque
adicionales. No se presume que 0x19 sea un watchdog: se prueba esa hipótesis.

Comando: python3 scripts/test_lcd_static.py --send --session-report --hold-seconds 20
El resultado visual debe confirmarlo el usuario. No se integra aún en la GUI.

## Confirmación visual Linux y séptima captura: salida de iCUE

El usuario confirmó que la segunda prueba Linux (con reporte periódico y retención
de interfaz de 20 s) mostró el patrón de borde menta y flecha. Después volvió la
imagen anterior. Se actualizó captures/linux_static_tests/20260908T210112_621793Z/result.json
con physical_display_confirmed=true. La prueba cambió dos factores respecto a la
primera (reporte periódico y tiempo antes de restaurar HID): no los aisla causalmente.

Nueva captura: captures/20260908T210709_560110Z_baseline/lcd.pcapng.
Usuario: cambio de imagen y salida de iCUE a los 10–13 s; la imagen persiste.
132 registros, cero descartes/truncamientos/errores de finalización, sin URB
pendientes. Los registros abarcan 57.128194 s de una ventana solicitada de 60 s.

- Un JPEG completo de 50,399 bytes/480 × 480 se transmite entre t=12.099739 y
  t=12.146288 s, en 50 fragmentos. Coincide exactamente con el logo multicolor de
  la sexta captura (SHA-256 36be8e83f74d8d525e62e4a3a2b41a6d07ab4ea2b5953cbfee9fddd84c4fdb3a).
- Se observan 13 SET_REPORT `03 19 03 01…`, desde t=3.122 hasta t=57.128 s.
  Diez de ellos ocurren después de t=13 s. El intervalo sigue siendo unos 4.5 s.
- No se observa una orden específica de salida, brillo o rotación en esta toma.

Conclusión: cerrar la interfaz de iCUE NO detuvo el tráfico periódico en esta
prueba. Su persistencia es compatible con un servicio/proceso Windows todavía
activo. usbmon no identifica qué proceso Windows originó las transferencias, por
lo que no se puede nombrar el servicio responsable solo con esta captura.

La imagen persistente no demuestra funcionamiento autónomo sin aplicación: aún
había comunicación. Tampoco prueba que el reporte sea suficiente por sí solo en
un arranque en frío. No es necesario seguir capturando el cierre de la ventana
para avanzar: la implementación Linux debe mantener una sesión independiente de
la visibilidad de la GUI y probar separadamente pérdida de reportes y liberación
HID. No añadir reportes de firmware, memoria persistente o PWM para resolverlo.

Siguiente prueba controlada propuesta: mantener interfaz USB y reporte periódico
al menos 60 s, luego suspender únicamente reportes conservando la interfaz un
intervalo adicional; registrar la observación física en ambas fases. Finalmente
liberar/restaurar HID. Requiere LCD devuelto al anfitrión Linux; no ejecutarla
mientras la VM mantenga el dispositivo.

## Octava captura: salida efectiva de iCUE y animación de respaldo

Archivo: captures/20260908T211250_256875Z_baseline/lcd.pcapng.
SHA-256: 8d716093ac81076498f4cf422354a8cc0ff56d17384c76bf619c50df1f173976.
Al analizarla no había metadata.json; la descripción proviene del usuario:
seleccionó dos imágenes estáticas y al salir de iCUE volvió la animación por
defecto. No atribuir tiempos exactos de sus clics fuera de lo registrado.

67 registros, 27,668 bytes, cero descartes/truncamientos/errores de finalización.
Se reconstruye UN JPEG de 19,802 bytes/480 × 480 en 20 reportes, desde t=4.644258
hasta 4.678063 s. No hay evidencia de dos transmisiones de imagen completas en
esta ventana: un cambio pudo ocurrir fuera de ella o no producir un nuevo envío.

Los reportes periódicos 03 19 continúan hasta t=31.561 s. Después se observa:

| t relativo | SET_REPORT de 32 bytes (prefijo) | Resultado USB |
| --- | --- | --- |
| 33.653 s | 03 1e 03 01… | Finalización estado 0 |
| 33.655 s | 03 1d 00 01… | Finalización estado 0 |

Mismo transporte HID observado: bmRequestType=0x21, bRequest=0x09,
wValue=0x0303, wIndex=0, wLength=32. No aparecen después reportes 03 19 ni JPEG.
El último registro es una consulta estándar de descriptor a t=116.712910 s cuya
respuesta queda fuera de la toma. Esto extiende el intervalo entre registros
más allá de 60 s; sin metadata no inferir la duración configurada ni su causa.

La secuencia es compatible con salida de la sesión de software. En el arranque
se había observado 03 1d 01 00…; al cerrar aparece 03 1d 00 01…: el byte 2 cambia
de 1 a 0. Es una hipótesis fuerte para un interruptor de sesión, todavía no un
comando individual validado. El byte 3 difiere y las colas tienen residuos:
no asignar significado a todos los bytes ni reproducirlos indiscriminadamente.
La función de 0x1e aún no se ha aislado. No presentarlo como guardar memoria,
apagar la pantalla, actualizar firmware o confirmar una imagen.

El usuario confirma el retorno a la animación por defecto. Esta toma demuestra
que a diferencia del cierre anterior aquí cesó la comunicación periódica y hubo
órdenes específicas. No distingue por sí sola si la animación volvió por 0x1e,
0x1d, falta de reportes o combinación de factores. No se enviaron estas órdenes
desde Linux durante la revisión.

### Diseño que resulta de las evidencias

- Mostrar/cerrar la ventana no debe determinar por sí solo la vida de la sesión
  LCD. Mantener el trabajador USB mientras la app siga activa en bandeja.
- Distinguir enviar cuadro, mantener sesión y salida a contenido de respaldo.
  La permanencia en pantalla observada con iCUE no prueba escritura en flash.
- Estados propuestos: desconectado, interfaz reclamada, sesión experimental activa,
  salida/restauración y error. Un solo propietario y cola de órdenes por LCD.
- Reporte periódico observado cada 4.5 s independiente del ritmo de imágenes.
  Usar reloj monotónico y tiempo límite, manejar ausencia de dispositivo sin bucle
  intensivo ni datos térmicos inventados.
- No integrar 0x1e/0x1d como salida definitiva hasta probar su efecto individual.
  No añadir operaciones de memoria no capturadas al cierre normal.
- La prueba Linux confirmada fue en estado previamente configurado por iCUE.
  Mantener esta limitación explícita hasta probar inicialización tras arranque.

Se corrigió capture_lcd_usb.py para guardar metadatos técnicos ANTES de esperar
la descripción física, evitando archivos sin metadata si el usuario cierra o
interrumpe el terminal en esa pregunta. Esta mejora se aplica a capturas futuras.

## Novena captura: Device Memory Mode ON (sin guardar)

Archivo: captures/20260908T211938_933068Z_baseline/lcd.pcapng.
Metadatos: «memory Modeon»; usuario confirma activación del selector.
43,221 registros durante 30.029097 s, cero descartes/truncamientos/errores USB.
Se reconstruyeron 325 JPEG completos de 480 × 480 (324 hashes distintos), con
un cuadro parcial y un envío pendiente al finalizar.

El flujo JPEG empieza a t=8.385595 s y continúa hasta el final. Solo se observan
lecturas estándar de descriptores, imágenes por interrupt OUT 0x09 y siete
SET_REPORT periódicos 03 19 03 01… a intervalos aproximados de 4.5 s. No aparecen
órdenes nuevas de control 0x1d/0x1e ni un prefijo de imagen diferente al observado
en visualización normal. No hay errores de secuencia del analizador.

Conclusión limitada: esta activación de la interfaz de memoria NO revela por sí
sola una orden específica de guardado ni demuestra escritura persistente. El
comportamiento es compatible con que iCUE siga renderizando la previsualización
mientras el usuario edita contenido para memoria. No se puede identificar la
escritura en flash ni asignarle un opcode a partir de esta toma.

Próxima captura propuesta: con modo ON, seleccionar una imagen estática distinta
y pulsar el icono Guardar, con tiempos anotados. Permitir que finalice cualquier
indicador de guardado antes de cerrar iCUE o desconectar la VM. La captura debe
iniciarse antes de seleccionar/guardar; si la operación supera el límite de
captura, dejar que iCUE termine de todos modos. Luego verificar persistencia al
salir de iCUE por separado. Sin guardar, mantener ON solo prueba la edición.

## Décima captura: Guardar en Device Memory Mode

Archivo: captures/20260908T214032_853209Z_image/lcd.pcapng.
Metadatos: «savemem». 263 registros; cero descartes, truncamientos o errores USB
de finalización reportados. Todos corresponden a bus 1/dirección 3. Hay una
transferencia IN empezada fuera de captura y dos envíos pendientes al finalizar.

A t=5.173–5.210 s se transmite una previsualización JPEG de 50,818 bytes por el
formato habitual 02 05. A t=11.546–11.586 s aparece una NUEVA transferencia por
interrupt OUT 0x09, con prefijo 02 06: un reporte inicial y 53 de datos. Todos los
reportes tienen 1,024 bytes y finalizaciones satisfactorias.

### Contenedor de memoria reconstruido (observación, no especificación completa)

- Los bytes 2–5 de cada reporte 02 06 contienen little endian 53,281, coincidente
  con la longitud total reconstruida. El reporte inicial tiene bytes 6–7=00 00;
  los de datos 01 00. Otros campos del reporte inicial no están interpretados.
- Los reportes de datos tienen cabecera de 16 bytes; byte 10 marca el último
  fragmento (1), bytes 12–13 indican longitud útil (máximo 1,008), y bytes 14–15
  contienen índice consecutivo 0–52. El fragmento final contiene 865 bytes.
- La carga reconstruida es una envoltura de 13 bytes y un JPEG de 53,268 bytes.
  Envoltura: 01 e0 01 e0 01 01 00 b3 03 14 d0 00 00.
- Offsets 1–2 y 3–4 de esa envoltura coinciden con dimensiones 480 × 480, y
  offsets 9–12 con la longitud JPEG de 53,268. El significado del resto requiere
  otras muestras; no asumir checksum, formato o flags por un único ejemplo.
- El JPEG decodifica completamente. SHA-256:
  352e7a99ad82bf9713c9a8c0a5c19cd344e46e92d80be6c7e6a1840ce8fac5c2.
- La imagen para memoria no coincide byte por byte con la previsualización de
  esta toma: iCUE puede recomprimir/preparar el contenido para el otro transporte.

### Control y respuestas durante el guardado

GET_REPORT 0x030f precede al envío. Luego GET_REPORT 0x030b responde
0b 00 00 be 03…; no atribuir significado numérico aún. Tras el envío hay cinco
GET_REPORT 0x030a: cuatro respuestas 0a 00… y una 0a 01… a t=11.6311 s.
Esta transición es compatible con estado pendiente/completado, pendiente de
validación con fallos/repeticiones. A t=11.6202 s se recibe un input report
512 bytes con prefijo 01 00 01 00 00 00 64…; podría indicar progreso, no confirmado.

Después aparecen SET_REPORT 03 1c 1c 06… (t=11.6316) y 03 1b 00 06… (t=11.6336).
Ambos completan con estado USB 0. No llamar a cada uno «commit», «guardar» o
«activar memoria» sin aislar su función. Las colas contienen restos del último
reporte de datos. Continúan los reportes periódicos 03 19 hasta el final.

Esta evidencia identifica una operación distinta del streaming, correlacionada
con Guardar en memoria. La escritura persistente no queda demostrada solamente
por respuestas USB: falta que el usuario cierre iCUE y observe la nueva imagen.
Persistencia tras cierre no equivale todavía a persistencia tras corte eléctrico.

### Herramientas y siguiente paso

scripts/analyze_lcd_memory.py reconstruye y valida esta estructura OFFLINE; no
escribe USB ni memoria. Artefactos en memory_analysis/memory_00.jpg y
memory_analysis/memory_analysis.json. El analizador general ahora cuenta los
reportes que no son 02 05 por separado, sin etiquetarlos como JPEG corruptos;
analysis_v2/ sustituye el diagnóstico preliminar de analysis/.

No se añadió guardado de memoria al driver Linux: faltan validación de campos,
respuestas de error y semántica de finalización. El siguiente paso de usuario es
salir de iCUE una vez concluido su guardado y confirmar cuál imagen queda visible,
con Windows y USB todavía conectados. No requiere cambiar brillo ni orientación.


## Confirmación física posterior del usuario y siguiente comparación

El usuario confirmó que la imagen guardada mediante iCUE permaneció tras salir
de iCUE. También confirmó posteriormente imagen estática, temperatura, giro,
brillo e iniciar/detener en Algor. Al salir de Algor se pierde el contenido
de sesión: la integración actual no escribe memoria. No se ha probado persistencia
tras retirar totalmente la alimentación.

La única carga de memoria disponible no permite separar campos constantes,
metadatos de imagen y posibles identificadores. Antes de construir un escritor
para imágenes arbitrarias, capturar otro guardado de una imagen estática distinta,
con brillo y orientación conservados. Comparar envoltura, cabeceras, respuestas
0x0a y órdenes finales 0x1c/0x1b. No repetir automáticamente una escritura de memoria
ante timeout: una respuesta perdida no demuestra que la escritura haya fallado.

El capturador admite ahora `--label memory --duration 60` con instrucciones
específicas. El control de memoria continúa sin exponerse en la GUI hasta resolver
esta comparación; no se ha enviado ninguna orden persistente desde Linux.


## Undécima captura: savemem1, repetición de guardado

Archivo: `captures/20260908T223402_240407Z_memory/lcd.pcapng`.
59.972558 s, 10,592 registros, cero descartes/truncamientos/errores de
finalización. Un IN iniciado fuera de captura y uno pendiente al terminar.
El flujo normal contiene 54 JPEG distintos; la transferencia de memoria contiene
UN JPEG de 53,268 bytes en 53 reportes de datos más el inicial.

El JPEG de memoria es idéntico al de savemem (SHA-256
352e7a99ad82bf9713c9a8c0a5c19cd344e46e92d80be6c7e6a1840ce8fac5c2).
La envoltura cambia únicamente en offset 7: b3 → b0. La cabecera inicial
permanece igual. Por tanto ese byte no puede ser una función determinista
exclusivamente del JPEG. Su función sigue sin determinarse.

Se repiten GET 0x0f, GET 0x0b, carga 02 06 y consultas GET 0x0a:
tres respuestas 0 y una 1, seguidas de SET 0x1c y 0x1b idénticos a la primera
captura. Carga entre t=8.193133 y 8.236164; respuesta 0a01 a 8.270080;
SET finales a 8.270599 y 8.272497.

El usuario confirma permanencia de la imagen tras cerrar iCUE y Windows.
No equivale a prueba tras retirar alimentación USB. Se conserva su observación
en `memory_analysis/comparison.json`, separada del análisis de paquetes.
Aunque el flujo de previsualización sí cambia, el JPEG efectivamente enviado
para memoria es el mismo. Falta otro guardado con imagen estática diferente
seleccionada dentro de Device Memory Mode; no habilitar escritura arbitraria
basándose en esta repetición.


## Duodécima captura: savemem2, imagen diferente

Archivo: `captures/20260908T223805_732234Z_memory/lcd.pcapng`.
271 registros, cero descartes, truncamientos y errores de finalización.
Un IN iniciado fuera de captura y dos pendientes al final. La duración entre
registros es 64.166901 s; el capturador se configuró para 60 s.

La carga de memoria contiene 58,036 bytes JPEG, 480 × 480, SHA-256
6c6965cd92a05e566f789379ef9b55902e89a06804b95fa45e808fb81cfebe5e.
Son 58 fragmentos de datos más un inicio; total contenedor 58,049 bytes.
Envoltura: `01e001e0010100c903b4e20000`. La imagen sí difiere de las dos anteriores.
La carga va de t=12.411437 a 12.461292. GET 0x0a devuelve tres ceros y un uno;
SET 0x1c/0x1b siguen a t=12.494879/12.497063, con finalización USB satisfactoria.
El usuario indicó «img fija diferente savemem2»; no atribuir a esta muestra una
confirmación nueva de persistencia tras cierre que todavía no comunicó.

### Relación entre consultas y orden final

Los bytes 2–5 de SET 0x1c son ahora `9e2bfc94`: coinciden con bytes 1–4 de
GET 0x0f en savemem1. En savemem y savemem1, SET 0x1c contenía `1c068d9b`,
que coincide con GET 0x0f de savemem2. La consulta inmediata de savemem2
responde precisamente `1c068d9b`, no el valor usado en su SET final.

La alternancia podría relacionarse con contenido/ranuras anteriores, pero es
una hipótesis. No está justificado sustituir esos cuatro bytes por la consulta
actual ni copiar el valor capturado. La envoltura conserva un campo variable
en offsets 7–8: b303, b003, c903; tampoco se conoce aún su función.

`scripts/compare_lcd_memory.py` reproduce las coincidencias offline y conserva
consultas/finalizadores completos en `memory_analysis/control_comparison.json`.
No se ha implementado ni ejecutado escritura de memoria desde Linux. Ya hay
una comparación con contenido diferente; nuevas capturas deben buscar una
hipótesis concreta sobre estos campos, no repetir indiscriminadamente guardados.


## Captura savememABC: identificación de CRC32

`captures/20260908T225405_780878Z_memory/lcd.pcapng`: tres cargas completas,
622 registros, cero descartes/truncamientos/errores USB de finalización. Dos
finalizaciones sin inicio en captura y dos envíos pendientes al terminar.

| Imagen por orden | Inicio (s) | Bytes JPEG | CRC32 en orden de transmisión |
| --- | ---: | ---: | --- |
| A | 10.098332 | 21007 | 3e e0 fd 35 |
| B | 36.097402 | 58036 | 9e 2b fc 94 |
| C | 50.614567 | 53268 | 1c 06 8d 9b |

En los tres casos, `struct.pack('<I', zlib.crc32(jpeg))` coincide exactamente
con bytes 2–5 de SET 03 1c. GET 0x0f devuelve en orden el CRC anterior C, A y B.
Esta evidencia corrige la hipótesis de tokens/ranuras: el campo identificado
es el CRC32 del JPEG, excluyendo la envoltura de 13 bytes. No debe copiarse de
GET 0x0f para guardar una imagen nueva.

GET 0x0a responde 1 directamente para A; para B y C se observan siete respuestas
0 antes de 1. No exigir observar un 0 para reconocer finalización. Los tres
SET 0x1c van seguidos de SET 0x1b con byte 2 cero y cola residual del informe
anterior. Sigue pendiente aislar la necesidad de cada orden.

El campo de dos bytes en offsets 7–8 de la envoltura contiene ce03, d403, b603
(974, 980 y 950 en little endian). Varía para el mismo JPEG entre capturas;
podría ser temporal, pero no está demostrado. No etiquetarlo como duración
ni fijarlo arbitrariamente al construir un escritor general.

El analizador de memoria ahora calcula CRC32 por carga, lo compara con la única
orden 0x1c entre esa carga y la siguiente y conserva el resultado. Validación
offline: tres coincidencias exactas en `memory_verified/memory_analysis.json`.
Esta captura no añade por sí sola una observación física tras cierre; el usuario
solo indicó que terminó. No se ha escrito memoria desde Linux.

## Confirmación y prueba limitada posterior a savememABC

El usuario confirmó que C permanece después de salir de iCUE. Se añade
`lcd_memory.py` y `scripts/test_lcd_memory.py` para probar una sola escritura
con las imágenes capturadas exactas. El hash SHA-256 valida el activo antes de
cualquier acceso USB; su envoltura original se conserva y el CRC se calcula.

No se habilita codificación de envolturas arbitrarias. La prueba compara el CRC
antes de escribir, evita reescribir si ya coincide, envía una vez, espera estado
1, emite 0x1c/0x1b y consulta el CRC posterior. El readback posterior es una
verificación añadida por Linux basada en la relación entre guardados capturada.
No hay reintentos automáticos de memoria. Hasta este punto solo se han ejecutado
validación offline y pruebas con transporte simulado; la prueba física Linux
queda pendiente. Instrucciones en PRUEBA_MEMORIA_LCD.md.


### Revisión de capturas adicionales ya existentes

Se analizaron `20260908T224330_684425Z_memory` y
`20260908T224827_113130Z_memory`, ambas sin descripción física en metadata.
Cada una contiene A/B/C completas, con CRC coincidente con la orden final.
Campos variables en offsets 7–8, valores little endian por orden A/B/C:
primera: 971/960/967; segunda: 975/959/946. Las seis cargas reiteran que este
campo varía incluso con el JPEG idéntico; no establecen su semántica. Se conservan
los resultados en `memory_analysis` de cada captura. No justifican ampliar el
escritor a JPEG arbitrarios ni atribuirles persistencia física no comunicada.


## savememGIF200800: dos cuadros en memoria

`captures/20260909T000910_859806Z_memory_gif/lcd.pcapng`: carga de 22740 bytes,
23 reportes de datos más inicio, entre t=25.430163 y 25.445501.
Envoltura: `01e001e0010200ee01dc2b0000e72c0000`.

Formato consistente con la captura y las estáticas: byte 0=1; uint16LE ancho,
alto y cantidad de cuadros en offsets 1, 3 y 5; campo variable uint16LE en 7;
desde 9, una longitud uint32LE por cuadro; después los JPEG concatenados.
Aquí la cabecera mide 17 bytes y los JPEG miden 11228 y 11495 bytes.
CRC32 de JPEG concatenados, excluyendo envoltura/tabla: `6c34f7e5` little endian,
coincide exactamente con SET 0x1c. El primer GET 0x0a ya devuelve 1.

El campo pendiente vale 494, cercano a la media 500 ms del GIF 200/800 ms.
Hipótesis: intervalo común de cuadros; no demuestra unidad, redondeo ni ritmo
físico. Falta confirmar alternancia tras salir de iCUE y si ambos cuadros duran
aproximadamente igual. No se ha escrito GIF desde Linux.

Analizador ampliado para tabla de longitudes y múltiples JPEG; regresión offline
comprobada con A/B/C y el GIF. Resultados en memory_analysis de esta captura.


## savememGIFABC: dos animaciones grandes y paginación

Archivo: `captures/20260909T001619_392097Z_memory_gif/lcd.pcapng`.
Metadatos: savememGIFABC; el usuario aclara que fueron dos GIF. 168775 registros,
cero descartes, truncamientos y errores de finalización USB. 102400948 bytes:
se alcanzó el límite configurado de tamaño antes de los 120 segundos solicitados.
Intervalo entre registros: 87.647101 s. Ambos guardados finalizaron antes del corte.

| Orden | Contenido visual del primer cuadro | Cuadros | Bytes contenedor | Páginas | Inicio/fin (s) | CRC JPEG concatenados (LE) |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 1 | Logotipo iCUE multicolor | 134 | 6871424 | 53 | 16.527680 / 21.433339 | ee0303c4 |
| 2 | Ondas de puntos | 480 | 36362437 | 278 | 32.828558 / 58.483413 | 8ee28c0a |

En ambos coincide exactamente el CRC calculado con SET 0x1c; el campo temporal
candidato vale 37 en ambos. No se reconstruye un tercer guardado del GIF de prueba
morado–verde. La observación actual del usuario se conserva separada de lo capturado;
no atribuir al último guardado observado persistencia física no confirmada.

Corrección del formato de paquetes para cargas grandes: bytes 6–7 son un número
de página uint16LE (0=inicio); el índice de fragmento en 14–15 vuelve a cero en
cada página. Byte 10 termina la página; byte 11 indica la página final. Una página
completa lleva 131072 bytes: 130 fragmentos de 1008 y uno de 32. En cargas pequeñas
solo se observaba página 1, por lo que el analizador anterior confundía esos campos
con constantes y fin de carga. NO interpretar byte 6 aislado como inicio (se hace
cero al alcanzar página 256). No ampliar límites del escritor USB por este análisis.

Se amplía únicamente el analizador OFFLINE a contenedores de hasta 64 MiB y 4096
cuadros, validando secuencia de páginas/fragmentos, tamaños y terminaciones. La
carpeta `memory_analysis/` corresponde al intento inicial rechazado por límite de
1 MiB; usar `memory_analysis_v2/`, con las dos cargas y todos sus JPEG completos.
Regresión offline comprobada sobre A/B/C y el GIF de dos cuadros (CRC coincidente).

Estos datos confirman estructura y paginación pero no explican todavía la
observación física de tiempos desiguales del GIF 200/800. No suponer que 37 ni 494
son milisegundos efectivos basándose solo en su magnitud. Los GIF originales de
estas dos animaciones no están en memory_probe_media; no comparar duraciones
originales que no se han leído.


## Corrección de progreso GET 0x0a tras Nautilus1_LCD.gif

Registro del usuario `20260909T020722_867900Z.json`: todos los 5485 informes fueron
enviados; al esperar, GET 0x0a devolvió `0a290000…`. El controlador solo admitía
0/1, una interpretación incompleta heredada de cargas de una página. Por ello
se detuvo sin enviar SET 0x1c/0x1b. No atribuir este fallo al tamaño del GIF.

Comparación con savememGIFABC: la carga de 53 páginas responde 51,51,51,51,52,52,53;
la de 278 responde 276,277,278 (valores que ocupan más de un byte). El campo desde
byte 1 cuenta páginas procesadas. `0x29=41` es progreso pendiente frente a las
42 páginas de Nautilus1_LCD.gif. Se lee little endian en bytes 1–4 y se espera
igualdad con el total de páginas; no basta probar el primer byte contra 1.

Se conservan los límites de espera, el rechazo a contadores superiores al total
y la ausencia de reintentos de escritura. La UI informa bloques procesados y el
registro conserva total y progreso. 48 pruebas pasan, incluyendo 41→42, la secuencia
capturada de 53 y 257→278 para evitar una finalización falsa por byte bajo igual a 1.
No se ha repetido la escritura física durante esta corrección.
