import tkinter as tk
from tkinter import messagebox


class FormularioPaisesFijosFueraTabla:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None, datos_paises=None):

        self.ventana_padre = ventana_padre
        self.datos_paises = datos_paises or []
        self.resultado = None

        self.variables_paises = {}
        self.modo = tk.StringVar(value="LISTA")
        self.destino_manual = tk.IntVar(value=1)

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Paises obligados fuera de tabla")
        self.ventana.geometry("900x700")
        self.ventana.resizable(True, True)
        self.ventana.grab_set()

        self.crear_controles()

    #---------------------------------------------------------
    # Normalizar pais
    #---------------------------------------------------------
    def normalizar_pais(self, pais):

        if pais is None:
            return ""

        return str(pais).strip().upper()

    #---------------------------------------------------------
    # Crear controles
    #---------------------------------------------------------
    def crear_controles(self):

        tk.Label(
            self.ventana,
            text="PAISES OBLIGADOS FUERA DE TABLA",
            font=("Arial", 16, "bold")
        ).pack(pady=10)

        tk.Label(
            self.ventana,
            text="Marca si algun pais debe ir obligatoriamente al CLA 1 o al CLA 2.",
            font=("Arial", 10)
        ).pack(pady=(0, 8))

        self.crear_selector_modo()
        self.crear_bloque_pegar()
        self.crear_bloque_lista()
        self.crear_botones()

    #---------------------------------------------------------
    # Selector modo
    #---------------------------------------------------------
    def crear_selector_modo(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Modo",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="x", padx=12, pady=6)

        tk.Radiobutton(
            marco,
            text="Seleccionar paises de la lista de fuera de tabla",
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
    # Bloque pegar
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
            width=34,
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
    # Bloque lista
    #---------------------------------------------------------
    def crear_bloque_lista(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Opcion 2 - Paises fuera de tabla",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="both", expand=True, padx=12, pady=6)

        cabecera = tk.Frame(marco)
        cabecera.pack(fill="x", pady=(0, 4))

        columnas = [
            ("Pais", 20),
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
    # Crear filas paises
    #---------------------------------------------------------
    def crear_filas_paises(self):

        if len(self.datos_paises) == 0:
            tk.Label(
                self.frame_paises,
                text="No hay paises fuera de tabla.",
                font=("Arial", 10, "italic")
            ).grid(row=0, column=0, sticky="w", pady=8)
            return

        fila = 0

        for datos in self.datos_paises:

            pais = self.normalizar_pais(datos.get("Pais", ""))
            pais_mostrar = datos.get("PaisMostrar", pais)

            variable = tk.StringVar(value="AUTO")
            self.variables_paises[pais] = variable

            color_fondo = "#ffffff" if fila % 2 == 0 else "#f4f4f4"

            marco_fila = tk.Frame(self.frame_paises, background=color_fondo)
            marco_fila.grid(row=fila, column=0, sticky="w")

            tk.Label(marco_fila, text=pais_mostrar, width=20, anchor="w", background=color_fondo).grid(row=0, column=0, sticky="w", padx=2, pady=2)
            tk.Label(marco_fila, text=str(datos.get("Tiendas", 0)), width=10, anchor="center", background=color_fondo).grid(row=0, column=1, padx=2)
            tk.Label(marco_fila, text=str(round(datos.get("Lotes", 0), 2)), width=12, anchor="center", background=color_fondo).grid(row=0, column=2, padx=2)

            tk.Radiobutton(marco_fila, variable=variable, value="AUTO", background=color_fondo).grid(row=0, column=3, padx=10)
            tk.Radiobutton(marco_fila, variable=variable, value="CLA1", background=color_fondo).grid(row=0, column=4, padx=10)
            tk.Radiobutton(marco_fila, variable=variable, value="CLA2", background=color_fondo).grid(row=0, column=5, padx=10)

            fila += 1

    #---------------------------------------------------------
    # Crear botones
    #---------------------------------------------------------
    def crear_botones(self):

        marco = tk.Frame(self.ventana)
        marco.pack(fill="x", padx=12, pady=10)

        tk.Button(
            marco,
            text="Sin paises forzados",
            width=20,
            command=self.sin_paises
        ).pack(side="left", padx=6)

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
            if pais != "" and pais not in paises:
                paises.append(pais)

        return paises

    #---------------------------------------------------------
    # Sin paises
    #---------------------------------------------------------
    def sin_paises(self):

        self.resultado = {
            "Activo": False,
            "Modo": "NINGUNO",
            "PaisesCLA1": [],
            "PaisesCLA2": [],
            "RestoAlOtro": False
        }
        self.ventana.destroy()

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
                messagebox.showwarning("Sin paises", "Debes pegar al menos un pais.", parent=self.ventana)
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
                self.sin_paises()
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
