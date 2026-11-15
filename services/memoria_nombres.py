"""Memoria explícita de identidades por nombre y club, independiente del documento."""
from sqlalchemy import text
from services.deportistas import ValidacionError, ConflictoError

TABLAS = {'variante':'variante_nombre_deportista','descarte':'descarte_nombre_deportista'}

def clave(nombre):
    from services.revision_participantes import normalizar
    if ',' in nombre:
        apellidos,propio=nombre.split(',',1)
        nombre=propio.strip()+' '+apellidos.strip()
    return normalizar(nombre)


def guardar(c, participante, dni, tipo):
    club=participante.get('id_club_identificado')
    normal=clave(participante['nombre_original'])
    if not club or not normal:
        raise ValidacionError('Confirma el club de la fuente antes de recordar decisiones de identidad.')
    parametros=dict(dni=dni,club=club,normal=normal,original=participante['nombre_original'],
                    origen=participante['id_participante_importado'])
    # Corregir expresamente una decisión elimina su opuesta, sin afectar homónimos.
    opuesta=TABLAS['descarte' if tipo=='variante' else 'variante']
    c.execute(text(f'DELETE FROM public.{opuesta} WHERE dni_deportista=:dni AND id_club=:club AND nombre_normalizado=:normal'),parametros)
    c.execute(text(f'''INSERT INTO public.{TABLAS[tipo]}
        (dni_deportista,id_club,nombre_original,nombre_normalizado,id_participante_origen)
        VALUES (:dni,:club,:original,:normal,:origen)
        ON CONFLICT (dni_deportista,id_club,nombre_normalizado) DO UPDATE SET
        nombre_original=excluded.nombre_original,id_participante_origen=excluded.id_participante_origen,
        confirmado_en=CURRENT_TIMESTAMP'''),parametros)


def listar(engine, identificador):
    from database import importaciones as datos
    with engine.connect() as c:
        p=datos.contexto_participante(c,identificador)
        if not p:return []
        salida=[]
        for tipo,tabla in TABLAS.items():
            for r in c.execute(text(f'''SELECT m.dni_deportista,d.nombre,d.apellidos,m.nombre_original,m.confirmado_en
                FROM public.{tabla} m JOIN public.deportista d ON d.dni=m.dni_deportista
                WHERE m.nombre_normalizado=:normal AND m.id_club=:club ORDER BY d.apellidos,d.nombre'''),
                dict(normal=clave(p['nombre_original']),club=p['id_club_identificado'])).mappings():
                salida.append(dict(r,tipo=tipo))
        return salida


def olvidar(engine, participante, version, decisiones):
    from services import importaciones as base
    from services.revision_participantes import version_participante
    if not isinstance(decisiones,list) or not decisiones:raise ValidacionError('Selecciona las decisiones que quieres olvidar.')
    with engine.begin() as c:
        p=base._bloquear_participante(c,participante)
        if version_participante(p)!=version:raise ConflictoError('La revisión cambió. Actualiza antes de olvidar decisiones.')
        for d in decisiones:
            if not isinstance(d,dict) or set(d)!={'tipo','dni'} or d['tipo'] not in TABLAS or not isinstance(d['dni'],str):
                raise ValidacionError('Selecciona una decisión válida.')
            c.execute(text(f'DELETE FROM public.{TABLAS[d["tipo"]]} WHERE dni_deportista=:dni AND id_club=:club AND nombre_normalizado=:normal'),
                      dict(dni=d['dni'],club=p['id_club_identificado'],normal=clave(p['nombre_original'])))


def olvidar_en_proveedor(proveedor,*args):
    from database.database import crear_engine
    m=crear_engine(proveedor)
    try:return olvidar(m,*args)
    finally:m.dispose()
