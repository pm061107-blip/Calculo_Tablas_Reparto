from pathlib import Path
from datetime import datetime
import csv
import tkinter as tk
from tkinter import filedialog

from bd.basedatos import BaseDatos
from modulos.gestor_grutiep import validar_y_avisar_grutiep
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo

try:
    from modulos.generar_mapa_tipo_caja import crear_mapa_tipo_caja_pdf
except Exception:
    crear_mapa_tipo_caja_pdf = None


#---------------------------------------------------------
# Seleccionar carpeta donde guardar los archivos
#---------------------------------------------------------
def seleccionar_carpeta_salida(parent=None):

    ventana_temporal = None
    padre_dialogo = parent

    if padre_dialogo is None:
        ventana_temporal = tk.Tk()
        ventana_temporal.withdraw()
        ventana_temporal.attributes("-topmost", True)
        padre_dialogo = ventana_temporal

    try:
        carpeta = filedialog.askdirectory(
            title="Selecciona la carpeta donde guardar los CSV y PDF",
            parent=padre_dialogo,
        )
    finally:
        if ventana_temporal is not None:
            ventana_temporal.destroy()

    if carpeta == "":
        return None

    return Path(carpeta)


#---------------------------------------------------------
# Obtener reparto completo
#---------------------------------------------------------
def obtener_reparto_completo(bd):

    return bd.consultar("""
        SELECT
            Clasificador,
            Lado,
            Zona,
            Tramo,
            Bloque,
            Destino,
            Tienda,
            Aparte,
            Lotes,
            TipoCaja,
            Prioridad,
            PrioridadOrden
        FROM REPARTO_CLASIFICADOR
        ORDER BY
            Clasificador,
            Lado,
            Zona,
            Tramo,
            Bloque,
            Destino
    """)


#---------------------------------------------------------
# Obtener registros de un clasificador para CSV
#---------------------------------------------------------
def obtener_registros_clasificador(bd, clasificador):

    return bd.consultar(f"""
        SELECT
            Destino,
            Tienda,
            Aparte
        FROM REPARTO_CLASIFICADOR
        WHERE Clasificador = {clasificador}
        ORDER BY Destino
    """)


#---------------------------------------------------------
# Escribir CSV de un clasificador
#---------------------------------------------------------
def escribir_csv_clasificador(ruta_archivo, registros):

    with open(ruta_archivo, "w", newline="", encoding="utf-8-sig") as archivo:

        escritor = csv.writer(
            archivo,
            delimiter=";",
            lineterminator="\r\n"
        )

        escritor.writerow([
            "DESTINO",
            "TIENDA",
            "SECCION",
            "APARTE"
        ])

        for destino, tienda, aparte in registros:

            if aparte is None:
                aparte = 0

            escritor.writerow([destino, tienda, 1, aparte])
            escritor.writerow([destino, tienda, 2, aparte])


#---------------------------------------------------------
# Color por lado para PDF
#---------------------------------------------------------
def color_lado(lado):

    colores = {
        1: (0.86, 0.93, 1.00),   # azul claro
        2: (0.88, 0.97, 0.89),   # verde claro
        3: (1.00, 0.93, 0.84),   # naranja claro
        4: (0.94, 0.90, 1.00),   # violeta claro
    }

    return colores.get(lado, (1, 1, 1))


#---------------------------------------------------------
# Escapar texto para PDF
#---------------------------------------------------------
def texto_pdf(texto):

    texto = str(texto)

    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "ñ": "n", "Ñ": "N",
        "€": "EUR"
    }

    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)

    texto = texto.replace("\\", "\\\\")
    texto = texto.replace("(", "\\(")
    texto = texto.replace(")", "\\)")

    return texto


#---------------------------------------------------------
# Recortar texto para que quepa en una celda
#---------------------------------------------------------
def recortar_texto(texto, max_caracteres):

    texto = str(texto)

    if len(texto) <= max_caracteres:
        return texto

    if max_caracteres <= 3:
        return texto[:max_caracteres]

    return texto[:max_caracteres - 3] + "..."


