"""
lector_csv.py
-------------
Módulo encargado de leer y parsear archivos CSV de osciloscopios.

Soporta DOS formatos distintos:

  FORMATO A — Señales en el tiempo (osciloscopio clásico):
    x-axis,1,2,3,4
    second,Volt,Volt,Volt,Volt
    -84.48E-06,0.0,4.70,4.99,5.01
    ...

  FORMATO B — Autobode Keysight:
    #,Frequency (Hz),Amplitude (Vpp),Gain (dB),Phase (°)
    1,3700.0,2.0000,1.52,-5.16
    ...

  FORMATO C — Bode exportado desde LTSpice (separado por tabs):
    Freq.\tV(nodo)
    3.80e+03\t(1.16dB,-4.84°)
    ...

  FORMATO B — Autobode Keysight (original):
    #,Frequency (Hz),Amplitude (Vpp),Gain (dB),Phase (°)
    1,3700.0,2.0000,1.52,-5.16
    ...

El módulo detecta automáticamente cuál de los dos formatos es y devuelve
los datos en una estructura unificada que el graficador puede usar.
"""

import pandas as pd
import os


# Unidades legibles para mostrar en los ejes (formato A)
UNIDADES_TIEMPO = {
    1e0:  ("s",  1e0),
    1e-3: ("ms", 1e3),
    1e-6: ("µs", 1e6),
    1e-9: ("ns", 1e9),
}

UNIDADES_TENSION = {
    1e0:  ("V",  1e0),
    1e-3: ("mV", 1e3),
    1e-6: ("µV", 1e6),
}

# Tipos de formato reconocidos
FORMATO_TIEMPO   = "tiempo"    # señales vs tiempo
FORMATO_AUTOBODE = "autobode"  # ganancia/fase vs frecuencia (Keysight)
FORMATO_LTSPICE  = "ltspice"   # ganancia/fase vs frecuencia exportado desde LTSpice


class ErrorCSV(Exception):
    """Excepción personalizada para errores relacionados con el CSV."""
    pass


# ------------------------------------------------------------------ #
#  Función principal                                                   #
# ------------------------------------------------------------------ #

def leer_csv(ruta_archivo: str) -> dict:
    """
    Lee un archivo CSV de osciloscopio y devuelve los datos procesados.

    Detecta automáticamente si es un CSV de señales en el tiempo (Formato A)
    o un autobode de Keysight (Formato B).

    Parámetros
    ----------
    ruta_archivo : str
        Ruta al archivo .csv

    Retorna
    -------
    dict con las claves comunes:
        - 'formato'        : str  ('tiempo' o 'autobode')
        - 'nombre_archivo' : str

    Para formato 'tiempo' agrega:
        - 'tiempo'         : list[float]
        - 'canales'        : dict { nombre: list[float] }
        - 'unidad_tiempo'  : str  (ej: 'µs')
        - 'factor_tiempo'  : float
        - 'unidad_tension' : str  (ej: 'V')
        - 'factor_tension' : float

    Para formato 'autobode' agrega:
        - 'frecuencia'     : list[float]  (Hz)
        - 'ganancia_db'    : list[float]  (dB)
        - 'fase_deg'       : list[float]  (grados)
        - 'amplitud'       : list[float]  (Vpp, puede ser None)

    Lanza
    -----
    ErrorCSV si el archivo no es válido.
    """

    # --- Validación de extensión ---
    if not ruta_archivo.lower().endswith(".csv"):
        raise ErrorCSV(
            f"El archivo '{os.path.basename(ruta_archivo)}' no tiene extensión .csv"
        )

    # --- Leer las primeras líneas para detectar el formato ---
    try:
        with open(ruta_archivo, "r", encoding="utf-8", errors="replace") as f:
            primera_linea = f.readline().strip()
    except Exception as e:
        raise ErrorCSV(f"No se pudo abrir el archivo: {e}")

    # --- Detectar formato ---
    if _es_bode_ltspice(primera_linea):
        return _leer_bode_ltspice(ruta_archivo)
    elif _es_autobode_keysight(primera_linea):
        return _leer_autobode(ruta_archivo)
    elif _es_formato_tiempo(primera_linea):
        return _leer_tiempo(ruta_archivo)
    else:
        raise ErrorCSV(
            "El archivo no tiene un formato reconocido.\n\n"
            "Formatos soportados:\n"
            "  • Señales de tiempo: primera fila debe contener 'x-axis'\n"
            "  • Autobode Keysight: primera fila debe contener 'Frequency' y 'Gain'\n"
            "  • Bode LTSpice: primera fila debe contener 'Freq.' separado por tab"
        )


# ------------------------------------------------------------------ #
#  Detección de formato                                                #
# ------------------------------------------------------------------ #

def _es_autobode_keysight(primera_linea: str) -> bool:
    """
    Detecta si el CSV es un autobode de Keysight.
    La primera línea contiene encabezados como 'Frequency', 'Gain', 'Phase'.
    """
    linea_lower = primera_linea.lower()
    return "frequency" in linea_lower and ("gain" in linea_lower or "phase" in linea_lower)


