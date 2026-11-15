# Variantes de nombre y coincidencias descartadas

No se añade una lista de nombres al atributo `deportista`. Se crean dos relaciones normalizadas:

- `variante_nombre_deportista`: nombre original, nombre normalizado, ficha confirmada, club de la fuente, participante de origen y fecha de confirmación.
- `descarte_nombre_deportista`: los mismos datos, pero expresa que ese nombre y club no corresponden a esa ficha.

En cada relación, un deportista tiene cero o muchas decisiones; cada decisión corresponde a exactamente un deportista y un club. El participante de origen es opcional y se conserva mientras exista. El DNI de ambas tablas se actualiza en cascada cuando se completa el documento de una ficha provisional. No se guardan DNIs inventados ni se modifica el nombre oficial por recordar una variante.

La clave es `(dni_deportista, id_club, nombre_normalizado)`. No se impone que un nombre pertenezca a una única persona: los homónimos deben seguir siendo posibles y ambiguos. El nombre normalizado elimina acentos, puntuación y diferencias de mayúsculas; invierte el formato «APELLIDOS, Nombre». No deduce equivalencias entre nombres distintos: esas variantes requieren confirmación.

## Uso

En Revisión de participantes, abre la revisión individual, selecciona o crea la ficha correcta y confirma el club de la fuente. Opcionalmente marca **Recordar este nombre como variante de la ficha confirmada** y selecciona las otras fichas que sean personas distintas. Se guarda todo con la revisión; si falla la incorporación asociada del resultado, también se revierte la memoria de esa operación.

En la tabla de vínculos por lotes puedes marcar **Recordar los nombres seleccionados como variantes de sus fichas**. Esto exige confirmar los vínculos y el club de cada persona; no convierte una propuesta en una identidad automáticamente.

Para rectificar, abre **Consultar o corregir decisiones de nombres recordadas**. Selecciona las decisiones del nombre y club actuales, confirma y pulsa **Olvidar decisiones seleccionadas**. Esto no cambia deportistas, resultados ni vínculos ya incorporados. Una nueva variante confirmada elimina el descarte opuesto para esa ficha y contexto, y viceversa.

## Reutilización

Una variante exacta confirmada se considera evidencia fuerte en futuras clasificaciones del mismo club. Si hay varios candidatos equivalentes o fechas de nacimiento contradictorias, el lote sigue pendiente de revisión. El documento exacto tiene prioridad. Los descartes se omiten de las propuestas ordinarias; la búsqueda manual permite recuperarlos y advierte de la decisión previa.

Las propuestas siguen necesitando confirmación humana. No se entrenan modelos ni se generan recuerdos a partir de decisiones antiguas. Los cambios de club requieren revisar el nuevo contexto. La lectura del catálogo y de su memoria se hace en una consulta conjunta, no una consulta por regatista.

## Instalación

Ejecutar `sql/migrations/002_memoria_nombres.sql` tras la migración 001 en Supabase y Cloud SQL antes de usar esta versión. Es repetible, no modifica datos de deportistas y activa RLS sin políticas de acceso por Data API. Las tablas nuevas empiezan vacías. `sql/create_tables.sql` ya las incluye para instalaciones nuevas.
