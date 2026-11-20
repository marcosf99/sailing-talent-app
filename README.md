# Sailing Talent App

Aplicación para la gestión y seguimiento del talento en vela.

## Objetivo

Gestionar la trayectoria deportiva de regatistas, incluyendo:

- deportistas
- clubes y federaciones
- clases
- unidades competitivas
- competiciones
- resultados
- registros antropométricos

## Stack previsto

- Python
- Streamlit
- SQLAlchemy
- PostgreSQL
- Google Cloud SQL
- Google Cloud Run
- GitHub

## Estructura

- `app/`: interfaz Streamlit
- `database/`: acceso a datos y modelos
- `services/`: lógica de negocio
- `sql/`: scripts SQL
- `docs/`: documentación del proyecto
- `tests/`: pruebas

## Ampliacion del esquema: importacion de clasificaciones

El esquema contiene 16 tablas: las 11 originales y cinco tablas de revision:
`importacion_clasificacion`, `fila_clasificacion_importada`,
`participante_importado`, `coincidencia_propuesta` y `alias_club`.
Estas cinco tablas se crean vacias; no se modifican los scripts de datos de ejemplo.

### Base de datos nueva

Ejecutar `sql/create_tables.sql` una sola vez. Incluye todo el esquema y una
transaccion. Despues se pueden cargar los scripts de datos de ejemplo existentes.
No ejecutar tambien la migracion 001: ya esta incluida en el esquema completo.

### Bases de datos existentes (Supabase y Cloud SQL)

Ejecutar solo `sql/migrations/001_importacion_clasificaciones.sql`, una vez en cada
base. La migracion conserva los datos existentes y crea las cinco tablas nuevas.
Tambien anade una clave unica auxiliar en `competicion` para garantizar que la
competicion confirmada de una importacion pertenece a la clase seleccionada.
No ejecutar `create_tables.sql` sobre estas bases ya creadas.

En Supabase, copiar el contenido de la migracion en SQL Editor y ejecutarlo.
En Cloud Shell, subir el archivo y, conectado con psql a `sailing_talent`, ejecutar:

```sql
\set ON_ERROR_STOP on
\i ~/001_importacion_clasificaciones.sql
```

Para comprobar que existen las cinco tablas nuevas:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'importacion_clasificacion', 'fila_clasificacion_importada',
    'participante_importado', 'coincidencia_propuesta', 'alias_club'
  )