#---------------------------------------------------------
# Generador PDF sencillo con tablas coloreadas
#---------------------------------------------------------
class PDFTabla:

    def __init__(self, ruta_pdf, titulo, subtitulo):

        self.ruta_pdf = ruta_pdf
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.ancho = 842
        self.alto = 595
        self.margen = 36
        self.paginas = []
        self.comandos = []
        self.y = 0
        self.nueva_pagina()

    def nueva_pagina(self):

        if len(getattr(self, "comandos", [])) > 0:
            self.paginas.append("\n".join(self.comandos))

        self.comandos = []
        self.y = self.alto - self.margen

        self.texto(36, self.y, self.titulo, 15, "F2", (0.08, 0.16, 0.30))
        self.y -= 18
        self.texto(36, self.y, self.subtitulo, 9, "F1", (0.20, 0.20, 0.20))
        self.y -= 22

    def finalizar(self):

        self.paginas.append("\n".join(self.comandos))
        self.escribir_pdf()

    def color(self, color, relleno=True):

        r, g, b = color
        operador = "rg" if relleno else "RG"
        self.comandos.append(f"{r:.3f} {g:.3f} {b:.3f} {operador}")

    def rectangulo(self, x, y, w, h, relleno=None, borde=(0.75, 0.75, 0.75)):

        if relleno is not None:
            self.color(relleno, True)
            self.comandos.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

        self.color(borde, False)
        self.comandos.append("0.4 w")
        self.comandos.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def texto(self, x, y, texto, tamano=8, fuente="F1", color=(0, 0, 0)):

        self.color(color, True)
        self.comandos.append("BT")
        self.comandos.append(f"/{fuente} {tamano} Tf")
        self.comandos.append(f"{x:.2f} {y:.2f} Td")
        self.comandos.append("(" + texto_pdf(texto) + ") Tj")
        self.comandos.append("ET")

    def tabla(self, columnas, filas, anchuras, color_fila=None):

        x0 = self.margen
        alto_cabecera = 22
        alto_fila = 20
        ancho_total = sum(anchuras)

        if self.y - alto_cabecera < self.margen:
            self.nueva_pagina()

        self.rectangulo(x0, self.y - alto_cabecera, ancho_total, alto_cabecera, relleno=(0.12, 0.20, 0.34), borde=(0.12, 0.20, 0.34))

        x = x0
        for i, columna in enumerate(columnas):
            self.texto(x + 4, self.y - 14, columna, 8, "F2", (1, 1, 1))
            x += anchuras[i]

        self.y -= alto_cabecera

        for fila in filas:

            if self.y - alto_fila < self.margen:
                self.nueva_pagina()
                self.rectangulo(x0, self.y - alto_cabecera, ancho_total, alto_cabecera, relleno=(0.12, 0.20, 0.34), borde=(0.12, 0.20, 0.34))
                x = x0
                for i, columna in enumerate(columnas):
                    self.texto(x + 4, self.y - 14, columna, 8, "F2", (1, 1, 1))
                    x += anchuras[i]
                self.y -= alto_cabecera

            relleno = (1, 1, 1)
            if color_fila is not None:
                relleno = color_fila(fila)

            self.rectangulo(x0, self.y - alto_fila, ancho_total, alto_fila, relleno=relleno, borde=(0.80, 0.80, 0.80))

            x = x0
            for i, valor in enumerate(fila):
                max_chars = max(4, int(anchuras[i] / 5.2))
                self.texto(x + 4, self.y - 13, recortar_texto(valor, max_chars), 7, "F1", (0.05, 0.05, 0.05))
                x += anchuras[i]

            self.y -= alto_fila

    def escribir_pdf(self):

        objetos = []
        paginas_ids = []

        objetos.append("<< /Type /Catalog /Pages 2 0 R >>")
        objetos.append(None)
        objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objetos.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        siguiente_id = 5

        for pagina in self.paginas:

            page_id = siguiente_id
            content_id = siguiente_id + 1
            siguiente_id += 2

            paginas_ids.append(page_id)

            objetos.append(
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                "/Contents " + str(content_id) + " 0 R >>"
            )

            objetos.append(
                "<< /Length " + str(len(pagina.encode("latin-1", errors="replace"))) + " >>\n"
                "stream\n" + pagina + "\nendstream"
            )

        kids = " ".join([str(pid) + " 0 R" for pid in paginas_ids])
        objetos[1] = "<< /Type /Pages /Kids [" + kids + "] /Count " + str(len(paginas_ids)) + " >>"

        salida = bytearray()
        salida.extend(b"%PDF-1.4\n")
        offsets = [0]

        for i, objeto in enumerate(objetos, start=1):
            offsets.append(len(salida))
            salida.extend((str(i) + " 0 obj\n").encode("latin-1"))
            salida.extend(objeto.encode("latin-1", errors="replace"))
            salida.extend(b"\nendobj\n")

        xref_pos = len(salida)
        salida.extend(("xref\n0 " + str(len(objetos) + 1) + "\n").encode("latin-1"))
        salida.extend(b"0000000000 65535 f \n")

        for offset in offsets[1:]:
            salida.extend((str(offset).zfill(10) + " 00000 n \n").encode("latin-1"))

        salida.extend((
            "trailer\n<< /Size " + str(len(objetos) + 1) + " /Root 1 0 R >>\n"
            "startxref\n" + str(xref_pos) + "\n%%EOF\n"
        ).encode("latin-1"))

        with open(self.ruta_pdf, "wb") as archivo:
            archivo.write(salida)


