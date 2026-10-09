from datetime import datetime
from pathlib import Path


COLUMNA_3 = "Z"
COLUMNA_4 = "ADELANTO"
COLUMNA_5 = "0AUTOMATISTAS"
COLUMNA_7 = "0"
NOMBRE_FICHERO = "GRTDASWP.txt"


# Regla funcional de Calculo Adelanto:
# - SUBPEDIDO                       -> No_Evacuar
# - PEDIDO COMPLETO MENOS SUBPEDIDO -> Evacuar
#
# Se mantienen los nombres antiguos de algunos parametros y claves de retorno
# para no romper llamadas de versiones anteriores, pero toda llamada nueva usa
# los nombres explicitos codigo_no_evacuar y codigo_evacuar.


def normalizar_tienda(valor):
    """Devuelve la tienda normalizada sin decimales artificiales."""
    if valor is None:
        return None

    texto = str(valor).strip()

    if texto == "":
        return None

    try:
        numero = float(texto.replace(",", "."))
        if numero.is_integer():
            return str(int(numero))
    except Exception:
        pass

    return texto


def obtener_tiendas_unicas(registros):
    """Obtiene tiendas unicas ignorando apartes y las ordena de forma estable."""
    tiendas = set()

    for registro in registros or []:
        if registro is None:
            continue

        if isinstance(registro, (list, tuple)):
            if len(registro) == 0:
                continue
            valor_tienda = registro[0]
        else:
            valor_tienda = registro

        tienda = normalizar_tienda(valor_tienda)

        if tienda is not None:
            tiendas.add(tienda)

    def clave_orden(valor):
        try:
            return (0, int(valor))
        except Exception:
            return (1, valor)

    return sorted(tiendas, key=clave_orden)


def _validar_codigo(codigo, bloque="GRTDASWP"):
    if codigo is None:
        raise ValueError("El codigo de " + bloque + " no puede estar vacio.")

    codigo = str(codigo).strip()

    if codigo == "":
        raise ValueError("El codigo de " + bloque + " no puede estar vacio.")

    if "\t" in codigo or "\r" in codigo or "\n" in codigo:
        raise ValueError(
            "El codigo de " + bloque + " contiene caracteres no validos."
        )

    return codigo


def _crear_linea(codigo, nombre, tienda):
    linea = [
        codigo,
        nombre,
        COLUMNA_3,
        COLUMNA_4,
        COLUMNA_5,
        tienda,
        COLUMNA_7,
    ]

    if len(linea) != 7:
        raise ValueError("La linea GRTDASWP no tiene exactamente 7 columnas.")

    return linea


def _resolver_codigos(codigo, codigo_no_evacuar, codigo_evacuar):
    """Resuelve los codigos explicitos conservando compatibilidad antigua."""
    # En versiones antiguas el parametro generico `codigo` representaba el
    # codigo Evacuar. Solo se usa como respaldo cuando no se facilita el nombre
    # explicito.
    if codigo_evacuar is None:
        codigo_evacuar = codigo

    codigo_evacuar = _validar_codigo(
        codigo_evacuar,
        "Evacuar - pedido completo",
    )

    # Compatibilidad con la version de codigo unico: si no se facilita el
    # codigo No_Evacuar, se reutiliza el codigo Evacuar.
    if codigo_no_evacuar is None:
        codigo_no_evacuar = codigo_evacuar

    codigo_no_evacuar = _validar_codigo(
        codigo_no_evacuar,
        "No_Evacuar - subpedido",
    )

    return codigo_no_evacuar, codigo_evacuar


