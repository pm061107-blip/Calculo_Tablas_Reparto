from tkinter import filedialog
import inspect

from modulos.posiciones_estarepp import POSICIONES
from modulos.dialogo_estados_estarepp import (
    seleccionar_estados_estarepp,
    analizar_y_seleccionar_estados_estarepp,
)
from bd.basedatos import BaseDatos
from modulos.ventanas_tk import resolver_parent_tk


class ImportarESTAREPP:

    ESTADOS_IMPORTABLES = ("INICIAL", "1", "2")

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ficheros=None, bd=None, selector_estados=None, parent=None):

        if ficheros is None:
            self.ficheros = []
        else:
            self.ficheros = list(ficheros)

        self.bd = bd if bd is not None else BaseDatos()
        self.selector_estados = selector_estados or seleccionar_estados_estarepp
        self.parent = resolver_parent_tk(parent)
        self.resumen_estados = None
        self.estados_seleccionados = None

    #---------------------------------------------------------
    # Seleccionar ficheros
    #---------------------------------------------------------
    def seleccionar_ficheros(self):

        self.ficheros = filedialog.askopenfilenames(
            parent=resolver_parent_tk(self.parent),
            title="Seleccionar ESTAREPP",
            filetypes=[
                ("Archivos TXT", "*.txt"),
                ("Todos los archivos", "*.*")
            ]
        )

        if len(self.ficheros) == 0:
            print("No se selecciono ningun fichero.")
            return False

        return True

    #---------------------------------------------------------
    # Interpretar una linea
    #---------------------------------------------------------
    def interpretar_linea(self, linea):

        registro = {}

        for campo, (inicio, fin, tipo) in POSICIONES.items():

            valor = linea[inicio:fin].strip()

            if tipo == "N":

                if valor == "":
                    valor = 0
                else:
                    valor = int(valor)

            registro[campo] = valor

        #-----------------------------------------------------
        # Calcular Lotes
        #-----------------------------------------------------
        if registro["UxL"] == 0:
            registro["Lotes"] = 0
        else:
            registro["Lotes"] = registro["Unidades"] / registro["UxL"]

        return registro

    #---------------------------------------------------------
    # Clasificar Estado respetando blanco = Inicial
    #---------------------------------------------------------
    def clasificar_estado_linea(self, linea):

        inicio, fin, _tipo = POSICIONES["Estado"]
        valor = linea[inicio:fin].strip()

        if valor == "":
            return "INICIAL"

        # El campo ocupa dos posiciones y segun el origen puede llegar
        # como " 1", "01", "1", " 2" o "02". Se normaliza como numero
        # para que todos esos formatos representen el mismo Estado.
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            numero = None

        if numero == 1:
            return "1"

        if numero == 2:
            return "2"

        return "OTROS:" + valor

    #---------------------------------------------------------
    # Leer un numero directamente de una linea fija
    #---------------------------------------------------------
    def numero_campo_linea(self, linea, campo):

        inicio, fin, _tipo = POSICIONES[campo]
        valor = linea[inicio:fin].strip()

        if valor == "":
            return 0

        return int(valor)

    #---------------------------------------------------------
    # Calcular lotes de una linea sin interpretar 20 campos
    #---------------------------------------------------------
    def lotes_linea(self, linea):

        unidades = self.numero_campo_linea(linea, "Unidades")
        uxl = self.numero_campo_linea(linea, "UxL")

        if uxl == 0:
            return 0.0

        return unidades / uxl

    #---------------------------------------------------------
    # Analizar lotes por Estado antes de tocar SQLite
    #---------------------------------------------------------
    def analizar_estados(self):

        resumen = {
            "INICIAL": {"Registros": 0, "Lotes": 0.0},
            "1": {"Registros": 0, "Lotes": 0.0},
            "2": {"Registros": 0, "Lotes": 0.0},
            "OTROS": {"Registros": 0, "Lotes": 0.0, "Estados": []},
            "TOTAL": {"Registros": 0, "Lotes": 0.0},
        }

        otros_estados = set()

        for fichero in self.ficheros:

            with open(fichero, "r", encoding="latin-1", errors="ignore") as archivo:

                for numero_linea, linea in enumerate(archivo, start=1):

                    if not linea.strip():
                        continue

                    try:
                        # Para el resumen previo solo necesitamos Estado,
                        # Unidades y UxL. Esto reduce mucho el tiempo de
                        # lectura de ESTAREPP grandes en unidades de red.
                        categoria = self.clasificar_estado_linea(linea)
                        lotes = float(self.lotes_linea(linea))
                    except Exception as error:
                        raise ValueError(
                            "No se pudo interpretar la linea " + str(numero_linea)
                            + " de " + str(fichero) + ": " + str(error)
                        ) from error

                    resumen["TOTAL"]["Registros"] += 1
                    resumen["TOTAL"]["Lotes"] += lotes

                    if categoria in self.ESTADOS_IMPORTABLES:
                        resumen[categoria]["Registros"] += 1
                        resumen[categoria]["Lotes"] += lotes
                    else:
                        valor_estado = categoria.split(":", 1)[1] if ":" in categoria else categoria
                        resumen["OTROS"]["Registros"] += 1
                        resumen["OTROS"]["Lotes"] += lotes
                        otros_estados.add(valor_estado)

        resumen["OTROS"]["Estados"] = sorted(otros_estados)
        self.resumen_estados = resumen

        return resumen

    #---------------------------------------------------------
    # Pedir al operador que estados desea importar
    #---------------------------------------------------------
    def pedir_estados_a_importar(self):

        resumen = self.resumen_estados or self.analizar_estados()

        kwargs = {"ficheros": self.ficheros}

        # Los selectores de pruebas/versiones antiguas pueden no aceptar
        # parent. Se detecta la firma para mantener compatibilidad.
        try:
            firma = inspect.signature(self.selector_estados)
            parametros = firma.parameters.values()
            acepta_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in parametros
            )
            if "parent" in firma.parameters or acepta_kwargs:
                kwargs["parent"] = self.parent
        except (TypeError, ValueError):
            pass

        seleccion = self.selector_estados(
            resumen,
            **kwargs
        )

        if seleccion is None:
            self.estados_seleccionados = None
            return None

        seleccion = set(seleccion).intersection(self.ESTADOS_IMPORTABLES)

        if not seleccion:
            self.estados_seleccionados = None
            return None

        self.estados_seleccionados = seleccion
        return seleccion

    #---------------------------------------------------------
    # Importar solo los estados elegidos
    #---------------------------------------------------------
    def importar_seleccion(self, estados_seleccionados):

        estados_seleccionados = set(estados_seleccionados or [])

        if not estados_seleccionados:
            return False

        # Muy importante: solo se vacia ESTAREPP despues de que
        # el operador haya confirmado una seleccion valida.
        self.bd.vaciar_tabla("ESTAREPP")

        registros = 0
        lotes_importados = 0.0
        por_estado = {
            "INICIAL": {"Registros": 0, "Lotes": 0.0},
            "1": {"Registros": 0, "Lotes": 0.0},
            "2": {"Registros": 0, "Lotes": 0.0},
        }

        for fichero in self.ficheros:

            print("Archivo:", fichero)

            with open(fichero, "r", encoding="latin-1", errors="ignore") as archivo:

                for linea in archivo:

                    if not linea.strip():
                        continue

                    categoria = self.clasificar_estado_linea(linea)

                    if categoria not in estados_seleccionados:
                        continue

                    registro = self.interpretar_linea(linea)

                    self.bd.insertar_diccionario(
                        "ESTAREPP",
                        registro
                    )

                    lotes = float(registro.get("Lotes", 0) or 0)
                    registros += 1
                    lotes_importados += lotes
                    por_estado[categoria]["Registros"] += 1
                    por_estado[categoria]["Lotes"] += lotes

        self.bd.guardar()

        total = self.bd.contar_registros("ESTAREPP")

        print("Registros importados :", registros)
        print("Registros en SQLite  :", total)
        print("Lotes importados     :", round(lotes_importados, 2))
        print("Estados seleccionados:", ", ".join(sorted(estados_seleccionados)))

        for estado in self.ESTADOS_IMPORTABLES:
            if estado not in estados_seleccionados:
                continue
            etiqueta = "Inicial" if estado == "INICIAL" else "Estado " + estado
            print(
                etiqueta + ":",
                por_estado[estado]["Registros"],
                "registros |",
                round(por_estado[estado]["Lotes"], 2),
                "lotes"
            )

        print("----------------------------------------")

        return True

    #---------------------------------------------------------
    # Importar ESTAREPP
    #---------------------------------------------------------
    def importar(self):

        if len(self.ficheros) == 0:
            return False

        print()
        print("----------------------------------------")
        print("ANALIZANDO ESTAREPP")
        print("----------------------------------------")

        # V17.9: el analisis y la seleccion se realizan dentro de un unico
        # panel modal embebido en el formulario activo. No se encadenan dos
        # Toplevel ni se cambia el grab entre una barra y otro selector.
        if self.selector_estados is seleccionar_estados_estarepp:
            seleccion = analizar_y_seleccionar_estados_estarepp(
                self.analizar_estados,
                ficheros=self.ficheros,
                parent=self.parent
            )

            if seleccion is not None:
                seleccion = set(seleccion).intersection(self.ESTADOS_IMPORTABLES)
                seleccion = seleccion or None
                self.estados_seleccionados = seleccion
        else:
            self.analizar_estados()
            seleccion = self.pedir_estados_a_importar()

        if seleccion is None:
            print("Importacion ESTAREPP cancelada por el operador.")
            print("La tabla ESTAREPP existente no se ha modificado.")
            print("----------------------------------------")
            return False

        print()
        print("----------------------------------------")
        print("IMPORTANDO ESTAREPP")
        print("----------------------------------------")

        return self.importar_seleccion(seleccion)