#---------------------------------------------------------
# Generar rangos por TipoCaja y lado
#---------------------------------------------------------
def generar_rangos_tipo_caja(registros):

    registros_ordenados = sorted(
        registros,
        key=lambda r: (r[0], r[1], r[5])
    )

    rangos = []

    for registro in registros_ordenados:

        clasificador = registro[0]
        lado = registro[1]
        zona = registro[2]
        destino = registro[5]
        lotes = registro[8]
        tipo_caja = registro[9]

        if len(rangos) == 0:
            rangos.append([clasificador, lado, zona, tipo_caja, destino, destino, 1, lotes])
        else:
            ultimo = rangos[-1]

            if (
                ultimo[0] == clasificador and
                ultimo[1] == lado and
                ultimo[2] == zona and
                ultimo[3] == tipo_caja and
                destino == ultimo[5] + 1
            ):
                ultimo[5] = destino
                ultimo[6] += 1
                ultimo[7] += lotes
            else:
                rangos.append([clasificador, lado, zona, tipo_caja, destino, destino, 1, lotes])

    return rangos


#---------------------------------------------------------
# Crear PDF resumen por TipoCaja
#---------------------------------------------------------
def crear_pdf_resumen_tipo_caja(ruta_pdf, registros, fecha_hora):

    filas = []

    for rango in generar_rangos_tipo_caja(registros):
        filas.append([
            rango[0],
            rango[1],
            rango[2],
            rango[3],
            rango[4],
            rango[5],
            rango[6],
            round(rango[7], 2)
        ])

    pdf = PDFTabla(
        ruta_pdf,
        "Resumen de reparto por TipoCaja",
        "Fecha y hora: " + fecha_hora + "  |  Colores por lado"
    )

    pdf.tabla(
        ["CLA", "Lado", "Zona", "TipoCaja", "Desde", "Hasta", "Dest.", "Lotes"],
        filas,
        [42, 45, 82, 145, 55, 55, 50, 75],
        color_fila=lambda fila: color_lado(int(fila[1]))
    )

    pdf.finalizar()


