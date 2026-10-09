from modulos.formulario_maestro_base import FormularioMaestroBase


class FormularioMaestroTipoCajaTienda(FormularioMaestroBase):

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        super().__init__(ventana_padre)

        self.titulo = "Tipo Caja Tienda a Mayores"
        self.tabla_bd = "TipoCajaTiendaAMayores"
        self.hoja_excel = "TipoCajaTiendaAMayores"
        self.columnas = ["Tienda", "TipoCaja"]
        self.columnas_bd = ["Tienda", "TipoCaja"]
        self.anchuras = {
            "Tienda": 140,
            "TipoCaja": 240
        }
        self.aviso_guardado = (
            "Excepciones por tienda. Doble click para modificar una celda. "
            "Al guardar se actualiza Configuracion.xlsx y despues SQLite."
        )

        self.iniciar_formulario(900, 620)

    #---------------------------------------------------------
    # Validar fila
    #---------------------------------------------------------
    def validar_fila(self, fila, numero_fila):

        tienda = self.entero_obligatorio(fila[0], "Tienda", numero_fila)
        tipo_caja = self.texto_obligatorio(fila[1], "TipoCaja", numero_fila)

        return [tienda, tipo_caja]

    #---------------------------------------------------------
    # Clave unica
    #---------------------------------------------------------
    def obtener_clave_unica(self, fila):

        return fila[0]
