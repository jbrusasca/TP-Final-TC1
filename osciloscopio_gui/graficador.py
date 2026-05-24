"""
graficador.py
-------------
Módulo que maneja la lógica de graficado con Matplotlib.

Responsabilidades:
- Crear y actualizar la figura con los canales del osciloscopio
- Aplicar escala, desplazamiento y color a cada curva
- Marcar puntos especiales (máximo, mínimo, etc.)
- Cambiar escala del eje X a logarítmica si se solicita
- Gestionar la grilla
- Mostrar/ocultar canales individuales
"""

import matplotlib
matplotlib.use("TkAgg")  # Backend compatible con tkinter

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.ticker as ticker
import numpy as np


# Colores por defecto para hasta 8 canales
COLORES_DEFECTO = [
    "#2196F3",   # azul
    "#F44336",   # rojo
    "#4CAF50",   # verde
    "#FF9800",   # naranja
    "#9C27B0",   # violeta
    "#00BCD4",   # cian
    "#E91E63",   # rosa
    "#8BC34A",   # verde claro
]


class Graficador:
    """
    Encapsula la figura de matplotlib y la integra con el frame de tkinter.

    Uso típico
    ----------
    g = Graficador(frame_tkinter)
    g.actualizar(datos, configuracion)
    """

    def __init__(self, frame_padre):
        """
        Crea la figura embebida en el frame tkinter.

        Parámetros
        ----------
        frame_padre : tk.Frame
            El contenedor tkinter donde se dibujará la figura.
        """
        # Figura y ejes de matplotlib
        self.figura, self.eje = plt.subplots(figsize=(10, 5))
        self.figura.patch.set_facecolor("#1e1e2e")  # fondo oscuro
        self.eje.set_facecolor("#2a2a3e")

        # Canvas de tkinter que renderiza la figura
        self.canvas = FigureCanvasTkAgg(self.figura, master=frame_padre)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Barra de herramientas de matplotlib (zoom, pan, guardar, etc.)
        self.toolbar = NavigationToolbar2Tk(self.canvas, frame_padre)
        self.toolbar.update()

        # Estado interno
        self._lineas = {}          # { nombre_canal: objeto Line2D }
        self._datos_actuales = None
        self._config_actuales = None
        self._cursores = []        # líneas verticales de cursores
        self._anotaciones = []     # anotaciones de puntos marcados

        # Conectar eventos de mouse para cursores
        self._cid_click = self.canvas.mpl_connect("button_press_event", self._on_click)

    # ------------------------------------------------------------------ #
    #  Método principal de actualización                                   #
    # ------------------------------------------------------------------ #

    def actualizar(self, datos: dict, config: dict):
        """
        Redibuja el gráfico con los datos y configuración actuales.

        Parámetros
        ----------
        datos : dict
            Resultado de lector_csv.leer_csv()
        config : dict
            Configuración con las siguientes claves:
              - 'canales_visibles'  : { nombre: bool }
              - 'escala'            : { nombre: float }   (multiplicador)
              - 'offset'            : { nombre: float }   (en unidades de tensión ya escaladas)
              - 'colores'           : { nombre: str }
              - 'grilla'            : bool
              - 'paso_grilla_x'     : float o None
              - 'paso_grilla_y'     : float o None
              - 'eje_x_log'         : bool
              - 'eje_y_log'         : bool
              - 'mostrar_maxmin'    : bool
              - 'modo_xy'           : bool  (figura de Lissajous)
              - 'canal_x_lissajous' : str   (nombre del canal para eje X)
              - 'canal_y_lissajous' : str   (nombre del canal para eje Y)
        """
        self._datos_actuales  = datos
        self._config_actuales = config

        # Limpiar el eje anterior
        self.eje.cla()
        self._lineas = {}
        self._anotaciones = []

        tiempo_raw  = datos["tiempo"]
        canales     = datos["canales"]
        ft          = datos["factor_tiempo"]
        fv          = datos["factor_tension"]
        ut          = datos["unidad_tiempo"]
        uv          = datos["unidad_tension"]
        nombre_arch = datos["nombre_archivo"]

        # Tiempo escalado a la unidad conveniente
        tiempo = [t * ft for t in tiempo_raw]

        # ---- Modo XY (Lissajous) ----
        if config.get("modo_xy", False):
            self._graficar_lissajous(tiempo, canales, config, fv, uv)
            return

        # ---- Modo normal ----
        for i, (nombre, valores_raw) in enumerate(canales.items()):
            # ¿Está habilitado este canal?
            if not config.get("canales_visibles", {}).get(nombre, True):
                continue

            # Aplicar escala y offset
            escala = config.get("escala", {}).get(nombre, 1.0)
            offset = config.get("offset", {}).get(nombre, 0.0)

            # Valores en la unidad conveniente con escala y offset aplicados
            valores = [(v * fv * escala) + offset for v in valores_raw]

            # Color
            color = config.get("colores", {}).get(nombre, COLORES_DEFECTO[i % len(COLORES_DEFECTO)])

            # Graficar
            linea, = self.eje.plot(tiempo, valores, color=color, linewidth=1.2, label=nombre)
            self._lineas[nombre] = linea

            # Marcar máximo y mínimo si se pidió
            if config.get("mostrar_maxmin", False):
                self._marcar_maxmin(tiempo, valores, nombre, color)

        # ---- Etiquetas y estilo ----
        self.eje.set_xlabel(f"Tiempo [{ut}]", color="white", fontsize=11)
        self.eje.set_ylabel(f"Tensión [{uv}]", color="white", fontsize=11)
        self.eje.set_title(f"Osciloscopio — {nombre_arch}", color="white", fontsize=12)
        self.eje.tick_params(colors="white")
        for spine in self.eje.spines.values():
            spine.set_edgecolor("#555577")
        self.eje.legend(facecolor="#2a2a3e", edgecolor="#555577", labelcolor="white")

        # ---- Escala logarítmica ----
        if config.get("eje_x_log", False):
            self.eje.set_xscale("log")
        if config.get("eje_y_log", False):
            self.eje.set_yscale("log")

        # ---- Grilla ----
        if config.get("grilla", True):
            paso_x = config.get("paso_grilla_x")
            paso_y = config.get("paso_grilla_y")
            if paso_x:
                self.eje.xaxis.set_major_locator(ticker.MultipleLocator(paso_x))
            if paso_y:
                self.eje.yaxis.set_major_locator(ticker.MultipleLocator(paso_y))
            self.eje.grid(True, color="#444466", linestyle="--", linewidth=0.6)
        else:
            self.eje.grid(False)

        self.figura.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    #  Modo Lissajous (XY)                                                 #
    # ------------------------------------------------------------------ #

    def _graficar_lissajous(self, tiempo, canales, config, fv, uv):
        """Grafica la figura de Lissajous: canal X vs canal Y."""
        nombres = list(canales.keys())
        if len(nombres) < 2:
            self.eje.text(0.5, 0.5, "Se necesitan al menos 2 canales para Lissajous",
                          ha="center", va="center", color="white", transform=self.eje.transAxes)
            self.canvas.draw()
            return

        nombre_x = config.get("canal_x_lissajous", nombres[0])
        nombre_y = config.get("canal_y_lissajous", nombres[1] if len(nombres) > 1 else nombres[0])

        if nombre_x not in canales or nombre_y not in canales:
            nombre_x, nombre_y = nombres[0], nombres[1]

        datos_x = [v * fv for v in canales[nombre_x]]
        datos_y = [v * fv for v in canales[nombre_y]]

        # Colorear por tiempo (degradado)
        puntos = np.array([datos_x, datos_y]).T.reshape(-1, 1, 2)
        segmentos = np.concatenate([puntos[:-1], puntos[1:]], axis=1)
        from matplotlib.collections import LineCollection
        from matplotlib.cm import plasma
        colores = plasma(np.linspace(0, 1, len(segmentos)))
        lc = LineCollection(segmentos, colors=colores, linewidth=1.2)
        self.eje.add_collection(lc)
        self.eje.autoscale()

        self.eje.set_xlabel(f"{nombre_x} [{uv}]", color="white", fontsize=11)
        self.eje.set_ylabel(f"{nombre_y} [{uv}]", color="white", fontsize=11)
        self.eje.set_title(f"Figura de Lissajous — {nombre_x} vs {nombre_y}", color="white", fontsize=12)
        self.eje.tick_params(colors="white")
        for spine in self.eje.spines.values():
            spine.set_edgecolor("#555577")

        self.figura.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------ #
    #  Marcar máximo y mínimo                                              #
    # ------------------------------------------------------------------ #

    def _marcar_maxmin(self, tiempo, valores, nombre, color):
        """Agrega anotaciones de máximo y mínimo sobre la curva."""
        if not valores:
            return

        idx_max = int(np.argmax(valores))
        idx_min = int(np.argmin(valores))

        for idx, etiqueta, marker in [(idx_max, "MAX", "^"), (idx_min, "MIN", "v")]:
            self.eje.plot(tiempo[idx], valores[idx],
                          marker=marker, markersize=8, color=color, zorder=5)
            self.eje.annotate(
                f"{etiqueta}\n{valores[idx]:.3g}",
                xy=(tiempo[idx], valores[idx]),
                xytext=(10, 10 if etiqueta == "MAX" else -20),
                textcoords="offset points",
                color=color,
                fontsize=8,
                arrowprops=dict(arrowstyle="->", color=color, lw=0.8),
            )

    # ------------------------------------------------------------------ #
    #  Cursores interactivos                                               #
    # ------------------------------------------------------------------ #

    def _on_click(self, evento):
        """
        Maneja el clic del mouse sobre el gráfico para colocar cursores.
        Clic derecho = colocar cursor; si ya hay 2 cursores, los borra.
        """
        if evento.button == 3 and evento.inaxes == self.eje:  # botón derecho
            if len(self._cursores) >= 2:
                # Borrar cursores anteriores
                for linea in self._cursores:
                    linea.remove()
                self._cursores.clear()
                for anotacion in self._anotaciones:
                    try:
                        anotacion.remove()
                    except Exception:
                        pass
                self._anotaciones.clear()

            # Agregar nuevo cursor
            linea = self.eje.axvline(x=evento.xdata, color="#FFFF00",
                                     linewidth=1, linestyle="--", alpha=0.8)
            self._cursores.append(linea)

            # Si hay 2 cursores, mostrar diferencia de tiempo
            if len(self._cursores) == 2:
                x1 = self._cursores[0].get_xdata()[0]
                x2 = self._cursores[1].get_xdata()[0]
                delta = abs(x2 - x1)
                ymax = self.eje.get_ylim()[1]
                anotacion = self.eje.text(
                    (x1 + x2) / 2, ymax * 0.95,
                    f"Δt = {delta:.4g}",
                    color="#FFFF00", ha="center", fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#333355", edgecolor="#FFFF00"),
                )
                self._anotaciones.append(anotacion)

            self.canvas.draw()

    # ------------------------------------------------------------------ #
    #  Guardar figura                                                       #
    # ------------------------------------------------------------------ #

    def guardar_figura(self, ruta: str):
        """Exporta la figura actual como imagen PNG."""
        self.figura.savefig(ruta, dpi=150, bbox_inches="tight",
                            facecolor=self.figura.get_facecolor())