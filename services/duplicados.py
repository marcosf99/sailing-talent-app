"""Revisión de duplicados y unión explícita, transaccional y con copia de auditoría."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json

from sqlalchemy import Date, JSON, Numeric, bindparam, text
from sqlalchemy.exc import IntegrityError
from database import importaciones as datos
from services import revision_participantes as revision
from services.deportistas import ValidacionError, ConflictoError


RELACIONES = {
    'registro_antropometrico':'dni_deportista',
    'informe':'dni_deportista',
    'forma_parte':'dni_deportista',
    'participante_importado':'dni_deportista_confirmado',
    'coincidencia_propuesta':'dni_deportista',
    'variante_nombre_deportista':'dni_deportista',
    'descarte_nombre_deportista':'dni_deportista',
}


def provisional(documento):
    return documento.upper().startswith(('TEMP-','TEST-','STDEMO','PRUEBA'))


def catalogo(engine):
    with engine.connect() as c:
        return datos.fichas_revision(c)


def posibles(fichas, limite=200):
    """Bloques por primer apellido; un nombre propio distinto no genera aviso."""
    if type(limite) is not int or not 1<=limite<=1000:
        raise ValidacionError('Indica un límite válido de propuestas.')
    bloques=defaultdict(list)
    for f in fichas:
        palabras=[p for p in revision.normalizar(f['apellidos']).split()
                  if p not in ('de','del','la','las','los','y')]
        if palabras:bloques[palabras[0]].append(f)
    pares=[]
    for bloque in bloques.values():
        for i,a in enumerate(bloque):
            p=dict(nombre_original=a['nombre']+' '+a['apellidos'],nombre_propuesto=a['nombre'],
                apellidos_propuestos=a['apellidos'],id_club_identificado=a['id_club'],
                club_original=a['club'],federacion_club_identificado=a['federacion'])
            for b in bloque[i+1:]:
                candidatos=revision._candidatos(None,p,fichas=[b],aliases=[])
                if candidatos and (candidatos[0]['indice_similitud']>=Decimal('.75') or candidatos[0]['nombre_abreviado']):
                    pares.append(dict(a=a['dni'],b=b['dni'],similitud=candidatos[0]['indice_similitud'],motivos=candidatos[0]['motivos']))
    return sorted(pares,key=lambda p:(-p['similitud'],p['a'],p['b']))[:limite]


def _identificadores(origen,destino):
    if any(not isinstance(d,str) or not d.strip() or len(d)>20 for d in (origen,destino)) or origen==destino:
        raise ValidacionError('Selecciona dos fichas distintas y válidas.')


def _snapshot(c,origen,destino,bloquear=False):
    _identificadores(origen,destino)
    parametros=dict(origen=origen,destino=destino)
    bloqueo=' FOR UPDATE' if bloquear else ''
    fichas=[dict(r) for r in c.execute(text('''SELECT dni,nombre,apellidos,fecha_nacimiento,sexo,id_club
        FROM public.deportista WHERE dni IN (:origen,:destino) ORDER BY dni'''+bloqueo
        ).columns(fecha_nacimiento=Date()),parametros).mappings()]
    if len(fichas)!=2:
        raise ConflictoError('Una de las fichas ya no existe. Actualiza la revisión.')
    relaciones={}
    for tabla,campo in RELACIONES.items():
        filas=[dict(r) for r in c.execute(text(f'SELECT * FROM public.{tabla} WHERE {campo} IN (:origen,:destino)'+bloqueo),parametros).mappings()]
        relaciones[tabla]=sorted(filas,key=lambda r:json.dumps(r,sort_keys=True,default=str))
    if bloquear:
        # La FK de participa_en toma un bloqueo sobre la unidad. Bloquear estas
        # unidades evita insertar nuevos resultados durante la unión revisada.
        c.execute(text('''SELECT id_unidad FROM public.unidad_competitiva
            WHERE id_unidad IN (SELECT id_unidad FROM public.forma_parte
                WHERE dni_deportista IN (:origen,:destino)) ORDER BY id_unidad FOR UPDATE'''),parametros).all()
        c.execute(text('''SELECT id_unidad,id_competicion FROM public.participa_en
            WHERE id_unidad IN (SELECT id_unidad FROM public.forma_parte
                WHERE dni_deportista IN (:origen,:destino)) ORDER BY id_unidad,id_competicion FOR UPDATE'''),parametros).all()
    # Las unidades y sus resultados no se modifican, pero forman parte de la
    # revisión para detectar dos resultados distintos de la misma competición.
    equipos=[dict(r) for r in c.execute(text('''SELECT fp.*,u.id_clase,u.fecha_inicio,u.fecha_fin,
        cl.nombre AS clase,cl.numero_tripulantes
        FROM public.forma_parte fp JOIN public.unidad_competitiva u ON u.id_unidad=fp.id_unidad
        JOIN public.clase cl ON cl.id_clase=u.id_clase
        WHERE fp.id_unidad IN (SELECT id_unidad FROM public.forma_parte
            WHERE dni_deportista IN (:origen,:destino))
        ORDER BY fp.id_unidad,fp.dni_deportista'''),parametros).mappings()]
    resultados=[dict(r) for r in c.execute(text('''SELECT fp.dni_deportista,p.*,co.nombre AS competicion,
        co.fecha_inicio,co.nivel,cl.nombre AS clase
        FROM public.forma_parte fp JOIN public.participa_en p ON p.id_unidad=fp.id_unidad
        JOIN public.competicion co ON co.id_competicion=p.id_competicion
        JOIN public.clase cl ON cl.id_clase=co.id_clase
        WHERE fp.dni_deportista IN (:origen,:destino)
        ORDER BY co.id_competicion,p.id_unidad,fp.dni_deportista'''),parametros).mappings()]
    auditorias=[dict(r) for r in c.execute(text('''SELECT id_fusion,dni_deportista FROM public.fusion_deportista
        WHERE dni_deportista IN (:origen,:destino) ORDER BY id_fusion'''+bloqueo),parametros).mappings()]
    return dict(fichas=fichas,relaciones=relaciones,equipos=equipos,resultados=resultados,auditorias=auditorias)


def _version(snapshot,origen,destino):
    return hashlib.sha256(json.dumps([origen,destino,snapshot],sort_keys=True,default=str).encode()).hexdigest()


def _plan(snapshot,origen,destino):
    fichas={f['dni']:f for f in snapshot['fichas']};a,b=fichas[origen],fichas[destino]
    bloqueos=[]
    if not provisional(origen) and not provisional(destino):
        bloqueos.append('Las dos fichas tienen documentos definitivos distintos. Comprueba los documentos antes de unirlas.')
    elif not provisional(origen) and provisional(destino):
        bloqueos.append('Conserva la ficha con documento definitivo; cambia la dirección de la unión.')
    for campo,etiqueta in [('fecha_nacimiento','fechas de nacimiento'),('sexo','datos de sexo')]:
        if a[campo] is not None and b[campo] is not None and a[campo]!=b[campo]:
            bloqueos.append('Las fichas tienen '+etiqueta+' diferentes. Corrige o verifica ese dato antes de unirlas.')
    por_unidad=defaultdict(list)
    for r in snapshot['relaciones']['forma_parte']:por_unidad[r['id_unidad']].append(r)
    equipos={r['id_unidad']:r for r in snapshot['equipos']}
    for unidad,miembros in por_unidad.items():
        if len(miembros)>1 and (equipos[unidad]['numero_tripulantes']>1 or len({m['rol'] for m in miembros if m['rol']})>1):
            bloqueos.append(f"Ambas fichas aparecen como miembros del mismo equipo de {equipos[unidad]['clase']} (unidad {unidad}). No se puede reducir su tripulación al unirlas.")
    filas=defaultdict(list)
    for r in snapshot['relaciones']['participante_importado']:filas[r['id_fila']].append(r)
    for fila,personas in filas.items():
        if len(personas)>1:
            bloqueos.append(f'Ambas fichas están confirmadas en la misma embarcación importada (fila {fila}). Revisa las identidades de sus miembros.')
    eventos=defaultdict(list)
    for r in snapshot['resultados']:eventos[r['id_competicion']].append(r)
    for evento,resultados in eventos.items():
        if len({r['dni_deportista'] for r in resultados})>1 and len({r['id_unidad'] for r in resultados})>1:
            bloqueos.append(f"Las fichas tienen resultados con equipos distintos en «{resultados[0]['competicion']}». La unión no decide qué resultado es correcto.")
    claves=lambda tabla:{(r['id_club'],r['nombre_normalizado']) for r in snapshot['relaciones'][tabla]}
    canonicos={(f['id_club'],revision.memoria.clave(f['nombre']+' '+f['apellidos'])) for f in (a,b) if f['id_club']}
    if (claves('variante_nombre_deportista') | canonicos) & claves('descarte_nombre_deportista'):
        bloqueos.append('Hay variantes y descartes de nombres contradictorios. Revisa la memoria de nombres antes de unir las fichas.')
    final={**b}
    for campo in ('fecha_nacimiento','sexo','id_club'):
        if final[campo] is None:final[campo]=a[campo]
    avisos=[]
    if a['id_club'] and b['id_club'] and a['id_club']!=b['id_club']:
        avisos.append('Se conserva el club de la ficha elegida. Los clubes originales de las clasificaciones no se modifican.')
    if a['nombre']!=b['nombre'] or a['apellidos']!=b['apellidos']:
        avisos.append('Se conserva el nombre de la ficha elegida; el nombre de la ficha retirada queda en la copia de auditoría.')
    cantidades={tabla:sum(r[campo]==origen for r in snapshot['relaciones'][tabla]) for tabla,campo in RELACIONES.items()}
    return dict(origen=a,destino=b,ficha_final=final,bloqueos=bloqueos,avisos=avisos,
                cantidades=cantidades,resultados=snapshot['resultados'])


def preparar(engine,origen,destino):
    with engine.connect() as c:
        snapshot=_snapshot(c,origen,destino)
        return {**_plan(snapshot,origen,destino),'version':_version(snapshot,origen,destino)}


def unir(engine,origen,destino,version,motivo,*,confirmar=False):
    if confirmar is not True or not isinstance(motivo,str) or not motivo.strip() or len(motivo)>1000:
        raise ValidacionError('Confirma que es la misma persona y explica el motivo de la unión (hasta 1.000 caracteres).')
    _identificadores(origen,destino)
    try:
        with engine.begin() as c:
            snapshot=_snapshot(c,origen,destino,True)
            if not isinstance(version,str) or version!=_version(snapshot,origen,destino):
                raise ConflictoError('Las fichas o sus historiales han cambiado. Actualiza la comparación antes de unirlas.')
            plan=_plan(snapshot,origen,destino)
            if plan['bloqueos']:raise ConflictoError(' '.join(plan['bloqueos']))
            parametros=dict(origen=origen,destino=destino)
            # Copia completa antes de mover o eliminar cualquier dato.
            copia=json.loads(json.dumps(snapshot,default=str))
            final=json.loads(json.dumps(plan['ficha_final'],default=str))
            c.execute(text('''INSERT INTO public.fusion_deportista
                (documento_origen,documento_conservado,dni_deportista,motivo,datos_antes,ficha_despues)
                VALUES (:origen,:destino,:destino,:motivo,:antes,:despues)''').bindparams(
                    bindparam('antes',type_=JSON()),bindparam('despues',type_=JSON())),
                dict(parametros,motivo=motivo.strip(),antes=copia,despues=final))
            ficha=plan['ficha_final']
            c.execute(text('''UPDATE public.deportista SET fecha_nacimiento=:nacimiento,sexo=:sexo,id_club=:club
                WHERE dni=:destino''').bindparams(bindparam('nacimiento',type_=Date())),
                dict(parametros,nacimiento=ficha['fecha_nacimiento'],sexo=ficha['sexo'],club=ficha['id_club']))
            for tabla in ('registro_antropometrico','informe','participante_importado'):
                campo=RELACIONES[tabla]
                c.execute(text(f'UPDATE public.{tabla} SET {campo}=:destino WHERE {campo}=:origen'),parametros)
            c.execute(text('''INSERT INTO public.forma_parte(dni_deportista,id_unidad,rol)
                SELECT :destino,id_unidad,rol FROM public.forma_parte WHERE dni_deportista=:origen
                ON CONFLICT (dni_deportista,id_unidad) DO UPDATE SET rol=COALESCE(forma_parte.rol,excluded.rol)'''),parametros)
            c.execute(text('DELETE FROM public.forma_parte WHERE dni_deportista=:origen'),parametros)
            for tabla in ('variante_nombre_deportista','descarte_nombre_deportista'):
                c.execute(text(f'''INSERT INTO public.{tabla}
                    (dni_deportista,id_club,nombre_original,nombre_normalizado,id_participante_origen,confirmado_en)
                    SELECT :destino,id_club,nombre_original,nombre_normalizado,id_participante_origen,confirmado_en
                    FROM public.{tabla} WHERE dni_deportista=:origen
                    ON CONFLICT (dni_deportista,id_club,nombre_normalizado) DO NOTHING'''),parametros)
                c.execute(text(f'DELETE FROM public.{tabla} WHERE dni_deportista=:origen'),parametros)
            for original in (plan['origen'],plan['destino']):
                if original['id_club']:
                    nombre=original['nombre']+' '+original['apellidos']
                    c.execute(text('''INSERT INTO public.variante_nombre_deportista
                        (dni_deportista,id_club,nombre_original,nombre_normalizado)
                        VALUES (:destino,:club,:nombre,:normal)
                        ON CONFLICT (dni_deportista,id_club,nombre_normalizado) DO NOTHING'''),
                        dict(destino=destino,club=original['id_club'],nombre=nombre,normal=revision.memoria.clave(nombre)))
            # El índice parcial permite solo una propuesta aceptada por aparición.
            # Liberarla dentro de la transacción antes de trasladar la aceptación.
            c.execute(text("UPDATE public.coincidencia_propuesta SET estado_revision='pendiente' WHERE dni_deportista=:origen AND estado_revision='aceptada'"),parametros)
            for r in snapshot['relaciones']['coincidencia_propuesta']:
                if r['dni_deportista']!=origen:continue
                c.execute(text('''INSERT INTO public.coincidencia_propuesta
                    (id_participante_importado,dni_deportista,indice_similitud,motivos,estado_revision,revisado_en)
                    VALUES (:id,:destino,:indice,:motivos,:estado,:revisado)
                    ON CONFLICT (id_participante_importado,dni_deportista) DO NOTHING''').bindparams(bindparam('indice',type_=Numeric())),
                    dict(destino=destino,id=r['id_participante_importado'],indice=r['indice_similitud'],motivos=r['motivos'],estado=r['estado_revision'],revisado=r['revisado_en']))
            c.execute(text('DELETE FROM public.coincidencia_propuesta WHERE dni_deportista=:origen'),parametros)
            c.execute(text('''UPDATE public.coincidencia_propuesta SET estado_revision='aceptada',revisado_en=CURRENT_TIMESTAMP
                WHERE dni_deportista=:destino AND id_participante_importado IN
                (SELECT id_participante_importado FROM public.participante_importado
                    WHERE dni_deportista_confirmado=:destino)'''),parametros)
            c.execute(text('UPDATE public.fusion_deportista SET dni_deportista=:destino WHERE dni_deportista=:origen'),parametros)
            if c.execute(text('DELETE FROM public.deportista WHERE dni=:origen'),parametros).rowcount!=1:
                raise ConflictoError('La ficha de origen cambió. No se guardó la unión.')
            return dict(dni=destino,trasladados=plan['cantidades'])
    except IntegrityError:
        raise ConflictoError('No se guardó ninguna parte de la unión: hay relaciones incompatibles. Actualiza la comparación.') from None


def unir_en_proveedor(proveedor,*args,**opciones):
    from database.database import crear_engine
    motor=crear_engine(proveedor)
    try:return unir(motor,*args,**opciones)
    finally:motor.dispose()
