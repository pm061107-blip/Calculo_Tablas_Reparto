import tkinter as tk
from tkinter import simpledialog, messagebox

from modulos.ventanas_tk import activar_primer_plano_sistema


#---------------------------------------------------------
# Obtener ventana raiz y padre real
#---------------------------------------------------------
def obtener_raiz_y_padre():

    raiz_creada = False
    raiz = tk._default_root

    if raiz is None:
        raiz = tk.Tk()
        raiz.withdraw()
        raiz_creada = True

    padre = None

    # Si hay una ventana con grab activo, esa es la ventana que manda.
    # En la aplicacion suele ser el formulario de reparto.
    try:
        grab_actual = raiz.grab_current()
        if grab_actual is not None and grab_actual.winfo_exists():
            padre = grab_actual.winfo_toplevel()
    except Exception:
        padre = None

    # Si no hay grab, usamos la ventana que tenga foco.
    if padre is None:
        try:
            foco = raiz.focus_get()
            if foco is not None and foco.winfo_exists():
                padre = foco.winfo_toplevel()
        except Exception:
            padre = None

    # Ultimo recurso: raiz principal.
    if padre is None:
        padre = raiz

    return raiz, padre, raiz_creada


#---------------------------------------------------------
# Centrar ventana en pantalla
#---------------------------------------------------------
def centrar_ventana(ventana, ancho, alto):

    ventana.update_idletasks()

    try:
        ancho_pantalla = ventana.winfo_screenwidth()
        alto_pantalla = ventana.winfo_screenheight()

        if ancho > ancho_pantalla - 40:
            ancho = ancho_pantalla - 40

        if alto > alto_pantalla - 70:
            alto = alto_pantalla - 70

        x = int((ancho_pantalla - ancho) / 2)
        y = int((alto_pantalla - alto) / 2)

        if x < 0:
            x = 0

        if y < 0:
            y = 0

        ventana.geometry(str(ancho) + "x" + str(alto) + "+" + str(x) + "+" + str(y))

    except Exception:
        ventana.geometry(str(ancho) + "x" + str(alto))


#---------------------------------------------------------
# Forzar ventana al frente
#---------------------------------------------------------
def forzar_ventana_al_frente(ventana, focus_widget=None):

    def elevar():
        try:
            if not ventana.winfo_exists():
                return
            ventana.deiconify()
            ventana.lift()
            ventana.attributes("-topmost", True)
            ventana.focus_force()
            ventana.update_idletasks()
            activar_primer_plano_sistema(ventana)
        except Exception:
            pass

    elevar()

    try:
        ventana.after_idle(elevar)
        ventana.after(80, elevar)
        ventana.after(300, elevar)
    except Exception:
        pass

    if focus_widget is not None:
        def enfocar():
            elevar()
            try:
                if focus_widget.winfo_exists():
                    focus_widget.focus_force()
            except Exception:
                pass

        try:
            ventana.after_idle(enfocar)
            ventana.after(100, enfocar)
        except Exception:
            pass


#---------------------------------------------------------
# Pedir tamano de bloque mediante ventana
#---------------------------------------------------------
def pedir_tamano_bloque(valor_defecto=10):

    raiz = None
    raiz_creada = False

    try:
        raiz, padre, raiz_creada = obtener_raiz_y_padre()

        valor = simpledialog.askinteger(
            "Tamano de bloque",
            "Introduce el tamano de bloque de reparto:",
            initialvalue=valor_defecto,
            minvalue=1,
            maxvalue=999,
            parent=padre
        )

        if valor is None:
            return valor_defecto

        return valor

    except Exception:
        return valor_defecto

    finally:
        if raiz_creada and raiz is not None:
            try:
                raiz.destroy()
            except Exception:
                pass


