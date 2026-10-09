import re
from collections import Counter, defaultdict
from statistics import median

from bd.basedatos import BaseDatos


class VolumetriaDesdeContenedores:
    """Calcula volumetria estimada por SKU a partir del stock de Contenedores.

    Reglas:
    - SKU: Modelo/Calidad/Color/Talla/Campana/Anio.
    - Solo se usan cajas con unidades > 0 y TCM 580x380x300 o 580x380x400.
    - Para cada SKU y tipo de caja, UxB es la moda de Unidades.
      Si hay empate de frecuencia, gana el valor de unidades mayor para evitar
      que una caja parcial se convierta en referencia.
    - El volumen unitario de cada tipo es volumen fisico de la caja / UxB.
    - Si el SKU tiene referencia 300 y 400, el volumen unitario final es la
      mediana de ambos valores.
    - EM se obtiene de Estado de mercancia tomando lo anterior al primer '-'
      y convirtiendolo a INTEGER.
    """

    VOLUMEN_CAJA_300_M3 = 0.580 * 0.380 * 0.300
    VOLUMEN_CAJA_400_M3 = 0.580 * 0.380 * 0.400

    TIPOS = {
        163: {
            "alto": 300,
            "tcm": "Caja 580x380x300",
            "volumen_m3": VOLUMEN_CAJA_300_M3,
        },
        155: {
            "alto": 400,
            "tcm": "Caja 580x380x400",
            "volumen_m3": VOLUMEN_CAJA_400_M3,
        },
    }

    def __init__(self):
        self.bd = BaseDatos()

    @staticmethod
    def _texto(valor):
        if valor is None:
            return ""
        return str(valor).strip()

    @classmethod
    def _entero(cls, valor, defecto=None):
        try:
            return int(float(cls._texto(valor).replace(",", ".")))
        except Exception:
            return defecto

    @classmethod
    def extraer_em(cls, estado_mercancia):
        texto = cls._texto(estado_mercancia)
        if not texto:
            return None
        prefijo = texto.split("-", 1)[0].strip()
        return cls._entero(prefijo, None)

    @classmethod
    def tipo_contenedor_desde_tcm(cls, tcm):
        """Devuelve 163 (300), 155 (400) o None."""
        texto = cls._texto(tcm).lower().replace(" ", "")
        match = re.search(r"580(?:[x×])380(?:[x×])(300|400)", texto)
        if not match:
            # Respaldo: admite decimales y texto adicional siempre que las tres
            # medidas sean exactamente las esperadas tras normalizar.
            match = re.search(
                r"(\d+(?:[\.,]\d+)?)[x×](\d+(?:[\.,]\d+)?)[x×](\d+(?:[\.,]\d+)?)",
                texto,
            )
            if not match:
                return None
            try:
                medidas = tuple(int(round(float(x.replace(",", ".")))) for x in match.groups())
            except Exception:
                return None
            if medidas == (580, 380, 300):
                return 163
            if medidas == (580, 380, 400):
                return 155
            return None
        return 163 if match.group(1) == "300" else 155

    @classmethod
    def volumen_tipo_m3(cls, tipo_contenedor):
        info = cls.TIPOS.get(int(tipo_contenedor)) if tipo_contenedor is not None else None
        return float(info["volumen_m3"]) if info else None

    def _columna_existe(self, tabla, columna):
        try:
            filas = self.bd.consultar("PRAGMA table_info(" + tabla + ")")
        except Exception:
            return False
        objetivo = columna.lower()
        return any(str(fila[1]).strip().lower() == objetivo for fila in filas)

    def validar_estructura_contenedores(self):
        if not self._columna_existe("CAJAS_CONTENEDORES", "EstadoMercancia"):
            raise RuntimeError(
                "La tabla CAJAS_CONTENEDORES fue importada con una version anterior y no contiene "
                "EstadoMercancia. Reimporta Contenedores.csv una vez con esta version para poder "
                "calcular y exportar la volumetria faltante."
            )

    @staticmethod
    def _moda_unidades(valores):
        valores = [int(v) for v in valores if v is not None and int(v) > 0]
        if not valores:
            return 0
        contador = Counter(valores)
        # Mayor frecuencia; en empate, mayor numero de unidades. Esto evita que
        # una caja parcial aislada se tome como capacidad estandar.
        return max(contador.items(), key=lambda par: (par[1], par[0]))[0]

    def construir_indice(self):
        self.validar_estructura_contenedores()

        filas = self.bd.consultar("""
            SELECT SKUCompleto, Unidades, TCM, EstadoMercancia
            FROM CAJAS_CONTENEDORES
            WHERE IFNULL(SKUCompleto, '') <> ''
              AND CAST(IFNULL(Unidades, 0) AS INTEGER) > 0
        """)

        agrupado = defaultdict(lambda: defaultdict(lambda: {
            "unidades": [],
            "ems": set(),
        }))

        for sku, unidades, tcm, estado_mercancia in filas:
            sku = self._texto(sku)
            if not sku:
                continue
            tipo = self.tipo_contenedor_desde_tcm(tcm)
            if tipo is None:
                continue
            uds = self._entero(unidades, 0)
            if uds is None or uds <= 0:
                continue
            agrupado[sku][tipo]["unidades"].append(int(uds))
            em = self.extraer_em(estado_mercancia)
            if em is not None:
                agrupado[sku][tipo]["ems"].add(int(em))

        resultado = {}
        for sku, tipos in agrupado.items():
            por_tipo = {}
            volumenes_unitarios = []

            for tipo in (163, 155):  # 300 primero, 400 despues
                datos = tipos.get(tipo)
                if not datos:
                    continue
                uxb = self._moda_unidades(datos["unidades"])
                if uxb <= 0:
                    continue
                volumen_caja = self.volumen_tipo_m3(tipo)
                volumen_unidad = volumen_caja / uxb
                volumenes_unitarios.append(volumen_unidad)
                por_tipo[tipo] = {
                    "TipoContenedor": int(tipo),
                    "TCM": self.TIPOS[tipo]["tcm"],
                    "VolumenCajaM3": float(volumen_caja),
                    "UxB": int(uxb),
                    "Muestras": int(len(datos["unidades"])),
                    "EMs": sorted(int(x) for x in datos["ems"]),
                    "VolumenUnitarioM3": float(volumen_unidad),
                }

            if not por_tipo:
                continue

            resultado[sku] = {
                "SKU": sku,
                "PorTipo": por_tipo,
                "VolumenUnitarioM3": float(median(volumenes_unitarios)),
                "TiposValidos": len(por_tipo),
                "Muestras": sum(x["Muestras"] for x in por_tipo.values()),
            }

        return resultado
