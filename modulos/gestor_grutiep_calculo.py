"""Validacion GRUTIEP previa al calculo de tablas.

Esta validacion no modifica GRUTIEP ni el pedido de trabajo permanente del
formulario. Si el operador decide excluir las tiendas que no estan en GRUTIEP,
se crea una copia temporal del pedido para ese calculo concreto.
"""

from __future__ import annotations

from datetime import datetime
from tkinter import messagebox
from uuid import uuid4

from modulos.gestor_grutiep import GestorGRUTIEP
from modulos.gestor_pedidos_trabajo import GestorPedidosTrabajo


def _formatear_tiendas(tiendas, por_linea=12):
    valores = [str(int(t)) for t in sorted(tiendas or [])]
    if not valores:
        return "-"
    return "\n".join(
        ", ".join(valores[i : i + por_linea])
        for i in range(0, len(valores), por_linea)
    )


def _copiar_pedido_filtrado(conexion, clave_origen, clave_destino, tiendas_excluidas):
    gestor = GestorPedidosTrabajo(conexion)
    estado = gestor.obtener_estado(clave_origen)
    if not estado.get("Disponible"):
        raise RuntimeError(GestorPedidosTrabajo.texto_estado(estado))

    tiendas_excluidas = {int(t) for t in tiendas_excluidas or set()}
    id_pedido = uuid4().hex
    fecha_hora = datetime.now().isoformat(timespec="seconds")
    cursor = conexion.cursor()

    try:
        if conexion.in_transaction:
            conexion.commit()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "DELETE FROM PEDIDOS_TRABAJO_DETALLE WHERE ClaveFormulario=?",
            (clave_destino,),
        )
        cursor.execute(
            "DELETE FROM PEDIDOS_TRABAJO_META WHERE ClaveFormulario=?",
            (clave_destino,),
        )
        cursor.execute(
            "DELETE FROM PEDIDOS_TRABAJO_ULTIMO_CALCULO WHERE ClaveFormulario=?",
            (clave_destino,),
        )

        cursor.execute(
            """
            INSERT INTO PEDIDOS_TRABAJO_DETALLE (
                ClaveFormulario, IdPedido, Tienda, Aparte, Lotes, Pais, TipoCaja
            )
            SELECT ?, ?, Tienda, Aparte, Lotes, Pais, TipoCaja
            FROM PEDIDOS_TRABAJO_DETALLE
            WHERE ClaveFormulario=?
              AND IdPedido=?
              AND CAST(Tienda AS INTEGER) NOT IN (
            """
            + ",".join("?" for _ in tiendas_excluidas)
            + ")",
            [clave_destino, id_pedido, estado["ClaveFormulario"], estado["IdPedido"]]
            + sorted(tiendas_excluidas),
        )

        cursor.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT Tienda), COUNT(DISTINCT Tienda || '-' || Aparte),
                   IFNULL(SUM(Lotes), 0)
            FROM PEDIDOS_TRABAJO_DETALLE
            WHERE ClaveFormulario=? AND IdPedido=?
            """,
            (clave_destino, id_pedido),
        )
        registros, tiendas, apartes, lotes = cursor.fetchone() or (0, 0, 0, 0.0)
        registros = int(registros or 0)
        if registros <= 0:
            raise RuntimeError(
                "Al excluir las tiendas que no estan en GRUTIEP, el pedido queda vacio."
            )

        detalle = str(estado.get("DetalleOrigen", "") or "").strip()
        if detalle:
            detalle += "\n"
        detalle += (
            "Pedido efectivo del calculo: se excluyeron tiendas no presentes en GRUTIEP: "
            + ", ".join(str(t) for t in sorted(tiendas_excluidas))
        )

        cursor.execute(
            """
            INSERT INTO PEDIDOS_TRABAJO_META (
                ClaveFormulario, IdPedido, TipoOrigen, NombreOrigen,
                DetalleOrigen, FechaHora, TablaOrigen, RegistrosOrigen,
                TiendasOrigen, TiendasAparte, Lotes, Unidades, Valido
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                clave_destino,
                id_pedido,
                str(estado.get("TipoOrigen", "")) or "COPIA_INTERNA",
                str(estado.get("NombreOrigen", "")) + " - sin tiendas fuera de GRUTIEP",
                detalle,
                fecha_hora,
                "PEDIDOS_TRABAJO_DETALLE",
                registros,
                int(tiendas or 0),
                int(apartes or 0),
                float(lotes or 0.0),
                0,
            ),
        )
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise

    return gestor.obtener_estado(clave_destino)