#---------------------------------------------------------
# Texto resumen de una opcion de lado corto
#---------------------------------------------------------
def texto_opcion_lado_corto(opcion, recomendada):

    resumen = opcion.get("Resumen", {})
    lineas = []

    titulo = str(opcion["Numero"]) + ". " + opcion["Nombre"]

    if recomendada is not None and opcion["Numero"] == recomendada["Numero"]:
        titulo += "  (RECOMENDADA)"

    lineas.append(titulo)

    clasificadores = resumen.get("Clasificadores", {})

    for clasificador in sorted(clasificadores.keys()):
        datos = clasificadores[clasificador]
        lineas.append(
            "CLA " + str(clasificador) +
            "  |  Lotes: " + str(round(datos.get("Lotes", 0), 2)) +
            "  |  Tiendas: " + str(datos.get("Tiendas", 0))
        )

    lineas.append(
        "Diferencia lotes: " + str(round(resumen.get("DiferenciaLotes", 0), 2)) +
        "  |  Diferencia tiendas: " + str(resumen.get("DiferenciaTiendas", 0))
    )

    lados_cortos = resumen.get("LadosCortos", {})

    if len(lados_cortos) == 0:
        lineas.append("Lado corto: sin destinos en lado corto")
    else:
        for clave in sorted(lados_cortos.keys()):
            clasificador, lado = clave
            datos = lados_cortos[clave]
            lineas.append(
                "Lado corto: CLA " + str(clasificador) +
                " - Lado " + str(lado) +
                "  |  Tiendas: " + str(datos.get("Tiendas", 0)) +
                "  |  Lotes: " + str(round(datos.get("Lotes", 0), 2))
            )

    return "\n".join(lineas)


