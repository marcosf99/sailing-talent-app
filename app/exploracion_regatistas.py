"""Información para decidir a quién seguir, con el contexto de cada resultado."""
import pandas as pd
import streamlit as st
from services import seguimiento
from app import candidatos


def mostrar_lista(filas,fecha,*,orden='Resultados ponderados',desde=None,clases=()):
    st.subheader('Explorar regatistas')
    # La base ordena antes del límite; no reordenar aquí un subconjunto alfabético.
    with st.expander('Cómo se ordenan los resultados'):
        st.write('Cada resultado recibe 1.000 puntos de índice si es internacional, 100 si es nacional y 10 si es autonómico, divididos entre la raíz cuadrada del puesto general. Los tres mejores aportan el 100 %, 50 % y 25 % de su valor.')
        st.write('En empate se compara el mejor resultado individual, después el mejor puesto internacional, nacional y autonómico, y finalmente la fecha más reciente. Si persiste, se usa un identificador estable sin atribuir superioridad deportiva.')
        st.caption('Ejemplo: un 4.º internacional aporta 500; un 1.º nacional, 100; un 1.º autonómico, 10. No se suman los puntos publicados por regatas distintas. Las participaciones sin puesto no puntúan.')
    contexto=('Desde '+desde.strftime('%d/%m/%Y')) if desde else 'Todo el historial'
    st.caption(contexto+' hasta '+fecha.strftime('%d/%m/%Y')+' · '+(', '.join(clases) if clases else 'Todas las clases')+'.')
    st.caption(f'{len(filas)} fichas · {sum(p.get("fecha_nacimiento") is None for p in filas)} sin fecha de nacimiento. Selecciona debajo un regatista para abrir su historial.')
    marco=pd.DataFrame([{
        'Regatista':p['nombre']+' '+p['apellidos'],
        'Índice de resultados':round(float(p.get('indice_resultados') or 0),2),
        'Resultados valorados':p.get('resultados_valorados',0),'Club':p.get('club') or 'Sin club',
        'Federación':p.get('federacion') or 'Sin federación',
        'Año nacimiento':p['fecha_nacimiento'].year if p.get('fecha_nacimiento') else None,
        'Edad':candidatos.edad_en_medicion(p.get('fecha_nacimiento'),fecha),
        'Clases de su trayectoria':p.get('clases_navegadas') or p.get('clases_activas') or 'Sin trayectoria registrada',
        'Clases activas':p.get('clases_activas') or 'Sin unidad activa',
        'Regatas':p.get('participaciones',0),'Nacionales':p.get('nacionales',0),
        'Internacionales':p.get('internacionales',0),'Mejor autonómico':p.get('mejor_autonomico'),'Mejor nacional':p.get('mejor_nacional'),
        'Mejor internacional':p.get('mejor_internacional'),'Última regata':p.get('ultima_regata'),
    } for p in filas])
    for col in ('Año nacimiento','Regatas','Nacionales','Internacionales','Mejor nacional','Mejor internacional','Mejor autonómico','Resultados valorados'):
        marco[col]=pd.to_numeric(marco[col],errors='coerce').astype('Int64')
    detalle=st.checkbox('Mostrar todas las columnas deportivas',key='consulta_detalle_deportivo')
    columnas=None if detalle else ['Regatista','Índice de resultados','Año nacimiento','Club',
        'Clases de su trayectoria','Clases activas','Mejor internacional','Mejor nacional','Regatas']
    st.dataframe(marco,hide_index=True,width='stretch',column_order=columnas,
        column_config={'Índice de resultados':st.column_config.NumberColumn(format='%.2f',
            help='Tres mejores resultados ponderados por nivel y puesto dentro del periodo y las clases seleccionados.')})
    st.caption('El índice, los recuentos y los mejores puestos usan el periodo y las clases seleccionados. Cada competición cuenta una vez por regatista; en dobles ambos miembros comparten el resultado. Es un orden de resultados registrados, no una estimación del talento: no ajusta por edad, tamaño de flota ni calidad de participantes. Usa los años de nacimiento para comparar edades similares.')
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
