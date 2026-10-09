import pyodbc


class ConexionAccess:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self, ruta):

        self.ruta = ruta
        self.conexion = None

    #---------------------------------------------------------
    # Conectar
    #---------------------------------------------------------
    def conectar(self):

        cadena = (
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            f"DBQ={self.ruta};"
        )

        self.conexion = pyodbc.connect(cadena)

    #---------------------------------------------------------
    # Ejecutar consulta
    #---------------------------------------------------------
    def consultar(self, sql):

        cursor = self.conexion.cursor()

        cursor.execute(sql)

        return cursor.fetchall()

    #---------------------------------------------------------
    # Cerrar conexión
    #---------------------------------------------------------
    def cerrar(self):

        if self.conexion:

            self.conexion.close()