import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modulos.formulario_calculo_adelanto import FormularioCalculoAdelanto


class _FormularioFalso:
    def __init__(self):
        self.ventana = object()
        self.opcion_subpedido = {
            "Clasificador": 1,
            "Registros": [(1001, 0, 10, "ES", "1_Nueva_30")],
        }
        self.opcion_resto = {
            "Clasificador": 2,
            "Registros": [(2001, 0, 20, "PT", "1_Nueva_30")],
        }

    def validar_sin_solape_tiendas(self, *args, **kwargs):
        return None

    def crear_reparto_clasificador_adelanto(self):
        return None

    def obtener_tiendas_reparto_generado(self, clasificador):
        if clasificador == 1:
            return [(1001,)]
        return [(2001,)]

    def validar_tiendas_grtdaswp_generadas(self, *args, **kwargs):
        return None


class FormularioCalculoAdelantoCodigosTests(unittest.TestCase):

    def test_pregunta_en_orden_y_asigna_cada_codigo_a_su_grupo(self):
        formulario = _FormularioFalso()
        llamadas_exportador = {}

        def exportador_falso(**kwargs):
            llamadas_exportador.update(kwargs)
            return {
                "ruta": Path(kwargs["carpeta_destino"]) / "GRTDASWP.txt",
                "tiendas_no_evacuar": ["1001"],
                "tiendas_evacuar": ["2001"],
                "codigo_no_evacuar": kwargs["codigo_no_evacuar"],
                "codigo_evacuar": kwargs["codigo_evacuar"],
            }

        with tempfile.TemporaryDirectory() as carpeta:
            archivo_csv = Path(carpeta) / "Reparto_Clasificador_1.csv"

            with patch(
                "modulos.formulario_calculo_adelanto.simpledialog.askstring",
                side_effect=["COD_NO_EVACUAR", "COD_EVACUAR"],
            ) as pedir_codigo, patch(
                "modulos.formulario_calculo_adelanto.exportar_tablas_reparto_csv",
                return_value=[archivo_csv],
            ), patch(
                "modulos.formulario_calculo_adelanto.exportar_grtdaswp_adelanto",
                side_effect=exportador_falso,
            ), patch(
                "modulos.formulario_calculo_adelanto.messagebox.showinfo"
            ) as mostrar_info, patch(
                "modulos.formulario_calculo_adelanto.messagebox.showerror"
            ) as mostrar_error:
                FormularioCalculoAdelanto.generar_tablas_exportar(formulario)

        self.assertEqual(pedir_codigo.call_count, 2)

        primera_pregunta = pedir_codigo.call_args_list[0]
        segunda_pregunta = pedir_codigo.call_args_list[1]

        self.assertIn("No_Evacuar", primera_pregunta.args[0])
        self.assertIn("SUBPEDIDO", primera_pregunta.args[0])
        self.assertIn("SUBPEDIDO", primera_pregunta.args[1])
        self.assertIn("NO EVACUAR", primera_pregunta.args[1])

        self.assertIn("Evacuar", segunda_pregunta.args[0])
        self.assertIn("PEDIDO COMPLETO", segunda_pregunta.args[0])
        self.assertIn("PEDIDO COMPLETO", segunda_pregunta.args[1])
        self.assertIn("EVACUAR", segunda_pregunta.args[1])

        self.assertEqual(
            llamadas_exportador["codigo_no_evacuar"],
            "COD_NO_EVACUAR",
        )
        self.assertEqual(
            llamadas_exportador["codigo_evacuar"],
            "COD_EVACUAR",
        )
        self.assertNotIn("codigo", llamadas_exportador)
        self.assertEqual(
            llamadas_exportador["registros_subpedido_generado"],
            [(1001,)],
        )
        self.assertEqual(
            llamadas_exportador["registros_pedido_generado"],
            [(2001,)],
        )
        mostrar_info.assert_called_once()
        mensaje_final = mostrar_info.call_args.args[1]
        self.assertIn("SUBPEDIDO -> No_Evacuar", mensaje_final)
        self.assertIn("PEDIDO COMPLETO MENOS SUBPEDIDO -> Evacuar", mensaje_final)
        mostrar_error.assert_not_called()

    def test_cancelar_codigo_evacuar_detiene_exportacion(self):
        formulario = _FormularioFalso()

        with patch(
            "modulos.formulario_calculo_adelanto.simpledialog.askstring",
            side_effect=["COD_NO_EVACUAR", None],
        ) as pedir_codigo, patch(
            "modulos.formulario_calculo_adelanto.exportar_tablas_reparto_csv"
        ) as exportar_csv, patch(
            "modulos.formulario_calculo_adelanto.exportar_grtdaswp_adelanto"
        ) as exportar_txt:
            FormularioCalculoAdelanto.generar_tablas_exportar(formulario)

        self.assertEqual(pedir_codigo.call_count, 2)
        exportar_csv.assert_not_called()
        exportar_txt.assert_not_called()

    def test_cancelar_codigo_no_evacuar_detiene_antes_de_segunda_pregunta(self):
        formulario = _FormularioFalso()

        with patch(
            "modulos.formulario_calculo_adelanto.simpledialog.askstring",
            return_value=None,
        ) as pedir_codigo, patch(
            "modulos.formulario_calculo_adelanto.exportar_tablas_reparto_csv"
        ) as exportar_csv, patch(
            "modulos.formulario_calculo_adelanto.exportar_grtdaswp_adelanto"
        ) as exportar_txt:
            FormularioCalculoAdelanto.generar_tablas_exportar(formulario)

        self.assertEqual(pedir_codigo.call_count, 1)
        exportar_csv.assert_not_called()
        exportar_txt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
