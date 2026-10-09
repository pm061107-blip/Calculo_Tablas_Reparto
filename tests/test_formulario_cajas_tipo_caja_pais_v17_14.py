import unittest
from unittest.mock import patch

from modulos.formulario_calculo_cajas_pedido import FormularioCalculoCajasPedido


class VariableFalsa:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor


class GestorFalso:
    def __init__(self):
        self.guardado = None

    @staticmethod
    def normalizar_pais(valor):
        return str(valor or "").strip().upper()

    def preparar_actualizacion(self, seleccionados):
        diagnosticos = []
        for pais in seleccionados:
            diagnosticos.append({
                "Pais": pais,
                "Estado": "OK",
                "TipoCaja400": "4_Nueva_40",
                "TipoNuevo": "4_Nueva_40",
            })
        return {
            "Diagnosticos": diagnosticos,
            "Errores": [],
            "Anadir": diagnosticos,
            "SinCambios": [],
            "Conflictos": [],
            "Eliminar": [{"Pais": "NO SELECCIONADO", "TipoActual": "3_Usada_40"}],
            "MaestroActual": {"NO SELECCIONADO": "3_Usada_40"},
        }

    def guardar_maestro_seleccionado(self, objetivo):
        self.guardado = dict(objetivo)
        return {
            "Backup": "backup.xlsx",
            "Anadidos": dict(objetivo),
            "Modificados": {},
            "Eliminados": {"NO SELECCIONADO": "3_Usada_40"},
            "SinCambios": {},
            "TotalMaestro": len(objetivo),
        }

    @staticmethod
    def texto_errores(errores):
        return str(errores)


class FormularioCajasTipoCajaPaisV1714Tests(unittest.TestCase):

    def _crear_formulario(self, seleccion_a, seleccion_b):
        formulario = FormularioCalculoCajasPedido.__new__(FormularioCalculoCajasPedido)
        formulario.ventana = None
        formulario.resumen_paises = {
            "Paises": [{"Pais": "A"}, {"Pais": "B"}],
        }
        formulario.paises_vars = {
            "A": {"400": VariableFalsa(seleccion_a)},
            "B": {"400": VariableFalsa(seleccion_b)},
        }
        formulario.gestor_tipo_caja_pais = GestorFalso()
        return formulario

    @patch("modulos.formulario_calculo_cajas_pedido.messagebox.showinfo")
    @patch("modulos.formulario_calculo_cajas_pedido.messagebox.askyesno", return_value=True)
    def test_envia_al_gestor_solo_los_paises_caja_400(
        self,
        _askyesno,
        _showinfo,
    ):
        formulario = self._crear_formulario(1, 0)

        formulario.cargar_paises_400_en_maestro()

        self.assertEqual(
            formulario.gestor_tipo_caja_pais.guardado,
            {"A": "4_Nueva_40"},
        )

    @patch("modulos.formulario_calculo_cajas_pedido.messagebox.showinfo")
    @patch("modulos.formulario_calculo_cajas_pedido.messagebox.askyesno", return_value=True)
    def test_sin_paises_400_guarda_objetivo_vacio_y_elimina_todo(
        self,
        _askyesno,
        _showinfo,
    ):
        formulario = self._crear_formulario(0, 0)

        formulario.cargar_paises_400_en_maestro()

        self.assertEqual(formulario.gestor_tipo_caja_pais.guardado, {})


if __name__ == "__main__":
    unittest.main()