#---------------------------------------------------------
# Crear PDF resumen de lotes por lados
#---------------------------------------------------------
def crear_pdf_resumen_lados(ruta_pdf, registros, fecha_hora):

    resumen = {}
    total_cla = {}

    for registro in registros:

        clasificador = registro[0]
        lado = registro[1]
        zona = registro[2]
        lotes = registro[8]

        clave = (clasificador, lado, zona)

        if clave not in resumen:
            resumen[clave] = {"Tiendas": 0, "Lotes": 0}

        resumen[clave]["Tiendas"] += 1
        resumen[clave]["Lotes"] += lotes

        if clasificador not in total_cla:
            total_cla[clasificador] = {"Tiendas": 0, "Lotes": 0}

        total_cla[clasificador]["Tiendas"] += 1
        total_cla[clasificador]["Lotes"] += lotes

    filas = []

    for clave, datos in sorted(resumen.items()):
        clasificador, lado, zona = clave
        filas.append([
            clasificador,
            lado,
            zona,
            datos["Tiendas"],
            round(datos["Lotes"], 2)
        ])

    filas.append(["", "", "", "", ""])

    for clasificador in sorted(total_cla.keys()):
        filas.append([
            clasificador,
            "TOTAL",
            "Clasificador",
            total_cla[clasificador]["Tiendas"],
            round(total_cla[clasificador]["Lotes"], 2)
        ])

    pdf = PDFTabla(
        ruta_pdf,
        "Resumen de lotes por lados",
        "Fecha y hora: " + fecha_hora + "  |  Colores por lado"
    )

    def color_resumen(fila):
        if fila[1] == "TOTAL":
            return (0.90, 0.90, 0.90)
        if fila[1] == "":
            return (1, 1, 1)
        return color_lado(int(fila[1]))

    pdf.tabla(
        ["CLA", "Lado", "Zona", "Tiendas", "Lotes"],
        filas,
        [55, 65, 120, 80, 100],
        color_fila=color_resumen
    )

    pdf.finalizar()



#---------------------------------------------------------
# Color por clasificador para PDF
#---------------------------------------------------------
def color_clasificador(clasificador):

    colores = {
        1: (0.84, 0.90, 1.00),
        2: (0.86, 0.96, 0.88)
    }

    return colores.get(clasificador, (0.92, 0.92, 0.92))


#---------------------------------------------------------
# Normalizar pais para PDF
#---------------------------------------------------------
def normalizar_pais_pdf(pais):

    if pais is None:
        return ""

    return str(pais).strip().upper()


#---------------------------------------------------------
# Mostrar pais en PDF
#---------------------------------------------------------
def mostrar_pais_pdf(pais):

    pais = normalizar_pais_pdf(pais)

    if pais == "":
        return "(SIN PAIS)"

    return pais


#---------------------------------------------------------
# Obtener resumen por paises fijos desde el reparto final
#---------------------------------------------------------
def obtener_resumen_paises_fijos(
    bd,
    clasificadores_activos,
    clave_pedido_trabajo=None,
):

    clasificadores_limpios = []

    for clasificador in clasificadores_activos:
        try:
            clasificadores_limpios.append(int(clasificador))
        except Exception:
            pass

    if len(clasificadores_limpios) == 0:
        clasificadores_limpios = [1, 2]

    lista_clasificadores = ",".join([str(c) for c in clasificadores_limpios])

    if clave_pedido_trabajo:
        # El pais se obtiene del pedido independiente que uso realmente este
        # formulario. Nunca se consulta TMP_ESTAREPP, porque puede pertenecer
        # a otra ventana abierta.
        gestor = GestorPedidosTrabajo(bd.conexion)
        mapa_paises = {
            (int(tienda), int(aparte or 0)): normalizar_pais_pdf(pais)
            for tienda, aparte, _lotes, pais, _tipo_caja
            in gestor.obtener_detalle(clave_pedido_trabajo)
        }
        reparto = bd.consultar(f"""
            SELECT
                Clasificador,
                Tienda,
                IFNULL(Aparte, 0),
                IFNULL(Lotes, 0)
            FROM REPARTO_CLASIFICADOR
            WHERE Clasificador IN ({lista_clasificadores})
            ORDER BY Clasificador, Tienda, IFNULL(Aparte, 0)
        """)
        agrupado = {}
        for clasificador, tienda, aparte, lotes in reparto:
            pais = mapa_paises.get((int(tienda), int(aparte or 0)), "")
            clave = (int(clasificador), pais)
            if clave not in agrupado:
                agrupado[clave] = [0, 0.0]
            agrupado[clave][0] += 1
            agrupado[clave][1] += float(lotes or 0)
        datos = [
            (clasificador, pais, valores[0], valores[1])
            for (clasificador, pais), valores in sorted(agrupado.items())
        ]
    else:
        # Compatibilidad para exportaciones antiguas y Calculo Adelanto.
        datos = bd.consultar(f"""
            SELECT
                r.Clasificador,
                IFNULL(t.Pais, '') AS Pais,
                COUNT(*) AS Tiendas,
                IFNULL(SUM(r.Lotes), 0) AS Lotes
            FROM REPARTO_CLASIFICADOR r
            LEFT JOIN TMP_ESTAREPP t
                ON r.Tienda = t.Tienda
                AND IFNULL(r.Aparte, 0) = IFNULL(t.Aparte, 0)
            WHERE r.Clasificador IN ({lista_clasificadores})
            GROUP BY
                r.Clasificador,
                IFNULL(t.Pais, '')
            ORDER BY
                r.Clasificador,
                IFNULL(t.Pais, '')
        """)

    resumen = {}

    for clasificador, pais, tiendas, lotes in datos:

        if clasificador not in resumen:
            resumen[clasificador] = []

        resumen[clasificador].append({
            "Pais": normalizar_pais_pdf(pais),
            "PaisMostrar": mostrar_pais_pdf(pais),
            "Tiendas": tiendas,
            "Lotes": lotes
        })

    return resumen


