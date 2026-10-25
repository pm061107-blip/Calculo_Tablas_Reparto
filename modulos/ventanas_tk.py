"""Utilidades comunes para resolver ventanas activas de Tkinter.

La aplicacion mantiene una unica raiz ``Tk`` y abre los formularios de trabajo
como ``Toplevel``. La raiz principal se oculta mientras un formulario secundario
esta abierto. Por eso no se debe usar directamente ``tk._default_root`` como
padre de un dialogo: puede existir, pero estar en estado ``withdrawn``.
"""

import os
import tkinter as tk


def _existe(widget):
    if widget is None:
        return False
    try:
        return int(widget.winfo_exists()) == 1
    except Exception:
        return False



def activar_primer_plano_sistema(ventana):
    """Solicita al sistema operativo que active la ventana.

    En Windows, ``lift`` y ``focus_force`` no siempre bastan cuando otra
    ventana con grab acaba de cerrarse. Se usa tambien la API nativa como
    refuerzo. En otros sistemas la funcion no hace nada adicional.
    """

    if not _existe(ventana) or os.name != "nt":
        return

    try:
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(ventana.winfo_id()))
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

def _toplevel(widget):
    if not _existe(widget):
        return None
    try:
        top = widget.winfo_toplevel()
    except Exception:
        top = widget
    return top if _existe(top) else None


def _visible(widget):
    top = _toplevel(widget)
    if top is None:
        return False
    try:
        estado = str(top.state()).lower()
        if estado in ("withdrawn", "iconic"):
            return False
    except Exception:
        pass
    try:
        # ``winfo_viewable`` puede ser 0 durante los primeros milisegundos de
        # creacion. Un estado normal/zoomed sigue siendo un padre valido.
        return str(top.state()).lower() in ("normal", "zoomed") or bool(top.winfo_viewable())
    except Exception:
        return True


def _descendientes(widget):
    resultado = []
    if not _existe(widget):
        return resultado
    try:
        hijos = list(widget.winfo_children())
    except Exception:
        return resultado
    for hijo in hijos:
        resultado.append(hijo)
        resultado.extend(_descendientes(hijo))
    return resultado


def resolver_parent_tk(parent=None):
    """Devuelve el ``Tk/Toplevel`` visible que debe ser padre del dialogo.

    Orden de prioridad:
    1. padre explicito;
    2. ventana que posee el grab actual;
    3. ventana que contiene el foco;
    4. ultimo Toplevel visible de la aplicacion;
    5. raiz principal, solo si tambien esta visible.

    Nunca devuelve una raiz retirada (``withdrawn``), que era la causa de que
    los dialogos ESTAREPP quedasen abiertos pero invisibles.
    """

    explicito = _toplevel(parent)
    if explicito is not None and _visible(explicito):
        return explicito

    raiz = tk._default_root
    if not _existe(raiz):
        return None

    try:
        actual = raiz.grab_current()
    except Exception:
        actual = None
    actual = _toplevel(actual)
    if actual is not None and _visible(actual):
        return actual

    try:
        foco = raiz.focus_get()
    except Exception:
        foco = None
    foco = _toplevel(foco)
    if foco is not None and _visible(foco):
        return foco

    candidatos = []
    for widget in _descendientes(raiz):
        top = _toplevel(widget)
        if top is None or top is raiz or not _visible(top):
            continue
        if top not in candidatos:
            candidatos.append(top)

    if candidatos:
        return candidatos[-1]

    if _visible(raiz):
        return raiz

    return None


def obtener_grab_actual(reference=None):
    """Obtiene la ventana que tiene el grab local en este interprete Tcl."""

    referencia = _toplevel(reference) or tk._default_root
    if not _existe(referencia):
        return None
    try:
        grab = referencia.grab_current()
    except Exception:
        return None
    return _toplevel(grab)


def liberar_grab_temporal(reference=None):
    """Libera el grab actual y devuelve la ventana para restaurarlo despues."""

    grab = obtener_grab_actual(reference)
    if grab is not None:
        try:
            grab.grab_release()
        except Exception:
            pass
    return grab


def restaurar_grab(grab):
    """Restaura el grab del formulario padre si sigue abierto y visible."""

    if grab is None or not _existe(grab) or not _visible(grab):
        return
    try:
        grab.grab_set()
    except Exception:
        return
    try:
        grab.lift()
        grab.focus_force()
    except Exception:
        pass


