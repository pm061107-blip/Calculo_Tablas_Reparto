import math
import re
from collections import Counter, defaultdict

from bd.basedatos import BaseDatos
from modulos.volumetria_desde_contenedores import VolumetriaDesdeContenedores


class CalculadorCajasPaises:
    """Calcula volumen teorico por pais y optimiza la reutilizacion de cajas 400.

    La volumetria se convierte a m3 por unidad usando el tipo de contenedor
    medio (T.CONT.MED.) y UDS./BULTO. Antes de agrupar por pais se descuenta
    obligatoriamente la demanda cubierta por XDOC.
    """

    VOLUMEN_CAJA_300_M3 = 0.580 * 0.380 * 0.300
    VOLUMEN_CAJA_400_M3 = 0.580 * 0.380 * 0.400

    def __init__(self):
        self.bd = BaseDatos()

    # ---------------------------------------------------------
    # Normalizacion
    # ---------------------------------------------------------
    def _texto(self, valor):
        if valor is None:
            return ""
        return str(valor).strip()

    def _entero(self, valor, defecto=0):
        try:
            return int(round(float(str(valor).replace(",", "."))))
        except Exception:
            return defecto

    def _normalizar_anio(self, valor):
        try:
            return str(int(float(valor)))
        except Exception:
            return self._texto(valor)

    def _entero_texto(self, valor, ancho):
        try:
            texto = str(int(float(valor)))
        except Exception:
            texto = self._texto(valor)
        return texto.zfill(ancho)

    def _normalizar_talla(self, valor):
        try:
            numero = float(str(valor).replace(",", "."))
            entero = int(numero)
            if numero != entero:
                return None
            return entero
        except Exception:
            return None

    def _sku_base(self, modelo, calidad, color, talla):
        return "/".join([
            self._entero_texto(modelo, 4),
            self._entero_texto(calidad, 3),
            self._entero_texto(color, 3),
            str(int(talla)),
        ])

    def _sku(self, modelo, calidad, color, talla, campana, anio):
        return self._sku_base(modelo, calidad, color, talla) + "/" + self._texto(campana).upper() + "/" + self._normalizar_anio(anio)

    # ---------------------------------------------------------
    # Volumen de una caja de referencia
    # ---------------------------------------------------------
    @classmethod
    def volumen_tcm_m3(cls, texto_tcm):
        """Extrae medidas en mm de textos como 'Caja 580x380x300'."""
        texto = str(texto_tcm or "").lower().replace(" ", "")
        coincidencia = re.search(r"(\d+(?:[\.,]\d+)?)x(\d+(?:[\.,]\d+)?)x(\d+(?:[\.,]\d+)?)", texto)
        if not coincidencia:
            return None
        try:
            largo = float(coincidencia.group(1).replace(",", ".")) / 1000.0
            ancho = float(coincidencia.group(2).replace(",", ".")) / 1000.0
            alto = float(coincidencia.group(3).replace(",", ".")) / 1000.0
        except Exception:
            return None
        volumen = largo * ancho * alto
        return volumen if volumen > 0 else None

    @staticmethod
    def _valor_representativo(valores):
        """Moda del volumen unitario, redondeada para evitar ruido binario."""
        if not valores:
            return None
        redondeados = [round(float(v), 12) for v in valores if v is not None and float(v) > 0]
        if not redondeados:
            return None
        contador = Counter(redondeados)
        return sorted(contador.items(), key=lambda x: (-x[1], x[0]))[0][0]

    # ---------------------------------------------------------
    # Indices de volumetria
    # ---------------------------------------------------------
    def _cargar_volumetria(self):
        exacta_uxl = defaultdict(list)
        base_uxl = defaultdict(list)
        exacta = defaultdict(list)
        base = defaultdict(list)

        filas = self.bd.consultar("""
            SELECT SKUCompleto, SKUBase, UxL, TCM, UdsBulto
            FROM CAJAS_VOLUMETRIA
            WHERE IFNULL(UdsBulto, 0) > 0
        """)

        filas_validas = 0
        for sku, sku_base, uxl, tcm, uds_bulto in filas:
            uds = self._entero(uds_bulto, 0)
            volumen_caja = self.volumen_tcm_m3(tcm)
            if uds <= 0 or volumen_caja is None:
                continue
            volumen_unidad = volumen_caja / uds
            sku = self._texto(sku)
            sku_base = self._texto(sku_base)
            uxl = self._entero(uxl, 0)
            if sku:
                exacta_uxl[(sku, uxl)].append(volumen_unidad)
                exacta[sku].append(volumen_unidad)
            if sku_base:
                base_uxl[(sku_base, uxl)].append(volumen_unidad)
                base[sku_base].append(volumen_unidad)
            filas_validas += 1

        return {
            "exacta_uxl": {k: self._valor_representativo(v) for k, v in exacta_uxl.items()},
            "base_uxl": {k: self._valor_representativo(v) for k, v in base_uxl.items()},
            "exacta": {k: self._valor_representativo(v) for k, v in exacta.items()},
            "base": {k: self._valor_representativo(v) for k, v in base.items()},
            "filas_validas": filas_validas,
        }

    def _obtener_volumen_unitario(self, indices, sku, sku_base, uxl):
        claves = [
            ("EXACTA+UXL", indices["exacta_uxl"].get((sku, uxl))),
            ("BASE+UXL", indices["base_uxl"].get((sku_base, uxl))),
            ("EXACTA", indices["exacta"].get(sku)),
            ("BASE", indices["base"].get(sku_base)),
        ]
        for origen, valor in claves:
            if valor is not None and valor > 0:
                return float(valor), origen
        return None, "SIN VOLUMETRIA"

    # ---------------------------------------------------------
    # Pais por tienda
    # ---------------------------------------------------------
    def _cargar_paises_tienda(self):
        mapa = {}
        try:
            filas = self.bd.consultar("SELECT Tienda, Pais FROM Tiendas_Web")
        except Exception:
            filas = []
        for tienda, pais in filas:
            clave = self._entero(tienda, None)
            pais = self.normalizar_pais(pais)
            if clave is None or not pais:
                continue
            if clave not in mapa:
                mapa[clave] = pais
        return mapa

    # ---------------------------------------------------------
    # Calculo por pais
    # ---------------------------------------------------------
    def calcular(self):
        indices = self._cargar_volumetria()
        pais_por_tienda = self._cargar_paises_tienda()

        # Fallback profesional: la volumetria oficial manda siempre. Solo si
        # no existe para el SKU/UXL se usa una estimacion calculada desde
        # Contenedores (moda de Uds/caja por tipo 300/400 y volumen fisico).
        fallback_contenedores_disponible = True
        try:
            indice_contenedores = VolumetriaDesdeContenedores().construir_indice()
        except RuntimeError:
            fallback_contenedores_disponible = False
            # Permite seguir usando la aplicacion si todavia no se ha
            # reimportado Contenedores con la nueva columna EstadoMercancia.
            # En ese caso no hay fallback hasta que se reimporte.
            indice_contenedores = {}

        # La optimizacion por pais se hace SOLO sobre la demanda que realmente
        # ira a carruseles. Por eso se parte de la tabla de demanda generada por
        # el calculo de cajas y se descuenta todo lo cubierto por XDOC.
        #
        # CAJAS_PEDIDO_DEMANDA se crea en cada calculo, por lo que este origen
        # garantiza que no mezclamos resultados viejos ni unidades XDOC.
        try:
            filas = self.bd.consultar("""
                SELECT
                    Tienda, Modelo, Calidad, Color, Talla, Campana, Anio, UxL,
                    CAST(IFNULL(SUM(DemandaInicial), 0) AS INTEGER) AS DemandaInicial,
                    CAST(IFNULL(SUM(DemandaXDOC), 0) AS INTEGER) AS DemandaXDOC,
                    CAST(IFNULL(SUM(DemandaInicial - DemandaXDOC), 0) AS INTEGER) AS DemandaCarruseles
                FROM CAJAS_PEDIDO_DEMANDA
                GROUP BY Tienda, Modelo, Calidad, Color, Talla, Campana, Anio, UxL
            """)
        except Exception as exc:
            raise RuntimeError(
                "Primero debes ejecutar CALCULAR CAJAS. "
                "El calculo por pais necesita descontar las unidades XDOC del pedido."
            ) from exc

        volumen_pais = defaultdict(float)
        unidades_pais = defaultdict(int)
        skus_pais = defaultdict(set)
        skus_sin_oficial = set()
        skus_oficiales_usados = set()
        skus_contenedores_usados = set()
        incidencias_sku = set()
        unidades_sin_volumetria = 0
        tiendas_sin_pais = set()
        unidades_pedido_original = 0
        unidades_descontadas_xdoc = 0
        unidades_demanda_carruseles = 0

        for tienda, modelo, calidad, color, talla_num, campana, anio, uxl, demanda_inicial, demanda_xdoc, demanda_carruseles in filas:
            demanda_inicial = self._entero(demanda_inicial, 0)
            demanda_xdoc = self._entero(demanda_xdoc, 0)
            unidades = self._entero(demanda_carruseles, 0)

            unidades_pedido_original += max(0, demanda_inicial)
            unidades_descontadas_xdoc += max(0, demanda_xdoc)
            unidades_demanda_carruseles += max(0, unidades)

            if unidades <= 0:
                continue

            tienda_num = self._entero(tienda, None)
            pais = pais_por_tienda.get(tienda_num, "")
            if not pais:
                tiendas_sin_pais.add(tienda_num)
                continue

            talla = self._normalizar_talla(talla_num)
            if talla is None:
                incidencias_sku.add((pais, "TALLA_NO_NUMERICA"))
                unidades_sin_volumetria += unidades
                continue

            sku_base = self._sku_base(modelo, calidad, color, talla)
            sku = self._sku(modelo, calidad, color, talla, campana, anio)
            uxl_num = self._entero(uxl, 0)

            volumen_unitario, origen = self._obtener_volumen_unitario(indices, sku, sku_base, uxl_num)
            if volumen_unitario is not None:
                skus_oficiales_usados.add(sku)
            else:
                skus_sin_oficial.add(sku)
                info_cont = indice_contenedores.get(sku)
                if info_cont and float(info_cont.get("VolumenUnitarioM3", 0.0) or 0.0) > 0:
                    volumen_unitario = float(info_cont["VolumenUnitarioM3"])
                    origen = "CALCULADA_CONTENEDORES"
                    skus_contenedores_usados.add(sku)
                else:
                    incidencias_sku.add((pais, sku))
                    unidades_sin_volumetria += unidades
                    continue

            volumen = volumen_unitario * unidades
            volumen_pais[pais] += volumen
            unidades_pais[pais] += unidades
            skus_pais[pais].add(sku)

        resultados = []
        for pais in volumen_pais.keys():
            volumen = float(volumen_pais[pais])
            cajas_300 = int(math.ceil(max(0.0, volumen - 1e-12) / self.VOLUMEN_CAJA_300_M3)) if volumen > 0 else 0
            cajas_400 = int(math.ceil(max(0.0, volumen - 1e-12) / self.VOLUMEN_CAJA_400_M3)) if volumen > 0 else 0
            resultados.append({
                "Pais": pais,
                "VolumenM3": volumen,
                "Cajas300": cajas_300,
                "Cajas400": cajas_400,
                "Unidades": int(unidades_pais[pais]),
                "Skus": len(skus_pais[pais]),
            })

        # La tabla del formulario debe presentar primero los paises que mas
        # cajas 400 necesitan. El desempate se realiza por volumen y pais para
        # que el orden sea estable entre ejecuciones.
        resultados = self.ordenar_paises(resultados)

        total_volumen = sum(r["VolumenM3"] for r in resultados)
        return {
            "Paises": resultados,
            "VolumenTotalM3": total_volumen,
            "Cajas300TotalTeorico": int(math.ceil(max(0.0, total_volumen - 1e-12) / self.VOLUMEN_CAJA_300_M3)) if total_volumen > 0 else 0,
            "Cajas400TotalTeorico": int(math.ceil(max(0.0, total_volumen - 1e-12) / self.VOLUMEN_CAJA_400_M3)) if total_volumen > 0 else 0,
            "SkusSinVolumetriaOficial": len(skus_sin_oficial),
            "SkusVolumetriaOficial": len(skus_oficiales_usados),
            "SkusVolumetriaContenedores": len(skus_contenedores_usados),
            "SkusSinVolumetria": len(incidencias_sku),
            "UnidadesSinVolumetria": int(unidades_sin_volumetria),
            "TiendasSinPais": len([x for x in tiendas_sin_pais if x is not None]),
            "VolumetriasValidas": int(indices["filas_validas"]),
            "FallbackContenedoresDisponible": bool(fallback_contenedores_disponible),
            "UnidadesPedidoOriginal": int(unidades_pedido_original),
            "UnidadesDescontadasXDOC": int(unidades_descontadas_xdoc),
            "UnidadesDemandaCarruseles": int(unidades_demanda_carruseles),
        }

    # ---------------------------------------------------------
    # Orden visual por demanda de caja 400
    # ---------------------------------------------------------
    @staticmethod
    def normalizar_pais(valor):
        return " ".join(str(valor or "").strip().upper().split())

    @classmethod
    def ordenar_paises(cls, paises):
        return sorted(
            list(paises or []),
            key=lambda fila: (
                -int(fila.get("Cajas400", 0) or 0),
                -float(fila.get("VolumenM3", 0.0) or 0.0),
                cls.normalizar_pais(fila.get("Pais", "")),
            ),
        )

    # ---------------------------------------------------------
    # Optimizacion subset-sum: maximo <= objetivo
    # ---------------------------------------------------------
    @classmethod
    def seleccionar_paises_400(cls, paises, objetivo):
        """Devuelve nombres normalizados, nunca posiciones de la tabla.

        De este modo la seleccion automatica sigue siendo correcta aunque la
        presentacion se reordene por numero de cajas 400.
        """
        objetivo = int(objetivo or 0)
        if objetivo <= 0 or not paises:
            return set(), 0

        items = []
        for fila in paises:
            pais = cls.normalizar_pais(fila.get("Pais", ""))
            valor = int(fila.get("Cajas400", 0) or 0)
            if pais and valor > 0 and valor <= objetivo:
                items.append((pais, valor))

        if not items:
            return set(), 0

        alcanzable = bytearray(objetivo + 1)
        alcanzable[0] = 1
        padre_suma = [-1] * (objetivo + 1)
        padre_item = [None] * (objetivo + 1)

        for pais, valor in items:
            for suma in range(objetivo - valor, -1, -1):
                if alcanzable[suma] and not alcanzable[suma + valor]:
                    nueva = suma + valor
                    alcanzable[nueva] = 1
                    padre_suma[nueva] = suma
                    padre_item[nueva] = pais

        mejor = objetivo
        while mejor > 0 and not alcanzable[mejor]:
            mejor -= 1

        seleccion = set()
        suma = mejor
        while suma > 0:
            pais = padre_item[suma]
            anterior = padre_suma[suma]
            if not pais or anterior < 0:
                break
            seleccion.add(pais)
            suma = anterior

        return seleccion, mejor
