# Captura del Nautilus LCD desde VMware

Captura pasiva en el anfitrión Linux. No envía órdenes al LCD ni controla motores.
Requiere dumpcap (wireshark-common), tshark para el análisis, módulo usbmon y sudo.

1. En una terminal Linux: `sudo apt install wireshark-common tshark`.
   Si el paquete pregunta por capturas para usuarios sin privilegios, puede responderse No:
   el capturador usa sudo solo para modprobe/dumpcap; no necesita acceso permanente de grupo.
2. Salir de Algor desde la bandeja. Abrir Windows en VMware, conectar únicamente
   CORSAIR Nautilus LCD Cap 1b1c:0c57 a la VM y abrir iCUE. Dejar una imagen estática visible.
3. Desde la raíz del proyecto, ejecutar `python3 scripts/capture_lcd_usb.py --label baseline`.
   Seguir los avisos de la terminal. No modificar nada en esta captura inicial.
4. Repetir con `--label image`, luego `--label rotation`, luego `--label brightness`.
   Cada ejecución dura hasta 30 segundos o 100 MB. Hacer UNA acción al aparecer
   "Capturing on" y anotar si se refleja en el LCD físico. Puede ajustarse --duration (5–120 s).
5. Compartir la ruta de captures/ para analizarla. Los archivos son del usuario, dentro
   de carpetas privadas. No añadir capturas binarias al repositorio público.

El programa vuelve a detectar bus y dirección tras preparar la VM, usa el formato
USB_LINUX_MMAPPED y filtra link[11] (device_address) en el bus concreto antes de guardar.
No usar usbmon0 ni capturar todo el bus sin filtro. No cambiar conexiones durante cada
captura: las direcciones USB son temporales; si el LCD se reconecta, descartar esa toma.
La instantánea máxima es 1 MiB por paquete; revisar truncamientos y pérdidas antes de
concluir cómo funciona la transmisión de imágenes. Una captura vacía no prueba ausencia
 de comunicación: comprobar filtro, asignación a VMware y actividad del dispositivo.

No actualizar firmware durante estas pruebas. No desconectar cables USB internos en caliente.
El módulo usbmon queda cargado, pero no queda ninguna captura ejecutándose después del proceso.

Fuentes técnicas:
- https://wiki.wireshark.org/CaptureSetup/USB
- https://www.wireshark.org/docs/man-pages/dumpcap.html
- https://raw.githubusercontent.com/the-tcpdump-group/libpcap/master/pcap/usb.h

Estado de preparación: el script se comprobó con fixtures y sintaxis Python; la captura
real y la compilación del filtro quedan pendientes de instalar dumpcap y habilitar usbmon.
