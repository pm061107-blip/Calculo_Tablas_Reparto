from modulos.formulario_maestro_base import FormularioMaestroBase


class FormularioMaestroTiposDeCaja(FormularioMaestroBase):

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        super().__init__(ventana_padre)

        self.titulo = "Homologacion Tipos de Caja"
        self.tabla_bd = "TiposDeCaja"
        self.hoja_excel = "TiposDeCaja"
        self.columnas = ["TipoGenerico", "TipoCaja"]
        self.columnas_bd = ["TipoGenerico", "TipoCaja"]
        self.anchuras = {
            "TipoGenerico": 220,
            "TipoCaja": 220
        }
        self.aviso_guardado = (
            "Homologacion de tipo generico a TipoCaja final. Doble click para modificar. "
            "Al guardar se actualiza Configuracion.xlsx y despues SQLite."
        )

        self.iniciar_formulario(900, 620)

    #---------------------------------------------------------
    # Validar fila
    #---------------------------------------------------------
    def validar_fila(self, fila, numero_fila):

        tipo_generico = self.texto_obligatorio(fila[0], "TipoGenerico", numero_fila)
        tipo_caja = self.texto_obligatorio(fila[1], "TipoCaja", numero_fila)

        return [tipo_generico, tipo_caja]

    #---------------------------------------------------------
    # Clave unica
    #---------------------------------------------------------
    def obtener_clave_unica(self, fila):

        return fila[0].upper()
