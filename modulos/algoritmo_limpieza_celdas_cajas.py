from collections import Counter, defaultdict
from functools import lru_cache
from math import gcd, sqrt


class AlgoritmoLimpiezaCeldas:
    """
    Limpieza de celdas V17.25.10, ajustada contra comparativa real SILO.

    Jerarquia revisada para aproximarse al SILO:
    1. Minimizar el numero de cajas es el criterio principal absoluto.
       Una seleccion con menos cajas gana aunque tenga una caja parcial/retorno.
    2. Se permite como maximo una caja de retorno por SKU para evitar cajas
       adicionales de ajuste fino.
    3. Entre soluciones con el mismo numero de cajas, se prioriza de forma fuerte
       el equilibrio de pasillos por movimientos/cajas. La seleccion fisica evita
       cargar repetidamente el pasillo mas ocupado.
    4. El exceso/retorno se evalua despues del equilibrio operativo.
    5. La limpieza de celdas queda como desempate posterior, no debe provocar
       usar mas cajas ni sobrecargar un pasillo si existe una alternativa
       equivalente en un pasillo menos cargado.
    """

    def __init__(self):
        pass

    # ---------------------------------------------------------
    # Utilidades
    # ---------------------------------------------------------
    def _entero(self, valor, defecto=0):
        try:
            return int(round(float(valor)))
        except Exception:
            return defecto

    def _peso_lotes(self, caja):
        lotes = self._entero(caja.get("Lotes", 0), 0)
        return lotes if lotes > 0 else 1

    def _pasillo(self, caja):
        valor = str(caja.get("Pasillo", "") or "").strip()
        return valor if valor else "(SIN PASILLO)"

    def _celda(self, caja):
        return str(caja.get("Celda", "") or caja.get("Posicion", "") or "").strip()

    def _matricula(self, caja):
        return str(caja.get("Matricula", "") or "").strip()

    def _profundidad(self, caja):
        return self._entero(caja.get("Profundidad", 0), 0)

    def _carga_vacia(self):
        pasillos = [str(numero).zfill(2) for numero in range(1, 11)]
        return {
            "cajas": {pasillo: 0 for pasillo in pasillos},
            "lotes": {pasillo: 0 for pasillo in pasillos},
            "unidades": {pasillo: 0 for pasillo in pasillos},
        }

    def _normalizar_cargas(self, carga_pasillos):
        cargas = self._carga_vacia()
        if not carga_pasillos:
            return cargas

        if all(clave in carga_pasillos for clave in ("cajas", "lotes", "unidades")):
            for metrica in ("cajas", "lotes", "unidades"):
                for pasillo, valor in dict(carga_pasillos.get(metrica, {})).items():
                    cargas[metrica][str(pasillo)] = self._entero(valor, 0)
            return cargas

        # Compatibilidad con versiones antiguas: el diccionario simple se
        # interpretaba como carga de lotes.
        for pasillo, valor in dict(carga_pasillos).items():
            if isinstance(valor, dict):
                continue
            cargas["lotes"][str(pasillo)] = self._entero(valor, 0)
        return cargas

    def _copiar_cargas(self, cargas):
        return {
            metrica: dict(valores)
            for metrica, valores in cargas.items()
        }

    def _sumar_carga(self, cargas, caja):
        pasillo = self._pasillo(caja)
        cargas["cajas"][pasillo] = cargas["cajas"].get(pasillo, 0) + 1
        cargas["lotes"][pasillo] = cargas["lotes"].get(pasillo, 0) + self._peso_lotes(caja)
        cargas["unidades"][pasillo] = cargas["unidades"].get(pasillo, 0) + self._entero(
            caja.get("Unidades", 0), 0
        )

    # ---------------------------------------------------------
    # API principal
    # ---------------------------------------------------------
    def seleccionar(
        self,
        demanda,
        cajas,
        carga_pasillos=None,
        ocupacion_celdas=None,
    ):
        """
        Devuelve:
            seleccion_indices, indice_retorno, motivo
        """
        demanda = self._entero(demanda, 0)
        if carga_pasillos is None:
            carga_pasillos = {}
        if ocupacion_celdas is None:
            ocupacion_celdas = {}

        if demanda <= 0:
            return [], None, "SIN DEMANDA"

        grupos = defaultdict(list)
        for indice, caja in enumerate(cajas):
            unidades = self._entero(caja.get("Unidades", 0), 0)
            if unidades > 0:
                grupos[unidades].append(indice)

        if not grupos:
            return [], None, "SIN CAJAS"

        stock_total = sum(unidades * len(indices) for unidades, indices in grupos.items())
        cargas = self._normalizar_cargas(carga_pasillos)
        # Solo las celdas que contienen cajas candidatas de este SKU pueden
        # limpiarse en esta llamada. Se conserva la ocupacion global completa
        # de esas celdas, incluidas matriculas de otros SKU.
        celdas_candidatas = {
            self._celda(caja)
            for caja in cajas
            if self._celda(caja)
        }
        ocupacion = {
            celda: set(ocupacion_celdas.get(celda, set()))
            for celda in celdas_candidatas
            if ocupacion_celdas.get(celda)
        }

        if stock_total < demanda:
            cantidades = Counter({u: len(indices) for u, indices in grupos.items()})
            seleccion = self._materializar_cantidades(
                cantidades,
                cajas,
                cargas,
                ocupacion,
            )
            return (
                seleccion,
                None,
                "STOCK INSUFICIENTE: SELECCION DE TODO EL STOCK DISPONIBLE",
            )

        # -----------------------------------------------------
        # Seleccion tipo SILO: primero menor numero de cajas.
        #
        # Versiones anteriores daban prioridad absoluta a la combinacion
        # exacta y a la limpieza de celdas. En el caso real analizado eso
        # generaba mas cajas que el SILO: preferia 13+1 antes que 14, o
        # 2+2+2 antes que una caja parcial de 8. Para limpieza debemos
        # evaluar exactas y no exactas juntas, ordenando siempre por cajas.
        # -----------------------------------------------------
        k_min = self._minimo_numero_cajas(demanda, grupos)
        if k_min <= 0:
            return [], None, "SIN SELECCION"

        total_cajas = sum(len(indices) for indices in grupos.values())
        candidatos = self._crear_candidatos_para_cardinalidades(
            demanda=demanda,
            grupos=grupos,
            cajas=cajas,
            cargas=cargas,
            ocupacion=ocupacion,
            cardinalidades=range(k_min, min(k_min + 2, total_cajas) + 1),
            exacta=False,
        )

        if not candidatos:
            cantidades = self._fallback_k_mayores(grupos, k_min)
            seleccion = self._materializar_cantidades(
                cantidades,
                cajas,
                cargas,
                ocupacion,
            )
            total = sum(self._entero(cajas[i].get("Unidades", 0), 0) for i in seleccion)
            retorno = self._elegir_caja_retorno(seleccion, cajas, demanda, total)
            return seleccion, retorno, "FALLBACK MINIMO NUMERO DE CAJAS"

        mejor = min(candidatos, key=lambda candidato: candidato["valor"])

        # Mejora fisica final solo sobre el candidato ganador. Esto mantiene la
        # calidad de V17.25.9 pero evita repetir la busqueda de equivalentes para
        # cada candidato intermedio.
        seleccion_final = self._reequilibrar_equivalentes(
            mejor["seleccion"],
            cajas,
            cargas,
        )
        total_final = sum(self._entero(cajas[i].get("Unidades", 0), 0) for i in seleccion_final)
        retorno_final = None
        if total_final > demanda:
            retorno_final = self._elegir_caja_retorno(seleccion_final, cajas, demanda, total_final)
        celdas_final = self._celdas_limpiadas_globales(seleccion_final, cajas, ocupacion)

        motivo = (
            "SILO-LIMPIEZA | CAJAS "
            + str(len(seleccion_final))
            + " | EXCESO "
            + str(max(0, total_final - demanda))
            + " | CELDAS "
            + str(len(celdas_final))
            + " | MAXIMO UN RETORNO | EQUILIBRIO FUERTE PASILLOS OPT"
        )
        return seleccion_final, retorno_final, motivo

    def _crear_candidatos_para_cardinalidades(
        self,
        demanda,
        grupos,
        cajas,
        cargas,
        ocupacion,
        cardinalidades,
        exacta,
    ):
        candidatos = []
        vistos = set()

        for k in cardinalidades:
            if k <= 0:
                continue

            if exacta:
                objetivo = demanda
            else:
                objetivo = self._menor_total_con_k_cajas(demanda, grupos, k)
                if objetivo is None:
                    continue

            combinaciones = self._generar_candidatos_cantidades(
                objetivo=objetivo,
                cajas_objetivo=k,
                grupos=grupos,
                cajas=cajas,
                ocupacion=ocupacion,
            )

            for cantidades in combinaciones:
                clave = tuple(sorted((int(u), int(n)) for u, n in cantidades.items() if n > 0))
                if clave in vistos:
                    continue
                vistos.add(clave)

                # En la generacion de candidatos no se ejecuta la mejora fisica
                # completa. Ejecutarla aqui para cada combinacion es muy costoso
                # en pedidos grandes. La mejora final se aplica solo al candidato
                # ganador, manteniendo unidades, cajas y retorno.
                seleccion = self._materializar_cantidades(
                    cantidades,
                    cajas,
                    cargas,
                    ocupacion,
                    optimizar_equivalentes=False,
                )
                if len(seleccion) != k:
                    continue

                total = sum(self._entero(cajas[i].get("Unidades", 0), 0) for i in seleccion)
                if exacta and total != demanda:
                    continue
                if not exacta and total < demanda:
                    continue

                retorno = None
                exceso = max(0, total - demanda)
                if exceso > 0:
                    retorno = self._elegir_caja_retorno(seleccion, cajas, demanda, total)
                    if retorno is None:
                        continue

                celdas = self._celdas_limpiadas_globales(seleccion, cajas, ocupacion)
                cajas_en_celdas = sum(
                    1
                    for indice in seleccion
                    if self._celda(cajas[indice]) in celdas
                )
                equilibrio = self._valor_pasillos_con_indices(
                    seleccion,
                    cajas,
                    cargas,
                )
                fisico = self._valor_fisico(seleccion, cajas)

                # Criterio SILO: una caja menos prevalece sobre exactitud y
                # limpieza. La limpieza solo desempata cuando el numero de cajas,
                # la compensacion de pasillos y el retorno son equivalentes.
                valor = (
                    len(seleccion),
                    equilibrio,
                    exceso,
                    -len(celdas),
                    -cajas_en_celdas,
                    fisico,
                    tuple(sorted(self._matricula(cajas[i]) for i in seleccion)),
                )

                candidatos.append({
                    "seleccion": seleccion,
                    "retorno": retorno,
                    "total": total,
                    "exceso": exceso,
                    "celdas": len(celdas),
                    "cajas_en_celdas": cajas_en_celdas,
                    "valor": valor,
                })

        return candidatos

    # ---------------------------------------------------------
    # Exactitud y cardinalidad
    # ---------------------------------------------------------
    def _minimo_numero_cajas_exactas(self, demanda, grupos):
        if demanda <= 0:
            return 0

        unidades_validas = [u for u in grupos if u > 0 and u <= demanda]
        if not unidades_validas:
            return None

        max_cajas = min(
            sum(len(grupos[u]) for u in unidades_validas),
            demanda // min(unidades_validas),
        )
        if max_cajas <= 0:
            return None

        mascara = (1 << (demanda + 1)) - 1
        bits_por_cantidad = [0] * (max_cajas + 1)
        bits_por_cantidad[0] = 1

        for unidades in sorted(unidades_validas, reverse=True):
            restante = min(len(grupos[unidades]), max_cajas)
            potencia = 1
            bloques = []
            while restante > 0:
                toma = min(potencia, restante)
                bloques.append((toma, unidades * toma))
                restante -= toma
                potencia <<= 1

            for toma, suma_bloque in bloques:
                for cantidad in range(max_cajas, toma - 1, -1):
                    anterior = bits_por_cantidad[cantidad - toma]
                    if anterior:
                        bits_por_cantidad[cantidad] |= anterior << suma_bloque
                        bits_por_cantidad[cantidad] &= mascara

        for cantidad in range(1, max_cajas + 1):
            if (bits_por_cantidad[cantidad] >> demanda) & 1:
                return cantidad
        return None

    def _minimo_numero_cajas(self, demanda, grupos):
        acumulado = 0
        numero = 0

        for unidades in sorted(grupos.keys(), reverse=True):
            cantidad = len(grupos[unidades])
            if cantidad <= 0:
                continue

            faltan = demanda - acumulado
            if faltan <= 0:
                break

            necesarias = (faltan + unidades - 1) // unidades
            toma = min(cantidad, necesarias)
            acumulado += unidades * toma
            numero += toma

            if acumulado >= demanda:
                return numero

        return 0

    def _menor_total_con_k_cajas(self, demanda, grupos, k):
        if k <= 0:
            return None

        superior = self._suma_k_mayores(grupos, k)
        if superior < demanda:
            return None

        mascara = (1 << (superior + 1)) - 1
        bits_por_cantidad = [0] * (k + 1)
        bits_por_cantidad[0] = 1

        bloques = []
        for unidades in sorted(grupos.keys(), reverse=True):
            restante = min(len(grupos[unidades]), k)
            potencia = 1
            while restante > 0:
                toma = min(potencia, restante)
                bloques.append((toma, unidades * toma))
                restante -= toma
                potencia <<= 1

        max_cajas_procesadas = 0
        for toma, suma_bloque in bloques:
            limite = min(k, max_cajas_procesadas + toma)
            for cantidad in range(limite, toma - 1, -1):
                anterior = bits_por_cantidad[cantidad - toma]
                if anterior:
                    bits_por_cantidad[cantidad] |= anterior << suma_bloque
                    bits_por_cantidad[cantidad] &= mascara
            max_cajas_procesadas = min(k, max_cajas_procesadas + toma)

        posibles = bits_por_cantidad[k] >> demanda
        if posibles == 0:
            return None

        menor_bit = posibles & -posibles
        exceso = menor_bit.bit_length() - 1
        return demanda + exceso

    def _suma_k_mayores(self, grupos, k):
        faltan = k
        total = 0
        for unidades in sorted(grupos.keys(), reverse=True):
            if faltan <= 0:
                break
            toma = min(faltan, len(grupos[unidades]))
            total += unidades * toma
            faltan -= toma
        return total if faltan == 0 else -1

    # ---------------------------------------------------------
    # Candidatos de cantidades y reconstruccion
    # ---------------------------------------------------------
    def _generar_candidatos_cantidades(
        self,
        objetivo,
        cajas_objetivo,
        grupos,
        cajas,
        ocupacion,
    ):
        resultados = []
        vistos = set()

        def agregar(cantidades):
            if not cantidades:
                return
            clave = tuple(sorted((int(u), int(n)) for u, n in cantidades.items() if n > 0))
            if not clave or clave in vistos:
                return
            vistos.add(clave)
            resultados.append(Counter(dict(clave)))

        base = self._reconstruir_objetivo(
            objetivo=objetivo,
            grupos=grupos,
            cajas_objetivo=cajas_objetivo,
        )
        agregar(base)

        celdas = self._celdas_globalmente_limpiables(cajas, ocupacion)
        semillas = []
        for celda, indices in celdas.items():
            cuenta = Counter(
                self._entero(cajas[indice].get("Unidades", 0), 0)
                for indice in indices
            )
            total = sum(u * n for u, n in cuenta.items())
            numero = sum(cuenta.values())
            if total <= objetivo and numero <= cajas_objetivo:
                semillas.append((celda, indices, cuenta, total, numero))

        semillas.sort(key=lambda item: (item[4], -item[3], item[0]))
        semillas = semillas[:40]

        for _, _, cuenta, total, numero in semillas:
            candidato = self._completar_semilla(
                semilla=cuenta,
                total_semilla=total,
                cajas_semilla=numero,
                objetivo=objetivo,
                cajas_objetivo=cajas_objetivo,
                grupos=grupos,
            )
            agregar(candidato)

        # Combinaciones de dos celdas, limitadas para mantener rendimiento.
        limite_pares = min(len(semillas), 18)
        for i in range(limite_pares):
            for j in range(i + 1, limite_pares):
                cuenta = semillas[i][2] + semillas[j][2]
                total = semillas[i][3] + semillas[j][3]
                numero = semillas[i][4] + semillas[j][4]
                if total > objetivo or numero > cajas_objetivo:
                    continue
                candidato = self._completar_semilla(
                    semilla=cuenta,
                    total_semilla=total,
                    cajas_semilla=numero,
                    objetivo=objetivo,
                    cajas_objetivo=cajas_objetivo,
                    grupos=grupos,
                )
                agregar(candidato)

        return resultados

    def _completar_semilla(
        self,
        semilla,
        total_semilla,
        cajas_semilla,
        objetivo,
        cajas_objetivo,
        grupos,
    ):
        for unidades, cantidad in semilla.items():
            if cantidad > len(grupos.get(unidades, [])):
                return None

        restante_objetivo = objetivo - total_semilla
        restantes_cajas = cajas_objetivo - cajas_semilla
        if restante_objetivo < 0 or restantes_cajas < 0:
            return None
        if restante_objetivo == 0 and restantes_cajas == 0:
            return Counter(semilla)
        if restante_objetivo <= 0 or restantes_cajas <= 0:
            return None

        grupos_restantes = {}
        for unidades, indices in grupos.items():
            disponibles = len(indices) - int(semilla.get(unidades, 0))
            if disponibles > 0:
                grupos_restantes[unidades] = [None] * disponibles

        complemento = self._reconstruir_objetivo(
            objetivo=restante_objetivo,
            grupos=grupos_restantes,
            cajas_objetivo=restantes_cajas,
        )
        if not complemento:
            return None
        return Counter(semilla) + Counter(complemento)

    def _reconstruir_objetivo(self, objetivo, grupos, cajas_objetivo=None):
        unidades = sorted((u for u in grupos if u > 0), reverse=True)
        if not unidades:
            return None

        limites = [len(grupos[u]) for u in unidades]
        n = len(unidades)

        suma_max_sufijo = [0] * (n + 1)
        cajas_sufijo = [0] * (n + 1)
        gcd_sufijo = [0] * (n + 1)
        for pos in range(n - 1, -1, -1):
            suma_max_sufijo[pos] = suma_max_sufijo[pos + 1] + unidades[pos] * limites[pos]
            cajas_sufijo[pos] = cajas_sufijo[pos + 1] + limites[pos]
            gcd_sufijo[pos] = gcd(unidades[pos], gcd_sufijo[pos + 1])

        @lru_cache(maxsize=None)
        def resolver(pos, restante, cajas_restantes):
            if restante == 0:
                if cajas_restantes in (-1, 0):
                    return ()
                return None
            if pos >= n or restante < 0:
                return None
            if restante > suma_max_sufijo[pos]:
                return None
            if gcd_sufijo[pos] and restante % gcd_sufijo[pos] != 0:
                return None

            if cajas_restantes >= 0:
                if cajas_restantes > cajas_sufijo[pos]:
                    return None
                maximo = self._max_suma_con_k_desde(unidades, limites, pos, cajas_restantes)
                minimo = self._min_suma_con_k_desde(unidades, limites, pos, cajas_restantes)
                if maximo < restante or minimo > restante:
                    return None

            unidad = unidades[pos]
            max_toma = min(limites[pos], restante // unidad)
            if cajas_restantes >= 0:
                max_toma = min(max_toma, cajas_restantes)

            for toma in range(max_toma, -1, -1):
                nuevas_cajas = -1 if cajas_restantes < 0 else cajas_restantes - toma
                respuesta = resolver(
                    pos + 1,
                    restante - unidad * toma,
                    nuevas_cajas,
                )
                if respuesta is not None:
                    return (toma,) + respuesta
            return None

        cajas_iniciales = -1 if cajas_objetivo is None else int(cajas_objetivo)
        solucion = resolver(0, int(objetivo), cajas_iniciales)
        if solucion is None:
            return None

        resultado = Counter()
        for unidad, cantidad in zip(unidades, solucion):
            if cantidad:
                resultado[unidad] = cantidad
        return resultado

    def _max_suma_con_k_desde(self, unidades, limites, pos, k):
        faltan = k
        total = 0
        for i in range(pos, len(unidades)):
            if faltan <= 0:
                break
            toma = min(faltan, limites[i])
            total += unidades[i] * toma
            faltan -= toma
        return total if faltan == 0 else -1

    def _min_suma_con_k_desde(self, unidades, limites, pos, k):
        faltan = k
        total = 0
        for i in range(len(unidades) - 1, pos - 1, -1):
            if faltan <= 0:
                break
            toma = min(faltan, limites[i])
            total += unidades[i] * toma
            faltan -= toma
        return total if faltan == 0 else 10**30

    # ---------------------------------------------------------
    # Materializacion fisica y limpieza global
    # ---------------------------------------------------------
    def _celdas_globalmente_limpiables(self, cajas, ocupacion):
        matricula_indice = {
            self._matricula(caja): indice
            for indice, caja in enumerate(cajas)
            if self._matricula(caja)
        }
        resultado = {}
        for celda, matriculas in ocupacion.items():
            if not celda or not matriculas:
                continue
            if all(matricula in matricula_indice for matricula in matriculas):
                resultado[celda] = [matricula_indice[m] for m in sorted(matriculas)]
        return resultado

    def _materializar_cantidades(self, cantidades, cajas, cargas_iniciales, ocupacion, optimizar_equivalentes=True):
        necesarias = Counter({int(u): int(n) for u, n in cantidades.items() if n > 0})
        if not necesarias:
            return []

        seleccion = []
        seleccion_set = set()
        cargas = self._copiar_cargas(cargas_iniciales)

        por_unidades = defaultdict(list)
        for indice, caja in enumerate(cajas):
            unidades = self._entero(caja.get("Unidades", 0), 0)
            if unidades > 0:
                por_unidades[unidades].append(indice)

        celdas_limpiables = self._celdas_globalmente_limpiables(cajas, ocupacion)

        while True:
            mejor = None
            mejor_valor = None

            for celda, indices in celdas_limpiables.items():
                indices_libres = [i for i in indices if i not in seleccion_set]
                if not indices_libres:
                    continue

                cuenta = Counter(
                    self._entero(cajas[i].get("Unidades", 0), 0)
                    for i in indices_libres
                )
                if any(u <= 0 for u in cuenta):
                    continue
                if any(cuenta[u] > necesarias.get(u, 0) for u in cuenta):
                    continue

                equilibrio = self._valor_pasillos_con_indices(
                    indices_libres,
                    cajas,
                    cargas,
                )
                # No forzamos limpieza de celdas a costa de cargar siempre
                # el mismo pasillo. Primero equilibrio; despues la limpieza.
                valor = (
                    equilibrio,
                    len(indices_libres),
                    self._valor_fisico(indices_libres, cajas),
                    celda,
                )
                if mejor_valor is None or valor < mejor_valor:
                    mejor_valor = valor
                    mejor = indices_libres

            if mejor is None:
                break

            for indice in mejor:
                unidad = self._entero(cajas[indice].get("Unidades", 0), 0)
                if necesarias.get(unidad, 0) <= 0:
                    continue
                seleccion.append(indice)
                seleccion_set.add(indice)
                necesarias[unidad] -= 1
                self._sumar_carga(cargas, cajas[indice])

            necesarias += Counter()
            if not necesarias:
                if optimizar_equivalentes:
                    return self._reequilibrar_equivalentes(
                        seleccion,
                        cajas,
                        cargas_iniciales,
                    )
                return seleccion

        for unidad in sorted(necesarias.keys(), reverse=True):
            veces = necesarias[unidad]
            disponibles = [
                i
                for i in por_unidades.get(unidad, [])
                if i not in seleccion_set
            ]

            for _ in range(veces):
                if not disponibles:
                    return []

                mejor_indice = min(
                    disponibles,
                    key=lambda i: self._valor_caja_fisica(
                        i,
                        cajas,
                        seleccion_set,
                        cargas,
                        ocupacion,
                    ),
                )
                seleccion.append(mejor_indice)
                seleccion_set.add(mejor_indice)
                self._sumar_carga(cargas, cajas[mejor_indice])
                disponibles.remove(mejor_indice)

        if optimizar_equivalentes:
            return self._reequilibrar_equivalentes(
                seleccion,
                cajas,
                cargas_iniciales,
            )
        return seleccion

    def _reequilibrar_equivalentes(self, seleccion, cajas, cargas_iniciales):
        """
        Mejora final de seleccion fisica, optimizada para pedidos grandes.

        La combinacion de unidades ya esta decidida. Este paso solo sustituye
        una caja por otra de las mismas unidades para mejorar el equilibrio de
        pasillos sin cambiar unidades, numero de cajas ni retorno.

        En V17.25.9 se evaluaban muchas sustituciones recalculando la seleccion
        completa, lo que hacia lento el calculo con silos grandes. Esta version
        usa una heuristica incremental: intenta mover cajas desde pasillos mas
        cargados hacia pasillos menos cargados cuando existe una caja equivalente.
        """
        if not seleccion:
            return seleccion

        seleccion = list(seleccion)
        seleccion_set = set(seleccion)

        cargas = self._copiar_cargas(cargas_iniciales)
        for indice in seleccion:
            self._sumar_carga(cargas, cajas[indice])

        por_unidades = defaultdict(list)
        for indice, caja in enumerate(cajas):
            unidades = self._entero(caja.get("Unidades", 0), 0)
            if unidades > 0 and indice not in seleccion_set:
                por_unidades[unidades].append(indice)

        # Orden estable de alternativas. Se recalcula parcialmente cuando hay
        # cambios de carga; no se inspeccionan todos los candidatos en cada caja.
        for unidad, indices in por_unidades.items():
            indices.sort(
                key=lambda i: (
                    cargas["cajas"].get(self._pasillo(cajas[i]), 0),
                    cargas["lotes"].get(self._pasillo(cajas[i]), 0),
                    cargas["unidades"].get(self._pasillo(cajas[i]), 0),
                    self._pasillo(cajas[i]),
                    self._celda(cajas[i]),
                    self._matricula(cajas[i]),
                    i,
                )
            )

        def carga_pasillo(pasillo):
            return (
                cargas["cajas"].get(pasillo, 0),
                cargas["lotes"].get(pasillo, 0),
                cargas["unidades"].get(pasillo, 0),
            )

        def restar_carga(indice):
            pasillo = self._pasillo(cajas[indice])
            cargas["cajas"][pasillo] = cargas["cajas"].get(pasillo, 0) - 1
            cargas["lotes"][pasillo] = cargas["lotes"].get(pasillo, 0) - self._peso_lotes(cajas[indice])
            cargas["unidades"][pasillo] = cargas["unidades"].get(pasillo, 0) - self._entero(cajas[indice].get("Unidades", 0), 0)

        def mejora_suficiente(pasillo_origen, pasillo_destino):
            if pasillo_origen == pasillo_destino:
                return False
            carga_origen = carga_pasillo(pasillo_origen)
            carga_destino = carga_pasillo(pasillo_destino)
            # Mover solo si el destino esta claramente menos cargado en cajas o,
            # en empate, en lotes/unidades. Evita sustituciones cosmeticas.
            return carga_destino < carga_origen

        # Trabajamos primero sobre las cajas ubicadas en pasillos mas cargados.
        # Una sola pasada suele bastar; una segunda permite aprovechar cambios
        # producidos por la primera sin coste excesivo.
        max_pasadas = 2
        max_candidatos_por_caja = 24
        max_sustituciones = max(20, len(seleccion) // 2)
        sustituciones = 0

        for _ in range(max_pasadas):
            hubo_mejora = False
            orden_posiciones = sorted(
                range(len(seleccion)),
                key=lambda pos: (
                    -cargas["cajas"].get(self._pasillo(cajas[seleccion[pos]]), 0),
                    -cargas["lotes"].get(self._pasillo(cajas[seleccion[pos]]), 0),
                    -cargas["unidades"].get(self._pasillo(cajas[seleccion[pos]]), 0),
                    self._pasillo(cajas[seleccion[pos]]),
                    self._celda(cajas[seleccion[pos]]),
                    self._matricula(cajas[seleccion[pos]]),
                )
            )

            for posicion in orden_posiciones:
                if sustituciones >= max_sustituciones:
                    return seleccion

                indice_actual = seleccion[posicion]
                unidades = self._entero(cajas[indice_actual].get("Unidades", 0), 0)
                alternativas = por_unidades.get(unidades, [])
                if not alternativas:
                    continue

                pasillo_origen = self._pasillo(cajas[indice_actual])
                mejor = None
                mejor_valor = None

                revisados = 0
                for candidato in alternativas:
                    if candidato in seleccion_set:
                        continue
                    revisados += 1
                    if revisados > max_candidatos_por_caja:
                        break

                    pasillo_destino = self._pasillo(cajas[candidato])
                    if not mejora_suficiente(pasillo_origen, pasillo_destino):
                        continue

                    valor = (
                        carga_pasillo(pasillo_destino),
                        self._pasillo(cajas[candidato]),
                        self._celda(cajas[candidato]),
                        self._matricula(cajas[candidato]),
                        candidato,
                    )
                    if mejor_valor is None or valor < mejor_valor:
                        mejor_valor = valor
                        mejor = candidato

                if mejor is None:
                    continue

                # Aplicar sustitucion incremental.
                restar_carga(indice_actual)
                self._sumar_carga(cargas, cajas[mejor])
                seleccion_set.remove(indice_actual)
                seleccion_set.add(mejor)
                seleccion[posicion] = mejor
                sustituciones += 1
                hubo_mejora = True

            if not hubo_mejora:
                break

        return seleccion

    def _valor_caja_fisica(self, indice, cajas, seleccion_set, cargas, ocupacion):
        caja = cajas[indice]
        celda = self._celda(caja)
        matriculas_celda = set(ocupacion.get(celda, set())) if celda else set()
        matriculas_seleccionadas = {
            self._matricula(cajas[i])
            for i in seleccion_set
            if self._matricula(cajas[i])
        }
        matricula = self._matricula(caja)
        if matricula:
            matriculas_seleccionadas.add(matricula)

        limpia = bool(matriculas_celda) and matriculas_celda.issubset(matriculas_seleccionadas)
        pendientes = len(matriculas_celda - matriculas_seleccionadas)
        equilibrio = self._valor_pasillos_con_indices([indice], cajas, cargas)

        return (
            equilibrio,
            -int(limpia),
            pendientes,
            -self._profundidad(caja),
            self._pasillo(caja),
            celda,
            matricula,
            indice,
        )

    def _celdas_limpiadas_globales(self, seleccion, cajas, ocupacion):
        seleccionadas = {
            self._matricula(cajas[indice])
            for indice in seleccion
            if self._matricula(cajas[indice])
        }
        celdas_tocadas = {
            self._celda(cajas[indice])
            for indice in seleccion
            if self._celda(cajas[indice])
        }
        return {
            celda
            for celda in celdas_tocadas
            if ocupacion.get(celda)
            and set(ocupacion[celda]).issubset(seleccionadas)
        }

    # ---------------------------------------------------------
    # Compensacion compuesta de pasillos
    # ---------------------------------------------------------
    def _coeficiente_variacion(self, valores):
        if not valores:
            return 0.0
        media = sum(valores) / float(len(valores))
        if media <= 0:
            return 0.0
        varianza = sum((valor - media) ** 2 for valor in valores) / float(len(valores))
        return sqrt(varianza) / media

    def _valor_pasillos_con_indices(self, indices, cajas, cargas_actuales):
        cargas = self._copiar_cargas(cargas_actuales)
        pasillos_afectados = []
        cajas_anadidas = Counter()

        for indice in indices:
            pasillo = self._pasillo(cajas[indice])
            pasillos_afectados.append(pasillo)
            cajas_anadidas[pasillo] += 1
            self._sumar_carga(cargas, cajas[indice])

        if not pasillos_afectados:
            pasillos_afectados = [str(numero).zfill(2) for numero in range(1, 11)]

        cargas_cajas_antes = self._copiar_cargas(cargas_actuales).get("cajas", {})
        cargas_afectadas_despues = [
            cargas["cajas"].get(pasillo, 0)
            for pasillo in sorted(set(pasillos_afectados))
        ]
        cargas_afectadas_antes = [
            cargas_cajas_antes.get(pasillo, 0)
            for pasillo in sorted(set(pasillos_afectados))
        ]

        # Bloque fuerte: elegir primero pasillos que ya estan menos cargados.
        # En la comparativa real el pasillo 01 quedaba muy por encima del SILO;
        # por eso se penaliza antes de nada la carga post-seleccion del pasillo
        # tocado y la concentracion de varias cajas en el mismo pasillo.
        max_afectado_post = max(cargas_afectadas_despues) if cargas_afectadas_despues else 0
        suma_afectado_post = sum(cargas_afectadas_despues)
        max_afectado_pre = max(cargas_afectadas_antes) if cargas_afectadas_antes else 0
        max_cajas_mismo_pasillo = max(cajas_anadidas.values()) if cajas_anadidas else 0

        metricas = {}
        cvs = []
        rangos = []
        max_sobres = []
        objetivos = []
        for metrica in ("cajas", "lotes", "unidades"):
            valores = [
                cargas[metrica].get(str(numero).zfill(2), 0)
                for numero in range(1, 11)
            ]
            media = sum(valores) / float(len(valores)) if valores else 0.0
            cv = self._coeficiente_variacion(valores)
            rango = (max(valores) - min(valores)) / max(1.0, media)
            max_sobre = (max(valores) - media) / max(1.0, media)
            exceso_objetivo = sum(
                max(0.0, valor - media) ** 2
                for valor in valores
            ) / max(1.0, media)
            metricas[metrica] = (max_sobre, rango, cv, exceso_objetivo)
            cvs.append(cv)
            rangos.append(rango)
            max_sobres.append(max_sobre)
            objetivos.append(exceso_objetivo)

        combinado = (
            sum(cvs)
            + (sum(rangos) * 0.25)
            + (sum(max_sobres) * 0.75)
            + (sum(objetivos) * 0.50)
        )

        # El primer bloque es deliberadamente por cajas/movimientos. Lotes y
        # unidades son desempates. Esto evita que una limpieza de celda o el
        # orden fisico vuelva a llevar demasiadas cajas al mismo pasillo.
        valores = (
            max_afectado_post,
            suma_afectado_post,
            max_afectado_pre,
            max_cajas_mismo_pasillo,
            metricas["cajas"][0],
            metricas["cajas"][3],
            metricas["cajas"][1],
            metricas["cajas"][2],
            combinado,
            metricas["lotes"][0],
            metricas["lotes"][3],
            metricas["lotes"][1],
            metricas["lotes"][2],
            metricas["unidades"][0],
            metricas["unidades"][3],
            metricas["unidades"][1],
            metricas["unidades"][2],
        )
        return tuple(round(valor, 8) for valor in valores)

    def _valor_fisico(self, seleccion, cajas):
        return (
            -sum(self._profundidad(cajas[i]) for i in seleccion),
            tuple(
                sorted(
                    (
                        -self._profundidad(cajas[i]),
                        self._celda(cajas[i]),
                        self._matricula(cajas[i]),
                    )
                    for i in seleccion
                )
            ),
        )

    # ---------------------------------------------------------
    # Caja de retorno
    # ---------------------------------------------------------
    def _elegir_caja_retorno(self, seleccion, cajas, demanda, total):
        if total <= demanda:
            return None

        candidatos = []
        for indice in seleccion:
            unidades = self._entero(cajas[indice].get("Unidades", 0), 0)
            if total - unidades < demanda:
                candidatos.append(indice)

        if not candidatos:
            return None

        return min(
            candidatos,
            key=lambda i: (
                self._entero(cajas[i].get("Unidades", 0), 0),
                self._pasillo(cajas[i]),
                self._celda(cajas[i]),
                self._matricula(cajas[i]),
            ),
        )

    # ---------------------------------------------------------
    # Fallback y compatibilidad
    # ---------------------------------------------------------
    def _fallback_k_mayores(self, grupos, k):
        resultado = Counter()
        faltan = k
        for unidades in sorted(grupos.keys(), reverse=True):
            if faltan <= 0:
                break
            toma = min(faltan, len(grupos[unidades]))
            if toma:
                resultado[unidades] += toma
                faltan -= toma
        return resultado

    def indices_por_celda(self, cajas):
        por_celda = defaultdict(list)
        for indice, caja in enumerate(cajas):
            por_celda[self._celda(caja)].append(indice)
        return dict(por_celda)

    def contar_celdas_limpiadas(self, cajas, seleccion, ocupacion_celdas=None):
        if ocupacion_celdas is None:
            por_celda = self.indices_por_celda(cajas)
            seleccion_set = set(seleccion)
            return sum(
                1
                for celda, indices in por_celda.items()
                if celda and indices and set(indices).issubset(seleccion_set)
            )
        return len(self._celdas_limpiadas_globales(seleccion, cajas, ocupacion_celdas))