def preparar_pedido_con_grutiep_para_tablas(
    conexion,
    clave_pedido_trabajo,
    parent=None,
    titulo="Validacion GRUTIEP",
):
    """Devuelve la clave efectiva que debe usar el motor para este calculo.

    Si no hay tiendas fuera de GRUTIEP, o si el operador decide incluirlas, se
    devuelve la clave original. Si decide excluirlas, se crea una copia temporal
    filtrada y se devuelve esa clave.
    """

    clave_original = str(clave_pedido_trabajo or "").strip().upper()
    if not clave_original:
        raise ValueError("No se ha indicado la clave del pedido de trabajo.")

    gestor_pedidos = GestorPedidosTrabajo(conexion)
    estado = gestor_pedidos.obtener_estado(clave_original)
    if not estado.get("Disponible"):
        raise RuntimeError(GestorPedidosTrabajo.texto_estado(estado))

    gestor_grutiep = GestorGRUTIEP(conexion=conexion)
    importacion = gestor_grutiep.obtener_ultima_importacion()
    if importacion is None:
        messagebox.showwarning(
            "GRUTIEP no importado",
            "No hay ningun GRUTIEP importado.\n\n"
            "No se puede comprobar si las tiendas del pedido pertenecen al grupo de reparto.\n"
            "El calculo continuara con el pedido completo del formulario.",
            parent=parent,
        )
        return {
            "ClavePedidoTrabajo": clave_original,
            "Decision": "SIN_GRUTIEP",
            "TiendasNoGrutiep": [],
            "Resumen": "GRUTIEP: no importado; calculo con pedido completo.",
        }

    disponibles = gestor_grutiep.obtener_tiendas_importadas()
    detalle = gestor_pedidos.obtener_detalle(clave_original)
    tiendas_pedido = {int(fila[0]) for fila in detalle}
    faltantes = sorted(tiendas_pedido - disponibles)

    if not faltantes:
        return {
            "ClavePedidoTrabajo": clave_original,
            "Decision": "OK",
            "TiendasNoGrutiep": [],
            "Resumen": "GRUTIEP: todas las tiendas del pedido existen en TRTIEN.",
        }

    mensaje = (
        "Hay tiendas del pedido que no estan en el GRUTIEP importado.\n\n"
        "GRUTIEP: "
        + str(importacion.get("NombreArchivo", ""))
        + "\nTiendas no encontradas: "
        + str(len(faltantes))
        + "\n\n"
        + _formatear_tiendas(faltantes)
        + "\n\n¿Quieres INCLUIRLAS igualmente en este calculo?\n\n"
        "Si respondes NO, se excluiran solo para este calculo. "
        "No se modificara GRUTIEP ni el pedido guardado del formulario."
    )

    incluir = messagebox.askyesno(
        titulo,
        mensaje,
        parent=parent,
    )

    if incluir:
        return {
            "ClavePedidoTrabajo": clave_original,
            "Decision": "INCLUIDAS",
            "TiendasNoGrutiep": faltantes,
            "Resumen": "GRUTIEP: " + str(len(faltantes)) + " tiendas no encontradas, incluidas por decision del operador.",
        }

    clave_temporal = clave_original + "__GRUTIEP_EFECTIVO"
    estado_filtrado = _copiar_pedido_filtrado(
        conexion,
        clave_origen=clave_original,
        clave_destino=clave_temporal,
        tiendas_excluidas=set(faltantes),
    )

    return {
        "ClavePedidoTrabajo": clave_temporal,
        "Decision": "EXCLUIDAS",
        "TiendasNoGrutiep": faltantes,
        "EstadoFiltrado": estado_filtrado,
        "Resumen": "GRUTIEP: " + str(len(faltantes)) + " tiendas no encontradas, excluidas por decision del operador.",
    }
