# Clubes gallegos observados en clasificaciones

Revisión: 11 de noviembre de 2026. El script `sql/sample_clubes_galicia.sql`
añade los once clubes que faltaban a los cuatro gallegos de `sample_data.sql`.
Todos se vinculan a Real Federación Gallega de Vela por su nombre, sin fijar IDs.
Se indican municipios en localidad y se dejan director deportivo y teléfono
en NULL. No se cambian los registros existentes ni se crean alias confirmados.

## Clasificaciones aportadas

- `Unknown-5.pdf`: Optimist, XXVII Semana del Atlántico Ciudad de Vigo,
  29/10/2026–01/11/2026, diez páginas.
- `Unknown-6.pdf`: ILCA 4, XXVII Semana del Atlántico Ciudad de Vigo,
  03/10/2026–04/10/2026, cuatro páginas.
- `overall_Nacra17.pdf`: revisado; no aporta otros clubes gallegos identificables
  por el campo club. No se infieren clubes a partir de nombres de deportistas.

Los PDF originales y sus datos personales no se incluyen en este documento.
Las referencias de página siguientes usan numeración desde 1.

## Correspondencias y fuentes de contraste

- **Club Alamar Sada** — `C. Alamar Sada`, ILCA 4, página 2.
  Sada, A Coruña. [Web del club](https://alamarsada.com/gl/).
- **Club Grupo Bazán** — `C.Grupo Bazán`, ILCA 4, página 3.
  Ferrol, A Coruña. [Ficha de la Federación Gallega de Tenis](https://www.fgtenis.net/portfolio-item/club-grupo-bazan/).
  Es un club con varias secciones deportivas; la clasificación acredita su
  participación en vela.
- **Club Marítimo de Oza O Puntal** — `C.M. Oza`, ILCA 4, página 2.
  A Coruña, A Coruña. [Denominación en el BOE](https://www.boe.es/diario_boe/txt.php?id=BOE-B-2024-12547).
- **Club do Mar Cariño** — `C.M.Carino`, ILCA 4, página 3.
  Cariño, A Coruña. [Directorio de Fundación Ecomar](https://fundacionecomar.org/que-hacemos/grimpola-ecomar/clubes-grimpola-2025/).
  Se conserva la denominación del directorio, en lugar de expandir libremente
  las iniciales como «Club Marítimo».
- **Club Náutico Deportivo de Riveira** — `C.N.D.Riveira`, ILCA 4, página 2.
  Ribeira, A Coruña. [Convocatoria oficial del club](https://www.nauticoriveira.com/v10/noticias_detalle.php?noticiaID=271).
  El club utiliza «Riveira» en su nombre; el municipio se registra como Ribeira.
- **Club Náutico Marina Coruña** — `C.N.Marina Coruna`, ILCA 4, página 2.
  A Coruña, A Coruña. [Ficha de la RFEV](https://rfev.es/clubes/club-nautico-marina-coruna/).
- **Club Náutico Ría de Ares** — `C.N.Ría De Ares`, ILCA 4, página 2.
  Ares, A Coruña. [Ficha del Sergas](https://observatoriosaudepublica.sergas.gal/es/atopa-saude/club-nautico-ria-de-ares).
- **Monte Real Club de Yates de Baiona** — `M.R.C.Y.B.`, ILCA 4, página 3.
  Baiona, Pontevedra. [Localización oficial](https://www.mrcyb.es/el-club/localizacion/).
- **Real Club de Mar de Aguete** — `R.C.M.Aguete`, Optimist, página 10,
  e ILCA 4, página 3. Marín, Pontevedra. [Web oficial](https://rcmaraguete.com/).
- **Real Club Náutico Rodeira** — `R.C.N.Rodeira`, ILCA 4, página 4.
  Cangas, Pontevedra. [Web del club](https://nauticorodeira.com/club/).
- **Club Marítimo de Canido** — `C.M.Canido`, Optimist, página 10.
  Vigo, Pontevedra. [Contacto oficial](https://www.cmcanido.es/contacto/).

Ya estaban dados de alta Real Club Náutico de Portosín, Real Club Náutico de
Vigo, Real Club Náutico de A Coruña y Real Club Náutico de Sanxenxo.
`R.C.N.La Coruna` corresponde al registro existente de A Coruña.

Se excluye `C.V.Atlántico` de esta ampliación gallega: el
[directorio de la Federação Portuguesa de Vela](https://fpvela.pt/federacao-portuguesa-de-vela/clubes-norte/)
lo sitúa en Leça da Palmeira (Portugal).

## Ejecución y alcance

En una instalación nueva: crear el esquema, cargar `sample_data.sql` y después
`sample_clubes_galicia.sql`. En una base ya inicializada basta con este último.
El script es transaccional, exige que exista la federación gallega y evita
repetir nombres con diferencias de mayúsculas o espacios exteriores dentro de
esa federación. No intenta fusionar clubes registrados con otros nombres:
esas variantes deben revisarse antes de ejecutar una futura ampliación.

Con los datos base originales, el resultado esperado es 26 clubes en total,
15 de ellos gallegos. No se modifica el esquema ni se añaden deportistas,
resultados o informes.
