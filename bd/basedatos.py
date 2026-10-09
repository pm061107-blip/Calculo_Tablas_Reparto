from bd.conexion import ConexionBD


class BaseDatos:

    #---------------------------------------------------------
    # Constructor
    #---------------------------------------------------------
    def __init__(self):

        self.bd = ConexionBD()
        self.conexion = self.bd.conectar()

    #---------------------------------------------------------
    # Inicializar Base de Datos
    #---------------------------------------------------------
    def crear_base(self):

        print("======================================")
        print(" BASE DE DATOS INICIALIZADA")
        print("======================================")

    #---------------------------------------------------------
    # Crear una tabla
    #---------------------------------------------------------
    def crear_tabla(self, nombre, campos):

        cursor = self.conexion.cursor()

        sql = f"CREATE TABLE IF NOT EXISTS {nombre} ("

        lista = []

        for campo, tipo in campos:
            lista.append(f"{campo} {tipo}")

        sql += ", ".join(lista)
        sql += ")"

        cursor.execute(sql)

        self.conexion.commit()

        print(f"Tabla {nombre} creada correctamente.")

    #---------------------------------------------------------
    # Crear todas las tablas
    #---------------------------------------------------------
    def crear_tablas(self):

        print()
        print("Creando tablas...")

        self.crear_tabla(
            "Tiendas_Web",
            [
                ("Tienda", "INTEGER"),
                ("Nombre", "TEXT"),
                ("Pais", "TEXT")
            ]
        )
        self.ejecutar("""
            CREATE INDEX IF NOT EXISTS IX_TIENDAS_WEB_TIENDA
            ON Tiendas_Web (Tienda)
        """)
        self.crear_tabla(
            "TIENDAS_WEB_IMPORTACION",
            [
                ("Id", "INTEGER PRIMARY KEY"),
                ("Ruta", "TEXT NOT NULL"),
                ("NombreArchivo", "TEXT NOT NULL"),
                ("FechaHora", "TEXT NOT NULL"),
                ("Registros", "INTEGER NOT NULL")
            ]
        )

        self.crear_tabla(
            "TipoCajaInicial",
            [
                ("Tienda", "INTEGER"),
                ("Pais", "TEXT"),
                ("TipoCajaInicial", "TEXT")
            ]
        )

        self.crear_tabla(
            "TipoCajaPais",
            [
                ("Pais", "TEXT"),
                ("TipoCajaPais", "TEXT")
            ]
        )
        self.crear_tabla(
            "TipoCajaTiendaAMayores",
            [
                ("Tienda", "INTEGER"),
                ("TipoCaja", "TEXT")
            ]
        )
        self.crear_tabla(
            "TiposDeCaja",
            [
                ("TipoGenerico", "TEXT"),
                ("TipoCaja", "TEXT")
            ]
        )

        # Tiendas con tolerancia especial para XDOC.
        # Si una tienda no existe en esta tabla, el motor usa 0%%.
        # PerfilVolumetria se conserva por compatibilidad, pero el motor usa
        # siempre el perfil fijo 01_UNICA.
        self.crear_tabla(
            "TiendasXDOC",
            [
                ("Tienda", "INTEGER"),
                ("ToleranciaXDOC", "INTEGER"),
                ("PerfilVolumetria", "TEXT")
            ]
        )
        # Migracion no destructiva para instalaciones anteriores. SQLite no
        # modifica una tabla ya existente con CREATE TABLE IF NOT EXISTS, por
        # lo que la nueva columna debe asegurarse de forma explicita.
        self.asegurar_columna(
            "TiendasXDOC",
            "PerfilVolumetria",
            "TEXT"
        )
        try:
            self.ejecutar("""
                UPDATE TiendasXDOC
                SET PerfilVolumetria = '01_UNICA'
            """)
        except Exception:
            pass

        self.crear_tabla(
            "CAJAS_IMPORTACIONES",
            [
                ("Tipo", "TEXT PRIMARY KEY"),
                ("Ruta", "TEXT"),
                ("FechaHora", "TEXT"),
                ("Registros", "INTEGER"),
                ("Detalle", "TEXT")
            ]
        )

        # Maestro global para validar las tiendas exportadas a CLA 1 y CLA 2.
        # TRCODS y TRTIEN se almacenan siempre como INTEGER.
        self.crear_tabla(
            "GRUTIEP",
            [
                ("TRCODS", "INTEGER NOT NULL"),
                ("TRDESC", "TEXT"),
                ("TRTIEN", "INTEGER NOT NULL")
            ]
        )
        self.ejecutar("""
            CREATE UNIQUE INDEX IF NOT EXISTS UX_GRUTIEP_GRUPO_TIENDA
            ON GRUTIEP (TRCODS, TRTIEN)
        """)
        self.ejecutar("""
            CREATE INDEX IF NOT EXISTS IX_GRUTIEP_TRTIEN
            ON GRUTIEP (TRTIEN)
        """)
        self.crear_tabla(
            "GRUTIEP_IMPORTACION",
            [
                ("Id", "INTEGER PRIMARY KEY"),
                ("Ruta", "TEXT NOT NULL"),
                ("NombreArchivo", "TEXT NOT NULL"),
                ("FechaHora", "TEXT NOT NULL"),
                ("Registros", "INTEGER NOT NULL"),
                ("Tiendas", "INTEGER NOT NULL")
            ]
        )

        self.crear_tabla(
            "TablasDistribucionClasificador",
            [
                ("Clasificador", "INTEGER"),
                ("Lado", "INTEGER"),
                ("Destino", "INTEGER"),
                ("Descripcion", "TEXT"),
                ("Prioridad", "INTEGER"),
                ("Prioridad_Orden", "INTEGER")
            ]
        )
        self.crear_tabla(
            "ESTAREPP",
            [
                ("MarcaComercial", "TEXT"),
                ("Campaña", "TEXT"),
                ("Año", "INTEGER"),
                ("Tienda", "INTEGER"),
                ("Seccion", "INTEGER"),
                ("Aparte", "INTEGER"),
                ("DescTienda", "TEXT"),
                ("Modelo", "INTEGER"),
                ("Calidad", "INTEGER"),
                ("Color", "INTEGER"),
                ("TallaNum", "INTEGER"),
                ("TallaAlfa", "TEXT"),
                ("POC", "TEXT"),
                ("Familia", "INTEGER"),
                ("Subfamilia", "INTEGER"),
                ("Carrusel", "TEXT"),
                ("Estado", "INTEGER"),
                ("Unidades", "INTEGER"),
                ("UoL", "TEXT"),
                ("UxL", "INTEGER"),
                ("Lotes", "REAL"),
            ]
        )
        self.crear_tabla(
            "TMP_ESTAREPP",
            [
                ("Tienda", "INTEGER"),
                ("Aparte", "INTEGER"),
                ("Lotes", "REAL"),
                ("Pais", "TEXT"),
                ("TipoCaja", "TEXT")
            ]
        )

        
        self.crear_tabla(
            "REPARTO_CLASIFICADOR",
            [
                ("Clasificador", "INTEGER"),
                ("Lado", "INTEGER"),
                ("Zona", "TEXT"),
                ("Tramo", "INTEGER"),
                ("Bloque", "INTEGER"),
                ("Destino", "INTEGER"),
                ("Tienda", "INTEGER"),
                ("Aparte", "INTEGER"),
                ("Lotes", "REAL"),
                ("TipoCaja", "TEXT"),
                ("Prioridad", "INTEGER"),
                ("PrioridadOrden", "INTEGER")
            ]
        )
        print("Todas las tablas creadas correctamente.")

    #---------------------------------------------------------
    # Asegurar columna sin borrar datos existentes
    #---------------------------------------------------------
    def asegurar_columna(self, tabla, columna, tipo):

        cursor = self.conexion.cursor()
        cursor.execute("PRAGMA table_info(" + tabla + ")")
        existentes = {
            str(fila[1]).strip().lower()
            for fila in cursor.fetchall()
        }

        if str(columna).strip().lower() in existentes:
            return False

        cursor.execute(
            "ALTER TABLE " + tabla + " ADD COLUMN " + columna + " " + tipo
        )
        self.conexion.commit()
        print("Columna " + columna + " añadida a " + tabla + ".")
        return True
    #---------------------------------------------------------
    # Vaciar una tabla
    #---------------------------------------------------------
    def vaciar_tabla(self, nombre):

        cursor = self.conexion.cursor()

        cursor.execute(f"DELETE FROM {nombre}")

        self.conexion.commit()

        print(f"Tabla {nombre} vaciada correctamente.")

    #---------------------------------------------------------
    # Insertar un registro
    #---------------------------------------------------------
    def insertar(self, tabla, valores):

        cursor = self.conexion.cursor()

        marcadores = ",".join(["?"] * len(valores))

        sql = f"INSERT INTO {tabla} VALUES ({marcadores})"

        cursor.execute(sql, valores)
    #---------------------------------------------------------
    # Insertar un registro
    #---------------------------------------------------------
    def insertar(self, tabla, valores):

        cursor = self.conexion.cursor()

        marcadores = ",".join(["?"] * len(valores))

        sql = f"INSERT INTO {tabla} VALUES ({marcadores})"

        cursor.execute(sql, valores)

    #---------------------------------------------------------
    # Insertar un diccionario
    #---------------------------------------------------------
    def insertar_diccionario(self, tabla, registro):

        cursor = self.conexion.cursor()

        columnas = ",".join(registro.keys())

        marcadores = ",".join(["?"] * len(registro))

        sql = f"""
        INSERT INTO {tabla}
        ({columnas})
        VALUES
        ({marcadores})
        """

        cursor.execute(sql, tuple(registro.values()))
    #---------------------------------------------------------
    # Guardar cambios
    #---------------------------------------------------------
    def guardar(self):

        self.conexion.commit()

    #---------------------------------------------------------
    # Contar registros
    #---------------------------------------------------------
    def contar_registros(self, tabla):

        cursor = self.conexion.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM {tabla}")

        return cursor.fetchone()[0]

    #---------------------------------------------------------
    # Ejecutar SQL
    #---------------------------------------------------------
    def ejecutar(self, sql, parametros=None):

        cursor = self.conexion.cursor()

        if parametros is None:

            cursor.execute(sql)

        else:

            cursor.execute(sql, parametros)

        self.conexion.commit()

    #---------------------------------------------------------
    # Consultar
    #---------------------------------------------------------
    def consultar(self, sql):

        cursor = self.conexion.cursor()

        cursor.execute(sql)

        return cursor.fetchall()
    #---------------------------------------------------------
    # Borrar todos los registros de una tabla
    #---------------------------------------------------------
    def borrar_tabla(self, tabla):

        cursor = self.conexion.cursor()

        cursor.execute(f"DELETE FROM {tabla}")

        self.conexion.commit()
    #---------------------------------------------------------
    # Obtener todos los registros de una tabla
    #---------------------------------------------------------
    def leer_tabla(self, tabla):

        cursor = self.conexion.cursor()

        cursor.execute(f"SELECT * FROM {tabla}")

        return cursor.fetchall()
    #---------------------------------------------------------
    # Cerrar
    #---------------------------------------------------------
    def cerrar(self):

        self.bd.cerrar()