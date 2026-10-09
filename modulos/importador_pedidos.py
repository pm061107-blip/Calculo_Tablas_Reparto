from pathlib import Path
from tkinter import filedialog
import tkinter as tk

from modulos.importar_estarepp import ImportarESTAREPP
from modulos.importar_pedidos_pte import ImportarPedidosPTE
from modulos.ventanas_tk import resolver_parent_tk


class ImportadorPedidos:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, parent=None):

        self.ruta = None
        self.tipo = None
        self.parent = resolver_parent_tk(parent)

    @staticmethod
    def _parent_valido(parent):
        return resolver_parent_tk(parent)

    #---------------------------------------------------------
    # Seleccionar fichero
    #---------------------------------------------------------
    def seleccionar_fichero(self):

        parent = resolver_parent_tk(self.parent)
        root_temporal = None

        if parent is None:
            root_temporal = tk.Tk()
            root_temporal.withdraw()
            parent = root_temporal

        try:
            ruta = filedialog.askopenfilename(
                parent=parent,
                title="Importar pedidos",
                filetypes=[
                    ("Todos los ficheros", "*.*"),
                    ("ESTAREPP", "*.txt"),
                    ("CSV", "*.csv")
                ]
            )
        finally:
            if root_temporal is not None:
                try:
                    root_temporal.destroy()
                except Exception:
                    pass

        if ruta == "":
            return False

        self.ruta = Path(ruta)

        return True

    #---------------------------------------------------------
    # Detectar tipo de fichero
    #---------------------------------------------------------
    def detectar_tipo(self):

        with open(
            self.ruta,
            "r",
            encoding="latin-1",
            errors="ignore"
        ) as fichero:

            primera_linea = fichero.readline().upper()

        if "SKU" in primera_linea and "ID LOC." in primera_linea and "DEM.L" in primera_linea:

            self.tipo = "PEDIDOS_PTE"

            return self.tipo

        if self.ruta.suffix.lower() == ".txt":

            self.tipo = "ESTAREPP"

            return self.tipo

        self.tipo = "DESCONOCIDO"

        return self.tipo

    #---------------------------------------------------------
    # Importar
    #---------------------------------------------------------
    def importar(self):

        if not self.seleccionar_fichero():
            return None

        tipo = self.detectar_tipo()

        print()
        print("----------------------------------------")
        print("FICHERO SELECCIONADO")
        print("----------------------------------------")
        print("Archivo:", self.ruta)
        print("Tipo   :", tipo)
        print("----------------------------------------")

        if tipo == "ESTAREPP":

            importador = ImportarESTAREPP(
                [self.ruta],
                parent=self._parent_valido(self.parent)
            )

            resultado = importador.importar()

            if not resultado:
                return None

            return tipo

        if tipo == "PEDIDOS_PTE":

            importador = ImportarPedidosPTE(
                self.ruta
            )

            importador.importar()

            return tipo

        print()
        print("----------------------------------------")
        print("FORMATO NO RECONOCIDO")
        print("----------------------------------------")

        return None
