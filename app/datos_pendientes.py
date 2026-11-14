"""Organiza los datos personales por completar; no envía solicitudes externas."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from services import deportistas


def filtrar(filas, federacion=None, club=None, dato='Cualquiera'):
    return [f for f in filas
        if (federacion is None or (f['id_federacion'] or -1)==federacion)
        and (club is None or (f['id_club'] or -1)==club)
        and (dato=='Cualquiera' or dato=='Sin DNI' and f['sin_dni']
             or dato=='Sin fecha de nacimiento' and f['sin_nacimiento']
             or dato=='Ambos datos' and f['sin_dni'] and f['sin_nacimiento'])]


def agrupar(filas):
    grupos = {}
    for f in filas:
        g = grupos.setdefault((f['id_federacion'],f['id_club']),dict(
            Federación=f['federacion'] or 'Sin federación', Club=f['club'] or 'Sin club',
            Deportistas=0, **{'Sin DNI':0,'Sin nacimiento':0}))
        g['Deportistas']+=1; g['Sin DNI']+=int(f['sin_dni']); g['Sin nacimiento']+=int(f['sin_nacimiento'])
    return list(grupos.values())


def mostrar(proveedor,motor,lectura):
    with st.expander('Datos personales pendientes · por federación y club',expanded=True):
        st.caption('Todas las fichas de la base seleccionada, no solo esta clasificación. '
                   'TEMP-, TEST-, STDEMO y PRUEBA identifican documentos provisionales o de prueba. '
                   'Puedes completar los datos en Gestión de deportistas → Editar ficha. No se envían solicitudes desde esta pantalla.')
        try:
            filas = lectura((proveedor,'datos_personales_pendientes'),deportistas.datos_pendientes,motor)
        except (SQLAlchemyError,KeyError,OSError,ValueError):
            st.warning('No se pudieron consultar los datos personales pendientes. Puedes continuar con la revisión.')
            return
        if not filas:
            st.info('No hay fichas con documento provisional o fecha de nacimiento pendiente.')
            return
        federaciones = {f['id_federacion'] or -1:f['federacion'] or 'Sin federación' for f in filas}
        clave_fed = 'pendientes_fed_'+proveedor
        if st.session_state.get(clave_fed) not in federaciones:st.session_state.pop(clave_fed,None)
        fed = st.selectbox('Federación de los datos pendientes',[None]+list(federaciones),
            format_func=lambda v:'Todas las federaciones' if v is None else federaciones[v],key=clave_fed)
        disponibles = filtrar(filas,fed)
        clubes = {f['id_club'] or -1:f['club'] or 'Sin club' for f in disponibles}
        clave = 'pendientes_club_'+proveedor
        if st.session_state.get(clave) not in clubes:st.session_state.pop(clave,None)
        club = st.selectbox('Club de los datos pendientes',[None]+list(clubes),
            format_func=lambda v:'Todos los clubes' if v is None else clubes[v],key=clave)
        dato = st.selectbox('Dato pendiente',['Cualquiera','Sin DNI','Sin fecha de nacimiento','Ambos datos'],key='pendientes_dato_'+proveedor)
        elegidas = filtrar(filas,fed,club,dato)
        st.caption(f'{len(elegidas)} deportistas · {sum(f["sin_dni"] for f in elegidas)} sin DNI · {sum(f["sin_nacimiento"] for f in elegidas)} sin fecha de nacimiento. Una ficha puede tener ambos datos pendientes.')
        if not elegidas:
            st.info('No hay fichas con estos filtros.'); return
        st.dataframe(pd.DataFrame(agrupar(elegidas)),hide_index=True,width='stretch')
        st.dataframe(pd.DataFrame([{'Identificador actual':f['dni'],'Regatista':f['nombre']+' '+f['apellidos'],
            'Federación':f['federacion'] or 'Sin federación','Club':f['club'] or 'Sin club',
            'DNI pendiente':'Sí' if f['sin_dni'] else 'No',
            'Nacimiento pendiente':'Sí' if f['sin_nacimiento'] else 'No'} for f in elegidas]),hide_index=True,width='stretch')
