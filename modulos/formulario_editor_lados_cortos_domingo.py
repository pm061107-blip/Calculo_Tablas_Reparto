"""Editor de lados cortos para el modo domingo de Busca Fuera de Tabla (V2.4).

V2.5: las tiendas repetidas aparecen tantas veces como copias tengan (columna
REP). Las colocadas se identifican por su posicion (CLA, destino) y las
pendientes por su posicion en la lista; todas las copias van al mismo CLA.

El calculo ya se ha hecho IGUAL que siempre (lados largos y lados cortos). En
este editor el operador ve como quedan los CLA y los lados, con informacion de
tipo de caja, y puede mover a su gusto las tiendas/apartes que han ido a los
lados cortos:
- Mover seleccionadas a otro lado corto.
- Quitar seleccionadas (pasan a pendientes) y volver a colocarlas por lado.
- Repartir automaticamente las pendientes entre los lados cortos marcados.
La tolva concreta la asigna la aplicacion por prioridad y cada lado corto se
compacta en sus primeras tolvas. No se puede aceptar con pendientes.

Toda la logica vive en MotorBuscaFueraTabla; este formulario solo muestra el
estado y llama al motor.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from modulos.ventanas_tk import maximizar_ventana


TIPOS_CAJA = ("4_Nueva_40", "3_Usada_40", "2_Reutilizada_30", "1_Nueva_30")

NOMBRE_TIPO = {
    "4_Nueva_40": "4 Nueva 40",
    "3_Usada_40": "3 Usada 40",
    "2_Reutilizada_30": "2 Reutil. 30",
    "1_Nueva_30": "1 Nueva 30",
}

# Mismos colores que el mapa PDF de tipo de caja, en version clara.
COLOR_TIPO = {
    "4_Nueva_40": "#f4cccc",
    "3_Usada_40": "#cfe2f3",
    "2_Reutilizada_30": "#d9ead3",
    "1_Nueva_30": "#fff2cc",
}

TODOS_LOS_TIPOS = "Todos los tipos"


def _lotes(valor):
    try:
        numero = float(valor or 0)
    except Exception:
        return str(valor)
    texto = ("%.1f" % numero).rstrip("0").rstrip(".")
    return texto or "0"


def _tipo_y_lotes(cantidad, lotes):
    if not cantidad:
        return "-"
    return str(cantidad) + " / " + _lotes(lotes)


class EditorLadosCortosDomingo:

    def __init__(self, ventana_padre, motor):
        self.motor = motor
        self.aceptado = False
        self.orden_pendientes = ("Lotes", True)

        self.ventana = tk.Toplevel(ventana_padre)
        self.ventana.title("Modo domingo - Ajuste de lados cortos")
        self.ventana.geometry("1400x940")
        self.ventana.minsize(1200, 780)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cancelar)
        try:
            self.ventana.transient(ventana_padre)
        except Exception:
            pass

        self.lados = list(self.motor.LADOS_CORTOS_DOMINGO)
        self.var_auto = {
            (clasificador, lado): tk.BooleanVar(master=self.ventana, value=True)
            for clasificador, lado, _nombre in self.lados
        }
        self.var_mover = tk.StringVar(master=self.ventana, value=self.lados[0][2])
        self.var_filtro_tipo = tk.StringVar(master=self.ventana, value=TODOS_LOS_TIPOS)

        self.crear_controles()
        self.refrescar()

        maximizar_ventana(self.ventana)
        try:
            self.ventana.grab_set()
            self.ventana.focus_force()
        except Exception:
            pass

    # ---------------------------------------------------------
    # Interfaz
    # ---------------------------------------------------------
    def crear_controles(self):
        tk.Label(
            self.ventana,
            text="MODO DOMINGO - AJUSTE DE LADOS CORTOS",
            font=("Arial", 16, "bold"),
        ).pack(pady=(10, 2))
        tk.Label(
            self.ventana,
            text=(
                "El calculo ya esta hecho como siempre. Revisa como quedan los CLA y los lados "
                "y mueve las tiendas de los lados cortos donde quieras. La tolva la asigna la "
                "aplicacion por prioridad y cada lado corto se mantiene en sus primeras tolvas. "
                "Las posiciones de las tablas activas no se mueven."
            ),
            font=("Arial", 9),
            wraplength=1300,
        ).pack(pady=(0, 6))

        arriba = tk.Frame(self.ventana)
        arriba.pack(fill="x", padx=12, pady=2)
        arriba.grid_columnconfigure(0, weight=4)
        arriba.grid_columnconfigure(1, weight=6)

        # Resumen por CLA con tipo de caja
        marco_cla = tk.LabelFrame(
            arriba, text="Como quedan los CLA (tiendas/apartes / lotes)",
            font=("Arial", 10, "bold"), padx=6, pady=4,
        )
        marco_cla.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        columnas_cla = ("CLA", "Tiendas", "Lotes") + TIPOS_CAJA
        self.tabla_cla = ttk.Treeview(
            marco_cla, columns=columnas_cla, show="headings", height=3, selectmode="none"
        )
        for columna in columnas_cla:
            self.tabla_cla.heading(columna, text=NOMBRE_TIPO.get(columna, columna.upper()))
            self.tabla_cla.column(
                columna, width=95 if columna in TIPOS_CAJA else 75, anchor="center"
            )
        self.tabla_cla.tag_configure("diferencia", background="#eeeeee")
        self.tabla_cla.tag_configure("alerta", background="#f4cccc")
        self.tabla_cla.pack(fill="x")
        self.lbl_cla = tk.Label(marco_cla, text="", font=("Arial", 10, "bold"), anchor="w")
        self.lbl_cla.pack(fill="x", pady=(3, 0))

        # Leyenda de colores
        leyenda = tk.Frame(marco_cla)
        leyenda.pack(fill="x", pady=(3, 0))
        tk.Label(leyenda, text="Colores:", font=("Arial", 8)).pack(side="left")
        for tipo in TIPOS_CAJA:
            tk.Label(
                leyenda, text=" " + NOMBRE_TIPO[tipo] + " ", bg=COLOR_TIPO[tipo],
                font=("Arial", 8), relief="groove",
            ).pack(side="left", padx=2)

        # Resumen por lado con tipo de caja
        marco_lados = tk.LabelFrame(
            arriba, text="Como quedan los lados (cajas por tipo: n / lotes)",
            font=("Arial", 10, "bold"), padx=6, pady=4,
        )
        marco_lados.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        columnas = (
            "Lado", "Tolvas", "Cap", "Exist", "Nuevas", "Libres", "Lotes",
        ) + TIPOS_CAJA
        self.tabla_lados = ttk.Treeview(
            marco_lados, columns=columnas, show="headings", height=8, selectmode="none"
        )
        anchos = {"Lado": 140, "Tolvas": 65, "Cap": 45, "Exist": 50, "Nuevas": 55, "Libres": 50, "Lotes": 70}
        for columna in columnas:
            self.tabla_lados.heading(columna, text=NOMBRE_TIPO.get(columna, columna.upper()))
            self.tabla_lados.column(
                columna, width=anchos.get(columna, 92),
                anchor="w" if columna == "Lado" else "center",
                stretch=(columna == "Lado"),
            )
        self.tabla_lados.tag_configure("corto", background="#fff8e1")
        self.tabla_lados.tag_configure("largo", background="#eef3f8")
        self.tabla_lados.pack(fill="x")

        # Zona central: pendientes | acciones | tiendas en lados cortos
        centro = tk.Frame(self.ventana)
        centro.pack(fill="both", expand=True, padx=12, pady=6)
        centro.grid_columnconfigure(0, weight=4)
        centro.grid_columnconfigure(1, weight=0)
        centro.grid_columnconfigure(2, weight=7)
        centro.grid_rowconfigure(0, weight=1)

        self.marco_pendientes = tk.LabelFrame(
            centro, text="Pendientes", font=("Arial", 10, "bold"), padx=6, pady=4
        )
        self.marco_pendientes.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.tabla_pendientes = self._crear_tabla(
            self.marco_pendientes,
            ("Tienda", "Aparte", "Rep", "Lotes", "Pais", "TipoCaja"),
            {"Tienda": 70, "Aparte": 55, "Rep": 40, "Lotes": 70, "Pais": 130, "TipoCaja": 120},
            ordenable=True,
        )

        acciones = tk.Frame(centro)
        acciones.grid(row=0, column=1, sticky="ns", padx=6)
        tk.Label(
            acciones, text="Colocar pendientes\nseleccionadas en:",
            font=("Arial", 10, "bold"), justify="center",
        ).pack(pady=(4, 6))
        self.botones_lado = {}
        for clasificador, lado, nombre in self.lados:
            boton = tk.Button(
                acciones, text=nombre, width=26, height=2, bg="#d9ead3",
                command=lambda c=clasificador, l=lado: self.colocar_seleccionadas(c, l),
            )
            boton.pack(pady=3)
            self.botones_lado[(clasificador, lado)] = boton

        ttk.Separator(acciones, orient="horizontal").pack(fill="x", pady=10)
        tk.Label(
            acciones, text="Repartir automaticamente\nlas pendientes en:",
            font=("Arial", 10, "bold"), justify="center",
        ).pack(pady=(0, 4))
        for clasificador, lado, nombre in self.lados:
            tk.Checkbutton(
                acciones, text=nombre, variable=self.var_auto[(clasificador, lado)], anchor="w",
            ).pack(fill="x")
        tk.Button(
            acciones, text="Repartir pendientes", width=26, command=self.repartir_automatico,
        ).pack(pady=(6, 3))

        self.marco_colocadas = tk.LabelFrame(
            centro, text="Tiendas en lados cortos (movibles)",
            font=("Arial", 10, "bold"), padx=6, pady=4,
        )
        self.marco_colocadas.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        filtro = tk.Frame(self.marco_colocadas)
        filtro.pack(fill="x", pady=(0, 4))
        tk.Label(filtro, text="Ver tipo de caja:").pack(side="left")
        combo = ttk.Combobox(
            filtro, textvariable=self.var_filtro_tipo,
            values=[TODOS_LOS_TIPOS] + list(TIPOS_CAJA), state="readonly", width=20,
        )
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refrescar_colocadas())
        tk.Button(
            filtro, text="Seleccionar todas las visibles", command=self.seleccionar_visibles,
        ).pack(side="left", padx=8)

        self.tabla_colocadas = self._crear_tabla(
            self.marco_colocadas,
            ("Lado", "Destino", "Tienda", "Aparte", "Rep", "Lotes", "Pais", "TipoCaja"),
            {"Lado": 130, "Destino": 65, "Tienda": 70, "Aparte": 55, "Rep": 40, "Lotes": 70, "Pais": 130, "TipoCaja": 120},
        )
        botones_colocadas = tk.Frame(self.marco_colocadas)
        botones_colocadas.pack(fill="x", pady=(6, 0))
        tk.Label(botones_colocadas, text="Mover seleccionadas a:").pack(side="left")
        ttk.Combobox(
            botones_colocadas, textvariable=self.var_mover,
            values=[nombre for _c, _l, nombre in self.lados], state="readonly", width=18,
        ).pack(side="left", padx=4)
        tk.Button(
            botones_colocadas, text="Mover", width=10, bg="#cfe2f3", command=self.mover_seleccionadas,
        ).pack(side="left", padx=4)
        tk.Button(
            botones_colocadas, text="Quitar (pasan a pendientes)", width=26,
            command=self.quitar_seleccionadas,
        ).pack(side="right", padx=4)

        pie = tk.Frame(self.ventana)
        pie.pack(fill="x", padx=12, pady=(4, 12))
        self.lbl_estado = tk.Label(pie, text="", font=("Arial", 10, "bold"), anchor="w")
        self.lbl_estado.pack(side="left", fill="x", expand=True)
        tk.Button(pie, text="Cancelar", width=14, height=2, command=self.cancelar).pack(side="right", padx=6)
        self.btn_aceptar = tk.Button(
            pie, text="ACEPTAR Y EXPORTAR", width=24, height=2, bg="#cfe2f3",
            font=("Arial", 10, "bold"), command=self.aceptar,
        )
        self.btn_aceptar.pack(side="right", padx=6)

    def _crear_tabla(self, marco, columnas, anchos, ordenable=False):
        contenedor = tk.Frame(marco)
        contenedor.pack(fill="both", expand=True)
        tabla = ttk.Treeview(contenedor, columns=columnas, show="headings", selectmode="extended")
        for columna in columnas:
            if ordenable and columna != "Rep":
                tabla.heading(columna, text=columna.upper(), command=lambda c=columna: self.ordenar_pendientes(c))
            else:
                tabla.heading(columna, text=columna.upper())
            tabla.column(columna, width=anchos.get(columna, 80), anchor="center")
        for tipo, color in COLOR_TIPO.items():
            tabla.tag_configure(tipo, background=color)
        scroll = ttk.Scrollbar(contenedor, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tabla

    # ---------------------------------------------------------
    # Refresco
    # ---------------------------------------------------------
    def _nombre_lado(self, clasificador, lado, zona):
        if zona == "Lado_corto":
            for c, l, nombre in self.lados:
                if c == clasificador and l == lado:
                    return nombre
        return "CLA " + str(clasificador) + " - Largo " + str(lado)

    def refrescar(self):
        resumen = self.motor.resumen_domingo()
        cla1 = resumen["CLA"][1]
        cla2 = resumen["CLA"][2]

        for item in self.tabla_cla.get_children():
            self.tabla_cla.delete(item)
        for numero, datos in ((1, cla1), (2, cla2)):
            self.tabla_cla.insert(
                "", "end",
                values=(
                    "CLA " + str(numero), datos["Tiendas"], _lotes(datos["Lotes"]),
                ) + tuple(
                    _tipo_y_lotes(datos["TipoCaja"][tipo], datos["LotesTipoCaja"][tipo])
                    for tipo in TIPOS_CAJA
                ),
            )
        total = max(1.0, cla1["Lotes"] + cla2["Lotes"])
        alerta = resumen["DiferenciaLotes"] > 0.05 * total / 2
        self.tabla_cla.insert(
            "", "end",
            values=(
                "Diferencia", resumen["DiferenciaTiendas"], _lotes(resumen["DiferenciaLotes"]),
            ) + tuple(
                str(abs(cla1["TipoCaja"][tipo] - cla2["TipoCaja"][tipo])) + " / "
                + _lotes(abs(cla1["LotesTipoCaja"][tipo] - cla2["LotesTipoCaja"][tipo]))
                for tipo in TIPOS_CAJA
            ),
            tags=("alerta" if alerta else "diferencia",),
        )
        self.lbl_cla.config(
            text=(
                "Diferencia de lotes entre CLA: " + _lotes(resumen["DiferenciaLotes"])
                + (" (mas del 5%)" if alerta else " (equilibrado)")
            ),
            fg="#9c0006" if alerta else "#176b2c",
        )

        for item in self.tabla_lados.get_children():
            self.tabla_lados.delete(item)
        libres_por_corto = {}
        for fila in resumen["Lados"]:
            zona = fila["Zona"]
            if zona == "Lado_corto":
                libres_por_corto[(fila["Clasificador"], fila["Lado"])] = fila["Libres"]
            self.tabla_lados.insert(
                "", "end",
                values=(
                    self._nombre_lado(fila["Clasificador"], fila["Lado"], zona),
                    str(fila["Desde"]) + "-" + str(fila["Hasta"]),
                    fila["Capacidad"], fila["Existentes"], fila["Nuevas"], fila["Libres"],
                    _lotes(fila["Lotes"]),
                ) + tuple(
                    _tipo_y_lotes(fila["TipoCaja"][tipo], fila["LotesTipoCaja"][tipo])
                    for tipo in TIPOS_CAJA
                ),
                tags=("corto" if zona == "Lado_corto" else "largo",),
            )

        for (clasificador, lado), boton in self.botones_lado.items():
            libres = libres_por_corto.get((clasificador, lado), 0)
            boton.config(
                text=self._nombre_lado(clasificador, lado, "Lado_corto") + "  |  libres: " + str(libres),
                state="normal" if libres > 0 else "disabled",
            )

        self._refrescar_pendientes()
        self._refrescar_colocadas()

        pendientes = resumen["Pendientes"]
        self.marco_pendientes.config(
            text="Pendientes: " + str(pendientes) + " | " + _lotes(resumen["LotesPendientes"]) + " lotes"
        )
        if pendientes > 0:
            self.lbl_estado.config(
                text="Quedan " + str(pendientes) + " tiendas/apartes pendientes. Colocalas para poder exportar.",
                fg="#9c0006",
            )
            self.btn_aceptar.config(state="disabled")
        else:
            self.lbl_estado.config(text="Todo colocado. Puedes aceptar y exportar.", fg="#176b2c")
            self.btn_aceptar.config(state="normal")

    def _refrescar_pendientes(self):
        for item in self.tabla_pendientes.get_children():
            self.tabla_pendientes.delete(item)
        columna, descendente = self.orden_pendientes
        indice = {"Tienda": 0, "Aparte": 1, "Lotes": 2, "Pais": 3, "TipoCaja": 4}[columna]
        filas = sorted(
            enumerate(self.motor.pendientes_domingo),
            key=lambda par: (par[1][indice] if par[1][indice] is not None else ""),
            reverse=descendente,
        )
        for posicion, (tienda, aparte, lotes, pais, tipo_caja) in filas:
            self.tabla_pendientes.insert(
                "", "end",
                iid="P" + str(posicion),
                values=(tienda, aparte, self._texto_rep(tienda, aparte), _lotes(lotes), pais, tipo_caja),
                tags=(tipo_caja,),
            )

    def _refrescar_colocadas(self):
        for item in self.tabla_colocadas.get_children():
            self.tabla_colocadas.delete(item)
        filtro = self.var_filtro_tipo.get()
        colocadas = self.motor.colocadas_domingo()
        visibles = 0
        for destino in colocadas:
            tipo = destino.get("TipoCaja", "")
            if filtro != TODOS_LOS_TIPOS and tipo != filtro:
                continue
            visibles += 1
            self.tabla_colocadas.insert(
                "", "end",
                iid="C" + str(int(destino["Clasificador"])) + "_" + str(int(destino["Destino"])),
                values=(
                    self._nombre_lado(destino["Clasificador"], destino["Lado"], "Lado_corto"),
                    destino["Destino"], destino["Tienda"], destino.get("Aparte") or 0,
                    self._texto_rep(destino["Tienda"], destino.get("Aparte")),
                    _lotes(destino["Lotes"]), destino.get("Pais", ""), tipo,
                ),
                tags=(tipo,),
            )
        texto = "Tiendas en lados cortos (movibles): " + str(len(colocadas))
        if filtro != TODOS_LOS_TIPOS:
            texto += " | visibles " + str(visibles) + " de " + filtro
        self.marco_colocadas.config(text=texto)

    def _texto_rep(self, tienda, aparte):
        try:
            clave = (int(tienda), int(aparte or 0))
        except Exception:
            return ""
        veces = (getattr(self.motor, "repeticiones", {}) or {}).get(clave)
        return "x" + str(veces) if veces else ""

    def ordenar_pendientes(self, columna):
        actual, descendente = self.orden_pendientes
        self.orden_pendientes = (columna, not descendente if actual == columna else columna == "Lotes")
        self._refrescar_pendientes()

    def seleccionar_visibles(self):
        try:
            self.tabla_colocadas.selection_set(self.tabla_colocadas.get_children())
        except Exception:
            pass

    # ---------------------------------------------------------
    # Acciones
    # ---------------------------------------------------------
    @staticmethod
    def _indices_pendientes(tabla):
        return [int(str(item)[1:]) for item in tabla.selection() if str(item).startswith("P")]

    @staticmethod
    def _posiciones(tabla):
        posiciones = []
        for item in tabla.selection():
            texto = str(item)
            if not texto.startswith("C"):
                continue
            clasificador, destino = texto[1:].split("_")
            posiciones.append((int(clasificador), int(destino)))
        return posiciones

    def _ejecutar(self, accion):
        try:
            accion()
        except Exception as error:
            messagebox.showwarning("No se puede realizar", str(error), parent=self.ventana)
        self.refrescar()

    def colocar_seleccionadas(self, clasificador, lado):
        indices = self._indices_pendientes(self.tabla_pendientes)
        if not indices:
            messagebox.showwarning(
                "Sin seleccion", "Selecciona en la lista de pendientes las tiendas a colocar.", parent=self.ventana
            )
            return
        self._ejecutar(lambda: self.motor.colocar_en_lado_corto(indices, clasificador, lado))

    def _lado_por_nombre(self, nombre):
        for clasificador, lado, texto in self.lados:
            if texto == nombre:
                return clasificador, lado
        return None

    def mover_seleccionadas(self):
        claves = self._posiciones(self.tabla_colocadas)
        destino = self._lado_por_nombre(self.var_mover.get())
        if not claves or destino is None:
            messagebox.showwarning(
                "Sin seleccion", "Selecciona tiendas de los lados cortos y el lado al que moverlas.", parent=self.ventana
            )
            return
        self._ejecutar(lambda: self.motor.mover_a_lado_corto(claves, destino[0], destino[1]))

    def quitar_seleccionadas(self):
        claves = self._posiciones(self.tabla_colocadas)
        if not claves:
            messagebox.showwarning(
                "Sin seleccion", "Selecciona las tiendas de los lados cortos que quieres quitar.", parent=self.ventana
            )
            return
        self._ejecutar(lambda: self.motor.quitar_de_lado_corto(claves))

    def repartir_automatico(self):
        lados = [clave for clave, variable in self.var_auto.items() if variable.get()]
        if not lados:
            messagebox.showwarning("Sin lados", "Marca al menos un lado corto.", parent=self.ventana)
            return
        if not self.motor.pendientes_domingo:
            messagebox.showinfo("Sin pendientes", "No hay tiendas pendientes.", parent=self.ventana)
            return
        antes = len(self.motor.pendientes_domingo)

        def accion():
            colocadas = self.motor.repartir_pendientes_domingo(lados)
            if colocadas < antes:
                messagebox.showinfo(
                    "Reparto automatico",
                    "Colocadas: " + str(colocadas) + " de " + str(antes)
                    + ". Las demas no caben en los lados marcados.",
                    parent=self.ventana,
                )

        self._ejecutar(accion)

    def aceptar(self):
        if self.motor.pendientes_domingo:
            messagebox.showwarning(
                "Quedan pendientes",
                "Coloca todas las tiendas/apartes pendientes antes de exportar.",
                parent=self.ventana,
            )
            return
        self.aceptado = True
        self._cerrar()

    def cancelar(self):
        if messagebox.askyesno(
            "Cancelar modo domingo",
            "Se descartaran los cambios y no se guardara ni exportara nada.\n\n¿Cancelar?",
            parent=self.ventana,
        ):
            self.aceptado = False
            self._cerrar()

    def _cerrar(self):
        try:
            self.ventana.grab_release()
        except Exception:
            pass
        self.ventana.destroy()

    def ejecutar(self):
        self.ventana.wait_window()
        return self.aceptado
