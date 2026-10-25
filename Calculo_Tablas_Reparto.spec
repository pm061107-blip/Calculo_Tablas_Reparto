# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('config/config.json', 'config'), ('datos_iniciales/Configuracion.xlsx', 'datos_iniciales'), ('datos_iniciales/Layout_Carruseles_TipoCaja.png', 'datos_iniciales')]
binaries = []
hiddenimports = ['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox', 'tkinter.simpledialog', 'modulos.dialogos_operador', 'modulos.dialogos_ui', 'modulos.dialogo_progreso', 'modulos.gestor_reset_calculos', 'modulos.sincronizador', 'modulos.dialogo_estados_estarepp', 'modulos.ventanas_tk', 'modulos.version_aplicacion', 'modulos.formulario_calculo_cajas_pedido', 'modulos.gestor_grupos_calculo_cajas', 'modulos.gestor_tiendas_fijas_cajas', 'modulos.gestor_pedido_escenario_activo', 'modulos.componente_pedido_escenario_activo', 'modulos.gestor_pedidos_trabajo', 'modulos.gestor_pedidos_cajas', 'modulos.formulario_editor_lados_cortos_domingo', 'modulos.repeticion_tiendas', 'modulos.componente_pedido_trabajo', 'modulos.procesar_estarepp', 'modulos.calculador_escenarios_cajas', 'modulos.formulario_volumetria_reutilizacion_paises', 'modulos.formulario_reparto_por_lados', 'modulos.motor_reparto_lados', 'modulos.configuracion_lados_carrusel', 'modulos.exportar_tabla_reparto_lados_csv', 'modulos.generar_mapa_tipo_caja', 'modulos.calculador_cajas_paises', 'modulos.volumetria_desde_contenedores', 'modulos.exportar_sin_volumetria', 'modulos.registro_importaciones_cajas', 'modulos.motor_calculo_cajas_pedido', 'modulos.algoritmo_xdoc_cajas', 'modulos.algoritmo_limpieza_celdas_cajas', 'modulos.algoritmo_mas_unidades_cajas', 'modulos.importar_volumetria_cajas', 'modulos.importar_contenedores_cajas', 'modulos.formulario_busca_fuera_tabla', 'modulos.formulario_paises_fuera_tabla', 'modulos.motor_busca_fuera_tabla', 'modulos.formulario_prioridad_paises_un_carrusel', 'modulos.formulario_maestros', 'modulos.formulario_maestro_tiendas_xdoc', 'modulos.cargar_configuracion', 'modulos.gestor_tipo_caja_pais', 'modulos.gestor_grutiep', 'modulos.gestor_grutiep_calculo', 'modulos.componente_grutiep']
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Calculo_Tablas_Reparto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Calculo_Tablas_Reparto',
)