ORDER BY table_name;
```

La migracion no es repetible: si ya se ha aplicado, no volver a ejecutarla.
Los errores dejan sin aplicar todos los cambios de la transaccion. Si psql queda
en una transaccion fallida, ejecutar `ROLLBACK;` antes de reintentar.

### Convenciones para el futuro servicio de importacion

- Una importacion corresponde a una clase; el nivel puede completarse durante
  la revision, antes de confirmar resultados.
- `mapeo_columnas` y `datos_originales` son objetos JSON. `criterio_inclusion`
  conserva un objeto JSON con el criterio aplicado: autonómicas hasta el puesto
  40, nacionales hasta el 80 e internacionales sin corte de posición. En todos
  los niveles se exige ESP en el número de vela; sin ese dato la fila queda
  pendiente de revisión o excluida si indica otro país.
  Se mantienen los empates en el corte; no se renumeran las posiciones.
- La huella del documento es SHA-256 en hexadecimal minusculo. Varias
  importaciones pueden compartir documento si corresponde a varias clases.
- Los pendientes se guardan en `participante_importado`. Las coincidencias son
  propuestas y no crean ni confirman deportistas automaticamente.
- `indice_similitud` usa una escala de 0 a 1, como indicador heuristico.
- Solo puede haber una propuesta aceptada por participante. La confirmacion de
  identidad se almacena en `dni_deportista_confirmado` y `confirmado_en`.
- La fila confirmada referencia la clave conjunta de `participa_en`; ambos IDs
  deben ser NULL o tener valor. La competicion debe ser la de su importacion.
- `actualizado_en` se actualiza mediante un trigger al modificar la importacion.
- Las nuevas tablas tienen RLS habilitado, sin politicas de acceso mediante la
  Data API. La conexion SQL del backend como propietario conserva el acceso.
  Antes de usar otro usuario SQL, definir sus permisos y politicas expresamente.

La extraccion y la vista previa guardan borradores de revision. El siguiente
desarrollo sera resolver identidades, validar tripulaciones y sus fechas, y
guardar las entidades definitivas en una unica transaccion.
No hace falta cambiar todavia los archivos de conexion ni `database/queries.py`.

## Capa de importacion y revision (sin interfaz)

`database/importaciones.py` concentra el SQL parametrizado de las tablas nuevas.
Recibe una conexion y no abre transacciones ni carga credenciales.
`services/importaciones.py` recibe un motor explicito de SQLAlchemy, valida los
datos y controla las transacciones. Sirve para cualquiera de los dos proveedores.
`database/models.py` no es necesario: se mantiene el acceso mediante SQL directo.

Funciones principales del servicio:

- `calcular_huella(contenido)`: SHA-256 de los bytes originales.
- `evaluar_seleccion(nivel, posicion_general, numero_vela)`: criterio 40/80/ESP;
  devuelve `cumple_criterio=None` cuando falta el dato necesario.
- `preparar_filas(filas, nivel, numero_tripulantes)`: prepara la vista previa,
  detecta datos o tripulantes que faltan y conserva todas las filas, incluidas
  las excluidas, sus posiciones originales y los empates.
- `crear_borrador(engine, campos, filas=None)`: guarda la cabecera y opcionalmente
  todas las filas y sus participantes en una sola transaccion.
- `actualizar_borrador(engine, id, campos, actualizado_en)`: completa los metadatos
  antes de guardar filas; exige la version que vio el usuario y conserva la fuente.
- `guardar_filas(engine, id, filas)`: guarda filas en un borrador aun vacio;
  rechaza sobrescribir una revision existente.
- `obtener_borrador(engine, id)` y `listar_borradores(engine, limite=50,
  desplazamiento=0)`: recuperan el trabajo guardado y los listados paginados.
- `proponer_coincidencias(engine, participante, candidatos)`: conserva sugerencias
  recibidas, sin confirmar automaticamente. El buscador de nombres similares
  se implementara con la revision de identidades.
- `vincular_participante(engine, participante, dni, documento_anterior=None)`:
  confirma explicitamente una ficha existente. Para cambiar una identidad ya
  confirmada debe proporcionarse el documento que vio el usuario. No modifica
  el club ni otros atributos de la ficha definitiva.
- `registrar_alias_club(engine, texto_alias, id_club, contexto_fuente=None)`:
  normaliza abreviaturas y controla las ambiguedades por contexto.

Las entradas son diccionarios. Las fechas propuestas usan `datetime.date`,
las horas de actualizacion de la fuente usan `datetime.datetime` con zona horaria,
y los campos originales y el mapeo de columnas son objetos JSON. Las posiciones
ya normalizadas deben ser enteros positivos o `None`; los puntos admiten coma
u otra representacion decimal con hasta dos decimales, sin redondear.

Ejemplo de fila normalizada que producira la futura extraccion/vista previa:

```python
fila = {
    "numero_fila": 1,
    "datos_originales": {"Pos": "40", "Vela": "ESP 123", "Total": "25,5"},
    "posicion_general": 40,
    "numero_vela_original": "ESP 123",
    "puntos": "25,5",
    "participantes": [{"nombre_original": "Nombre tal como figura en el PDF"}],
}
```

`numero_fila` identifica el orden de la fuente, no la posicion deportiva.
Cada participante es un miembro de esa embarcacion. No se divide un nombre
ni se deducen DNI, fecha de nacimiento o sexo a partir de categorias.
En internacionales el codigo ESP de una columna de pais separada no sustituye
la comprobacion del numero de vela. Se selecciona toda la tripulacion ESP.

Las escrituras bloquean la importacion mientras guardan. Un error revierte la
operacion completa. Por ahora no se crean deportistas, unidades competitivas ni
resultados definitivos. Esta capa de validacion no lee un PDF ni descarga enlaces;
la extraccion y el almacenamiento se realizan en los adaptadores descritos abajo. La referencia y la huella identifican la copia que proporcionara
la siguiente capa de extraccion/almacenamiento.

Pruebas locales, sin credenciales y sin escribir en Supabase ni Cloud SQL:

```bash
python -m unittest discover -s tests -p 'test_importaciones.py' -v
python -m unittest discover -s tests -v
```

Las pruebas del servicio utilizan el DDL real adaptado a SQLite para tipos,
funciones y bloqueos. No prueban la concurrencia de PostgreSQL ni sus politicas RLS.

## Carga y vista previa de PDF

La pagina **Importar clasificaciones** permite:

1. Subir y analizar un PDF con texto seleccionable (hasta 20 MB y 50 paginas).
2. Consultar cada pagina original y la tabla de texto extraida.
3. Elegir la columna de posicion general, puntos, vela y opcionalmente nombres
   y categoria. Los encabezados repetidos se distinguen con su numero de columna.
   NET se propone antes que TOTAL; el usuario confirma la columna adecuada.
4. Seleccionar manualmente nivel y clase del catálogo. El texto de clase detectado
   en el PDF es una referencia informativa y no bloquea el guardado: prevalece la
   elección manual, que debe confirmarse junto con la revisión de las columnas.
5. Revisar las celdas y escribir cada tripulante por separado. Para individuales
   puede elegirse explicitamente primera linea como nombre y siguientes como club.
   En clases dobles puede elegirse **Dobles · Escora** o **Dobles · Sailti** para
   proponer los dos miembros y sus clubes. La distribución ambigua se revisa
   manualmente. No se deducen DNI ni fechas de nacimiento a partir de categorias.
6. Comprobar seleccionados, excluidos e incidencias. Se conservan todas las filas,
   sus celdas originales y las posiciones con empates. Los datos incompletos se
   guardan pendientes de correccion, sin crear resultados definitivos.
7. Confirmar la revision y pulsar **Guardar borrador para revisar**. El guardado
   se hace solo en el proveedor elegido. El listado **Ver borradores guardados**
   permite comprobar el guardado antes de reintentar si se pierde la conexion.

Para iniciar desde la raiz del proyecto con el entorno virtual activo:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app/main.py
```

`services/extraccion_clasificaciones.py` detecta tablas con puestos en su primera
columna y una columna de vela. Reutiliza los encabezados en paginas continuadas,
conserva los encabezados repetidos y no aplica OCR. No es un conversor universal:
los PDF escaneados requieren OCR previo y los cambios de estructura dentro del
mismo documento deben separarse en archivos antes de subirlos. Los nombres con
texto superpuesto o mal codificado requieren comparacion y transcripcion manual.
Para una regata publicada mediante enlace, descargar su PDF y subirlo; todavia
no se descargan documentos automaticamente desde una URL.

### Tripulaciones de 420 y 470: Escora y Sailti

Con una clase de dos tripulantes seleccionada, **Tratamiento de los nombres**
ofrece dos modos adicionales:

- **Dobles · Escora**: lee los dos nombres y sus clubes al final de la celda.
  Une las continuaciones del segundo nombre y las señala para revisión. Si solo
  aparece un club, conserva ambos nombres pero deja los dos clubes pendientes:
  no presupone que pertenezcan al mismo club ni a cuál corresponde el dato.
- **Dobles · Sailti**: separa los bloques `APELLIDOS, nombre / club`, manteniendo
  la separación de nombre y apellidos. Ignora el patrocinador tras un segundo
  `/`. Usa el orden de los caracteres del flujo PDF para no mezclar líneas
  superpuestas de un nombre y la continuación del club anterior. Si no hay dos
  bloques reconocibles, conserva el texto original y exige revisión manual.

Los roles comienzan sin confirmar. Se pueden elegir en las columnas **Rol 1**
y **Rol 2**, o confirmar expresamente que el primer nombre es patrón y el segundo
tripulante en todo el documento. Esa confirmación precarga los roles, que siguen
siendo editables. Cambiarla exige revisar otra vez antes de guardar el borrador.
Los roles no se deducen del sexo, categoría mixta ni orden por defecto.

