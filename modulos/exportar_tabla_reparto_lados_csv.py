from datetime import datetime

from bd.basedatos import BaseDatos
from modulos.exportar_tabla_reparto_csv import (
    seleccionar_carpeta_salida,
    obtener_registros_clasificador,
    escribir_csv_clasificador,
    obtener_reparto_completo,
    crear_pdf_resumen_tipo_caja,
    crear_pdf_resumen_lados,
)
from modulos.gestor_grutiep import validar_y_avisar_grutiep

try:
    from modulos.generar_mapa_tipo_caja import crear_mapa_tipo_caja_pdf
except Exception:
    crear_mapa_tipo_caja_pdf = None


def exportar_tablas_reparto_lados(clasificadores_activos, parent=None, validar_grutiep=True):
    """Exporta CSV, resumenes PDF y mapa CLA del reparto por lados."""
    clasificadores = sorted({int(c) for c in clasificadores_activos})
    carpeta_salida = seleccionar_carpeta_salida(parent=parent)

    if carpeta_salida is None:
        return []

    bd = BaseDatos()
    fecha_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")
    fecha_pdf = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    archivos = []
    tiendas_por_clasificador = {}

    try:
        for clasificador in clasificadores:
            registros = obtener_registros_clasificador(bd, clasificador)
            if not registros:
                continue

            ruta = carpeta_salida / f"Tabla_Cla_{clasificador}_{fecha_archivo}.csv"
            escribir_csv_clasificador(ruta, registros)
            archivos.append(ruta)
            tiendas_por_clasificador[clasificador] = {
                registro[1]
                for registro in registros
                if len(registro) > 1 and registro[1] is not None
            }

        # REPARTO_CLASIFICADOR se vacia antes de guardar cada reparto, por lo que
        # aqui solo existen los destinos utilizados en el calculo actual.
        registros_completos = obtener_reparto_completo(bd)
        registros_completos = [
            registro
            for registro in registros_completos
            if int(registro[0]) in clasificadores
        ]

        if registros_completos:
            ruta_tipo = carpeta_salida / f"Resumen_TipoCaja_{fecha_archivo}.pdf"
            crear_pdf_resumen_tipo_caja(ruta_tipo, registros_completos, fecha_pdf)
            archivos.append(ruta_tipo)

            ruta_lados = carpeta_salida / f"Resumen_Lotes_Lados_{fecha_archivo}.pdf"
            crear_pdf_resumen_lados(ruta_lados, registros_completos, fecha_pdf)
            archivos.append(ruta_lados)

            # Igual que en el reparto normal: mapa visual del CLA por TipoCaja.
            if crear_mapa_tipo_caja_pdf is not None:
                try:
                    archivos_mapa = crear_mapa_tipo_caja_pdf(
                        carpeta_salida,
                        registros_completos,
                        fecha_archivo,
                        fecha_pdf,
                    )
                    archivos.extend(archivos_mapa or [])
                except Exception as error:
                    # La exportacion CSV/PDF principal no debe perderse por un
                    # problema aislado al generar el mapa.
                    print()
                    print("AVISO: no se pudo generar el mapa del CLA.")
                    print(error)
                    print()

        # La validacion previa al calculo puede desactivar este aviso posterior.
        if validar_grutiep and tiendas_por_clasificador:
            try:
                validar_y_avisar_grutiep(
                    bd,
                    tiendas_por_clasificador,
                    parent=parent,
                )
            except Exception as error:
                print()
                print("AVISO: no se pudo realizar la validacion GRUTIEP.")
                print(error)
                print()

        return archivos
    finally:
        try:
            bd.cerrar()
        except Exception:
            pass