#---------------------------------------------------------
# Escribir cabecera de seccion en PDF
#---------------------------------------------------------
def escribir_seccion_pdf(pdf, titulo, color_fondo):

    ancho = pdf.ancho - (pdf.margen * 2)

    if pdf.y - 36 < pdf.margen:
        pdf.nueva_pagina()

    pdf.rectangulo(
        pdf.margen,
        pdf.y - 24,
        ancho,
        24,
        relleno=color_fondo,
        borde=color_fondo
    )

    pdf.texto(
        pdf.margen + 8,
        pdf.y - 16,
        titulo,
        11,
        "F2",
        (0.06, 0.10, 0.18)
    )

    pdf.y -= 32


#---------------------------------------------------------
# Crear PDF resumen de paises fijos
#---------------------------------------------------------
def crear_pdf_resumen_paises_fijos(
    ruta_pdf,
    bd,
    clasificadores_activos,
    fecha_hora,
    configuracion_paises,
    clave_pedido_trabajo=None,
):

    resumen = obtener_resumen_paises_fijos(
        bd,
        clasificadores_activos,
        clave_pedido_trabajo=clave_pedido_trabajo,
    )

    paises_cla_1 = configuracion_paises.get("PaisesCLA1", []) if configuracion_paises is not None else []
    paises_cla_2 = configuracion_paises.get("PaisesCLA2", []) if configuracion_paises is not None else []
    resto_al_otro = configuracion_paises.get("RestoAlOtro", False) if configuracion_paises is not None else False

    def preparar_filas(clasificador):

        datos_cla = resumen.get(int(clasificador), [])
        filas = []
        total_tiendas = 0
        total_lotes = 0

        for datos in datos_cla:

            tiendas = datos.get("Tiendas", 0)
            lotes = datos.get("Lotes", 0)

            filas.append({
                "Pais": datos.get("PaisMostrar", ""),
                "Tiendas": tiendas,
                "Lotes": lotes,
                "Total": False
            })

            total_tiendas += tiendas
            total_lotes += lotes

        if len(filas) == 0:
            filas.append({
                "Pais": "Sin registros",
                "Tiendas": 0,
                "Lotes": 0,
                "Total": False
            })

        filas.append({
            "Pais": "TOTAL CLA " + str(clasificador),
            "Tiendas": total_tiendas,
            "Lotes": total_lotes,
            "Total": True
        })

        return filas, total_tiendas, total_lotes

    filas_cla_1, total_tiendas_1, total_lotes_1 = preparar_filas(1)
    filas_cla_2, total_tiendas_2, total_lotes_2 = preparar_filas(2)

    texto_cla_1 = ", ".join([mostrar_pais_pdf(pais) for pais in paises_cla_1])
    texto_cla_2 = ", ".join([mostrar_pais_pdf(pais) for pais in paises_cla_2])

    if texto_cla_1 == "":
        texto_cla_1 = "-"

    if texto_cla_2 == "":
        texto_cla_2 = "-"

    modo_resto = "NO"

    if resto_al_otro:
        modo_resto = "SI"

    pdf = PDFTabla(
        ruta_pdf,
        "Resumen de paises fijos por carrusel",
        "Fecha y hora: " + fecha_hora + "  |  Vista comparativa en una pagina"
    )

    #-----------------------------------------------------
    # Utilidades internas de dibujo
    #-----------------------------------------------------
    def texto_celda(x, y, ancho, texto, tamano=7, fuente="F1", color=(0.05, 0.05, 0.05), alineacion="left"):

        texto = recortar_texto(texto, max(4, int(ancho / 4.6)))
        texto = str(texto)

        if alineacion == "right":
            x_texto = x + ancho - 5 - (len(texto) * tamano * 0.42)
        elif alineacion == "center":
            x_texto = x + (ancho / 2) - (len(texto) * tamano * 0.21)
        else:
            x_texto = x + 5

        if x_texto < x + 3:
            x_texto = x + 3

        pdf.texto(
            x_texto,
            y,
            texto,
            tamano,
            fuente,
            color
        )

    def dibujar_celda(x, y, ancho, alto, texto, relleno, borde=(0.78, 0.78, 0.78), tamano=7, fuente="F1", color=(0.05, 0.05, 0.05), alineacion="left"):

        pdf.rectangulo(
            x,
            y,
            ancho,
            alto,
            relleno=relleno,
            borde=borde
        )

        texto_celda(
            x,
            y + (alto / 2) - 2.5,
            ancho,
            texto,
            tamano,
            fuente,
            color,
            alineacion
        )

    def dibujar_tarjeta(x, y, ancho, alto, titulo, valor, relleno):

        pdf.rectangulo(
            x,
            y,
            ancho,
            alto,
            relleno=relleno,
            borde=(0.70, 0.76, 0.84)
        )

        pdf.texto(
            x + 8,
            y + alto - 13,
            titulo,
            7,
            "F2",
            (0.20, 0.24, 0.30)
        )

        pdf.texto(
            x + 8,
            y + 8,
            valor,
            11,
            "F2",
            (0.06, 0.10, 0.18)
        )

    def dibujar_panel_cla(x, y_top, ancho, alto, clasificador, filas, total_tiendas, total_lotes, texto_forzado, color_base):

        y_base = y_top - alto

        pdf.rectangulo(
            x,
            y_base,
            ancho,
            alto,
            relleno=(0.98, 0.99, 1.00),
            borde=(0.52, 0.58, 0.66)
        )

        alto_banda = 34

        pdf.rectangulo(
            x,
            y_top - alto_banda,
            ancho,
            alto_banda,
            relleno=color_base,
            borde=(0.52, 0.58, 0.66)
        )

        pdf.texto(
            x + 10,
            y_top - 15,
            "CLA " + str(clasificador),
            13,
            "F2",
            (0.06, 0.10, 0.18)
        )

        pdf.texto(
            x + 10,
            y_top - 28,
            "Tiendas: " + str(total_tiendas) + "  |  Lotes: " + str(round(total_lotes, 2)),
            8,
            "F2",
            (0.06, 0.10, 0.18)
        )

        pdf.texto(
            x + ancho - 115,
            y_top - 18,
            "Paises forzados",
            7,
            "F2",
            (0.18, 0.22, 0.28)
        )

        pdf.texto(
            x + ancho - 115,
            y_top - 30,
            recortar_texto(texto_forzado, 28),
            7,
            "F1",
            (0.18, 0.22, 0.28)
        )

        y = y_top - alto_banda - 3

        col_pais = ancho * 0.48
        col_tiendas = ancho * 0.22
        col_lotes = ancho - col_pais - col_tiendas
        alto_cabecera = 18

        dibujar_celda(x, y - alto_cabecera, col_pais, alto_cabecera, "Pais", (0.12, 0.20, 0.34), (0.12, 0.20, 0.34), 7, "F2", (1, 1, 1), "left")
        dibujar_celda(x + col_pais, y - alto_cabecera, col_tiendas, alto_cabecera, "Tiendas", (0.12, 0.20, 0.34), (0.12, 0.20, 0.34), 7, "F2", (1, 1, 1), "center")
        dibujar_celda(x + col_pais + col_tiendas, y - alto_cabecera, col_lotes, alto_cabecera, "Lotes", (0.12, 0.20, 0.34), (0.12, 0.20, 0.34), 7, "F2", (1, 1, 1), "right")

        y -= alto_cabecera

        espacio_filas = alto - alto_banda - 3 - alto_cabecera - 6
        cantidad_filas = max(len(filas), 1)
        alto_fila = espacio_filas / cantidad_filas

        if alto_fila > 18:
            alto_fila = 18

        tamano_fuente = 7

        if alto_fila < 12:
            tamano_fuente = 6

        if alto_fila < 10:
            tamano_fuente = 5

        for indice, fila in enumerate(filas):

            if fila.get("Total", False):
                relleno = (0.86, 0.88, 0.91)
                fuente = "F2"
            elif indice % 2 == 0:
                relleno = (1.00, 1.00, 1.00)
                fuente = "F1"
            else:
                relleno = (0.95, 0.97, 0.99)
                fuente = "F1"

            dibujar_celda(x, y - alto_fila, col_pais, alto_fila, fila["Pais"], relleno, (0.80, 0.82, 0.86), tamano_fuente, fuente, (0.05, 0.05, 0.05), "left")
            dibujar_celda(x + col_pais, y - alto_fila, col_tiendas, alto_fila, fila["Tiendas"], relleno, (0.80, 0.82, 0.86), tamano_fuente, fuente, (0.05, 0.05, 0.05), "center")
            dibujar_celda(x + col_pais + col_tiendas, y - alto_fila, col_lotes, alto_fila, round(fila["Lotes"], 2), relleno, (0.80, 0.82, 0.86), tamano_fuente, fuente, (0.05, 0.05, 0.05), "right")

            y -= alto_fila

    #-----------------------------------------------------
    # Encabezado superior compacto
    #-----------------------------------------------------
    ancho_total = pdf.ancho - (pdf.margen * 2)
    y_top = pdf.y

    pdf.rectangulo(
        pdf.margen,
        y_top - 54,
        ancho_total,
        54,
        relleno=(0.96, 0.98, 1.00),
        borde=(0.70, 0.76, 0.84)
    )

    pdf.texto(
        pdf.margen + 10,
        y_top - 14,
        "Vista rapida del reparto forzado por pais",
        11,
        "F2",
        (0.06, 0.10, 0.18)
    )

    pdf.texto(
        pdf.margen + 10,
        y_top - 29,
        "Resto automaticamente al otro CLA: " + modo_resto,
        8,
        "F1",
        (0.16, 0.18, 0.22)
    )

    tarjeta_ancho = 112
    tarjeta_alto = 34
    tarjeta_y = y_top - 46
    tarjeta_x = pdf.margen + ancho_total - (tarjeta_ancho * 4) - 18

    dibujar_tarjeta(tarjeta_x, tarjeta_y, tarjeta_ancho, tarjeta_alto, "CLA 1 tiendas", str(total_tiendas_1), (0.89, 0.93, 1.00))
    dibujar_tarjeta(tarjeta_x + tarjeta_ancho + 6, tarjeta_y, tarjeta_ancho, tarjeta_alto, "CLA 1 lotes", str(round(total_lotes_1, 2)), (0.89, 0.93, 1.00))
    dibujar_tarjeta(tarjeta_x + (tarjeta_ancho + 6) * 2, tarjeta_y, tarjeta_ancho, tarjeta_alto, "CLA 2 tiendas", str(total_tiendas_2), (0.90, 0.97, 0.91))
    dibujar_tarjeta(tarjeta_x + (tarjeta_ancho + 6) * 3, tarjeta_y, tarjeta_ancho, tarjeta_alto, "CLA 2 lotes", str(round(total_lotes_2, 2)), (0.90, 0.97, 0.91))

    pdf.y = y_top - 70

    separacion = 14
    ancho_panel = (ancho_total - separacion) / 2
    alto_panel = pdf.y - pdf.margen
    y_panel_top = pdf.y

    dibujar_panel_cla(
        pdf.margen,
        y_panel_top,
        ancho_panel,
        alto_panel,
        1,
        filas_cla_1,
        total_tiendas_1,
        total_lotes_1,
        texto_cla_1,
        (0.84, 0.90, 1.00)
    )

    dibujar_panel_cla(
        pdf.margen + ancho_panel + separacion,
        y_panel_top,
        ancho_panel,
        alto_panel,
        2,
        filas_cla_2,
        total_tiendas_2,
        total_lotes_2,
        texto_cla_2,
        (0.86, 0.96, 0.88)
    )

    pdf.finalizar()

