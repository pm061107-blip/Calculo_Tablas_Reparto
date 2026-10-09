import unittest

from modulos.calculador_cajas_paises import CalculadorCajasPaises


class CalculadorCajasPaisesV1714Tests(unittest.TestCase):

    def test_ordena_por_cajas_400_volumen_y_pais(self):
        paises = [
            {"Pais": "B", "Cajas400": 30, "VolumenM3": 20.0},
            {"Pais": "C", "Cajas400": 50, "VolumenM3": 10.0},
            {"Pais": "A", "Cajas400": 50, "VolumenM3": 12.0},
            {"Pais": "D", "Cajas400": 50, "VolumenM3": 12.0},
        ]

        ordenados = CalculadorCajasPaises.ordenar_paises(paises)

        self.assertEqual(
            [fila["Pais"] for fila in ordenados],
            ["A", "D", "C", "B"],
        )

    def test_seleccion_devuelve_paises_y_no_indices(self):
        paises = [
            {"Pais": "PAIS GRANDE", "Cajas400": 80},
            {"Pais": "PAIS MEDIO", "Cajas400": 45},
            {"Pais": "PAIS PEQUENO", "Cajas400": 25},
        ]

        seleccion, total = CalculadorCajasPaises.seleccionar_paises_400(
            paises,
            70,
        )

        self.assertEqual(total, 70)
        self.assertEqual(seleccion, {"PAIS MEDIO", "PAIS PEQUENO"})
        self.assertTrue(all(isinstance(pais, str) for pais in seleccion))


if __name__ == "__main__":
    unittest.main()
