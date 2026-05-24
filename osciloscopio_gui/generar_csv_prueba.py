"""
generar_csv_prueba.py
---------------------
Script auxiliar para generar archivos CSV de prueba con el formato
del osciloscopio, útil para probar la GUI sin tener un osciloscopio.

Ejecutá con:  python generar_csv_prueba.py
Genera:       prueba_4canales.csv  y  prueba_2canales.csv
"""

import math
import os

# Parámetros de la señal de prueba
MUESTRAS    = 500
FRECUENCIA  = 1000    # Hz
AMPLITUD    = 5.0     # Volts
DURACION    = 2e-3    # 2 ms = un par de períodos


def generar(nombre_archivo: str, num_canales: int):
    """
    Genera un CSV de prueba con el formato de osciloscopio.

    Parámetros
    ----------
    nombre_archivo : str
        Nombre del archivo a crear (relativo al directorio actual)
    num_canales : int
        Número de canales de tensión a generar (1 a 4)
    """
    dt = DURACION / MUESTRAS
    t_inicio = -DURACION / 2

    # Encabezados: fila 1 = nombres, fila 2 = unidades
    nombres   = ["x-axis"] + [str(i) for i in range(1, num_canales + 1)]
    unidades  = ["second"] + ["Volt"] * num_canales

    with open(nombre_archivo, "w") as f:
        # Fila de nombres
        f.write(",".join(nombres) + "\n")
        # Fila de unidades
        f.write(",".join(unidades) + "\n")

        # Datos: señales de prueba
        for i in range(MUESTRAS):
            t = t_inicio + i * dt
            fila = [f"{t:.6E}"]

            for canal in range(num_canales):
                # Cada canal tiene una señal diferente
                if canal == 0:
                    # Seno
                    v = AMPLITUD * math.sin(2 * math.pi * FRECUENCIA * t)
                elif canal == 1:
                    # Coseno (cuadratura)
                    v = AMPLITUD * math.cos(2 * math.pi * FRECUENCIA * t)
                elif canal == 2:
                    # Onda cuadrada aproximada (suma de armónicos)
                    v = AMPLITUD * (
                        math.sin(2 * math.pi * FRECUENCIA * t) +
                        (1/3) * math.sin(2 * math.pi * 3 * FRECUENCIA * t)
                    )
                else:
                    # Señal constante + ruido pequeño
                    import random
                    v = 2.5 + random.uniform(-0.1, 0.1)

                fila.append(f"{v:.6E}")

            f.write(",".join(fila) + "\n")

    print(f"Generado: {os.path.abspath(nombre_archivo)}")


if __name__ == "__main__":
    generar("prueba_4canales.csv", num_canales=4)
    generar("prueba_2canales.csv", num_canales=2)
    print("\n¡Listo! Abrí alguno de estos archivos con la GUI para probar.")