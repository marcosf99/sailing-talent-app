-- Catálogo ampliado de clubes españoles observados en las clasificaciones.
-- Ejecutar después de sample_data.sql, sample_clubes_galicia.sql y migración 001.
-- Repetible; no sustituye clubes, equivalencias ni datos ya confirmados.
-- Fuentes y decisiones: docs/fuentes_clubes_nacionales.md.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
LOCK TABLE public.federacion_autonomica, public.club, public.alias_club IN SHARE ROW EXCLUSIVE MODE;
INSERT INTO public.federacion_autonomica(nombre,comunidad_autonoma)
SELECT 'Federación Vasca de Vela','País Vasco'
WHERE NOT EXISTS (SELECT 1 FROM public.federacion_autonomica WHERE nombre='Federación Vasca de Vela');
CREATE TEMP TABLE catalogo_ampliado(nombre TEXT,localidad TEXT,provincia TEXT,federacion TEXT) ON COMMIT DROP;
INSERT INTO catalogo_ampliado VALUES
('Club Náutico de Altea','Altea','Alicante','Federación de la Comunidad Valenciana de Vela'),
('Club Náutico de Jávea','Jávea','Alicante','Federación de la Comunidad Valenciana de Vela'),
('Club Náutico Puerto Sherry','El Puerto de Santa María','Cádiz','Federación Andaluza de Vela'),
('Club Náutico Sevilla','Sevilla','Sevilla','Federación Andaluza de Vela'),
('Club Nàutic Vilassar de Mar','Vilassar de Mar','Barcelona','Federación Catalana de Vela'),
('Club Nàutic de Cala Gamba','Palma','Illes Balears','Federación Balear de Vela'),
('Real Club Náutico de Gran Canaria','Las Palmas de Gran Canaria','Las Palmas','Federación Canaria de Vela'),
('Real Club Náutico de Arrecife','Arrecife','Las Palmas','Federación Canaria de Vela'),
('Real Club Marítimo de Santander','Santander','Cantabria','Federación Cántabra de Vela'),
('Real Club Náutico de San Sebastián','San Sebastián','Gipuzkoa','Federación Vasca de Vela'),
('Club Náutico de Hondarribia','Hondarribia','Gipuzkoa','Federación Vasca de Vela'),
('Club Náutico de Álava "Aldayeta"','Nanclares de Gamboa','Álava','Federación Vasca de Vela'),
('Real Club Marítimo del Abra - Real Sporting Club','Getxo','Bizkaia','Federación Vasca de Vela'),
('Club Vela Fluvial As Pontes','As Pontes de García Rodríguez','A Coruña','Real Federación Gallega de Vela');
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM catalogo_ampliado n WHERE (SELECT COUNT(*) FROM public.federacion_autonomica f WHERE f.nombre=n.federacion)<>1) THEN
RAISE EXCEPTION 'Falta una federación o su nombre es ambiguo; revisar antes de ampliar clubes'; END IF;
IF EXISTS (SELECT 1 FROM catalogo_ampliado n WHERE (SELECT COUNT(*) FROM public.club c WHERE LOWER(BTRIM(c.nombre))=LOWER(n.nombre))>1) THEN
RAISE EXCEPTION 'Hay clubes con nombre duplicado; revisar antes de ampliar'; END IF;
END $$;
INSERT INTO public.club(nombre,director_deportivo,telefono,localidad,provincia,id_federacion)
SELECT n.nombre,NULL,NULL,n.localidad,n.provincia,(SELECT id_federacion FROM public.federacion_autonomica WHERE nombre=n.federacion)
FROM catalogo_ampliado n WHERE NOT EXISTS (SELECT 1 FROM public.club c WHERE LOWER(BTRIM(c.nombre))=LOWER(n.nombre));
CREATE TEMP TABLE equivalencias_ampliadas(texto TEXT,normalizado TEXT,club TEXT) ON COMMIT DROP;
INSERT INTO equivalencias_ampliadas VALUES
('C. Alamar Sada','c alamar sada','Club Alamar Sada'),
('C.Grupo Bazán','c grupo bazan','Club Grupo Bazán'),
('C.M.Canido','c m canido','Club Marítimo de Canido'),
('C.M.Carino','c m carino','Club do Mar Cariño'),
('C.M. Oza','c m oza','Club Marítimo de Oza O Puntal'),
('C.N.D.Riveira','c n d riveira','Club Náutico Deportivo de Riveira'),
('C.N.Marina Coruna','c n marina coruna','Club Náutico Marina Coruña'),
('C.N.Ría De Ares','c n ria de ares','Club Náutico Ría de Ares'),
('C.V.F As Pontes','c v f as pontes','Club Vela Fluvial As Pontes'),
('Club Alamar Sada','club alamar sada','Club Alamar Sada'),
('Club de Vela Fluvial de As Pontes','club de vela fluvial de as pontes','Club Vela Fluvial As Pontes'),
('Club do Mar Cariño','club do mar carino','Club do Mar Cariño'),
('Club Grupo Bazán','club grupo bazan','Club Grupo Bazán'),
('Club Marítimo de Canido','club maritimo de canido','Club Marítimo de Canido'),
('Club Marítimo de Oza O Puntal','club maritimo de oza o puntal','Club Marítimo de Oza O Puntal'),
('Club Marítimo San Antonio de la Playa','club maritimo san antonio de la playa','Club Marítimo San Antonio de la Playa'),
('Club Nautic Cala Gamba','club nautic cala gamba','Club Nàutic de Cala Gamba'),
('Club Nàutic de Cala Gamba','club nautic de cala gamba','Club Nàutic de Cala Gamba'),
('Club Nautic El Balis','club nautic el balis','Club Nàutic El Balís'),
('Club Nàutic S''Arenal','club nautic s arenal','Club Nàutic S''Arenal'),
('Club Nàutic Vilassar de Mar','club nautic vilassar de mar','Club Nàutic Vilassar de Mar'),
('Club Náutico Aldayeta','club nautico aldayeta','Club Náutico de Álava "Aldayeta"'),
('Club Náutico Altea','club nautico altea','Club Náutico de Altea'),
('Club Náutico de Álava "Aldayeta"','club nautico de alava aldayeta','Club Náutico de Álava "Aldayeta"'),
('Club Náutico de Altea','club nautico de altea','Club Náutico de Altea'),
('Club Náutico de Hondarribia','club nautico de hondarribia','Club Náutico de Hondarribia'),
('Club Náutico de Jávea','club nautico de javea','Club Náutico de Jávea'),
('Club Náutico Deportivo de Riveira','club nautico deportivo de riveira','Club Náutico Deportivo de Riveira'),
('Club Náutico Javea','club nautico javea','Club Náutico de Jávea'),
('Club Náutico Marina Coruña','club nautico marina coruna','Club Náutico Marina Coruña'),
('Club Náutico Puerto Sherry','club nautico puerto sherry','Club Náutico Puerto Sherry'),
('Club Náutico Ría de Ares','club nautico ria de ares','Club Náutico Ría de Ares'),
('Club Náutico Sevilla','club nautico sevilla','Club Náutico Sevilla'),
('Club Vela Fluvial As Pontes','club vela fluvial as pontes','Club Vela Fluvial As Pontes'),
('CM Canido','cm canido','Club Marítimo de Canido'),
('CMSAP','cmsap','Club Marítimo San Antonio de la Playa'),
('CMSAP - C''an Pastilla','cmsap c an pastilla','Club Marítimo San Antonio de la Playa'),
('CN ALTEA','cn altea','Club Náutico de Altea'),
('CN ARENAL','cn arenal','Club Nàutic S''Arenal'),
('CN Cala Gamba','cn cala gamba','Club Nàutic de Cala Gamba'),
('CN EL BALÍS','cn el balis','Club Nàutic El Balís'),
('CN JAVEA','cn javea','Club Náutico de Jávea'),
('CN PUERTO SHERRY','cn puerto sherry','Club Náutico Puerto Sherry'),
('CN s''Arenal','cn s arenal','Club Nàutic S''Arenal'),
('CN SEVILLA','cn sevilla','Club Náutico Sevilla'),
('CN VILASSAR DE MAR','cn vilassar de mar','Club Nàutic Vilassar de Mar'),
('M.R.C.Y.B.','m r c y b','Monte Real Club de Yates de Baiona'),
('Monte Real Club de Yates de Baiona','monte real club de yates de baiona','Monte Real Club de Yates de Baiona'),
('MRCYB','mrcyb','Monte Real Club de Yates de Baiona'),
('R.C.M.Aguete','r c m aguete','Real Club de Mar de Aguete'),
('R.C.N.La Coruna','r c n la coruna','Real Club Náutico de A Coruña'),
('R.C.N.Portosin','r c n portosin','Real Club Náutico de Portosín'),
('R.C.N.Rodeira','r c n rodeira','Real Club Náutico Rodeira'),
('R.C.N.Sanxenxo','r c n sanxenxo','Real Club Náutico de Sanxenxo'),
('R.C.N.Vigo','r c n vigo','Real Club Náutico de Vigo'),
('RCM SANTANDER','rcm santander','Real Club Marítimo de Santander'),
('RCMA RSC','rcma rsc','Real Club Marítimo del Abra - Real Sporting Club'),
('RCMS','rcms','Real Club Marítimo de Santander'),
('RCN ARRECIFE','rcn arrecife','Real Club Náutico de Arrecife'),
('RCN BARCELONA','rcn barcelona','Real Club Náutico de Barcelona'),
('RCN GRAN CANARIA','rcn gran canaria','Real Club Náutico de Gran Canaria'),
('RCN LA CORUÑA','rcn la coruna','Real Club Náutico de A Coruña'),
('RCN SAN SEBASTIAN','rcn san sebastian','Real Club Náutico de San Sebastián'),
('RCN VIGO','rcn vigo','Real Club Náutico de Vigo'),
('RCNGC','rcngc','Real Club Náutico de Gran Canaria'),
('RCNPP','rcnpp','Real Club Náutico Port de Pollença'),
('RCR ALICANTE','rcr alicante','Real Club de Regatas de Alicante'),
('RCRA','rcra','Real Club de Regatas de Alicante'),
('Real Club de Mar de Aguete','real club de mar de aguete','Real Club de Mar de Aguete'),
('Real Club de Regatas de Alicante','real club de regatas de alicante','Real Club de Regatas de Alicante'),
('Real Club Marítimo de Santander','real club maritimo de santander','Real Club Marítimo de Santander'),
('Real Club Marítimo del Abra - Real Sporting Club','real club maritimo del abra real sporting club','Real Club Marítimo del Abra - Real Sporting Club'),
('Real Club Náutico Arrecife','real club nautico arrecife','Real Club Náutico de Arrecife'),
('Real Club Náutico de A Coruña','real club nautico de a coruna','Real Club Náutico de A Coruña'),
('Real Club Náutico de Arrecife','real club nautico de arrecife','Real Club Náutico de Arrecife'),
('Real Club Náutico de Barcelona','real club nautico de barcelona','Real Club Náutico de Barcelona'),
('Real Club Náutico de Gran Canaria','real club nautico de gran canaria','Real Club Náutico de Gran Canaria'),
('Real Club Náutico de Portosín','real club nautico de portosin','Real Club Náutico de Portosín'),
('Real Club Náutico de San Sebastian','real club nautico de san sebastian','Real Club Náutico de San Sebastián'),
('Real Club Náutico de Sanxenxo','real club nautico de sanxenxo','Real Club Náutico de Sanxenxo'),
('Real Club Náutico de Vigo','real club nautico de vigo','Real Club Náutico de Vigo'),
('Real Club Náutico Port de Pollença','real club nautico port de pollenca','Real Club Náutico Port de Pollença'),
('Real Club Nautico puerto pollensa','real club nautico puerto pollensa','Real Club Náutico Port de Pollença'),
('Real Club Náutico Rodeira','real club nautico rodeira','Real Club Náutico Rodeira');
-- Solo se añaden correspondencias inequívocas; se preservan decisiones previas.
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM equivalencias_ampliadas e WHERE (SELECT COUNT(*) FROM public.club c WHERE c.nombre=e.club)<>1) THEN
RAISE EXCEPTION 'Falta un club de referencia o existe duplicado; ejecutar también el catálogo gallego'; END IF;
IF EXISTS (SELECT 1 FROM equivalencias_ampliadas e JOIN public.club c ON c.nombre=e.club
JOIN public.alias_club a ON a.texto_normalizado=e.normalizado AND COALESCE(BTRIM(a.contexto_fuente),'')=''
WHERE a.id_club<>c.id_club) THEN
RAISE EXCEPTION 'Una equivalencia ya apunta a otro club; no se sobrescribe'; END IF;
END $$;
INSERT INTO public.alias_club(texto_alias,texto_normalizado,id_club,contexto_fuente)
SELECT e.texto,e.normalizado,c.id_club,NULL FROM equivalencias_ampliadas e JOIN public.club c ON c.nombre=e.club
WHERE NOT EXISTS (SELECT 1 FROM public.alias_club a WHERE a.texto_normalizado=e.normalizado AND COALESCE(BTRIM(a.contexto_fuente),'')='');
COMMIT;
