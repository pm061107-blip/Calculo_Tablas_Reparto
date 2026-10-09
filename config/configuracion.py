import json
from pathlib import Path


class Configuracion:

    def __init__(self):

        self.archivo = Path(__file__).parent / "config.json"

        with open(self.archivo, "r", encoding="utf-8") as f:
            self.datos = json.load(f)

    def obtener(self, clave):

        return self.datos["rutas"].get(clave, "")

    def tiendas_web(self):

        return self.obtener("tiendas_web")

    def tipo_caja_inicial(self):

        return self.obtener("tipo_caja_inicial")
    