#---------------------------------------------------------
# Seleccionar opcion de lado corto mediante ventana
#---------------------------------------------------------
def seleccionar_opcion_lado_corto(opciones, recomendada):

    if opciones is None or len(opciones) == 0:
        return recomendada

    if recomendada is None:
        recomendada = opciones[0]

    raiz = None
    ventana = None
    raiz_creada = False
    grab_anterior = None

    try:
        raiz, padre, raiz_creada = obtener_raiz_y_padre()

        try:
            grab_anterior = raiz.grab_current()
        except Exception:
            grab_anterior = None

        # Evita el bloqueo que aparecia en el EXE:
        # si el formulario padre ya tiene grab_set(), lo soltamos
        # temporalmente y se lo damos a esta ventana hija visible.
        try:
            if grab_anterior is not None and grab_anterior.winfo_exists():
                grab_anterior.grab_release()
        except Exception:
            pass

        ventana = tk.Toplevel(padre)
        ventana._mantener_topmost = True
        ventana.title("Seleccion de Lado_corto")
        ventana.minsize(900, 560)
        ventana.resizable(True, True)

        try:
            ventana.transient(padre)
        except Exception:
            pass

        centrar_ventana(ventana, 980, 720)

        seleccion = tk.StringVar(
            master=ventana,
            value=str(recomendada["Numero"])
        )

        opciones_por_numero = {}
        frames_por_numero = {}
        radios_por_numero = {}
        resultado = {"opcion": recomendada}

        titulo = tk.Label(
            ventana,
            text="Selecciona como tratar las tiendas que van a Lado_corto",
            font=("Segoe UI", 13, "bold")
        )
        titulo.pack(padx=14, pady=(12, 4), anchor="w")

        subtitulo = tk.Label(
            ventana,
            text="Revisa las diferencias de lotes y tiendas antes de elegir. Pulsa Aceptar para continuar.",
            font=("Segoe UI", 9)
        )
        subtitulo.pack(padx=14, pady=(0, 10), anchor="w")

        contenedor = tk.Frame(ventana)
        contenedor.pack(fill="both", expand=True, padx=12, pady=6)

        canvas = tk.Canvas(contenedor, borderwidth=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(contenedor, orient="vertical", command=canvas.yview)
        frame_opciones = tk.Frame(canvas)

        ventana_canvas = canvas.create_window((0, 0), window=frame_opciones, anchor="nw")

        def configurar_scroll(evento=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                canvas.itemconfig(ventana_canvas, width=canvas.winfo_width())
            except Exception:
                pass

        frame_opciones.bind("<Configure>", configurar_scroll)
        canvas.bind("<Configure>", configurar_scroll)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def mover_rueda(evento):
            try:
                canvas.yview_scroll(int(-1 * (evento.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind_all("<MouseWheel>", mover_rueda)

        def actualizar_colores():

            numero_seleccionado = seleccion.get()

            for numero, frame in frames_por_numero.items():

                if str(numero) == numero_seleccionado:
                    color = "#d9ead3"
                elif numero == recomendada["Numero"]:
                    color = "#f4f7fb"
                else:
                    color = "#ffffff"

                try:
                    frame.configure(background=color)
                    radios_por_numero[numero].configure(background=color)
                except Exception:
                    pass

        def seleccionar_numero(numero):

            seleccion.set(str(numero))
            actualizar_colores()

        for opcion in opciones:

            numero = opcion["Numero"]
            opciones_por_numero[str(numero)] = opcion
            texto = texto_opcion_lado_corto(opcion, recomendada)

            opcion_frame = tk.Frame(
                frame_opciones,
                bd=1,
                relief="solid",
                padx=8,
                pady=6,
                background="#ffffff"
            )
            opcion_frame.pack(fill="x", padx=4, pady=5)

            radio = tk.Radiobutton(
                opcion_frame,
                text=texto,
                variable=seleccion,
                value=str(numero),
                justify="left",
                anchor="w",
                wraplength=870,
                background=opcion_frame["background"],
                font=("Consolas", 9),
                command=actualizar_colores
            )
            radio.pack(fill="x", anchor="w")

            opcion_frame.bind(
                "<Button-1>",
                lambda evento, n=numero: seleccionar_numero(n)
            )

            radio.bind(
                "<ButtonRelease-1>",
                lambda evento: actualizar_colores()
            )

            frames_por_numero[numero] = opcion_frame
            radios_por_numero[numero] = radio

        actualizar_colores()

        botones = tk.Frame(ventana)
        botones.pack(fill="x", padx=14, pady=(8, 12))

        lbl_aviso = tk.Label(
            botones,
            text="Si no eliges nada, se usara la opcion recomendada.",
            font=("Segoe UI", 8),
            fg="#555555"
        )
        lbl_aviso.pack(side="left", padx=4)

        def cerrar_con_resultado(opcion):
            resultado["opcion"] = opcion
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            try:
                ventana.grab_release()
            except Exception:
                pass
            ventana.destroy()

        def aceptar():

            numero = seleccion.get()
            opcion = opciones_por_numero.get(numero, recomendada)
            cerrar_con_resultado(opcion)

        def cancelar():

            cerrar_con_resultado(recomendada)

        boton_aceptar = tk.Button(
            botones,
            text="Aceptar",
            width=16,
            command=aceptar
        )
        boton_aceptar.pack(side="right", padx=4)

        boton_cancelar = tk.Button(
            botones,
            text="Usar recomendada",
            width=18,
            command=cancelar
        )
        boton_cancelar.pack(side="right", padx=4)

        ventana.protocol("WM_DELETE_WINDOW", cancelar)
        ventana.bind("<Return>", lambda evento: aceptar())
        ventana.bind("<Escape>", lambda evento: cancelar())

        # Primero mostramos y actualizamos. Despues hacemos el grab.
        # Este orden es importante al compilar con PyInstaller.
        ventana.update_idletasks()
        radio_inicial = radios_por_numero.get(recomendada["Numero"])
        forzar_ventana_al_frente(ventana, focus_widget=radio_inicial)

        try:
            ventana.grab_set()
        except Exception:
            pass

        ventana.wait_window()

        opcion_final = resultado.get("opcion", recomendada)

        if opcion_final is None:
            opcion_final = recomendada

        return opcion_final

    except Exception as error:

        try:
            if ventana is not None and ventana.winfo_exists():
                ventana.destroy()
        except Exception:
            pass

        try:
            messagebox.showwarning(
                "Lado_corto",
                "No se pudo abrir la ventana de Lado_corto. Se usara la opcion recomendada.\n\n" + str(error)
            )
        except Exception:
            pass

        return recomendada

    finally:

        # Restauramos el grab de la ventana padre para que la aplicacion
        # no se quede bloqueada despues de cerrar el dialogo.
        try:
            if grab_anterior is not None and grab_anterior.winfo_exists():
                grab_anterior.grab_set()
                grab_anterior.lift()
                grab_anterior.focus_force()
        except Exception:
            pass

        if raiz_creada and raiz is not None:
            try:
                raiz.destroy()
            except Exception:
                pass
