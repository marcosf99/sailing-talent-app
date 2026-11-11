"""Copias locales de fuentes PDF, fuera de Git y con nombres por SHA-256.

El almacenamiento local sirve para desarrollo. Un despliegue con disco efímero
necesitará sustituir este adaptador por almacenamiento de objetos persistente.
"""
from pathlib import Path
import os
import tempfile

from services import importaciones
from services.deportistas import ValidacionError
from services.extraccion_clasificaciones import validar_pdf


CARPETA_DOCUMENTOS = Path(__file__).resolve().parents[1] / '.local' / 'importaciones'


def guardar_fuente(contenido, carpeta=None):
    validar_pdf(contenido)
    huella = importaciones.calcular_huella(contenido)
    raiz = Path(carpeta) if carpeta is not None else CARPETA_DOCUMENTOS
    raiz.mkdir(parents=True, exist_ok=True, mode=0o700)
    destino = raiz / (huella + '.pdf')
    if destino.is_symlink():
        raise ValidacionError('La referencia local del documento no es válida.')
    if destino.exists():
        if importaciones.calcular_huella(destino.read_bytes()) != huella:
            raise ValidacionError('La copia almacenada del documento no coincide con su huella.')
        return destino.resolve()
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(dir=raiz, suffix='.tmp', delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(contenido)
            salida.flush()
            os.fsync(salida.fileno())
        # El archivo temporal tiene permisos privados; replace evita copias incompletas.
        os.replace(str(temporal), str(destino))
    finally:
        if temporal is not None and temporal.exists():
            temporal.unlink()
    return destino.resolve()


def guardar_borrador_pdf(engine, contenido, campos, filas, carpeta=None):
    """Guarda la fuente inmutable y el borrador, sin crear resultados oficiales.

    Si la base rechaza el guardado, se conserva la fuente para reintentar. Nunca se
    elimina un archivo compartido por otras importaciones del mismo documento.
    """
    validar_pdf(contenido)
    huella = importaciones.calcular_huella(contenido)
    referencia = (Path(carpeta) if carpeta is not None else CARPETA_DOCUMENTOS) / (huella + '.pdf')
    metadatos = {**campos, 'tipo_fuente': 'pdf', 'huella_documento': huella,
                 'referencia_documento': str(referencia.resolve())}
    importaciones.validar_importacion(metadatos)
    guardar_fuente(contenido, carpeta)
    return importaciones.crear_borrador(engine, metadatos, filas)


def guardar_en_proveedor(proveedor, contenido, campos, filas):
    from database.database import crear_engine
    motor = crear_engine(proveedor)
    try:
        return guardar_borrador_pdf(motor, contenido, campos, filas)
    finally:
        motor.dispose()
