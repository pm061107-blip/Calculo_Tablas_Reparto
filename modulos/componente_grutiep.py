"""Bloque Tkinter reutilizable para importar y mostrar el estado de GRUTIEP."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from modulos.gestor_grutiep import ErrorGRUTIEP, GestorGRUTIEP


class ComponenteGRUTIEP:
    """Boton de importacion y resumen persistente del ultimo GRUTIEP."""

    def __init__(
        self,
        padre,
        ventana=None,
        padx=12,
        pady=6,
        wraplength=860,
        texto_marco="Control GRUTIEP",
    ):
        self.padre = padre
        self.ventana = ventana or padre.winfo_toplevel()
        self.wraplength = wraplength

        self.marco = tk.LabelFrame(
            padre,
            text=texto_marco,
            font=("Arial", 10, "bold"),
            padx=10,
            pady=8,
        )
        self.marco.pack(fill="x", padx=padx, pady=pady)

        self.boton = tk.Button(
            self.marco,
            text="IMPORTAR GRUTIEP",
            width=22,
            height=2,
            command=self.importar,
        )
        self.boton.grid(row=0, column=0, padx=(0, 14), pady=2, sticky="nw")

        self.lbl_estado = tk.Label(
            self.marco,
            text="",
            anchor="w",
            justify="left",
            wraplength=self.wraplength,
            font=("Arial", 9),
        )
        self.lbl_estado.grid(row=0, column=1, sticky="nsew", pady=2)
        self.marco.grid_columnconfigure(1, weight=1)

        self.refrescar()

    def refrescar(self):
        gestor = GestorGRUTIEP()
        try:
            info = gestor.obtener_ultima_importacion()
            self.lbl_estado.config(text=GestorGRUTIEP.texto_estado_formulario(info))
            return info
        finally:
            gestor.cerrar()

    def importar(self):
        ruta = filedialog.askopenfilename(
            parent=self.ventana,
            title="Selecciona el fichero GRUTIEP",
            filetypes=[
                ("Ficheros de texto", "*.txt *.TXT"),
                ("Todos los ficheros", "*.*"),
            ],
        )

        if ruta is None or str(ruta).strip() == "":
            return None

        gestor = GestorGRUTIEP()
        try:
            info = gestor.importar(Path(ruta))
        except ErrorGRUTIEP as error:
            messagebox.showerror(
                "GRUTIEP no importado",
                str(error)
                + "\n\nSe conserva sin cambios el ultimo GRUTIEP valido.",
                parent=self.ventana,
            )
            return None
        except Exception as error:
            messagebox.showerror(
                "Error importando GRUTIEP",
                str(error)
                + "\n\nSe conserva sin cambios el ultimo GRUTIEP valido.",
                parent=self.ventana,
            )
            return None
        finally:
            gestor.cerrar()

        self.refrescar()

        messagebox.showinfo(
            "GRUTIEP importado",
            "Importacion finalizada correctamente.\n\n"
            + "Fecha: "
            + GestorGRUTIEP.formatear_fecha(info.get("FechaHora"))
            + "\nFichero: "
            + str(info.get("NombreArchivo", ""))
            + "\nTiendas: "
            + str(info.get("Tiendas", 0))
            + "\nGrupos: "
            + GestorGRUTIEP.formatear_grupos(info.get("Grupos", [])),
            parent=self.ventana,
        )

        return info
