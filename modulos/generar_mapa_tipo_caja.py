from pathlib import Path
from datetime import datetime

PIL_DISPONIBLE = True
ERROR_PIL = None

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception as error:
    PIL_DISPONIBLE = False
    ERROR_PIL = error


#---------------------------------------------------------
# Configuracion visual
#---------------------------------------------------------
COLORES_TIPO_CAJA = {
    "4_Nueva_40": (222, 47, 43),
    "3_Usada_40": (65, 130, 230),
    "2_Reutilizada_30": (37, 177, 75),
    "1_Nueva_30": (255, 213, 50),
}

ORDEN_TIPO_CAJA = [
    "4_Nueva_40",
    "3_Usada_40",
    "2_Reutilizada_30",
    "1_Nueva_30",
]

ORDEN_RESUMEN = [
    "1_Nueva_30",
    "2_Reutilizada_30",
    "3_Usada_40",
    "4_Nueva_40",
]

# A4 horizontal a 300 ppp. Preparado para imprimir.
A4_HORIZONTAL_300 = (3508, 2480)
MARGEN = 105

# Coordenadas calibradas sobre datos_iniciales/Layout_Carruseles_TipoCaja.png
# Formato: destino_inicio, destino_fin, x_inicio, y_inicio, x_fin, y_fin
COORDENADAS_RECORRIDO = {
    1: [
        (1, 44, 900, 178, 1064, 178),
        (45, 172, 1065, 82, 388, 82),
        (173, 214, 150, 82, 92, 82),
        (215, 340, 84, 172, 575, 172),
    ],
    2: [
        (1, 44, 884, 466, 1069, 466),
        (45, 172, 1055, 370, 373, 370),
        (173, 214, 150, 370, 84, 370),
        (215, 340, 83, 466, 648, 466),
    ],
}


#---------------------------------------------------------
# Fuentes
#---------------------------------------------------------
def cargar_fuente(tamano, negrita=False):

    if not PIL_DISPONIBLE:
        return None

    rutas = []

    if negrita:
        rutas = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        rutas = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            pass

    return ImageFont.load_default()


#---------------------------------------------------------
# Conversion registros SQLite -> diccionarios
#---------------------------------------------------------
def normalizar_registros(registros):

    salida = []

    for registro in registros:

        if isinstance(registro, dict):
            salida.append(registro)
            continue

        salida.append({
            "Clasificador": registro[0],
            "Lado": registro[1],
            "Zona": registro[2],
            "Tramo": registro[3],
            "Bloque": registro[4],
            "Destino": registro[5],
            "Tienda": registro[6],
            "Aparte": registro[7],
            "Lotes": registro[8],
            "TipoCaja": registro[9],
            "Prioridad": registro[10] if len(registro) > 10 else None,
            "PrioridadOrden": registro[11] if len(registro) > 11 else None,
        })

    return salida


#---------------------------------------------------------
# Utilidades de calculo
#---------------------------------------------------------
def posicion_destino(destino, segmento):

    d1, d2, x1, y1, x2, y2 = segmento

    if d2 == d1:
        return (x1 + x2) // 2, (y1 + y2) // 2

    proporcion = (destino - d1) / (d2 - d1)

    x = x1 + proporcion * (x2 - x1)
    y = y1 + proporcion * (y2 - y1)

    return float(x), float(y)


def escalar_punto(x, y, offset_x, offset_y, escala):
    return int(round(offset_x + x * escala)), int(round(offset_y + y * escala))


def separar_intervalo_fisico(inicio, fin, clasificador):

    piezas = []

    for segmento in COORDENADAS_RECORRIDO[int(clasificador)]:

        destino_inicio = segmento[0]
        destino_fin = segmento[1]

        inicio_pieza = max(int(inicio), int(destino_inicio))
        fin_pieza = min(int(fin), int(destino_fin))

        if inicio_pieza <= fin_pieza:
            piezas.append((inicio_pieza, fin_pieza, segmento))

    return piezas


