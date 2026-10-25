import math


class AlgoritmoXDOC:
    """
    XDOC V17 - comportamiento aproximado al estudio real de SILO.

    Reglas principales:
    - Se trabaja por Tienda + Aparte + SKU.
    - La seleccion se repite sobre la demanda pendiente hasta que ya no existe
      otro lote valido.
    - Nunca se supera la demanda pendiente.
    - La tolerancia XDOC se aplica completa por debajo de la moda.
    - Por encima de la moda se limita siempre a un maximo del 20%.
      Ejemplo: moda 14 y tolerancia 40 acepta cajas de 9 a 16 unidades.
    - Prioridad de cada lote: proximidad a la moda, limpieza fisica de celda,
      numero de cajas, equilibrio de pasillos y despues profundidad/posicion
      (V2.2: el pasillo va antes del desempate fisico).
    """

    def __init__(self):
        pass

    def _entero(self, valor, defecto=0):
        try:
            return int(round(float(valor)))
        except Exception:
            return defecto

    def _peso_pasillo(self, caja):
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

    def calcular_rango(self, moda, tolerancia_xdoc=0):
        """
        Calcula la ventana XDOC alrededor de la moda.

        Regla V17.25.12:
        - tolerancia 0  -> solo cajas iguales a la moda.
        - tolerancia 40 -> por debajo mantiene 60%, pero por encima
          se limita a 120% de la moda.

        La limitacion final de no superar la demanda pendiente de
        Tienda + Aparte + SKU se aplica despues, en _seleccionar_lote.
        """
        moda = self._entero(moda, 0)
        tolerancia = max(0, min(100, self._entero(tolerancia_xdoc, 0)))

        if moda <= 0:
            return 0, 0

        porcentaje_minimo = 100 - tolerancia
        # La tolerancia por encima de la moda no puede superar el 20%.
        # Evita que una tienda parametrizada con tolerancias amplias acepte
        # cajas demasiado grandes como XDOC; la demanda pendiente sigue
        # actuando como limite final en _seleccionar_lote.
        tolerancia_superior = min(tolerancia, 20)
        porcentaje_maximo = 100 + tolerancia_superior
        minimo = max(1, int(math.ceil((moda * porcentaje_minimo) / 100.0)))
        maximo = max(moda, int(math.floor((moda * porcentaje_maximo) / 100.0)))
        return minimo, maximo

    def seleccionar(
        self,
        demanda,
        cajas,
        moda,
        carga_pasillos=None,
        tolerancia_xdoc=0,
        ocupacion_celdas=None,
    ):
        """API compatible con versiones anteriores."""
        return self.seleccionar_con_diagnostico(
            demanda=demanda,
            cajas=cajas,
            moda=moda,
            carga_pasillos=carga_pasillos,
            tolerancia_xdoc=tolerancia_xdoc,
            ocupacion_celdas=ocupacion_celdas,
        )["indices"]

    def seleccionar_con_diagnostico(
        self,
        demanda,
        cajas,
        moda,
        carga_pasillos=None,
        tolerancia_xdoc=0,
        ocupacion_celdas=None,
    ):
        demanda = self._entero(demanda, 0)
        moda = self._entero(moda, 0)

        if carga_pasillos is None:
            carga_pasillos = {}
        if ocupacion_celdas is None:
            ocupacion_celdas = {}

        resultado_vacio = {
            "indices": [],
            "unidades": 0,
            "iteraciones": 0,
            "desviacion_moda": 0,
            "celdas_limpiadas": 0,
            "cajas_en_celdas_limpiadas": 0,
            "demanda_pendiente": max(0, demanda),
        }

        if demanda <= 0 or moda <= 0 or not cajas:
            return resultado_vacio

        minimo, maximo = self.calcular_rango(moda, tolerancia_xdoc)
        if minimo <= 0 or maximo <= 0:
            return resultado_vacio

        disponibles = set(range(len(cajas)))
        seleccion_total = []
        demanda_pendiente = demanda
        iteraciones = 0
        desviacion_total = 0

        cargas = {
            str(clave): self._entero(valor, 0)
            for clave, valor in dict(carga_pasillos).items()
            if not isinstance(valor, dict)
        }
        for numero in range(1, 11):
            cargas.setdefault(str(numero).zfill(2), 0)

        # Copiar las decenas de miles de celdas del silo para cada
        # Tienda+Aparte+SKU era prohibitivo. Solo las celdas tocadas por las
        # cajas candidatas pueden quedar limpias en esta llamada; aun asi se
        # conserva la ocupacion COMPLETA de esas celdas para detectar cajas de
        # otros SKU.
        celdas_candidatas = {
            self._celda(caja)
            for caja in cajas
            if self._celda(caja)
        }
        ocupacion_inicial = {
            celda: set(ocupacion_celdas.get(celda, set()))
            for celda in celdas_candidatas
            if ocupacion_celdas.get(celda)
        }
        ocupacion_local = {
            celda: set(matriculas)
            for celda, matriculas in ocupacion_inicial.items()
        }

        while demanda_pendiente > 0 and disponibles:
            lote = self._seleccionar_lote(
                demanda=demanda_pendiente,
                cajas=cajas,
                disponibles=disponibles,
                moda=moda,
                minimo=minimo,
                maximo=maximo,
                carga_pasillos=cargas,
                ocupacion_celdas=ocupacion_local,
            )

            if not lote:
                break

            unidades_lote = sum(
                self._entero(cajas[indice].get("Unidades", 0), 0)
                for indice in lote
            )
            if unidades_lote <= 0 or unidades_lote > demanda_pendiente:
                break

            objetivo_lote = min(demanda_pendiente, moda)
            desviacion_total += abs(objetivo_lote - unidades_lote)
            iteraciones += 1

            for indice in lote:
                if indice not in disponibles:
                    continue
                seleccion_total.append(indice)
                disponibles.remove(indice)

                caja = cajas[indice]
                pasillo = self._pasillo(caja)
                cargas[pasillo] = cargas.get(pasillo, 0) + self._peso_pasillo(caja)

                celda = self._celda(caja)
                matricula = self._matricula(caja)
                if celda in ocupacion_local and matricula:
                    ocupacion_local[celda].discard(matricula)
                    if not ocupacion_local[celda]:
                        del ocupacion_local[celda]

            demanda_pendiente -= unidades_lote

        matriculas_seleccionadas = {
            self._matricula(cajas[indice])
            for indice in seleccion_total
            if self._matricula(cajas[indice])
        }
        celdas_tocadas = {
            self._celda(cajas[indice])
            for indice in seleccion_total
            if self._celda(cajas[indice])
        }
        celdas_limpiadas = {
            celda
            for celda in celdas_tocadas
            if ocupacion_inicial.get(celda)
            and ocupacion_inicial[celda].issubset(matriculas_seleccionadas)
        }
        cajas_en_celdas = sum(
            1
            for indice in seleccion_total
            if self._celda(cajas[indice]) in celdas_limpiadas
        )

        return {
            "indices": seleccion_total,
            "unidades": demanda - demanda_pendiente,
            "iteraciones": iteraciones,
            "desviacion_moda": desviacion_total,
            "celdas_limpiadas": len(celdas_limpiadas),
            "cajas_en_celdas_limpiadas": cajas_en_celdas,
            "demanda_pendiente": demanda_pendiente,
        }

    def _seleccionar_lote(
        self,
        demanda,
        cajas,
        disponibles,
        moda,
        minimo,
        maximo,
        carga_pasillos,
        ocupacion_celdas,
    ):
        candidatos = []
        for indice in sorted(disponibles):
            caja = cajas[indice]
            unidades = self._entero(caja.get("Unidades", 0), 0)
            if unidades <= 0:
                continue
            if unidades < minimo or unidades > maximo:
                continue
            if unidades > demanda:
                continue
            candidatos.append((indice, caja))

        if not candidatos:
            return []

        objetivo = min(demanda, moda)

        if len(candidatos) <= 120 and demanda <= 30000:
            seleccion = self._seleccionar_por_dp(
                candidatos,
                objetivo,
                demanda,
                cajas,
                carga_pasillos,
                ocupacion_celdas,
            )
            if seleccion:
                return seleccion

        limite = 600 if len(candidatos) > 600 else len(candidatos)
        candidatos_ordenados = sorted(
            candidatos,
            key=lambda item: self._valor_seleccion(
                [item[0]],
                objetivo,
                cajas,
                carga_pasillos,
                ocupacion_celdas,
            ),
        )[:limite]

        return self._seleccionar_greedy(
            candidatos_ordenados,
            objetivo,
            demanda,
            cajas,
            carga_pasillos,
            ocupacion_celdas,
        )

    def _seleccionar_por_dp(
        self,
        candidatos,
        objetivo,
        demanda,
        cajas,
        carga_pasillos,
        ocupacion_celdas,
    ):
        estados = {0: []}

        for indice, caja in candidatos:
            unidades = self._entero(caja.get("Unidades", 0), 0)
            if unidades <= 0:
                continue

            nuevos = {}
            for suma, seleccion in list(estados.items()):
                nueva_suma = suma + unidades
                if nueva_suma > demanda:
                    continue

                nueva_seleccion = seleccion + [indice]
                actual = nuevos.get(nueva_suma, estados.get(nueva_suma))
                if actual is None:
                    nuevos[nueva_suma] = nueva_seleccion
                else:
                    valor_nuevo = self._valor_seleccion(
                        nueva_seleccion,
                        objetivo,
                        cajas,
                        carga_pasillos,
                        ocupacion_celdas,
                    )
                    valor_actual = self._valor_seleccion(
                        actual,
                        objetivo,
                        cajas,
                        carga_pasillos,
                        ocupacion_celdas,
                    )
                    if valor_nuevo < valor_actual:
                        nuevos[nueva_suma] = nueva_seleccion

            estados.update(nuevos)

        mejor = []
        mejor_valor = None
        for suma, seleccion in estados.items():
            if suma <= 0:
                continue
            valor = self._valor_seleccion(
                seleccion,
                objetivo,
                cajas,
                carga_pasillos,
                ocupacion_celdas,
            )
            if mejor_valor is None or valor < mejor_valor:
                mejor_valor = valor
                mejor = seleccion

        return mejor

    def _seleccionar_greedy(
        self,
        candidatos,
        objetivo,
        demanda,
        cajas,
        carga_pasillos,
        ocupacion_celdas,
    ):
        seleccion = []
        total = 0
        pendientes = list(candidatos)

        while pendientes:
            mejor_indice = None
            mejor_valor = None

            for indice, caja in pendientes:
                unidades = self._entero(caja.get("Unidades", 0), 0)
                if unidades <= 0 or total + unidades > demanda:
                    continue

                prueba = seleccion + [indice]
                valor = self._valor_seleccion(
                    prueba,
                    objetivo,
                    cajas,
                    carga_pasillos,
                    ocupacion_celdas,
                )
                if mejor_valor is None or valor < mejor_valor:
                    mejor_valor = valor
                    mejor_indice = indice

            if mejor_indice is None:
                break

            if seleccion:
                valor_actual = self._valor_seleccion(
                    seleccion,
                    objetivo,
                    cajas,
                    carga_pasillos,
                    ocupacion_celdas,
                )
                if mejor_valor >= valor_actual:
                    break

            seleccion.append(mejor_indice)
            total += self._entero(cajas[mejor_indice].get("Unidades", 0), 0)
            pendientes = [
                (indice, caja)
                for indice, caja in pendientes
                if indice != mejor_indice
            ]

            if total == objetivo:
                break

        return seleccion

    def _valor_seleccion(
        self,
        seleccion,
        objetivo,
        cajas,
        carga_pasillos,
        ocupacion_celdas,
    ):
        total = sum(
            self._entero(cajas[indice].get("Unidades", 0), 0)
            for indice in seleccion
        )
        celdas = self._celdas_limpiadas(
            seleccion,
            cajas,
            ocupacion_celdas,
        )
        cajas_en_celdas = sum(
            1
            for indice in seleccion
            if self._celda(cajas[indice]) in celdas
        )

        # V2.2: el equilibrio de pasillos va antes del desempate fisico. Antes
        # el desempate por nombre de celda decidia siempre a favor del
        # pasillo 01 (103 de 277 cajas XDOC en la comparativa real).
        return (
            abs(objetivo - total),
            -total,
            -len(celdas),
            -cajas_en_celdas,
            len(seleccion),
            self._valor_pasillo_suave(seleccion, cajas, carga_pasillos),
            self._valor_fisico(seleccion, cajas),
            tuple(sorted(self._matricula(cajas[indice]) for indice in seleccion)),
        )

    def _celdas_limpiadas(self, seleccion, cajas, ocupacion_celdas):
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
            if ocupacion_celdas.get(celda)
            and set(ocupacion_celdas[celda]).issubset(seleccionadas)
        }

    def _valor_fisico(self, seleccion, cajas):
        profundidades = [self._profundidad(cajas[indice]) for indice in seleccion]
        detalle = tuple(
            sorted(
                (
                    -self._profundidad(cajas[indice]),
                    self._celda(cajas[indice]),
                    str(cajas[indice].get("Posicion", "") or ""),
                    self._matricula(cajas[indice]),
                )
                for indice in seleccion
            )
        )
        return (-sum(profundidades), detalle)

    def _valor_pasillo_suave(self, seleccion, cajas, carga_pasillos):
        cargas = {
            str(numero).zfill(2): self._entero(
                carga_pasillos.get(str(numero).zfill(2), 0),
                0,
            )
            for numero in range(1, 11)
        }
        for clave, valor in carga_pasillos.items():
            if not isinstance(valor, dict):
                cargas.setdefault(str(clave), self._entero(valor, 0))

        for indice in seleccion:
            caja = cajas[indice]
            pasillo = self._pasillo(caja)
            cargas[pasillo] = cargas.get(pasillo, 0) + self._peso_pasillo(caja)

        valores = list(cargas.values())
        if not valores:
            return (0, 0)
        return (max(valores) - min(valores), max(valores))
