from bd.basedatos import BaseDatos
from modulos.sincronizador import Sincronizador
from modulos.cargar_configuracion import CargarConfiguracion
from modulos.formulario_principal import FormularioPrincipal
from modulos.dialogos_ui import (
    configurar_enfoque_automatico,
    instalar_dialogos_globales,
)


def main():

    # Instalar antes de abrir cualquier formulario: todos los messagebox y
    # simpledialog quedan ligados al formulario visible y se muestran delante.
    instalar_dialogos_globales()

    bd = BaseDatos()

    try:
        bd.crear_base()
        bd.crear_tablas()

        sincronizador = Sincronizador()
        resultado_tiendas_web = None

        try:
            # Esta sincronizacion nunca debe cerrar la aplicacion. Si el fichero
            # de red no se puede leer, devuelve el estado de la copia local.
            resultado_tiendas_web = sincronizador.sincronizar_tiendas_web()

            # Se conserva el comportamiento existente para TipoCajaInicial.
            sincronizador.sincronizar_tipo_caja_inicial()
        finally:
            sincronizador.cerrar()

        configuracion = CargarConfiguracion()
        configuracion.cargar_configuracion()

        formulario = FormularioPrincipal(
            resultado_tiendas_web=resultado_tiendas_web
        )
        configurar_enfoque_automatico(formulario.ventana)
        formulario.ejecutar()

    finally:
        bd.cerrar()


if __name__ == "__main__":
    main()
