"""
lector_csv.py
-------------
Módulo encargado de leer y parsear archivos CSV provenientes de osciloscopios.

El formato esperado es el siguiente (primeras dos filas son encabezados):
    x-axis    1       2       3       4
    second    Volt    Volt    Volt    Volt
    -84.48E-6  0.0   4.70    4.99    5.01
    ...

Las columnas están separadas por comas.
La primera columna es el eje de tiempo, las siguientes son los canales de tensión.
"""

import pandas as pd
import os


# Unidades legibles para mostrar en los ejes
UNIDADES_TIEMPO = {
    1e0:   ("s",  1e0),
    1e-3:  ("ms", 1e3),
    1e-6:  ("µs", 1e6),
    1e-9:  ("ns", 1e9),
}

UNIDADES_TENSION = {
    1e0:   ("V",  1e0),
    1e-3:  ("mV", 1e3),
    1e-6:  ("µV", 1e6),
}


class ErrorCSV(Exception):
    """Excepción personalizada para errores relacionados con el CSV."""
    pass


def leer_csv(ruta_archivo: str) -> dict:
    """
    Lee un archivo CSV de osciloscopio y devuelve los datos procesados.

    Parámetros
    ----------
    ruta_archivo : str
        Ruta absoluta o relativa al archivo .csv

    Retorna
    -------
    dict con las claves:
        - 'tiempo'      : lista de floats con los valores de tiempo
        - 'canales'     : dict { nombre_canal: lista de floats }
        - 'unidad_tiempo': str (ej: 'µs')
        - 'unidad_tension': str (ej: 'V')
        - 'factor_tiempo' : float (para convertir de la unidad nativa)
        - 'factor_tension': float

    Lanza
    -----
    ErrorCSV si el archivo no es un CSV válido de osciloscopio.
    """

    # --- Validación básica de extensión ---
    if not ruta_archivo.lower().endswith(".csv"):
        raise ErrorCSV(f"El archivo '{os.path.basename(ruta_archivo)}' no tiene extensión .csv")

    # --- Lectura del archivo ---
    try:
        # Leer las dos primeras filas como encabezados
        encabezados = pd.read_csv(ruta_archivo, header=None, nrows=2)
    except Exception as e:
        raise ErrorCSV(f"No se pudo leer el archivo como CSV: {e}")

    # --- Validación del formato de osciloscopio ---
    try:
        fila_nombres  = encabezados.iloc[0].tolist()   # ["x-axis", "1", "2", ...]
        fila_unidades = encabezados.iloc[1].tolist()   # ["second", "Volt", "Volt", ...]
    except Exception:
        raise ErrorCSV("El archivo no tiene el formato esperado (mínimo 2 filas de encabezado).")

    # Verificar que la primera columna sea temporal
    nombre_eje_x   = str(fila_nombres[0]).strip().lower()
    unidad_eje_x   = str(fila_unidades[0]).strip().lower()

    if unidad_eje_x not in ("second", "s", "seconds"):
        raise ErrorCSV(
            f"La primera columna debería ser 'second' pero se encontró '{fila_unidades[0]}'.\n"
            "¿Es realmente un CSV de osciloscopio?"
        )

    # --- Leer los datos numéricos (salteando las 2 filas de encabezado) ---
    try:
        datos = pd.read_csv(ruta_archivo, header=None, skiprows=2)
    except Exception as e:
        raise ErrorCSV(f"Error al leer los datos numéricos: {e}")

    if datos.empty:
        raise ErrorCSV("El archivo CSV no contiene datos numéricos.")

    # Convertir todo a float (los valores científicos como 4.70E+00 ya los maneja pandas)
    try:
        datos = datos.apply(pd.to_numeric, errors='coerce')
    except Exception as e:
        raise ErrorCSV(f"Error convirtiendo datos a número: {e}")

    # Remover filas completamente vacías o NaN en la columna de tiempo
    datos.dropna(subset=[0], inplace=True)
    if datos.empty:
        raise ErrorCSV("Después de limpiar los datos no quedan filas válidas.")

    # --- Separar tiempo y canales ---
    tiempo_raw = datos.iloc[:, 0].values.tolist()

    # Nombres de los canales: segunda fila del encabezado, columnas 1 en adelante
    nombres_canales = [str(fila_nombres[i]).strip() for i in range(1, len(fila_nombres))]
    if not nombres_canales or len(nombres_canales) < datos.shape[1] - 1:
        # Si hay más columnas de datos que nombres, generarlos automáticamente
        nombres_canales = [f"Canal {i}" for i in range(1, datos.shape[1])]

    canales = {}
    for idx, nombre in enumerate(nombres_canales, start=1):
        if idx < datos.shape[1]:
            valores = datos.iloc[:, idx].fillna(0).values.tolist()
            canales[nombre] = valores

    # --- Determinar unidades convenientes para el tiempo ---
    rango_tiempo = max(abs(t) for t in tiempo_raw) if tiempo_raw else 1
    unidad_tiempo, factor_tiempo = _elegir_unidad(rango_tiempo, UNIDADES_TIEMPO)

    # --- Determinar unidades convenientes para la tensión ---
    todos_los_valores = [v for canal in canales.values() for v in canal if v is not None]
    rango_tension = max(abs(v) for v in todos_los_valores) if todos_los_valores else 1
    unidad_tension, factor_tension = _elegir_unidad(rango_tension, UNIDADES_TENSION)

    return {
        "tiempo":         tiempo_raw,
        "canales":        canales,
        "unidad_tiempo":  unidad_tiempo,
        "factor_tiempo":  factor_tiempo,
        "unidad_tension": unidad_tension,
        "factor_tension": factor_tension,
        "nombre_archivo": os.path.basename(ruta_archivo),
    }


def _elegir_unidad(valor_max: float, tabla_unidades: dict) -> tuple:
    """
    Elige la unidad más conveniente dado el valor máximo de la señal.

    Ejemplo: si el tiempo máximo es 84e-6, elige µs (factor 1e6).

    Retorna
    -------
    (nombre_unidad: str, factor: float)
    """
    if valor_max == 0:
        return list(tabla_unidades.values())[0]

    # Buscar la unidad cuyo valor escalado quede entre 0.1 y 9999
    mejor_unidad  = list(tabla_unidades.values())[-1][0]
    mejor_factor  = list(tabla_unidades.values())[-1][1]
    mejor_diff    = float('inf')

    for umbral, (nombre, factor) in tabla_unidades.items():
        valor_escalado = valor_max * factor
        if 0.1 <= valor_escalado <= 9999:
            diff = abs(valor_escalado - 100)  # preferimos valores cerca de 100
            if diff < mejor_diff:
                mejor_diff   = diff
                mejor_unidad = nombre
                mejor_factor = factor

    return mejor_unidad, mejor_factor