En Sailti se sigue proponiendo **NET**, manteniendo **TOTAL** como elección
manual alternativa. Para nivel internacional se seleccionan los equipos cuyo
número de vela contiene ESP, incluyendo a ambos miembros y conservando el
puesto general del PDF. La revisión posterior conserva el flujo por lotes:
si un equipo mezcla una ficha existente y una alta nueva, primero se vincula la
existente sin incorporar aún el resultado y después se completa el equipo con
la nueva ficha. Solo se incorpora cuando estén confirmados ambos miembros y roles.

`services/documentos_importacion.py` conserva las fuentes locales en
`.local/importaciones/<sha256>.pdf`, excluidas de Git, con permisos privados y
escritura mediante archivo temporal. Las referencias se guardan en la base.
Una fuente compartida por varias importaciones no se elimina si falla una de
ellas; la copia puede reutilizarse al reintentar. Solo se sustituyen archivos
completos, y se verifica la huella de las copias que ya existen.

Este almacenamiento es para desarrollo local: el despliegue necesita un adaptador
con almacenamiento persistente de objetos. Hasta entonces debe conservarse la
carpeta local en el equipo desde el que se guardan los borradores.

Las pruebas generan PDF ficticios en memoria y simulan las escrituras de la
interfaz; no incluyen clasificaciones reales ni sus datos personales en Git.

## Revision de participantes

La pagina **Revision de participantes** abre los borradores existentes. Trabaja
solo con filas que cumplen el criterio de seleccion; las excluidas se conservan
sin dar de alta sus participantes desde esta pantalla.

- Muestra la fila original, el nombre y club de la fuente, el puesto y la vela.
- Propone fichas por nombre completo o parcial, incluyendo acentos, orden de los
  apellidos y coincidencias de club/federacion. Tambien admite buscar otro nombre
  o documento. La similitud es heuristica: no representa una probabilidad.
- **Vincular ficha existente** requiere seleccionar una ficha y confirmar la
  identidad. El club identificado en la fuente no cambia el club actual de la ficha.
- **Crear deportista** exige nombre y apellidos. Sin DNI se genera un identificador
  provisional `TEMP-` aleatorio, que no representa un documento real. Nacimiento y sexo son
  opcionales. El usuario confirma expresamente que debe crearse otra ficha;
  el servicio vuelve a comprobar documentos y posibles coincidencias al guardar.
  **Crear deportista y guardar resultado** incorpora tambien la regata, su unidad
  y el resultado en esa misma accion. Los datos de la regata se precargan desde
  el borrador y se revisan una sola vez en el bloque **Datos de la regata**.
- **Dejar pendiente** conserva los datos parciales para completarlos mas tarde,
  sin crear la ficha definitiva ni inventar documentos o fechas.
- Permite incorporar miembros que falten en una embarcacion. En dobles debe haber
  un patron y un tripulante, y no puede repetirse un deportista en la misma fila.

`services/revision_participantes.py` controla las operaciones y utiliza el SQL
parametrizado de `database/importaciones.py`. La pantalla recibe un motor de
lectura; solo al pulsar un boton de guardado se crea el motor de escritura del
proveedor elegido. No se añaden tablas ni dependencias.

El alta de la ficha, el vinculo con el participante y las propuestas de coincidencia
se guardan en una transaccion. Un fallo revierte todo el conjunto. Se bloquea el
borrador y se comprueba una version de los campos del participante para evitar
sobrescribir otra revision abierta. Los campos originales permanecen intactos.

El buscador compara los datos minimos de las fichas existentes en Python, sin
necesitar extensiones ni funciones de semejanza en PostgreSQL. Los alias globales
confirmados apoyan el contexto del club; los alias con contexto no se aplican
como si fueran universales. Las sugerencias se guardan al confirmar una decision;
abrir la pantalla o buscar candidatos no modifica las bases de datos.

Una fila pasa a `lista` cuando tiene los miembros e identidades requeridos,
posicion y puntos, y los roles correctos en dobles. Las altas nuevas incorporan
automaticamente el resultado al completar esas condiciones. Si el equipo doble
esta incompleto, se guarda la ficha y el resultado queda pendiente hasta confirmar
al segundo miembro. Esto tambien se aplica a equipos mixtos con un miembro nuevo
y otro ya existente. Los equipos formados solo por fichas existentes mantienen el
paso **Incorporar resultados revisados**, en esta misma pantalla.
El caracter provisional/definitivo de la fuente no cambia al revisar identidades.

El alta conjunta usa una unica conexion y transaccion para ficha, propuestas,
identidad, competicion, unidad y resultado. Un conflicto de puesto, equipo o
resultado revierte tambien la ficha creada en esa accion; no deja un alta parcial.
Si faltan miembros o roles, se indica expresamente que el equipo queda pendiente.
No se incorporan automaticamente resultados de otras filas del borrador.

### Incorporar resultados revisados

1. Elegir los resultados preparados, incluidos los de deportistas creados antes
   de disponer de este paso. No se vuelven a dar de alta las fichas.
2. Revisar nombre, fechas y localidad de la regata, y confirmar si la fuente es
   provisional o definitiva. La clase y el nivel proceden del borrador.
3. Confirmar participantes, puestos y puntos y pulsar **Incorporar resultados
   seleccionados**. Los resultados aparecen entonces en la consulta de deportistas.

`services/resultados_importados.py` guarda en una transaccion la competicion,
las unidades, sus miembros, los resultados y sus referencias en el borrador.
Reutiliza una competicion del mismo nombre (ignorando mayusculas), clase y fechas
si sus demas metadatos coinciden. No sobrescribe competiciones ni resultados
incompatibles. Se bloquean importacion, clase, competicion, deportistas y unidades
reutilizadas, y se comprueba la version de la revision mostrada al usuario.

Se reutiliza una unidad de los mismos miembros y roles que cubra toda la regata.
Si la unidad comienza despues, se puede adelantar su inicio conservando su cierre
manual y sus resultados. Si no existe un equipo compatible, se crea otra unidad
con inicio en la regata y `fecha_fin = NULL`.
Un regatista puede tener varias unidades abiertas de la misma clase con distintas
parejas o roles. No se cierran por cambiar de pareja ni por importar otra regata.
Las etapas cerradas se conservan y no se fusionan automaticamente. Si hay varias
unidades del mismo equipo que cubren la regata, se solicita revision de duplicados.
La antigua opcion de cierre de etapas historicas en la carga ya no es necesaria;
los cierres se gestionan desde **Unidades competitivas**.
En clases individuales el rol es Patron. En dobles hacen falta ambos miembros
confirmados, con un Patron y un Tripulante.

