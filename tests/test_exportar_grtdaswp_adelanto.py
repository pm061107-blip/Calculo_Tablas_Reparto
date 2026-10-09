import tempfile
import unittest
from pathlib import Path

from modulos.exportar_grtdaswp_adelanto import (
    construir_lineas_grtdaswp,
    exportar_grtdaswp_adelanto,
)


class ExportarGrtdaswpAdelantoTests(unittest.TestCase):

    def test_subpedido_es_no_evacuar_y_pedido_completo_es_evacuar(self):
        resultado = construir_lineas_grtdaswp(
            codigo_no_evacuar="COD_NO_EVACUAR",
            codigo_evacuar="COD_EVACUAR",
            registros_subpedido_generado=[(1002,), (1001,), (1001,)],
            registros_pedido_generado=[(2002,), (2001,)],
            fecha="20261001",
        )

        self.assertEqual(resultado["codigo_no_evacuar"], "COD_NO_EVACUAR")
        self.assertEqual(resultado["codigo_evacuar"], "COD_EVACUAR")
        self.assertEqual(resultado["tiendas_no_evacuar"], ["1001", "1002"])
        self.assertEqual(resultado["tiendas_evacuar"], ["2001", "2002"])
        self.assertEqual(resultado["origen_no_evacuar"], "SUBPEDIDO")
        self.assertEqual(
            resultado["origen_evacuar"],
            "PEDIDO COMPLETO MENOS SUBPEDIDO",
        )

        lineas_no_evacuar = resultado["lineas"][:2]
        lineas_evacuar = resultado["lineas"][2:]

        self.assertTrue(
            all(linea[0] == "COD_NO_EVACUAR" for linea in lineas_no_evacuar)
        )
        self.assertTrue(
            all(linea[0] == "COD_EVACUAR" for linea in lineas_evacuar)
        )
        self.assertTrue(
            all(
                linea[1] == "Reparto_20261001_No_Evacuar"
                for linea in lineas_no_evacuar
            )
        )
        self.assertTrue(
            all(
                linea[1] == "Reparto_20261001_Evacuar"
                for linea in lineas_evacuar
            )
        )
        self.assertTrue(all(len(linea) == 7 for linea in resultado["lineas"]))

    def test_compatibilidad_con_codigo_unico_anterior(self):
        resultado = construir_lineas_grtdaswp(
            codigo="COD_LEGACY",
            registros_subpedido_generado=[(1001,)],
            registros_pedido_generado=[(2001,)],
            fecha="20261001",
        )

        self.assertEqual(resultado["codigo_no_evacuar"], "COD_LEGACY")
        self.assertEqual(resultado["codigo_evacuar"], "COD_LEGACY")
        self.assertEqual(resultado["lineas"][0][0], "COD_LEGACY")
        self.assertEqual(resultado["lineas"][1][0], "COD_LEGACY")

    def test_codigo_evacuar_explicito_prevalece_sobre_parametro_antiguo(self):
        resultado = construir_lineas_grtdaswp(
            codigo="COD_ANTIGUO",
            codigo_no_evacuar="COD_NO_EVACUAR",
            codigo_evacuar="COD_EVACUAR_EXPLICITO",
            registros_subpedido_generado=[(1001,)],
            registros_pedido_generado=[(2001,)],
            fecha="20261001",
        )

        self.assertEqual(resultado["codigo_evacuar"], "COD_EVACUAR_EXPLICITO")
        self.assertEqual(resultado["lineas"][1][0], "COD_EVACUAR_EXPLICITO")

    def test_rechaza_solape_de_tiendas(self):
        with self.assertRaisesRegex(ValueError, "tiendas repetidas"):
            construir_lineas_grtdaswp(
                codigo_no_evacuar="COD_NO_EVACUAR",
                codigo_evacuar="COD_EVACUAR",
                registros_subpedido_generado=[(1001,)],
                registros_pedido_generado=[(1001,)],
                fecha="20261001",
            )

    def test_rechaza_codigo_no_evacuar_vacio(self):
        with self.assertRaisesRegex(ValueError, "No_Evacuar"):
            construir_lineas_grtdaswp(
                codigo_no_evacuar="   ",
                codigo_evacuar="COD_EVACUAR",
                registros_subpedido_generado=[(1001,)],
                registros_pedido_generado=[(2001,)],
                fecha="20261001",
            )

    def test_rechaza_codigo_evacuar_vacio(self):
        with self.assertRaisesRegex(ValueError, "Evacuar"):
            construir_lineas_grtdaswp(
                codigo_no_evacuar="COD_NO_EVACUAR",
                codigo_evacuar="   ",
                registros_subpedido_generado=[(1001,)],
                registros_pedido_generado=[(2001,)],
                fecha="20261001",
            )

    def test_exporta_txt_con_crlf_y_asignacion_correcta(self):
        with tempfile.TemporaryDirectory() as carpeta:
            resultado = exportar_grtdaswp_adelanto(
                codigo_no_evacuar="COD_NO_EVACUAR",
                codigo_evacuar="COD_EVACUAR",
                registros_subpedido_generado=[(1001,)],
                registros_pedido_generado=[(2001,)],
                carpeta_destino=carpeta,
                fecha="20261001",
            )

            ruta = Path(resultado["ruta"])
            contenido = ruta.read_bytes()

            self.assertEqual(ruta.name, "GRTDASWP.txt")
            self.assertEqual(resultado["total_lineas"], 2)
            self.assertIn(
                b"COD_NO_EVACUAR\tReparto_20261001_No_Evacuar\t",
                contenido,
            )
            self.assertIn(
                b"COD_EVACUAR\tReparto_20261001_Evacuar\t",
                contenido,
            )
            self.assertEqual(contenido.count(b"\r\n"), 2)
            self.assertNotIn(b"\n", contenido.replace(b"\r\n", b""))


if __name__ == "__main__":
    unittest.main()
