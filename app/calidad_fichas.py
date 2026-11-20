"""Nacimiento prioritario y acceso directo para completar una ficha."""
from datetime import date
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from app import datos_pendientes
from services import deportistas


def editar_nacimiento(proveedor,dni,anterior=None,prefijo='calidad'):
    st.caption('Introduce la fecha completa confirmada. No se deduce de la categoría ni del año de competición.')
    with st.form(f'{prefijo}_nacimiento_{proveedor}_{dni}'):
        nacimiento=st.date_input('Fecha de nacimiento confirmada',value=anterior,
            min_value=date(1900,1,1),max_value=date.today(),format='DD/MM/YYYY')
        guardar=st.form_submit_button('Guardar fecha de nacimiento',type='primary')
    if not guardar:
        return
    try:
        deportistas.guardar_nacimiento_en_proveedor(proveedor,dni,nacimiento,anterior)
    except (deportistas.ValidacionError,deportistas.ConflictoError) as error:
        st.error(str(error));return
    except (SQLAlchemyError,KeyError,OSError):
        st.error('No se pudo confirmar el guardado. Actualiza los datos antes de reintentar.');return
    st.session_state['lecturas']={}
    st.session_state.pop('edad_revisada_'+proveedor,None)
    st.session_state['calidad_guardado']='Fecha de nacimiento guardada. La edad y las consultas se han actualizado.'
    st.rerun()


def mensaje_guardado():
    mensaje=st.session_state.pop('calidad_guardado',None)
    if mensaje:
        st.success(mensaje)


def mostrar(proveedor,motor,lectura):
    st.title('Calidad de fichas')
    st.write('La fecha de nacimiento es prioritaria para estudiar la evolución por edad y comparar trayectorias.')
    st.caption('Completa los datos confirmados por los clubes o federaciones. El DNI puede seguir pendiente sin impedir el seguimiento.')
    mensaje_guardado()
    datos_pendientes.mostrar(proveedor,motor,lectura,priorizar_nacimiento=True,permitir_edicion=True)
    from app import duplicados
    duplicados.mostrar(proveedor,motor,lectura)
