@echo off
setlocal EnableExtensions

title Compilar Calculo_Tablas_Reparto 2.0

set "PROYECTO=C:\Trabajos\Calculo_Tablas_Reparto"
set "PYTHON=C:\Users\juanmcp\AppData\Local\Programs\Python\Python314-32\python.exe"
set "NOMBRE_APP=Calculo_Tablas_Reparto"

echo ============================================================
echo  COMPILACION DE CALCULO_TABLAS_REPARTO 2.0
echo ============================================================
echo.

if not exist "%PROYECTO%\main.py" (
    echo ERROR: No se encuentra:
    echo %PROYECTO%\main.py
    echo.
    pause
    exit /b 1
)

if not exist "%PYTHON%" (
    echo ERROR: No se encuentra Python en:
    echo %PYTHON%
    echo.
    pause
    exit /b 1
)

if not exist "%PROYECTO%\config\config.json" (
    echo ERROR: Falta config\config.json
    pause
    exit /b 1
)

if not exist "%PROYECTO%\datos_iniciales\Configuracion.xlsx" (
    echo ERROR: Falta datos_iniciales\Configuracion.xlsx
    pause
    exit /b 1
)

if not exist "%PROYECTO%\datos_iniciales\Layout_Carruseles_TipoCaja.png" (
    echo ERROR: Falta datos_iniciales\Layout_Carruseles_TipoCaja.png
    pause
    exit /b 1
)

rem Verificacion expresa de dependencias del escenario activo.
rem Evita generar un EXE incompleto si se ha omitido una actualizacion incremental.
if not exist "%PROYECTO%\modulos\gestor_pedido_escenario_activo.py" (
    echo ERROR: Falta modulos\gestor_pedido_escenario_activo.py
    echo Copia primero todos los archivos de esta actualizacion.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\componente_pedido_escenario_activo.py" (
    echo ERROR: Falta modulos\componente_pedido_escenario_activo.py
    echo Copia primero todos los archivos de esta actualizacion.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\gestor_pedidos_trabajo.py" (
    echo ERROR: Falta modulos\gestor_pedidos_trabajo.py
    echo Debes tener instalada la actualizacion V17.24.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\componente_pedido_trabajo.py" (
    echo ERROR: Falta modulos\componente_pedido_trabajo.py
    echo Debes tener instalada la actualizacion V17.24.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\procesar_estarepp.py" (
    echo ERROR: Falta modulos\procesar_estarepp.py
    echo Copia primero la actualizacion 2.0.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\algoritmo_xdoc_cajas.py" (
    echo ERROR: Falta modulos\algoritmo_xdoc_cajas.py
    echo Copia primero todos los archivos de esta actualizacion.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\dialogo_progreso.py" (
    echo ERROR: Falta modulos\dialogo_progreso.py
    echo Copia primero todos los archivos de esta actualizacion.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\gestor_reset_calculos.py" (
    echo ERROR: Falta modulos\gestor_reset_calculos.py
    echo Copia primero todos los archivos de esta actualizacion.
    pause
    exit /b 1
)
if not exist "%PROYECTO%\modulos\gestor_grutiep_calculo.py" (
    echo ERROR: Falta modulos\gestor_grutiep_calculo.py
    echo Copia primero la actualizacion V17.25 o posterior.
    pause
    exit /b 1
)

cd /d "%PROYECTO%"

echo.
echo Verificando imports obligatorios...
"%PYTHON%" -c "import inspect; import modulos.gestor_pedido_escenario_activo; import modulos.componente_pedido_escenario_activo; import modulos.gestor_grupos_calculo_cajas; import modulos.formulario_calculo_cajas_pedido; import modulos.dialogo_progreso; import modulos.gestor_reset_calculos; import modulos.gestor_pedidos_trabajo; import modulos.componente_pedido_trabajo; import modulos.gestor_grutiep_calculo; from modulos.procesar_estarepp import ProcesarESTAREPP; p=inspect.signature(ProcesarESTAREPP.__init__).parameters; assert 'tabla_origen' in p and 'bd' in p, 'ProcesarESTAREPP desactualizado: faltan tabla_origen/bd'"
if errorlevel 1 (
    echo.
    echo ERROR: No se pueden importar los modulos obligatorios del pedido.
    echo Revisa que la actualizacion se haya extraido sobre la carpeta del proyecto.
    pause
    exit /b 1
)

echo Verificando version de fuentes...
"%PYTHON%" -c "from modulos.version_aplicacion import VERSION_APP; assert VERSION_APP == '2.0', 'Version de fuentes incorrecta: ' + str(VERSION_APP)"
if errorlevel 1 (
    echo.
    echo ERROR: Las fuentes no corresponden a 2.0.
    echo Extrae de nuevo el ZIP completo de esta correccion.
    pause
    exit /b 1
)

echo Cerrando posibles ejecuciones anteriores...
taskkill /F /IM "%NOMBRE_APP%.exe" >nul 2>&1

echo.
echo Comprobando PyInstaller...
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller no esta instalado. Instalando...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo ERROR: No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Limpiando compilaciones anteriores...
if exist "build" rmdir /S /Q "build"
if exist "dist" rmdir /S /Q "dist"
if exist "%NOMBRE_APP%.spec" del /F /Q "%NOMBRE_APP%.spec"
for /D /R "%PROYECTO%" %%D in (__pycache__) do @if exist "%%D" rmdir /S /Q "%%D"
del /S /Q "*.pyc" >nul 2>&1