def forzar_ventana_visible(
    ventana,
    parent=None,
    mantener_arriba=False,
    focus_widget=None,
):
    """Mapea, eleva y enfoca una ventana de forma fiable.

    ``mantener_arriba`` debe activarse en avisos modales o ventanas que el
    operador tiene que atender antes de continuar. En ese caso la ventana se
    mantiene ``topmost`` hasta que se destruye. Para ventanas normales se
    conserva el comportamiento temporal anterior.

    Si se indica ``focus_widget``, el cursor se coloca en ese control cuando la
    ventana ya esta visible.
    """

    if not _existe(ventana):
        return

    if parent is not None and _existe(parent):
        try:
            ventana.transient(parent)
        except Exception:
            pass

    try:
        ventana.deiconify()
    except Exception:
        pass
    try:
        ventana.update_idletasks()
    except Exception:
        pass

    def elevar():
        if not _existe(ventana):
            return
        try:
            ventana.lift()
            ventana.attributes("-topmost", True)
            ventana.focus_force()
            ventana.update_idletasks()
            activar_primer_plano_sistema(ventana)
        except Exception:
            pass

    elevar()

    # Repetir la elevacion evita que Windows deje la ventana detras cuando el
    # formulario padre tenia un grab activo o estaba recuperando el foco.
    try:
        ventana.after_idle(elevar)
        ventana.after(80, elevar)
        ventana.after(300, elevar)
    except Exception:
        pass

    if not mantener_arriba:
        try:
            ventana.after(
                700,
                lambda: ventana.attributes("-topmost", False)
                if _existe(ventana)
                else None,
            )
        except Exception:
            pass

    if focus_widget is not None:
        def enfocar_control():
            if not _existe(ventana) or not _existe(focus_widget):
                return
            try:
                focus_widget.focus_force()
                if hasattr(focus_widget, "selection_range"):
                    focus_widget.selection_range(0, "end")
                if hasattr(focus_widget, "icursor"):
                    focus_widget.icursor("end")
            except Exception:
                pass

        try:
            ventana.after_idle(enfocar_control)
            ventana.after(100, enfocar_control)
        except Exception:
            pass


def maximizar_ventana(ventana):
    """Abre una ventana como ventana normal maximizada.

    Los formularios principales deben poder minimizarse y alternarse desde la
    barra de tareas. Por eso no se aplica topmost permanente ni grab modal.
    """
    if not _existe(ventana):
        return
    try:
        ventana.deiconify()
    except Exception:
        pass
    try:
        ventana.update_idletasks()
    except Exception:
        pass
    try:
        ventana.state("zoomed")
        return
    except Exception:
        pass
    try:
        ancho = int(ventana.winfo_screenwidth())
        alto = int(ventana.winfo_screenheight())
        ventana.geometry(f"{ancho}x{alto}+0+0")
    except Exception:
        pass


def preparar_formulario_navegable(ventana, parent=None, maximizar=True):
    """Prepara un formulario grande para trabajar como ventana independiente.

    Libera cualquier grab heredado, quita topmost permanente, trae la ventana al
    frente de forma temporal y, por defecto, la maximiza. Se usa para formularios
    principales; los dialogos puntuales siguen usando el comportamiento modal.
    """
    if not _existe(ventana):
        return

    try:
        ventana.grab_release()
    except Exception:
        pass

    try:
        ventana.attributes("-topmost", False)
    except Exception:
        pass

    try:
        ventana._mantener_topmost = False
    except Exception:
        pass

    if parent is not None and _existe(parent):
        try:
            ventana.transient("")
        except Exception:
            pass

    if maximizar:
        maximizar_ventana(ventana)

    try:
        ventana.lift()
        ventana.focus_force()
        activar_primer_plano_sistema(ventana)
    except Exception:
        pass

    try:
        ventana.after(600, lambda: ventana.attributes("-topmost", False) if _existe(ventana) else None)
    except Exception:
        pass