### Cierre manual y limite de Optimist

Las unidades se cierran manualmente desde **Unidades competitivas**, conservando
miembros y resultados. La unica excepcion por edad es Optimist, con el criterio
confirmado para esta aplicacion: ultima temporada el año en que cumple **14**;
desde el 1 de enero del año en que cumple 15 ya no se admite competir en Optimist.
El limite se calcula por año de nacimiento, no por el dia del cumpleaños.

Mientras no haya vencido el limite, `fecha_fin` permanece NULL. No se programan
fechas futuras. Al abrir la aplicacion o en la primera interaccion de un nuevo dia
se comprueban las unidades abiertas del proveedor seleccionado. Solo si hay
Optimist con limite ya pasado se abre una transaccion de escritura para cerrarlas
con fecha efectiva 31 de diciembre del año en que cumplieron 14. **Actualizar
datos** permite repetir la comprobacion ese mismo dia. No hay un proceso en
segundo plano: si la aplicacion esta cerrada, se aplica el cierre al volver a abrirla.

Sin fecha de nacimiento no se infiere el limite y la unidad sigue abierta para
revision manual. Los cierres manuales anteriores no se sustituyen. Si existen
resultados o un inicio posteriores al limite, se avisa y se conserva la historia
para revision, sin truncarla automaticamente. El servicio de incorporacion
rechaza nuevos resultados incompatibles con la edad conocida. Al incorporar una
unidad historica cuyo limite ya paso, se guarda directamente ese cierre pasado.
En las demas clases la edad no provoca cierre ni una fecha final automatica.

Las unidades ya cerradas por versiones anteriores no se reabren automaticamente:
el esquema no distingue ese cierre de uno decidido manualmente.

Se rechazan puestos generales duplicados, participantes en varias embarcaciones
y resultados contradictorios. Repetir una incorporacion ya completada no duplica
regatas ni resultados. Un resultado previo identico puede vincularse desde otra
importacion sin repetirlo. Los empates de la fuente se conservan en el borrador,
pero requieren revision antes de incorporar puestos generales repetidos.

El borrador queda `parcialmente_importada` si faltan filas por resolver y permite
seguir revisando sus identidades pendientes. Cuando se incorporan todas las filas
seleccionadas queda `completada`. Las filas ya importadas no admiten cambios de
identidad desde esta pantalla. Un fallo revierte todo el lote de resultados,
conservando las fichas y revisiones de identidad guardadas anteriormente.
No se requieren migraciones ni nuevas dependencias.

Pruebas de esta funcionalidad:

```bash
python -m unittest discover -s tests -p 'test_revision_participantes*.py' -v
```

Se utilizan fixtures ficticios, el esquema adaptado a SQLite y la interfaz de
pruebas de Streamlit. El bloqueo concurrente real de PostgreSQL debe validarse
tambien en integracion; las pruebas locales simulan una revision obsoleta.

## Consulta y comparacion de informes tecnicos

La ficha de **Consulta de regatistas** incorpora una pestaña **Informes tecnicos**.
Muestra el historial hasta la fecha de consulta, con el mas reciente primero, y
permite seleccionar un informe para consultar sus cuatro valoraciones (estrategia,
tactica, trimado y tecnica), fortalezas, debilidades y recomendaciones, junto con
fecha, tecnico y titulacion registrada. Se conservan todos los informes del mismo
dia; el identificador distingue informes de un mismo tecnico y fecha. El orden
inicial para fechas iguales es identificador descendente, sin inferir una hora
de evaluacion que el modelo no registra.

En **Candidatos y comparacion**, al seleccionar hasta tres deportistas, aparece la
comparacion tecnica ademas de la fisica. Por defecto se usa el ultimo informe
disponible de cada candidato hasta la fecha de consulta; el usuario puede elegir
otro informe por candidato. Una tabla muestra fechas, autores y valores. El grafico
de barras agrupadas compara las cuatro dimensiones en la misma escala de 1 a 5,
con fechas y autores en la informacion de cada barra. Se necesitan valoraciones
en al menos dos perfiles para mostrar el grafico.

Los valores sin registrar se muestran vacios en las tablas y no generan barras:
no se sustituyen por cero, ni se promedian informes de diferentes fechas o autores.
Los candidatos sin informes permanecen en la tabla. La comparacion tecnica
funciona aunque no haya mediciones antropometricas. Las valoraciones pertenecen
a sus tecnicos; no se calcula una puntuacion global de talento.

`services/informes.py` filtra las fechas en SQL y obtiene los historiales de los
candidatos con una sola consulta parametrizada. La interfaz reutiliza el motor de
lectura y la cache privada de la sesion, separada por proveedor, fecha y candidatos.
Consultar o cambiar el informe seleccionado no guarda ni modifica informes.
La creacion de informes sigue en su pantalla actual y vacia la cache al guardar.
No hay cambios de esquema ni migraciones. Altair se declara como dependencia
explicita para el grafico; ya formaba parte de las dependencias de Streamlit.

### Evolucion antropometrica comparada

En candidatos, el grafico fisico utiliza lineas temporales con puntos y un color
por regatista, conservado al cambiar de indicador. Permite seleccionar altura,
peso, envergadura o porcentaje graso, cada uno con sus propias unidades. Las
tablas de perfiles siguen mostrando la ultima medicion; el grafico utiliza todo
el historial disponible hasta la fecha de consulta, aunque la ultima medicion
del perfil no contenga ese indicador.

Con una sola fecha se representa un punto. Los perfiles sin valores para el
indicador se identifican en un aviso y permanecen en la tabla. Los valores
ausentes no se convierten en cero ni se trasladan a otras fechas. Cuando hay
varias mediciones de un indicador en un mismo dia, se muestra la conocida de
mayor identificador, sin promediar; otra medicion parcial de ese dia no borra
un valor anterior registrado para el indicador.

