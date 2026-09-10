# Captura de memoria con tiempos conocidos

Objetivo: comprobar si los dos bytes variables observados en la envoltura estática
representan un tiempo, y cómo se codifican varios cuadros. No se da esa hipótesis
por confirmada. La captura anterior de streaming GIF no contiene escritura en
memoria y no resuelve este formato.

Generador local reproducible, sin USB:

```bash
python3 scripts/prepare_memory_probe.py
```

Produce `captures/memory_probe_media/probe_200_800.gif`: 480 × 480, dos cuadros
distintos de 200 y 800 ms, bucle infinito. Incluye PNG estático y JSON con los
tiempos. Pasa este GIF a Windows mediante tu carpeta compartida de VMware.

1. Sal de Algor, conecta el LCD a Windows, abre iCUE y activa Device Memory Mode.
2. Inicia en Linux:

```bash
python3 scripts/capture_lcd_usb.py --label memory_gif --duration 90
```

3. Cuando comience la captura, importa `probe_200_800.gif` en iCUE y pulsa Guardar
una sola vez. Mantén brillo y orientación. Espera a que termine el guardado y la
captura antes de salir de iCUE.
4. Describe la toma como `savememGIF200800` y observa si siguen alternando ambos
cuadros tras salir de iCUE.

No hay que cambiar conexiones de bomba ni ventiladores. La evidencia determinará
la siguiente implementación; el escritor Linux actual no acepta aún GIF en memoria.

Referencia externa consultada: el controlador Nautilus de OpenLinkHub expone Image/GIF
para sesión, pero no documenta aquí el campo pendiente de nuestra envoltura de memoria:
https://github.com/jurkovic-nikola/OpenLinkHub/blob/main/src/devices/nautilusLcd/nautilusLcd.go
La implementación local de reproducción utiliza Pillow y el transporte de sesión
ya capturado, sin incorporar órdenes USB nuevas ni código de ese proyecto.
