from collections import Counter, defaultdict


class AlgoritmoMasUnidades:
    """
    Seleccion de cajas para el modo MAS UNIDADES.

    Reglas inferidas del estudio real de SILO (septiembre de 2026):

    1. Cubrir la demanda con el menor numero posible de cajas.
    2. Para ese numero minimo, conservar el multiconjunto de tamanos de las
       cajas de mayor contenido (TOP-K). No se minimiza el exceso.
    3. Todas las cajas se consumen completas salvo, como maximo, una caja de
       retorno.
    4. Entre matriculas equivalentes por cantidad, equilibrar el numero de
       movimientos por pasillo.
    5. Dentro de pasillos con la misma carga, favorecer el vaciado de celdas,
       especialmente las celdas dobles.
    6. Si no se vacia la celda, priorizar la profundidad 01 y despues el orden
       fisico de la posicion.

    La seleccion es determinista: con la misma demanda, stock, ocupacion y
    carga por pasillos siempre devuelve las mismas matriculas.
    """

    PASILLOS_ESTANDAR = tuple(str(i).zfill(2) for i in range(1, 11))
    MAX_CANDIDATOS_POR_PASILLO = 60


    def __init__(self):
        self.ultimo_diagnostico = {}

    # ------------------------------------------------------------------
    # Lecturas seguras
    # ------------------------------------------------------------------
    def _entero(self, valor, defecto=0):
        try:
            return int(round(float(valor or 0)))
        except Exception:
            return defecto

    def _texto(self, valor):
        if valor is None:
            return ""
        return str(valor).strip()

    def _unidades(self, caja):
        return max(0, self._entero(caja.get("Unidades"), 0))

    def _matricula(self, caja):
        return self._texto(caja.get("Matricula"))

    def _pasillo(self, caja):
        return self._texto(caja.get("Pasillo")) or "(SIN PASILLO)"

    def _celda(self, caja):
        return self._texto(caja.get("Celda") or caja.get("Posicion"))

    def _profundidad(self, caja):
        return self._texto(caja.get("Profundidad"))

    def _posicion(self, caja):
        return self._texto(caja.get("Posicion"))

    def _prioridad_profundidad(self, caja):
        """Profundidad 01 primero; despues el resto en orden numerico/texto."""
        profundidad = self._profundidad(caja)
        if profundidad in ("1", "01"):
            return (0, 1)
        try:
            return (1, int(float(profundidad)))
        except Exception:
            return (2, profundidad)

    def _clave_preorden_fisico(self, cajas, indice):
        caja = cajas[indice]
        return (
            self._prioridad_profundidad(caja),
            self._celda(caja),
            self._posicion(caja),
            self._matricula(caja),
            indice,
        )

    def _pasillo_estandar(self, pasillo):
        return pasillo in self.PASILLOS_ESTANDAR

    # ------------------------------------------------------------------
    # Numero minimo y cuotas TOP-K
    # ------------------------------------------------------------------
    def _calcular_top_k(self, demanda, cajas, indices_candidatos):
        orden = sorted(
            indices_candidatos,
            key=lambda indice: (
                -self._unidades(cajas[indice]),
                self._posicion(cajas[indice]),
                self._matricula(cajas[indice]),
                indice,
            ),
        )

        acumulado = 0
        top_k = []
        for indice in orden:
            top_k.append(indice)
            acumulado += self._unidades(cajas[indice])
            if acumulado >= demanda:
                break

        stock_suficiente = acumulado >= demanda
        if not stock_suficiente:
            top_k = orden

        cuotas = Counter(self._unidades(cajas[indice]) for indice in top_k)
        return top_k, cuotas, stock_suficiente

    # ------------------------------------------------------------------
    # Ocupacion y limpieza de celdas
    # ------------------------------------------------------------------
    def _normalizar_ocupacion(self, ocupacion_celdas, celdas_relevantes=None):
        """
        Normaliza solo las celdas del SKU que se esta calculando.

        La ocupacion global puede contener decenas de miles de celdas; copiarla
        completa para cada SKU penalizaba de forma innecesaria el rendimiento.
        """
        fuente = ocupacion_celdas or {}
        if celdas_relevantes is None:
            elementos = fuente.items()
        else:
            elementos = (
                (celda, fuente.get(celda, set()))
                for celda in celdas_relevantes
            )

        normalizada = {}
        for celda, matriculas in elementos:
            clave = self._texto(celda)
            if not clave:
                continue
            valores = {
                self._texto(matricula)
                for matricula in (matriculas or set())
                if self._texto(matricula)
            }
            if valores:
                normalizada[clave] = valores
        return normalizada

    def _celda_limpia_al_elegir(
        self,
        caja,
        seleccionadas,
        ocupacion_celdas,
    ):
        celda = self._celda(caja)
        matricula = self._matricula(caja)
        ocupantes = ocupacion_celdas.get(celda, set())
        if not celda or not matricula or not ocupantes:
            return False
        return ocupantes.issubset(seleccionadas | {matricula})

    def _celda_completable(
        self,
        caja,
        seleccionadas,
        cuotas_restantes,
        matricula_a_indice,
        cajas,
        ocupacion_celdas,
    ):
        """
        Indica si, despues de elegir la caja candidata, todas las cajas que
        queden en su celda podrian seleccionarse respetando las cuotas TOP-K.

        No obliga a completar la celda; se usa como desempate suave.
        """
        celda = self._celda(caja)
        matricula = self._matricula(caja)
        ocupantes = ocupacion_celdas.get(celda, set())
        if not celda or not matricula or len(ocupantes) <= 1:
            return False

        restantes = Counter(cuotas_restantes)
        unidades_candidata = self._unidades(caja)
        restantes[unidades_candidata] -= 1
        if restantes[unidades_candidata] < 0:
            return False

        necesidades = Counter()
        for ocupante in ocupantes:
            if ocupante == matricula or ocupante in seleccionadas:
                continue
            indice = matricula_a_indice.get(ocupante)
            if indice is None:
                return False
            necesidades[self._unidades(cajas[indice])] += 1

        return all(
            necesidades[unidades] <= restantes[unidades]
            for unidades in necesidades
        )

    def _calcular_celdas_limpiadas(
        self,
        cajas,
        seleccion,
        ocupacion_celdas,
    ):
        matriculas = {
            self._matricula(cajas[indice])
            for indice in seleccion
            if self._matricula(cajas[indice])
        }
        celdas = {
            celda
            for celda, ocupantes in ocupacion_celdas.items()
            if ocupantes and ocupantes.issubset(matriculas)
        }
        cajas_en_celdas = sum(len(ocupacion_celdas[celda]) for celda in celdas)
        return celdas, cajas_en_celdas

    # ------------------------------------------------------------------
    # Seleccion fisica de matriculas para las cuotas TOP-K
    # ------------------------------------------------------------------
    def _seleccionar_por_cuotas(
        self,
        cajas,
        indices_candidatos,
        cuotas,
        carga_pasillos,
        ocupacion_celdas,
    ):
        """Materializa las cuotas TOP-K con una heuristica fisica rapida.

        La version anterior revisaba demasiadas matriculas equivalentes en
        cada movimiento. Esta variante conserva la prioridad funcional de
        MAS_UNIDADES, pero preordena los candidatos por cantidad/pasillo y
        limita la evaluacion dinamica a los primeros candidatos utiles de los
        pasillos menos cargados.
        """
        carga = defaultdict(int)
        for pasillo, valor in (carga_pasillos or {}).items():
            carga[self._texto(pasillo)] = max(0, self._entero(valor, 0))
        for pasillo in self.PASILLOS_ESTANDAR:
            carga[pasillo] += 0

        candidatos_por_unidades_pasillo = defaultdict(lambda: defaultdict(list))
        matricula_a_indice = {}
        for indice in indices_candidatos:
            caja = cajas[indice]
            unidades = self._unidades(caja)
            if unidades not in cuotas:
                continue
            pasillo = self._pasillo(caja)
            candidatos_por_unidades_pasillo[unidades][pasillo].append(indice)
            matricula = self._matricula(caja)
            if matricula:
                matricula_a_indice[matricula] = indice

        for unidades, por_pasillo in candidatos_por_unidades_pasillo.items():
            for pasillo, indices in por_pasillo.items():
                indices.sort(key=lambda indice: self._clave_preorden_fisico(cajas, indice))

        punteros = defaultdict(int)
        seleccion = []
        seleccion_set = set()
        seleccionadas = set()
        cuotas_restantes = Counter(cuotas)

        def candidatos_disponibles(unidades, pasillo):
            lista = candidatos_por_unidades_pasillo.get(unidades, {}).get(pasillo, [])
            clave = (unidades, pasillo)
            pos = int(punteros.get(clave, 0))
            while pos < len(lista) and lista[pos] in seleccion_set:
                pos += 1
            punteros[clave] = pos

            salida = []
            j = pos
            while j < len(lista) and len(salida) < self.MAX_CANDIDATOS_POR_PASILLO:
                indice = lista[j]
                if indice not in seleccion_set:
                    salida.append(indice)
                j += 1
            return salida

        # Las cantidades se procesan de mayor a menor. Esto mantiene visible y
        # auditable la regla TOP-K y hace que la caja de retorno tienda a ser la
        # ultima (normalmente una de las menores del conjunto seleccionado).
        for unidades in sorted(cuotas.keys(), reverse=True):
            cantidad = cuotas[unidades]

            for _ in range(cantidad):
                por_pasillo = candidatos_por_unidades_pasillo.get(unidades, {})
                pasillos_con_stock = [
                    pasillo
                    for pasillo in por_pasillo.keys()
                    if candidatos_disponibles(unidades, pasillo)
                ]
                if not pasillos_con_stock:
                    raise Exception(
                        "No se pudieron materializar las cuotas TOP-K de MAS UNIDADES. "
                        "Cantidad pendiente: " + str(unidades)
                    )

                estandar = [
                    pasillo
                    for pasillo in pasillos_con_stock
                    if self._pasillo_estandar(pasillo)
                ]
                pasillos_valorables = estandar or pasillos_con_stock
                carga_minima = min(carga[pasillo] for pasillo in pasillos_valorables)
                pasillos_elegibles = {
                    pasillo
                    for pasillo in pasillos_valorables
                    if carga[pasillo] == carga_minima
                }

                mejor_indice = None
                mejor_valor = None

                for pasillo in sorted(pasillos_elegibles):
                    for indice in candidatos_disponibles(unidades, pasillo):
                        caja = cajas[indice]
                        matricula = self._matricula(caja)
                        celda = self._celda(caja)
                        ocupantes = ocupacion_celdas.get(celda, set())

                        limpia_ahora = self._celda_limpia_al_elegir(
                            caja,
                            seleccionadas,
                            ocupacion_celdas,
                        )
                        limpia_doble = limpia_ahora and len(ocupantes) >= 2
                        completable = self._celda_completable(
                            caja,
                            seleccionadas,
                            cuotas_restantes,
                            matricula_a_indice,
                            cajas,
                            ocupacion_celdas,
                        )

                        valor = (
                            0 if limpia_doble else 1,
                            self._prioridad_profundidad(caja),
                            0 if limpia_ahora else 1,
                            0 if completable else 1,
                            celda,
                            self._posicion(caja),
                            matricula,
                            indice,
                        )

                        if mejor_valor is None or valor < mejor_valor:
                            mejor_valor = valor
                            mejor_indice = indice

                if mejor_indice is None:
                    raise Exception(
                        "No se encontro una matricula valida para la cuota TOP-K "
                        + str(unidades)
                    )

                caja = cajas[mejor_indice]
                pasillo = self._pasillo(caja)
                seleccion.append(mejor_indice)
                seleccion_set.add(mejor_indice)
                seleccionadas.add(self._matricula(caja))
                cuotas_restantes[unidades] -= 1
                carga[pasillo] += 1

        return seleccion, dict(carga)

    # ------------------------------------------------------------------
    # Retorno unico
    # ------------------------------------------------------------------
    def _determinar_retorno(self, demanda, cajas, seleccion):
        total = sum(self._unidades(cajas[indice]) for indice in seleccion)
        if total <= demanda:
            return None

        # Recorremos al reves: la seleccion se construye de mayor a menor y SILO
        # suele dejar como retorno la ultima caja necesaria (normalmente una de
        # las menores del TOP-K). Todas las anteriores quedan completas.
        for indice in reversed(seleccion):
            if total - self._unidades(cajas[indice]) < demanda:
                return indice

        # No deberia ocurrir si K es realmente minimo, pero se conserva una
        # salvaguarda determinista.
        return seleccion[-1] if seleccion else None

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def seleccionar_con_diagnostico(
        self,
        demanda,
        cajas,
        carga_pasillos=None,
        ocupacion_celdas=None,
    ):
        demanda = max(0, self._entero(demanda, 0))

        diagnostico = {
            "indices": [],
            "retorno": None,
            "k_minimo": 0,
            "unidades": 0,
            "exceso": 0,
            "celdas_limpiadas": 0,
            "cajas_en_celdas_limpiadas": 0,
            "stock_suficiente": False,
            "tamanos_top_k": [],
            "carga_pasillos_final": dict(carga_pasillos or {}),
            "motivo": "SIN DEMANDA",
        }

        if demanda <= 0:
            self.ultimo_diagnostico = diagnostico
            return diagnostico

        indices_candidatos = [
            indice
            for indice, caja in enumerate(cajas)
            if self._unidades(caja) > 0
        ]
        if not indices_candidatos:
            diagnostico["motivo"] = "SIN CAJAS"
            self.ultimo_diagnostico = diagnostico
            return diagnostico

        celdas_relevantes = {
            self._celda(cajas[indice])
            for indice in indices_candidatos
            if self._celda(cajas[indice])
        }
        ocupacion = self._normalizar_ocupacion(
            ocupacion_celdas,
            celdas_relevantes,
        )

        top_k, cuotas, stock_suficiente = self._calcular_top_k(
            demanda,
            cajas,
            indices_candidatos,
        )

        seleccion, carga_final = self._seleccionar_por_cuotas(
            cajas,
            indices_candidatos,
            cuotas,
            carga_pasillos or {},
            ocupacion,
        )

        total = sum(self._unidades(cajas[indice]) for indice in seleccion)
        retorno = self._determinar_retorno(demanda, cajas, seleccion)
        celdas, cajas_en_celdas = self._calcular_celdas_limpiadas(
            cajas,
            seleccion,
            ocupacion,
        )

        exceso = max(0, total - demanda)
        if not stock_suficiente:
            estado = "STOCK INSUFICIENTE"
        elif exceso == 0:
            estado = "COBERTURA EXACTA"
        else:
            estado = "UN RETORNO"

        motivo = (
            "TOP-K MAYORES"
            + " | K " + str(len(seleccion))
            + " | " + estado
            + " | EXCESO " + str(exceso)
            + " | CELDAS " + str(len(celdas))
            + " | CAJAS_CELDA " + str(cajas_en_celdas)
            + " | BALANCE CAJAS/PASILLO"
            + " | PROFUNDIDAD 01"
        )

        diagnostico.update({
            "indices": seleccion,
            "retorno": retorno,
            "k_minimo": len(top_k),
            "unidades": total,
            "exceso": exceso,
            "celdas_limpiadas": len(celdas),
            "cajas_en_celdas_limpiadas": cajas_en_celdas,
            "stock_suficiente": stock_suficiente,
            "tamanos_top_k": sorted(
                [self._unidades(cajas[indice]) for indice in top_k],
                reverse=True,
            ),
            "carga_pasillos_final": carga_final,
            "motivo": motivo,
        })

        self.ultimo_diagnostico = diagnostico
        return diagnostico

    def seleccionar(
        self,
        demanda,
        cajas,
        carga_pasillos=None,
        ocupacion_celdas=None,
    ):
        diagnostico = self.seleccionar_con_diagnostico(
            demanda=demanda,
            cajas=cajas,
            carga_pasillos=carga_pasillos,
            ocupacion_celdas=ocupacion_celdas,
        )
        return diagnostico["indices"], diagnostico["retorno"]
