from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import csv
import tkinter as tk
from tkinter import filedialog

from bd.basedatos import BaseDatos
from modulos.algoritmo_xdoc_cajas import AlgoritmoXDOC
from modulos.algoritmo_limpieza_celdas_cajas import AlgoritmoLimpiezaCeldas
from modulos.algoritmo_mas_unidades_cajas import AlgoritmoMasUnidades


class MotorCalculoCajasPedido:

    # Regla operativa temporal: toda la volumetria XDOC usa exclusivamente
    # el perfil 01_UNICA. Se conserva PerfilVolumetria en tablas/resultados
    # solo por compatibilidad y trazabilidad.
    PERFIL_VOLUMETRIA_FIJO = "01_UNICA"

    def __init__(self):
        self.bd = BaseDatos()

        # Estado GLOBAL de la ejecucion. Se comparte entre XDOC, LIMPIEZA y
        # MAS UNIDADES. Una matricula usada no puede volver a aparecer.
        self.matriculas_usadas = set()

        # Cada fase mantiene su propia compensacion. XDOC conserva la carga
        # historica ponderada por lotes. LIMPIEZA usa una carga compuesta y
        # MAS UNIDADES equilibra exclusivamente NUMERO DE CAJAS/MOVIMIENTOS,
        # segun el estudio real de SILO.
        self.carga_pasillos = {str(i).zfill(2): 0 for i in range(1, 11)}
        self.carga_pasillos_limpieza = self.crear_carga_pasillos_limpieza()
        self.carga_pasillos_mas_unidades = self.crear_carga_pasillos_cajas()

        self.algoritmo_xdoc = AlgoritmoXDOC()
        self.algoritmo_limpieza = AlgoritmoLimpiezaCeldas()
        self.algoritmo_mas_unidades = AlgoritmoMasUnidades()

        # Indices en memoria para que el calculo no consulte SQLite por cada SKU.
        self.cajas_por_sku = defaultdict(list)
        self.moda_volumetria = {}
        self.moda_volumetria_base = {}
        self.moda_volumetria_perfil = {}
        self.moda_volumetria_base_perfil = {}
        self.moda_silo = {}

        # Ocupacion FISICA global. Una celda solo se considera limpia si salen
        # todas sus matriculas, aunque alguna pertenezca a otro SKU.
        self.ocupacion_celdas_global = {}

        # Configuracion XDOC por tienda. Ausencia en el maestro = tolerancia 0.
        # El perfil de volumetria es siempre 01_UNICA para todas las tiendas.
        self.tolerancias_xdoc = {}
        self.configuracion_xdoc = {}

        self.detalle_buffer = []
        self.resumen_buffer = []
        self.xdoc_resumen_buffer = []
        self.incidencias_buffer = []
        self.resumen_general = {}

    #---------------------------------------------------------
    # Tablas de trabajo y resultados
    #---------------------------------------------------------
    def crear_tablas(self):
        # Son tablas temporales/resultados del calculo de cajas. Se recrean en
        # cada ejecucion para garantizar tipos INTEGER y evitar arrastrar una
        # estructura antigua de versiones anteriores.
        for tabla in [
            "CAJAS_PEDIDO_DEMANDA",
            "CAJAS_RESULTADO_DETALLE",
            "CAJAS_RESULTADO_RESUMEN_SKU",
            "CAJAS_XDOC_RESUMEN",
            "CAJAS_RESULTADO_INCIDENCIAS",
            "CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR"
        ]:
            self.bd.ejecutar("DROP TABLE IF EXISTS " + tabla)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_PEDIDO_DEMANDA (
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                SKUClave TEXT,
                TipoProducto TEXT,
                Modelo TEXT,
                Calidad TEXT,
                Color TEXT,
                Talla TEXT,
                Campana TEXT,
                Anio TEXT,
                Cd TEXT,
                UxL INTEGER,
                DemandaInicial INTEGER,
                DemandaPendiente INTEGER,
                DemandaXDOC INTEGER,
                DemandaLimpieza INTEGER,
                DemandaMasUnidades INTEGER
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_RESULTADO_DETALLE (
                Algoritmo TEXT,
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                SKUClave TEXT,
                Matricula TEXT,
                Posicion TEXT,
                Pasillo TEXT,
                Lado TEXT,
                Celda TEXT,
                Profundidad TEXT,
                TCM TEXT,
                UnidadesCaja INTEGER,
                UnidadesUsadas INTEGER,
                UnidadesRetorno INTEGER,
                TipoMovimiento TEXT,
                CeldaLimpiada TEXT,
                Moda INTEGER,
                MotivoSeleccion TEXT
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_RESULTADO_RESUMEN_SKU (
                Algoritmo TEXT,
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                SKUClave TEXT,
                DemandaInicial INTEGER,
                DemandaPendiente INTEGER,
                StockDisponible INTEGER,
                Moda INTEGER,
                UnidadesBajadas INTEGER,
                UnidadesUsadas INTEGER,
                UnidadesRetorno INTEGER,
                CajasCompletas INTEGER,
                CajasRetorno INTEGER,
                CeldasLimpiadas INTEGER,
                Estado TEXT
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_XDOC_RESUMEN (
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                DemandaInicial INTEGER,
                Moda INTEGER,
                OrigenModa TEXT,
                PerfilVolumetria TEXT,
                ToleranciaXDOC INTEGER,
                MinimoCajaXDOC INTEGER,
                MaximoCajaXDOC INTEGER,
                CajasXDOC INTEGER,
                UnidadesXDOC INTEGER,
                IteracionesXDOC INTEGER,
                DesviacionModa INTEGER,
                CeldasLimpiasXDOC INTEGER,
                PendienteTrasXDOC INTEGER,
                Estado TEXT
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_RESULTADO_INCIDENCIAS (
                FechaHora TEXT,
                Algoritmo TEXT,
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                Tipo TEXT,
                Detalle TEXT
            )
        """)

        self.bd.ejecutar("""
            CREATE TABLE CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR (
                Tienda INTEGER,
                Aparte INTEGER,
                SKUCompleto TEXT,
                SKUClave TEXT,
                DemandaInicial INTEGER,
                DemandaXDOC INTEGER,
                DemandaLimpieza INTEGER,
                DemandaMasUnidades INTEGER,
                DemandaPendiente INTEGER,
                Estado TEXT
            )
        """)

        self.crear_indices_calculo()

    def crear_indices_calculo(self):
        for sql in [
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_DEMANDA_SKU ON CAJAS_PEDIDO_DEMANDA (SKUCompleto, Tienda, Aparte)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_DETALLE_EXPORT ON CAJAS_RESULTADO_DETALLE (Algoritmo, SKUCompleto, Tienda, Aparte)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_RESUMEN_EXPORT ON CAJAS_RESULTADO_RESUMEN_SKU (SKUCompleto, Tienda, Aparte, Algoritmo)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_XDOC_RESUMEN ON CAJAS_XDOC_RESUMEN (Tienda, Aparte, SKUCompleto)",
            "CREATE INDEX IF NOT EXISTS IDX_CAJAS_INCIDENCIAS ON CAJAS_RESULTADO_INCIDENCIAS (Algoritmo, SKUCompleto, Tienda, Aparte)"
        ]:
            try:
                self.bd.ejecutar(sql)
            except Exception:
                pass

    #---------------------------------------------------------
    # Normalizacion de SKU
    #---------------------------------------------------------
    def texto(self, valor):
        if valor is None:
            return ""
        return str(valor).strip()

    def numero(self, valor, defecto=0):
        """Unidades y lotes se trabajan siempre como enteros."""
        texto = self.texto(valor).replace(",", ".")
        if texto == "":
            return defecto
        try:
            return int(round(float(texto)))
        except Exception:
            return defecto

    def crear_carga_pasillos_limpieza(self):
        pasillos = [str(i).zfill(2) for i in range(1, 11)]
        return {
            "cajas": {pasillo: 0 for pasillo in pasillos},
            "lotes": {pasillo: 0 for pasillo in pasillos},
            "unidades": {pasillo: 0 for pasillo in pasillos}
        }

    def crear_carga_pasillos_cajas(self):
        """Carga independiente por numero de movimientos para MAS UNIDADES."""
        return {str(i).zfill(2): 0 for i in range(1, 11)}

    def clave_celda(self, caja):
        return self.texto(caja.get("Celda") or caja.get("Posicion"))

    def normalizar_estado_mercancia(self, valor):
        """Normaliza los alias historicos de UNICA al perfil fijo 01_UNICA."""
        perfil = self.texto(valor).upper().replace("-", "_").replace(" ", "_")
        while "__" in perfil:
            perfil = perfil.replace("__", "_")

        compacto = perfil.replace("_", "")
        if compacto in ("UNICA", "1UNICA", "01UNICA"):
            return self.PERFIL_VOLUMETRIA_FIJO

        return perfil or "SIN_PERFIL"

    def normalizar_perfil_xdoc(self, valor=None):
        # El valor del maestro se ignora deliberadamente: por ahora toda la
        # volumetria XDOC debe usar siempre 01_UNICA.
        return self.PERFIL_VOLUMETRIA_FIJO

    def entero_texto(self, valor, ancho):
        texto = self.texto(valor)
        try:
            texto = str(int(float(texto.replace(",", "."))))
        except Exception:
            pass
        return texto.zfill(ancho)

    def normalizar_talla(self, valor):
        """Talla SIEMPRE numerica. Nunca se usa TallaAlfa."""
        texto = self.texto(valor).replace(",", ".")
        if texto == "":
            return None
        try:
            numero = float(texto)
            entero = int(numero)
            if numero != entero:
                return None
            return entero
        except Exception:
            return None

    def normalizar_anio(self, valor):
        texto = self.texto(valor)
        try:
            return str(int(float(texto)))
        except Exception:
            return texto

    def crear_sku(self, modelo, calidad, color, talla, campana, anio):
        """
        CLAVE UNICA Y DEFINITIVA:
        Modelo / Calidad / Color / Talla numerica / Campana / Anio.
        """
        return "/".join([
            self.entero_texto(modelo, 4),
            self.entero_texto(calidad, 3),
            self.entero_texto(color, 3),
            str(int(talla)),
            self.texto(campana).upper(),
            self.normalizar_anio(anio)
        ])

    def sku_base_desde_sku(self, sku):
        partes = self.texto(sku).split("/")
        return "/".join(partes[:4]) if len(partes) >= 4 else self.texto(sku)

    #---------------------------------------------------------
    # Demanda del pedido
    #---------------------------------------------------------
    def preparar_demanda(
        self,
        tiendas_excluidas=None,
        skus_permitidos=None,
        tiendas_fijas=None,
    ):
        """
        XDOC se calcula por:
        Tienda + Aparte + Modelo/Calidad/Color/Talla/Campana/Anio.

        NO se separa por UxL y NO se utiliza TallaAlfa.

        ``tiendas_excluidas`` y ``skus_permitidos`` permiten ejecutar
        simulaciones de escenario sin modificar la tabla ESTAREPP. El filtro
        de SKU se calcula previamente sobre el pedido inicial completo de las
        tiendas normales y se mantiene fijo para todos los grupos.

        Las lineas de ``tiendas_fijas`` no se filtran por SKU. No obstante, si
        una tienda fija tambien esta en ``tiendas_excluidas``, se elimina igual
        que cualquier otra tienda del grupo.
        """
        self.bd.ejecutar("DELETE FROM CAJAS_PEDIDO_DEMANDA")
        self.bd.ejecutar("DELETE FROM CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR")

        registros = self.bd.consultar("""
            SELECT
                Tienda,
                Aparte,
                Modelo,
                Calidad,
                Color,
                TallaNum,
                Campaña,
                Año,
                UxL,
                Unidades
            FROM ESTAREPP
        """)

        agrupado = {}
        talla_invalida = 0

        tiendas_excluidas = {
            self.numero(valor, None)
            for valor in (tiendas_excluidas or set())
            if self.numero(valor, None) is not None
        }
        if skus_permitidos is not None:
            skus_permitidos = {self.texto(valor) for valor in skus_permitidos}
        tiendas_fijas = {
            self.numero(valor, None)
            for valor in (tiendas_fijas or set())
            if self.numero(valor, None) is not None
        }

        for tienda, aparte, modelo, calidad, color, talla_num, campana, anio, uxl, unidades in registros:
            tienda_num = self.numero(tienda, None)
            if tienda_num is not None and tienda_num in tiendas_excluidas:
                continue

            talla = self.normalizar_talla(talla_num)
            if talla is None:
                talla_invalida += 1
                continue

            sku = self.crear_sku(modelo, calidad, color, talla, campana, anio)
            es_tienda_fija = tienda_num is not None and tienda_num in tiendas_fijas
            if (
                skus_permitidos is not None
                and sku not in skus_permitidos
                and not es_tienda_fija
            ):
                continue

            clave = (tienda, aparte, sku)

            if clave not in agrupado:
                agrupado[clave] = {
                    "Tienda": tienda,
                    "Aparte": aparte,
                    "SKUCompleto": sku,
                    "SKUClave": sku,
                    "Modelo": self.entero_texto(modelo, 4),
                    "Calidad": self.entero_texto(calidad, 3),
                    "Color": self.entero_texto(color, 3),
                    "Talla": talla,
                    "Campana": self.texto(campana).upper(),
                    "Anio": self.normalizar_anio(anio),
                    "UxL": int(self.numero(uxl, 0)),
                    "DemandaInicial": 0
                }

            agrupado[clave]["DemandaInicial"] += self.numero(unidades, 0)

        cursor = self.bd.conexion.cursor()
        filas = []
        for datos in agrupado.values():
            filas.append((
                datos["Tienda"],
                datos["Aparte"],
                datos["SKUCompleto"],
                datos["SKUClave"],
                "",
                datos["Modelo"],
                datos["Calidad"],
                datos["Color"],
                datos["Talla"],
                datos["Campana"],
                datos["Anio"],
                "",
                datos["UxL"],
                datos["DemandaInicial"],
                datos["DemandaInicial"],
                0,
                0,
                0
            ))

        if filas:
            cursor.executemany("""
                INSERT INTO CAJAS_PEDIDO_DEMANDA
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, filas)
            self.bd.conexion.commit()

        if talla_invalida:
            print("AVISO: registros ESTAREPP omitidos por TallaNum no numerica:", talla_invalida)

        return len(agrupado)

    def cargar_demanda(self):
        filas = self.bd.consultar("""
            SELECT
                Tienda, Aparte, SKUCompleto, SKUClave,
                DemandaInicial, DemandaPendiente,
                IFNULL(DemandaXDOC, 0),
                IFNULL(DemandaLimpieza, 0),
                IFNULL(DemandaMasUnidades, 0)
            FROM CAJAS_PEDIDO_DEMANDA
            ORDER BY SKUCompleto, Tienda, Aparte
        """)

        resultado = []
        for fila in filas:
            tienda, aparte, sku, sku_clave, inicial, pendiente, xdoc, limpieza, mas = fila
            resultado.append({
                "Tienda": tienda,
                "Aparte": aparte,
                "SKUCompleto": self.texto(sku),
                "SKUClave": self.texto(sku_clave),
                "DemandaInicial": self.numero(inicial, 0),
                "DemandaPendiente": self.numero(pendiente, 0),
                "DemandaXDOC": self.numero(xdoc, 0),
                "DemandaLimpieza": self.numero(limpieza, 0),
                "DemandaMasUnidades": self.numero(mas, 0)
            })
        return resultado

    #---------------------------------------------------------
    # Carga masiva de cajas y volumetria en memoria
    #---------------------------------------------------------
    def cargar_indices_memoria(self):
        self.cajas_por_sku = defaultdict(list)
        self.moda_volumetria = {}
        self.moda_volumetria_base = {}
        self.moda_volumetria_perfil = {}
        self.moda_volumetria_base_perfil = {}
        self.moda_silo = {}
        ocupacion = defaultdict(set)

        # Se cargan todas las cajas fisicas disponibles para conocer la
        # ocupacion real de cada celda. Solo las que tienen SKU pueden ser
        # candidatas, pero una caja sin SKU tambien impide declarar la celda
        # como limpia.
        filas = self.bd.consultar("""
            SELECT
                Matricula, Posicion, Pasillo, Lado, Celda, Profundidad,
                TCM, Unidades, Lotes, SKUCompleto
            FROM CAJAS_CONTENEDORES
            WHERE Disponible = 1
              AND IFNULL(Unidades, 0) > 0
            ORDER BY SKUCompleto, Pasillo, Lado, Celda, Profundidad
        """)

        contadores_moda = defaultdict(Counter)
        for matricula, posicion, pasillo, lado, celda, profundidad, tcm, unidades, lotes, sku in filas:
            caja = {
                "Matricula": self.texto(matricula),
                "Posicion": self.texto(posicion),
                "Pasillo": self.texto(pasillo),
                "Lado": self.texto(lado),
                "Celda": self.texto(celda),
                "Profundidad": self.texto(profundidad),
                "TCM": self.texto(tcm),
                "Unidades": self.numero(unidades, 0),
                "Lotes": self.numero(lotes, 0),
                "SKU": self.texto(sku)
            }
            if caja["Matricula"] == "":
                continue

            clave_celda = self.clave_celda(caja)
            if clave_celda:
                ocupacion[clave_celda].add(caja["Matricula"])

            if caja["SKU"] == "":
                continue

            self.cajas_por_sku[caja["SKU"]].append(caja)
            unidades_moda = int(round(caja["Unidades"]))
            if unidades_moda > 0:
                contadores_moda[caja["SKU"]][unidades_moda] += 1

        self.ocupacion_celdas_global = {
            celda: set(matriculas)
            for celda, matriculas in ocupacion.items()
            if celda and matriculas
        }

        # En caso de empate de frecuencia no se elige automaticamente el valor
        # mayor. Se usa el menor como criterio determinista de seguridad.
        for sku, contador in contadores_moda.items():
            if contador:
                moda = sorted(contador.items(), key=lambda x: (-x[1], x[0]))[0][0]
                self.moda_silo[sku] = int(moda)

        # Regla temporal: se carga exclusivamente la volumetria 01_UNICA.
        # Se reconocen tambien los alias historicos UNICA, 1_UNICA y 01 UNICA.
        # PAIS5 y cualquier otro perfil se ignoran por completo.
        try:
            filas_vol = self.bd.consultar("""
                SELECT SKUCompleto, SKUBase, UdsBulto, EstadoMercancia
                FROM CAJAS_VOLUMETRIA
                WHERE IFNULL(UdsBulto, 0) > 0
            """)

            exactos = defaultdict(lambda: defaultdict(Counter))
            bases = defaultdict(lambda: defaultdict(Counter))
            for sku, sku_base, uds, perfil in filas_vol:
                valor = self.numero(uds, 0)
                if valor <= 0:
                    continue

                valor_clave = int(valor)
                sku = self.texto(sku)
                sku_base = self.texto(sku_base)
                perfil = self.normalizar_estado_mercancia(perfil)
                if perfil != self.PERFIL_VOLUMETRIA_FIJO:
                    continue

                if sku:
                    exactos[sku][perfil][valor_clave] += 1
                if sku_base:
                    bases[sku_base][perfil][valor_clave] += 1

            for sku, perfiles in exactos.items():
                self.moda_volumetria_perfil[sku] = {}
                for perfil, contador in perfiles.items():
                    moda = sorted(contador.items(), key=lambda x: (-x[1], x[0]))[0][0]
                    self.moda_volumetria_perfil[sku][perfil] = int(moda)

            for sku_base, perfiles in bases.items():
                self.moda_volumetria_base_perfil[sku_base] = {}
                for perfil, contador in perfiles.items():
                    moda = sorted(contador.items(), key=lambda x: (-x[1], x[0]))[0][0]
                    self.moda_volumetria_base_perfil[sku_base][perfil] = int(moda)

            # Mapas historicos conservados para compatibilidad. Su valor
            # representa siempre el perfil fijo 01_UNICA.
            for sku, perfiles in self.moda_volumetria_perfil.items():
                for perfil in self.ordenar_perfiles(perfiles):
                    self.moda_volumetria[sku] = perfiles[perfil]
                    break
            for sku_base, perfiles in self.moda_volumetria_base_perfil.items():
                for perfil in self.ordenar_perfiles(perfiles):
                    self.moda_volumetria_base[sku_base] = perfiles[perfil]
                    break
        except Exception:
            pass

    def ordenar_perfiles(self, perfiles):
        prioridad = {self.PERFIL_VOLUMETRIA_FIJO: 0}
        return sorted(
            perfiles.keys(),
            key=lambda perfil: (
                prioridad.get(self.normalizar_estado_mercancia(perfil), 9),
                self.texto(perfil)
            )
        )

    def cargar_cajas_sku(self, sku):
        """Devuelve exclusivamente cajas de ese SKU cuya matricula nunca se uso."""
        usadas = self.matriculas_usadas
        return [caja for caja in self.cajas_por_sku.get(self.texto(sku), []) if caja["Matricula"] not in usadas]

    def obtener_candidatos_moda_sku(self, sku, perfil=None):
        sku = self.texto(sku)
        perfil = self.PERFIL_VOLUMETRIA_FIJO

        def construir(mapa, clave, origen):
            perfiles = mapa.get(clave, {})
            if not perfiles:
                return []

            # Solo se admite 01_UNICA. La comprobacion normalizada permite
            # trabajar tambien con una base antigua que aun guarde UNICA.
            candidatos = []
            for nombre, moda in perfiles.items():
                if self.normalizar_estado_mercancia(nombre) != perfil:
                    continue
                valor_moda = self.numero(moda, 0)
                if valor_moda <= 0:
                    continue
                candidatos.append({
                    "Moda": valor_moda,
                    "Perfil": perfil,
                    "Origen": origen
                })

            return candidatos[:1]

        candidatos = construir(
            self.moda_volumetria_perfil,
            sku,
            "VOLUMETRIA"
        )
        if candidatos:
            return candidatos

        base = self.sku_base_desde_sku(sku)
        candidatos = construir(
            self.moda_volumetria_base_perfil,
            base,
            "VOLUMETRIA_BASE"
        )
        if candidatos:
            return candidatos

        if sku in self.moda_silo:
            return [{
                "Moda": self.numero(self.moda_silo[sku], 0),
                "Perfil": "SILO",
                "Origen": "SILO"
            }]

        return []

    def obtener_moda_sku(self, sku, perfil=None):
        candidatos = self.obtener_candidatos_moda_sku(sku, perfil)
        if candidatos:
            candidato = candidatos[0]
            return candidato["Moda"], candidato["Origen"]
        return 0, "SIN MODA"

    #---------------------------------------------------------
    # Maestro de tolerancias XDOC por tienda
    #---------------------------------------------------------
    def cargar_tolerancias_xdoc(self):
        self.tolerancias_xdoc = {}
        self.configuracion_xdoc = {}

        try:
            filas = self.bd.consultar("""
                SELECT Tienda, ToleranciaXDOC
                FROM TiendasXDOC
            """)
        except Exception:
            filas = []

        for tienda, tolerancia in filas:
            try:
                tienda_int = int(tienda)
            except Exception:
                continue

            tolerancia_int = max(0, min(100, self.numero(tolerancia, 0)))
            self.tolerancias_xdoc[tienda_int] = tolerancia_int
            self.configuracion_xdoc[tienda_int] = {
                "Tolerancia": tolerancia_int,
                "Perfil": self.PERFIL_VOLUMETRIA_FIJO
            }

    def obtener_configuracion_xdoc(self, tienda):
        configuracion_defecto = {
            "Tolerancia": 0,
            "Perfil": self.PERFIL_VOLUMETRIA_FIJO
        }
        try:
            tienda_int = int(tienda)
        except Exception:
            return dict(configuracion_defecto)

        configuracion = dict(self.configuracion_xdoc.get(
            tienda_int,
            configuracion_defecto
        ))
        configuracion["Perfil"] = self.PERFIL_VOLUMETRIA_FIJO
        return configuracion

    def obtener_tolerancia_xdoc(self, tienda):
        return int(self.obtener_configuracion_xdoc(tienda)["Tolerancia"])

    def obtener_perfil_xdoc(self, tienda):
        return self.obtener_configuracion_xdoc(tienda)["Perfil"]

    #---------------------------------------------------------
    # Demanda posterior a XDOC: una unica demanda por SKU
    #---------------------------------------------------------
    def agrupar_pendiente_por_sku(self, demandas):
        agrupado = {}
        for demanda in demandas:
            pendiente = self.numero(demanda.get("DemandaPendiente"), 0)
            if pendiente <= 0:
                continue

            sku = demanda["SKUCompleto"]
            if sku not in agrupado:
                agrupado[sku] = {
                    "Tienda": None,
                    "Aparte": None,
                    "SKUCompleto": sku,
                    "SKUClave": sku,
                    "DemandaInicial": 0,
                    "DemandaPendiente": 0,
                    "DemandaXDOC": 0,
                    "DemandaLimpieza": 0,
                    "DemandaMasUnidades": 0,
                    "Registros": []
                }

            agrupado[sku]["DemandaInicial"] += pendiente
            agrupado[sku]["DemandaPendiente"] += pendiente
            agrupado[sku]["Registros"].append(demanda)

        return [agrupado[sku] for sku in sorted(agrupado.keys())]

    def campo_algoritmo(self, algoritmo):
        if algoritmo == "XDOC":
            return "DemandaXDOC"
        if algoritmo == "LIMPIEZA_CELDAS":
            return "DemandaLimpieza"
        return "DemandaMasUnidades"

    def descontar_demanda(self, demanda, algoritmo, unidades_usadas):
        """
        XDOC descuenta directamente de Tienda+Aparte+SKU.
        LIMPIEZA/MAS UNIDADES descuentan la cobertura total del SKU sobre los
        registros de pedido que aun tienen demanda pendiente.
        """
        restante = max(0, self.numero(unidades_usadas, 0))
        campo = self.campo_algoritmo(algoritmo)

        if "Registros" not in demanda:
            usadas = min(restante, self.numero(demanda.get("DemandaPendiente"), 0))
            demanda[campo] = self.numero(demanda.get(campo), 0) + usadas
            demanda["DemandaPendiente"] = max(0, self.numero(demanda.get("DemandaPendiente"), 0) - usadas)
            return usadas

        usadas_totales = 0
        for registro in demanda["Registros"]:
            if restante <= 0:
                break
            pendiente = self.numero(registro.get("DemandaPendiente"), 0)
            if pendiente <= 0:
                continue
            usadas = min(pendiente, restante)
            registro[campo] = self.numero(registro.get(campo), 0) + usadas
            registro["DemandaPendiente"] = max(0, pendiente - usadas)
            restante -= usadas
            usadas_totales += usadas

        demanda[campo] = self.numero(demanda.get(campo), 0) + usadas_totales
        demanda["DemandaPendiente"] = max(0, self.numero(demanda.get("DemandaPendiente"), 0) - usadas_totales)
        return usadas_totales

    #---------------------------------------------------------
    # Celdas y seleccion
    #---------------------------------------------------------
    def calcular_celdas_limpiadas(self, cajas, seleccion_indices):
        matriculas = {
            self.texto(cajas[indice].get("Matricula"))
            for indice in seleccion_indices
            if self.texto(cajas[indice].get("Matricula"))
        }
        return {
            celda
            for celda, ocupantes in self.ocupacion_celdas_global.items()
            if ocupantes and set(ocupantes).issubset(matriculas)
        }

    def retirar_ocupacion_seleccionada(self, cajas, seleccion_indices):
        for indice in seleccion_indices:
            caja = cajas[indice]
            celda = self.clave_celda(caja)
            matricula = self.texto(caja.get("Matricula"))
            if not celda or not matricula:
                continue
            if celda not in self.ocupacion_celdas_global:
                continue
            self.ocupacion_celdas_global[celda].discard(matricula)
            if not self.ocupacion_celdas_global[celda]:
                del self.ocupacion_celdas_global[celda]

    def peso_pasillo(self, caja):
        lotes = self.numero(caja.get("Lotes"), 0)
        return lotes if lotes > 0 else 1

    def actualizar_carga_pasillo(self, algoritmo, caja):
        pasillo = self.texto(caja.get("Pasillo")) or "(SIN PASILLO)"
        if algoritmo == "LIMPIEZA_CELDAS":
            self.carga_pasillos_limpieza["cajas"][pasillo] = (
                self.carga_pasillos_limpieza["cajas"].get(pasillo, 0) + 1
            )
            self.carga_pasillos_limpieza["lotes"][pasillo] = (
                self.carga_pasillos_limpieza["lotes"].get(pasillo, 0)
                + self.peso_pasillo(caja)
            )
            self.carga_pasillos_limpieza["unidades"][pasillo] = (
                self.carga_pasillos_limpieza["unidades"].get(pasillo, 0)
                + self.numero(caja.get("Unidades"), 0)
            )
            return

        if algoritmo == "MAS_UNIDADES":
            self.carga_pasillos_mas_unidades[pasillo] = (
                self.carga_pasillos_mas_unidades.get(pasillo, 0) + 1
            )
            return

        # XDOC mantiene su ponderacion historica por lotes.
        self.carga_pasillos[pasillo] = (
            self.carga_pasillos.get(pasillo, 0) + self.peso_pasillo(caja)
        )

    def asegurar_retorno_si_hay_exceso(self, algoritmo, demanda, cajas, seleccion_indices, indice_retorno):
        if indice_retorno is not None or not seleccion_indices:
            return indice_retorno

        total = sum(self.numero(cajas[i].get("Unidades"), 0) for i in seleccion_indices)
        objetivo = self.numero(demanda.get("DemandaPendiente"), 0)
        if total <= objetivo:
            return None

        if algoritmo == "XDOC":
            raise Exception("Error interno XDOC: una seleccion supera la demanda de Tienda+Aparte+SKU.")

        # Seguridad: nunca se permiten dos retornos. Buscamos una unica caja que,
        # dejando completas las demas, absorba todo el exceso.
        for indice in reversed(seleccion_indices):
            sin_ella = total - self.numero(cajas[indice].get("Unidades"), 0)
            if sin_ella < objetivo:
                return indice

        raise Exception("No se pudo determinar una unica caja de retorno para el SKU " + demanda["SKUCompleto"])

    def guardar_seleccion(self, algoritmo, demanda, cajas, seleccion_indices, indice_retorno=None, moda=0, motivo=""):
        if not seleccion_indices:
            return

        # Validacion dura de la regla: una caja fisica solo puede aparecer UNA vez
        # en toda la ejecucion, independientemente del algoritmo.
        matriculas_locales = set()
        for indice in seleccion_indices:
            matricula = self.texto(cajas[indice].get("Matricula"))
            if matricula == "":
                raise Exception("Se intento seleccionar una caja sin matricula.")
            if matricula in matriculas_locales:
                raise Exception("La matricula " + matricula + " aparece dos veces en la misma seleccion.")
            if matricula in self.matriculas_usadas:
                raise Exception("La matricula " + matricula + " ya fue utilizada por un algoritmo anterior.")
            matriculas_locales.add(matricula)

        demanda_inicial = self.numero(demanda.get("DemandaPendiente"), 0)
        indice_retorno = self.asegurar_retorno_si_hay_exceso(
            algoritmo, demanda, cajas, seleccion_indices, indice_retorno
        )

        # La caja de retorno se procesa siempre la ultima; todas las anteriores
        # son cajas completas.
        orden = [i for i in seleccion_indices if i != indice_retorno]
        if indice_retorno is not None:
            orden.append(indice_retorno)

        celdas_limpiadas = self.calcular_celdas_limpiadas(cajas, seleccion_indices)
        tienda = demanda.get("Tienda")
        aparte = demanda.get("Aparte")
        sku = demanda["SKUCompleto"]

        unidades_bajadas = 0
        unidades_usadas = 0
        unidades_retorno = 0
        cajas_completas = 0
        cajas_retorno = 0
        restante = demanda_inicial

        for indice in orden:
            caja = cajas[indice]
            unidades_caja = self.numero(caja.get("Unidades"), 0)
            unidades_bajadas += unidades_caja

            if indice_retorno is not None and indice == indice_retorno:
                tipo_movimiento = "RETORNO"
                usadas = min(restante, unidades_caja)
                retorno = max(0, unidades_caja - usadas)
                cajas_retorno += 1
            else:
                tipo_movimiento = "COMPLETA"
                # Una caja completa se consume completa. Los algoritmos garantizan
                # que las completas no sobrepasan la demanda antes del retorno.
                usadas = unidades_caja
                retorno = 0
                cajas_completas += 1

            if usadas > restante and tipo_movimiento == "COMPLETA":
                raise Exception("Error interno: una caja marcada COMPLETA supera la demanda restante del SKU " + sku)

            restante = max(0, restante - usadas)
            unidades_usadas += usadas
            unidades_retorno += retorno

            self.matriculas_usadas.add(caja["Matricula"])
            self.actualizar_carga_pasillo(algoritmo, caja)

            self.detalle_buffer.append((
                algoritmo,
                tienda,
                aparte,
                sku,
                sku,
                caja["Matricula"],
                caja["Posicion"],
                caja["Pasillo"],
                caja["Lado"],
                caja["Celda"],
                caja["Profundidad"],
                caja["TCM"],
                unidades_caja,
                usadas,
                retorno,
                tipo_movimiento,
                "SI" if self.clave_celda(caja) in celdas_limpiadas else "NO",
                moda,
                motivo
            ))

        # La ocupacion se descuenta despues de calcular que celdas quedaron
        # completamente vacias en esta seleccion.
        self.retirar_ocupacion_seleccionada(cajas, seleccion_indices)

        stock_disponible = sum(self.numero(caja.get("Unidades"), 0) for caja in cajas)
        if unidades_usadas >= demanda_inicial:
            estado = "CUBIERTO"
        elif unidades_usadas <= 0:
            estado = "SIN SELECCION"
        else:
            estado = "PARCIAL"

        self.resumen_buffer.append((
            algoritmo,
            tienda,
            aparte,
            sku,
            sku,
            demanda_inicial,
            max(0, demanda_inicial - unidades_usadas),
            stock_disponible,
            moda,
            unidades_bajadas,
            unidades_usadas,
            unidades_retorno,
            cajas_completas,
            cajas_retorno,
            len(celdas_limpiadas),
            estado
        ))

        self.descontar_demanda(demanda, algoritmo, unidades_usadas)

    def guardar_sin_seleccion(self, algoritmo, demanda, stock_disponible, moda, estado):
        self.resumen_buffer.append((
            algoritmo,
            demanda.get("Tienda"),
            demanda.get("Aparte"),
            demanda["SKUCompleto"],
            demanda["SKUCompleto"],
            self.numero(demanda.get("DemandaPendiente"), 0),
            self.numero(demanda.get("DemandaPendiente"), 0),
            stock_disponible,
            moda,
            0, 0, 0, 0, 0, 0,
            estado
        ))

    def registrar_incidencia(self, algoritmo, demanda, tipo, detalle):
        self.incidencias_buffer.append((
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.texto(algoritmo),
            demanda.get("Tienda"),
            demanda.get("Aparte"),
            demanda.get("SKUCompleto"),
            self.texto(tipo),
            self.texto(detalle)
        ))

    #---------------------------------------------------------
    # Algoritmos
    #---------------------------------------------------------
    def registrar_resumen_xdoc(
        self,
        demanda,
        demanda_inicial,
        moda,
        origen_moda,
        perfil,
        tolerancia,
        minimo,
        maximo,
        cajas_xdoc,
        unidades_xdoc,
        iteraciones,
        desviacion,
        celdas_limpias,
        estado,
    ):
        self.xdoc_resumen_buffer.append((
            demanda.get("Tienda"),
            demanda.get("Aparte"),
            demanda["SKUCompleto"],
            self.numero(demanda_inicial, 0),
            self.numero(moda, 0),
            self.texto(origen_moda),
            self.texto(perfil),
            self.numero(tolerancia, 0),
            self.numero(minimo, 0),
            self.numero(maximo, 0),
            self.numero(cajas_xdoc, 0),
            self.numero(unidades_xdoc, 0),
            self.numero(iteraciones, 0),
            self.numero(desviacion, 0),
            self.numero(celdas_limpias, 0),
            self.numero(demanda.get("DemandaPendiente"), 0),
            self.texto(estado)
        ))

    def valor_candidato_moda_xdoc(self, candidato, diagnostico):
        iteraciones = max(1, self.numero(diagnostico.get("iteraciones"), 0))
        desviacion_media = (
            float(self.numero(diagnostico.get("desviacion_moda"), 0))
            / float(iteraciones)
        )
        prioridad_perfil = {
            self.PERFIL_VOLUMETRIA_FIJO: 0,
            "SILO": 1
        }
        perfil = self.texto(candidato.get("Perfil")).upper()

        # Primero se cubre la mayor demanda posible. En empate se elige la
        # seleccion mas proxima a su propia moda y con mas limpieza. El ultimo
        # desempate es el perfil, nunca el valor de moda mas alto.
        return (
            self.numero(diagnostico.get("demanda_pendiente"), 0),
            round(desviacion_media, 8),
            -self.numero(diagnostico.get("celdas_limpiadas"), 0),
            -self.numero(diagnostico.get("cajas_en_celdas_limpiadas"), 0),
            prioridad_perfil.get(perfil, 9),
            self.texto(perfil),
            self.numero(candidato.get("Moda"), 0)
        )

    def ejecutar_xdoc(self, demandas):
        # XDOC SIEMPRE por Tienda + Aparte + SKU. Cada moda se aplica de forma
        # iterativa sobre la demanda pendiente hasta que no queda otro lote
        # valido, sin superar nunca la demanda.
        for demanda in demandas:
            if demanda["DemandaPendiente"] <= 0:
                continue

            sku = demanda["SKUCompleto"]
            demanda_inicial = self.numero(demanda["DemandaPendiente"], 0)
            configuracion = self.obtener_configuracion_xdoc(demanda.get("Tienda"))
            tolerancia = configuracion["Tolerancia"]
            perfil_configurado = configuracion["Perfil"]
            cajas = self.cargar_cajas_sku(sku)
            candidatos_moda = self.obtener_candidatos_moda_sku(
                sku,
                perfil_configurado
            )

            if not cajas or not candidatos_moda:
                candidato = candidatos_moda[0] if candidatos_moda else {
                    "Moda": 0,
                    "Origen": "SIN MODA",
                    "Perfil": perfil_configurado
                }
                moda = self.numero(candidato["Moda"], 0)
                minimo, maximo = self.algoritmo_xdoc.calcular_rango(moda, tolerancia)
                estado = "SIN CAJAS O SIN MODA"
                self.guardar_sin_seleccion(
                    "XDOC",
                    demanda,
                    sum(c["Unidades"] for c in cajas),
                    moda,
                    estado
                )
                self.registrar_resumen_xdoc(
                    demanda, demanda_inicial, moda, candidato["Origen"],
                    candidato["Perfil"], tolerancia, minimo, maximo,
                    0, 0, 0, 0, 0, estado
                )
                continue

            evaluados = []
            for candidato in candidatos_moda:
                moda = self.numero(candidato.get("Moda"), 0)
                if moda <= 0:
                    continue
                diagnostico = self.algoritmo_xdoc.seleccionar_con_diagnostico(
                    demanda=demanda["DemandaPendiente"],
                    cajas=cajas,
                    moda=moda,
                    carga_pasillos=self.carga_pasillos,
                    tolerancia_xdoc=tolerancia,
                    ocupacion_celdas=self.ocupacion_celdas_global,
                )
                evaluados.append((
                    self.valor_candidato_moda_xdoc(candidato, diagnostico),
                    candidato,
                    diagnostico
                ))

            if not evaluados:
                estado = "SIN MODA VALIDA"
                self.guardar_sin_seleccion(
                    "XDOC", demanda, sum(c["Unidades"] for c in cajas), 0, estado
                )
                self.registrar_resumen_xdoc(
                    demanda, demanda_inicial, 0, "SIN MODA", perfil_configurado,
                    tolerancia, 0, 0, 0, 0, 0, 0, 0, estado
                )
                continue

            _, candidato, diagnostico = min(evaluados, key=lambda item: item[0])
            seleccion = diagnostico["indices"]
            moda = self.numero(candidato["Moda"], 0)
            origen_moda = candidato["Origen"]
            perfil_usado = candidato["Perfil"]
            minimo, maximo = self.algoritmo_xdoc.calcular_rango(moda, tolerancia)

            if not seleccion:
                estado = "SIN XDOC"
                self.guardar_sin_seleccion(
                    "XDOC",
                    demanda,
                    sum(c["Unidades"] for c in cajas),
                    moda,
                    estado
                )
                self.registrar_resumen_xdoc(
                    demanda, demanda_inicial, moda, origen_moda, perfil_usado,
                    tolerancia, minimo, maximo, 0, 0,
                    diagnostico.get("iteraciones", 0),
                    diagnostico.get("desviacion_moda", 0),
                    diagnostico.get("celdas_limpiadas", 0),
                    estado
                )
                continue

            unidades_xdoc = self.numero(diagnostico.get("unidades"), 0)
            motivo = (
                "MODA " + origen_moda
                + " | PERFIL " + str(perfil_usado)
                + " | TOL " + str(tolerancia) + "%"
                + " | RANGO " + str(minimo) + "-" + str(maximo)
                + " | ITERACIONES " + str(diagnostico.get("iteraciones", 0))
                + " | CELDAS " + str(diagnostico.get("celdas_limpiadas", 0))
            )

            self.guardar_seleccion(
                "XDOC", demanda, cajas, seleccion, None, moda, motivo
            )

            estado = "CUBIERTO" if demanda.get("DemandaPendiente", 0) <= 0 else "PARCIAL"
            self.registrar_resumen_xdoc(
                demanda, demanda_inicial, moda, origen_moda, perfil_usado,
                tolerancia, minimo, maximo, len(seleccion), unidades_xdoc,
                diagnostico.get("iteraciones", 0),
                diagnostico.get("desviacion_moda", 0),
                diagnostico.get("celdas_limpiadas", 0),
                estado
            )

    def ejecutar_limpieza_celdas(self, demandas):
        # SILO no parece heredar de forma fuerte el desequilibrio de XDOC. La
        # compensacion de Limpieza empieza de cero y combina cajas/lotes/uds.
        self.carga_pasillos_limpieza = self.crear_carga_pasillos_limpieza()

        # Despues de XDOC se agrega TODO el pendiente por SKU.
        for demanda in self.agrupar_pendiente_por_sku(demandas):
            if demanda["DemandaPendiente"] <= 0:
                continue

            sku = demanda["SKUCompleto"]
            cajas = self.cargar_cajas_sku(sku)
            moda, _ = self.obtener_moda_sku(sku)

            if not cajas:
                self.guardar_sin_seleccion(
                    "LIMPIEZA_CELDAS", demanda, 0, moda, "SIN CAJAS"
                )
                continue

            seleccion, retorno, motivo = self.algoritmo_limpieza.seleccionar(
                demanda=demanda["DemandaPendiente"],
                cajas=cajas,
                carga_pasillos=self.carga_pasillos_limpieza,
                ocupacion_celdas=self.ocupacion_celdas_global,
            )

            if not seleccion:
                stock = sum(c["Unidades"] for c in cajas)
                self.guardar_sin_seleccion(
                    "LIMPIEZA_CELDAS", demanda, stock, moda, "SIN SELECCION"
                )
                if stock >= self.numero(demanda["DemandaPendiente"], 0):
                    self.registrar_incidencia(
                        "LIMPIEZA_CELDAS",
                        demanda,
                        "SIN_SELECCION_CON_STOCK",
                        "Habia stock suficiente, pero no se pudo reconciliar una seleccion con maximo un retorno."
                    )
                continue

            self.guardar_seleccion(
                "LIMPIEZA_CELDAS", demanda, cajas, seleccion, retorno, moda, motivo
            )

    def ejecutar_mas_unidades(self, demandas):
        # El estudio real muestra que MAS UNIDADES compensa movimientos/cajas
        # de forma independiente. No hereda la carga por lotes de XDOC.
        self.carga_pasillos_mas_unidades = self.crear_carga_pasillos_cajas()

        # MUY IMPORTANTE: despues de XDOC se agrega TODO el pendiente por SKU.
        for demanda in self.agrupar_pendiente_por_sku(demandas):
            if demanda["DemandaPendiente"] <= 0:
                continue

            sku = demanda["SKUCompleto"]
            cajas = self.cargar_cajas_sku(sku)
            moda, _ = self.obtener_moda_sku(sku)

            if not cajas:
                self.guardar_sin_seleccion(
                    "MAS_UNIDADES", demanda, 0, moda, "SIN CAJAS"
                )
                continue

            diagnostico = self.algoritmo_mas_unidades.seleccionar_con_diagnostico(
                demanda=demanda["DemandaPendiente"],
                cajas=cajas,
                carga_pasillos=self.carga_pasillos_mas_unidades,
                ocupacion_celdas=self.ocupacion_celdas_global,
            )
            seleccion = diagnostico.get("indices", [])
            retorno = diagnostico.get("retorno")

            if not seleccion:
                self.guardar_sin_seleccion(
                    "MAS_UNIDADES",
                    demanda,
                    sum(self.numero(c.get("Unidades"), 0) for c in cajas),
                    moda,
                    diagnostico.get("motivo", "SIN SELECCION"),
                )
                continue

            self.guardar_seleccion(
                "MAS_UNIDADES",
                demanda,
                cajas,
                seleccion,
                retorno,
                moda,
                diagnostico.get("motivo", "TOP-K MAYORES"),
            )

            if not diagnostico.get("stock_suficiente", False):
                self.registrar_incidencia(
                    "MAS_UNIDADES",
                    demanda,
                    "STOCK_INSUFICIENTE",
                    "Se seleccionaron todas las cajas disponibles, pero no cubren la demanda pendiente.",
                )

    #---------------------------------------------------------
    # Persistencia masiva
    #---------------------------------------------------------
    def volcar_buffers(self):
        cursor = self.bd.conexion.cursor()
        if self.detalle_buffer:
            cursor.executemany("""
                INSERT INTO CAJAS_RESULTADO_DETALLE
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, self.detalle_buffer)
        if self.resumen_buffer:
            cursor.executemany("""
                INSERT INTO CAJAS_RESULTADO_RESUMEN_SKU
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, self.resumen_buffer)
        if self.xdoc_resumen_buffer:
            cursor.executemany("""
                INSERT INTO CAJAS_XDOC_RESUMEN
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, self.xdoc_resumen_buffer)
        if self.incidencias_buffer:
            cursor.executemany("""
                INSERT INTO CAJAS_RESULTADO_INCIDENCIAS
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, self.incidencias_buffer)
        self.bd.conexion.commit()
        self.detalle_buffer = []
        self.resumen_buffer = []
        self.xdoc_resumen_buffer = []
        self.incidencias_buffer = []

    def actualizar_demanda_bd(self, demandas):
        registros = []
        for d in demandas:
            registros.append((
                self.numero(d.get("DemandaPendiente"), 0),
                self.numero(d.get("DemandaXDOC"), 0),
                self.numero(d.get("DemandaLimpieza"), 0),
                self.numero(d.get("DemandaMasUnidades"), 0),
                d["Tienda"], d["Aparte"], d["SKUCompleto"]
            ))

        if registros:
            cursor = self.bd.conexion.cursor()
            cursor.executemany("""
                UPDATE CAJAS_PEDIDO_DEMANDA
                SET DemandaPendiente = ?,
                    DemandaXDOC = ?,
                    DemandaLimpieza = ?,
                    DemandaMasUnidades = ?
                WHERE Tienda = ?
                  AND IFNULL(Aparte, 0) = IFNULL(?, 0)
                  AND SKUCompleto = ?
            """, registros)
            self.bd.conexion.commit()

    def generar_pendiente_clasificador(self):
        self.bd.ejecutar("DELETE FROM CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR")
        filas = self.bd.consultar("""
            SELECT Tienda, Aparte, SKUCompleto, SKUClave,
                   DemandaInicial, DemandaXDOC, IFNULL(DemandaLimpieza, 0),
                   DemandaMasUnidades, DemandaPendiente
            FROM CAJAS_PEDIDO_DEMANDA
            ORDER BY SKUCompleto, Tienda, Aparte
        """)

        cursor = self.bd.conexion.cursor()
        salida = []
        for fila in filas:
            tienda, aparte, sku, sku_clave, inicial, xdoc, limpieza, mas, pendiente = fila
            pendiente = self.numero(pendiente, 0)
            estado = "SIN PENDIENTE" if pendiente <= 0 else "PENDIENTE CLASIFICADOR"
            salida.append((
                tienda, aparte, sku, sku_clave,
                self.numero(inicial, 0), self.numero(xdoc, 0),
                self.numero(limpieza, 0), self.numero(mas, 0),
                pendiente, estado
            ))

        if salida:
            cursor.executemany("""
                INSERT INTO CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, salida)
            self.bd.conexion.commit()

    #---------------------------------------------------------
    # Ejecucion completa
    #---------------------------------------------------------
    def calcular(
        self,
        modo="XDOC_LIMPIEZA",
        tiendas_excluidas=None,
        skus_permitidos=None,
        tiendas_fijas=None,
    ):
        self.crear_tablas()
        self.bd.ejecutar("DELETE FROM CAJAS_RESULTADO_DETALLE")
        self.bd.ejecutar("DELETE FROM CAJAS_RESULTADO_RESUMEN_SKU")

        self.matriculas_usadas = set()
        self.carga_pasillos = {str(i).zfill(2): 0 for i in range(1, 11)}
        self.carga_pasillos_limpieza = self.crear_carga_pasillos_limpieza()
        self.carga_pasillos_mas_unidades = self.crear_carga_pasillos_cajas()
        self.ocupacion_celdas_global = {}
        self.detalle_buffer = []
        self.resumen_buffer = []
        self.xdoc_resumen_buffer = []
        self.incidencias_buffer = []

        self.preparar_demanda(
            tiendas_excluidas=tiendas_excluidas,
            skus_permitidos=skus_permitidos,
            tiendas_fijas=tiendas_fijas,
        )
        demandas = self.cargar_demanda()
        self.cargar_indices_memoria()
        self.cargar_tolerancias_xdoc()

        # Las tres opciones SIEMPRE empiezan por XDOC.
        self.ejecutar_xdoc(demandas)

        if modo == "XDOC_LIMPIEZA":
            self.ejecutar_limpieza_celdas(demandas)
        elif modo == "XDOC_MAS_UNIDADES":
            self.ejecutar_mas_unidades(demandas)
        elif modo != "XDOC":
            raise Exception("Tipo de calculo no reconocido: " + str(modo))

        self.actualizar_demanda_bd(demandas)
        self.volcar_buffers()
        self.generar_pendiente_clasificador()
        self.bd.guardar()

        self.validar_matriculas_resultado()
        self.resumen_general = self.obtener_resumen_general()
        return self.resumen_general

    def validar_matriculas_resultado(self):
        duplicadas = self.bd.consultar("""
            SELECT Matricula, COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            GROUP BY Matricula
            HAVING COUNT(*) > 1
        """)
        if duplicadas:
            raise Exception("ERROR DE SEGURIDAD: una o mas matriculas fueron utilizadas mas de una vez: " + str(duplicadas[:10]))

    #---------------------------------------------------------
    # Resumen
    #---------------------------------------------------------
    def obtener_resumen_general(self):
        resumen = {
            "SkusPedido": 0,
            "CajasCompletas": 0,
            "CajasRetorno": 0,
            "CeldasLimpiadas": 0,
            "UnidadesRetorno": 0,
            "Incidencias": 0,
            "PorAlgoritmo": [],
            "PorTCM": [],
            "PorPasillo": [],
            "PendientesClasificador": 0,
            "UnidadesPendientesClasificador": 0,
            "CajasReservadasXDOC": 0,
            "UnidadesCubiertasXDOC": 0,
            "CajasXDOCPorTCM": [],
            "CajasCarruselTotal": 0,
            "CajasCarruselCompletas": 0,
            "CajasCarruselRetorno": 0,
            "CajasCarruselPorTCM": [],
            "CajasCarruselCompletasPorTCM": [],
            "CajasCarruselRetornoPorTCM": [],
            "Cajas400CarruselReutilizables": 0,
            "CajasReservadasTotal": 0,
            "AgotadasPorTCM": [],
            "Cajas400Agotadas": 0,
            "DetalleXDOC": [],
            "DetalleIncidencias": [],
            "EvolucionDemanda": []
        }

        datos = self.bd.consultar("SELECT COUNT(DISTINCT SKUCompleto) FROM CAJAS_PEDIDO_DEMANDA")
        if datos:
            resumen["SkusPedido"] = datos[0][0]

        datos = self.bd.consultar("""
            SELECT
                IFNULL(SUM(CajasCompletas), 0),
                IFNULL(SUM(CajasRetorno), 0),
                IFNULL(SUM(CeldasLimpiadas), 0),
                IFNULL(SUM(UnidadesRetorno), 0),
                IFNULL(SUM(CASE WHEN Estado NOT IN ('CUBIERTO', 'PARCIAL', 'SIN XDOC') THEN 1 ELSE 0 END), 0)
            FROM CAJAS_RESULTADO_RESUMEN_SKU
        """)
        if datos:
            resumen["CajasCompletas"] = datos[0][0]
            resumen["CajasRetorno"] = datos[0][1]
            resumen["CeldasLimpiadas"] = datos[0][2]
            resumen["UnidadesRetorno"] = datos[0][3]
            resumen["Incidencias"] = datos[0][4]

        resumen["PorAlgoritmo"] = self.bd.consultar("""
            SELECT Algoritmo,
                   SUM(CASE WHEN TipoMovimiento = 'COMPLETA' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN TipoMovimiento = 'RETORNO' THEN 1 ELSE 0 END),
                   COUNT(*),
                   IFNULL(SUM(UnidadesUsadas), 0),
                   IFNULL(SUM(UnidadesRetorno), 0)
            FROM CAJAS_RESULTADO_DETALLE
            GROUP BY Algoritmo
            ORDER BY Algoritmo
        """)

        resumen["PorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)

        resumen["CajasReservadasTotal"] = int(resumen.get("CajasCompletas", 0) or 0) + int(resumen.get("CajasRetorno", 0) or 0)

        # Desglose operativo: XDOC va directo a expediciones y NO se reutiliza.
        # Las cajas para carruseles son exclusivamente las seleccionadas por
        # LIMPIEZA_CELDAS o MAS_UNIDADES despues de descontar XDOC.
        resumen["CajasXDOCPorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo = 'XDOC'
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)

        carrusel_totales = self.bd.consultar("""
            SELECT
                COUNT(*),
                SUM(CASE WHEN TipoMovimiento = 'COMPLETA' THEN 1 ELSE 0 END),
                SUM(CASE WHEN TipoMovimiento = 'RETORNO' THEN 1 ELSE 0 END)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo <> 'XDOC'
        """)
        if carrusel_totales:
            resumen["CajasCarruselTotal"] = int(carrusel_totales[0][0] or 0)
            resumen["CajasCarruselCompletas"] = int(carrusel_totales[0][1] or 0)
            resumen["CajasCarruselRetorno"] = int(carrusel_totales[0][2] or 0)

        resumen["CajasCarruselPorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo <> 'XDOC'
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)
        resumen["CajasCarruselCompletasPorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo <> 'XDOC' AND TipoMovimiento = 'COMPLETA'
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)
        resumen["CajasCarruselRetornoPorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo <> 'XDOC' AND TipoMovimiento = 'RETORNO'
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)

        # Se conserva el resumen historico de todas las cajas completas para no
        # romper otras partes de la aplicacion que puedan consultarlo.
        resumen["AgotadasPorTCM"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)'), COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE TipoMovimiento = 'COMPLETA'
            GROUP BY IFNULL(NULLIF(TRIM(TCM), ''), '(SIN TCM)')
            ORDER BY 1
        """)

        # Para reutilizacion por pais SOLO cuentan las cajas 400 completas que
        # van a carruseles. Las XDOC van directas a expediciones y las de retorno
        # vuelven al silo con mercancia, por lo que ninguna de ellas se reutiliza.
        cajas_400_carrusel = 0
        for tcm, cantidad in resumen["CajasCarruselCompletasPorTCM"]:
            texto_tcm = str(tcm or '').lower().replace(' ', '')
            if '580x380x400' in texto_tcm:
                cajas_400_carrusel += int(cantidad or 0)
        resumen["Cajas400CarruselReutilizables"] = cajas_400_carrusel

        # Compatibilidad con versiones anteriores: este campo pasa a representar
        # el objetivo REAL de reutilizacion, no todas las cajas 400 agotadas.
        resumen["Cajas400Agotadas"] = cajas_400_carrusel

        resumen["PorPasillo"] = self.bd.consultar("""
            SELECT IFNULL(NULLIF(TRIM(Pasillo), ''), '(SIN PASILLO)'),
                   SUM(CASE WHEN TipoMovimiento = 'COMPLETA' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN TipoMovimiento = 'RETORNO' THEN 1 ELSE 0 END),
                   COUNT(*)
            FROM CAJAS_RESULTADO_DETALLE
            GROUP BY IFNULL(NULLIF(TRIM(Pasillo), ''), '(SIN PASILLO)')
            ORDER BY 1
        """)

        xdoc_totales = self.bd.consultar("""
            SELECT COUNT(*), IFNULL(SUM(UnidadesUsadas), 0)
            FROM CAJAS_RESULTADO_DETALLE
            WHERE Algoritmo = 'XDOC'
        """)
        if xdoc_totales:
            resumen["CajasReservadasXDOC"] = int(xdoc_totales[0][0] or 0)
            resumen["UnidadesCubiertasXDOC"] = int(xdoc_totales[0][1] or 0)

        incidencias = self.bd.consultar("""
            SELECT FechaHora, Algoritmo, Tienda, Aparte, SKUCompleto, Tipo, Detalle
            FROM CAJAS_RESULTADO_INCIDENCIAS
            ORDER BY FechaHora, Algoritmo, SKUCompleto, Tienda, Aparte
        """)
        resumen["DetalleIncidencias"] = incidencias
        resumen["Incidencias"] = len(incidencias)

        resumen["DetalleXDOC"] = self.bd.consultar("""
            SELECT Tienda, Aparte, SKUCompleto, DemandaInicial, Moda, OrigenModa,
                   PerfilVolumetria, ToleranciaXDOC, MinimoCajaXDOC, MaximoCajaXDOC,
                   CajasXDOC, UnidadesXDOC, IteracionesXDOC, DesviacionModa,
                   CeldasLimpiasXDOC, PendienteTrasXDOC, Estado
            FROM CAJAS_XDOC_RESUMEN
            ORDER BY Tienda, Aparte, SKUCompleto
        """)

        resumen["EvolucionDemanda"] = self.bd.consultar("""
            WITH demanda AS (
                SELECT
                    SKUCompleto,
                    CAST(IFNULL(SUM(DemandaInicial), 0) AS INTEGER) AS DemandaInicial,
                    CAST(IFNULL(SUM(DemandaXDOC), 0) AS INTEGER) AS DemandaXDOC,
                    CAST(IFNULL(SUM(DemandaLimpieza), 0) AS INTEGER) AS DemandaLimpieza,
                    CAST(IFNULL(SUM(DemandaMasUnidades), 0) AS INTEGER) AS DemandaMasUnidades,
                    CAST(IFNULL(SUM(DemandaPendiente), 0) AS INTEGER) AS DemandaPendiente
                FROM CAJAS_PEDIDO_DEMANDA
                GROUP BY SKUCompleto
            ),
            cajas AS (
                SELECT
                    SKUCompleto,
                    SUM(CASE WHEN Algoritmo = 'XDOC' THEN 1 ELSE 0 END) AS CajasXDOC,
                    SUM(CASE WHEN Algoritmo = 'LIMPIEZA_CELDAS' THEN 1 ELSE 0 END) AS CajasLimpieza,
                    SUM(CASE WHEN Algoritmo = 'MAS_UNIDADES' THEN 1 ELSE 0 END) AS CajasMasUnidades
                FROM CAJAS_RESULTADO_DETALLE
                GROUP BY SKUCompleto
            )
            SELECT
                d.SKUCompleto,
                d.DemandaInicial,
                d.DemandaXDOC,
                d.DemandaInicial - d.DemandaXDOC AS PendienteTrasXDOC,
                d.DemandaLimpieza,
                d.DemandaMasUnidades,
                d.DemandaPendiente AS PendienteFinal,
                IFNULL(c.CajasXDOC, 0),
                IFNULL(c.CajasLimpieza, 0),
                IFNULL(c.CajasMasUnidades, 0)
            FROM demanda d
            LEFT JOIN cajas c ON c.SKUCompleto = d.SKUCompleto
            ORDER BY d.SKUCompleto
        """)

        pendientes = self.bd.consultar("""
            SELECT COUNT(*), IFNULL(SUM(DemandaPendiente), 0)
            FROM CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR
            WHERE DemandaPendiente > 0
        """)
        if pendientes:
            resumen["PendientesClasificador"] = pendientes[0][0]
            resumen["UnidadesPendientesClasificador"] = pendientes[0][1]

        return resumen

    #---------------------------------------------------------
    # Exportacion
    #---------------------------------------------------------
    def seleccionar_carpeta_salida(self):
        ventana = tk.Tk()
        ventana.withdraw()
        ventana.attributes("-topmost", True)
        carpeta = filedialog.askdirectory(title="Selecciona carpeta para exportar calculo de cajas")
        ventana.destroy()
        if carpeta == "":
            return None
        return Path(carpeta)

    def exportar_resultados(self):
        carpeta = self.seleccionar_carpeta_salida()
        if carpeta is None:
            return []

        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        return [
            self.exportar_detalle(carpeta / ("Calculo_Cajas_Detalle_" + fecha + ".csv")),
            self.exportar_resumen_sku(carpeta / ("Calculo_Cajas_Resumen_SKU_" + fecha + ".csv")),
            self.exportar_resumen_general(carpeta / ("Calculo_Cajas_Resumen_General_" + fecha + ".csv")),
            self.exportar_resumen_xdoc(carpeta / ("Calculo_Cajas_Resumen_XDOC_" + fecha + ".csv")),
            self.exportar_evolucion_demanda(carpeta / ("Calculo_Cajas_Evolucion_Demanda_" + fecha + ".csv")),
            self.exportar_pendiente_clasificador(carpeta / ("Calculo_Cajas_Pendiente_Clasificador_" + fecha + ".csv")),
            self.exportar_incidencias(carpeta / ("Calculo_Cajas_Incidencias_" + fecha + ".csv"))
        ]

    def escribir_csv(self, ruta, columnas, filas):
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo, delimiter=";", lineterminator="\r\n")
            escritor.writerow(columnas)
            escritor.writerows(filas)
        return ruta

    def exportar_detalle(self, ruta):
        columnas = [
            "ALGORITMO", "TIENDA", "APARTE", "SKU", "SKU_CLAVE", "MATRICULA", "POSICION",
            "PASILLO", "LADO", "CELDA", "PROFUNDIDAD", "TCM", "UNIDADES_CAJA",
            "UNIDADES_USADAS", "UNIDADES_RETORNO", "TIPO_MOVIMIENTO", "CELDA_LIMPIADA",
            "MODA", "MOTIVO_SELECCION"
        ]
        filas = self.bd.consultar("""
            SELECT Algoritmo, Tienda, Aparte, SKUCompleto, SKUClave, Matricula, Posicion,
                   Pasillo, Lado, Celda, Profundidad, TCM, UnidadesCaja,
                   UnidadesUsadas, UnidadesRetorno, TipoMovimiento, CeldaLimpiada,
                   Moda, MotivoSeleccion
            FROM CAJAS_RESULTADO_DETALLE
            ORDER BY Algoritmo, SKUCompleto, Tienda, Aparte, TipoMovimiento, Pasillo, Celda, Profundidad
        """)
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_resumen_sku(self, ruta):
        columnas = [
            "ALGORITMO", "TIENDA", "APARTE", "SKU", "SKU_CLAVE", "DEMANDA_INICIAL",
            "DEMANDA_PENDIENTE", "STOCK_DISPONIBLE", "MODA", "UNIDADES_BAJADAS",
            "UNIDADES_USADAS", "UNIDADES_RETORNO", "CAJAS_COMPLETAS", "CAJAS_RETORNO",
            "CELDAS_LIMPIADAS", "ESTADO"
        ]
        filas = self.bd.consultar("""
            SELECT Algoritmo, Tienda, Aparte, SKUCompleto, SKUClave, DemandaInicial,
                   DemandaPendiente, StockDisponible, Moda, UnidadesBajadas,
                   UnidadesUsadas, UnidadesRetorno, CajasCompletas, CajasRetorno,
                   CeldasLimpiadas, Estado
            FROM CAJAS_RESULTADO_RESUMEN_SKU
            ORDER BY SKUCompleto, Tienda, Aparte, Algoritmo
        """)
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_resumen_xdoc(self, ruta):
        columnas = [
            "TIENDA", "APARTE", "SKU", "DEMANDA_INICIAL", "MODA", "ORIGEN_MODA",
            "PERFIL_VOLUMETRIA", "TOLERANCIA_XDOC", "MINIMO_CAJA_XDOC",
            "MAXIMO_CAJA_XDOC", "CAJAS_XDOC", "UNIDADES_XDOC", "ITERACIONES_XDOC",
            "DESVIACION_MODA", "CELDAS_LIMPIAS_XDOC", "PENDIENTE_TRAS_XDOC", "ESTADO"
        ]
        filas = self.bd.consultar("""
            SELECT Tienda, Aparte, SKUCompleto, DemandaInicial, Moda, OrigenModa,
                   PerfilVolumetria, ToleranciaXDOC, MinimoCajaXDOC, MaximoCajaXDOC,
                   CajasXDOC, UnidadesXDOC, IteracionesXDOC, DesviacionModa,
                   CeldasLimpiasXDOC, PendienteTrasXDOC, Estado
            FROM CAJAS_XDOC_RESUMEN
            ORDER BY Tienda, Aparte, SKUCompleto
        """)
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_evolucion_demanda(self, ruta):
        columnas = [
            "SKU", "DEMANDA_INICIAL", "UDS_XDOC", "PENDIENTE_TRAS_XDOC",
            "UDS_LIMPIEZA", "UDS_MAS_UNIDADES", "PENDIENTE_FINAL",
            "CAJAS_XDOC", "CAJAS_LIMPIEZA", "CAJAS_MAS_UNIDADES"
        ]
        filas = self.obtener_resumen_general().get("EvolucionDemanda", [])
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_pendiente_clasificador(self, ruta):
        columnas = [
            "TIENDA", "APARTE", "SKU", "SKU_CLAVE", "DEMANDA_INICIAL",
            "DEMANDA_XDOC", "DEMANDA_LIMPIEZA", "DEMANDA_MAS_UNIDADES", "DEMANDA_PENDIENTE", "ESTADO"
        ]
        filas = self.bd.consultar("""
            SELECT Tienda, Aparte, SKUCompleto, SKUClave, DemandaInicial,
                   DemandaXDOC, IFNULL(DemandaLimpieza, 0), DemandaMasUnidades,
                   DemandaPendiente, Estado
            FROM CAJAS_DEMANDA_PENDIENTE_CLASIFICADOR
            ORDER BY SKUCompleto, Tienda, Aparte
        """)
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_incidencias(self, ruta):
        columnas = [
            "FECHA_HORA", "ALGORITMO", "TIENDA", "APARTE", "SKU", "TIPO", "DETALLE"
        ]
        filas = self.bd.consultar("""
            SELECT FechaHora, Algoritmo, Tienda, Aparte, SKUCompleto, Tipo, Detalle
            FROM CAJAS_RESULTADO_INCIDENCIAS
            ORDER BY FechaHora, Algoritmo, SKUCompleto, Tienda, Aparte
        """)
        return self.escribir_csv(ruta, columnas, filas)

    def exportar_resumen_general(self, ruta):
        resumen = self.obtener_resumen_general()
        filas = [
            ["SKUS_PEDIDO", resumen["SkusPedido"]],
            ["CAJAS_COMPLETAS", resumen["CajasCompletas"]],
            ["CAJAS_RETORNO", resumen["CajasRetorno"]],
            ["CELDAS_LIMPIADAS", resumen["CeldasLimpiadas"]],
            ["UNIDADES_RETORNO", resumen["UnidadesRetorno"]],
            ["CAJAS_RESERVADAS_XDOC", resumen["CajasReservadasXDOC"]],
            ["UNIDADES_CUBIERTAS_XDOC", resumen["UnidadesCubiertasXDOC"]],
            ["PENDIENTES_CLASIFICADOR", resumen["PendientesClasificador"]],
            ["UNIDADES_PENDIENTES_CLASIFICADOR", resumen["UnidadesPendientesClasificador"]],
            ["INCIDENCIAS", resumen["Incidencias"]],
            [],
            ["ALGORITMO", "COMPLETAS", "RETORNO", "TOTAL_CAJAS", "UNIDADES_USADAS", "UNIDADES_RETORNO"]
        ]
        filas.extend([list(fila) for fila in resumen["PorAlgoritmo"]])
        filas.append([])
        filas.append(["TCM", "CAJAS"])
        filas.extend([[tcm, cajas] for tcm, cajas in resumen["PorTCM"]])
        filas.append([])
        filas.append(["PASILLO", "COMPLETAS", "RETORNO", "TOTAL"])
        filas.extend([[pasillo, completas, retorno, total] for pasillo, completas, retorno, total in resumen["PorPasillo"]])

        return self.escribir_csv(
            ruta,
            ["CONCEPTO", "VALOR", "VALOR_2", "VALOR_3", "VALOR_4", "VALOR_5"],
            filas
        )