#---------------------------------------------------------
# Exportar CSV y PDF de tablas de reparto
#---------------------------------------------------------
def exportar_tablas_reparto_csv(
    clasificadores_activos=None,
    configuracion_paises=None,
    parent=None,
    clave_pedido_trabajo=None,
    validar_grutiep=True,
):

    if clasificadores_activos is None:
        clasificadores_activos = [1, 2]

    clasificadores_activos = sorted({int(valor) for valor in clasificadores_activos})
    carpeta_salida = seleccionar_carpeta_salida(parent=parent)

    if carpeta_salida is None:

        print()
        print("----------------------------------------")
        print("EXPORTACION CANCELADA")
        print("No se selecciono ninguna carpeta.")
        print("----------------------------------------")

        return []

    bd = BaseDatos()

    fecha_hora_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")
    fecha_hora_pdf = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    archivos_generados = []
    tiendas_por_clasificador = {}

    try:
        for clasificador in clasificadores_activos:

            registros_csv = obtener_registros_clasificador(bd, clasificador)

            if len(registros_csv) == 0:
                continue

            nombre_archivo = f"Tabla_Cla_{clasificador}_{fecha_hora_archivo}.csv"
            ruta_archivo = carpeta_salida / nombre_archivo

            escribir_csv_clasificador(ruta_archivo, registros_csv)
            archivos_generados.append(ruta_archivo)
            tiendas_por_clasificador[clasificador] = {
                registro[1]
                for registro in registros_csv
                if len(registro) > 1 and registro[1] is not None
            }

        registros_completos = obtener_reparto_completo(bd)
        registros_completos = [
            registro for registro in registros_completos
            if int(registro[0]) in clasificadores_activos
        ]

        ruta_pdf_tipo_caja = carpeta_salida / f"Resumen_TipoCaja_{fecha_hora_archivo}.pdf"
        crear_pdf_resumen_tipo_caja(ruta_pdf_tipo_caja, registros_completos, fecha_hora_pdf)
        archivos_generados.append(ruta_pdf_tipo_caja)

        ruta_pdf_lados = carpeta_salida / f"Resumen_Lotes_Lados_{fecha_hora_archivo}.pdf"
        crear_pdf_resumen_lados(ruta_pdf_lados, registros_completos, fecha_hora_pdf)
        archivos_generados.append(ruta_pdf_lados)

        # Mapa profesional por TipoCaja sobre layout de carruseles - solo PDF A4
        if crear_mapa_tipo_caja_pdf is not None and len(registros_completos) > 0:

            try:
                archivos_mapa = crear_mapa_tipo_caja_pdf(
                    carpeta_salida,
                    registros_completos,
                    fecha_hora_archivo,
                    fecha_hora_pdf
                )

                for archivo_mapa in archivos_mapa:
                    archivos_generados.append(archivo_mapa)

            except Exception as error:
                print()
                print("AVISO: no se pudo generar el mapa TipoCaja de carruseles.")
                print(error)
                print()

        if configuracion_paises is not None and configuracion_paises.get("Activo", False):

            ruta_pdf_paises = carpeta_salida / f"Resumen_Paises_Fijos_{fecha_hora_archivo}.pdf"

            crear_pdf_resumen_paises_fijos(
                ruta_pdf_paises,
                bd,
                clasificadores_activos,
                fecha_hora_pdf,
                configuracion_paises,
                clave_pedido_trabajo=clave_pedido_trabajo,
            )

            archivos_generados.append(ruta_pdf_paises)

        # La validacion previa al calculo puede desactivar este aviso posterior
        # para evitar preguntar o avisar dos veces al operador.
        if validar_grutiep and tiendas_por_clasificador:
            try:
                validar_y_avisar_grutiep(
                    bd,
                    tiendas_por_clasificador,
                    parent=parent,
                )
            except Exception as error:
                print()
                print("AVISO: no se pudo realizar la validacion GRUTIEP.")
                print(error)
                print()

    finally:
        bd.cerrar()

    print()
    print("----------------------------------------")
    print("EXPORTACION FINALIZADA")
    print("----------------------------------------")

    for archivo in archivos_generados:
        print(archivo)

    print("----------------------------------------")

    return archivos_generados