def _es_formato_tiempo(primera_linea: str) -> bool:
    """
    Detecta si el CSV es de señales en el tiempo.
    La primera línea comienza con 'x-axis'.
    """
    return primera_linea.lower().startswith("x-axis")


def _es_bode_ltspice(primera_linea: str) -> bool:
    """
    Detecta si el CSV es un bode exportado desde LTSpice.
    La primera línea tiene el formato:  Freq.\tV(nodo)
    separado por TAB, con 'Freq.' como primera columna.
    """
    partes = primera_linea.split("\t")
    if len(partes) < 2:
        return False
    return partes[0].strip().lower().startswith("freq")


# ------------------------------------------------------------------ #
#  Lector Formato A: señales en el tiempo                              #
# ------------------------------------------------------------------ #

def _leer_tiempo(ruta_archivo: str) -> dict:
    """Lee un CSV de señales en el tiempo (formato clásico de osciloscopio)."""

    try:
        encabezados = pd.read_csv(ruta_archivo, header=None, nrows=2)
    except Exception as e:
        raise ErrorCSV(f"No se pudo leer el archivo como CSV: {e}")

    try:
        fila_nombres  = encabezados.iloc[0].tolist()
        fila_unidades = encabezados.iloc[1].tolist()
    except Exception:
        raise ErrorCSV("El archivo no tiene el formato esperado (mínimo 2 filas de encabezado).")

    unidad_eje_x = str(fila_unidades[0]).strip().lower()
    if unidad_eje_x not in ("second", "s", "seconds"):
        raise ErrorCSV(
            f"La primera columna debería ser 'second' pero se encontró '{fila_unidades[0]}'."
        )

    try:
        datos = pd.read_csv(ruta_archivo, header=None, skiprows=2)
        datos = datos.apply(pd.to_numeric, errors='coerce')
        datos.dropna(subset=[0], inplace=True)
    except Exception as e:
        raise ErrorCSV(f"Error al leer los datos numéricos: {e}")

    if datos.empty:
        raise ErrorCSV("El archivo CSV no contiene datos numéricos válidos.")

    tiempo_raw     = datos.iloc[:, 0].values.tolist()
    nombres_canales = [str(fila_nombres[i]).strip() for i in range(1, len(fila_nombres))]
    if len(nombres_canales) < datos.shape[1] - 1:
        nombres_canales = [f"Canal {i}" for i in range(1, datos.shape[1])]

    canales = {}
    for idx, nombre in enumerate(nombres_canales, start=1):
        if idx < datos.shape[1]:
            canales[nombre] = datos.iloc[:, idx].fillna(0).values.tolist()

    rango_tiempo   = max(abs(t) for t in tiempo_raw) if tiempo_raw else 1
    ut, ft         = _elegir_unidad(rango_tiempo, UNIDADES_TIEMPO)

    todos_valores  = [v for canal in canales.values() for v in canal]
    rango_tension  = max(abs(v) for v in todos_valores) if todos_valores else 1
    uv, fv         = _elegir_unidad(rango_tension, UNIDADES_TENSION)

    return {
        "formato":         FORMATO_TIEMPO,
        "tiempo":          tiempo_raw,
        "canales":         canales,
        "unidad_tiempo":   ut,
        "factor_tiempo":   ft,
        "unidad_tension":  uv,
        "factor_tension":  fv,
        "nombre_archivo":  os.path.basename(ruta_archivo),
    }



# ------------------------------------------------------------------ #
#  Lector Formato C: bode LTSpice                                      #
# ------------------------------------------------------------------ #

