from pathlib import Path
import csv

from bd.basedatos import BaseDatos
from modulos.calculador_cajas_paises import CalculadorCajasPaises
from modulos.volumetria_desde_contenedores import VolumetriaDesdeContenedores


class ExportadorSinVolumetria:
    """Genera Sin_volumetria.csv con el formato de carga proporcionado."""

    CABECERAS = [
        "CD", "SGA", "CADENA", "TIPO_SECION", "Producto", "Modelo", "Calidad",
        "Color", "Talla_Num", "UxL", "EM", "UxB", "BxP", "Uxm", "BLOQUEADO",
        "TIPO CONTENEDOR",
    ]

    CABECERAS_DIAGNOSTICO = [
        "SKU", "Seccion", "UxL", "TipoContenedor", "TCM", "UxB", "Muestras",
        "EM", "VolumenUnitarioM3", "Estado",
    ]

    def __init__(self):
        self.bd = BaseDatos()
        self.calculador = CalculadorCajasPaises()
        self.derivador = VolumetriaDesdeContenedores()

    @staticmethod
    def _entero(valor, defecto=0):
        try:
            return int(float(str(valor).replace(",", ".")))
        except Exception:
            return defecto

    def _pedido_sin_volumetria_oficial(self):
        indices_oficiales = self.calculador._cargar_volumetria()
        filas = self.bd.consultar("""
            SELECT Seccion, Modelo, Calidad, Color, TallaNum, Campaña, Año, UxL
            FROM CAJAS_PEDIDO_LINEAS
            GROUP BY Seccion, Modelo, Calidad, Color, TallaNum, Campaña, Año, UxL
        """)

        faltantes = []
        vistos = set()
        for seccion, modelo, calidad, color, talla_num, campana, anio, uxl in filas:
            talla = self.calculador._normalizar_talla(talla_num)
            if talla is None:
                continue
            sku_base = self.calculador._sku_base(modelo, calidad, color, talla)
            sku = self.calculador._sku(modelo, calidad, color, talla, campana, anio)
            uxl_num = self._entero(uxl, 0)
            volumen_oficial, _ = self.calculador._obtener_volumen_unitario(
                indices_oficiales, sku, sku_base, uxl_num
            )
            if volumen_oficial is not None:
                continue

            clave = (
                self._entero(seccion, 0),
                self._entero(modelo, 0),
                self._entero(calidad, 0),
                self._entero(color, 0),
                int(talla),
                str(campana or "").strip().upper(),
                str(self.calculador._normalizar_anio(anio)),
                int(uxl_num),
                sku,
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            faltantes.append(clave)

        return faltantes

    def construir(self):
        faltantes = self._pedido_sin_volumetria_oficial()
        indice_contenedores = self.derivador.construir_indice()

        filas_exportacion = []
        diagnostico = []
        skus_calculables = set()
        skus_sin_datos = set()

        for seccion, modelo, calidad, color, talla, campana, anio, uxl, sku in faltantes:
            info = indice_contenedores.get(sku)
            if not info:
                skus_sin_datos.add(sku)
                diagnostico.append({
                    "SKU": sku,
                    "Seccion": seccion,
                    "UxL": uxl,
                    "TipoContenedor": "",
                    "TCM": "",
                    "UxB": "",
                    "Muestras": 0,
                    "EM": "",
                    "VolumenUnitarioM3": "",
                    "Estado": "SIN CONTENEDORES VALIDOS 300/400",
                })
                continue

            skus_calculables.add(sku)
            for tipo in (163, 155):
                tipo_info = info["PorTipo"].get(tipo)
                if not tipo_info:
                    continue
                ems = tipo_info.get("EMs", []) or []
                if not ems:
                    diagnostico.append({
                        "SKU": sku,
                        "Seccion": seccion,
                        "UxL": uxl,
                        "TipoContenedor": tipo,
                        "TCM": tipo_info["TCM"],
                        "UxB": tipo_info["UxB"],
                        "Muestras": tipo_info["Muestras"],
                        "EM": "",
                        "VolumenUnitarioM3": info["VolumenUnitarioM3"],
                        "Estado": "SIN EM VALIDO",
                    })
                    continue

                for em in ems:
                    filas_exportacion.append([
                        10004,                   # CD fijo
                        2,                       # SGA fijo
                        2,                       # CADENA fijo
                        int(seccion),            # TIPO_SECION desde ESTAREPP
                        0,                       # Producto fijo
                        int(modelo),
                        int(calidad),
                        int(color),
                        int(talla),
                        int(uxl),
                        int(em),                 # prefijo de Estado de mercancia
                        int(tipo_info["UxB"]),  # moda de unidades por SKU + tipo
                        0,                       # BxP fijo
                        99,                      # Uxm fijo
                        "NO",                    # BLOQUEADO fijo
                        int(tipo),               # 163=300 / 155=400
                    ])
                    diagnostico.append({
                        "SKU": sku,
                        "Seccion": seccion,
                        "UxL": uxl,
                        "TipoContenedor": tipo,
                        "TCM": tipo_info["TCM"],
                        "UxB": tipo_info["UxB"],
                        "Muestras": tipo_info["Muestras"],
                        "EM": int(em),
                        "VolumenUnitarioM3": info["VolumenUnitarioM3"],
                        "Estado": "CALCULADA DESDE CONTENEDORES",
                    })

        # Orden estable para facilitar la revision y comparacion entre ejecuciones.
        orden_tipo = {163: 0, 155: 1}
        filas_exportacion.sort(key=lambda r: (
            r[5], r[6], r[7], r[8], r[9], orden_tipo.get(r[15], 99), r[10]
        ))
        diagnostico.sort(key=lambda r: (
            str(r["SKU"]), int(r["Seccion"] or 0), int(r["UxL"] or 0),
            str(r["TipoContenedor"]), str(r["EM"]),
        ))

        return {
            "Filas": filas_exportacion,
            "Diagnostico": diagnostico,
            "SkusSinOficial": len({x[-1] for x in faltantes}),
            "SkusCalculables": len(skus_calculables),
            "SkusSinDatos": len(skus_sin_datos),
        }

    def exportar(self, ruta):
        ruta = Path(ruta)
        if ruta.suffix.lower() != ".csv":
            ruta = ruta.with_suffix(".csv")
        ruta.parent.mkdir(parents=True, exist_ok=True)

        resultado = self.construir()
        with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.writer(f, delimiter=";", lineterminator="\r\n")
            escritor.writerow(self.CABECERAS)
            escritor.writerows(resultado["Filas"])

        ruta_diag = ruta.with_name(ruta.stem + "_diagnostico.csv")
        with open(ruta_diag, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(
                f,
                fieldnames=self.CABECERAS_DIAGNOSTICO,
                delimiter=";",
                lineterminator="\r\n",
            )
            escritor.writeheader()
            for fila in resultado["Diagnostico"]:
                fila = dict(fila)
                vu = fila.get("VolumenUnitarioM3")
                if isinstance(vu, float):
                    fila["VolumenUnitarioM3"] = format(vu, ".12f")
                escritor.writerow(fila)

        resultado["Ruta"] = str(ruta)
        resultado["RutaDiagnostico"] = str(ruta_diag)
        return resultado
