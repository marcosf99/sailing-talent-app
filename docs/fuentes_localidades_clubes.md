# Localidad y provincia de los clubes iniciales

Revisión: 11 de noviembre de 2026. `sql/update_localidades_clubes.sql`
completa los campos vacíos de los quince clubes de `sample_data.sql`.
Se usa el municipio en `localidad` para mantener el mismo criterio que en
la ampliación de clubes gallegos. Los núcleos concretos se explican aquí.
La provincia balear es Illes Balears, no Mallorca (isla).

## Galicia

- **Real Club Náutico de Portosín**: Porto do Son, A Coruña. La sede está en
  el núcleo de Portosín, dentro del municipio de Porto do Son.
  [Directorio turístico municipal](https://portodoson.gal/directorio-turistico/)
  y [ocio náutico municipal](https://portodoson.gal/turismo/rutas-e-experiencias/son-aventura/ocio-natico/).
- **Real Club Náutico de Vigo**: Vigo, Pontevedra. Se utiliza la sede náutica
  de Vigo, aunque el club también tiene instalaciones en Nigrán.
  [Contacto del club](https://rcnauticovigo.com/contacto/).
- **Real Club Náutico de A Coruña**: A Coruña, A Coruña.
  [Contacto del club](https://rcncoruna.com/contacto/).
- **Real Club Náutico de Sanxenxo**: Sanxenxo, Pontevedra.
  [Contacto del club](https://www.rcnsanxenxo.com/contactar/).

## Illes Balears

- **Real Club Náutico de Palma**: Palma, Illes Balears.
  [Ficha de la RFEV](https://rfev.es/clubes/real-club-nautico-de-palma/).
- **Club Nàutic S'Arenal**: Llucmajor, Illes Balears. El núcleo de s'Arenal
  se extiende por Palma y Llucmajor; el club pertenece al lado de Llucmajor.
  [Turismo de Llucmajor](https://www.visitllucmajor.com/ca/club-nautic-sarenal/).
- **Real Club Náutico Port de Pollença**: Pollença, Illes Balears. La sede
  está en el núcleo de Port de Pollença.
  [Web oficial](https://rcnpp.club/es/).
- **Club Marítimo San Antonio de la Playa**: Palma, Illes Balears. La sede
  está en Can Pastilla, municipio de Palma.
  [Web del club](https://www.cmsap.com/) y
  [prueba organizada en Can Pastilla](https://www.elitechip.net/en/competitions/2a-palma-beach-sup-crossing-2026).

## Cataluña

- **Real Club Náutico de Barcelona**: Barcelona, Barcelona.
  [Contacto del club](https://www.rcnb.com/contacto/).
- **Club Náutico El Masnou**: El Masnou, Barcelona.
  [Web del club](https://nauticmasnou.com/el-club/).
- **Club Nàutic El Balís**: Sant Andreu de Llavaneres, Barcelona.
  [Contacto del club](https://activitats.cnelbalis.com/es/default/contact).
- **Club Nàutic Garraf**: Sitges, Barcelona. Se encuentra en el núcleo de
  Garraf, dentro del municipio de Sitges.
  [Directorio municipal de entidades](https://www.sitges.cat/serveis/participacio-ciutadana/oficina-dentitats-i-voluntariat/portal-dentitat/directori-dentitats/@@entity_view/ENT-0141).

## Comunidad Valenciana

- **Real Club Náutico de Valencia**: Valencia, Valencia.
  [Contacto del club](https://www.rcnv.es/contacto/).
- **Real Club de Regatas de Alicante**: Alicante, Alicante.
  [Web oficial](https://web.rcra.es/).
- **Real Club Náutico de Torrevieja**: Torrevieja, Alicante.
  [Contacto del club](https://www.rcnt.com/contactos-y-horarios-rcnt-torrevieja/).

## Aplicación

Ejecutar `sql/update_localidades_clubes.sql` después de `sql/sample_data.sql`.
El script incluye BEGIN/COMMIT y busca cada club por nombre y federación,
sin depender de IDs autogenerados. Solo rellena campos NULL o vacíos, incluidos
espacios en blanco. Conserva cualquier valor ya informado y se puede repetir.
No requiere migraciones del esquema. En bases que ya tengan la ampliación
gallega, los 26 clubes quedarán con localidad y provincia informadas.
