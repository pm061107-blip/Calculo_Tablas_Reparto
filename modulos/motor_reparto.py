from bd.basedatos import BaseDatos
from modulos.dialogos_operador import seleccionar_opcion_lado_corto
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo


class MotorReparto:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, clave_pedido_trabajo=None):

        self.bd = BaseDatos()
        self.clave_pedido_trabajo = (
            str(clave_pedido_trabajo).strip().upper()
            if clave_pedido_trabajo is not None
            else None
        )
        self.gestor_pedidos_trabajo = (
            GestorPedidosTrabajo(self.bd.conexion)
            if self.clave_pedido_trabajo
            else None
        )

        self.tmp = []
        self.destinos = []

        self.clasificadores_activos = []
        self.numero_destinos = 0
        self.ultimo_destino_previsto = None
        self.tamano_bloque = 10
        self.prioridad = "NORMAL"
        self.configuracion_paises = None
        self.configuracion_prioridad_paises = None
        self.prioridad_tienda_activa = None
        self.tipo_caja_activo = None

        self.opcion_lado_corto = None
        self.opciones_lado_corto = []

        self.clasificadores = self.crear_estadisticas_vacias()

    #---------------------------------------------------------
    # Crear estructura de estadisticas
    #---------------------------------------------------------
    def crear_estadisticas_vacias(self):

        return {
            1: {
                "Lotes": 0,
                "Tiendas": 0,
                "Lados": {
                    1: {"Lado_corto": 0, "Lado_Largo": 0},
                    2: {"Lado_corto": 0, "Lado_Largo": 0}
                }
            },
            2: {
                "Lotes": 0,
                "Tiendas": 0,
                "Lados": {
                    3: {"Lado_corto": 0, "Lado_Largo": 0},
                    4: {"Lado_corto": 0, "Lado_Largo": 0}
                }
            }
        }

    #---------------------------------------------------------
    # Reparto general
    #---------------------------------------------------------
    def reparto_general(self, clasificadores_activos, tamano_bloque=10, prioridad="NORMAL", configuracion_paises=None, configuracion_prioridad_paises=None):

        self.clasificadores_activos = clasificadores_activos
        self.tamano_bloque = tamano_bloque
        self.prioridad = prioridad
        self.configuracion_paises = self.normalizar_configuracion_paises(configuracion_paises)
        self.configuracion_prioridad_paises = self.normalizar_configuracion_prioridad_paises(configuracion_prioridad_paises)

        if len(self.clasificadores_activos) != 1:
            self.prioridad = "NORMAL"
            self.configuracion_prioridad_paises = {
                "Activo": False,
                "PaisesNormal": [],
                "PaisesInversa": []
            }

        self.cargar_tmp()
        self.cargar_destinos()
        self.validar_capacidad_paises_forzados()
        self.calcular_tramos_destinos()
        self.ordenar_tiendas()
        self.calcular_numero_destinos()

        if self.usar_prioridad_directa_un_carrusel():
            self.opcion_lado_corto = {
                "Numero": 1,
                "Nombre": "Prioridad directa por un carrusel",
                "Modo": "AUTO",
                "LadosPermitidos": None
            }
        else:
            self.seleccionar_lado_corto_operador()

        self.resetear_reparto_en_memoria()
        self.ejecutar_reparto_core()

        if self.hay_paises_fijos():
            self.validar_reparto_completo()

        total_guardado = self.guardar_reparto_clasificador()
        self.imprimir_resumen_final(total_guardado)

        return {
            "Registros": total_guardado,
            "LadoCorto": dict(self.opcion_lado_corto or {}),
            "Clasificadores": list(self.clasificadores_activos),
        }

    #---------------------------------------------------------
    # Calcular bloque de destino
    #---------------------------------------------------------
    def calcular_bloque_destino(self, destino):

        return ((int(destino) - 1) // self.tamano_bloque) + 1

    #---------------------------------------------------------
    # Comprobar si se usa prioridad inversa
    #---------------------------------------------------------
    def usar_prioridad_inversa(self):

        if len(self.clasificadores_activos) != 1:
            return False

        return self.prioridad == "INVERSA"

    #---------------------------------------------------------
    # Prioridad directa en un carrusel
    #---------------------------------------------------------
    def usar_prioridad_directa_un_carrusel(self):

        if len(self.clasificadores_activos) != 1:
            return False

        if self.prioridad == "INVERSA":
            return True

        return self.hay_prioridad_paises_un_carrusel()

    #---------------------------------------------------------
    # Comprobar si la tienda activa usa inversa
    #---------------------------------------------------------
    def usar_prioridad_inversa_activa(self):

        if len(self.clasificadores_activos) != 1:
            return False

        return self.prioridad_tienda_activa == "INVERSA"

    #---------------------------------------------------------
    # Normalizar pais
    #---------------------------------------------------------
    def normalizar_pais(self, pais):

        if pais is None:
            return ""

        return str(pais).strip().upper()

    #---------------------------------------------------------
    # Normalizar configuracion de paises
    #---------------------------------------------------------
    def normalizar_configuracion_paises(self, configuracion):

        if configuracion is None:
            return {
                "Activo": False,
                "PaisesCLA1": [],
                "PaisesCLA2": [],
                "RestoAlOtro": False
            }

        paises_cla_1 = []
        paises_cla_2 = []

        for pais in configuracion.get("PaisesCLA1", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado not in paises_cla_1:
                paises_cla_1.append(pais_normalizado)

        for pais in configuracion.get("PaisesCLA2", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado not in paises_cla_2:
                paises_cla_2.append(pais_normalizado)

        return {
            "Activo": bool(configuracion.get("Activo", False)),
            "PaisesCLA1": paises_cla_1,
            "PaisesCLA2": paises_cla_2,
            "RestoAlOtro": bool(configuracion.get("RestoAlOtro", False))
        }


    #---------------------------------------------------------
    # Normalizar configuracion de prioridad por pais en un carrusel
    #---------------------------------------------------------
    def normalizar_configuracion_prioridad_paises(self, configuracion):

        if configuracion is None:
            return {
                "Activo": False,
                "PaisesNormal": [],
                "PaisesInversa": []
            }

        paises_normal = []
        paises_inversa = []

        for pais in configuracion.get("PaisesNormal", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado not in paises_normal:
                paises_normal.append(pais_normalizado)

        for pais in configuracion.get("PaisesInversa", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado not in paises_inversa:
                paises_inversa.append(pais_normalizado)

        return {
            "Activo": bool(configuracion.get("Activo", False)),
            "PaisesNormal": paises_normal,
            "PaisesInversa": paises_inversa
        }

    #---------------------------------------------------------
    # Hay prioridad por pais en un carrusel
    #---------------------------------------------------------
    def hay_prioridad_paises_un_carrusel(self):

        if self.configuracion_prioridad_paises is None:
            return False

        if len(self.clasificadores_activos) != 1:
            return False

        return self.configuracion_prioridad_paises.get("Activo", False)

    #---------------------------------------------------------
    # Obtener prioridad que corresponde a una tienda
    #---------------------------------------------------------
    def obtener_prioridad_tienda(self, tienda):

        prioridad = self.prioridad

        if not self.hay_prioridad_paises_un_carrusel():
            return prioridad

        pais = self.obtener_pais_tienda(tienda)

        if pais in self.configuracion_prioridad_paises.get("PaisesInversa", []):
            return "INVERSA"

        if pais in self.configuracion_prioridad_paises.get("PaisesNormal", []):
            return "NORMAL"

        return prioridad

    #---------------------------------------------------------
    # Obtener pais de tienda TMP
    #---------------------------------------------------------
    def obtener_pais_tienda(self, tienda):

        try:
            return self.normalizar_pais(tienda[3])
        except Exception:
            return ""

    #---------------------------------------------------------
    # Obtener clasificador forzado por pais
    #---------------------------------------------------------
    def obtener_clasificador_forzado_pais(self, tienda):

        if self.configuracion_paises is None:
            return None

        if not self.configuracion_paises.get("Activo", False):
            return None

        pais = self.obtener_pais_tienda(tienda)

        paises_cla_1 = self.configuracion_paises.get("PaisesCLA1", [])
        paises_cla_2 = self.configuracion_paises.get("PaisesCLA2", [])

        if pais in paises_cla_1:
            return 1

        if pais in paises_cla_2:
            return 2

        if self.configuracion_paises.get("RestoAlOtro", False):

            if len(paises_cla_1) > 0:
                return 2

            if len(paises_cla_2) > 0:
                return 1

        return None

    #---------------------------------------------------------
    # Comprobar si hay paises fijos
    #---------------------------------------------------------
    def hay_paises_fijos(self):

        if self.configuracion_paises is None:
            return False

        return self.configuracion_paises.get("Activo", False)

    #---------------------------------------------------------
    # Contar capacidad de un clasificador
    #---------------------------------------------------------
    def contar_capacidad_clasificador(self, clasificador):

        total = 0

        for destino in self.destinos:

            if destino["Clasificador"] == clasificador:
                total += 1

        return total

    #---------------------------------------------------------
    # Validar capacidad de paises forzados
    #---------------------------------------------------------
    def validar_capacidad_paises_forzados(self):

        if not self.hay_paises_fijos():
            return

        if sorted(self.clasificadores_activos) != [1, 2]:
            raise Exception("Los paises fijos solo se pueden usar con dos carruseles.")

        tiendas_forzadas = {1: 0, 2: 0}
        lotes_forzados = {1: 0, 2: 0}

        for tienda in self.tmp:

            clasificador = self.obtener_clasificador_forzado_pais(tienda)

            if clasificador is None:
                continue

            tiendas_forzadas[clasificador] += 1
            lotes_forzados[clasificador] += tienda[2]

        for clasificador in [1, 2]:

            capacidad = self.contar_capacidad_clasificador(clasificador)

            if tiendas_forzadas[clasificador] > capacidad:
                raise Exception(
                    "Los paises forzados al CLA "
                    + str(clasificador)
                    + " necesitan "
                    + str(tiendas_forzadas[clasificador])
                    + " destinos y solo hay "
                    + str(capacidad)
                    + "."
                )

    #---------------------------------------------------------
    # Cargar TMP_ESTAREPP
    #---------------------------------------------------------
    def cargar_tmp(self):

        if self.gestor_pedidos_trabajo is not None:
            self.tmp = self.gestor_pedidos_trabajo.obtener_detalle(
                self.clave_pedido_trabajo
            )
            return

        self.tmp = self.bd.consultar("""
            SELECT *
            FROM TMP_ESTAREPP
        """)

    #---------------------------------------------------------
    # Cargar destinos
    #---------------------------------------------------------
    def cargar_destinos(self):

        orden = "ASC"

        if self.usar_prioridad_inversa():
            orden = "DESC"

        datos = self.bd.consultar(f"""
            SELECT *
            FROM TablasDistribucionClasificador
            ORDER BY Prioridad_Orden {orden}
        """)

        self.destinos = []

        for fila in datos:

            if fila[0] not in self.clasificadores_activos:
                continue

            self.destinos.append({
                "Clasificador": fila[0],
                "Lado": fila[1],
                "Destino": fila[2],
                "Bloque": self.calcular_bloque_destino(fila[2]),
                "Tramo": 0,
                "Descripcion": fila[3],
                "Prioridad": fila[4],
                "PrioridadOrden": fila[5],
                "Libre": True,
                "Tienda": None,
                "Aparte": None,
                "Lotes": 0,
                "TipoCaja": ""
            })

    #---------------------------------------------------------
    # Calcular tramos de destino
    #---------------------------------------------------------
    def calcular_tramos_destinos(self):

        grupos = {}

        for destino in self.destinos:

            clave = (
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"]
            )

            bloque = destino["Bloque"]

            if clave not in grupos:
                grupos[clave] = {}

            if bloque not in grupos[clave]:
                grupos[clave][bloque] = destino["PrioridadOrden"]

            if self.usar_prioridad_inversa():

                if destino["PrioridadOrden"] > grupos[clave][bloque]:
                    grupos[clave][bloque] = destino["PrioridadOrden"]

            else:

                if destino["PrioridadOrden"] < grupos[clave][bloque]:
                    grupos[clave][bloque] = destino["PrioridadOrden"]

        tramos = {}

        for clave, bloques in grupos.items():

            bloques_ordenados = sorted(
                bloques.items(),
                key=lambda item: item[1],
                reverse=self.usar_prioridad_inversa()
            )

            numero_tramo = 1

            for bloque, prioridad in bloques_ordenados:
                tramos[(clave, bloque)] = numero_tramo
                numero_tramo += 1

        for destino in self.destinos:

            clave = (
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"]
            )

            destino["Tramo"] = tramos[(clave, destino["Bloque"])]

    #---------------------------------------------------------
    # Ordenar tiendas por tipo de caja
    #---------------------------------------------------------
    def ordenar_tiendas(self):

        orden_tipos = [
            "4_Nueva_40",
            "3_Usada_40",
            "2_Reutilizada_30",
            "1_Nueva_30"
        ]

        tiendas_ordenadas = []

        for tipo_caja in orden_tipos:

            tiendas_tipo = []

            for tienda in self.tmp:
                if tienda[4] == tipo_caja:
                    tiendas_tipo.append(tienda)

            tiendas_tipo = self.ordenar_tipo_caja_por_bloques(tiendas_tipo)
            tiendas_ordenadas.extend(tiendas_tipo)

        self.tmp = tiendas_ordenadas

    #---------------------------------------------------------
    # Ordenar un tipo de caja por bloques virtuales equilibrados
    #---------------------------------------------------------
    def ordenar_tipo_caja_por_bloques(self, tiendas):

        if len(tiendas) == 0:
            return []

        tiendas.sort(
            key=lambda r: r[2],
            reverse=True
        )

        numero_bloques = (len(tiendas) + self.tamano_bloque - 1) // self.tamano_bloque

        bloques = []

        for i in range(numero_bloques):
            bloques.append({"Tiendas": [], "Lotes": 0})

        for tienda in tiendas:

            bloque = self.buscar_bloque_virtual_menos_cargado(bloques)
            bloque["Tiendas"].append(tienda)
            bloque["Lotes"] += tienda[2]

        resultado = []

        for bloque in bloques:

            bloque["Tiendas"].sort(
                key=lambda r: r[2],
                reverse=True
            )

            for tienda in bloque["Tiendas"]:
                resultado.append(tienda)

        return resultado

    #---------------------------------------------------------
    # Buscar bloque virtual menos cargado
    #---------------------------------------------------------
    def buscar_bloque_virtual_menos_cargado(self, bloques):

        mejor_bloque = None
        menor_valor = None

        for bloque in bloques:

            if len(bloque["Tiendas"]) >= self.tamano_bloque:
                continue

            valor = (
                bloque["Lotes"],
                len(bloque["Tiendas"])
            )

            if menor_valor is None or valor < menor_valor:
                menor_valor = valor
                mejor_bloque = bloque

        return mejor_bloque

    #---------------------------------------------------------
    # Calcular numero de destinos a ocupar
    #---------------------------------------------------------
    def calcular_numero_destinos(self):

        self.numero_destinos = len(self.tmp)

        if self.numero_destinos == 0:
            self.ultimo_destino_previsto = None
            return

        if self.numero_destinos > len(self.destinos):
            self.ultimo_destino_previsto = self.destinos[-1]
        else:
            self.ultimo_destino_previsto = self.destinos[self.numero_destinos - 1]

    #---------------------------------------------------------
    # Resetear reparto en memoria
    #---------------------------------------------------------
    def resetear_reparto_en_memoria(self):

        self.clasificadores = self.crear_estadisticas_vacias()

        for destino in self.destinos:
            destino["Libre"] = True
            destino["Tienda"] = None
            destino["Aparte"] = None
            destino["Lotes"] = 0
            destino["TipoCaja"] = ""

    #---------------------------------------------------------
    # Calcular tiendas que irian a lado corto
    #---------------------------------------------------------
    def calcular_tiendas_previstas_lado_corto(self):

        if self.hay_paises_fijos():
            return self.calcular_tiendas_previstas_lado_corto_paises()

        capacidad_lado_largo = 0

        for destino in self.destinos:
            if destino["Descripcion"] == "Lado_Largo":
                capacidad_lado_largo += 1

        tiendas_lado_corto = len(self.tmp) - capacidad_lado_largo

        if tiendas_lado_corto < 0:
            tiendas_lado_corto = 0

        return tiendas_lado_corto

    #---------------------------------------------------------
    # Calcular lado corto con paises fijos
    #---------------------------------------------------------
    def calcular_tiendas_previstas_lado_corto_paises(self):

        opcion_anterior = self.opcion_lado_corto

        self.opcion_lado_corto = {
            "Numero": 1,
            "Nombre": "Automatico actual",
            "Modo": "AUTO",
            "LadosPermitidos": None
        }

        self.resetear_reparto_en_memoria()
        self.ejecutar_reparto_core()

        total = self.contar_destinos_lado_corto_asignados()

        self.resetear_reparto_en_memoria()
        self.opcion_lado_corto = opcion_anterior

        return total

    #---------------------------------------------------------
    # Contar destinos asignados
    #---------------------------------------------------------
    def contar_destinos_asignados(self):

        total = 0

        for destino in self.destinos:

            if destino["Tienda"] is not None:
                total += 1

        return total

    #---------------------------------------------------------
    # Contar destinos asignados a lado corto
    #---------------------------------------------------------
    def contar_destinos_lado_corto_asignados(self):

        total = 0

        for destino in self.destinos:

            if destino["Tienda"] is None:
                continue

            if destino["Descripcion"] == "Lado_corto":
                total += 1

        return total

    #---------------------------------------------------------
    # Validar reparto completo
    #---------------------------------------------------------
    def validar_reparto_completo(self):

        asignados = self.contar_destinos_asignados()
        esperados = len(self.tmp)

        if asignados == esperados:
            return

        pendientes = esperados - asignados

        raise Exception(
            "No se pudo completar el reparto con los paises fijos. "
            + "Quedaron "
            + str(pendientes)
            + " tiendas/apartes sin destino. Revisa la configuracion de paises o la opcion de Lado_corto."
        )

    #---------------------------------------------------------
    # Obtener capacidad de lados cortos
    #---------------------------------------------------------
    def obtener_capacidades_lados_cortos(self):

        capacidades = {}

        for destino in self.destinos:

            if destino["Descripcion"] != "Lado_corto":
                continue

            clave = (
                destino["Clasificador"],
                destino["Lado"]
            )

            if clave not in capacidades:
                capacidades[clave] = {
                    "Capacidad": 0,
                    "PrioridadOrden": destino["PrioridadOrden"]
                }

            capacidades[clave]["Capacidad"] += 1

            if destino["PrioridadOrden"] < capacidades[clave]["PrioridadOrden"]:
                capacidades[clave]["PrioridadOrden"] = destino["PrioridadOrden"]

        return capacidades

    #---------------------------------------------------------
    # Seleccionar opcion de lado corto
    #---------------------------------------------------------
    def seleccionar_lado_corto_operador(self):

        tiendas_lado_corto = self.calcular_tiendas_previstas_lado_corto()

        if tiendas_lado_corto <= 0:
            self.opcion_lado_corto = {
                "Numero": 1,
                "Nombre": "Automatico sin lado corto",
                "Modo": "AUTO",
                "LadosPermitidos": None
            }
            return

        opciones = self.generar_opciones_lado_corto(tiendas_lado_corto)

        for opcion in opciones:
            opcion["Resumen"] = self.simular_opcion_lado_corto(opcion)

        if self.hay_paises_fijos():
            opciones = self.filtrar_opciones_lado_corto_paises(opciones)

        recomendada = self.obtener_opcion_recomendada(opciones)

        self.opcion_lado_corto = seleccionar_opcion_lado_corto(
            opciones,
            recomendada
        )

    #---------------------------------------------------------
    # Filtrar opciones de lado corto con paises fijos
    #---------------------------------------------------------
    def filtrar_opciones_lado_corto_paises(self, opciones):

        opciones_validas = []

        for opcion in opciones:

            resumen = opcion.get("Resumen", {})

            if resumen.get("Valida", True):
                opciones_validas.append(opcion)

        if len(opciones_validas) == 0:
            raise Exception(
                "No hay ninguna opcion valida de Lado_corto para los paises fijos seleccionados."
            )

        numero = 1

        for opcion in opciones_validas:
            opcion["Numero"] = numero
            numero += 1

        return opciones_validas

    #---------------------------------------------------------
    # Generar opciones de lado corto
    #---------------------------------------------------------
    def generar_opciones_lado_corto(self, tiendas_lado_corto):

        capacidades = self.obtener_capacidades_lados_cortos()
        opciones = []
        numero = 1

        opciones.append({
            "Numero": numero,
            "Nombre": "Automatico actual",
            "Modo": "AUTO",
            "LadosPermitidos": None
        })
        numero += 1

        for clave, datos in sorted(capacidades.items()):

            clasificador, lado = clave

            if clasificador not in self.clasificadores_activos:
                continue

            if tiendas_lado_corto <= datos["Capacidad"]:

                opciones.append({
                    "Numero": numero,
                    "Nombre": "Todo en CLA " + str(clasificador) + " lado corto " + str(lado),
                    "Modo": "UNICO",
                    "LadosPermitidos": [clave]
                })
                numero += 1

        lados_c1 = []
        lados_c2 = []

        for clave, datos in capacidades.items():

            clasificador, lado = clave

            if clasificador == 1 and clasificador in self.clasificadores_activos:
                lados_c1.append((clave, datos))

            if clasificador == 2 and clasificador in self.clasificadores_activos:
                lados_c2.append((clave, datos))

        for clave1, datos1 in sorted(lados_c1):
            for clave2, datos2 in sorted(lados_c2):

                capacidad_total = datos1["Capacidad"] + datos2["Capacidad"]

                if tiendas_lado_corto > capacidad_total:
                    continue

                opciones.append({
                    "Numero": numero,
                    "Nombre": "Repartir en CLA " + str(clave1[0]) + " lado " + str(clave1[1]) + " y CLA " + str(clave2[0]) + " lado " + str(clave2[1]),
                    "Modo": "REPARTIDO",
                    "LadosPermitidos": [clave1, clave2]
                })
                numero += 1

        return opciones

    #---------------------------------------------------------
    # Simular una opcion de lado corto
    #---------------------------------------------------------
    def simular_opcion_lado_corto(self, opcion):

        opcion_anterior = self.opcion_lado_corto

        self.opcion_lado_corto = opcion
        self.resetear_reparto_en_memoria()
        self.ejecutar_reparto_core()

        resumen = self.obtener_resumen_opcion()

        self.resetear_reparto_en_memoria()
        self.opcion_lado_corto = opcion_anterior

        return resumen

    #---------------------------------------------------------
    # Obtener resumen de una simulacion
    #---------------------------------------------------------
    def obtener_resumen_opcion(self):

        resumen = {
            "Clasificadores": {},
            "LadosCortos": {}
        }

        for clasificador in self.clasificadores_activos:
            resumen["Clasificadores"][clasificador] = {
                "Lotes": self.clasificadores[clasificador]["Lotes"],
                "Tiendas": self.clasificadores[clasificador]["Tiendas"]
            }

        for destino in self.destinos:

            if destino["Tienda"] is None:
                continue

            if destino["Descripcion"] != "Lado_corto":
                continue

            clave = (
                destino["Clasificador"],
                destino["Lado"]
            )

            if clave not in resumen["LadosCortos"]:
                resumen["LadosCortos"][clave] = {
                    "Tiendas": 0,
                    "Lotes": 0
                }

            resumen["LadosCortos"][clave]["Tiendas"] += 1
            resumen["LadosCortos"][clave]["Lotes"] += destino["Lotes"]

        lotes = [datos["Lotes"] for datos in resumen["Clasificadores"].values()]
        tiendas = [datos["Tiendas"] for datos in resumen["Clasificadores"].values()]

        resumen["DiferenciaLotes"] = max(lotes) - min(lotes) if len(lotes) > 0 else 0
        resumen["DiferenciaTiendas"] = max(tiendas) - min(tiendas) if len(tiendas) > 0 else 0

        asignados = self.contar_destinos_asignados()
        esperados = len(self.tmp)
        pendientes = esperados - asignados

        if pendientes < 0:
            pendientes = 0

        resumen["RegistrosEsperados"] = esperados
        resumen["RegistrosAsignados"] = asignados
        resumen["RegistrosPendientes"] = pendientes
        resumen["Valida"] = pendientes == 0

        return resumen

    #---------------------------------------------------------
    # Obtener opcion recomendada
    #---------------------------------------------------------
    def obtener_opcion_recomendada(self, opciones):

        mejor = None
        menor = None

        for opcion in opciones:

            resumen = opcion["Resumen"]

            if self.hay_paises_fijos() and not resumen.get("Valida", True):
                continue

            valor = (
                resumen["DiferenciaLotes"],
                resumen["DiferenciaTiendas"],
                opcion["Numero"]
            )

            if menor is None or valor < menor:
                menor = valor
                mejor = opcion

        if mejor is None and len(opciones) > 0:
            mejor = opciones[0]

        return mejor

    #---------------------------------------------------------
    # Imprimir opcion de lado corto
    #---------------------------------------------------------
    def imprimir_opcion_lado_corto(self, opcion, recomendada):

        resumen = opcion["Resumen"]
        marca = ""

        if opcion["Numero"] == recomendada["Numero"]:
            marca = "  <-- recomendada"

        print()
        print(str(opcion["Numero"]) + ". " + opcion["Nombre"] + marca)

        for clasificador in sorted(resumen["Clasificadores"].keys()):
            datos = resumen["Clasificadores"][clasificador]
            print(
                "   CLA", clasificador,
                "| lotes:", datos["Lotes"],
                "| tiendas:", datos["Tiendas"]
            )

        print("   Diferencia lotes  :", resumen["DiferenciaLotes"])
        print("   Diferencia tiendas:", resumen["DiferenciaTiendas"])

        if len(resumen["LadosCortos"]) == 0:
            print("   Lado corto        : sin destinos en lado corto")
        else:
            for clave, datos in sorted(resumen["LadosCortos"].items()):
                clasificador, lado = clave
                print(
                    "   Lado corto        : CLA", clasificador,
                    "lado", lado,
                    "| tiendas:", datos["Tiendas"],
                    "| lotes:", datos["Lotes"]
                )

    #---------------------------------------------------------
    # Pedir opcion de lado corto
    #---------------------------------------------------------
    def pedir_opcion_lado_corto(self, opciones, recomendada):

        while True:

            texto = input(
                "Selecciona opcion de lado corto [ENTER = "
                + str(recomendada["Numero"])
                + "]: "
            ).strip()

            if texto == "":
                return recomendada

            try:
                numero = int(texto)
            except ValueError:
                print("Valor no valido.")
                continue

            for opcion in opciones:
                if opcion["Numero"] == numero:
                    return opcion

            print("Opcion no valida.")

    #---------------------------------------------------------
    # Ejecutar reparto core
    #---------------------------------------------------------
    def ejecutar_reparto_core(self):

        orden = [
            "4_Nueva_40",
            "3_Usada_40",
            "2_Reutilizada_30",
            "1_Nueva_30"
        ]

        for tipo_caja in orden:
            self.repartir_tipo_caja(tipo_caja)

    #---------------------------------------------------------
    # Repartir un tipo de caja
    #---------------------------------------------------------
    def repartir_tipo_caja(self, tipo_caja):

        self.tipo_caja_activo = tipo_caja

        for tienda in self.tmp:

            if tienda[4] != tipo_caja:
                continue

            destino = self.siguiente_destino(tienda)

            if destino is None:
                self.tipo_caja_activo = None
                return

            self.asignar_tienda(tienda, destino)

        self.tipo_caja_activo = None

    #---------------------------------------------------------
    # Validar destino segun opcion de lado corto
    #---------------------------------------------------------
    def destino_permitido_por_lado_corto(self, destino):

        if destino["Descripcion"] != "Lado_corto":
            return True

        if self.opcion_lado_corto is None:
            return True

        if self.opcion_lado_corto["Modo"] == "AUTO":
            return True

        lados_permitidos = self.opcion_lado_corto["LadosPermitidos"]

        if lados_permitidos is None:
            return True

        clave = (
            destino["Clasificador"],
            destino["Lado"]
        )

        return clave in lados_permitidos

    #---------------------------------------------------------
    # Siguiente destino
    #---------------------------------------------------------
    def siguiente_destino(self, tienda):

        self.prioridad_tienda_activa = self.obtener_prioridad_tienda(tienda)

        clasificador_forzado = self.obtener_clasificador_forzado_pais(tienda)

        if self.usar_prioridad_inversa_activa():
            return self.siguiente_destino_prioridad_directa(tienda, clasificador_forzado)

        descripcion = self.buscar_zona_activa(clasificador_forzado)

        if descripcion is None:
            return None

        clasificador = self.buscar_mejor_clasificador(
            descripcion,
            tienda,
            clasificador_forzado
        )

        if clasificador is None:
            return None

        return self.buscar_mejor_destino_en_clasificador(
            clasificador,
            descripcion,
            tienda
        )

    #---------------------------------------------------------
    # Siguiente destino por prioridad directa
    #---------------------------------------------------------
    def siguiente_destino_prioridad_directa(self, tienda, clasificador_forzado=None):

        descripcion = self.buscar_zona_activa(clasificador_forzado)

        if descripcion is None:
            return None

        if clasificador_forzado is not None:
            clasificador = clasificador_forzado
        elif len(self.clasificadores_activos) == 1:
            clasificador = self.clasificadores_activos[0]
        else:
            clasificador = self.buscar_mejor_clasificador(
                descripcion,
                tienda,
                clasificador_forzado
            )

        if clasificador is None:
            return None

        return self.buscar_mejor_destino_en_clasificador(
            clasificador,
            descripcion,
            tienda
        )

    #---------------------------------------------------------
    # Buscar zona activa
    #---------------------------------------------------------
    def buscar_zona_activa(self, clasificador_forzado=None):

        if self.usar_prioridad_inversa_activa():
            zonas = ["Lado_corto", "Lado_Largo"]
        else:
            zonas = ["Lado_Largo", "Lado_corto"]

        for zona in zonas:

            for destino in self.destinos:

                if not destino["Libre"]:
                    continue

                if destino["Clasificador"] not in self.clasificadores_activos:
                    continue

                if clasificador_forzado is not None and destino["Clasificador"] != clasificador_forzado:
                    continue

                if not self.destino_permitido_por_lado_corto(destino):
                    continue

                if destino["Descripcion"] == zona:
                    return zona

        return None

    #---------------------------------------------------------
    # Buscar mejor clasificador/carrusel
    #---------------------------------------------------------
    def buscar_mejor_clasificador(self, descripcion, tienda, clasificador_forzado=None):

        if clasificador_forzado is not None:

            if clasificador_forzado not in self.clasificadores_activos:
                return None

            if self.hay_destinos_libres_clasificador_zona(clasificador_forzado, descripcion):
                return clasificador_forzado

            return None

        candidatos = []

        for clasificador in self.clasificadores_activos:

            if not self.hay_destinos_libres_clasificador_zona(clasificador, descripcion):
                continue

            candidatos.append(clasificador)

        if len(candidatos) == 0:
            return None

        if len(candidatos) == 1:
            return candidatos[0]

        mejor_clasificador = None
        menor_valor = None

        for clasificador in candidatos:

            lotes_resultantes = {}
            tiendas_resultantes = {}

            for clasificador_activo in candidatos:
                lotes_resultantes[clasificador_activo] = self.clasificadores[clasificador_activo]["Lotes"]
                tiendas_resultantes[clasificador_activo] = self.clasificadores[clasificador_activo]["Tiendas"]

            lotes_resultantes[clasificador] += tienda[2]
            tiendas_resultantes[clasificador] += 1

            diferencia_lotes = max(lotes_resultantes.values()) - min(lotes_resultantes.values())
            diferencia_tiendas = max(tiendas_resultantes.values()) - min(tiendas_resultantes.values())

            valor = (
                diferencia_lotes,
                diferencia_tiendas,
                lotes_resultantes[clasificador],
                tiendas_resultantes[clasificador],
                clasificador
            )

            if menor_valor is None or valor < menor_valor:
                menor_valor = valor
                mejor_clasificador = clasificador

        return mejor_clasificador

    #---------------------------------------------------------
    # Comprobar destinos libres por clasificador y zona
    #---------------------------------------------------------
    def hay_destinos_libres_clasificador_zona(self, clasificador, descripcion):

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            return True

        return False

    #---------------------------------------------------------
    # Buscar mejor destino en clasificador elegido
    #---------------------------------------------------------
    def buscar_mejor_destino_en_clasificador(self, clasificador, descripcion, tienda):

        return self.buscar_mejor_destino_equilibrado_por_lado(
            clasificador,
            descripcion,
            tienda
        )

    #---------------------------------------------------------
    # Buscar mejor destino equilibrando por lado
    #---------------------------------------------------------
    def buscar_mejor_destino_equilibrado_por_lado(self, clasificador, descripcion, tienda):

        candidatos = self.obtener_primeros_destinos_libres_por_lado(
            clasificador,
            descripcion
        )

        if len(candidatos) == 0:
            return None

        mejor_destino = None
        mejor_valor = None

        for destino in candidatos:

            valor = self.valorar_destino_por_jerarquia(
                destino,
                tienda,
                descripcion
            )

            if mejor_valor is None or valor < mejor_valor:
                mejor_valor = valor
                mejor_destino = destino

        return mejor_destino

    #---------------------------------------------------------
    # Obtener primer destino libre de cada lado
    #---------------------------------------------------------
    def obtener_primeros_destinos_libres_por_lado(self, clasificador, descripcion):

        mejores_por_lado = {}

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            lado = destino["Lado"]
            prioridad = self.obtener_prioridad_comparable(destino)

            if lado not in mejores_por_lado:
                mejores_por_lado[lado] = destino
                continue

            prioridad_actual = self.obtener_prioridad_comparable(
                mejores_por_lado[lado]
            )

            if prioridad < prioridad_actual:
                mejores_por_lado[lado] = destino

        return list(mejores_por_lado.values())

    #---------------------------------------------------------
    # Prioridad comparable normal/inversa
    #---------------------------------------------------------
    def obtener_prioridad_comparable(self, destino):

        if self.usar_prioridad_inversa_activa():
            return self.calcular_prioridad_fisica_inversa(destino)

        return destino["PrioridadOrden"]

    #---------------------------------------------------------
    # Prioridad fisica inversa de un destino
    #---------------------------------------------------------
    def calcular_prioridad_fisica_inversa(self, destino):

        numero_destino = int(destino["Destino"])

        # Lado corto:
        # 44, 214, 43, 213, 42, 212...
        if 1 <= numero_destino <= 44:
            return (44 - numero_destino) * 2

        if 173 <= numero_destino <= 214:
            return ((214 - numero_destino) * 2) + 1

        # Lado largo:
        # 172, 215, 171, 216, 170, 217...
        if 45 <= numero_destino <= 172:
            return 1000 + ((172 - numero_destino) * 2)

        if 215 <= numero_destino <= 340:
            return 1000 + ((numero_destino - 215) * 2) + 1

        # Seguridad si aparece un destino fuera del plano esperado.
        return 9000 - int(destino["PrioridadOrden"])

    #---------------------------------------------------------
    # Valorar destino segun jerarquia general
    #---------------------------------------------------------
    def valorar_destino_por_jerarquia(self, destino, tienda, descripcion):

        clasificador = destino["Clasificador"]
        lado = destino["Lado"]
        tipo_caja = tienda[4]
        lotes = tienda[2]

        diferencia_lotes_lado = self.calcular_diferencia_lotes_lados_resultante(
            clasificador,
            descripcion,
            lado,
            lotes
        )

        diferencia_tipo_caja_lado = self.calcular_diferencia_tipo_caja_lados_resultante(
            clasificador,
            descripcion,
            lado,
            tipo_caja
        )

        lotes_lado_resultante = self.obtener_lotes_lado(
            clasificador,
            lado,
            descripcion
        ) + lotes

        cantidad_tipo_caja_lado_resultante = self.contar_tipo_caja_lado(
            clasificador,
            lado,
            descripcion,
            tipo_caja
        ) + 1

        prioridad = self.obtener_prioridad_comparable(destino)

        if self.usar_prioridad_inversa_activa():
            return (
                prioridad,
                diferencia_lotes_lado,
                diferencia_tipo_caja_lado,
                lotes_lado_resultante,
                cantidad_tipo_caja_lado_resultante
            )

        return (
            diferencia_lotes_lado,
            diferencia_tipo_caja_lado,
            lotes_lado_resultante,
            cantidad_tipo_caja_lado_resultante,
            prioridad
        )

    #---------------------------------------------------------
    # Obtener lados disponibles para equilibrar
    #---------------------------------------------------------
    def obtener_lados_disponibles_equilibrio(self, clasificador, descripcion):

        lados = []

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            lado = destino["Lado"]

            if lado not in lados:
                lados.append(lado)

        return lados

    #---------------------------------------------------------
    # Obtener lotes actuales de un lado
    #---------------------------------------------------------
    def obtener_lotes_lado(self, clasificador, lado, descripcion):

        try:
            return self.clasificadores[clasificador]["Lados"][lado][descripcion]
        except Exception:
            return 0

    #---------------------------------------------------------
    # Calcular diferencia de lotes por lados con candidato
    #---------------------------------------------------------
    def calcular_diferencia_lotes_lados_resultante(self, clasificador, descripcion, lado_candidato, lotes):

        lados = self.obtener_lados_disponibles_equilibrio(
            clasificador,
            descripcion
        )

        if lado_candidato not in lados:
            lados.append(lado_candidato)

        valores = []

        for lado in lados:

            total = self.obtener_lotes_lado(
                clasificador,
                lado,
                descripcion
            )

            if lado == lado_candidato:
                total += lotes

            valores.append(total)

        if len(valores) == 0:
            return 0

        return max(valores) - min(valores)

    #---------------------------------------------------------
    # Contar TipoCaja actual por lado
    #---------------------------------------------------------
    def contar_tipo_caja_lado(self, clasificador, lado, descripcion, tipo_caja):

        total = 0

        for destino in self.destinos:

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Lado"] != lado:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Tienda"] is None:
                continue

            if destino["TipoCaja"] == tipo_caja:
                total += 1

        return total

    #---------------------------------------------------------
    # Calcular diferencia de TipoCaja por lados con candidato
    #---------------------------------------------------------
    def calcular_diferencia_tipo_caja_lados_resultante(self, clasificador, descripcion, lado_candidato, tipo_caja):

        lados = self.obtener_lados_disponibles_equilibrio(
            clasificador,
            descripcion
        )

        if lado_candidato not in lados:
            lados.append(lado_candidato)

        valores = []

        for lado in lados:

            total = self.contar_tipo_caja_lado(
                clasificador,
                lado,
                descripcion,
                tipo_caja
            )

            if lado == lado_candidato:
                total += 1

            valores.append(total)

        if len(valores) == 0:
            return 0

        return max(valores) - min(valores)

    #---------------------------------------------------------
    # Buscar tramo activo dentro de un clasificador
    #---------------------------------------------------------
    def buscar_tramo_activo_clasificador(self, clasificador, descripcion):

        tramo_activo = None

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            if tramo_activo is None or destino["Tramo"] < tramo_activo:
                tramo_activo = destino["Tramo"]

        return tramo_activo

    #---------------------------------------------------------
    # Buscar mejor destino dentro del tramo activo del carrusel
    #---------------------------------------------------------
    def buscar_mejor_destino_en_tramo(self, clasificador, descripcion, tramo):

        candidatos = []
        bloques_revisados = set()

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Tramo"] != tramo:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            clave_bloque = (
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"],
                destino["Bloque"]
            )

            if clave_bloque in bloques_revisados:
                continue

            bloques_revisados.add(clave_bloque)

            primer_destino = self.buscar_primer_destino_libre_bloque(
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"],
                destino["Bloque"]
            )

            if primer_destino is not None:
                candidatos.append(primer_destino)

        mejor_destino = None
        menor_valor = None

        for destino in candidatos:

            lado = destino["Lado"]
            bloque = destino["Bloque"]

            lotes_lado = self.clasificadores[clasificador]["Lados"][lado][descripcion]

            lotes_bloque = self.calcular_lotes_bloque(
                clasificador,
                lado,
                descripcion,
                bloque
            )

            tiendas_bloque = self.calcular_tiendas_bloque(
                clasificador,
                lado,
                descripcion,
                bloque
            )

            prioridad_destino = destino["PrioridadOrden"]

            if self.usar_prioridad_inversa():
                prioridad_destino = prioridad_destino * -1

            valor = (
                lotes_bloque,
                tiendas_bloque,
                lotes_lado,
                prioridad_destino
            )

            if menor_valor is None or valor < menor_valor:
                menor_valor = valor
                mejor_destino = destino

        return mejor_destino

    #---------------------------------------------------------
    # Buscar primer destino libre dentro de un bloque
    #---------------------------------------------------------
    def buscar_primer_destino_libre_bloque(self, clasificador, lado, descripcion, bloque):

        for destino in self.destinos:

            if not destino["Libre"]:
                continue

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Lado"] != lado:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Bloque"] != bloque:
                continue

            if not self.destino_permitido_por_lado_corto(destino):
                continue

            return destino

        return None

    #---------------------------------------------------------
    # Calcular lotes de un bloque
    #---------------------------------------------------------
    def calcular_lotes_bloque(self, clasificador, lado, descripcion, bloque):

        total = 0

        for destino in self.destinos:

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Lado"] != lado:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Bloque"] != bloque:
                continue

            total += destino["Lotes"]

        return total

    #---------------------------------------------------------
    # Calcular tiendas de un bloque
    #---------------------------------------------------------
    def calcular_tiendas_bloque(self, clasificador, lado, descripcion, bloque):

        total = 0

        for destino in self.destinos:

            if destino["Clasificador"] != clasificador:
                continue

            if destino["Lado"] != lado:
                continue

            if destino["Descripcion"] != descripcion:
                continue

            if destino["Bloque"] != bloque:
                continue

            if destino["Tienda"] is not None:
                total += 1

        return total

    #---------------------------------------------------------
    # Asignar tienda
    #---------------------------------------------------------
    def asignar_tienda(self, tienda, destino):

        destino["Libre"] = False
        destino["Tienda"] = tienda[0]
        destino["Aparte"] = tienda[1]
        destino["Lotes"] = tienda[2]
        destino["TipoCaja"] = tienda[4]

        clasificador = destino["Clasificador"]
        lado = destino["Lado"]
        descripcion = destino["Descripcion"]

        self.clasificadores[clasificador]["Lotes"] += tienda[2]
        self.clasificadores[clasificador]["Tiendas"] += 1
        self.clasificadores[clasificador]["Lados"][lado][descripcion] += tienda[2]

    #---------------------------------------------------------
    # Guardar reparto final en SQLite
    #---------------------------------------------------------
    def guardar_reparto_clasificador(self):

        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS REPARTO_CLASIFICADOR (
                Clasificador INTEGER,
                Lado INTEGER,
                Zona TEXT,
                Tramo INTEGER,
                Bloque INTEGER,
                Destino INTEGER,
                Tienda INTEGER,
                Aparte INTEGER,
                Lotes REAL,
                TipoCaja TEXT,
                Prioridad INTEGER,
                PrioridadOrden INTEGER
            )
        """)

        self.bd.ejecutar("DELETE FROM REPARTO_CLASIFICADOR")

        total = 0

        for destino in self.destinos:

            if destino["Tienda"] is None:
                continue

            valores = (
                destino["Clasificador"],
                destino["Lado"],
                destino["Descripcion"],
                destino["Tramo"],
                destino["Bloque"],
                destino["Destino"],
                destino["Tienda"],
                destino["Aparte"],
                destino["Lotes"],
                destino["TipoCaja"],
                destino["Prioridad"],
                destino["PrioridadOrden"]
            )

            self.bd.insertar("REPARTO_CLASIFICADOR", valores)
            total += 1

        self.bd.guardar()

        return total

    #---------------------------------------------------------
    # Imprimir resumen final
    #---------------------------------------------------------
    def imprimir_resumen_final(self, total_guardado):

        lotes_c1 = self.clasificadores[1]["Lotes"]
        lotes_c2 = self.clasificadores[2]["Lotes"]
        tiendas_c1 = self.clasificadores[1]["Tiendas"]
        tiendas_c2 = self.clasificadores[2]["Tiendas"]

        print()
        print("----------------------------------------")
        print("REPARTO FINALIZADO")
        print("----------------------------------------")
        print("Tabla guardada        : REPARTO_CLASIFICADOR")
        print("Registros guardados   :", total_guardado)
        print("CLA 1 lotes           :", lotes_c1)
        print("CLA 2 lotes           :", lotes_c2)
        print("Diferencia lotes      :", abs(lotes_c1 - lotes_c2))
        print("CLA 1 tiendas         :", tiendas_c1)
        print("CLA 2 tiendas         :", tiendas_c2)
        print("Diferencia tiendas    :", abs(tiendas_c1 - tiendas_c2))
        print("Prioridad usada       :", self.prioridad)

        if self.hay_paises_fijos():
            print("Paises fijos         : SI")
            print("Paises CLA 1         :", ", ".join(self.configuracion_paises.get("PaisesCLA1", [])))
            print("Paises CLA 2         :", ", ".join(self.configuracion_paises.get("PaisesCLA2", [])))
        else:
            print("Paises fijos         : NO")

        if self.hay_prioridad_paises_un_carrusel():
            print("Prioridad por pais   : SI")
            print("Paises Normal        :", ", ".join(self.configuracion_prioridad_paises.get("PaisesNormal", [])))
            print("Paises Inversa       :", ", ".join(self.configuracion_prioridad_paises.get("PaisesInversa", [])))
        else:
            print("Prioridad por pais   : NO")

        if self.opcion_lado_corto is not None:
            print("Opcion lado corto     :", self.opcion_lado_corto["Nombre"])

        print("----------------------------------------")
