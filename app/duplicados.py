"""Comparación visible y confirmación explícita antes de unir dos fichas."""
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from services import duplicados as servicio


def nombre(f):return f['nombre']+' '+f['apellidos']+' · '+f['dni']


def mostrar(proveedor,motor,lectura):
    with st.expander('Revisar posibles fichas duplicadas'):
        if not st.checkbox('Buscar y revisar duplicados',key='calidad_buscar_duplicados_'+proveedor):
            st.caption('La similitud propone una revisión; nunca une personas automáticamente.');return
        fichas=lectura((proveedor,'catalogo_duplicados'),servicio.catalogo,motor)
        if len(fichas)<2:
            st.info('Se necesitan al menos dos fichas para comparar posibles duplicados.');return
        mapa={f['dni']:f for f in fichas}
        manual=st.checkbox('Elegir dos fichas manualmente',key='calidad_manual_duplicados_'+proveedor)
        if manual:
            texto=st.text_input('Localizar fichas para comparar',key='calidad_texto_duplicados_'+proveedor)
            tokens=servicio.revision.normalizar(texto).split()
            opciones=[f['dni'] for f in fichas if all(t in servicio.revision.normalizar(nombre(f)) for t in tokens)]
            if not opciones:st.info('No se han encontrado fichas con esa búsqueda.');return
            if st.session_state.get('calidad_primera_'+proveedor) not in opciones:
                st.session_state.pop('calidad_primera_'+proveedor,None)
            a=st.selectbox('Primera ficha',opciones,format_func=lambda d:nombre(mapa[d]),key='calidad_primera_'+proveedor)
            # La segunda puede buscarse en el catálogo completo, incluso si cambió el nombre.
            opciones_b=[d for d in mapa if d!=a]
            if st.session_state.get('calidad_segunda_'+proveedor) not in opciones_b:
                st.session_state.pop('calidad_segunda_'+proveedor,None)
            b=st.selectbox('Segunda ficha',opciones_b,format_func=lambda d:nombre(mapa[d]),key='calidad_segunda_'+proveedor)
        else:
            pares=servicio.posibles(fichas)
            if not pares:
                st.info('No hay coincidencias propuestas. Puedes elegir dos fichas manualmente si conoces un duplicado.');return
            if len(pares)==200:st.caption('Se muestran hasta 200 pares. La elección manual permite buscar otras fichas.')
            indices=list(range(len(pares)))
            clave='calidad_par_'+proveedor
            if st.session_state.get(clave) not in indices:st.session_state.pop(clave,None)
            i=st.selectbox('Posible duplicado',indices,key=clave,format_func=lambda i:nombre(mapa[pares[i]['a']])+' ↔ '+nombre(mapa[pares[i]['b']]))
            par=pares[i];a,b=par['a'],par['b']
            st.caption(f"Similitud orientativa: {par['similitud']}. {par['motivos']}")
        por_defecto=b if servicio.provisional(a) and not servicio.provisional(b) else a
        conservar=st.selectbox('Ficha que se conservará',[a,b],index=[a,b].index(por_defecto),
            format_func=lambda d:nombre(mapa[d]),key=f'calidad_conservar_{proveedor}_{a}_{b}')
        retirar=b if conservar==a else a
        try:
            plan=servicio.preparar(motor,retirar,conservar)
        except (servicio.ConflictoError,servicio.ValidacionError) as error:
            st.warning(str(error));return
        except SQLAlchemyError as error:
            codigo=getattr(getattr(error,'orig',None),'sqlstate',None)
            mensaje=str(error).lower()
            if codigo=='42P01' or ('fusion_deportista' in mensaje and 'no such table' in mensaje):
                st.info('Para activar la unión con auditoría, ejecuta sql/migrations/003_fusion_deportistas.sql en esta base. Después pulsa Actualizar datos.')
            else:
                st.error('No se pudo comparar el historial. Comprueba la conexión y pulsa Actualizar datos.')
            return
        etiquetas={'dni':'Identificador','nombre':'Nombre','apellidos':'Apellidos',
            'fecha_nacimiento':'Nacimiento','sexo':'Sexo','id_club':'Club'}
        def valor(f,campo):
            if campo=='id_club':return next((v.get('club') for v in fichas if v['id_club']==f['id_club']),'Sin club') or 'Sin club'
            v=f[campo]
            return v.strftime('%d/%m/%Y') if hasattr(v,'strftime') else (str(v) if v is not None else 'Sin registrar')
        st.dataframe(pd.DataFrame([{'Dato':etiqueta,'Ficha que se conserva':valor(plan['destino'],campo),
            'Ficha que se retira':valor(plan['origen'],campo),'Ficha resultante':valor(plan['ficha_final'],campo)} for campo,etiqueta in etiquetas.items()]),hide_index=True,width='stretch')
        titulos={'registro_antropometrico':'Mediciones','informe':'Informes técnicos','forma_parte':'Pertenencias a equipos',
            'participante_importado':'Apariciones en clasificaciones','coincidencia_propuesta':'Propuestas de identidad',
            'variante_nombre_deportista':'Variantes de nombre','descarte_nombre_deportista':'Descartes de nombre'}
        st.dataframe(pd.DataFrame([{'Historial de la ficha retirada':titulos[t],'Registros que se trasladan':n}
            for t,n in plan['cantidades'].items()]),hide_index=True,width='stretch')
        if plan['resultados']:
            st.dataframe(pd.DataFrame([{'Ficha':nombre(mapa[r['dni_deportista']]),
                'Competición':r['competicion'],'Clase':r['clase'],'Nivel':r['nivel'],
                'Inicio':r['fecha_inicio'],'Puesto general':r['posicion_general'],'Puntos':r['puntos']}
                for r in plan['resultados']]),hide_index=True,width='stretch')
        st.caption('Se conservan el identificador y el nombre de la ficha elegida. Nacimiento, sexo o club vacíos se completan con los de la otra ficha. Los resultados mantienen sus equipos, puestos y puntos originales.')
        for aviso in plan['avisos']:st.info(aviso)
        for bloqueo in plan['bloqueos']:st.warning(bloqueo)
        with st.form(f'calidad_union_{proveedor}_{retirar}_{conservar}_{plan["version"]}'):
            motivo=st.text_area('Motivo y comprobación de la identidad',max_chars=1000,
                help='Explica qué información confirma que las dos fichas son la misma persona.')
            confirmar=st.checkbox('He comprobado que ambas fichas pertenecen a la misma persona y quiero unir sus historiales.')
            guardar=st.form_submit_button('Unir las dos fichas revisadas',disabled=bool(plan['bloqueos']))
        if not guardar:return
        if not confirmar or not motivo.strip():
            st.error('Confirma que es la misma persona y explica el motivo antes de unir las fichas.');return
        try:
            servicio.unir_en_proveedor(proveedor,retirar,conservar,plan['version'],motivo,confirmar=confirmar)
        except (servicio.ValidacionError,servicio.ConflictoError) as error:
            st.error(str(error));return
        except (SQLAlchemyError,KeyError,OSError):
            st.error('No se pudo confirmar la unión. Actualiza los datos antes de reintentar.');return
        st.session_state['lecturas']={}
        st.session_state.pop('edad_revisada_'+proveedor,None)
        st.session_state['calidad_guardado']='Fichas unidas. Se ha conservado el historial y una copia de auditoría de los datos anteriores.'
        st.rerun()
