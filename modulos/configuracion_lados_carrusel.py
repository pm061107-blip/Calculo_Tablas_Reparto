"""Definicion unica de los ocho lados fisicos de los dos carruseles.

La clave tecnica combina clasificador, lado interno y zona. Los rangos de
destino se mantienen explicitos para validar que el reparto solo utiliza las
tolvas fisicas seleccionadas por el operador.
"""

LADOS_CARRUSEL = [
    {
        "Id": "CLA1_CORTO1",
        "Clasificador": 1,
        "Lado": 1,
        "Descripcion": "Lado_corto",
        "Nombre": "CLA 1 - Corto 1",
        "Desde": 1,
        "Hasta": 44,
        "CapacidadEsperada": 44,
    },
    {
        "Id": "CLA1_LARGO1",
        "Clasificador": 1,
        "Lado": 1,
        "Descripcion": "Lado_Largo",
        "Nombre": "CLA 1 - Largo 1",
        "Desde": 45,
        "Hasta": 172,
        "CapacidadEsperada": 128,
    },
    {
        "Id": "CLA1_CORTO2",
        "Clasificador": 1,
        "Lado": 2,
        "Descripcion": "Lado_corto",
        "Nombre": "CLA 1 - Corto 2",
        "Desde": 173,
        "Hasta": 214,
        "CapacidadEsperada": 42,
    },
    {
        "Id": "CLA1_LARGO2",
        "Clasificador": 1,
        "Lado": 2,
        "Descripcion": "Lado_Largo",
        "Nombre": "CLA 1 - Largo 2",
        "Desde": 215,
        "Hasta": 340,
        "CapacidadEsperada": 126,
    },
    {
        "Id": "CLA2_CORTO1",
        "Clasificador": 2,
        "Lado": 3,
        "Descripcion": "Lado_corto",
        "Nombre": "CLA 2 - Corto 1",
        "Desde": 1,
        "Hasta": 44,
        "CapacidadEsperada": 44,
    },
    {
        "Id": "CLA2_LARGO1",
        "Clasificador": 2,
        "Lado": 3,
        "Descripcion": "Lado_Largo",
        "Nombre": "CLA 2 - Largo 1",
        "Desde": 45,
        "Hasta": 172,
        "CapacidadEsperada": 128,
    },
    {
        "Id": "CLA2_CORTO2",
        "Clasificador": 2,
        "Lado": 4,
        "Descripcion": "Lado_corto",
        "Nombre": "CLA 2 - Corto 2",
        "Desde": 173,
        "Hasta": 214,
        "CapacidadEsperada": 42,
    },
    {
        "Id": "CLA2_LARGO2",
        "Clasificador": 2,
        "Lado": 4,
        "Descripcion": "Lado_Largo",
        "Nombre": "CLA 2 - Largo 2",
        "Desde": 215,
        "Hasta": 340,
        "CapacidadEsperada": 126,
    },
]

LADOS_POR_ID = {lado["Id"]: lado for lado in LADOS_CARRUSEL}


def obtener_lado(lado_id):
    try:
        return LADOS_POR_ID[lado_id]
    except KeyError as exc:
        raise ValueError("Lado de carrusel no valido: " + str(lado_id)) from exc


def clave_fisica(lado):
    return (
        int(lado["Clasificador"]),
        int(lado["Lado"]),
        str(lado["Descripcion"]),
    )


def destino_pertenece(lado, clasificador, numero_lado, descripcion, destino):
    return (
        int(clasificador) == int(lado["Clasificador"])
        and int(numero_lado) == int(lado["Lado"])
        and str(descripcion) == str(lado["Descripcion"])
        and int(lado["Desde"]) <= int(destino) <= int(lado["Hasta"])
    )
