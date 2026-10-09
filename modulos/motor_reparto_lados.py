from collections import Counter

from modulos.motor_reparto import MotorReparto
from modulos.configuracion_lados_carrusel import (
    obtener_lado,
    clave_fisica,
    destino_pertenece,
)


class MotorRepartoLados(MotorReparto):
    """Motor especializado en repartir sobre los lados fisicos elegidos.

    Mantiene las reglas del motor general para:
    - orden de TipoCaja;
    - bloques virtuales por lotes;
    - destinos consecutivos por prioridad;
    - equilibrio de lotes y TipoCaja.

    La diferencia es que el universo de destinos queda limitado estrictamente
    a los lados fisicos elegidos por el operador. Puede ser un solo lado,
    varios lados, un carrusel completo o los dos carruseles. El equilibrio se
    calcula entre todos los lados seleccionados.
    """

    def __init__(self, clave_pedido_trabajo=None):
        super().__init__(clave_pedido_trabajo=clave_pedido_trabajo)
        self.lados_seleccionados = []
        self.ids_lados_seleccionados = []
        self.estadisticas_lados_seleccionados = {}

    # ---------------------------------------------------------
    # Entrada principal
    # ---------------------------------------------------------
    def reparto_por_lados(self, ids_lados, tamano_bloque=10):
        ids_lados = list(dict.fromkeys(ids_lados or []))

        if len(ids_lados) < 1:
            raise ValueError("Debes seleccionar al menos un lado fisico.")

        self.ids_lados_seleccionados = ids_lados
        self.lados_seleccionados = [obtener_lado(lado_id) for lado_id in ids_lados]
        self.clasificadores_activos = sorted(
            {int(lado["Clasificador"]) for lado in self.lados_seleccionados}
        )
        self.tamano_bloque = max(1, int(tamano_bloque or 10))
        self.prioridad = "NORMAL"
        self.configuracion_paises = self.normalizar_configuracion_paises(None)

        # Compatibilidad con versiones recientes del motor general.
        if hasattr(self, "normalizar_configuracion_prioridad_paises"):
            self.configuracion_prioridad_paises = self.normalizar_configuracion_prioridad_paises(None)
        self.prioridad_tienda_activa = "NORMAL"

        self.cargar_tmp()
        self.cargar_destinos_seleccionados()

        if len(self.tmp) == 0:
            raise ValueError("TMP_ESTAREPP no contiene Tienda + Aparte para repartir.")

        capacidad = len(self.destinos)
        necesarios = len(self.tmp)
        if necesarios > capacidad:
            raise ValueError(
                "No cabe en los lados seleccionados. Necesarios: "
                + str(necesarios)
                + " | Disponibles: "
                + str(capacidad)
                + " | Faltan: "
                + str(necesarios - capacidad)
            )

        self.calcular_tramos_destinos()
        self.ordenar_tiendas()
        self.calcular_numero_destinos()

        # No se usa el dialogo de lado corto: los lados ya vienen fijados.
        self.opcion_lado_corto = {
            "Numero": 1,
            "Nombre": "Seleccion manual de lados fisicos",
            "Modo": "AUTO",
            "LadosPermitidos": None,
        }

        self.resetear_reparto_en_memoria()
        self.inicializar_estadisticas_lados()
        self.ejecutar_reparto_core()
        self.validar_reparto_completo_lados()

        total_guardado = self.guardar_reparto_clasificador()
        return self.obtener_resumen_lados(total_guardado)

    # ---------------------------------------------------------
    # Cargar solo los destinos de los lados elegidos
    # ---------------------------------------------------------
    def cargar_destinos_seleccionados(self):
        datos = self.bd.consultar("""
            SELECT
                Clasificador,
                Lado,
                Destino,
                Descripcion,
                Prioridad,
                Prioridad_Orden
            FROM TablasDistribucionClasificador
            ORDER BY Prioridad_Orden ASC
        """)

        self.destinos = []

        for fila in datos:
            clasificador, lado, destino, descripcion, prioridad, prioridad_orden = fila

            lado_config = None
            for candidato in self.lados_seleccionados:
                if destino_pertenece(
                    candidato,
                    clasificador,
                    lado,
                    descripcion,
                    destino,
                ):
                    lado_config = candidato
                    break

            if lado_config is None:
                continue

            self.destinos.append({
                "Clasificador": int(clasificador),
                "Lado": int(lado),
                "Destino": int(destino),
                "Bloque": self.calcular_bloque_destino(destino),
                "Tramo": 0,
                "Descripcion": descripcion,
                "Prioridad": prioridad,
                "PrioridadOrden": prioridad_orden,
                "Libre": True,
                "Tienda": None,
                "Aparte": None,
                "Lotes": 0,
                "TipoCaja": "",
                "IdLadoFisico": lado_config["Id"],
            })

        if len(self.destinos) == 0:
            raise ValueError(
                "No se han encontrado destinos en TablasDistribucionClasificador "
                "para los lados seleccionados."
            )

    # ---------------------------------------------------------
    # Estadisticas rapidas por lado seleccionado
    # ---------------------------------------------------------
    def inicializar_estadisticas_lados(self):
        self.estadisticas_lados_seleccionados = {}
        for lado in self.lados_seleccionados:
            self.estadisticas_lados_seleccionados[lado["Id"]] = {
                "Lotes": 0,
                "Tiendas": 0,
                "TipoCaja": Counter(),
            }

    # ---------------------------------------------------------
    # Siguiente destino: equilibrar solo entre los lados elegidos
    # ---------------------------------------------------------
    def siguiente_destino(self, tienda):
        self.prioridad_tienda_activa = "NORMAL"
        candidatos = self.obtener_primer_destino_libre_por_lado_fisico()

        if not candidatos:
            return None

        mejor = None
        mejor_valor = None

        for destino in candidatos:
            valor = self.valorar_destino_lados(destino, tienda)
            if mejor_valor is None or valor < mejor_valor:
                mejor_valor = valor
                mejor = destino

        return mejor

    def obtener_primer_destino_libre_por_lado_fisico(self):
        mejores = {}

        for destino in self.destinos:
            if not destino["Libre"]:
                continue

            lado_id = destino["IdLadoFisico"]
            actual = mejores.get(lado_id)

            if actual is None:
                mejores[lado_id] = destino
                continue

            if destino["PrioridadOrden"] < actual["PrioridadOrden"]:
                mejores[lado_id] = destino
            elif (
                destino["PrioridadOrden"] == actual["PrioridadOrden"]
                and destino["Destino"] < actual["Destino"]
            ):
                mejores[lado_id] = destino

        return list(mejores.values())

    # ---------------------------------------------------------
    # Jerarquia de equilibrio entre los lados seleccionados
    # ---------------------------------------------------------
    def valorar_destino_lados(self, destino, tienda):
        lado_id = destino["IdLadoFisico"]
        lotes = tienda[2]
        tipo_caja = tienda[4]

        lotes_resultantes = []
        tiendas_resultantes = []
        tipos_resultantes = []

        for lado in self.lados_seleccionados:
            id_actual = lado["Id"]
            estadistica = self.estadisticas_lados_seleccionados[id_actual]

            total_lotes = estadistica["Lotes"]
            total_tiendas = estadistica["Tiendas"]
            total_tipo = estadistica["TipoCaja"].get(tipo_caja, 0)

            if id_actual == lado_id:
                total_lotes += lotes
                total_tiendas += 1
                total_tipo += 1

            lotes_resultantes.append(total_lotes)
            tiendas_resultantes.append(total_tiendas)
            tipos_resultantes.append(total_tipo)

        diferencia_lotes = max(lotes_resultantes) - min(lotes_resultantes)
        diferencia_tipo = max(tipos_resultantes) - min(tipos_resultantes)
        diferencia_tiendas = max(tiendas_resultantes) - min(tiendas_resultantes)

        estadistica_candidata = self.estadisticas_lados_seleccionados[lado_id]
        lotes_lado_resultante = estadistica_candidata["Lotes"] + lotes
        tipo_lado_resultante = estadistica_candidata["TipoCaja"].get(tipo_caja, 0) + 1
        tiendas_lado_resultante = estadistica_candidata["Tiendas"] + 1

        return (
            diferencia_lotes,
            diferencia_tipo,
            diferencia_tiendas,
            lotes_lado_resultante,
            tipo_lado_resultante,
            tiendas_lado_resultante,
            destino["PrioridadOrden"],
            destino["Destino"],
        )

    # ---------------------------------------------------------
    # Asignar y actualizar estadisticas O(1)
    # ---------------------------------------------------------
    def asignar_tienda(self, tienda, destino):
        super().asignar_tienda(tienda, destino)

        lado_id = destino["IdLadoFisico"]
        estadistica = self.estadisticas_lados_seleccionados[lado_id]
        estadistica["Lotes"] += tienda[2]
        estadistica["Tiendas"] += 1
        estadistica["TipoCaja"][tienda[4]] += 1

    # ---------------------------------------------------------
    # Validacion final estricta
    # ---------------------------------------------------------
    def validar_reparto_completo_lados(self):
        asignados = self.contar_destinos_asignados()
        esperados = len(self.tmp)

        if asignados != esperados:
            raise RuntimeError(
                "El reparto por lados no se ha completado. Esperados: "
                + str(esperados)
                + " | Asignados: "
                + str(asignados)
                + " | Pendientes: "
                + str(max(0, esperados - asignados))
            )

    # ---------------------------------------------------------
    # Resumen para el formulario
    # ---------------------------------------------------------
    def obtener_resumen_lados(self, total_guardado):
        lados = []

        for lado in self.lados_seleccionados:
            estadistica = self.estadisticas_lados_seleccionados[lado["Id"]]
            capacidad = sum(
                1
                for destino in self.destinos
                if destino["IdLadoFisico"] == lado["Id"]
            )
            lados.append({
                "Id": lado["Id"],
                "Nombre": lado["Nombre"],
                "Rango": str(lado["Desde"]) + "-" + str(lado["Hasta"]),
                "Capacidad": capacidad,
                "Tiendas": estadistica["Tiendas"],
                "Lotes": estadistica["Lotes"],
            })

        return {
            "Registros": total_guardado,
            "Necesarios": len(self.tmp),
            "Capacidad": len(self.destinos),
            "Libres": len(self.destinos) - total_guardado,
            "Clasificadores": list(self.clasificadores_activos),
            "Lados": lados,
        }
