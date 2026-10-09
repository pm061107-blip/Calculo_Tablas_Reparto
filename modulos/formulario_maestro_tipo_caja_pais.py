from modulos.formulario_maestro_base import FormularioMaestroBase


class FormularioMaestroTipoCajaPais(FormularioMaestroBase):

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        super().__init__(ventana_padre)

        self.titulo = "Tipo Caja por Pais"
        self.tabla_bd = "TipoCajaPais"
        self.hoja_excel = "TipoCajaPais"
        self.columnas = ["Pais", "TipoCajaPais"]
        self.columnas_bd = ["Pais", "TipoCajaPais"]
        self.anchuras = {
            "Pais": 220,
            "TipoCajaPais": 220
        }
        self.aviso_guardado = (
            "Doble click para modificar una celda. Al guardar se actualiza Configuracion.xlsx "
            "y despues la tabla SQLite TipoCajaPais."
        )

        self.iniciar_formulario(900, 620)

    #---------------------------------------------------------
    # Validar fila
    #---------------------------------------------------------
    def validar_fila(self, fila, numero_fila):

        pais = self.texto_obligatorio(fila[0], "Pais", numero_fila).upper()
        tipo_caja = self.texto_obligatorio(fila[1], "TipoCajaPais", numero_fila)

        return [pais, tipo_caja]

    #---------------------------------------------------------
    # Clave unica
    #---------------------------------------------------------
    def obtener_clave_unica(self, fila):

        return fila[0]
