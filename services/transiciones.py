"""Transiciones observadas: primeras entradas, sin inferir abandono ni éxito."""
from calendar import monthrange
from collections import defaultdict
from datetime import date


MEDIDAS = {'altura': 'Altura (cm)', 'peso': 'Peso (kg)',
           'envergadura': 'Envergadura (cm)', 'porcentaje_graso': 'Grasa corporal (%)'}


def incorporaciones(unidades, fecha, nacimiento=None):
    """Primer inicio por clase adicional, sin convertir un cambio de equipo en cambio de clase.

    No presupone la salida de otras clases. Las clases iniciales (incluso varias
    en el mismo día) son la base, y no se presentan como un cambio.
    """
    primeras = {}
    for u in unidades:
        dia = u['fecha_inicio']
        if dia > fecha or (nacimiento and dia < nacimiento):
            continue
        clase = u['clase']
        if clase not in primeras or dia < primeras[clase]:
            primeras[clase] = dia
    inicial = min(primeras.values(), default=None)
    return [{'fecha': dia, 'clase': clase} for clase, dia in sorted(
        primeras.items(), key=lambda par: (par[1], par[0])) if dia != inicial]


def edad_meses(nacimiento, fecha):
    if nacimiento is None or fecha < nacimiento:
        return None
    return (fecha.year-nacimiento.year)*12 + fecha.month-nacimiento.month - (fecha.day<nacimiento.day)


def edad_texto(nacimiento, fecha):
    meses = edad_meses(nacimiento, fecha)
    if meses is None:
        return 'Sin nacimiento válido'
    anos, resto = divmod(meses, 12)
    return f"{anos} {'año' if anos == 1 else 'años'} y {resto} {'mes' if resto == 1 else 'meses'}"


def desplazar_meses(fecha, meses):
    anio, mes = divmod(fecha.year*12+fecha.month-1+meses, 12)
    return date(anio, mes+1, min(fecha.day, monthrange(anio, mes+1)[1]))


def preparar(datos, fecha):
    """Una ficha por persona; nunca una fila por compañero o por medición."""
    if type(fecha) is not date:
        raise ValueError('Indica una fecha válida.')
    personas = {}
    for u in datos['unidades']:
        if u['fecha_inicio'] > fecha:
            continue
        dni = u['dni']
        if dni not in personas:
            personas[dni] = {**{k: u.get(k) for k in (
                'dni', 'nombre', 'apellidos', 'sexo', 'fecha_nacimiento',
                'id_club', 'club', 'id_federacion', 'federacion')},
                'unidades': [], 'resultados': [], 'mediciones': [], 'informes': []}
        if u['id_unidad'] not in {r['id_unidad'] for r in personas[dni]['unidades']}:
            personas[dni]['unidades'].append(dict(u))
    for tipo in ('resultados', 'mediciones', 'informes'):
        vistos = set()
        for r in datos[tipo]:
            dni = r['dni']
            fin = r.get('fecha_fin') if tipo == 'resultados' else r['fecha']
            if dni not in personas or fin is None or fin > fecha:
                continue
            nacimiento = personas[dni]['fecha_nacimiento']
            inicio = r['fecha_inicio'] if tipo == 'resultados' else r['fecha']
            if nacimiento and inicio < nacimiento:
                continue
            identidad = ((dni, r['id_competicion']) if tipo == 'resultados' else
                         (dni, r['id_registro' if tipo == 'mediciones' else 'id_informe']))
            if identidad not in vistos:
                personas[dni][tipo].append(dict(r))
                vistos.add(identidad)
    return list(personas.values())


