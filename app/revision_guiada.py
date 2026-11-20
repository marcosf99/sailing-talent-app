"""Una lista por embarcación y una cola de excepciones; sin escrituras al abrir."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from services import revision_lotes as servicio, resultados_importados as resultados
from services.deportistas import ValidacionError,ConflictoError


def _ir(clave,destino):st.session_state[clave]=destino


def _guardar(proveedor,operacion,identificador,decisiones,version,campos,al_guardar):
    try:
        salida=servicio.guardar_en_proveedor(proveedor,operacion,identificador,decisiones,version,campos)
    except (ValidacionError,ConflictoError) as error:
        st.error(str(error));return
    except (SQLAlchemyError,KeyError,OSError):
        st.error('No se pudo confirmar el guardado. Pulsa Actualizar revisión antes de reintentar.');return
    if operacion=='clubes':
        mensaje=f"Clubes confirmados para {salida['participantes']} participantes. Las propuestas se han actualizado."
    else:
        mensaje=f"{salida['resultados_incorporados']} resultados guardados · {salida['vinculados']} fichas vinculadas · {salida['creados']} fichas nuevas."
        if salida['pendientes']:mensaje+=f" Quedan {salida['pendientes']} embarcaciones para revisar o guardar."
    al_guardar(mensaje)


def mostrar(proveedor,motor,lectura,revision,clubes,campos,al_guardar):
    """Devuelve los IDs del único caso que requiere el formulario individual."""
    imp=revision['importacion'];ident=imp['id_importacion']
    prefijo=f'revision_guiada_{proveedor}_{ident}'
    version=resultados.version_resultados(revision)
    try:
        resumen=lectura((proveedor,'revision_lotes',ident,version),servicio.cargar_resumen,motor,ident)
    except (SQLAlchemyError,KeyError,OSError,ValidacionError):
        st.error('No se pudo preparar la revisión. Pulsa Actualizar revisión.');return None
    with st.expander('Ajustar identificación de fichas nuevas'):
        umbral=st.number_input('Umbral de similitud para fichas nuevas',min_value=.65,max_value=.85,
            value=.75,step=.01,format='%.2f',key=prefijo+'_umbral')
        st.caption('Se mantiene el criterio 0,75. Las coincidencias ambiguas, nombres abreviados y equipos incompletos siguen pendientes.')
        if umbral>.75:st.warning('Un umbral más alto permite más altas, pero aumenta el riesgo de duplicados.')
    plan=servicio.plan_revision_rapida(revision,resumen,umbral,campos)
    incorporadas=sum(f['estado']=='importada' for f in revision['filas'])
    a,b,c=st.columns(3)
    a.metric('Resultados incorporados',incorporadas)
    b.metric('Preparados para guardar',len(plan['preparadas']))
    c.metric('Necesitan revisión',len(plan['pendientes']))
    if imp['estado']=='completada':
        st.success('Clasificación completada. Los resultados están disponibles en las fichas de los regatistas.');return None
    if imp['estado'] not in ('recibida','extraida','en_revision','parcialmente_importada'):
        st.info('Esta clasificación no admite cambios de identidad.');return None
    if plan['error_regata']:
        st.info('Completa los datos de la regata antes de guardar: '+plan['error_regata'])
    clave=prefijo+'_ruta'
    ruta=st.session_state.get(clave,'resumen')
    if ruta=='resumen':
        st.subheader('Resultados preparados')
        st.caption('Revisa la propuesta y deja marcadas las embarcaciones que quieres incorporar. El botón vincula las fichas existentes, crea las nuevas y guarda sus resultados juntos.')
        filas=plan['preparadas']
        if filas:
            marco=pd.DataFrame([{'Guardar':True,'Puesto':f['puesto'],'Participantes en la clasificación':f['nombres'],
                'Vincular a fichas existentes':f['fichas_existentes'] or '—',
                'Crear fichas nuevas':f['fichas_nuevas'] or '—','Puntos':f['puntos']}
                for f in filas],index=[f['fila'] for f in filas])
            editado=st.data_editor(marco,hide_index=True,width='stretch',num_rows='fixed',
                disabled=[col for col in marco if col!='Guardar'],key=prefijo+'_preparadas_'+plan['version'][:12],
                column_config={'Guardar':st.column_config.CheckboxColumn('Guardar')})
            elegidas=[int(i) for i,r in editado.iterrows() if r['Guardar']==True]
            st.caption('Las fichas nuevas reciben un identificador provisional TEMP-. DNI y nacimiento desconocidos siguen pendientes, sin impedir el alta.')
        else:
            elegidas=[]
            st.info('No hay resultados preparados todavía. Resuelve los casos pendientes para continuar.')
        if st.button(f"Guardar {len(elegidas)} {'resultado preparado' if len(elegidas)==1 else 'resultados preparados'}",type='primary',
                disabled=not elegidas or bool(plan['error_regata']),key=prefijo+'_guardar'):
            _guardar(proveedor,'revision_rapida',ident,dict(filas=elegidas,umbral=umbral,version_plan=plan['version']),
                resumen['version'],campos,al_guardar)
        if plan['pendientes']:
            st.button(f"Resolver {len(plan['pendientes'])} {'caso pendiente' if len(plan['pendientes'])==1 else 'casos pendientes'}",on_click=_ir,args=(clave,'pendientes'),key=prefijo+'_pendientes')
            st.caption('Los casos pendientes quedan fuera del guardado. No bloquean las demás embarcaciones.')
        return None
    st.button('Volver al resumen',on_click=_ir,args=(clave,'resumen'),key=prefijo+'_volver')
    st.subheader('Resolver casos pendientes')
    if not plan['pendientes']:
        st.success('No quedan casos pendientes. Vuelve al resumen para guardar los resultados preparados.');return None
    casos={p['fila']:p for p in plan['pendientes']}
    clave_caso=prefijo+'_caso'
    if st.session_state.get(clave_caso) not in casos:st.session_state.pop(clave_caso,None)
    fila=st.selectbox('Caso que quieres resolver',list(casos),key=clave_caso,
        format_func=lambda i:f"Puesto {casos[i]['puesto']} · {casos[i]['nombres'] or 'Faltan participantes'}")
    caso=casos[fila]
    personas={p['id_participante_importado']:p for p in revision['participantes']}
    grupos=[g for g in resumen['grupos_club'] if any(p['id_fila']==fila for p in g['participantes'])]
    if grupos:
        st.write('Para crear fichas nuevas, identifica su club. La misma decisión se aplicará a las demás apariciones con ese texto. Si vas a vincular una ficha existente, puedes continuar con su identidad debajo.')
        etiquetas={c['id_club']:c['nombre']+' · '+c['federacion'] for c in clubes}
        inversa={v:k for k,v in etiquetas.items()}
        marco=pd.DataFrame([{'Club en el documento':' / '.join(g['textos']),
            'Club identificado':etiquetas.get(g['id_club_propuesto'],'Dejar pendiente'),
            'Participantes':len(g['participantes'])} for g in grupos],index=[g['normalizado'] for g in grupos])
        editado=st.data_editor(marco,hide_index=True,width='stretch',num_rows='fixed',
            disabled=['Club en el documento','Participantes'],key=prefijo+'_clubes_'+resumen['version'][:12]+'_'+str(fila),
            column_config={'Club identificado':st.column_config.SelectboxColumn('Club identificado',options=['Dejar pendiente']+list(inversa))})
        recordar=st.checkbox('Recordar estas equivalencias para próximas clasificaciones',value=True,key=prefijo+'_recordar_clubes')
        decisiones=[dict(normalizado=g['normalizado'],id_club=inversa[editado.loc[g['normalizado'],'Club identificado']],
            recordar=recordar,version=g['version']) for g in grupos if editado.loc[g['normalizado'],'Club identificado'] in inversa]
        if st.button('Guardar equivalencias de clubes',disabled=not decisiones,key=prefijo+'_guardar_clubes'):
            _guardar(proveedor,'clubes',ident,decisiones,None,None,al_guardar)
        st.caption('Puedes dejar sin identificar los clubes dudosos. Solo se guardan las equivalencias indicadas.')
    st.info(caso['motivo'])
    pendientes=[i for i in caso['participantes'] if not personas[i]['dni_deportista_confirmado']]
    return dict(fila=fila,participantes=pendientes or caso['participantes'])