Los historiales de hasta tres candidatos se obtienen con una sola consulta
parametrizada, con fechas filtradas en SQL y cache privada por proveedor, fecha
y seleccion. Este cambio no modifica las mediciones ni requiere migraciones.
La comparacion tecnica mantiene sus barras de valoraciones de 1 a 5.

Al pasar el cursor por un punto antropometrico se muestran regatista, fecha,
valor y edad en años y meses completos en el momento de esa medicion. Se calcula
desde la fecha de nacimiento registrada, independientemente de la edad actual
o de la fecha de consulta. Sin nacimiento, o si la medicion es anterior a este,
se muestra **Edad no disponible** y se conserva el punto sin inventar una edad.

### Ampliación de clubes de Galicia

`sql/sample_clubes_galicia.sql` añade once clubes identificados en las
clasificaciones aportadas de Optimist e ILCA 4. Se ejecuta después de
`sql/sample_data.sql`, tanto en Supabase como en Cloud SQL, y se puede repetir
sin duplicar esos clubes. Con la carga base quedan 26 clubes, 15 gallegos.
No requiere migraciones ni modifica los clubes existentes.

En psql, desde la raíz del repositorio:

```sql
\i sql/sample_clubes_galicia.sql
```

En Supabase también puede pegarse el contenido del archivo en SQL Editor.
Las abreviaturas observadas y las fuentes de contraste están en
[docs/fuentes_clubes_galicia.md](docs/fuentes_clubes_galicia.md).

`sql/update_localidades_clubes.sql` completa localidad y provincia de los
quince clubes iniciales. Ejecutarlo después de `sql/sample_data.sql` en ambos
proveedores, o pegarlo en SQL Editor de Supabase. Solo rellena campos vacíos y
se puede repetir. Localidad se registra como municipio; los núcleos concretos
y las fuentes están en
[docs/fuentes_localidades_clubes.md](docs/fuentes_localidades_clubes.md).

### Clases sobre la evolución antropométrica

Se conserva **Consulta de regatistas → Trayectoria y equipos**, con su tabla y
su línea temporal de unidades y regatas. La pantalla independiente de
transiciones se retira de la navegación y el análisis se concentra en las
curvas antropométricas existentes.

En la ficha individual, las primeras incorporaciones a clases adicionales
aparecen como líneas verticales discontinuas, con la clase identificada. El
cursor muestra la fecha de inicio registrada y la edad. Se usa el primer
inicio de unidad por clase: otra unidad de la misma clase no genera una marca.
Las clases iniciales no se interpretan como cambios. Se conservan las
incorporaciones simultáneas sin inventar una dirección entre clases y se
excluyen inicios futuros o anteriores al nacimiento conocido.

En **Candidatos y comparación**, cada marca utiliza el mismo color que las
mediciones de su regatista. La opción **Eje temporal** permite comparar por
**Edad al medir** o por **Fechas del calendario**. La edad es el valor inicial
si se comparan al menos dos personas y conocemos todos sus nacimientos. El
cursor conserva tanto la edad como la fecha real de cada medición y marca.

La edad se calcula en meses completos y el eje se etiqueta en años y meses. Sin
nacimiento válido no se inventa la edad: en ese eje se omiten esas mediciones
con un aviso; el perfil permanece en la tabla y puede verse por calendario.
Comparar por edad no supone que los regatistas compartan clase o experiencia.

Las líneas físicas unen medidas registradas; no se crean medidas en las fechas
de cambio ni se rellenan ausencias con cero. En una misma fecha e indicador
se conserva el último valor conocido. Una única medición se representa como
un punto. Las marcas pueden extender el eje para incluir incorporaciones
anteriores o posteriores a las medidas, siempre hasta la fecha de consulta.
Una incorporación no presupone abandonar otra clase ni cierra unidades.

La comparación obtiene los primeros inicios de hasta tres deportistas en una
sola consulta parametrizada, además de la lectura de mediciones existente.
La caché es privada de sesión, por proveedor, fecha y selección. Si falla la
lectura de las clases, se conservan las curvas y se informa de que no se han
podido mostrar sus marcas. No requiere migraciones ni escribe en las bases.

### Revisión conjunta de clubes y participantes

En **Revisión de participantes**, tras los datos de la regata, se añaden dos
tablas. Los formularios individuales y la incorporación de resultados se
conservan.

1. **Resolver clubes del documento** agrupa textos equivalentes tras normalizar
   acentos y puntuación. Propone el club a partir de decisiones del borrador,
   alias globales confirmados, nombre o similitud de texto. El usuario debe
   seleccionar expresamente las filas y confirmar antes de aplicar el club a
   sus participantes pendientes. Un texto ausente se revisa individualmente.
   Una equivalencia ya confirmada desaparece de las tareas pendientes, aunque
   las identidades de esos participantes todavía estén por resolver.
2. **Recordar equivalencia** es opcional y comienza desmarcado. Guarda un alias
   global en `alias_club` para futuras propuestas. Repetirlo para el mismo club
   no duplica registros; una equivalencia existente para otro club produce un
   conflicto y no se reemplaza. Se puede aplicar una decisión exclusivamente a
   este documento sin guardar el alias. Los alias con contexto específico no
   se aplican como globales.
3. **Vincular participantes en una tabla** muestra nombre y club de la fuente,
   club identificado, ficha propuesta, club actual, nacimiento, motivos y rol.
   **Seleccionar todas las coincidencias propuestas** permite marcar el lote y
   desmarcar excepciones antes de la confirmación explícita. Los homónimos, las
   fichas propuestas para varias posiciones y las coincidencias insuficientes se dejan para el
   formulario individual, que sigue permitiendo buscar otra ficha y crear una
   nueva con los datos requeridos.
   Solo se muestran filas que tengan una ficha existente propuesta; las altas
   sin coincidencias se muestran únicamente en su sección de creación.

La propuesta conjunta utiliza hasta cinco coincidencias por persona. Ofrece
una ficha si coincide un documento propuesto de forma única, o si la similitud
orientativa es al menos 0,75 y supera a la segunda en al menos 0,05. Estos
umbrales ordenan la revisión; no son probabilidades ni confirman identidades.
Las fichas y los alias se leen una vez por resumen, sin consultar de nuevo el
catálogo completo para cada participante. El resumen se guarda en la caché
privada de sesión con proveedor, borrador y versión.

