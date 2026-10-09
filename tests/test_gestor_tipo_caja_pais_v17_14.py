import sqlite3
import tempfile
import unittest
from pathlib import Path

import openpyxl

from modulos.gestor_tipo_caja_pais import (
    GestorTipoCajaPais,
    TIPO_NUEVA_400,
    TIPO_USADA_400,
)


class GestorTipoCajaPaisV1714Tests(unittest.TestCase):

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.temporal.name)
        self.excel = self.carpeta / "Configuracion.xlsx"
        self.conexion = sqlite3.connect(":memory:")
        self._crear_tablas()
        self._crear_excel()
        self.gestor = GestorTipoCajaPais(
            conexion=self.conexion,
            archivo_configuracion=self.excel,
        )

    def tearDown(self):
        self.conexion.close()
        self.temporal.cleanup()

    def _crear_tablas(self):
        cursor = self.conexion.cursor()
        cursor.execute("CREATE TABLE TiposDeCaja (TipoGenerico TEXT, TipoCaja TEXT)")
        cursor.execute("CREATE TABLE Tiendas_Web (Tienda INTEGER, Nombre TEXT, Pais TEXT)")
        cursor.execute("CREATE TABLE TipoCajaInicial (Tienda INTEGER, Pais TEXT, TipoCajaInicial TEXT)")
        cursor.execute("CREATE TABLE TipoCajaPais (Pais TEXT, TipoCajaPais TEXT)")

        cursor.executemany(
            "INSERT INTO TiposDeCaja VALUES (?, ?)",
            [
                ("Nueva", "1_Nueva_30"),
                ("Reutilizada", "2_Reutilizada_30"),
                ("3_Usada_40", "3_Usada_40"),
                ("4_Nueva_40", "4_Nueva_40"),
            ],
        )
        cursor.executemany(
            "INSERT INTO Tiendas_Web VALUES (?, ?, ?)",
            [
                (1, "Tienda 1", "MEXICO"),
                (2, "Tienda 2", "MEXICO"),
                (3, "Tienda 3", "FRANCIA"),
                (4, "Tienda 4", "FRANCIA"),
                (5, "Tienda 5", "MIXTO"),
                (6, "Tienda 6", "MIXTO"),
                (7, "Tienda 7", "ITALIA"),
            ],
        )
        cursor.executemany(
            "INSERT INTO TipoCajaInicial VALUES (?, ?, ?)",
            [
                (1, "MEXICO", "NUEVA"),
                (2, "MEXICO", "NUEVA"),
                (3, "FRANCIA", "REUTILIZADA"),
                (4, "FRANCIA", "REUTILIZADA"),
                (5, "MIXTO", "NUEVA"),
                (6, "MIXTO", "REUTILIZADA"),
                (7, "ITALIA", "REUTILIZADA"),
            ],
        )
        cursor.execute(
            "INSERT INTO TipoCajaPais VALUES (?, ?)",
            ("ITALIA", "4_Nueva_40"),
        )
        self.conexion.commit()

    def _crear_excel(self):
        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.title = "TipoCajaPais"
        hoja.append(["Pais", "TipoCajaPais"])
        hoja.append(["ITALIA", "4_Nueva_40"])
        otra = libro.create_sheet("TiposDeCaja")
        otra.append(["TipoGenerico", "TipoCaja"])
        libro.save(self.excel)
        libro.close()

    def _filas_excel(self):
        libro = openpyxl.load_workbook(self.excel, data_only=True)
        hoja = libro["TipoCajaPais"]
        filas = [
            tuple(fila)
            for fila in hoja.iter_rows(min_row=2, max_col=2, values_only=True)
            if any(valor not in (None, "") for valor in fila)
        ]
        libro.close()
        return filas

    def test_convierte_nueva_y_reutilizada_a_su_tipo_400(self):
        diagnosticos = {
            fila["Pais"]: fila
            for fila in self.gestor.analizar_paises(["MEXICO", "FRANCIA"])
        }

        self.assertEqual(diagnosticos["MEXICO"]["Estado"], "OK")
        self.assertEqual(diagnosticos["MEXICO"]["TipoCaja400"], TIPO_NUEVA_400)
        self.assertEqual(diagnosticos["FRANCIA"]["Estado"], "OK")
        self.assertEqual(diagnosticos["FRANCIA"]["TipoCaja400"], TIPO_USADA_400)

    def test_bloquea_un_pais_mixto(self):
        diagnostico = self.gestor.analizar_paises(["MIXTO"])[0]

        self.assertEqual(diagnostico["Estado"], "ERROR_COHERENCIA")
        self.assertEqual(diagnostico["TipoCaja400"], "")
        self.assertEqual(diagnostico["TiendasNueva"], 1)
        self.assertEqual(diagnostico["TiendasUsada"], 1)

        plan = self.gestor.preparar_actualizacion(["MIXTO"])
        self.assertEqual(len(plan["Errores"]), 1)
        self.assertEqual(plan["Anadir"], [])

    def test_plan_identifica_altas_conflictos_y_paises_a_eliminar(self):
        plan = self.gestor.preparar_actualizacion(["MEXICO", "FRANCIA"])

        self.assertEqual(
            {fila["Pais"] for fila in plan["Anadir"]},
            {"MEXICO", "FRANCIA"},
        )
        self.assertEqual(plan["Conflictos"], [])
        self.assertEqual(
            [(fila["Pais"], fila["TipoActual"]) for fila in plan["Eliminar"]],
            [("ITALIA", "4_Nueva_40")],
        )

    def test_guarda_solo_los_seleccionados_y_elimina_el_resto(self):
        resultado = self.gestor.guardar_maestro_seleccionado({
            "MEXICO": TIPO_NUEVA_400,
            "FRANCIA": TIPO_USADA_400,
        })

        self.assertEqual(set(resultado["Anadidos"]), {"MEXICO", "FRANCIA"})
        self.assertEqual(resultado["Eliminados"], {"ITALIA": "4_Nueva_40"})
        self.assertEqual(resultado["TotalMaestro"], 2)
        self.assertTrue(Path(resultado["Backup"]).exists())

        filas_bd = self.conexion.execute(
            "SELECT Pais, TipoCajaPais FROM TipoCajaPais ORDER BY Pais"
        ).fetchall()
        esperadas = [
            ("FRANCIA", "3_Usada_40"),
            ("MEXICO", "4_Nueva_40"),
        ]
        self.assertEqual(filas_bd, esperadas)
        self.assertEqual(self._filas_excel(), esperadas)

    def test_seleccion_vacia_elimina_todo_el_maestro(self):
        resultado = self.gestor.guardar_maestro_seleccionado({})

        self.assertEqual(resultado["Eliminados"], {"ITALIA": "4_Nueva_40"})
        self.assertEqual(resultado["TotalMaestro"], 0)
        self.assertTrue(Path(resultado["Backup"]).exists())
        self.assertEqual(
            self.conexion.execute("SELECT * FROM TipoCajaPais").fetchall(),
            [],
        )
        self.assertEqual(self._filas_excel(), [])

    def test_no_crea_backup_si_excel_y_sqlite_ya_son_exactos(self):
        resultado = self.gestor.guardar_maestro_seleccionado({
            "ITALIA": "4_Nueva_40",
        })

        self.assertEqual(resultado["Actualizados"], 0)
        self.assertIsNone(resultado["Backup"])
        self.assertFalse(resultado["SQLiteResincronizada"])

    def test_corrige_sqlite_aunque_excel_ya_coincida(self):
        self.conexion.execute(
            "INSERT INTO TipoCajaPais VALUES (?, ?)",
            ("MEXICO", "4_Nueva_40"),
        )
        self.conexion.commit()

        resultado = self.gestor.guardar_maestro_seleccionado({
            "ITALIA": "4_Nueva_40",
        })

        self.assertTrue(resultado["SQLiteResincronizada"])
        self.assertTrue(Path(resultado["Backup"]).exists())
        self.assertEqual(
            self.conexion.execute(
                "SELECT Pais, TipoCajaPais FROM TipoCajaPais ORDER BY Pais"
            ).fetchall(),
            [("ITALIA", "4_Nueva_40")],
        )
        self.assertEqual(self._filas_excel(), [("ITALIA", "4_Nueva_40")])


if __name__ == "__main__":
    unittest.main()