def construir_lineas_grtdaswp(
    codigo=None,
    registros_subpedido_generado=None,
    registros_pedido_generado=None,
    fecha=None,
    codigo_no_evacuar=None,
    codigo_evacuar=None,
):
    """
    Construye un unico GRTDASWP con dos bloques disjuntos:

    - SUBPEDIDO -> No_Evacuar: usa codigo_no_evacuar y contiene las tiendas
      de la tabla FINAL generada para el subpedido.
    - PEDIDO COMPLETO MENOS SUBPEDIDO -> Evacuar: usa codigo_evacuar y contiene
      las tiendas de la tabla FINAL generada para el pedido/resto.

    La separacion es por tienda, no por Tienda+Aparte.

    Compatibilidad: `codigo` conserva el significado antiguo de codigo Evacuar.
    Si no se facilita codigo_no_evacuar, se reutiliza ese mismo codigo como en
    las versiones anteriores a los dos codigos independientes.
    """
    codigo_no_evacuar, codigo_evacuar = _resolver_codigos(
        codigo=codigo,
        codigo_no_evacuar=codigo_no_evacuar,
        codigo_evacuar=codigo_evacuar,
    )

    if fecha is None:
        fecha = datetime.now().strftime("%Y%m%d")
    else:
        fecha = str(fecha).strip()

    nombre_no_evacuar = "Reparto_" + fecha + "_No_Evacuar"
    nombre_evacuar = "Reparto_" + fecha + "_Evacuar"

    tiendas_no_evacuar = obtener_tiendas_unicas(registros_subpedido_generado)
    tiendas_evacuar = obtener_tiendas_unicas(registros_pedido_generado)

    conjunto_no_evacuar = set(tiendas_no_evacuar)
    conjunto_evacuar = set(tiendas_evacuar)

    # Las tablas finales ya deben ser disjuntas. No se oculta un error del
    # calculo eliminando silenciosamente tiendas durante la exportacion.
    solape = conjunto_no_evacuar.intersection(conjunto_evacuar)
    if solape:
        raise ValueError(
            "ERROR CRITICO: existen tiendas repetidas entre SUBPEDIDO "
            "(No_Evacuar) y PEDIDO COMPLETO (Evacuar): "
            + ", ".join(sorted(solape))
        )

    lineas = []

    # Primer bloque: las tiendas seleccionadas en el subpedido NO se evacuan.
    for tienda in tiendas_no_evacuar:
        lineas.append(
            _crear_linea(codigo_no_evacuar, nombre_no_evacuar, tienda)
        )

    # Segundo bloque: las tiendas del pedido completo menos el subpedido SI se
    # evacuan.
    for tienda in tiendas_evacuar:
        lineas.append(_crear_linea(codigo_evacuar, nombre_evacuar, tienda))

    return {
        "lineas": lineas,
        "tiendas_no_evacuar": tiendas_no_evacuar,
        "tiendas_evacuar": tiendas_evacuar,
        "nombre_no_evacuar": nombre_no_evacuar,
        "nombre_evacuar": nombre_evacuar,
        "fecha": fecha,
        "solape": [],
        "codigo_no_evacuar": codigo_no_evacuar,
        "codigo_evacuar": codigo_evacuar,
        "origen_no_evacuar": "SUBPEDIDO",
        "origen_evacuar": "PEDIDO COMPLETO MENOS SUBPEDIDO",
        # Alias de compatibilidad para codigo que leyera claves antiguas.
        "tiendas_subpedido": tiendas_no_evacuar,
        "tiendas_pedido_origen": tiendas_evacuar,
        "tiendas_pedido_completo": tiendas_evacuar,
        "nombre_subpedido": nombre_no_evacuar,
        "nombre_pedido": nombre_evacuar,
    }


def exportar_grtdaswp_adelanto(
    codigo=None,
    registros_subpedido_generado=None,
    registros_pedido_generado=None,
    carpeta_destino=None,
    fecha=None,
    codigo_no_evacuar=None,
    codigo_evacuar=None,
):
    """Genera de forma atomica el fichero GRTDASWP.txt."""
    if carpeta_destino is None:
        raise ValueError("No se ha indicado la carpeta de destino de GRTDASWP.")

    carpeta_destino = Path(carpeta_destino)
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    resultado = construir_lineas_grtdaswp(
        codigo=codigo,
        codigo_no_evacuar=codigo_no_evacuar,
        codigo_evacuar=codigo_evacuar,
        registros_subpedido_generado=registros_subpedido_generado,
        registros_pedido_generado=registros_pedido_generado,
        fecha=fecha,
    )

    ruta = carpeta_destino / NOMBRE_FICHERO
    ruta_temporal = carpeta_destino / (NOMBRE_FICHERO + ".tmp")

    # Los campos son ASCII; cp1252 conserva compatibilidad con ficheros legacy
    # de Windows y produce exactamente los mismos bytes para estos valores.
    with open(ruta_temporal, "w", encoding="cp1252", newline="") as archivo:
        for columnas in resultado["lineas"]:
            archivo.write("\t".join(str(valor) for valor in columnas) + "\r\n")

    ruta_temporal.replace(ruta)

    resultado["ruta"] = ruta
    resultado["total_lineas"] = len(resultado["lineas"])
    return resultado
