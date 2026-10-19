# Portón vehicular con stickers UHF y lector de patentes

Guía para comprar, probar e instalar el acceso vehicular: sticker UHF en el parabrisas, lector UHF
en el portón y, opcionalmente, cámara de patentes como segunda credencial.

> **Estado del software:** la lógica (credenciales, modos de acceso, correlación sticker↔patente,
> antirrebote, anti-passback, bloqueo de stickers y el firmware del lector) está **probada con tests y
> con simulador**. **Nada de esto se ha probado todavía con hardware real.** Las pruebas de
> hardware son las de las secciones 4 y 5.

## 1. Lo que se compra

### Stickers UHF (parabrisas)

Exigir al proveedor, por escrito:

- **Protocolo EPC Gen2 (ISO 18000-6C)** y frecuencia **860–960 MHz**. Sin Gen2, el lector no los lee.
- **Un EPC único por sticker**, grabado de fábrica, y **lista de códigos entregada en CSV** (una fila por sticker). Sin esa lista no se pueden cargar al sistema ni detectar duplicados. Pedir que la lista venga con el número de lote.
- **Ningún EPC repetido dentro del lote**. Los lotes baratos a veces traen códigos duplicados; el importador los rechaza y los reporta por línea, pero es mejor que el proveedor los evite.
- **Prueba en parabrisas metalizado**: pedir una muestra de 3 stickers y probarlos en un auto con vidrio atérmico o metalizado antes de comprar el lote.
- **Alcance declarado**: el fabricante declara hasta ~10 m. Con lectores económicos se espera **3 a 6 m**. Lo que vale es el alcance **medido en su portón**, no el de la hoja de datos.
- Adhesivo para parabrisas (interior, para que no se despegue por lluvia o sol) y garantía de lectura durante un año en condiciones normales.

Cantidad: comprar primero **10 unidades de muestra** (sección 3). El lote grande solo después.

### Lector UHF de largo alcance (portón)

- **Alcance garantizado por el vendedor** por escrito, en las condiciones de tu portón (distancia, antena y potencia configurables).
- **Salida Wiegand 26 o 34, o RS485.** Pedir la hoja de datos con la **trama exacta** (bits, orden, terminador). El firmware soporta Wiegand 26/34 y RS485 con trama configurable; sin la trama no se puede configurar el RS485.
- Alimentación indicada (a menudo 12 V o 24 V) y consumo.
- **Antena adecuada** al ancho del acceso y montaje a la altura del parabrisas (la mayoría de los fabricantes lo especifica).
- Confirmar si puede **programarse en el campo** (potencia, modo de lectura, filtro de tags).

### Electrónica

| Ítem | Para qué | Observación |
|---|---|---|
| ESP32 (DevKit) | Controla el lector y el relé | Sin Wi-Fi: la red es Ethernet. |
| Módulo W5500 (Ethernet SPI) | Conexión a la red del edificio | Pines en `firmware/esp32/README.md`. |
| **Adaptador de nivel lógico** | Entre el lector Wiegand (5 V) y el ESP32 (3,3 V) | **Obligatorio** si el lector entrega 5 V. Divisor resistivo o conversor bidireccional. No conectar directo. |
| Fuente 5 V o 12 V | Alimenta el ESP32 y el adaptador | Según el lector, una fuente separada para el lector. |
| Relé con optoacoplador | Abre el portón | Contacto según el tablero del portón (NA). |
| Caja IP65 | Protege el equipo a la intemperie | Con prensaestopas para cables. |
| Protección contra sobretensión | Línea de alimentación y Ethernet | Recomendado en exterior. |

## 2. Modos de acceso

Se eligen en **Administración → Acceso** (o `PATCH /edificios/{id}/ajustes-acceso`).

| Modo | Abre con | Seguridad frente a clonación | Comodidad |
|---|---|---|---|
| **Sticker o patente** (por defecto) | Cualquiera de las dos | Baja: un sticker copiado abre sin el auto | Alta |
| **Sticker y patente** (recomendado si el riesgo importa) | Ambas, del mismo vehículo, dentro de la ventana | **Alta**: el sticker clonado en otro auto no abre | Menor: exige buena lectura de patente |
| Sólo sticker | El sticker | Baja | Alta; no depende de la cámara |
| Sólo patente | La patente | Media (depende de la cámara) | Depende de la cámara y la luz |

**Qué se pierde con "sticker y patente":** si la cámara no lee la patente (noche, lluvia, placa sucia,
moto con placa pequeña), el auto no abre aunque el sticker sea bueno. Un residente tiene que volver a
pasar. Si el lector de patentes falla con frecuencia, usar "sticker o patente" y aceptar el riesgo.

Parámetros del edificio:

- **Ventana de coincidencia** (por defecto 10 s): tiempo máximo entre el sticker y la patente.
- **Antirrebote** (por defecto 3 s): misma credencial repetida dentro de ese tiempo no vuelve a abrir.
- **Anti-passback** (opcional): impide entrar dos veces seguidas sin salir. Requiere que el lector
  informe la dirección (entrada/salida).
- **Confianza mínima de la patente** (por defecto 0,85): lecturas de cámara por debajo no abren.

## 3. Procedimiento de prueba de muestra (antes de comprar el lote)

