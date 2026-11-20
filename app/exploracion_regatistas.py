"""Información para decidir a quién seguir, con el contexto de cada resultado."""
import pandas as pd
import streamlit as st
from services import seguimiento
from app import candidatos


def mostrar_lista(filas,fecha):
    st.subheader('Explorar regatistas')
    orden=st.selectbox('Ordenar exploración',['Actividad reciente','Participaciones nacionales e internacionales','Nombre','Nacimiento pendiente'],key='consulta_orden')
    def nombre(p):return ((p.get('apellidos') or '').casefold(),p['nombre'].casefold(),p['dni'])
    if orden=='Actividad reciente':
        filas=sorted(filas,key=lambda p:(-(p.get('ultima_regata').toordinal() if p.get('ultima_regata') else 0),nombre(p)))
    elif orden=='Participaciones nacionales e internacionales':
        filas=sorted(filas,key=lambda p:(-((p.get('nacionales') or 0)+(p.get('internacionales') or 0)),nombre(p)))
    elif orden=='Nacimiento pendiente':
        filas=sorted(filas,key=lambda p:(p.get('fecha_nacimiento') is not None,nombre(p)))
    else:
        filas=sorted(filas,key=nombre)
    st.caption(f'{len(filas)} fichas · {sum(p.get("fecha_nacimiento") is None for p in filas)} sin fecha de nacimiento. Selecciona debajo un regatista para abrir su historial.')
    marco=pd.DataFrame([{
        'Regatista':p['nombre']+' '+p['apellidos'],'Club':p.get('club') or 'Sin club',
        'Federación':p.get('federacion') or 'Sin federación',
        'Año nacimiento':p['fecha_nacimiento'].year if p.get('fecha_nacimiento') else None,
        'Edad':candidatos.edad_en_medicion(p.get('fecha_nacimiento'),fecha),
        'Clases activas':p.get('clases_activas') or 'Sin unidad activa',
        'Regatas':p.get('participaciones',0),'Nacionales':p.get('nacionales',0),
        'Internacionales':p.get('internacionales',0),'Mejor nacional':p.get('mejor_nacional'),
        'Mejor internacional':p.get('mejor_internacional'),'Última regata':p.get('ultima_regata'),
    } for p in filas])
    for col in ('Año nacimiento','Regatas','Nacionales','Internacionales','Mejor nacional','Mejor internacional'):
        marco[col]=pd.to_numeric(marco[col],errors='coerce').astype('Int64')
    st.dataframe(marco,hide_index=True,width='stretch')
    st.caption('Los recuentos y mejores puestos abarcan el historial hasta la fecha consultada, también al filtrar por clase activa. Los puestos dependen de la clase y la competición: no son un ranking de talento. Usa el año de nacimiento para comparar edades similares.')
    return filas


def mostrar_resumen(contenido,fecha):
    filas=seguimiento.resumen_deportivo(contenido['resultados'],fecha)
    st.subheader('Resumen deportivo por año, clase y nivel')
    if not filas:
        st.info('Aún no hay resultados para construir un resumen deportivo.');return
    marco=pd.DataFrame(filas).rename(columns=dict(temporada='Año',clase='Clase',nivel='Nivel',
        regatas='Regatas',mejor_puesto='Mejor puesto',podios='Podios',ultima_regata='Última regata'))
    marco['Mejor puesto']=pd.to_numeric(marco['Mejor puesto'],errors='coerce').astype('Int64')
    st.dataframe(marco,hide_index=True,width='stretch')
    st.caption('Año natural de inicio de la regata. No se suman puntos de pruebas distintas ni se compara un puesto autonómico con uno internacional. El historial puede estar incompleto.')
