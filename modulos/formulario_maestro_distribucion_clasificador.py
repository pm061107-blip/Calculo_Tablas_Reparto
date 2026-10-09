from modulos.formulario_maestro_base import FormularioMaestroBase


class FormularioMaestroDistribucionClasificador(FormularioMaestroBase):

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None):

        super().__init__(ventana_padre)

        self.titulo = "Tablas Distribucion Clasificador"
        self.tabla_bd = "TablasDistribucionClasificador"
        self.hoja_excel = "TablasDistribucionClasificador"
        self.columnas = [
            "Clasificador",
            "Lado",
            "Destino",
            "Descripcion",
            "Prioridad",
            "Prioridad_orden"
        ]
        self.columnas_bd = [
            "Clasificador",
            "Lado",
            "Destino",
            "Descripcion",
            "Prioridad",
            "Prioridad_Orden"
        ]
        self.anchuras = {
            "Clasificador": 100,
            "Lado": 80,
            "Destino": 90,
            "Descripcion": 150,
            "Prioridad": 100,
            "Prioridad_orden": 130
        }
        self.aviso_guardado = (
            "ATENCION: este maestro afecta directamente a destinos, lados y prioridades. "
            "Al guardar se crea backup, se actualiza Configuracion.xlsx y despues SQLite."
        )

        self.iniciar_formulario(1120, 700)

    #---------------------------------------------------------
    # Validar fila
    #---------------------------------------------------------
    def validar_fila(self, fila, numero_fila):

        clasificador = self.entero_obligatorio(fila[0], "Clasificador", numero_fila)
        lado = self.entero_obligatorio(fila[1], "Lado", numero_fila)
        destino = self.entero_obligatorio(fila[2], "Destino", numero_fila)
        descripcion = self.texto_obligatorio(fila[3], "Descripcion", numero_fila)
        prioridad = self.entero_obligatorio(fila[4], "Prioridad", numero_fila)
        prioridad_orden = self.entero_obligatorio(fila[5], "Prioridad_orden", numero_fila)

        if clasificador not in [1, 2]:
            raise Exception("Fila " + str(numero_fila) + ": Clasificador debe ser 1 o 2.")

        if lado not in [1, 2, 3, 4]:
            raise Exception("Fila " + str(numero_fila) + ": Lado debe ser 1, 2, 3 o 4.")

        if descripcion not in ["Lado_corto", "Lado_Largo"]:
            raise Exception(
                "Fila " + str(numero_fila) + ": Descripcion debe ser Lado_corto o Lado_Largo."
            )

        return [
            clasificador,
            lado,
            destino,
            descripcion,
            prioridad,
            prioridad_orden
        ]

    #---------------------------------------------------------
    # Clave unica
    #---------------------------------------------------------
    def obtener_clave_unica(self, fila):

        return (fila[0], fila[2])