def obtener_intervalos(destinos):

    valores = sorted(set([int(destino) for destino in destinos]))

    if len(valores) == 0:
        return []

    intervalos = []
    inicio = valores[0]
    anterior = valores[0]

    for valor in valores[1:]:

        if valor == anterior + 1:
            anterior = valor
        else:
            intervalos.append((inicio, anterior))
            inicio = valor
            anterior = valor

    intervalos.append((inicio, anterior))

    return intervalos


def construir_piezas_fisicas(registros):

    piezas = []
    clasificadores = sorted(set([int(r["Clasificador"]) for r in registros]))

    for clasificador in clasificadores:

        for tipo_caja in ORDEN_TIPO_CAJA:

            destinos = []

            for registro in registros:
                if int(registro["Clasificador"]) == clasificador and str(registro["TipoCaja"]).strip() == tipo_caja:
                    destinos.append(int(registro["Destino"]))

            for inicio, fin in obtener_intervalos(destinos):
                for inicio_pieza, fin_pieza, segmento in separar_intervalo_fisico(inicio, fin, clasificador):
                    piezas.append((clasificador, tipo_caja, inicio_pieza, fin_pieza, segmento))

    return piezas


def resumen_por_tipo(registros, piezas):

    resumen = []
    clasificadores = sorted(set([int(r["Clasificador"]) for r in registros]))

    for clasificador in clasificadores:

        for tipo_caja in ORDEN_RESUMEN:

            datos = []

            for registro in registros:
                if int(registro["Clasificador"]) == clasificador and str(registro["TipoCaja"]).strip() == tipo_caja:
                    datos.append(registro)

            if len(datos) == 0:
                continue

            destinos = sorted(set([int(r["Destino"]) for r in datos]))
            lotes = 0

            for registro in datos:
                try:
                    lotes += float(registro["Lotes"])
                except Exception:
                    pass

            piezas_tipo = []

            for cla, tipo, inicio, fin, segmento in piezas:
                if cla == clasificador and tipo == tipo_caja:
                    piezas_tipo.append(str(inicio) + "-" + str(fin))

            resumen.append([
                clasificador,
                tipo_caja,
                "; ".join(piezas_tipo),
                len(destinos),
                lotes,
            ])

    return resumen


#---------------------------------------------------------
# Utilidades de dibujo
#---------------------------------------------------------
def pintar_texto(draw, x, y, texto, fuente, color=(0, 0, 0), anchor=None):

    if anchor is None:
        draw.text((x, y), str(texto), fill=color, font=fuente)
    else:
        draw.text((x, y), str(texto), fill=color, font=fuente, anchor=anchor)


def texto_centrado_en_caja(draw, caja, texto, fuente, color=(0, 0, 0)):

    x1, y1, x2, y2 = caja
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    draw.text((cx, cy), str(texto), fill=color, font=fuente, anchor="mm")


def rectangulo_redondeado(draw, caja, radio, relleno, borde=None, ancho_borde=1):

    try:
        draw.rounded_rectangle(caja, radius=radio, fill=relleno, outline=borde, width=ancho_borde)
    except Exception:
        draw.rectangle(caja, fill=relleno, outline=borde)


def caja_etiqueta(draw, texto, x, y, fuente, escala):

    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho = bbox[2] - bbox[0]
    alto = bbox[3] - bbox[1]
    pad_x = int(12 * escala)
    pad_y = int(7 * escala)

    return [
        int(x - ancho / 2 - pad_x),
        int(y - alto / 2 - pad_y),
        int(x + ancho / 2 + pad_x),
        int(y + alto / 2 + pad_y),
    ]


def cajas_solapan(a, b, margen=8):

    return not (
        a[2] + margen < b[0] or
        a[0] - margen > b[2] or
        a[3] + margen < b[1] or
        a[1] - margen > b[3]
    )


