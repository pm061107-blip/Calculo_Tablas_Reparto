import sqlite3
import unittest

from modulos.gestor_pedidos_cajas import (
    GestorPedidosCajas,
    linea_eliminada_por_picos,
)


COLUMNAS = GestorPedidosCajas.COLUMNAS_ESTAREPP


def linea(tienda, modelo, unidades):
    valores = dict.fromkeys(COLUMNAS, None)
    valores.update({
        "Tienda": tienda, "Aparte": 0, "Modelo": modelo, "Calidad": 1,
        "Color": 1, "TallaNum": 2, "Campaña": "I", "Año": 2026,
        "Unidades": unidades, "UxL": 1, "Lotes": float(unidades),
    })
    return tuple(valores[c] for c in COLUMNAS)


class GestorPedidosCajasV21Tests(unittest.TestCase):

    def setUp(self):
        self.conexion = sqlite3.connect(":memory:")
        columnas = ", ".join('"' + c + '"' for c in COLUMNAS)
        self.conexion.execute("CREATE TABLE ESTAREPP (" + columnas + ")")
        self.gestor = GestorPedidosCajas(self.conexion)

    def tearDown(self):
        self.conexion.close()

    def cargar_estarepp(self, filas):
        self.conexion.execute("DELETE FROM ESTAREPP")
        marcas = ",".join("?" for _ in COLUMNAS)
        self.conexion.executemany("INSERT INTO ESTAREPP VALUES (" + marcas + ")", filas)
        self.conexion.commit()

    def test_los_pedidos_se_acumulan_con_su_marca_de_picos(self):
        self.cargar_estarepp([linea(1, 100, 5), linea(2, 100, 7)])
        a = self.gestor.anadir_desde_estarepp("A.txt", "C:/A.txt", "ESTAREPP", True)
        self.cargar_estarepp([linea(3, 200, 4)])
        b = self.gestor.anadir_desde_estarepp("B.txt", "C:/B.txt", "ESTAREPP", False)

        self.assertEqual(self.gestor.contar_lineas(), 3)
        self.assertTrue(a["CalcularPicos"])
        self.assertFalse(b["CalcularPicos"])
        filas = self.conexion.execute(
            "SELECT IdPedido, CalcularPicos, COUNT(*) FROM CAJAS_PEDIDO_LINEAS GROUP BY 1, 2"
        ).fetchall()
        self.assertEqual(filas, [(a["IdPedido"], 1, 2), (b["IdPedido"], 0, 1)])

    def test_cambiar_picos_actualiza_todas_las_lineas(self):
        self.cargar_estarepp([linea(1, 100, 5), linea(2, 100, 7)])
        pedido = self.gestor.anadir_desde_estarepp("A.txt", "", "ESTAREPP", True)
        self.gestor.cambiar_picos(pedido["IdPedido"], False)
        self.assertFalse(self.gestor.obtener_pedido(pedido["IdPedido"])["CalcularPicos"])
        self.assertEqual(
            self.conexion.execute("SELECT DISTINCT CalcularPicos FROM CAJAS_PEDIDO_LINEAS").fetchall(),
            [(0,)],
        )

    def test_quitar_y_vaciar_pedidos(self):
        self.cargar_estarepp([linea(1, 100, 5)])
        a = self.gestor.anadir_desde_estarepp("A.txt", "", "ESTAREPP", True)
        self.cargar_estarepp([linea(2, 100, 5)])
        self.gestor.anadir_desde_estarepp("B.txt", "", "ESTAREPP", True)
        self.gestor.eliminar([a["IdPedido"]])
        self.assertEqual(self.gestor.contar_lineas(), 1)
        self.assertEqual(self.gestor.resumen()["Pedidos"], 1)
        self.gestor.vaciar()
        self.assertEqual(self.gestor.contar_lineas(), 0)
        self.assertEqual(self.gestor.resumen()["Pedidos"], 0)

    def test_detecta_el_mismo_fichero_importado_dos_veces(self):
        self.cargar_estarepp([linea(1, 100, 5)])
        self.gestor.anadir_desde_estarepp("A.txt", "", "ESTAREPP", True)
        estadisticas = self.gestor.estadisticas_estarepp()
        self.assertIsNotNone(self.gestor.buscar_duplicado("A.txt", estadisticas))
        self.assertIsNone(self.gestor.buscar_duplicado("B.txt", estadisticas))

    def test_migra_el_pedido_anterior_como_pedido_con_picos(self):
        conexion = sqlite3.connect(":memory:")
        columnas = ", ".join('"' + c + '"' for c in COLUMNAS)
        conexion.execute("CREATE TABLE ESTAREPP (" + columnas + ")")
        marcas = ",".join("?" for _ in COLUMNAS)
        conexion.execute("INSERT INTO ESTAREPP VALUES (" + marcas + ")", linea(1, 100, 5))
        conexion.execute(
            "CREATE TABLE CAJAS_IMPORTACIONES (Tipo TEXT PRIMARY KEY, Ruta TEXT, "
            "FechaHora TEXT, Registros INTEGER, Detalle TEXT)"
        )
        conexion.execute(
            "INSERT INTO CAJAS_IMPORTACIONES VALUES ('PEDIDO', 'H:\\\\PED\\\\E1.txt', '', 1, 'ESTAREPP')"
        )
        conexion.commit()
        pedidos = GestorPedidosCajas(conexion).obtener_pedidos()
        self.assertEqual(len(pedidos), 1)
        self.assertTrue(pedidos[0]["CalcularPicos"])
        self.assertEqual(pedidos[0]["NombreArchivo"], "E1.txt (version anterior)")
        # Una segunda apertura no vuelve a migrar.
        self.assertEqual(len(GestorPedidosCajas(conexion).obtener_pedidos()), 1)
        conexion.close()


class ReglaPicosV21Tests(unittest.TestCase):

    def test_sin_filtro_no_elimina_nada(self):
        self.assertFalse(linea_eliminada_por_picos("S", True, False, None))

    def test_pedido_sin_picos_conserva_la_linea(self):
        self.assertFalse(linea_eliminada_por_picos("S", False, False, set()))

    def test_tienda_fija_conserva_la_linea_aunque_el_pedido_tenga_picos(self):
        self.assertFalse(linea_eliminada_por_picos("S", True, True, set()))

    def test_pedido_con_picos_elimina_sku_bajo_umbral(self):
        self.assertTrue(linea_eliminada_por_picos("S", True, False, {"OTRO"}))
        self.assertFalse(linea_eliminada_por_picos("S", True, False, {"S"}))


if __name__ == "__main__":
    unittest.main()