def detectar(persona, fecha, criterio='regatas'):
    """Pares consecutivos de primeras entradas en clases distintas.

    Las clases que empiezan el mismo día no tienen orden conocido: se omiten
    los pares adyacentes a esa etapa, sin saltarla para inventar una transición.
    Los retornos a clases conocidas no son nuevas incorporaciones.
    """
    if criterio not in ('regatas', 'unidades'):
        raise ValueError('Criterio de referencia no válido.')
    primeras = {}
    filas = persona['resultados' if criterio == 'regatas' else 'unidades']
    for r in filas:
        inicio = r['fecha_inicio']
        if inicio > fecha or (criterio == 'regatas' and r['fecha_fin'] > fecha):
            continue
        if persona.get('fecha_nacimiento') and inicio < persona['fecha_nacimiento']:
            continue
        clave = r['id_clase']
        if clave not in primeras or inicio < primeras[clave]['fecha_inicio']:
            primeras[clave] = r
    etapas = defaultdict(list)
    for r in primeras.values():
        etapas[r['fecha_inicio']].append(r)
    fechas = sorted(etapas)
    salida = []
    for anterior, actual in zip(fechas, fechas[1:]):
        if len(etapas[anterior]) != 1 or len(etapas[actual]) != 1:
            continue
        origen, destino = etapas[anterior][0], etapas[actual][0]
        meses = edad_meses(persona.get('fecha_nacimiento'), actual)
        salida.append({
            'dni': persona['dni'], 'origen': origen['clase'], 'destino': destino['clase'],
            'id_origen': origen['id_clase'], 'id_destino': destino['id_clase'],
            'fecha': actual, 'fecha_origen': anterior, 'criterio': criterio,
            'edad_meses': meses, 'edad': meses/12 if meses is not None else None,
            'origen_abierto': any(u['id_clase'] == origen['id_clase']
                and u['fecha_inicio'] <= actual
                and (u['fecha_fin'] is None or u['fecha_fin'] >= actual)
                for u in persona['unidades']),
            'regatas_origen_posteriores': len({r['id_competicion'] for r in persona['resultados']
                if r['id_clase'] == origen['id_clase'] and actual <= r['fecha_inicio']
                and r['fecha_fin'] <= fecha}),
        })
    return salida, sum(len(v) > 1 for v in etapas.values())


def contexto(persona, evento):
    """Último valor conocido por indicador hasta la referencia; sin interpolar."""
    salida = []
    for campo, etiqueta in MEDIDAS.items():
        candidatos = [r for r in persona['mediciones']
                      if r['fecha'] <= evento['fecha'] and r.get(campo) is not None
                      and (persona.get('fecha_nacimiento') is None
                           or r['fecha'] >= persona['fecha_nacimiento'])]
        r = max(candidatos, key=lambda r: (r['fecha'], r.get('id_registro', 0)), default=None)
        salida.append({'Indicador': etiqueta, 'Valor': float(r[campo]) if r else None,
                       'Fecha de medición': r['fecha'] if r else None,
                       'Antigüedad (días)': (evento['fecha']-r['fecha']).days if r else None})
    return salida


def entorno(persona, evento, fecha, meses=12, nivel=None):
    if type(meses) is not int or not 1 <= meses <= 36:
        raise ValueError('La ventana debe ser de 1 a 36 meses.')
    inicio = desplazar_meses(evento['fecha'], -meses)
    fin = min(fecha, desplazar_meses(evento['fecha'], meses))
    salida = {}
    for tipo in ('resultados', 'mediciones', 'informes'):
        filas = []
        for r in persona[tipo]:
            dia = r['fecha_inicio'] if tipo == 'resultados' else r['fecha']
            termino = r['fecha_fin'] if tipo == 'resultados' else dia
            if not inicio <= dia <= fin or termino > fecha:
                continue
            if persona.get('fecha_nacimiento') and dia < persona['fecha_nacimiento']:
                continue
            if tipo == 'resultados' and nivel and r.get('nivel') != nivel:
                continue
            filas.append({**r, 'dias': (dia-evento['fecha']).days,
                          'meses': (dia-evento['fecha']).days/30.4375})
        salida[tipo] = sorted(filas, key=lambda r: (r['dias'], r.get('id_registro', r.get('id_informe', r.get('id_competicion', 0)))))
    return salida


def resumen_resultados(persona, evento, filas):
    """Resumen por clase y nivel; no mezcla puntos ni flotas de tamaño desconocido."""
    grupos = defaultdict(dict)
    for r in filas:
        etapa = ('Antes · origen' if r['dias'] < 0 and r['id_clase'] == evento['id_origen'] else
                 'Desde referencia · destino' if r['dias'] >= 0 and r['id_clase'] == evento['id_destino'] else None)
        if etapa:
            grupos[(etapa, r['clase'], r.get('nivel') or 'Sin nivel')][r['id_competicion']] = r
    salida = []
    for (etapa, clase, nivel), registros in sorted(grupos.items()):
        puestos = [r['posicion_general'] for r in registros.values() if r.get('posicion_general') is not None]
        salida.append({'Regatista': f"{persona['nombre']} {persona['apellidos']}", 'Etapa': etapa,
                       'Clase': clase, 'Nivel': nivel, 'Participaciones': len(registros),
                       'Mejor puesto registrado': min(puestos) if puestos else None})
    return salida