Cada lote se guarda en una transacción que bloquea su importación. Se comprueba
la versión de los datos revisados y de las fichas propuestas, el nacimiento
respecto a la regata, la exclusión de filas y las identidades repetidas. En
dobles se revisan los roles y una tripulación completa necesita un patrón y
un tripulante. Un fallo revierte todo el lote. No se cambia el texto original,
el club actual de una ficha existente ni las filas importadas/excluidas.

**Crear fichas sin DNI e incorporar resultados** permite seleccionar varias altas
que no tengan fichas similares y cuyo club ya se haya confirmado. Se revisan
nombre y apellidos en una tabla; el nacimiento desconocido permanece NULL. Cada
alta recibe un identificador aleatorio `TEMP-` y su resultado en la misma
transacción. Cualquier coincidencia nueva, equipo incompleto o conflicto revierte
todo el lote, incluso las altas ya preparadas. No se crean fichas automáticamente.

En **Gestión de deportistas → Editar ficha**, el identificador provisional puede
sustituirse por el DNI conocido. Las claves foráneas del modelo usan `ON UPDATE
CASCADE`, conservando mediciones, informes, equipos y las revisiones de origen.
Se rechaza un DNI que ya pertenezca a otra ficha y una edición obsoleta, sin
fusionar identidades. No se requieren migraciones del esquema actual. Las altas
individuales también admiten el DNI vacío para asignar un identificador provisional.

Con **Vincular e incorporar los resultados en este paso**, las fichas existentes
y sus resultados se asocian en una sola transacción, tras revisar también los
datos de la regata, puestos y puntos. Si algún equipo está incompleto o hay un
conflicto, se revierte todo el lote. Desmarcar esa opción permite preparar los
resultados para el botón existente. Tanto las altas como las vinculaciones
individuales incorporan el resultado al completar la tripulación y sus roles,
en la misma transacción. Si falta otro miembro, se conserva la identidad confirmada
y se informa de que el equipo sigue pendiente. No hay migración de esquema ni cargas iniciales
de alias: solo se registran equivalencias confirmadas por el usuario.

Se reconocen como propuestas las abreviaturas M.R.C.Y.B., CM Canido y C.V.F.
As Pontes frente a sus nombres completos del catálogo, ignorando puntuación y
partículas como «de». Si varios clubes coinciden, se exige revisión individual.

Al incorporar regatas en orden inverso, puede adelantarse el inicio de una
unidad existente de la misma clase con los mismos miembros y roles. Se elige
la etapa posterior más cercana, se conserva su cierre y sus resultados, y se
rechaza la ampliación si cruza otra etapa de cualquiera de sus miembros. El
adelanto se revierte si falla el resto de la incorporación. Se conservan las
comprobaciones de edad de Optimist; no se fusionan equipos distintos ni se
reabren unidades cerradas.

### Datos personales pendientes y rendimiento de la revisión

La sección **Datos personales pendientes · por federación y club** reúne todas
las fichas de la base seleccionada que tienen documento provisional o carecen
de fecha de nacimiento. Se reconocen los prefijos `TEMP-`, `TEST-`, `STDEMO` y
`PRUEBA`; no se presentan como DNIs reales. No se comprueba aquí la validez legal
de otros documentos. Se puede filtrar por federación, club, falta de DNI, falta
de nacimiento o ambos, incluyendo fichas sin club ni federación.

Se muestran totales por club/federación y el detalle de las fichas. Una misma
persona no se duplica cuando le faltan ambos datos. Los datos se completan en
**Gestión de deportistas → Editar ficha**; esta vista no escribe datos ni envía
solicitudes. El informe se actualiza con la caché privada del proveedor.

El formulario individual se abre únicamente al activar **Revisar una identidad
individual**, para coincidencias dudosas, búsquedas manuales y correcciones.
Mientras está cerrado no ejecuta búsquedas de candidatos.

La vinculación por lotes valida el borrador y las fichas una sola vez, agrupa
las escrituras de identidades, decisiones de coincidencia y estados de filas,
y evita repetir el flujo individual por persona. Los resultados comparten las
lecturas y bloqueos de deportistas y los resultados existentes de la competición.
Las altas nuevas reutilizan el catálogo dentro de su transacción y lo amplían
en memoria con cada decisión para detectar duplicados dentro del propio lote,
antes de escribir. Las versiones de cada participante, los clubes, nacimientos
y coincidencias se validan contra el borrador bloqueado y el catálogo compartido.
Los identificadores TEMP- se reservan comprobando tanto las fichas existentes como
las altas del lote; la clave primaria sigue protegiendo frente a colisiones concurrentes.
Las fichas, propuestas y confirmaciones se escriben en bloques de hasta 200.
Las coincidencias descartadas conservan su rastro de revisión.
Se conservan los controles de versiones, roles, nacimiento, edad, puestos,
equipos y reversión completa ante conflictos. No requiere migraciones.

La incorporación de resultados carga y bloquea las unidades y sus miembros una
vez para todo el lote. Los resultados y sus referencias en las filas importadas
se escriben en bloques de hasta 200, con parámetros y precisión NUMERIC(10,2).
La creación de unidades nuevas sigue necesitando recuperar sus identificadores.
En una prueba local de 80 resultados, las consultas bajan de 333 a 17 al reutilizar
unidades y de 413 a 176 al crearlas. Son recuentos de consultas de esta fase, no
tiempos medidos en Supabase. `tests/test_rendimiento_importacion.py` comprueba
los límites de consultas con 80 y 201 equipos ficticios y conserva los puntos.

Para el alta completa con resultados, una prueba local de 160 deportistas en 80
equipos dobles pasa de 2.905 a 190 consultas; con 40 altas individuales pasa de
785 a 110. `tests/test_rendimiento_altas.py` comprueba estos presupuestos y el
fraccionamiento de más de 200 altas. Las mediciones son con datos ficticios y no
representan tiempos de red de Supabase ni Cloud SQL. Las decisiones opcionales
de memoria de nombres añaden sus propias escrituras a esos recuentos.

