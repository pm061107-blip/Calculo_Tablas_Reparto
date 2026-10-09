from modulos.formulario_maestro_base import FormularioMaestroBase


class FormularioMaestroTiendasXDOC(FormularioMaestroBase):

    def __init__(self, ventana_padre=None):
        super().__init__(ventana_padre)

        self.titulo = "Tiendas XDOC"
        self.tabla_bd = "TiendasXDOC"
        self.hoja_excel = "TiendasXDOC"
        self.columnas = ["Tienda", "ToleranciaXDOC", "PerfilVolumetria"]
        self.columnas_bd = ["Tienda", "ToleranciaXDOC", "PerfilVolumetria"]
        self.anchuras = {
            "Tienda": 180,
            "ToleranciaXDOC": 220,
            "PerfilVolumetria": 220
        }
        self.aviso_guardado = (
            "Solo hace falta dar de alta las tiendas con una tolerancia XDOC especial. "
            "Si una tienda no aparece en este maestro, se usa 0%, es decir, la caja XDOC "
            "debe tener exactamente las mismas unidades que la moda. Para las tiendas actuales "
            "con regla especial utiliza 80%, que permite cajas desde el 20% hasta el 100% de la moda. "
            "PerfilVolumetria es fijo para todas las tiendas y siempre se guarda como 01_UNICA."
        )

        self.iniciar_formulario(1050, 620)

    def validar_fila(self, fila, numero_fila):
        tienda = self.entero_obligatorio(fila[0], "Tienda", numero_fila)
        tolerancia = self.entero_obligatorio(fila[1], "ToleranciaXDOC", numero_fila)

        if tolerancia < 0 or tolerancia > 100:
            raise Exception(
                "Fila " + str(numero_fila) + ": ToleranciaXDOC debe estar entre 0 y 100."
            )

        # La columna se conserva por compatibilidad con la tabla y el Excel,
        # pero el operador no puede seleccionar otro perfil.
        return [tienda, tolerancia, "01_UNICA"]

    def obtener_clave_unica(self, fila):
        return fila[0]
