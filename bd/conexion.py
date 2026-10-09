import sqlite3
from pathlib import Path


class ConexionBD:

    def __init__(self):

        self.ruta_bd = Path(__file__).parent.parent / "reparto.db"
        self.conexion = None

    def conectar(self):

        if self.conexion is None:

            self.conexion = sqlite3.connect(self.ruta_bd)

        return self.conexion

    def cerrar(self):

        if self.conexion:

            self.conexion.close()
            self.conexion = None
            