"""Repeticion de Tienda+Aparte grandes en varios destinos del mismo CLA (V2.5).

Cuando una Tienda+Aparte supera el umbral de lotes (parametro del operador,
2000 por defecto) se puede repetir en varios destinos del MISMO clasificador:
- El operador decide, para cada Tienda+Aparte, cuantas veces se repite.
- Cada repeticion es una linea mas para el motor, con la parte proporcional
  de lotes (por ejemplo 4500 lotes en 2 destinos = 2250 en cada uno).
- El motor coloca las repeticiones con su logica de siempre, pero todas en el
  CLA donde haya ido la primera.
- Si no caben, el calculo se detiene y avisa: nunca queda nada fuera.
  Excepcion: si el pedido ya no cabia entero antes de repetir (un solo
  carrusel), se permite, pero cada tienda repetida queda con TODAS sus copias
  o con ninguna, y cada copia deja otra tienda para fuera de tabla.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import messagebox

from modulos.ventanas_tk import crear_marco_scrollable


CLAVE_UMBRAL = "UMBRAL_LOTES_REPETICION"
UMBRAL_POR_DEFECTO = 2000.0
REPETICIONES_MAXIMAS = 10


# ---------------------------------------------------------
# Parametro persistente
# ---------------------------------------------------------
def _asegurar_tabla(conexion):
    conexion.execute(
        """
        CREATE TABLE IF NOT EXISTS CONFIG_PARAMETROS (
            Clave TEXT PRIMARY KEY,
            Valor TEXT
        )
        """
    )
    conexion.commit()


def obtener_umbral(conexion):
    try:
        _asegurar_tabla(conexion)
        fila = conexion.execute(
            "SELECT Valor FROM CONFIG_PARAMETROS WHERE Clave=?", (CLAVE_UMBRAL,)
        ).fetchone()
        if fila and str(fila[0]).strip() != "":
            valor = float(str(fila[0]).replace(",", "."))
            if valor > 0:
                return valor
    except Exception:
        pass
    return UMBRAL_POR_DEFECTO


def guardar_umbral(conexion, valor):
    valor = float(valor)
    if valor <= 0:
        raise ValueError("El umbral de lotes debe ser mayor que 0.")
    _asegurar_tabla(conexion)
    conexion.execute(
        "INSERT INTO CONFIG_PARAMETROS (Clave, Valor) VALUES (?, ?) "
        "ON CONFLICT(Clave) DO UPDATE SET Valor=excluded.Valor",
        (CLAVE_UMBRAL, str(valor)),
    )
    conexion.commit()


# ---------------------------------------------------------
# Logica pura (sin interfaz)
# ---------------------------------------------------------
def clave_fila(fila):
    return (int(fila[0]), int(fila[1] or 0))


def agrupar_filas(filas):
    """Suma lotes por Tienda+Aparte conservando pais y tipo de caja."""
    agrupado = {}
    for fila in filas or []:
        clave = clave_fila(fila)
        if clave not in agrupado:
            agrupado[clave] = [clave[0], clave[1], 0.0, fila[3], fila[4]]
        agrupado[clave][2] += float(fila[2] or 0)
    return {clave: tuple(valor) for clave, valor in agrupado.items()}


def detectar_candidatas(filas, umbral):
    """Tienda+Aparte con lotes estrictamente mayores que el umbral."""
    umbral = float(umbral)
    candidatas = [
        fila for fila in agrupar_filas(filas).values() if float(fila[2]) > umbral
    ]
    return sorted(candidatas, key=lambda f: (-float(f[2]), f[0], f[1]))


def sugerencia(lotes, umbral):
    """Repeticiones sugeridas: lotes / umbral redondeado hacia arriba."""
    if float(umbral) <= 0:
        return 1
    return max(1, min(REPETICIONES_MAXIMAS, int(math.ceil(float(lotes) / float(umbral)))))


def normalizar_repeticiones(repeticiones):
    resultado = {}
    for clave, veces in (repeticiones or {}).items():
        try:
            veces = int(veces)
        except Exception:
            continue
        if veces >= 2:
            resultado[(int(clave[0]), int(clave[1] or 0))] = min(veces, REPETICIONES_MAXIMAS)
    return resultado


def destinos_extra(repeticiones):
    return sum(veces - 1 for veces in normalizar_repeticiones(repeticiones).values())


def expandir_filas(filas, repeticiones):
    """Sustituye cada Tienda+Aparte repetida por N lineas con lotes / N.

    Mantiene el resto de campos y el orden original. Las filas son tuplas
    (Tienda, Aparte, Lotes, Pais, TipoCaja, ...).
    """
    repeticiones = normalizar_repeticiones(repeticiones)
    if not repeticiones:
        return list(filas or [])
    resultado = []
    for fila in filas or []:
        veces = repeticiones.get(clave_fila(fila), 1)
        if veces <= 1:
            resultado.append(fila)
            continue
        lotes = float(fila[2] or 0) / veces
        for _ in range(veces):
            nueva = list(fila)
            nueva[2] = lotes
            resultado.append(tuple(nueva))
    return resultado


def texto_resumen(repeticiones):
    repeticiones = normalizar_repeticiones(repeticiones)
    if not repeticiones:
        return "Repeticion de tiendas: ninguna"
    partes = [
        str(tienda) + "/" + str(aparte) + " x" + str(veces)
        for (tienda, aparte), veces in sorted(repeticiones.items())
    ]
    return "Repeticion de tiendas: " + ", ".join(partes)


# ---------------------------------------------------------
# Interfaz
# ---------------------------------------------------------
class DialogoRepeticionTiendas:
    """Lista de Tienda+Aparte que pasan del umbral con sus repeticiones."""

    def __init__(self, parent, conexion, filas, capacidad=None, lineas_base=None, contexto=""):
        self.conexion = conexion
        self.filas = list(filas or [])
        self.capacidad = capacidad
        self.lineas_base = len(agrupar_filas(self.filas)) if lineas_base is None else int(lineas_base)
        self.contexto = contexto
        self.resultado = None
        self.variables = {}
        self.etiquetas_lotes = {}

        self.ventana = tk.Toplevel(parent)
        self.ventana.title("Tiendas que superan el umbral de lotes")
        self.ventana.geometry("900x620")
        self.ventana.minsize(760, 460)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cancelar)
        try:
            self.ventana.transient(parent)
        except Exception:
            pass

        self.var_umbral = tk.StringVar(master=self.ventana, value=self._formato(obtener_umbral(conexion)))
        self.crear_controles()
        self.cargar_lista()
        try:
            self.ventana.grab_set()
            self.ventana.focus_force()
        except Exception:
            pass

    @staticmethod
    def _formato(valor):
        texto = ("%.2f" % float(valor)).rstrip("0").rstrip(".")
        return texto or "0"

    def crear_controles(self):
        tk.Label(
            self.ventana,
            text="REPETIR TIENDAS GRANDES EN EL MISMO CLA",
            font=("Arial", 14, "bold"),
        ).pack(pady=(10, 2))
        tk.Label(
            self.ventana,
            text=(
                (self.contexto + "\n" if self.contexto else "")
                + "Estas Tienda+Aparte superan el umbral de lotes. Indica cuantas veces quieres "
                "repetir cada una: la aplicacion la colocara en ese numero de destinos del mismo "
                "CLA con su logica de siempre. 1 = no repetir."
            ),
            font=("Arial", 9),
            wraplength=840,
            justify="left",
        ).pack(padx=12, pady=(0, 6), fill="x")

        fila_umbral = tk.Frame(self.ventana)
        fila_umbral.pack(fill="x", padx=12, pady=4)
        tk.Label(fila_umbral, text="Umbral de lotes (Tienda+Aparte con mas de):", font=("Arial", 10, "bold")).pack(side="left")
        tk.Entry(fila_umbral, textvariable=self.var_umbral, width=10, justify="center").pack(side="left", padx=6)
        tk.Button(fila_umbral, text="Aplicar y guardar umbral", command=self.aplicar_umbral).pack(side="left", padx=6)
        tk.Button(fila_umbral, text="Sugerir (lotes / umbral)", command=self.sugerir).pack(side="right", padx=4)
        tk.Button(fila_umbral, text="Todas a 1", command=self.todas_a_uno).pack(side="right", padx=4)

        marco = tk.LabelFrame(self.ventana, text="Tiendas", font=("Arial", 10, "bold"), padx=6, pady=4)
        marco.pack(fill="both", expand=True, padx=12, pady=6)
        self.cuerpo = crear_marco_scrollable(marco, padx=0, pady=0)

        pie = tk.Frame(self.ventana)
        pie.pack(fill="x", padx=12, pady=(4, 12))
        self.lbl_destinos = tk.Label(pie, text="", font=("Arial", 10, "bold"), anchor="w")
        self.lbl_destinos.pack(side="left", fill="x", expand=True)
        tk.Button(pie, text="Cancelar calculo", width=16, height=2, command=self.cancelar).pack(side="right", padx=6)
        self.btn_aceptar = tk.Button(
            pie, text="ACEPTAR", width=16, height=2, bg="#cfe2f3",
            font=("Arial", 10, "bold"), command=self.aceptar,
        )
        self.btn_aceptar.pack(side="right", padx=6)

    def _umbral_actual(self):
        texto = str(self.var_umbral.get() or "").strip().replace(",", ".")
        valor = float(texto)
        if valor <= 0:
            raise ValueError("El umbral debe ser mayor que 0.")
        return valor

    def cargar_lista(self):
        anteriores = {clave: var.get() for clave, var in self.variables.items()}
        for hijo in list(self.cuerpo.winfo_children()):
            hijo.destroy()
        self.variables = {}
        self.etiquetas_lotes = {}

        try:
            umbral = self._umbral_actual()
        except Exception:
            umbral = obtener_umbral(self.conexion)
        self.candidatas = detectar_candidatas(self.filas, umbral)

        cabeceras = ("Tienda", "Aparte", "Pais", "Tipo caja", "Lotes", "Repeticiones", "Lotes por destino")
        for columna, texto in enumerate(cabeceras):
            tk.Label(self.cuerpo, text=texto, font=("Arial", 9, "bold"), padx=6).grid(row=0, column=columna, sticky="w")

        if not self.candidatas:
            tk.Label(
                self.cuerpo,
                text="Ninguna Tienda+Aparte supera el umbral. Pulsa ACEPTAR para calcular sin repeticiones.",
                font=("Arial", 9, "italic"),
            ).grid(row=1, column=0, columnspan=7, sticky="w", pady=8)

        for indice, (tienda, aparte, lotes, pais, tipo_caja) in enumerate(self.candidatas, start=1):
            clave = (int(tienda), int(aparte))
            variable = tk.StringVar(master=self.ventana, value=anteriores.get(clave, "1"))
            variable.trace_add("write", lambda *_a: self.actualizar_totales())
            self.variables[clave] = variable
            valores = (tienda, aparte, pais, tipo_caja, self._formato(lotes))
            for columna, valor in enumerate(valores):
                tk.Label(self.cuerpo, text=str(valor), padx=6).grid(row=indice, column=columna, sticky="w")
            tk.Spinbox(
                self.cuerpo, from_=1, to=REPETICIONES_MAXIMAS, width=5,
                textvariable=variable, justify="center",
            ).grid(row=indice, column=5, padx=6, pady=1)
            etiqueta = tk.Label(self.cuerpo, text="", padx=6)
            etiqueta.grid(row=indice, column=6, sticky="w")
            self.etiquetas_lotes[clave] = (etiqueta, float(lotes))
        self.actualizar_totales()

    def _veces(self, clave):
        try:
            veces = int(str(self.variables[clave].get()).strip())
        except Exception:
            return None
        if veces < 1 or veces > REPETICIONES_MAXIMAS:
            return None
        return veces

    def repeticiones(self):
        return normalizar_repeticiones({clave: self._veces(clave) or 1 for clave in self.variables})

    def actualizar_totales(self):
        invalidas = 0
        for clave, (etiqueta, lotes) in self.etiquetas_lotes.items():
            veces = self._veces(clave)
            if veces is None:
                invalidas += 1
                etiqueta.config(text="valor no valido", fg="#9c0006")
            else:
                etiqueta.config(text=self._formato(lotes / veces) + " x " + str(veces), fg="#000000")
        extra = destinos_extra(self.repeticiones())
        necesarios = self.lineas_base + extra
        texto = "Destinos necesarios: " + str(necesarios) + " (" + str(extra) + " por repeticiones)"
        excede = False
        if self.capacidad is not None:
            texto += " | disponibles: " + str(self.capacidad)
            if self.lineas_base > int(self.capacidad):
                # El pedido ya no cabia entero (p. ej. un carrusel): no se
                # bloquea, pero cada copia deja fuera de tabla otra tienda.
                if extra:
                    texto += "  -> el pedido no cabe entero: " + str(extra) + " tiendas mas quedaran fuera"
            else:
                excede = necesarios > int(self.capacidad)
        if excede:
            texto += "  -> NO CABE"
        self.lbl_destinos.config(text=texto, fg="#9c0006" if excede or invalidas else "#176b2c")
        self.btn_aceptar.config(state="disabled" if excede or invalidas else "normal")

    def aplicar_umbral(self):
        try:
            umbral = self._umbral_actual()
            guardar_umbral(self.conexion, umbral)
        except Exception as error:
            messagebox.showerror("Umbral no valido", str(error), parent=self.ventana)
            return
        self.cargar_lista()

    def sugerir(self):
        try:
            umbral = self._umbral_actual()
        except Exception:
            umbral = obtener_umbral(self.conexion)
        for tienda, aparte, lotes, _pais, _tipo in self.candidatas:
            self.variables[(int(tienda), int(aparte))].set(str(sugerencia(lotes, umbral)))

    def todas_a_uno(self):
        for variable in self.variables.values():
            variable.set("1")

    def aceptar(self):
        try:
            guardar_umbral(self.conexion, self._umbral_actual())
        except Exception:
            pass
        self.resultado = self.repeticiones()
        self._cerrar()

    def cancelar(self):
        self.resultado = None
        self._cerrar()

    def _cerrar(self):
        try:
            self.ventana.grab_release()
        except Exception:
            pass
        self.ventana.destroy()

    def ejecutar(self):
        self.ventana.wait_window()
        return self.resultado


def pedir_repeticiones(parent, conexion, filas, capacidad=None, lineas_base=None, contexto=""):
    """Devuelve {(tienda, aparte): veces} (solo veces >= 2), {} o None.

    - {} si ninguna Tienda+Aparte supera el umbral (no se muestra nada).
    - None si el operador cancela el calculo.
    """
    if not detectar_candidatas(filas, obtener_umbral(conexion)):
        return {}
    dialogo = DialogoRepeticionTiendas(
        parent, conexion, filas, capacidad=capacidad, lineas_base=lineas_base, contexto=contexto
    )
    return dialogo.ejecutar()


def capacidad_clasificadores(conexion, clasificadores):
    """Numero de destinos de los clasificadores indicados (None si no se sabe)."""
    try:
        lista = [int(c) for c in (clasificadores or [])]
        if not lista:
            return None
        marcas = ",".join("?" for _ in lista)
        fila = conexion.execute(
            "SELECT COUNT(*) FROM TablasDistribucionClasificador WHERE Clasificador IN (" + marcas + ")",
            lista,
        ).fetchone()
        return int(fila[0] or 0) or None
    except Exception:
        return None


def preguntar_durante_progreso(progreso, crear_progreso, parent, conexion, filas,
                               capacidad=None, lineas_base=None, contexto=""):
    """Cierra el progreso, pregunta las repeticiones y lo vuelve a abrir.

    Devuelve (repeticiones, progreso). repeticiones es None si se cancela.
    Si no hay candidatas no se cierra nada.
    """
    if not detectar_candidatas(filas, obtener_umbral(conexion)):
        return {}, progreso
    if progreso is not None:
        progreso.cerrar()
    repeticiones = pedir_repeticiones(
        parent, conexion, filas, capacidad=capacidad, lineas_base=lineas_base, contexto=contexto
    )
    if repeticiones is None:
        return None, progreso
    return repeticiones, crear_progreso()