1. Comprar **10 stickers de muestra** y el lector UHF con su antena.
2. Instalar el lector en el portón real, con la antena a la altura y la orientación definitivas.
3. Probar con **3 o 4 autos distintos**: un sedán claro, un SUV oscuro, un auto con vidrio atérmico
   o metalizado, y una camioneta alta si hay.
4. Para cada auto, pegar un sticker y medir con la herramienta de **Prueba de alcance** del panel
   (Administración → Prueba de alcance): caminar con el sticker desde el lector hacia afuera, y anotar
   la distancia donde deja de leer de forma estable ("leyó", "leyó a veces", "no leyó").
5. Repetir a distintas horas (día y noche) y con lluvia si es posible.
6. Anotar en la bitácora: alcance estable mínimo por auto, fallos y el modo elegido.
7. **Solo si el alcance estable cumple lo que necesitas** (por ejemplo, 3 m con el portón ya
   instalado), comprar el lote completo.
8. Cargar el lote con `scripts/importar_stickers.py` (plantilla en `docs/plantillas/stickers.csv`).

## 4. Lo que la prueba de muestra NO demuestra

- La clonación real: copiar un EPC requiere un lector y un grabador. Probar la clonación en
  laboratorio antes de confiar en el modo "sólo sticker" si el riesgo es alto.
- La durabilidad del adhesivo bajo sol y lluvia en varios meses.

## 5. Advertencia de seguridad

Los stickers UHF EPC **se pueden leer y copiar** con equipo económico. Un sticker no identifica a
una persona: identifica un código que alguien puede copiar. Por eso:

- Usar **"sticker y patente"** donde el riesgo importe (estacionamientos con autos valiosos, edificios
  con cobro por uso, o cuando un residente reporte un robo de sticker).
- **Reportar el sticker perdido de inmediato** desde la ficha del departamento: deja de abrir en la
  siguiente lectura. Es el único control que el sistema puede aplicar sin hardware nuevo.
- Revisar la bitácora del portón si aparecen lecturas de stickers desconocidos o de un sticker que
  abre en dos autos a la vez (el modo "sticker y patente" lo marca como posible clonación).
- Rotar la clave de dispositivo (`X-Device-Key`) si un lector sale del portón o se revisa físicamente.

## 6. Pruebas manuales antes de producción

Marcar cada una con fecha y responsable. No habilitar el portón a residentes hasta completar la lista.

**Lectura**
- [ ] Sticker de residente en el parabrisas: abre a la distancia de uso.
- [ ] Sticker desde el asiento del conductor, con el vidrio cerrado: abre.
- [ ] Sticker en parabrisas metalizado: abre (si no, el modo de muestra fue engañoso; revisar antena).
- [ ] Sticker de otro edificio: no abre (y queda en la bitácora como desconocido).

**Doble lectura y modos**
- [ ] Modo "sticker y patente": sticker y patente del mismo auto dentro de la ventana: abre.
- [ ] Modo "sticker y patente": sticker de un auto y patente de otro: no abre; la bitácora dice "pertenece a otro vehículo".
- [ ] Modo "sticker y patente": sólo el sticker, sin patente en la ventana: no abre; la bitácora dice "Esperando la patente".
- [ ] Lectura repetida del mismo sticker dentro del antirrebote: una sola apertura; la bitácora registra "Lectura duplicada".

**Sticker perdido**
- [ ] Marcar un sticker como perdido en el panel: en la siguiente pasada, no abre y la bitácora lo indica.
- [ ] Reactivarlo: vuelve a abrir.

**Corte de red**
- [ ] Desenchufar Ethernet del ESP32: el portón no abre y la consola lo informa.
- [ ] Reconectar: vuelve a leer sin reiniciar a mano.

**Corte de luz**
- [ ] Cortar la alimentación del portón con un auto dentro: al volver la luz el equipo arranca solo y no queda el relé activado.

**Patente sucia o de noche**
- [ ] Patente con barro o polvo: si no se lee, con "sticker y patente" el auto no abre (esperado); con "sticker o patente" abre por sticker.
- [ ] Noche con faros: la cámara lee con la confianza mínima; lecturas bajo el umbral no abren.

**Moto**
- [ ] Moto con sticker: abre (la moto no suele llevar parabrisas, revisar la ubicación del sticker).
- [ ] Moto sin sticker y con modo "sticker y patente": no abre; con "solo patente" depende de la cámara.

**Auto sin sticker**
- [ ] Auto de residente sin sticker y modo "sticker o patente": abre por patente.
- [ ] Mismo auto con modo "sólo sticker": no abre (esperado).

**Visita con QR**
- [ ] Código QR de visita vigente: abre en cualquier modo, respetando usos y horario.
- [ ] QR fuera de horario o ya usado: no abre.

**Respaldo**
- [ ] Copia de la lista de stickers y de la configuración del edificio guardada fuera del servidor.

## 7. Documentos relacionados

- `firmware/esp32/README.md`: cableado, advertencia de niveles lógicos, pruebas de banco del equipo.
- `backend/integraciones/lpr/README.md`: configuración del lector de patentes.
- `docs/PUESTA_EN_MARCHA.md`: instalación del sistema y carga de datos.
