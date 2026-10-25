"""Utilidades centralizadas de reseteo operativo de calculos.

El objetivo es dejar cada formulario preparado para empezar un calculo nuevo
sin borrar maestros ni configuraciones permanentes. La volumetria de cajas se
conserva expresamente: solo se sustituye cuando el operador importa otro fichero
porque no cambia con la misma frecuencia que pedido y contenedores.
"""

from __future__ import annotations

from typing import Iterable, Optional


class GestorResetCalculos:
    """Limpieza segura de datos temporales y resultados de formularios."""

    TABLAS_RESULTADOS_REPARTO = (
        "REPARTO_CLASIFICADOR",
    )

    TABLAS_FUERA_TABLA = (
        "FUERA_TABLA_ACTIVA",
        "FUERA_TABLA_PEDIDO",
        "FUERA_TABLA_EXISTENTE",
        "FUERA_TABLA_RESULTADO",
    )

    TABLAS_ADELANTO = (
        "ADELANTO_PEDIDO_1",
        "ADELANTO_PEDIDO_2",
        "ADELANTO_RESTO",
        "ADELANTO_SELECCION",
    )

    TABLAS_CAJAS_SIN_VOLUMETRIA = (
        "ESTAREPP",
        "CAJAS_PEDIDO_LINEAS",
        "CAJAS_PEDIDOS_IMPORTADOS",
        "CAJAS_CONTENEDORES",
        "CAJAS_PEDIDO_DEMANDA",
        "CAJAS_RESULTADO_DETALLE",
        "CAJAS_RESULTADO_RESUMEN_SKU",
        "CAJAS_XDOC_RESUMEN",
        "CAJAS_RESULTADO_INCIDENCIAS",
        "CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR",
        "CAJAS_PEDIDO_ESCENARIO_ACTIVO",
        "CAJAS_PEDIDO_ESCENARIO_DESCARTADO",
        "CAJAS_ESCENARIO_ACTIVO",
    )

    def __init__(self, conexion):
        if conexion is None:
            raise ValueError("Se necesita una conexion SQLite valida.")
        self.conexion = conexion

    @staticmethod
    def _identificador(nombre: str) -> str:
        return '"' + str(nombre).replace('"', '""') + '"'

    def tabla_existe(self, tabla: str) -> bool:
        cursor = self.conexion.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(tabla),),
        )
        return cursor.fetchone() is not None

    def vaciar_si_existe(self, tabla: str) -> bool:
        if not self.tabla_existe(tabla):
            return False
        self.conexion.execute("DELETE FROM " + self._identificador(tabla))
        return True

    def vaciar_tablas(self, tablas: Iterable[str]) -> int:
        total = 0
        for tabla in tablas:
            if self.vaciar_si_existe(tabla):
                total += 1
        return total

    def limpiar_pedido_trabajo(self, clave_formulario: str) -> None:
        clave = str(clave_formulario or "").strip().upper()
        if not clave:
            return
        if self.tabla_existe("PEDIDOS_TRABAJO_DETALLE"):
            self.conexion.execute(
                "DELETE FROM PEDIDOS_TRABAJO_DETALLE WHERE ClaveFormulario=?",
                (clave,),
            )
        if self.tabla_existe("PEDIDOS_TRABAJO_META"):
            self.conexion.execute(
                "DELETE FROM PEDIDOS_TRABAJO_META WHERE ClaveFormulario=?",
                (clave,),
            )
        if self.tabla_existe("PEDIDOS_TRABAJO_ULTIMO_CALCULO"):
            self.conexion.execute(
                "DELETE FROM PEDIDOS_TRABAJO_ULTIMO_CALCULO WHERE ClaveFormulario=?",
                (clave,),
            )

    def limpiar_pedidos_trabajo(self, claves: Iterable[str]) -> None:
        for clave in claves:
            self.limpiar_pedido_trabajo(clave)

    def resetear_reparto(self, clave_formulario: str) -> None:
        self.limpiar_pedido_trabajo(clave_formulario)
        self.vaciar_tablas(self.TABLAS_RESULTADOS_REPARTO)
        self.conexion.commit()

    def resetear_reparto_por_lados(self, clave_formulario: str) -> None:
        self.resetear_reparto(clave_formulario)

    def resetear_fuera_tabla(self, clave_formulario: str) -> None:
        self.limpiar_pedido_trabajo(clave_formulario)
        self.vaciar_tablas(self.TABLAS_FUERA_TABLA)
        self.vaciar_tablas(self.TABLAS_RESULTADOS_REPARTO)
        self.conexion.commit()

    def resetear_adelanto(self, claves: Iterable[str]) -> None:
        self.limpiar_pedidos_trabajo(claves)
        self.vaciar_tablas(self.TABLAS_ADELANTO)
        self.vaciar_tablas(self.TABLAS_RESULTADOS_REPARTO)
        self.conexion.commit()

    def resetear_calculo_cajas(self, conservar_volumetria: bool = True) -> None:
        tablas = list(self.TABLAS_CAJAS_SIN_VOLUMETRIA)
        if not conservar_volumetria:
            tablas.append("CAJAS_VOLUMETRIA")
        self.vaciar_tablas(tablas)
        if self.tabla_existe("CAJAS_IMPORTACIONES"):
            tipos = ["PEDIDO", "CONTENEDORES"]
            if not conservar_volumetria:
                tipos.append("VOLUMETRIA")
            marcas = ",".join(["?"] * len(tipos))
            self.conexion.execute(
                "DELETE FROM CAJAS_IMPORTACIONES WHERE Tipo IN (" + marcas + ")",
                tipos,
            )
        self.conexion.commit()

    def resetear_volumetria_paises(self) -> None:
        """Resetea solo el calculo visual por pais; no borra la volumetria SKU."""
        # No hay tablas persistentes propias que borrar en esta fase; los datos
        # se reconstruyen desde el ultimo calculo de cajas y la tabla TipoCajaPais.
        self.conexion.commit()
