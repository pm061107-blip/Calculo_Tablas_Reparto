# Memoria tecnica - Calculo Tablas Reparto V17.14

Fecha de referencia: 1 de octubre de 2026.

## Base

V17.14 parte de la aplicacion completa V17.13 y conserva todos sus modulos:
reparto, adelanto, busca fuera de tabla, reparto por lados, maestros y calculo
de cajas. La aplicacion usa Tkinter, SQLite (`reparto.db`) y el maestro
`datos_iniciales/Configuracion.xlsx`.

La version visible es:

`V17.14 - Sincronizacion exclusiva de paises Caja 400`

## Correccion funcional

En `FormularioCalculoCajasPedido`, el boton `CARGAR PAISES 400 EN MAESTRO`
ya no realiza una actualizacion incremental. Construye un maestro objetivo
completo con los paises actualmente marcados como Caja 400.

El contenido final de `TipoCajaPais` cumple:

- Pais seleccionado como Caja 400: permanece o se anade con su tipo resuelto.
- Pais no seleccionado: se elimina.
- Pais marcado como Caja 300: se elimina.
- Pais antiguo que no aparece en el calculo actual: se elimina.
- Ningun pais Caja 400 seleccionado: el maestro queda vacio tras confirmacion.

## Resolucion del tipo

La familia se obtiene sin consultar previamente `TipoCajaPais`, para evitar
circularidad:

1. Relacion Tienda -> Pais mediante `Tiendas_Web`.
2. Lectura de `TipoCajaInicial` por tienda.
3. Homologacion mediante `TiposDeCaja`.
4. Conversion:
   - Nueva -> `4_Nueva_40`.
   - Reutilizada/Usada -> `3_Usada_40`.

Un pais con tiendas de ambas familias es incoherente y bloquea toda la
operacion. Tambien bloquean los tipos sin homologar y la ausencia de informacion
suficiente.

## Persistencia exacta

`GestorTipoCajaPais.guardar_maestro_seleccionado()` recibe un diccionario que
representa el maestro final completo. La operacion:

1. Normaliza y valida paises y tipos.
2. Calcula altas, modificaciones, eliminaciones y coincidencias.
3. Compara el objetivo con Excel y con todas las filas SQLite, conservando los
   duplicados en la lectura para detectar inconsistencias.
4. Crea un backup de `Configuracion.xlsx`.
5. Genera un Excel temporal con solo las filas objetivo.
6. Inicia una transaccion SQLite `BEGIN IMMEDIATE`.
7. Sustituye completamente la tabla `TipoCajaPais`.
8. Reemplaza el Excel.
9. Verifica ambos destinos antes del commit.
10. Ante un error, ejecuta rollback y restaura el Excel desde el backup.

## Interfaz

La vista previa informa de:

- Paises Caja 400 seleccionados.
- Paises que se eliminaran.
- Altas, coincidencias y conflictos.
- Contenido final previsto.

El boton queda habilitado despues de calcular paises aunque la seleccion Caja
400 sea vacia. Esto permite sincronizar el maestro a cero registros de forma
consciente y confirmada.

## Pruebas

La bateria completa contiene 18 pruebas. Ademas de las pruebas heredadas, se
validan la sustitucion exclusiva, el vaciado, la resincronizacion SQLite y la
integracion del formulario.

La prueba con copias de los maestros reales elimino ALEMANIA al seleccionar
solo ITALIA y TURQUIA, y verifico que Excel y SQLite terminaron identicos.

V17.14 es la base de referencia para las siguientes modificaciones.
