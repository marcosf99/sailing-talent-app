"""Marcas de clase sobre curvas antropométricas; no crea mediciones."""
import altair as alt
import pandas as pd

from services import transiciones


def marcas(persona, unidades, fecha, etiqueta):
    nacimiento = persona.get('fecha_nacimiento')
    return [{'Regatista': etiqueta, 'Fecha': r['fecha'], 'Clase': r['clase'],
             'Edad al inicio': transiciones.edad_texto(nacimiento, r['fecha']),
             'Edad (meses)': transiciones.edad_meses(nacimiento, r['fecha']),
             'Etiqueta': r['clase']}
            for r in transiciones.incorporaciones(unidades, fecha, nacimiento)]


def con_clases(grafico, filas, *, por_edad=False, etiquetas=None):
    filas = [r for r in filas if not por_edad or r['Edad (meses)'] is not None]
    if not filas:
        return grafico
    campo = 'Edad (meses):Q' if por_edad else 'Fecha:T'
    grupos = {}
    for r in filas:
        # Un mismo deportista puede incorporarse a varias clases el mismo día.
        clave = (r['Regatista'], r['Fecha'])
        if clave not in grupos:
            grupos[clave] = {**r, 'Clases': []}
        grupos[clave]['Clases'].append(r['Clase'])
    ordenadas = sorted(grupos.values(), key=lambda r: (r['Fecha'], r['Regatista']))
    for i, r in enumerate(ordenadas):
        r['Clase'] = ' / '.join(sorted(set(r['Clases'])))
        r['Etiqueta'] = r['Clase']
        r['Carril'] = i % 3
    marco = pd.DataFrame(ordenadas)
    color = (alt.Color('Regatista:N', scale=alt.Scale(domain=etiquetas, scheme='tableau10'))
             if etiquetas else alt.value('#e69f00'))
    tooltip = ['Regatista:N', 'Clase:N', alt.Tooltip('Fecha:T', title='Inicio registrado', format='%d/%m/%Y'), 'Edad al inicio:N']
    reglas = alt.Chart(marco).mark_rule(strokeDash=[5, 4], opacity=0.7).encode(x=campo, color=color, tooltip=tooltip)
    salida = grafico + reglas
    for carril in range(3):
        datos = marco[marco['Carril'] == carril]
        if not datos.empty:
            textos = alt.Chart(datos).mark_text(align='left', baseline='top', dx=5, fontSize=11, limit=170).encode(
                x=campo, y=alt.value(8+15*carril), text='Etiqueta:N', color=color, tooltip=tooltip)
            salida += textos
    return salida
