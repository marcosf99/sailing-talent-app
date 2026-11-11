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
  40, nacionales hasta el 80 e internacionales con ESP en el numero de vela.
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

El siguiente desarrollo sera el servicio de extraccion, vista previa y revision.
Ese servicio validara el criterio de seleccion, las tripulaciones completas y
sus fechas, y guardara las entidades definitivas en una unica transaccion.
No hace falta cambiar todavia los archivos de conexion ni `database/queries.py`.
