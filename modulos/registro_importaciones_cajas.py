from datetime import datetime
from pathlib import Path

from bd.basedatos import BaseDatos


class RegistroImportacionesCajas:
    """Persistencia ligera de la ultima importacion de cada fichero de cajas.

    Los datos importados ya permanecen en SQLite. Esta tabla conserva la ruta,
    fecha/hora y numero de registros para poder reutilizarlos sin volver a
    importar y para mostrar al operador exactamente de cuando son.
    """

    def __init__(self):
        self.bd = BaseDatos()
        self._crear_tabla()

    def _crear_tabla(self):
        self.bd.ejecutar("""
            CREATE TABLE IF NOT EXISTS CAJAS_IMPORTACIONES (
                Tipo TEXT PRIMARY KEY,
                Ruta TEXT,
                FechaHora TEXT,
                Registros INTEGER,
                Detalle TEXT
            )
        """)
        self.bd.guardar()

    def guardar(self, tipo, ruta, registros, detalle=""):
        tipo = str(tipo or "").strip().upper()
        if not tipo:
            return

        ruta_texto = ""
        if ruta:
            try:
                ruta_texto = str(Path(ruta))
            except Exception:
                ruta_texto = str(ruta)

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.bd.ejecutar("DELETE FROM CAJAS_IMPORTACIONES WHERE Tipo = ?", (tipo,))
        self.bd.ejecutar(
            "INSERT INTO CAJAS_IMPORTACIONES (Tipo, Ruta, FechaHora, Registros, Detalle) VALUES (?, ?, ?, ?, ?)",
            (tipo, ruta_texto, fecha, int(registros or 0), str(detalle or "")),
        )
        self.bd.guardar()

    def obtener(self, tipo):
        tipo = str(tipo or "").strip().upper()
        filas = self.bd.consultar(
            "SELECT Tipo, Ruta, FechaHora, Registros, Detalle FROM CAJAS_IMPORTACIONES WHERE Tipo = '" + tipo.replace("'", "''") + "'"
        )
        if not filas:
            return None
        tipo, ruta, fecha, registros, detalle = filas[0]
        return {
            "Tipo": tipo,
            "Ruta": ruta or "",
            "FechaHora": fecha or "",
            "Registros": int(registros or 0),
            "Detalle": detalle or "",
        }

    def todos(self):
        filas = self.bd.consultar(
            "SELECT Tipo, Ruta, FechaHora, Registros, Detalle FROM CAJAS_IMPORTACIONES ORDER BY Tipo"
        )
        resultado = {}
        for tipo, ruta, fecha, registros, detalle in filas:
            resultado[str(tipo)] = {
                "Tipo": tipo,
                "Ruta": ruta or "",
                "FechaHora": fecha or "",
                "Registros": int(registros or 0),
                "Detalle": detalle or "",
            }
        return resultado
