import tkinter as tk
from tkinter import messagebox

from bd.basedatos import BaseDatos
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo


class FormularioPaisesFijos:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None, clave_pedido_trabajo=None):

        self.bd = BaseDatos()
        self.ventana_padre = ventana_padre
        self.resultado = None
        self.clave_pedido_trabajo = (
            str(clave_pedido_trabajo).strip().upper()
            if clave_pedido_trabajo is not None
            else None
        )
        self.gestor_pedidos_trabajo = (
            GestorPedidosTrabajo(self.bd.conexion)
            if self.clave_pedido_trabajo
            else None
        )

        self.modo = tk.StringVar(value="LISTA")
        self.destino_manual = tk.IntVar(value=1)

        self.variables_paises = {}
        self.datos_paises = []

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Paises fijos por carrusel")
        self.ventana.geometry("900x700")
        self.ventana.resizable(True, True)
        self.ventana.grab_set()

        self.cargar_paises_tmp()
        self.crear_controles()

    #---------------------------------------------------------
    # Normalizar pais
    #---------------------------------------------------------
    def normalizar_pais(self, pais):

        if pais is None:
            return ""

        return str(pais).strip().upper()

    #---------------------------------------------------------
    # Cargar paises desde el pedido propio del formulario
    #---------------------------------------------------------
    def cargar_paises_tmp(self):

        if self.gestor_pedidos_trabajo is not None:
            registros = self.gestor_pedidos_trabajo.obtener_detalle(
                self.clave_pedido_trabajo
            )
            agrupados = {}
            for _tienda, _aparte, lotes, pais, _tipo_caja in registros:
                clave = self.normalizar_pais(pais)
                if clave not in agrupados:
                    agrupados[clave] = [0, 0.0]
                agrupados[clave][0] += 1
                agrupados[clave][1] += float(lotes or 0)
            datos = [
                (pais, valores[0], valores[1])
                for pais, valores in sorted(agrupados.items())
            ]
        else:
            # Compatibilidad con llamadas antiguas. Los formularios V17.24
            # siempre proporcionan una clave de pedido independiente.
            datos = self.bd.consultar("""
                SELECT
                    IFNULL(Pais, '') AS Pais,
                    COUNT(*) AS Tiendas,
                    IFNULL(SUM(Lotes), 0) AS Lotes
                FROM TMP_ESTAREPP
                GROUP BY IFNULL(Pais, '')
                ORDER BY IFNULL(Pais, '')
            """)

        self.datos_paises = []

        for pais, tiendas, lotes in datos:

            pais_normalizado = self.normalizar_pais(pais)

            if pais_normalizado == "":
                pais_mostrar = "(SIN PAIS)"
            else:
                pais_mostrar = pais_normalizado

            self.datos_paises.append({
                "Pais": pais_normalizado,
                "PaisMostrar": pais_mostrar,
                "Tiendas": tiendas,
                "Lotes": lotes
            })

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        titulo = tk.Label(
            self.ventana,
            text="PAISES FIJOS POR CARRUSEL",
            font=("Arial", 16, "bold")
        )
        titulo.pack(pady=10)

        texto = tk.Label(
            self.ventana,
            text=(
                "Puedes pegar paises manualmente o seleccionar los paises "
                "detectados en el fichero importado."
            ),
            font=("Arial", 10)
        )
        texto.pack(pady=(0, 8))

        self.crear_selector_modo()
        self.crear_bloque_pegar()
        self.crear_bloque_lista()
        self.crear_botones()

    #---------------------------------------------------------
    # Selector de modo
    #---------------------------------------------------------
    def crear_selector_modo(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Modo de seleccion",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="x", padx=12, pady=6)

        tk.Radiobutton(
            marco,
            text="Seleccionar paises desde la lista del fichero",
            variable=self.modo,
            value="LISTA"
        ).grid(row=0, column=0, sticky="w", padx=8)

        tk.Radiobutton(
            marco,
            text="Pegar paises manualmente",
            variable=self.modo,
            value="PEGAR"
        ).grid(row=0, column=1, sticky="w", padx=20)

    #---------------------------------------------------------
    # Bloque pegar paises
    #---------------------------------------------------------
    def crear_bloque_pegar(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Opcion 1 - Pegar paises manualmente",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="x", padx=12, pady=6)

        tk.Label(
            marco,
            text="Pega aqui los paises que quieres forzar:",
            font=("Arial", 10)
        ).grid(row=0, column=0, sticky="w", pady=4)

        self.txt_paises = tk.Text(
            marco,
            width=32,
            height=5
        )
        self.txt_paises.grid(row=1, column=0, rowspan=3, sticky="w", padx=4, pady=4)

        tk.Label(
            marco,
            text="Estos paises van a:",
            font=("Arial", 10)
        ).grid(row=1, column=1, sticky="w", padx=20)

        tk.Radiobutton(
            marco,
            text="CLA 1",
            variable=self.destino_manual,
            value=1
        ).grid(row=2, column=1, sticky="w", padx=20)

        tk.Radiobutton(
            marco,
            text="CLA 2",
            variable=self.destino_manual,
            value=2
        ).grid(row=3, column=1, sticky="w", padx=20)

        tk.Label(
            marco,
            text="El resto de paises ira automaticamente al otro CLA.",
            font=("Arial", 9, "italic")
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

    #---------------------------------------------------------
    # Bloque lista paises
    #---------------------------------------------------------
    def crear_bloque_lista(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Opcion 2 - Paises detectados en el fichero",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="both", expand=True, padx=12, pady=6)

        cabecera = tk.Frame(marco)
        cabecera.pack(fill="x", pady=(0, 4))

        columnas = [
            ("Pais", 18),
            ("Tiendas", 10),
            ("Lotes", 12),
            ("Auto", 8),
            ("CLA 1", 8),
            ("CLA 2", 8)
        ]

        for columna, (texto, ancho) in enumerate(columnas):
            tk.Label(
                cabecera,
                text=texto,
                width=ancho,
                anchor="center" if columna > 0 else "w",
                font=("Arial", 9, "bold")
            ).grid(row=0, column=columna, sticky="w")

        contenedor = tk.Frame(marco)
        contenedor.pack(fill="both", expand=True)

        canvas = tk.Canvas(contenedor, borderwidth=0)
        scrollbar = tk.Scrollbar(contenedor, orient="vertical", command=canvas.yview)

        self.frame_paises = tk.Frame(canvas)

        self.frame_paises.bind(
            "<Configure>",
            lambda evento: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.frame_paises, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.crear_filas_paises()

    #---------------------------------------------------------
    # Crear filas de paises
    #---------------------------------------------------------
    def crear_filas_paises(self):

        if len(self.datos_paises) == 0:

            tk.Label(
                self.frame_paises,
                text="El pedido de este formulario no contiene paises.",
                font=("Arial", 10, "italic")
            ).grid(row=0, column=0, sticky="w", pady=8)

            return

        fila = 0

        for datos in self.datos_paises:

            pais = datos["Pais"]
            pais_mostrar = datos["PaisMostrar"]

            variable = tk.StringVar(value="AUTO")
            self.variables_paises[pais] = variable

            color_fondo = "#ffffff"

            if fila % 2 == 1:
                color_fondo = "#f4f4f4"

            marco_fila = tk.Frame(
                self.frame_paises,
                background=color_fondo
            )
            marco_fila.grid(row=fila, column=0, sticky="w")

            tk.Label(
                marco_fila,
                text=pais_mostrar,
                width=18,
                anchor="w",
                background=color_fondo
            ).grid(row=0, column=0, sticky="w", padx=2, pady=2)

            tk.Label(
                marco_fila,
                text=str(datos["Tiendas"]),
                width=10,
                anchor="center",
                background=color_fondo
            ).grid(row=0, column=1, padx=2)

            tk.Label(
                marco_fila,
                text=str(round(datos["Lotes"], 2)),
                width=12,
                anchor="center",
                background=color_fondo
            ).grid(row=0, column=2, padx=2)

            tk.Radiobutton(
                marco_fila,
                variable=variable,
                value="AUTO",
                background=color_fondo
            ).grid(row=0, column=3, padx=10)

            tk.Radiobutton(
                marco_fila,
                variable=variable,
                value="CLA1",
                background=color_fondo
            ).grid(row=0, column=4, padx=10)

            tk.Radiobutton(
                marco_fila,
                variable=variable,
                value="CLA2",
                background=color_fondo
            ).grid(row=0, column=5, padx=10)

            fila += 1

    #---------------------------------------------------------
    # Crear botones
    #---------------------------------------------------------
    def crear_botones(self):

        marco = tk.Frame(self.ventana)
        marco.pack(fill="x", padx=12, pady=10)

        tk.Button(
            marco,
            text="Aceptar",
            width=16,
            command=self.aceptar
        ).pack(side="right", padx=6)

        tk.Button(
            marco,
            text="Cancelar",
            width=16,
            command=self.cancelar
        ).pack(side="right", padx=6)

    #---------------------------------------------------------
    # Leer paises pegados
    #---------------------------------------------------------
    def leer_paises_pegados(self):

        texto = self.txt_paises.get("1.0", "end").strip()

        paises = []

        for linea in texto.replace(";", "\n").replace(",", "\n").splitlines():

            pais = self.normalizar_pais(linea)

            if pais == "":
                continue

            if pais not in paises:
                paises.append(pais)

        return paises

    #---------------------------------------------------------
    # Aceptar
    #---------------------------------------------------------
    def aceptar(self):

        paises_cla_1 = []
        paises_cla_2 = []
        resto_al_otro = False

        if self.modo.get() == "PEGAR":

            paises = self.leer_paises_pegados()

            if len(paises) == 0:

                messagebox.showwarning(
                    "Sin paises",
                    "Debes pegar al menos un pais."
                )

                return

            if self.destino_manual.get() == 1:
                paises_cla_1 = paises
            else:
                paises_cla_2 = paises

            resto_al_otro = True

        else:

            for pais, variable in self.variables_paises.items():

                valor = variable.get()

                if valor == "CLA1":
                    paises_cla_1.append(pais)

                elif valor == "CLA2":
                    paises_cla_2.append(pais)

            if len(paises_cla_1) == 0 and len(paises_cla_2) == 0:

                messagebox.showwarning(
                    "Sin paises forzados",
                    "Debes marcar al menos un pais para CLA 1 o CLA 2."
                )

                return

        self.resultado = {
            "Activo": True,
            "Modo": self.modo.get(),
            "PaisesCLA1": paises_cla_1,
            "PaisesCLA2": paises_cla_2,
            "RestoAlOtro": resto_al_otro
        }

        self.ventana.destroy()

    #---------------------------------------------------------
    # Cancelar
    #---------------------------------------------------------
    def cancelar(self):

        self.resultado = None
        self.ventana.destroy()

    #---------------------------------------------------------
    # Ejecutar
    #---------------------------------------------------------
    def ejecutar(self):

        self.ventana.wait_window()
        return self.resultado