echo.
echo Verificando sintaxis de fuentes...
"%PYTHON%" -m compileall -q main.py bd modulos
if errorlevel 1 (
    echo.
    echo ERROR: Hay errores de sintaxis en los modulos Python.
    pause
    exit /b 1
)

echo.
echo Compilando...
echo.

"%PYTHON%" -m PyInstaller ^
  --noconsole ^
  --onedir ^
  --clean ^
  --noconfirm ^
  --name "%NOMBRE_APP%" ^
  --hidden-import=tkinter ^
  --hidden-import=tkinter.ttk ^
  --hidden-import=tkinter.filedialog ^
  --hidden-import=tkinter.messagebox ^
  --hidden-import=tkinter.simpledialog ^
  --hidden-import=modulos.dialogos_operador ^
  --hidden-import=modulos.dialogos_ui ^
  --hidden-import=modulos.dialogo_progreso ^
  --hidden-import=modulos.gestor_reset_calculos ^
  --hidden-import=modulos.sincronizador ^
  --hidden-import=modulos.dialogo_estados_estarepp ^
  --hidden-import=modulos.ventanas_tk ^
  --hidden-import=modulos.version_aplicacion ^
  --hidden-import=modulos.formulario_calculo_cajas_pedido ^
  --hidden-import=modulos.gestor_grupos_calculo_cajas ^
  --hidden-import=modulos.gestor_tiendas_fijas_cajas ^
  --hidden-import=modulos.gestor_pedido_escenario_activo ^
  --hidden-import=modulos.componente_pedido_escenario_activo ^
  --hidden-import=modulos.gestor_pedidos_trabajo ^
  --hidden-import=modulos.componente_pedido_trabajo ^
  --hidden-import=modulos.procesar_estarepp ^
  --hidden-import=modulos.calculador_escenarios_cajas ^
  --hidden-import=modulos.formulario_volumetria_reutilizacion_paises ^
  --hidden-import=modulos.formulario_reparto_por_lados ^
  --hidden-import=modulos.motor_reparto_lados ^
  --hidden-import=modulos.configuracion_lados_carrusel ^
  --hidden-import=modulos.exportar_tabla_reparto_lados_csv ^
  --hidden-import=modulos.generar_mapa_tipo_caja ^
  --hidden-import=modulos.calculador_cajas_paises ^
  --hidden-import=modulos.volumetria_desde_contenedores ^
  --hidden-import=modulos.exportar_sin_volumetria ^
  --hidden-import=modulos.registro_importaciones_cajas ^
  --hidden-import=modulos.motor_calculo_cajas_pedido ^
  --hidden-import=modulos.algoritmo_xdoc_cajas ^
  --hidden-import=modulos.algoritmo_limpieza_celdas_cajas ^
  --hidden-import=modulos.algoritmo_mas_unidades_cajas ^
  --hidden-import=modulos.importar_volumetria_cajas ^
  --hidden-import=modulos.importar_contenedores_cajas ^
  --hidden-import=modulos.formulario_busca_fuera_tabla ^
  --hidden-import=modulos.formulario_paises_fuera_tabla ^
  --hidden-import=modulos.motor_busca_fuera_tabla ^
  --hidden-import=modulos.formulario_prioridad_paises_un_carrusel ^
  --hidden-import=modulos.formulario_maestros ^
  --hidden-import=modulos.formulario_maestro_tiendas_xdoc ^
  --hidden-import=modulos.cargar_configuracion ^
  --hidden-import=modulos.gestor_tipo_caja_pais ^
  --hidden-import=modulos.gestor_grutiep ^
  --hidden-import=modulos.gestor_grutiep_calculo ^
  --hidden-import=modulos.componente_grutiep ^
  --collect-all PIL ^
  --add-data "config\config.json;config" ^
  --add-data "datos_iniciales\Configuracion.xlsx;datos_iniciales" ^
  --add-data "datos_iniciales\Layout_Carruseles_TipoCaja.png;datos_iniciales" ^
  "main.py"

if errorlevel 1 (
    echo.
    echo ============================================================
    echo  ERROR: LA COMPILACION NO HA FINALIZADO CORRECTAMENTE
    echo ============================================================
    echo.
    echo Revisa los mensajes anteriores.
    echo Si aparece Acceso denegado, cierra el EXE y cualquier ventana
    echo abierta dentro de la carpeta dist y vuelve a ejecutar este BAT.
    echo.
    pause
    exit /b 1
)

set "EXE=%PROYECTO%\dist\%NOMBRE_APP%\%NOMBRE_APP%.exe"

if not exist "%EXE%" (
    echo.
    echo ERROR: PyInstaller finalizo, pero no se encuentra el EXE:
    echo %EXE%
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  COMPILACION FINALIZADA CORRECTAMENTE
echo ============================================================
echo.
echo Aplicacion generada en:
echo %EXE%
echo.
echo Para instalarla en otro PC, copia la carpeta completa:
echo %PROYECTO%\dist\%NOMBRE_APP%
echo.
echo No copies solo el EXE.
echo.

choice /C SN /N /M "Quieres abrir ahora la aplicacion? [S/N]: "
if errorlevel 2 goto FIN

start "" "%EXE%"

:FIN
echo.
pause
endlocal
