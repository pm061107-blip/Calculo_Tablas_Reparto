import tkinter as tk
from tkinter import messagebox

from bd.basedatos import BaseDatos
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo


class FormularioPrioridadPaisesUnCarrusel:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ventana_padre=None, configuracion_actual=None, prioridad_general="NORMAL", clave_pedido_trabajo=None):

        self.bd = BaseDatos()
        self.ventana_padre = ventana_padre
        self.resultado = None
        self.prioridad_general = prioridad_general
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

        self.variables_paises = {}
        self.datos_paises = []
        self.configuracion_actual = self.normalizar_configuracion_actual(configuracion_actual)

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Prioridad por pais - un carrusel")
        self.ventana.geometry("900x680")
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
    # Normalizar configuracion existente
    #---------------------------------------------------------
    def normalizar_configuracion_actual(self, configuracion):

        if configuracion is None:
            return {
                "Activo": False,
                "PaisesNormal": [],
                "PaisesInversa": []
            }

        paises_normal = []
        paises_inversa = []

        for pais in configuracion.get("PaisesNormal", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado != "" and pais_normalizado not in paises_normal:
                paises_normal.append(pais_normalizado)

        for pais in configuracion.get("PaisesInversa", []):
            pais_normalizado = self.normalizar_pais(pais)
            if pais_normalizado != "" and pais_normalizado not in paises_inversa:
                paises_inversa.append(pais_normalizado)

        return {
            "Activo": bool(configuracion.get("Activo", False)),
            "PaisesNormal": paises_normal,
            "PaisesInversa": paises_inversa
        }

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
            # Compatibilidad con llamadas antiguas.
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
            text="PRIORIDAD POR PAIS - UN CARRUSEL",
            font=("Arial", 16, "bold")
        )
        titulo.pack(pady=10)

        texto = tk.Label(
            self.ventana,
            text=(
                "Selecciona si cada pais entra con prioridad NORMAL o INVERSA. "
                "Los paises en AUTO usaran la prioridad general del formulario."
            ),
            font=("Arial", 10),
            wraplength=820,
            justify="center"
        )
        texto.pack(pady=(0, 8))

        aviso = tk.Label(
            self.ventana,
            text="Prioridad general actual: " + str(self.prioridad_general),
            font=("Arial", 10, "bold"),
            fg="#1f4e79"
        )
        aviso.pack(pady=(0, 8))

        self.crear_bloque_lista()
        self.crear_botones_masivos()
        self.crear_botones()

    #---------------------------------------------------------
    # Bloque lista paises
    #---------------------------------------------------------
    def crear_bloque_lista(self):

        marco = tk.LabelFrame(
            self.ventana,
            text="Paises detectados en el pedido",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8
        )
        marco.pack(fill="both", expand=True, padx=12, pady=6)

        cabecera = tk.Frame(marco)
        cabecera.pack(fill="x", pady=(0, 4))

        columnas = [
            ("Pais", 22),
            ("Tiendas", 10),
            ("Lotes", 12),
            ("Auto", 10),
            ("Normal", 10),
            ("Inversa", 10)
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

            valor_inicial = "AUTO"

            if pais in self.configuracion_actual.get("PaisesNormal", []):
                valor_inicial = "NORMAL"
            elif pais in self.configuracion_actual.get("PaisesInversa", []):
                valor_inicial = "INVERSA"

            variable = tk.StringVar(value=valor_inicial)
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
                width=22,
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
            ).grid(row=0, column=3, padx=16)

            tk.Radiobutton(
                marco_fila,
                variable=variable,
                value="NORMAL",
                background=color_fondo
            ).grid(row=0, column=4, padx=16)

            tk.Radiobutton(
                marco_fila,
                variable=variable,
                value="INVERSA",
                background=color_fondo
            ).grid(row=0, column=5, padx=16)

            fila += 1

    #---------------------------------------------------------
    # Botones masivos
    #---------------------------------------------------------
    def crear_botones_masivos(self):

        marco = tk.Frame(self.ventana)
        marco.pack(fill="x", padx=12, pady=(4, 2))

        tk.Button(
            marco,
            text="Todos Auto",
            width=14,
            command=lambda: self.marcar_todos("AUTO")
        ).pack(side="left", padx=4)

        tk.Button(
            marco,
            text="Todos Normal",
            width=14,
            command=lambda: self.marcar_todos("NORMAL")
        ).pack(side="left", padx=4)

        tk.Button(
            marco,
            text="Todos Inversa",
            width=14,
            command=lambda: self.marcar_todos("INVERSA")
        ).pack(side="left", padx=4)

    #---------------------------------------------------------
    # Marcar todos
    #---------------------------------------------------------
    def marcar_todos(self, valor):

        for variable in self.variables_paises.values():
            variable.set(valor)

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
    # Aceptar
    #---------------------------------------------------------
    def aceptar(self):

        paises_normal = []
        paises_inversa = []

        for pais, variable in self.variables_paises.items():

            valor = variable.get()

            if valor == "NORMAL":
                paises_normal.append(pais)

            elif valor == "INVERSA":
                paises_inversa.append(pais)

        activo = len(paises_normal) > 0 or len(paises_inversa) > 0

        self.resultado = {
            "Activo": activo,
            "Modo": "PAISES_PRIORIDAD_UN_CARRUSEL",
            "PaisesNormal": paises_normal,
            "PaisesInversa": paises_inversa
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
