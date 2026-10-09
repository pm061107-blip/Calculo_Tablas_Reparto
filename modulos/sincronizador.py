import csv
import io
import os
import sqlite3
import time
from datetime import datetime

from bd.basedatos import BaseDatos
from bd.conexion_access import ConexionAccess
from config.configuracion import Configuracion


class Sincronizador:

    def __init__(self, config=None, bd=None):
        self.config = config if config is not None else Configuracion()
        self.bd = bd if bd is not None else BaseDatos()

    # ---------------------------------------------------------
    # Estado persistente de Tiendas_Web
    # ---------------------------------------------------------
    def _asegurar_tabla_importacion_tiendas_web(self):
        self.bd.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS TIENDAS_WEB_IMPORTACION (
                Id INTEGER PRIMARY KEY,
                Ruta TEXT NOT NULL,
                NombreArchivo TEXT NOT NULL,
                FechaHora TEXT NOT NULL,
                Registros INTEGER NOT NULL
            )
            """
        )
        self.bd.conexion.commit()

    def _nombre_archivo(self, ruta):
        return os.path.basename(str(ruta).replace("\\", "/"))

    def obtener_estado_tiendas_web(self):
        self._asegurar_tabla_importacion_tiendas_web()

        try:
            registros_locales = int(self.bd.contar_registros("Tiendas_Web") or 0)
        except Exception:
            registros_locales = 0

        metadata = None
        try:
            cursor = self.bd.conexion.cursor()
            cursor.execute(
                """
                SELECT Ruta, NombreArchivo, FechaHora, Registros
                FROM TIENDAS_WEB_IMPORTACION
                WHERE Id = 1
                """
            )
            metadata = cursor.fetchone()
        except Exception:
            metadata = None

        if metadata is None:
            return {
                "hay_copia_local": registros_locales > 0,
                "registros_locales": registros_locales,
                "ruta_ultima": "",
                "nombre_ultima": "",
                "fecha_ultima": "",
                "registros_ultima": 0,
            }

        return {
            "hay_copia_local": registros_locales > 0,
            "registros_locales": registros_locales,
            "ruta_ultima": str(metadata[0] or ""),
            "nombre_ultima": str(metadata[1] or ""),
            "fecha_ultima": str(metadata[2] or ""),
            "registros_ultima": int(metadata[3] or 0),
        }

    # ---------------------------------------------------------
    # Lectura y validacion completa de Tiendas_Web
    # ---------------------------------------------------------
    @staticmethod
    def _normalizar_cabecera(valor):
        texto = str(valor or "").replace("\ufeff", "").strip().upper()
        return "".join(caracter for caracter in texto if caracter.isalnum())

    def _resolver_indices_tiendas_web(self, cabeceras):
        normalizadas = [self._normalizar_cabecera(valor) for valor in cabeceras]

        def buscar(candidatos):
            for candidato in candidatos:
                if candidato in normalizadas:
                    return normalizadas.index(candidato)
            return None

        indice_tienda = buscar(("TIEND9", "TIENDA", "CODTIENDA"))
        indice_nombre = buscar(("NOMBRE", "NOMBRETIENDA", "DESTIENDA"))
        indice_pais = buscar(("ORINOM", "PAIS", "NOMBREPAIS"))

        if None not in (indice_tienda, indice_nombre, indice_pais):
            return indice_tienda, indice_nombre, indice_pais

        # Compatibilidad con el formato historico usado por la aplicacion.
        if len(cabeceras) >= 5:
            return 0, 1, 4

        raise ValueError(
            "El fichero no contiene las columnas necesarias de Tiendas_Web. "
            "Se esperaban Tienda, Nombre y Pais."
        )

    @staticmethod
    def _convertir_tienda(valor, numero_linea):
        texto = str(valor or "").strip()
        if texto == "":
            raise ValueError(
                "La tienda esta vacia en la linea " + str(numero_linea) + "."
            )

        try:
            tienda = int(texto)
        except Exception as error:
            raise ValueError(
                "La tienda '" + texto + "' no es un entero valido en la linea "
                + str(numero_linea) + "."
            ) from error

        if tienda <= 0:
            raise ValueError(
                "La tienda debe ser mayor que cero en la linea "
                + str(numero_linea) + "."
            )

        return tienda

    def _leer_tiendas_web(self, ruta):
        # Primero se copia todo el fichero a memoria. La tabla SQLite no se toca
        # hasta que la lectura y la validacion han finalizado correctamente.
        with open(ruta, "rb") as fichero:
            contenido = fichero.read()

        if not contenido:
            raise ValueError("El fichero TIENDAS_WEB.TXT esta vacio.")

        texto = contenido.decode("latin-1")
        lector = csv.reader(io.StringIO(texto, newline=""), delimiter="\t")

        try:
            cabeceras = next(lector)
        except StopIteration as error:
            raise ValueError("El fichero TIENDAS_WEB.TXT no contiene cabecera.") from error

        indice_tienda, indice_nombre, indice_pais = (
            self._resolver_indices_tiendas_web(cabeceras)
        )
        indice_maximo = max(indice_tienda, indice_nombre, indice_pais)

        registros = []
        errores = []

        for numero_linea, fila in enumerate(lector, start=2):
            if not fila or all(str(valor or "").strip() == "" for valor in fila):
                continue

            if len(fila) <= indice_maximo:
                errores.append(
                    "Linea " + str(numero_linea)
                    + ": numero insuficiente de columnas."
                )
                if len(errores) >= 20:
                    break
                continue

            try:
                tienda = self._convertir_tienda(
                    fila[indice_tienda],
                    numero_linea,
                )
                nombre = str(fila[indice_nombre] or "").strip()
                pais = str(fila[indice_pais] or "").strip()
                registros.append((tienda, nombre, pais))
            except ValueError as error:
                errores.append(str(error))
                if len(errores) >= 20:
                    break

        if errores:
            mensaje = "No se ha importado Tiendas_Web por errores de formato:\n\n"
            mensaje += "\n".join(errores)
            if len(errores) >= 20:
                mensaje += "\n\nSe muestran como maximo los primeros 20 errores."
            raise ValueError(mensaje)

        if not registros:
            raise ValueError(
                "El fichero TIENDAS_WEB.TXT no contiene ningun registro valido."
            )

        return registros

    def _leer_tiendas_web_con_reintentos(self, ruta, intentos=3):
        ultimo_error = None

        for intento in range(1, max(1, int(intentos)) + 1):
            try:
                return self._leer_tiendas_web(ruta)
            except FileNotFoundError:
                raise
            except (PermissionError, OSError) as error:
                ultimo_error = error
                if intento < intentos:
                    time.sleep(0.25 * intento)

        if ultimo_error is not None:
            raise ultimo_error

        raise OSError("No se pudo leer TIENDAS_WEB.TXT.")

    # ---------------------------------------------------------
    # Sustitucion atomica de Tiendas_Web
    # ---------------------------------------------------------
    def _reemplazar_tiendas_web(self, ruta, registros, fecha_hora):
        self._asegurar_tabla_importacion_tiendas_web()

        conexion = self.bd.conexion
        cursor = conexion.cursor()

        try:
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("BEGIN IMMEDIATE")

            cursor.execute("DROP TABLE IF EXISTS TIENDAS_WEB_NUEVA")
            cursor.execute(
                """
                CREATE TEMP TABLE TIENDAS_WEB_NUEVA (
                    Tienda INTEGER,
                    Nombre TEXT,
                    Pais TEXT
                )
                """
            )
            cursor.executemany(
                """
                INSERT INTO TIENDAS_WEB_NUEVA (Tienda, Nombre, Pais)
                VALUES (?, ?, ?)
                """,
                registros,
            )

            cursor.execute("SELECT COUNT(*) FROM TIENDAS_WEB_NUEVA")
            total_temporal = int(cursor.fetchone()[0] or 0)
            if total_temporal != len(registros):
                raise RuntimeError(
                    "La tabla temporal no contiene todos los registros leidos."
                )

            cursor.execute("DELETE FROM Tiendas_Web")
            cursor.execute(
                """
                INSERT INTO Tiendas_Web (Tienda, Nombre, Pais)
                SELECT Tienda, Nombre, Pais
                FROM TIENDAS_WEB_NUEVA
                """
            )

            cursor.execute("SELECT COUNT(*) FROM Tiendas_Web")
            total_final = int(cursor.fetchone()[0] or 0)
            if total_final != len(registros):
                raise RuntimeError(
                    "La sustitucion de Tiendas_Web no ha quedado completa."
                )

            cursor.execute("DELETE FROM TIENDAS_WEB_IMPORTACION WHERE Id = 1")
            cursor.execute(
                """
                INSERT INTO TIENDAS_WEB_IMPORTACION
                    (Id, Ruta, NombreArchivo, FechaHora, Registros)
                VALUES
                    (1, ?, ?, ?, ?)
                """,
                (
                    str(ruta),
                    self._nombre_archivo(ruta),
                    fecha_hora,
                    total_final,
                ),
            )

            cursor.execute("DROP TABLE IF EXISTS TIENDAS_WEB_NUEVA")
            conexion.commit()
            return total_final

        except Exception:
            conexion.rollback()
            raise

    # ---------------------------------------------------------
    # Resultado y mensajes de error
    # ---------------------------------------------------------
    @staticmethod
    def _clasificar_error(error):
        if isinstance(error, PermissionError):
            return (
                "PERMISO",
                "Windows ha denegado el acceso al fichero. Puede estar "
                "bloqueado temporalmente o la sesion de red puede no tener "
                "permiso de lectura.",
            )
        if isinstance(error, FileNotFoundError):
            return (
                "NO_ENCONTRADO",
                "No se encuentra el fichero o la unidad de red no esta disponible.",
            )
        if isinstance(error, ValueError):
            return ("FORMATO", str(error))
        if isinstance(error, sqlite3.Error):
            return (
                "BASE_DATOS",
                "No se pudo actualizar la copia local de Tiendas_Web: " + str(error),
            )
        if isinstance(error, OSError):
            return (
                "RED_O_SISTEMA",
                "No se pudo leer el fichero por un problema de red o del sistema: "
                + str(error),
            )
        return ("DESCONOCIDO", str(error))

    def _resultado_error(self, ruta, error):
        estado = self.obtener_estado_tiendas_web()
        tipo_error, descripcion = self._clasificar_error(error)

        return {
            "exito": False,
            "ruta": str(ruta or ""),
            "nombre_archivo": self._nombre_archivo(ruta) if ruta else "",
            "fecha_hora": "",
            "registros": 0,
            "tipo_error": tipo_error,
            "descripcion_error": descripcion,
            "error_tecnico": str(error),
            **estado,
        }

    # ---------------------------------------------------------
    # Sincronizar Tiendas_Web sin destruir la copia anterior
    # ---------------------------------------------------------
    def sincronizar_tiendas_web(self, intentos=3):
        ruta = self.config.tiendas_web()

        print()
        print("========================================")
        print(" SINCRONIZANDO TIENDAS_WEB")
        print("========================================")

        if not str(ruta or "").strip():
            error = FileNotFoundError(
                "La ruta de Tiendas_Web no esta configurada."
            )
            resultado = self._resultado_error(ruta, error)
            print("ERROR - " + resultado["descripcion_error"])
            return resultado

        try:
            registros = self._leer_tiendas_web_con_reintentos(
                ruta,
                intentos=intentos,
            )
            fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            total = self._reemplazar_tiendas_web(
                ruta,
                registros,
                fecha_hora,
            )

            print("OK - " + str(total) + " registros importados")
            print("========================================")

            return {
                "exito": True,
                "ruta": str(ruta),
                "nombre_archivo": self._nombre_archivo(ruta),
                "fecha_hora": fecha_hora,
                "registros": total,
                "tipo_error": "",
                "descripcion_error": "",
                "error_tecnico": "",
                "hay_copia_local": total > 0,
                "registros_locales": total,
                "ruta_ultima": str(ruta),
                "nombre_ultima": self._nombre_archivo(ruta),
                "fecha_ultima": fecha_hora,
                "registros_ultima": total,
            }

        except Exception as error:
            resultado = self._resultado_error(ruta, error)

            print("ERROR - No se pudo actualizar Tiendas_Web")
            print(resultado["descripcion_error"])
            if resultado["hay_copia_local"]:
                print(
                    "Se conserva la copia local con "
                    + str(resultado["registros_locales"])
                    + " registros."
                )
            else:
                print("No existe una copia local disponible.")
            print("========================================")

            return resultado

    # ---------------------------------------------------------
    # Sincronizar TipoCajaInicial
    # ---------------------------------------------------------
    def sincronizar_tipo_caja_inicial(self):
        ruta = self.config.tipo_caja_inicial()

        print()
        print("========================================")
        print(" SINCRONIZANDO TIPO CAJA INICIAL")
        print("========================================")

        if not os.path.exists(ruta):
            print("ERROR")
            print("No existe el fichero:")
            print(ruta)
            return False

        print("OK - Archivo encontrado")

        self.bd.vaciar_tabla("TipoCajaInicial")
        print("OK - Tabla vaciada")

        access = ConexionAccess(ruta)
        access.conectar()

        sql = """
            SELECT
                Cod,
                Pais,
                [Tipo de caja]
            FROM T_TIPO_CAJA_TIENDA
        """

        registros = 0

        for fila in access.consultar(sql):
            self.bd.insertar(
                "TipoCajaInicial",
                (
                    fila.Cod,
                    fila.Pais,
                    fila[2],
                ),
            )
            registros += 1

        access.cerrar()
        self.bd.guardar()

        total = self.bd.contar_registros("TipoCajaInicial")

        print("OK - " + str(registros) + " registros importados")
        print("OK - " + str(total) + " registros en SQLite")
        print("========================================")

        return True

    # ---------------------------------------------------------
    # Sincronizar TablasDistribucionClasificador
    # ---------------------------------------------------------
    def sincronizar_tablas_distribucion_clasificador(self):
        ruta = self.config.tablas_distribucion()

        print()

    # ---------------------------------------------------------
    # Cerrar conexion
    # ---------------------------------------------------------
    def cerrar(self):
        self.bd.cerrar()