def crear_marco_scrollable(parent, padx=0, pady=0, fondo=None):
    """Crea un contenedor con scroll vertical para formularios grandes.

    Devuelve el frame interior donde deben colocarse los controles del
    formulario. La rueda del raton desplaza el formulario cuando el cursor esta
    dentro del area desplazable. Esta utilidad evita que los botones y datos
    queden fuera de pantalla en resoluciones bajas o con escalado de Windows.
    """
    if fondo is None:
        try:
            fondo = parent.cget("background")
        except Exception:
            fondo = None

    exterior = tk.Frame(parent, background=fondo)
    exterior.pack(fill="both", expand=True, padx=padx, pady=pady)
    exterior.grid_rowconfigure(0, weight=1)
    exterior.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(exterior, highlightthickness=0, borderwidth=0, background=fondo)
    scroll = tk.Scrollbar(exterior, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)

    canvas.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")

    contenido = tk.Frame(canvas, background=fondo)
    window_id = canvas.create_window((0, 0), window=contenido, anchor="nw")

    def _actualizar_scroll(_evento=None):
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _ajustar_ancho(evento):
        try:
            canvas.itemconfigure(window_id, width=evento.width)
        except Exception:
            pass

    contenido.bind("<Configure>", _actualizar_scroll, add="+")
    canvas.bind("<Configure>", _ajustar_ancho, add="+")

    def _rueda(evento):
        try:
            # Windows/macOS entregan delta. En Linux se usan Button-4/5.
            if getattr(evento, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(evento, "num", None) == 5:
                canvas.yview_scroll(3, "units")
            else:
                delta = int(evento.delta)
                if delta == 0:
                    return
                canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        except Exception:
            pass

    def _activar_rueda(_evento=None):
        try:
            canvas.bind_all("<MouseWheel>", _rueda, add="+")
            canvas.bind_all("<Button-4>", _rueda, add="+")
            canvas.bind_all("<Button-5>", _rueda, add="+")
        except Exception:
            pass

    def _desactivar_rueda(_evento=None):
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    exterior.bind("<Enter>", _activar_rueda, add="+")
    exterior.bind("<Leave>", _desactivar_rueda, add="+")
    contenido.bind("<Enter>", _activar_rueda, add="+")
    contenido.bind("<Leave>", _desactivar_rueda, add="+")

    contenido._scroll_canvas = canvas
    contenido._scroll_exterior = exterior
    contenido._scroll_barra = scroll
    return contenido


# =========================================================
# V2.7 - Adaptacion a la resolucion de cada PC
#
# Muchos formularios piden un tamano fijo (geometry / minsize) pensado para
# una pantalla grande. En un PC con menos resolucion la ventana quedaba mas
# grande que la pantalla y los botones fuera de la vista. Aqui se recortan
# AUTOMATICAMENTE esos tamanos al area visible de la pantalla de cada PC, sin
# tener que tocar cada formulario.
# =========================================================
MARGEN_BARRA_TAREAS = 60

_PATRON_GEOMETRIA = None


def _area_visible(ancho_pantalla, alto_pantalla):
    return max(320, int(ancho_pantalla)), max(240, int(alto_pantalla) - MARGEN_BARRA_TAREAS)


def ajustar_geometria_a_pantalla(texto, ancho_pantalla, alto_pantalla):
    """'1400x940+10+20' -> mismo texto recortado al area visible."""
    global _PATRON_GEOMETRIA
    if _PATRON_GEOMETRIA is None:
        import re
        _PATRON_GEOMETRIA = re.compile(r"^(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?$")
    if texto is None:
        return texto
    coincidencia = _PATRON_GEOMETRIA.match(str(texto).strip())
    if not coincidencia:
        return texto
    max_ancho, max_alto = _area_visible(ancho_pantalla, alto_pantalla)
    ancho = min(int(coincidencia.group(1)), max_ancho)
    alto = min(int(coincidencia.group(2)), max_alto)
    resultado = str(ancho) + "x" + str(alto)
    if coincidencia.group(3) is not None:
        x = max(0, min(int(coincidencia.group(3)), max_ancho - ancho))
        y = max(0, min(int(coincidencia.group(4)), max_alto - alto))
        resultado += "+" + str(x) + "+" + str(y)
    return resultado


def ajustar_minimo_a_pantalla(ancho, alto, ancho_pantalla, alto_pantalla):
    max_ancho, max_alto = _area_visible(ancho_pantalla, alto_pantalla)
    return min(int(ancho), int(max_ancho * 0.9)), min(int(alto), int(max_alto * 0.9))


def instalar_adaptacion_pantalla():
    """Recorta geometry() y minsize() de TODAS las ventanas a la pantalla."""
    wm = getattr(tk, "Wm", None)
    if wm is None or getattr(wm, "_adaptacion_pantalla_v27", False):
        return
    geometry_original = getattr(wm, "wm_geometry", None)
    minsize_original = getattr(wm, "wm_minsize", None)
    if geometry_original is None or minsize_original is None:
        return

    def wm_geometry(self, newGeometry=None):
        if newGeometry:
            try:
                newGeometry = ajustar_geometria_a_pantalla(
                    newGeometry, self.winfo_screenwidth(), self.winfo_screenheight()
                )
            except Exception:
                pass
        return geometry_original(self, newGeometry)

    def wm_minsize(self, width=None, height=None):
        if width is not None and height is not None:
            try:
                width, height = ajustar_minimo_a_pantalla(
                    width, height, self.winfo_screenwidth(), self.winfo_screenheight()
                )
            except Exception:
                pass
        return minsize_original(self, width, height)

    wm.wm_geometry = wm.geometry = wm_geometry
    wm.wm_minsize = wm.minsize = wm_minsize
    wm._adaptacion_pantalla_v27 = True


try:
    instalar_adaptacion_pantalla()
except Exception:
    pass

