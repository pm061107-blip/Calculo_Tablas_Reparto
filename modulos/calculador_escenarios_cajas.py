"""Calculo comparativo de escenarios por grupos de tiendas.

Cada grupo es una simulacion independiente. El umbral de unidades se evalua
una sola vez sobre el pedido inicial completo de las tiendas normales. Las
tiendas fijas quedan fuera de ese calculo y conservan todas sus lineas, salvo
cuando pertenecen al grupo que se esta excluyendo en el escenario.
"""

from __future__ import annotations

from collections import defaultdict

from bd.basedatos import BaseDatos
from modulos.motor_calculo_cajas_pedido import MotorCalculoCajasPedido
from modulos.gestor_pedidos_cajas import (
    GestorPedidosCajas,
    linea_eliminada_por_picos,
)


class CalculadorEscenariosCajas:
    CLAVE_TODO = "TODO"

    def __init__(self, bd=None):
        self._bd_propia = bd is None
        self.bd = bd or BaseDatos()

    def cerrar(self):
        if self._bd_propia and self.bd is not None:
            try:
                self.bd.cerrar()
            except Exception:
                pass
            self._bd_propia = False

    @staticmethod
    def escenario_todo():
        return {
            "Clave": CalculadorEscenariosCajas.CLAVE_TODO,
            "Grupo": "TODO",
            "Descripcion": "TODO",
            "Tiendas": set(),
        }

    @staticmethod
    def _numero_real(valor, defecto=0.0):
        texto = str(valor if valor is not None else "").strip().replace(",", ".")
        if texto == "":
            return defecto
        try:
            return float(texto)
        except Exception:
            return defecto

    @staticmethod
    def _normalizar_tiendas(valores):
        resultado = set()
        for valor in valores or set():
            try:
                tienda = int(valor)
            except Exception:
                continue
            if tienda > 0:
                resultado.add(tienda)
        return resultado

    def _cargar_base_pedido(self, motor, umbral, tiendas_fijas=None):
        """Prepara la base comun de todos los escenarios.

        V2.1: el umbral se calcula solo con la demanda de los pedidos marcados
        con picos y de tiendas no fijas. Las lineas de pedidos sin picos y
        todas las lineas de las tiendas fijas se conservan siempre.
        """
        GestorPedidosCajas(self.bd.conexion)
        filas = self.bd.consultar(
            """
            SELECT
                Tienda, Aparte, Modelo, Calidad, Color, TallaNum,
                Campaña, Año, UxL, Unidades, Lotes,
                IFNULL(CalcularPicos, 1)
            FROM CAJAS_PEDIDO_LINEAS
            """
        )

        tiendas_fijas = self._normalizar_tiendas(tiendas_fijas)
        registros = []
        unidades_normales_por_sku = defaultdict(int)
        lotes_normales_por_sku = defaultdict(float)
        unidades_totales_por_sku = defaultdict(int)
        lotes_totales_por_sku = defaultdict(float)
        skus_tiendas_fijas = set()
        tiendas_fijas_en_pedido = set()
        unidades_tiendas_fijas = 0
        lotes_tiendas_fijas = 0.0
        registros_tiendas_fijas = 0
        tallas_invalidas = 0
        unidades_sin_picos = 0
        lotes_sin_picos = 0.0
        registros_sin_picos = 0

        for fila in filas:
            (
                tienda,
                aparte,
                modelo,
                calidad,
                color,
                talla_num,
                campana,
                anio,
                uxl,
                unidades,
                lotes,
                calcular_picos,
            ) = fila
            calcular_picos = bool(int(calcular_picos or 0))

            talla = motor.normalizar_talla(talla_num)
            if talla is None:
                tallas_invalidas += 1
                continue

            sku = motor.crear_sku(modelo, calidad, color, talla, campana, anio)
            tienda_num = motor.numero(tienda, None)
            unidades_num = motor.numero(unidades, 0)
            lotes_num = self._numero_real(lotes, 0.0)
            es_tienda_fija = tienda_num is not None and tienda_num in tiendas_fijas

            registro = {
                "Tienda": tienda_num,
                "Aparte": aparte,
                "SKU": sku,
                "Unidades": unidades_num,
                "Lotes": lotes_num,
                "UxL": motor.numero(uxl, 0),
                "EsTiendaFija": bool(es_tienda_fija),
                "CalcularPicos": calcular_picos,
            }
            registros.append(registro)
            unidades_totales_por_sku[sku] += unidades_num
            lotes_totales_por_sku[sku] += lotes_num

            if es_tienda_fija:
                tiendas_fijas_en_pedido.add(tienda_num)
                skus_tiendas_fijas.add(sku)
                unidades_tiendas_fijas += unidades_num
                lotes_tiendas_fijas += lotes_num
                registros_tiendas_fijas += 1
            elif calcular_picos:
                unidades_normales_por_sku[sku] += unidades_num
                lotes_normales_por_sku[sku] += lotes_num
            else:
                unidades_sin_picos += unidades_num
                lotes_sin_picos += lotes_num
                registros_sin_picos += 1

        umbral = int(umbral or 0)
        skus_permitidos = {
            sku
            for sku, unidades in unidades_normales_por_sku.items()
            if int(unidades or 0) >= umbral
        }
        skus_descartados = set(unidades_normales_por_sku) - skus_permitidos

        registros_base = [
            registro
            for registro in registros
            if not linea_eliminada_por_picos(
                registro["SKU"],
                registro["CalcularPicos"],
                registro["EsTiendaFija"],
                skus_permitidos,
            )
        ]

        filtro = {
            "Umbral": umbral,
            "SkusIniciales": len(unidades_normales_por_sku),
            "SkusConsiderados": len(skus_permitidos),
            "SkusDescartados": len(skus_descartados),
            "SkusTiendasFijas": len(skus_tiendas_fijas),
            "UnidadesIniciales": int(sum(unidades_totales_por_sku.values())),
            "UnidadesEvaluadasPicos": int(sum(unidades_normales_por_sku.values())),
            "UnidadesTiendasFijas": int(unidades_tiendas_fijas),
            "UnidadesDescartadas": int(
                sum(unidades_normales_por_sku[sku] for sku in skus_descartados)
            ),
            "LotesDescartados": float(
                sum(lotes_normales_por_sku[sku] for sku in skus_descartados)
            ),
            "LotesTiendasFijas": float(lotes_tiendas_fijas),
            "TiendasFijasConfiguradas": len(tiendas_fijas),
            "TiendasFijasEnPedido": len(tiendas_fijas_en_pedido),
            "RegistrosTiendasFijas": int(registros_tiendas_fijas),
            "RegistrosTallaInvalida": int(tallas_invalidas),
            "UnidadesSinPicos": int(unidades_sin_picos),
            "LotesSinPicos": float(lotes_sin_picos),
            "RegistrosSinPicos": int(registros_sin_picos),
        }
        try:
            resumen_pedidos = GestorPedidosCajas(self.bd.conexion).resumen()
        except Exception:
            resumen_pedidos = {}
        filtro["Pedidos"] = int(resumen_pedidos.get("Pedidos", 0) or 0)
        filtro["PedidosConPicos"] = int(resumen_pedidos.get("ConPicos", 0) or 0)
        filtro["PedidosSinPicos"] = int(resumen_pedidos.get("SinPicos", 0) or 0)
        return registros_base, skus_permitidos, filtro

    @staticmethod
    def _normalizar_escenario(escenario):
        if not escenario or str(escenario.get("Clave", "")).upper() == "TODO":
            return CalculadorEscenariosCajas.escenario_todo()

        tiendas = set()
        for valor in escenario.get("Tiendas", set()) or set():
            try:
                tiendas.add(int(valor))
            except Exception:
                continue

        codigo = escenario.get("Grupo")
        try:
            codigo = int(codigo)
        except Exception:
            codigo = str(codigo or "").strip()

        return {
            "Clave": str(escenario.get("Clave") or ("GRUPO:" + str(codigo))),
            "Grupo": codigo,
            "Descripcion": " ".join(
                str(escenario.get("Descripcion", "") or "").strip().split()
            ),
            "Tiendas": tiendas,
        }

    @staticmethod
    def _estadisticas_pedido(registros_base, escenario, tiendas_fijas=None):
        excluidas = set(escenario.get("Tiendas", set()) or set())
        tiendas_fijas = CalculadorEscenariosCajas._normalizar_tiendas(
            tiendas_fijas
        )
        unidades = 0
        lotes = 0.0
        tiendas_presentes = set()
        tiendas_excluidas_presentes = set()
        tiendas_fijas_presentes = set()
        tiendas_fijas_eliminadas = set()

        for registro in registros_base:
            tienda = registro.get("Tienda")
            if tienda is not None:
                tiendas_presentes.add(tienda)
                if tienda in tiendas_fijas:
                    tiendas_fijas_presentes.add(tienda)
            if tienda is not None and tienda in excluidas:
                tiendas_excluidas_presentes.add(tienda)
                if tienda in tiendas_fijas:
                    tiendas_fijas_eliminadas.add(tienda)
                continue
            unidades += int(registro.get("Unidades", 0) or 0)
            lotes += float(registro.get("Lotes", 0.0) or 0.0)

        return {
            "Unidades": int(unidades),
            "Lotes": float(lotes),
            "TiendasPedido": len(tiendas_presentes),
            "TiendasGrupo": len(excluidas),
            "TiendasGrupoEnPedido": len(tiendas_excluidas_presentes),
            "TiendasFijasEnPedido": len(tiendas_fijas_presentes),
            "TiendasFijasEliminadasGrupo": len(tiendas_fijas_eliminadas),
            "TiendasFijasConservadas": len(
                tiendas_fijas_presentes - tiendas_fijas_eliminadas
            ),
        }

    @staticmethod
    def _resultado_compacto(escenario, estadisticas, resumen):
        return {
            "Clave": escenario["Clave"],
            "Grupo": escenario["Grupo"],
            "Descripcion": escenario["Descripcion"],
            "Lotes": float(estadisticas.get("Lotes", 0.0) or 0.0),
            "Unidades": int(estadisticas.get("Unidades", 0) or 0),
            "CajasXDC": int(resumen.get("CajasReservadasXDOC", 0) or 0),
            "CajasSilo": int(resumen.get("CajasCarruselTotal", 0) or 0),
            "TiendasGrupo": int(estadisticas.get("TiendasGrupo", 0) or 0),
            "TiendasGrupoEnPedido": int(
                estadisticas.get("TiendasGrupoEnPedido", 0) or 0
            ),
            "TiendasFijasEnPedido": int(
                estadisticas.get("TiendasFijasEnPedido", 0) or 0
            ),
            "TiendasFijasEliminadasGrupo": int(
                estadisticas.get("TiendasFijasEliminadasGrupo", 0) or 0
            ),
            "TiendasFijasConservadas": int(
                estadisticas.get("TiendasFijasConservadas", 0) or 0
            ),
        }

    def calcular_todos(
        self,
        modo,
        umbral,
        grupos,
        tiendas_fijas=None,
        progreso=None,
    ):
        """Calcula todos los grupos y deja TODO como escenario activo final."""
        motor = MotorCalculoCajasPedido()
        tiendas_fijas = self._normalizar_tiendas(tiendas_fijas)
        try:
            registros_base, skus_permitidos, filtro = self._cargar_base_pedido(
                motor, umbral, tiendas_fijas=tiendas_fijas
            )
            grupos_normalizados = [
                self._normalizar_escenario(grupo) for grupo in (grupos or [])
            ]
            # TODO se ejecuta al final para que las tablas de trabajo queden
            # preparadas para el comportamiento historico si el operador no
            # selecciona otro grupo.
            orden_ejecucion = grupos_normalizados + [self.escenario_todo()]
            total = len(orden_ejecucion)
            resultados_por_clave = {}
            resumen_activo = None

            for indice, escenario in enumerate(orden_ejecucion, start=1):
                if progreso is not None:
                    progreso(indice, total, escenario)

                resumen = motor.calcular(
                    modo,
                    tiendas_excluidas=escenario["Tiendas"],
                    skus_permitidos=skus_permitidos,
                    tiendas_fijas=tiendas_fijas,
                )
                estadisticas = self._estadisticas_pedido(
                    registros_base,
                    escenario,
                    tiendas_fijas=tiendas_fijas,
                )
                resultados_por_clave[escenario["Clave"]] = self._resultado_compacto(
                    escenario, estadisticas, resumen
                )
                if escenario["Clave"] == self.CLAVE_TODO:
                    resumen_activo = resumen

            resultados_ordenados = [resultados_por_clave[self.CLAVE_TODO]]
            for grupo in grupos_normalizados:
                resultado = resultados_por_clave.get(grupo["Clave"])
                if resultado is not None:
                    resultados_ordenados.append(resultado)

            return {
                "Resultados": resultados_ordenados,
                "PorClave": resultados_por_clave,
                "Filtro": filtro,
                "EscenarioActivo": self.escenario_todo(),
                "ResumenActivo": resumen_activo or {},
            }
        finally:
            try:
                motor.bd.cerrar()
            except Exception:
                pass

    def calcular_unico(self, modo, umbral, escenario, tiendas_fijas=None):
        """Calcula y deja activas las tablas del escenario indicado."""
        motor = MotorCalculoCajasPedido()
        tiendas_fijas = self._normalizar_tiendas(tiendas_fijas)
        try:
            registros_base, skus_permitidos, filtro = self._cargar_base_pedido(
                motor, umbral, tiendas_fijas=tiendas_fijas
            )
            escenario = self._normalizar_escenario(escenario)
            resumen = motor.calcular(
                modo,
                tiendas_excluidas=escenario["Tiendas"],
                skus_permitidos=skus_permitidos,
                tiendas_fijas=tiendas_fijas,
            )
            estadisticas = self._estadisticas_pedido(
                registros_base,
                escenario,
                tiendas_fijas=tiendas_fijas,
            )
            return {
                "Resultado": self._resultado_compacto(
                    escenario, estadisticas, resumen
                ),
                "Filtro": filtro,
                "EscenarioActivo": escenario,
                "ResumenActivo": resumen,
            }
        finally:
            try:
                motor.bd.cerrar()
            except Exception:
                pass