### Altas automáticas por similitud

En Revisión de participantes, «Alta automática de fichas nuevas» permite crear
las fichas y sus resultados con un solo botón. El umbral inicial es 0,75 y puede
ajustarse entre 0,65 y 0,85. Todas las coincidencias deben tener una similitud
estrictamente inferior al umbral: una puntuación igual queda pendiente. Esta
puntuación es orientativa, no una probabilidad; subir el umbral aumenta el riesgo
de duplicados. Se recomienda empezar con 0,75.

Cuando falta un apellido, un nombre compatible, el mismo primer apellido y el
mismo club confirmado elevan la puntuación al menos a 0,95 y refuerzan la propuesta
de ficha existente. Se conserva la comprobación de candidatos ambiguos y de fecha
de nacimiento. Si el club es distinto y la federación conocida también lo es,
la puntuación se limita a 0,64: no bloquea el alta nueva únicamente por ese apellido
omitido. La federación se toma del documento o del club identificado si falta en
el PDF. La federación del club identificado tiene prioridad sobre el texto del PDF;
si coincide el mismo club se usa su federación para comparar las identidades.
Un DNI coincidente o una variante confirmada conservan prioridad sobre esta regla.

Antes de comparar apellidos se comprueba la compatibilidad del nombre propio.
Los nombres claramente distintos no se proponen como coincidencias, aunque
compartan apellidos y club, ni bloquean la ficha exacta de otra persona del lote.
Se conserva tolerancia para erratas, iniciales y partes omitidas de nombres
compuestos. La búsqueda manual sigue permitiendo localizar otras fichas, y el
documento coincidente o una variante de nombre confirmada mantienen prioridad.

Las demás abreviaturas compatibles siguen pendientes independientemente de su
puntuación. También quedan pendientes los casos sin
nombre y apellidos, sin club identificado, con avisos de extracción o con equipos
incompletos. Se comprueban las similitudes tanto con fichas existentes como entre
las nuevas altas del mismo lote.

La separación provisional del nombre utiliza las propuestas del documento, el
formato «apellidos, nombre» o, como alternativa, la primera palabra como nombre.
El texto original se conserva y los datos pueden corregirse en la gestión de
deportistas. No se inventan fechas de nacimiento ni DNIs: se asigna un TEMP-.

Abrir la pantalla no escribe datos. Al pulsar el botón, el servicio vuelve a
comprobar las fichas y la versión del borrador, y guarda el lote en una transacción.
La revisión registra el umbral y la similitud utilizados. No requiere migración.

### Consulta de regatistas y calidad de fichas

La consulta muestra una tabla de exploración con año de nacimiento, edad a la
fecha consultada, clases activas, participaciones nacionales e internacionales,
mejores puestos por nivel y última regata registrada. Los filtros de clase activa,
nivel, nacimiento pendiente y años de nacimiento se aplican en la base antes del
límite de 500 filas. Puede ordenarse por actividad, experiencia nacional e
internacional, nombre o nacimiento pendiente. Las agregaciones se obtienen en
una consulta, sin una consulta adicional por cada regatista.

Los recuentos y mejores puestos de la tabla abarcan el historial completo hasta
la fecha consultada; el filtro de clase activa selecciona personas, no limita sus
resultados a esa clase. Son indicadores descriptivos, no puntuaciones de talento.
En la ficha individual, el resumen separa año natural, clase y nivel, y los
resultados muestran la edad al competir. No se suman puntos de regatas distintas
ni se inventan edades cuando falta el nacimiento.

La pantalla **Calidad de fichas** prioriza los nacimientos pendientes, agrupados
por federación y club, y permite completar una fecha confirmada desde la propia
pantalla. El mismo formulario está disponible en las fichas sin nacimiento.
La fecha inicial permanece vacía: no se infiere del nombre, categoría o resultado.
El guardado modifica únicamente el nacimiento, comprueba que no haya cambiado
desde la lectura, conserva el identificador y el historial, e invalida las lecturas
de la sesión. El DNI provisional no impide completar el nacimiento. Editar otros
datos sigue disponible en Gestión de deportistas.

No requiere cambios en el esquema. `tests/test_seguimiento.py`, las pruebas de
consulta y `tests/test_calidad_fichas_interfaz.py` comprueban filtros, ausencia de
duplicados, fecha histórica, guardado explícito y conflictos de edición.

### Revisión y unión de fichas duplicadas

En **Calidad de fichas → Revisar posibles fichas duplicadas**, activa la búsqueda
para obtener propuestas por nombre y primer apellido. Los nombres propios
claramente distintos no generan coincidencias solo por compartir apellidos.
También puedes elegir dos fichas manualmente. La propuesta no confirma una
identidad y nunca ejecuta una unión por sí sola.

La comparación muestra ambas fichas, los datos resultantes, sus resultados y los
registros que se trasladarán. Elige el identificador que se conservará, explica
la comprobación realizada y confirma expresamente que es la misma persona.
El nombre del destino se conserva; nacimiento, sexo o club vacíos se completan
con datos de la otra ficha. Los dos nombres originales quedan como variantes
confirmadas para sus respectivos clubes.

La unión se bloquea si hay documentos definitivos diferentes, nacimientos o
sexos contradictorios, dos miembros del mismo equipo doble, dos resultados de
equipos distintos en la misma competición, dos identidades confirmadas en la
misma embarcación importada o memoria de nombres contradictoria. No corrige
puestos, puntos, tripulaciones ni fechas de las unidades para resolver esos casos.
Las unidades compatibles permanecen como estaban, incluidas varias abiertas.

El guardado mueve mediciones, informes, pertenencias a equipos, identidades
importadas y memoria de nombres en una sola transacción. Los resultados siguen
vinculados a sus unidades originales. Una pertenencia idéntica de una clase
individual se consolida sin duplicar resultados. La ficha retirada deja de estar
disponible como deportista independiente. Se comprueba la versión de las fichas
y sus relaciones antes de guardar; un fallo revierte también la copia de auditoría.

Para bases existentes ejecuta una vez, en cada proveedor que vaya a utilizarlo:

```sql
\i sql/migrations/003_fusion_deportistas.sql
```