def ajustar_etiquetas_sin_solape(draw, etiquetas, fuente, escala, limite_superior, limite_inferior):

    colocadas = []
    resultado = []
    salto = int(30 * escala)

    for texto, x, y, color, direccion in etiquetas:

        y_actual = y
        caja = caja_etiqueta(draw, texto, x, y_actual, fuente, escala)
        intentos = 0

        while any(cajas_solapan(caja, anterior) for anterior in colocadas) and intentos < 12:
            y_actual += direccion * salto
            caja = caja_etiqueta(draw, texto, x, y_actual, fuente, escala)

            if caja[1] < limite_superior or caja[3] > limite_inferior:
                direccion = direccion * -1
                y_actual = y + direccion * salto
                caja = caja_etiqueta(draw, texto, x, y_actual, fuente, escala)

            intentos += 1

        colocadas.append(caja)
        resultado.append((texto, x, y_actual, color))

    return resultado


def etiqueta_tramo(draw, texto, x, y, fuente, escala, color_tipo):

    caja = caja_etiqueta(draw, texto, x, y, fuente, escala)

    rectangulo_redondeado(
        draw,
        caja,
        int(8 * escala),
        (255, 255, 255),
        (25, 25, 25),
        max(1, int(1.2 * escala))
    )

    # Raya pequena del color dentro de la etiqueta para asociarla al tramo.
    draw.rectangle(
        [caja[0] + int(7 * escala), caja[1] + int(7 * escala), caja[0] + int(22 * escala), caja[3] - int(7 * escala)],
        fill=color_tipo,
        outline=(25, 25, 25)
    )
    draw.text((x + int(8 * escala), y), texto, fill=(0, 0, 0), font=fuente, anchor="mm")


def partir_texto(texto, fuente, ancho_max, draw):

    palabras = str(texto).split(" ")
    lineas = []
    actual = ""

    for palabra in palabras:
        prueba = palabra if actual == "" else actual + " " + palabra
        caja = draw.textbbox((0, 0), prueba, font=fuente)
        if caja[2] - caja[0] <= ancho_max:
            actual = prueba
        else:
            if actual != "":
                lineas.append(actual)
            actual = palabra

    if actual != "":
        lineas.append(actual)

    return lineas