def _leer_bode_ltspice(ruta_archivo: str) -> dict:
    """
    Lee un CSV de bode exportado desde LTSpice.

    Formato esperado (separado por TAB):
        Freq.\tV(n005)
        3.80e+03\t(1.16dB,-4.84°)
        ...

    Cada fila de datos tiene:
      - columna 0: frecuencia en Hz
      - columna 1: string con ganancia y fase en formato (XdB,Y°)
        donde ° puede ser el símbolo Unicode o el byte \xb0 (latin-1)

    Pueden haber múltiples columnas de señal (varios nodos simulados).
    En ese caso se toman ganancia y fase del primer nodo.
    """
    import re

    frecuencia  = []
    ganancia_db = []
    fase_deg    = []
    nombre_nodo = ""

    # Patrón para extraer ganancia y fase del campo "(XdB,Y°)"
    PATRON = re.compile(
        r"\(\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*dB\s*,\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    )

    try:
        with open(ruta_archivo, "r", encoding="latin-1", errors="replace") as f:
            lineas = f.readlines()
    except Exception as e:
        raise ErrorCSV(f"No se pudo abrir el archivo LTSpice: {e}")

    if not lineas:
        raise ErrorCSV("El archivo está vacío.")

    # --- Encabezado: extraer nombre del nodo ---
    encabezado = lineas[0].strip().split("\t")
    if len(encabezado) >= 2:
        nombre_nodo = encabezado[1].strip()   # ej: "V(n005)"

    # --- Datos ---
    for num_linea, linea in enumerate(lineas[1:], start=2):
        linea = linea.strip()
        if not linea:
            continue

        partes = linea.split("\t")
        if len(partes) < 2:
            continue

        # Frecuencia
        try:
            freq = float(partes[0])
        except ValueError:
            continue

        # Ganancia y fase desde el campo "(XdB,Y°)"
        m = PATRON.search(partes[1])
        if not m:
            continue

        try:
            gan  = float(m.group(1))
            fase = float(m.group(2))
        except ValueError:
            continue

        frecuencia.append(freq)
        ganancia_db.append(gan)
        fase_deg.append(fase)

    if not frecuencia:
        raise ErrorCSV(
            "No se encontraron datos numéricos válidos en el archivo LTSpice.\n"
            "Verificá que el archivo sea un análisis AC exportado desde LTSpice."
        )

    return {
        "formato":         FORMATO_LTSPICE,
        "frecuencia":      frecuencia,
        "ganancia_db":     ganancia_db,
        "fase_deg":        fase_deg,
        "amplitud":        [],
        "nombre_nodo":     nombre_nodo,
        "nombre_archivo":  os.path.basename(ruta_archivo),
    }


# ------------------------------------------------------------------ #
#  Lector Formato B: autobode Keysight                                 #
# ------------------------------------------------------------------ #

def _leer_autobode(ruta_archivo: str) -> dict:
    """
    Lee un CSV de autobode generado por osciloscopios Keysight.

    Formato esperado:
        #, Frequency (Hz), Amplitude (Vpp), Gain (dB), Phase (°)
        1, 3700.0, 2.0000, 1.52, -5.16
        ...
    """
    try:
        datos = pd.read_csv(ruta_archivo, header=0,
                            encoding="utf-8", encoding_errors="replace")
    except Exception as e:
        raise ErrorCSV(f"No se pudo leer el autobode: {e}")

    if datos.empty:
        raise ErrorCSV("El archivo de autobode no contiene datos.")

    # Normalizar nombres de columnas: minúsculas y sin espacios extra
    datos.columns = [str(c).strip().lower() for c in datos.columns]

    # --- Buscar columna de frecuencia ---
    col_freq = _buscar_columna(datos, ["frequency", "freq", "hz", "frecuencia"])
    if col_freq is None:
        raise ErrorCSV("No se encontró la columna de Frecuencia en el autobode.")

    # --- Buscar columna de ganancia ---
    col_gain = _buscar_columna(datos, ["gain", "ganancia", "db"])
    if col_gain is None:
        raise ErrorCSV("No se encontró la columna de Ganancia (dB) en el autobode.")

    # --- Buscar columna de fase (puede no estar) ---
    col_fase = _buscar_columna(datos, ["phase", "fase", "°", "deg"])

    # --- Buscar columna de amplitud (puede no estar) ---
    col_amp = _buscar_columna(datos, ["amplitude", "amplitud", "vpp"])

    # Convertir a numérico
    frecuencia  = pd.to_numeric(datos[col_freq],  errors="coerce").dropna().tolist()
    ganancia_db = pd.to_numeric(datos[col_gain],  errors="coerce").tolist()
    fase_deg    = pd.to_numeric(datos[col_fase],  errors="coerce").tolist() if col_fase else []
    amplitud    = pd.to_numeric(datos[col_amp],   errors="coerce").tolist() if col_amp  else []

    if not frecuencia:
        raise ErrorCSV("La columna de frecuencia no contiene datos numéricos válidos.")

    return {
        "formato":         FORMATO_AUTOBODE,
        "frecuencia":      frecuencia,
        "ganancia_db":     ganancia_db,
        "fase_deg":        fase_deg,
        "amplitud":        amplitud,
        "nombre_archivo":  os.path.basename(ruta_archivo),
    }


def _buscar_columna(df: pd.DataFrame, palabras_clave: list) -> str | None:
    """
    Busca la primera columna cuyo nombre contenga alguna de las palabras clave.
    Retorna el nombre de la columna o None si no se encuentra.
    """
    for col in df.columns:
        for palabra in palabras_clave:
            if palabra in col:
                return col
    return None


# ------------------------------------------------------------------ #
#  Utilidad: elegir unidad conveniente                                 #
# ------------------------------------------------------------------ #

def _elegir_unidad(valor_max: float, tabla_unidades: dict) -> tuple:
    """
    Elige la unidad más conveniente dado el valor máximo de la señal.
    Retorna (nombre_unidad: str, factor: float)
    """
    if valor_max == 0:
        primera = list(tabla_unidades.values())[0]
        return primera[0], primera[1]

    mejor_nombre = list(tabla_unidades.values())[-1][0]
    mejor_factor = list(tabla_unidades.values())[-1][1]
    mejor_diff   = float('inf')

    for umbral, (nombre, factor) in tabla_unidades.items():
        valor_escalado = valor_max * factor
        if 0.1 <= valor_escalado <= 9999:
            diff = abs(valor_escalado - 100)
            if diff < mejor_diff:
                mejor_diff   = diff
                mejor_nombre = nombre
                mejor_factor = factor

    return mejor_nombre, mejor_factor