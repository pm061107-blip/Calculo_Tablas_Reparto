import copy
import os
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

from bd.basedatos import BaseDatos


TIPO_NUEVA_400 = "4_Nueva_40"
TIPO_USADA_400 = "3_Usada_40"
TIPOS_400_VALIDOS = {TIPO_NUEVA_400, TIPO_USADA_400}


class GestorTipoCajaPais:
    """Analiza y actualiza el maestro TipoCajaPais de forma transaccional.

    La familia de caja se obtiene reproduciendo el inicio del procesamiento de
    ESTAREPP: TipoCajaInicial por tienda y, a continuacion, homologacion con
    TiposDeCaja. TipoCajaPais no participa en el diagnostico para evitar una
    conversion circular.
    """

    def __init__(self, conexion=None, archivo_configuracion=None):
        self._bd_propia = None
        if conexion is None:
            self._bd_propia = BaseDatos()
            conexion = self._bd_propia.conexion
        self.conexion = conexion

        if archivo_configuracion is None:
            archivo_configuracion = (
                Path(__file__).resolve().parent.parent
                / "datos_iniciales"
                / "Configuracion.xlsx"
            )
        self.archivo_configuracion = Path(archivo_configuracion)

    # ---------------------------------------------------------
    # Normalizacion
    # ---------------------------------------------------------
    @staticmethod
    def normalizar_pais(valor):
        return " ".join(str(valor or "").strip().upper().split())

    @staticmethod
    def normalizar_tipo(valor):
        return str(valor or "").strip()

    @staticmethod
    def _clave_tienda(valor):
        try:
            return int(float(valor))
        except Exception:
            texto = str(valor or "").strip()
            return texto if texto else None

    @classmethod
    def familia_tipo(cls, tipo_caja):
        clave = cls.normalizar_tipo(tipo_caja).upper()
        if clave in {"1_NUEVA_30", "4_NUEVA_40"}:
            return "NUEVA"
        if clave in {"2_REUTILIZADA_30", "3_USADA_40"}:
            return "USADA"
        return None

    # ---------------------------------------------------------
    # Maestros de origen
    # ---------------------------------------------------------
    def _cargar_homologacion(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT TipoGenerico, TipoCaja FROM TiposDeCaja")

        homologacion = {}
        for tipo_generico, tipo_caja in cursor.fetchall():
            clave = self.normalizar_tipo(tipo_generico).upper()
            destino = self.normalizar_tipo(tipo_caja)
            if clave:
                homologacion[clave] = destino

        # Identidades defensivas para instalaciones donde el maestro no las
        # incluya expresamente.
        for tipo in (
            "1_Nueva_30",
            "2_Reutilizada_30",
            "3_Usada_40",
            "4_Nueva_40",
        ):
            homologacion.setdefault(tipo.upper(), tipo)

        return homologacion

    def _cargar_pais_por_tienda(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT Tienda, Pais FROM Tiendas_Web")

        resultado = {}
        for tienda, pais in cursor.fetchall():
            clave_tienda = self._clave_tienda(tienda)
            pais_normalizado = self.normalizar_pais(pais)
            if clave_tienda is None or not pais_normalizado:
                continue
            # Igual que ProcesarESTAREPP: si aparece repetida, prevalece la
            # ultima fila cargada en el maestro.
            resultado[clave_tienda] = pais_normalizado
        return resultado

    def _cargar_tipo_inicial_por_tienda(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT Tienda, TipoCajaInicial FROM TipoCajaInicial")

        resultado = {}
        for tienda, tipo in cursor.fetchall():
            clave_tienda = self._clave_tienda(tienda)
            if clave_tienda is None:
                continue
            resultado[clave_tienda] = self.normalizar_tipo(tipo)
        return resultado

    # ---------------------------------------------------------
    # Diagnostico de familia por pais
    # ---------------------------------------------------------
    def analizar_paises(self, paises):
        paises_ordenados = []
        vistos = set()
        for pais in paises or []:
            clave = self.normalizar_pais(pais)
            if clave and clave not in vistos:
                vistos.add(clave)
                paises_ordenados.append(clave)

        homologacion = self._cargar_homologacion()
        pais_por_tienda = self._cargar_pais_por_tienda()
        tipo_por_tienda = self._cargar_tipo_inicial_por_tienda()

        conteos = {
            pais: Counter()
            for pais in paises_ordenados
        }
        ejemplos = {
            pais: defaultdict(list)
            for pais in paises_ordenados
        }
        tipos_no_homologados = {
            pais: Counter()
            for pais in paises_ordenados
        }
        sin_tipo = Counter()

        seleccion = set(paises_ordenados)
        for tienda, tipo_inicial in tipo_por_tienda.items():
            pais = pais_por_tienda.get(tienda, "")
            if pais not in seleccion:
                continue

            tipo_texto = self.normalizar_tipo(tipo_inicial)
            if not tipo_texto:
                sin_tipo[pais] += 1
                if len(ejemplos[pais]["SIN_TIPO"]) < 10:
                    ejemplos[pais]["SIN_TIPO"].append(tienda)
                continue

            tipo_homologado = homologacion.get(tipo_texto.upper(), tipo_texto)
            familia = self.familia_tipo(tipo_homologado)
            if familia is None:
                tipos_no_homologados[pais][tipo_texto] += 1
                if len(ejemplos[pais]["NO_HOMOLOGADO"]) < 10:
                    ejemplos[pais]["NO_HOMOLOGADO"].append(tienda)
                continue

            conteos[pais][familia] += 1
            if len(ejemplos[pais][familia]) < 10:
                ejemplos[pais][familia].append(tienda)

        resultados = []
        for pais in paises_ordenados:
            nuevas = int(conteos[pais].get("NUEVA", 0))
            usadas = int(conteos[pais].get("USADA", 0))
            no_homologados = dict(tipos_no_homologados[pais])

            if nuevas > 0 and usadas > 0:
                estado = "ERROR_COHERENCIA"
                tipo_400 = ""
                descripcion = "El pais contiene tiendas NUEVA y USADA. No se admite un pais mixto."
            elif no_homologados:
                estado = "ERROR_TIPO_NO_HOMOLOGADO"
                tipo_400 = ""
                descripcion = "Hay tipos iniciales sin homologacion valida."
            elif nuevas > 0:
                estado = "OK"
                tipo_400 = TIPO_NUEVA_400
                descripcion = "Familia NUEVA: se guardara como " + TIPO_NUEVA_400 + "."
            elif usadas > 0:
                estado = "OK"
                tipo_400 = TIPO_USADA_400
                descripcion = "Familia USADA/REUTILIZADA: se guardara como " + TIPO_USADA_400 + "."
            else:
                estado = "SIN_INFORMACION"
                tipo_400 = ""
                descripcion = "No hay tiendas con TipoCajaInicial util para determinar la familia."

            resultados.append({
                "Pais": pais,
                "Estado": estado,
                "TipoCaja400": tipo_400,
                "Descripcion": descripcion,
                "TiendasNueva": nuevas,
                "TiendasUsada": usadas,
                "TiendasSinTipo": int(sin_tipo[pais]),
                "TiposNoHomologados": no_homologados,
                "EjemplosNueva": list(ejemplos[pais]["NUEVA"]),
                "EjemplosUsada": list(ejemplos[pais]["USADA"]),
                "EjemplosSinTipo": list(ejemplos[pais]["SIN_TIPO"]),
                "EjemplosNoHomologado": list(ejemplos[pais]["NO_HOMOLOGADO"]),
            })

        return resultados

    # ---------------------------------------------------------
    # Lectura del maestro persistente
    # ---------------------------------------------------------
    @staticmethod
    def _indices_hoja_tipo_caja_pais(hoja):
        cabeceras = {
            str(celda.value or "").strip().upper(): celda.column
            for celda in hoja[1]
        }
        columna_pais = cabeceras.get("PAIS")
        columna_tipo = cabeceras.get("TIPOCAJAPAIS")
        if columna_pais is None or columna_tipo is None:
            raise Exception(
                "La hoja TipoCajaPais debe contener las columnas Pais y TipoCajaPais."
            )
        return columna_pais, columna_tipo

    def leer_maestro_excel(self):
        if not self.archivo_configuracion.exists():
            raise Exception("No existe datos_iniciales/Configuracion.xlsx.")

        libro = openpyxl.load_workbook(self.archivo_configuracion, data_only=True)
        try:
            if "TipoCajaPais" not in libro.sheetnames:
                return {}

            hoja = libro["TipoCajaPais"]
            columna_pais, columna_tipo = self._indices_hoja_tipo_caja_pais(hoja)
            resultado = {}

            for numero_fila in range(2, hoja.max_row + 1):
                pais = self.normalizar_pais(
                    hoja.cell(row=numero_fila, column=columna_pais).value
                )
                tipo = self.normalizar_tipo(
                    hoja.cell(row=numero_fila, column=columna_tipo).value
                )
                if not pais and not tipo:
                    continue
                if not pais or not tipo:
                    raise Exception(
                        "Fila " + str(numero_fila)
                        + " incompleta en la hoja TipoCajaPais."
                    )
                if pais in resultado:
                    raise Exception(
                        "Pais duplicado en la hoja TipoCajaPais: " + pais
                    )
                resultado[pais] = tipo

            return resultado
        finally:
            libro.close()

    def leer_maestro_sqlite_filas(self):
        """Devuelve las filas SQLite normalizadas, conservando duplicados.

        Conservar los duplicados en la lectura permite detectar que SQLite no
        coincide exactamente con el maestro objetivo y forzar su saneamiento.
        """
        cursor = self.conexion.cursor()
        cursor.execute("SELECT Pais, TipoCajaPais FROM TipoCajaPais")
        filas = []
        for pais, tipo in cursor.fetchall():
            filas.append((
                self.normalizar_pais(pais),
                self.normalizar_tipo(tipo),
            ))
        return sorted(filas, key=lambda fila: (fila[0], fila[1]))

    # ---------------------------------------------------------
    # Preparar altas, coincidencias, conflictos y eliminaciones
    # ---------------------------------------------------------
    def preparar_actualizacion(self, paises):
        diagnosticos = self.analizar_paises(paises)
        maestro_actual = self.leer_maestro_excel()

        anadir = []
        sin_cambios = []
        conflictos = []
        errores = []

        for diagnostico in diagnosticos:
            if diagnostico["Estado"] != "OK":
                errores.append(diagnostico)
                continue

            pais = diagnostico["Pais"]
            tipo_nuevo = diagnostico["TipoCaja400"]
            tipo_actual = maestro_actual.get(pais)

            registro = dict(diagnostico)
            registro["TipoActual"] = tipo_actual or ""
            registro["TipoNuevo"] = tipo_nuevo

            if tipo_actual is None:
                registro["Accion"] = "ANADIR"
                anadir.append(registro)
            elif self.normalizar_tipo(tipo_actual).upper() == tipo_nuevo.upper():
                registro["Accion"] = "SIN_CAMBIOS"
                sin_cambios.append(registro)
            else:
                registro["Accion"] = "CONFLICTO"
                conflictos.append(registro)

        seleccionados = {
            diagnostico["Pais"]
            for diagnostico in diagnosticos
        }
        eliminar = [
            {
                "Pais": pais,
                "TipoActual": tipo,
                "Accion": "ELIMINAR",
            }
            for pais, tipo in sorted(maestro_actual.items())
            if pais not in seleccionados
        ]

        return {
            "Diagnosticos": diagnosticos,
            "Errores": errores,
            "Anadir": anadir,
            "SinCambios": sin_cambios,
            "Conflictos": conflictos,
            "Eliminar": eliminar,
            "MaestroActual": maestro_actual,
        }

    # ---------------------------------------------------------
    # Escritura atomica aproximada Excel + SQLite
    # ---------------------------------------------------------
    @staticmethod
    def _capturar_estilo(celda):
        return {
            "font": copy.copy(celda.font),
            "fill": copy.copy(celda.fill),
            "border": copy.copy(celda.border),
            "alignment": copy.copy(celda.alignment),
            "number_format": celda.number_format,
            "protection": copy.copy(celda.protection),
        }

    @staticmethod
    def _aplicar_estilo(celda, estilo):
        if not estilo:
            return
        celda.font = copy.copy(estilo["font"])
        celda.fill = copy.copy(estilo["fill"])
        celda.border = copy.copy(estilo["border"])
        celda.alignment = copy.copy(estilo["alignment"])
        celda.number_format = estilo["number_format"]
        celda.protection = copy.copy(estilo["protection"])

    def _crear_excel_temporal(self, datos_finales, ruta_temporal):
        libro = openpyxl.load_workbook(self.archivo_configuracion)
        try:
            if "TipoCajaPais" in libro.sheetnames:
                hoja = libro["TipoCajaPais"]
            else:
                hoja = libro.create_sheet("TipoCajaPais")
                hoja.cell(row=1, column=1, value="Pais")
                hoja.cell(row=1, column=2, value="TipoCajaPais")

            # Detectar las columnas existentes antes de reescribir la hoja.
            try:
                columna_pais, columna_tipo = self._indices_hoja_tipo_caja_pais(hoja)
            except Exception:
                columna_pais, columna_tipo = 1, 2
                hoja.cell(row=1, column=1, value="Pais")
                hoja.cell(row=1, column=2, value="TipoCajaPais")

            estilo_pais = None
            estilo_tipo = None
            if hoja.max_row >= 2:
                estilo_pais = self._capturar_estilo(
                    hoja.cell(row=2, column=columna_pais)
                )
                estilo_tipo = self._capturar_estilo(
                    hoja.cell(row=2, column=columna_tipo)
                )

            if hoja.max_row > 1:
                hoja.delete_rows(2, hoja.max_row - 1)

            hoja.cell(row=1, column=columna_pais, value="Pais")
            hoja.cell(row=1, column=columna_tipo, value="TipoCajaPais")

            for numero_fila, (pais, tipo) in enumerate(datos_finales, start=2):
                celda_pais = hoja.cell(
                    row=numero_fila,
                    column=columna_pais,
                    value=pais,
                )
                celda_tipo = hoja.cell(
                    row=numero_fila,
                    column=columna_tipo,
                    value=tipo,
                )
                self._aplicar_estilo(celda_pais, estilo_pais)
                self._aplicar_estilo(celda_tipo, estilo_tipo)

            letra_pais = openpyxl.utils.get_column_letter(columna_pais)
            letra_tipo = openpyxl.utils.get_column_letter(columna_tipo)
            hoja.column_dimensions[letra_pais].width = max(
                hoja.column_dimensions[letra_pais].width or 0,
                22,
            )
            hoja.column_dimensions[letra_tipo].width = max(
                hoja.column_dimensions[letra_tipo].width or 0,
                24,
            )
            hoja.freeze_panes = "A2"

            libro.save(ruta_temporal)
        finally:
            libro.close()

    def guardar_maestro_seleccionado(self, maestro_objetivo):
        """Sustituye TipoCajaPais por la seleccion completa de Caja 400.

        ``maestro_objetivo`` es un diccionario Pais -> TipoCajaPais y representa
        el contenido final completo. Todo pais que exista actualmente y no este
        en este diccionario se elimina tanto de Configuracion.xlsx como de
        SQLite. Un diccionario vacio deja el maestro sin registros.
        """
        objetivo_limpio = {}
        for pais, tipo in (maestro_objetivo or {}).items():
            pais_normalizado = self.normalizar_pais(pais)
            tipo_normalizado = self.normalizar_tipo(tipo)
            if not pais_normalizado:
                raise Exception("No se puede guardar un pais vacio.")
            if tipo_normalizado not in TIPOS_400_VALIDOS:
                raise Exception(
                    "Tipo de caja 400 no valido para " + pais_normalizado
                    + ": " + tipo_normalizado
                )
            objetivo_limpio[pais_normalizado] = tipo_normalizado

        if not self.archivo_configuracion.exists():
            raise Exception("No existe datos_iniciales/Configuracion.xlsx.")

        maestro_actual = self.leer_maestro_excel()
        sqlite_actual = self.leer_maestro_sqlite_filas()
        datos_finales = sorted(objetivo_limpio.items(), key=lambda fila: fila[0])

        anadidos = {
            pais: tipo
            for pais, tipo in objetivo_limpio.items()
            if pais not in maestro_actual
        }
        modificados = {
            pais: {
                "Anterior": maestro_actual[pais],
                "Nuevo": tipo,
            }
            for pais, tipo in objetivo_limpio.items()
            if pais in maestro_actual
            and self.normalizar_tipo(maestro_actual[pais]).upper() != tipo.upper()
        }
        eliminados = {
            pais: tipo
            for pais, tipo in maestro_actual.items()
            if pais not in objetivo_limpio
        }
        sin_cambios = {
            pais: tipo
            for pais, tipo in objetivo_limpio.items()
            if pais in maestro_actual
            and self.normalizar_tipo(maestro_actual[pais]).upper() == tipo.upper()
        }

        excel_igual = maestro_actual == objetivo_limpio
        sqlite_igual = sqlite_actual == datos_finales
        if excel_igual and sqlite_igual:
            return {
                "Backup": None,
                "Actualizados": 0,
                "TotalMaestro": len(datos_finales),
                "Cambios": {},
                "Anadidos": {},
                "Modificados": {},
                "Eliminados": {},
                "SinCambios": sin_cambios,
                "SQLiteResincronizada": False,
            }

        cambios = {}
        for pais, tipo in anadidos.items():
            cambios[pais] = {"Anterior": "", "Nuevo": tipo}
        cambios.update(modificados)

        fecha = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = self.archivo_configuracion.parent / (
            "Configuracion_BACKUP_TIPO_CAJA_PAIS_" + fecha + ".xlsx"
        )
        temporal = self.archivo_configuracion.parent / (
            ".Configuracion_TipoCajaPais_" + uuid.uuid4().hex + ".tmp.xlsx"
        )

        reemplazo_excel_realizado = False
        shutil.copy2(self.archivo_configuracion, backup)

        try:
            self._crear_excel_temporal(datos_finales, temporal)

            cursor = self.conexion.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute("DELETE FROM TipoCajaPais")
                for pais, tipo in datos_finales:
                    cursor.execute(
                        "INSERT INTO TipoCajaPais (Pais, TipoCajaPais) VALUES (?, ?)",
                        (pais, tipo),
                    )

                os.replace(temporal, self.archivo_configuracion)
                reemplazo_excel_realizado = True

                # Verificar ambas fuentes antes de confirmar la transaccion.
                if self.leer_maestro_excel() != objetivo_limpio:
                    raise Exception(
                        "La verificacion de Configuracion.xlsx no coincide con "
                        "la seleccion de paises Caja 400."
                    )
                if self.leer_maestro_sqlite_filas() != datos_finales:
                    raise Exception(
                        "La verificacion de SQLite no coincide con la seleccion "
                        "de paises Caja 400."
                    )

                self.conexion.commit()

            except Exception:
                self.conexion.rollback()
                if reemplazo_excel_realizado:
                    shutil.copy2(backup, self.archivo_configuracion)
                raise

        except PermissionError as error:
            raise PermissionError(
                "No se pudo actualizar Configuracion.xlsx. "
                "Cierra el archivo Excel y vuelve a intentarlo."
            ) from error
        finally:
            if temporal.exists():
                try:
                    temporal.unlink()
                except Exception:
                    pass

        return {
            "Backup": backup,
            "Actualizados": len(anadidos) + len(modificados) + len(eliminados),
            "TotalMaestro": len(datos_finales),
            "Cambios": cambios,
            "Anadidos": anadidos,
            "Modificados": modificados,
            "Eliminados": eliminados,
            "SinCambios": sin_cambios,
            "SQLiteResincronizada": not sqlite_igual,
        }

    def guardar_actualizaciones(self, actualizaciones):
        """Compatibilidad interna: en V17.14 el diccionario es el maestro final."""
        return self.guardar_maestro_seleccionado(actualizaciones)

    # ---------------------------------------------------------
    # Textos de diagnostico para la interfaz
    # ---------------------------------------------------------
    @staticmethod
    def texto_tipo_para_tabla(diagnostico):
        estado = diagnostico.get("Estado", "")
        if estado == "OK":
            return diagnostico.get("TipoCaja400", "")
        if estado == "ERROR_COHERENCIA":
            return "ERROR: NUEVA Y USADA"
        if estado == "ERROR_TIPO_NO_HOMOLOGADO":
            return "ERROR: TIPO SIN HOMOLOGAR"
        return "SIN INFORMACION"

    @staticmethod
    def texto_errores(errores, limite=12):
        lineas = [
            "No se ha modificado ningun dato.",
            "",
            "Un pais debe tener una unica familia de caja. No se admiten paises mixtos.",
            "",
        ]

        for diagnostico in list(errores)[:limite]:
            pais = diagnostico.get("Pais", "")
            estado = diagnostico.get("Estado", "")
            lineas.append(pais + " - " + diagnostico.get("Descripcion", ""))

            if estado == "ERROR_COHERENCIA":
                lineas.append(
                    "  Nueva: " + str(diagnostico.get("TiendasNueva", 0))
                    + " | Usada/Reutilizada: "
                    + str(diagnostico.get("TiendasUsada", 0))
                )
                nuevas = diagnostico.get("EjemplosNueva", [])
                usadas = diagnostico.get("EjemplosUsada", [])
                if nuevas:
                    lineas.append(
                        "  Ejemplos Nueva: " + ", ".join(map(str, nuevas))
                    )
                if usadas:
                    lineas.append(
                        "  Ejemplos Usada: " + ", ".join(map(str, usadas))
                    )
            elif estado == "ERROR_TIPO_NO_HOMOLOGADO":
                tipos = diagnostico.get("TiposNoHomologados", {})
                if tipos:
                    lineas.append(
                        "  Tipos: "
                        + ", ".join(
                            str(tipo) + " (" + str(total) + ")"
                            for tipo, total in sorted(tipos.items())
                        )
                    )
            lineas.append("")

        if len(errores) > limite:
            lineas.append(
                "Hay " + str(len(errores) - limite) + " paises adicionales con error."
            )

        return "\n".join(lineas).strip()