En Supabase puedes pegar el contenido del archivo en SQL Editor. En Cloud SQL
ejecútalo desde `psql` conectado a `sailing_talent`; la ruta debe corresponder al
archivo en el equipo o en Cloud Shell donde se ejecuta `psql`. La migración es
repetible y solo crea `fusion_deportista` y su índice; no une ni elimina deportistas.
`create_tables.sql` ya incluye esta tabla para instalaciones nuevas.

La tabla de auditoría conserva los documentos originales, motivo, datos de ambas
fichas y sus relaciones antes de la unión, y la ficha resultante. Tiene RLS activado
sin políticas públicas. La pantalla no incorpora una restauración automática;
las copias permiten inspeccionar los datos originales. Si falta la migración se
muestra un aviso y la unión no está disponible. La recogida de nacimientos sigue
funcionando sin esta migración.

Pruebas en `tests/test_duplicados.py` y `tests/test_duplicados_interfaz.py`, con
datos ficticios y sin conexiones a bases reales. Se han verificado también los
recorridos de unión, consolidación, auditoría y rollback en PostgreSQL temporal.

### Catalogo ampliado de clubes nacionales

`sql/sample_clubes_nacionales.sql` añade 13 clubes españoles observados en las
clasificaciones, conserva As Pontes si ya existe y registra 84 equivalencias de
nombres. Añade la Federacion Vasca de Vela para sus clubes. Se ejecuta despues de
`sample_data.sql`, `sample_clubes_galicia.sql` y la migracion 001; es repetible y
no sobrescribe clubes ni alias previos. Fuentes en `docs/fuentes_clubes_nacionales.md`.

```sql
\i sql/sample_clubes_nacionales.sql
```

En cargas nuevas, el nombre canonico exacto o un alias global confirmado identifica
el club automaticamente, manteniendo el texto original. No se vinculan deportistas
por esta decision. Los nombres duplicados, alias contextuales y siglas ambiguas
siguen requiriendo revision. Los borradores anteriores conservan sus decisiones.

### Memoria de nombres y coincidencias descartadas

La revisión permite recordar variantes de nombre confirmadas y descartar fichas
que correspondan a otras personas, siempre limitando la decisión al nombre y al
club de la fuente. Las opciones son explícitas y desmarcadas inicialmente.
Las futuras cargas reutilizan esas decisiones para preparar sus propuestas, sin
vincular personas automáticamente. Se pueden consultar y olvidar desde la revisión
individual. No se modifica el nombre oficial ni se reinterpretan resultados anteriores.

Antes de usar esta versión, ejecutar en ambas bases:

```sql
\i sql/migrations/002_memoria_nombres.sql
```

Las tablas nuevas y sus relaciones están descritas en
`docs/memoria_nombres.md`. La actualización del DNI conserva la memoria mediante
claves foráneas con `ON UPDATE CASCADE`.


### Revisión guiada de clasificaciones

La revisión abre un resumen por embarcación, con las fichas existentes que se
vincularán, las nuevas que se crearán y sus resultados. Se pueden desmarcar
embarcaciones completas y guardar las demás con un único botón. Un equipo doble
puede combinar una ficha existente con una nueva: vínculos, altas TEMP- y
resultados se guardan en la misma transacción. Un conflicto revierte el lote.

Los casos dudosos quedan en **Resolver casos pendientes**, donde se muestra una
embarcación cada vez. Desde ahí se identifican clubes, se revisan identidades o
se completan miembros. Las equivalencias de club se aplican a las apariciones del
mismo texto y pueden recordarse para próximas cargas. Tras resolverlos, se vuelve
al resumen para guardar los resultados preparados. DNI y nacimiento desconocidos
siguen pendientes en Calidad de fichas, sin inventar valores.

El umbral de altas se mantiene en 0,75 y puede ajustarse en un apartado plegado.
Las propuestas se vuelven a comprobar al guardar; si han cambiado desde la vista
previa se pide actualizar la revisión. **Herramientas avanzadas → Mostrar revisión
detallada** conserva los controles anteriores. Este flujo no requiere migraciones
adicionales. Pruebas: `test_revision_rapida.py` y
`test_revision_guiada_interfaz.py`.

### Exploración multiclase y orden por resultados

La pantalla inicial permite marcar varias clases en una barra de botones. El
filtro usa **cualquiera** de las clases seleccionadas; sin selección incluye
todas. Se puede consultar toda la trayectoria o solo unidades activas a la fecha
de consulta. Los botones y el periodo se aplican inmediatamente; los campos del
formulario se aplican con Buscar. El historial individual permanece completo.

El orden inicial es **Resultados ponderados**, dentro de los últimos 24 meses.
También se puede elegir el año natural de consulta o todo el historial. El índice
se calcula exclusivamente sobre resultados del periodo y las clases seleccionados:

- Valor por regata: peso del nivel dividido entre la raíz cuadrada del puesto
  general. Pesos iniciales: internacional 1.000, nacional 100, autonómico 10.
- Aportan los tres mejores valores, con factores 1, 0,5 y 0,25. Una cuarta regata
  puede mejorar el índice reemplazando una de las anteriores, pero no se suma.
- En empate: mejor valor individual, mejor puesto internacional, nacional,
  autonómico y fecha más reciente. El identificador deshace un empate persistente
  únicamente para mantener estable la lista, sin significado deportivo.
- Cada competición cuenta una vez por persona, aunque tenga varias unidades.
  Ambos miembros de una embarcación comparten resultado. Sin puesto no se puntúa.

Un 4.º internacional aporta 500, un 1.º nacional 100 y un 1.º autonómico 10 antes
del factor por orden. No se usan los puntos publicados por regatas distintas como
una escala común. El índice es una propuesta de ordenación descriptiva, no un
modelo validado de talento: no ajusta por edad, tamaño de flota ni nivel real de
los rivales. Las fichas sin resultados quedan visibles con índice cero.

La base filtra, agrega y ordena en una consulta antes del límite de 500 fichas.
El usuario puede escoger otros órdenes; la vista compacta deja las columnas
adicionales disponibles en Mostrar todas las columnas deportivas. No hay cambios
de esquema ni escrituras en bases de datos para esta funcionalidad.
