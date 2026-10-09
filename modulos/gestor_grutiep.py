"""Importacion persistente y validacion de tiendas del fichero GRUTIEP.

GRUTIEP se usa exclusivamente como maestro de comprobacion. La estructura de
los CSV de clasificador no se modifica: durante la exportacion solo se avisa si
alguna tienda no existe en TRTIEN.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from bd.basedatos import BaseDatos
from modulos.ventanas_tk import (
    forzar_ventana_visible,
    liberar_grab_temporal,
    resolver_parent_tk,
    restaurar_grab,
)


class ErrorGRUTIEP(ValueError):
    """Error de estructura o contenido del fichero GRUTIEP."""


class GestorGRUTIEP:
    """Gestiona el maestro global GRUTIEP almacenado en SQLite."""

    CAMPOS_REQUERIDOS = ("TRCODS", "TRDESC", "TRTIEN")
    MAX_ERRORES_MOSTRADOS = 25

    def __init__(self, bd=None, conexion=None):
        if bd is not None and conexion is not None:
            raise ValueError("Indica bd o conexion, pero no ambos.")

        self._bd_propia = False
        self.bd = bd

        if conexion is not None:
            self.conexion = conexion
        elif bd is not None:
            self.conexion = bd.conexion
        else:
            self.bd = BaseDatos()
            self.conexion = self.bd.conexion
            self._bd_propia = True

        self.asegurar_tablas()

    def cerrar(self):
        if self._bd_propia and self.bd is not None:
            self.bd.cerrar()
            self._bd_propia = False

    def asegurar_tablas(self):
        cursor = self.conexion.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS GRUTIEP (
                TRCODS INTEGER NOT NULL,
                TRDESC TEXT,
                TRTIEN INTEGER NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS UX_GRUTIEP_GRUPO_TIENDA
            ON GRUTIEP (TRCODS, TRTIEN)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS IX_GRUTIEP_TRTIEN
            ON GRUTIEP (TRTIEN)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS GRUTIEP_IMPORTACION (
                Id INTEGER PRIMARY KEY,
                Ruta TEXT NOT NULL,
                NombreArchivo TEXT NOT NULL,
                FechaHora TEXT NOT NULL,
                Registros INTEGER NOT NULL,
                Tiendas INTEGER NOT NULL
            )
            """
        )

        self.conexion.commit()

    @staticmethod
    def _normalizar_cabecera(valor):
        return str(valor or "").replace("\ufeff", "").strip().upper()

    @staticmethod
    def _normalizar_descripcion(valor):
        return " ".join(str(valor or "").strip().split())

    @staticmethod
    def _convertir_entero(valor, campo, numero_linea):
        texto = str(valor or "").strip()

        if texto == "":
            raise ErrorGRUTIEP(
                "Linea " + str(numero_linea) + ": " + campo + " esta vacio."
            )

        try:
            return int(texto)
        except (TypeError, ValueError):
            raise ErrorGRUTIEP(
                "Linea "
                + str(numero_linea)
                + ": "
                + campo
                + " debe ser INTEGER. Valor recibido: "
                + repr(texto)
            )

    @staticmethod
    def _leer_texto(ruta):
        ruta = Path(ruta)
        errores = []

        for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return ruta.read_text(encoding=codificacion), codificacion
            except UnicodeDecodeError as error:
                errores.append(codificacion + ": " + str(error))

        raise ErrorGRUTIEP(
            "No se pudo leer el fichero con UTF-8, CP1252 ni Latin-1.\n"
            + "\n".join(errores)
        )

    @classmethod
    def analizar_archivo(cls, ruta):
        ruta = Path(ruta)

        if not ruta.exists() or not ruta.is_file():
            raise ErrorGRUTIEP("No existe el fichero seleccionado: " + str(ruta))

        texto, codificacion = cls._leer_texto(ruta)
        lector = csv.reader(io.StringIO(texto, newline=""), delimiter="\t")

        try:
            cabecera_original = next(lector)
        except StopIteration:
            raise ErrorGRUTIEP("El fichero GRUTIEP esta vacio.")

        cabecera = [cls._normalizar_cabecera(valor) for valor in cabecera_original]

        if len(cabecera) == 0:
            raise ErrorGRUTIEP("El fichero GRUTIEP no contiene cabecera.")

        if cabecera[0] != "TRCODS":
            raise ErrorGRUTIEP(
                "La primera columna debe llamarse TRCODS. Se encontro: "
                + repr(cabecera_original[0] if cabecera_original else "")
            )

        indices = {}
        for campo in cls.CAMPOS_REQUERIDOS:
            apariciones = [i for i, nombre in enumerate(cabecera) if nombre == campo]
            if len(apariciones) == 0:
                raise ErrorGRUTIEP(
                    "Falta la columna obligatoria " + campo + " en la cabecera."
                )
            if len(apariciones) > 1:
                raise ErrorGRUTIEP(
                    "La columna " + campo + " aparece repetida en la cabecera."
                )
            indices[campo] = apariciones[0]

        indice_maximo = max(indices.values())
        errores = []
        relaciones = set()
        filas_validas = []
        descripciones_por_grupo = {}
        tiendas_por_grupo = defaultdict(set)
        tiendas_totales = set()

        for numero_linea, fila in enumerate(lector, start=2):
            if len(fila) == 0 or all(str(valor).strip() == "" for valor in fila):
                continue

            if len(fila) <= indice_maximo:
                errores.append(
                    "Linea "
                    + str(numero_linea)
                    + ": no contiene todas las columnas obligatorias."
                )
                continue

            try:
                trcods = cls._convertir_entero(
                    fila[indices["TRCODS"]], "TRCODS", numero_linea
                )
                trtien = cls._convertir_entero(
                    fila[indices["TRTIEN"]], "TRTIEN", numero_linea
                )
            except ErrorGRUTIEP as error:
                errores.append(str(error))
                continue

            trdesc = cls._normalizar_descripcion(fila[indices["TRDESC"]])
            relacion = (trcods, trtien)

            if relacion in relaciones:
                errores.append(
                    "Linea "
                    + str(numero_linea)
                    + ": relacion duplicada TRCODS="
                    + str(trcods)
                    + " / TRTIEN="
                    + str(trtien)
                    + "."
                )
                continue

            descripcion_anterior = descripciones_por_grupo.get(trcods, "")
            if descripcion_anterior and trdesc and descripcion_anterior != trdesc:
                errores.append(
                    "Linea "
                    + str(numero_linea)
                    + ": TRCODS "
                    + str(trcods)
                    + " tiene descripciones diferentes: "
                    + repr(descripcion_anterior)
                    + " y "
                    + repr(trdesc)
                    + "."
                )
                continue

            if trdesc and not descripcion_anterior:
                descripciones_por_grupo[trcods] = trdesc
            elif trcods not in descripciones_por_grupo:
                descripciones_por_grupo[trcods] = ""

            relaciones.add(relacion)
            filas_validas.append((trcods, trtien))
            tiendas_por_grupo[trcods].add(trtien)
            tiendas_totales.add(trtien)

        if errores:
            visibles = errores[: cls.MAX_ERRORES_MOSTRADOS]
            texto_error = "El fichero GRUTIEP contiene errores:\n\n" + "\n".join(visibles)
            restantes = len(errores) - len(visibles)
            if restantes > 0:
                texto_error += "\n\n... y " + str(restantes) + " errores mas."
            raise ErrorGRUTIEP(texto_error)

        if len(filas_validas) == 0:
            raise ErrorGRUTIEP("El fichero GRUTIEP no contiene registros validos.")

        registros = [
            (trcods, descripciones_por_grupo.get(trcods, ""), trtien)
            for trcods, trtien in sorted(filas_validas, key=lambda item: (item[0], item[1]))
        ]

        grupos = []
        for trcods in sorted(tiendas_por_grupo):
            grupos.append(
                {
                    "TRCODS": trcods,
                    "TRDESC": descripciones_por_grupo.get(trcods, ""),
                    "Tiendas": len(tiendas_por_grupo[trcods]),
                }
            )

        return {
            "Ruta": str(ruta.resolve()),
            "NombreArchivo": ruta.name,
            "Codificacion": codificacion,
            "Registros": len(registros),
            "Tiendas": len(tiendas_totales),
            "Grupos": grupos,
            "Datos": registros,
        }

    def importar(self, ruta):
        analisis = self.analizar_archivo(ruta)
        fecha_hora = datetime.now().isoformat(timespec="seconds")
        cursor = self.conexion.cursor()

        try:
            if self.conexion.in_transaction:
                self.conexion.commit()

            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("DELETE FROM GRUTIEP")
            cursor.executemany(
                "INSERT INTO GRUTIEP (TRCODS, TRDESC, TRTIEN) VALUES (?, ?, ?)",
                analisis["Datos"],
            )
            cursor.execute("DELETE FROM GRUTIEP_IMPORTACION")
            cursor.execute(
                """
                INSERT INTO GRUTIEP_IMPORTACION
                    (Id, Ruta, NombreArchivo, FechaHora, Registros, Tiendas)
                VALUES
                    (1, ?, ?, ?, ?, ?)
                """,
                (
                    analisis["Ruta"],
                    analisis["NombreArchivo"],
                    fecha_hora,
                    analisis["Registros"],
                    analisis["Tiendas"],
                ),
            )
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise

        return self.obtener_ultima_importacion()

    def obtener_grupos(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT
                TRCODS,
                COALESCE(TRDESC, ''),
                COUNT(DISTINCT TRTIEN)
            FROM GRUTIEP
            GROUP BY TRCODS, TRDESC
            ORDER BY TRCODS
            """
        )

        return [
            {
                "TRCODS": int(fila[0]),
                "TRDESC": str(fila[1] or "").strip(),
                "Tiendas": int(fila[2] or 0),
            }
            for fila in cursor.fetchall()
        ]

    def obtener_ultima_importacion(self):
        cursor = self.conexion.cursor()
        cursor.execute(
            """
            SELECT Ruta, NombreArchivo, FechaHora, Registros, Tiendas
            FROM GRUTIEP_IMPORTACION
            WHERE Id = 1
            """
        )
        fila = cursor.fetchone()

        if fila is None:
            return None

        return {
            "Ruta": str(fila[0] or ""),
            "NombreArchivo": str(fila[1] or ""),
            "FechaHora": str(fila[2] or ""),
            "Registros": int(fila[3] or 0),
            "Tiendas": int(fila[4] or 0),
            "Grupos": self.obtener_grupos(),
        }

    def obtener_tiendas_importadas(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT DISTINCT TRTIEN FROM GRUTIEP")
        return {int(fila[0]) for fila in cursor.fetchall()}

    @staticmethod
    def normalizar_tienda(valor):
        if valor is None:
            raise ValueError("Tienda vacia")
        texto = str(valor).strip()
        if texto == "":
            raise ValueError("Tienda vacia")
        return int(texto)

    def validar_tiendas_por_clasificador(self, tiendas_por_clasificador):
        tiendas_normalizadas = {}
        valores_invalidos = {}

        for clasificador, tiendas in (tiendas_por_clasificador or {}).items():
            cla = int(clasificador)
            tiendas_normalizadas[cla] = set()
            valores_invalidos[cla] = []

            for tienda in tiendas or []:
                try:
                    tiendas_normalizadas[cla].add(self.normalizar_tienda(tienda))
                except (TypeError, ValueError):
                    valores_invalidos[cla].append(str(tienda))

        if not any(tiendas_normalizadas.values()) and not any(valores_invalidos.values()):
            return {
                "Estado": "SIN_TIENDAS",
                "Faltantes": {},
                "ValoresInvalidos": {},
                "Importacion": self.obtener_ultima_importacion(),
            }

        importacion = self.obtener_ultima_importacion()
        if importacion is None:
            return {
                "Estado": "SIN_IMPORTACION",
                "Faltantes": {},
                "ValoresInvalidos": valores_invalidos,
                "Importacion": None,
                "TiendasEvaluadas": {
                    cla: len(tiendas) for cla, tiendas in tiendas_normalizadas.items()
                },
            }

        disponibles = self.obtener_tiendas_importadas()
        faltantes = {
            cla: sorted(tiendas - disponibles)
            for cla, tiendas in tiendas_normalizadas.items()
            if tiendas - disponibles
        }
        invalidos_limpios = {
            cla: valores
            for cla, valores in valores_invalidos.items()
            if valores
        }

        estado = "OK"
        if faltantes or invalidos_limpios:
            estado = "FALTANTES"

        return {
            "Estado": estado,
            "Faltantes": faltantes,
            "ValoresInvalidos": invalidos_limpios,
            "Importacion": importacion,
            "TiendasEvaluadas": {
                cla: len(tiendas) for cla, tiendas in tiendas_normalizadas.items()
            },
            "TiendasDisponibles": len(disponibles),
        }

    @staticmethod
    def formatear_fecha(fecha_hora):
        texto = str(fecha_hora or "").strip()
        if texto == "":
            return "-"
        try:
            return datetime.fromisoformat(texto).strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            return texto

    @staticmethod
    def formatear_grupos(grupos, incluir_recuento=False):
        partes = []
        for grupo in grupos or []:
            texto = str(int(grupo["TRCODS"]))
            descripcion = str(grupo.get("TRDESC", "") or "").strip()
            if descripcion:
                texto += " - " + descripcion
            if incluir_recuento:
                texto += " (" + str(int(grupo.get("Tiendas", 0))) + " tiendas)"
            partes.append(texto)
        return " | ".join(partes) if partes else "-"

    @classmethod
    def texto_estado_formulario(cls, info):
        if info is None:
            return (
                "Ultimo GRUTIEP: no importado.\n"
                "Grupos: -"
            )

        return (
            "Ultimo GRUTIEP: "
            + cls.formatear_fecha(info.get("FechaHora"))
            + " | Fichero: "
            + str(info.get("NombreArchivo", ""))
            + " | Tiendas: "
            + str(info.get("Tiendas", 0))
            + "\nGrupos: "
            + cls.formatear_grupos(info.get("Grupos", []), incluir_recuento=True)
        )


def _texto_tiendas(tiendas, por_linea=12):
    valores = [str(valor) for valor in tiendas]
    if not valores:
        return "-"
    lineas = []
    for indice in range(0, len(valores), por_linea):
        lineas.append(", ".join(valores[indice : indice + por_linea]))
    return "\n".join(lineas)


def construir_texto_aviso_validacion(resultado):
    lineas = [
        "Los CSV de los clasificadores se han generado sin cambios.",
        "No se ha eliminado ni modificado ninguna tienda.",
        "",
        "TIENDAS QUE NO EXISTEN EN EL ULTIMO GRUTIEP IMPORTADO",
        "",
    ]

    faltantes = resultado.get("Faltantes", {})
    invalidos = resultado.get("ValoresInvalidos", {})

    for clasificador in sorted(set(faltantes) | set(invalidos)):
        tiendas = faltantes.get(clasificador, [])
        valores = invalidos.get(clasificador, [])
        lineas.append(
            "CLA " + str(clasificador) + ": " + str(len(tiendas) + len(valores)) + " aviso(s)"
        )
        if tiendas:
            lineas.append("No encontradas (" + str(len(tiendas)) + "):")
            lineas.append(_texto_tiendas(tiendas))
        if valores:
            lineas.append("Valores de tienda no numericos:")
            lineas.append(_texto_tiendas(valores))
        lineas.append("")

    info = resultado.get("Importacion")
    if info is not None:
        lineas.extend(
            [
                "GRUTIEP utilizado:",
                "Fecha: " + GestorGRUTIEP.formatear_fecha(info.get("FechaHora")),
                "Fichero: " + str(info.get("NombreArchivo", "")),
                "Grupos: " + GestorGRUTIEP.formatear_grupos(info.get("Grupos", [])),
            ]
        )

    return "\n".join(lineas).strip()


def _mostrar_dialogo_texto(titulo, encabezado, texto, parent=None):
    padre = resolver_parent_tk(parent)
    grab_anterior = liberar_grab_temporal(padre)
    ventana = None

    try:
        if padre is None:
            messagebox.showwarning(titulo, texto)
            return

        ventana = tk.Toplevel(padre)
        ventana._mantener_topmost = True
        ventana.title(titulo)
        ventana.geometry("780x560")
        ventana.minsize(640, 420)
        ventana.resizable(True, True)
        ventana.transient(padre)

        tk.Label(
            ventana,
            text=encabezado,
            font=("Arial", 12, "bold"),
            fg="#990000",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(
            ventana,
            text=(
                "La exportacion no se bloquea. Revisa las tiendas indicadas antes "
                "de utilizar las tablas en produccion."
            ),
            font=("Arial", 9),
            anchor="w",
            justify="left",
            wraplength=740,
        ).pack(fill="x", padx=16, pady=(0, 8))

        contenedor = tk.Frame(ventana)
        contenedor.pack(fill="both", expand=True, padx=16, pady=6)

        barra = tk.Scrollbar(contenedor, orient="vertical")
        caja = tk.Text(
            contenedor,
            wrap="word",
            font=("Consolas", 10),
            yscrollcommand=barra.set,
        )
        barra.config(command=caja.yview)
        barra.pack(side="right", fill="y")
        caja.pack(side="left", fill="both", expand=True)
        caja.insert("1.0", texto)
        caja.config(state="disabled")

        botones = tk.Frame(ventana)
        botones.pack(fill="x", padx=16, pady=(8, 14))

        def cerrar():
            try:
                ventana.grab_release()
            except Exception:
                pass
            ventana.destroy()

        boton_aceptar = tk.Button(
            botones,
            text="Aceptar",
            width=16,
            height=2,
            command=cerrar,
            default="active",
        )
        boton_aceptar.pack(side="right")

        ventana.protocol("WM_DELETE_WINDOW", cerrar)
        ventana.bind("<Return>", lambda evento: cerrar())
        ventana.bind("<Escape>", lambda evento: cerrar())

        # El aviso se mantiene en primer plano durante toda su vida. Antes se
        # retiraba el atributo topmost a los 350 ms y Windows podia devolverlo
        # detras del formulario que acababa de exportar.
        ventana.grab_set()
        forzar_ventana_visible(
            ventana,
            padre,
            mantener_arriba=True,
            focus_widget=boton_aceptar,
        )
        ventana.wait_window()
    finally:
        try:
            if ventana is not None and ventana.winfo_exists():
                ventana.destroy()
        except Exception:
            pass
        restaurar_grab(grab_anterior)


def mostrar_aviso_validacion_grutiep(resultado, parent=None):
    estado = str((resultado or {}).get("Estado", ""))

    if estado in ("", "OK", "SIN_TIENDAS"):
        return

    padre = resolver_parent_tk(parent)

    if estado == "SIN_IMPORTACION":
        messagebox.showwarning(
            "Validacion GRUTIEP no realizada",
            "Los CSV se han generado normalmente, pero no existe ningun fichero "
            "GRUTIEP importado.\n\nNo se pudo comprobar si todas las tiendas "
            "estan incluidas.",
            parent=padre,
        )
        return

    if estado == "FALTANTES":
        _mostrar_dialogo_texto(
            "Aviso GRUTIEP",
            "Hay tiendas exportadas que no existen en GRUTIEP",
            construir_texto_aviso_validacion(resultado),
            parent=padre,
        )


def validar_y_avisar_grutiep(bd, tiendas_por_clasificador, parent=None):
    """Valida las tiendas exportadas y muestra un aviso no bloqueante."""

    gestor = GestorGRUTIEP(bd=bd)
    resultado = gestor.validar_tiendas_por_clasificador(tiendas_por_clasificador)
    mostrar_aviso_validacion_grutiep(resultado, parent=parent)
    return resultado