#---------------------------------------------------------
# Crear imagen A4 horizontal preparada para PDF
#---------------------------------------------------------
def crear_lienzo_a4(registros, ruta_layout, fecha_hora_pdf=""):

    if not PIL_DISPONIBLE:
        raise Exception(
            "Falta instalar Pillow. Ejecuta: python -m pip install pillow"
        )

    registros = normalizar_registros(registros)

    if len(registros) == 0:
        raise Exception("No hay registros en REPARTO_CLASIFICADOR para generar el mapa.")

    if not Path(ruta_layout).exists():
        raise Exception("No existe el layout del mapa: " + str(ruta_layout))

    page_w, page_h = A4_HORIZONTAL_300
    imagen = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(imagen)

    fuente_titulo = cargar_fuente(48, True)
    fuente_subtitulo = cargar_fuente(25, False)
    fuente = cargar_fuente(25, False)
    fuente_negrita = cargar_fuente(25, True)
    fuente_tabla = cargar_fuente(22, False)
    fuente_tabla_negrita = cargar_fuente(22, True)
    fuente_etiqueta = cargar_fuente(24, True)
    fuente_nota = cargar_fuente(18, False)

    # Cabecera
    draw.rectangle([0, 0, page_w, 105], fill=(245, 247, 250))
    draw.rectangle([0, 103, page_w, 105], fill=(185, 192, 204))
    pintar_texto(draw, MARGEN, 28, "MAPA TIPO CAJA POR DESTINO", fuente_titulo, (20, 36, 62))

    if fecha_hora_pdf != "":
        pintar_texto(draw, page_w - MARGEN, 42, "Fecha y hora: " + str(fecha_hora_pdf), fuente_subtitulo, (55, 55, 55), anchor="ra")

    layout = Image.open(ruta_layout).convert("RGB")
    layout_w, layout_h = layout.size

    mapa_x = MARGEN
    mapa_y = 135
    mapa_w = page_w - (MARGEN * 2)
    mapa_h_max = 1510
    escala = min(mapa_w / layout_w, mapa_h_max / layout_h)
    mapa_h = int(layout_h * escala)
    mapa_w_real = int(layout_w * escala)

    if mapa_w_real < mapa_w:
        mapa_x = MARGEN + int((mapa_w - mapa_w_real) / 2)

    layout_redimensionado = layout.resize((mapa_w_real, mapa_h), Image.Resampling.LANCZOS)
    imagen.paste(layout_redimensionado, (mapa_x, mapa_y))

    piezas = construir_piezas_fisicas(registros)
    ancho_linea = max(20, int(15 * escala))
    radio_punto = max(7, int(5 * escala))

    # Primero pintar todos los tramos.
    posiciones_etiqueta = []

    for clasificador, tipo_caja, inicio, fin, segmento in piezas:

        x1, y1 = posicion_destino(inicio, segmento)
        x2, y2 = posicion_destino(fin, segmento)

        sx1, sy1 = escalar_punto(x1, y1, mapa_x, mapa_y, escala)
        sx2, sy2 = escalar_punto(x2, y2, mapa_x, mapa_y, escala)

        color = COLORES_TIPO_CAJA.get(tipo_caja, (0, 0, 0))

        draw.line([sx1, sy1, sx2, sy2], fill=color, width=ancho_linea)
        draw.ellipse([sx1 - radio_punto, sy1 - radio_punto, sx1 + radio_punto, sy1 + radio_punto], fill=color, outline=(0, 0, 0))
        draw.ellipse([sx2 - radio_punto, sy2 - radio_punto, sx2 + radio_punto, sy2 + radio_punto], fill=color, outline=(0, 0, 0))

        mx = int(round((sx1 + sx2) / 2))
        my = int(round((sy1 + sy2) / 2))

        # Alternar la etiqueta arriba/abajo segun la linea fisica para que no tape tanto el plano.
        y_original = segmento[3]
        if y_original in (82, 370):
            ey = my - int(34 * escala)
            direccion = -1
        else:
            ey = my + int(34 * escala)
            direccion = 1

        etiqueta = str(inicio) + "-" + str(fin)
        posiciones_etiqueta.append((etiqueta, mx, ey, color, direccion))

    posiciones_etiqueta = ajustar_etiquetas_sin_solape(
        draw,
        posiciones_etiqueta,
        fuente_etiqueta,
        escala,
        mapa_y + int(5 * escala),
        mapa_y + mapa_h - int(5 * escala)
    )

    # Despues pintar etiquetas por encima de los colores.
    for etiqueta, x, y, color in posiciones_etiqueta:
        etiqueta_tramo(draw, etiqueta, x, y, fuente_etiqueta, escala, color)

    # Leyenda y resumen inferior
    y_info = mapa_y + mapa_h + 50

    # Leyenda color
    rectangulo_redondeado(draw, [MARGEN, y_info, page_w - MARGEN, y_info + 115], 14, (248, 250, 253), (190, 198, 210), 2)
    pintar_texto(draw, MARGEN + 25, y_info + 18, "Leyenda TipoCaja", fuente_negrita, (20, 36, 62))

    leyenda = [
        ("4_Nueva_40", COLORES_TIPO_CAJA["4_Nueva_40"]),
        ("3_Usada_40", COLORES_TIPO_CAJA["3_Usada_40"]),
        ("2_Reutilizada_30", COLORES_TIPO_CAJA["2_Reutilizada_30"]),
        ("1_Nueva_30", COLORES_TIPO_CAJA["1_Nueva_30"]),
    ]

    x_leyenda = MARGEN + 25
    for tipo_caja, color in leyenda:
        draw.rectangle([x_leyenda, y_info + 62, x_leyenda + 45, y_info + 92], fill=color, outline=(0, 0, 0))
        pintar_texto(draw, x_leyenda + 60, y_info + 61, tipo_caja, fuente)
        x_leyenda += 750

    # Tabla resumen
    resumen = resumen_por_tipo(registros, piezas)
    tabla_x = MARGEN
    tabla_y = y_info + 145
    tabla_w = page_w - (MARGEN * 2)
    alto_cab = 48
    alto_fila = 46

    col_cla = 145
    col_tipo = 430
    col_destinos = 1780
    col_cant = 280
    col_lotes = tabla_w - col_cla - col_tipo - col_destinos - col_cant
    columnas = [col_cla, col_tipo, col_destinos, col_cant, col_lotes]
    cabeceras = ["CLA", "TipoCaja", "Rangos pintados en el mapa", "Destinos", "Lotes"]

    draw.rectangle([tabla_x, tabla_y, tabla_x + tabla_w, tabla_y + alto_cab], fill=(25, 42, 70))
    x = tabla_x
    for ancho, cabecera in zip(columnas, cabeceras):
        pintar_texto(draw, x + 18, tabla_y + 13, cabecera, fuente_tabla_negrita, (255, 255, 255))
        x += ancho

    y = tabla_y + alto_cab

    for indice, fila in enumerate(resumen):

        clasificador, tipo_caja, tramos, destinos, lotes = fila
        fondo = (247, 249, 252) if indice % 2 else (255, 255, 255)
        color = COLORES_TIPO_CAJA.get(tipo_caja, (0, 0, 0))

        draw.rectangle([tabla_x, y, tabla_x + tabla_w, y + alto_fila], fill=fondo, outline=(215, 220, 228))
        draw.rectangle([tabla_x + 18, y + 10, tabla_x + 52, y + 36], fill=color, outline=(0, 0, 0))

        x = tabla_x
        valores = [
            str(clasificador),
            str(tipo_caja),
            str(tramos),
            str(destinos),
            f"{int(round(lotes)):,}".replace(",", "."),
        ]

        # CLA con color al lado
        pintar_texto(draw, x + 65, y + 10, valores[0], fuente_tabla)
        x += columnas[0]
        pintar_texto(draw, x + 18, y + 10, valores[1], fuente_tabla)
        x += columnas[1]

        # Rangos: si son largos, se recortan lo justo para que siga siendo legible en A4.
        rangos = valores[2]
        if len(rangos) > 105:
            rangos = rangos[:102] + "..."
        pintar_texto(draw, x + 18, y + 10, rangos, fuente_tabla)
        x += columnas[2]
        texto_centrado_en_caja(draw, [x, y, x + columnas[3], y + alto_fila], valores[3], fuente_tabla)
        x += columnas[3]
        pintar_texto(draw, x + columnas[4] - 18, y + 10, valores[4], fuente_tabla, anchor="ra")

        y += alto_fila

    nota = "PDF A4 horizontal. Los numeros dentro del plano son rangos reales de destino pintados por TipoCaja."
    pintar_texto(draw, MARGEN, page_h - 45, nota, fuente_nota, (70, 70, 70))

    return imagen


#---------------------------------------------------------
# Crear solo PDF A4 del mapa
#---------------------------------------------------------
def crear_mapa_tipo_caja_pdf(carpeta_salida, registros, fecha_hora_archivo=None, fecha_hora_pdf=None):

    if fecha_hora_archivo is None:
        fecha_hora_archivo = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fecha_hora_pdf is None:
        fecha_hora_pdf = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    carpeta_salida = Path(carpeta_salida)

    ruta_layout = (
        Path(__file__).resolve().parent.parent
        / "datos_iniciales"
        / "Layout_Carruseles_TipoCaja.png"
    )

    ruta_pdf = carpeta_salida / ("Mapa_TipoCaja_Carruseles_" + fecha_hora_archivo + ".pdf")

    imagen = crear_lienzo_a4(
        registros,
        ruta_layout,
        fecha_hora_pdf
    )

    imagen.save(ruta_pdf, "PDF", resolution=300.0)

    return [ruta_pdf]
