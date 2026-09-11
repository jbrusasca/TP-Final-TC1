"""
graficador.py
-------------
Módulo que maneja la lógica de graficado con Matplotlib.

Soporta tres formatos según datos['formato']:
  FORMATO_TIEMPO   → señales de tensión vs tiempo
  FORMATO_AUTOBODE → Bode Keysight (Ganancia dB + Fase)
  FORMATO_LTSPICE  → Bode LTSpice  (Ganancia dB + Fase)

Sistema de cursores
-------------------
Hay 4 cursores disponibles: CX1, CX2 (verticales) y CY1, CY2 (horizontales).
- Clic izquierdo en el gráfico: coloca el cursor activo en esa posición.
- Drag (mantener apretado y mover): arrastra el cursor activo.
- El cursor activo se selecciona desde el panel lateral de la GUI.
- Para cada cursor vertical se puede elegir a qué canal pertenece;
  el punto de intersección (X, Y interpolado) se muestra en el panel.
- Δx = |CX2 - CX1|,  Δy = |CY2 - CY1| (o vs 0 si solo hay uno).
- La GUI recibe las actualizaciones a través del callback on_cursor_update.
"""

import matplotlib
matplotlib.use("TkAgg")

# Texto vectorial en las exportaciones (TrueType embebido en el PDF y texto
# real en el SVG) para que los informes no pierdan resolución.
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"]  = 42
matplotlib.rcParams["svg.fonttype"] = "none"

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.ticker as ticker
import numpy as np

from lector_csv import FORMATO_TIEMPO, FORMATO_AUTOBODE, FORMATO_LTSPICE


# ------------------------------------------------------------------ #
#  Paleta del gráfico (tema claro, pensado para informes impresos)     #
# ------------------------------------------------------------------ #
COLOR_FONDO_FIG = "#ffffff"   # fondo de la figura completa
COLOR_FONDO_EJE = "#ffffff"   # fondo del área de ploteo (y de la leyenda)
COLOR_TEXTO     = "#1a1a1a"   # títulos, ejes, ticks y etiquetas
COLOR_BORDE     = "#555555"   # bordes (spines) y borde de la leyenda
COLOR_GRILLA    = "#c0c0c0"   # líneas de grilla y referencias auxiliares

COLORES_DEFECTO = [
    "#2196F3",  # azul
    "#F44336",  # rojo
    "#4CAF50",  # verde
    "#FF9800",  # naranja
    "#9C27B0",  # violeta
    "#00BCD4",  # cian
    "#E91E63",  # rosa
    "#8BC34A",  # verde claro
]

# Colores fijos para cada cursor
_COLOR_CX = {1: "#C99700", 2: "#E8590C"}   # CX1 ámbar, CX2 naranja
_COLOR_CY = {1: "#00897B", 2: "#D6336C"}   # CY1 verde azulado, CY2 magenta


class Graficador:
    """
    Encapsula la figura de matplotlib integrada en un frame de tkinter.
    Provee cursores interactivos con drag, interpolación de señal y
    cálculo de deltas.
    """

    def __init__(self, frame_padre):
        self.figura, self.eje = plt.subplots(figsize=(10, 5))
        self.figura.patch.set_facecolor(COLOR_FONDO_FIG)
        self.eje.set_facecolor(COLOR_FONDO_EJE)

        self.canvas = FigureCanvasTkAgg(self.figura, master=frame_padre)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.toolbar = NavigationToolbar2Tk(self.canvas, frame_padre)
        self.toolbar.update()

        # ---- Estado de cursores ----
        # Posición actual de cada cursor (None = no colocado)
        self._pos_cx = {1: None, 2: None}   # posición X (unidades del eje)
        self._pos_cy = {1: None, 2: None}   # posición Y (unidades del eje)

        # Canal asignado a cada cursor X (nombre de canal o None)
        self._canal_cx = {1: None, 2: None}

        # Objetos matplotlib de las líneas de cursor
        self._linea_cx = {1: None, 2: None}
        self._linea_cy = {1: None, 2: None}
        # Marcadores de intersección (punto sobre la curva)
        self._marker_cx = {1: None, 2: None}
        # Textos de etiqueta de cursor — se rastrean para poder borrarlos al mover
        self._texto_cx = {1: None, 2: None}
        self._texto_cy = {1: None, 2: None}

        # Qué cursor está activo para el próximo clic/drag
        # Formato: ("cx", 1), ("cx", 2), ("cy", 1), ("cy", 2), o None
        self._cursor_activo = None

        # Callback que la GUI registra para recibir actualizaciones
        # Firma: fn(info: dict)
        self.on_cursor_update = None

        # Datos actuales (para interpolación)
        self._datos = None
        self._config = None

        # Eje secundario (twinx) usado en los diagramas de Bode para la
        # fase. Los eventos de mouse pueden llegar con evento.inaxes
        # apuntando a este eje en vez de al principal, así que hay que
        # tenerlo en cuenta al procesar clics/drag de cursores.
        self._eje_secundario = None

        # Estado del drag
        self._dragging = False
        self._drag_start_x = None
        self._drag_start_y = None

        # Conectar eventos de mouse
        self.canvas.mpl_connect("button_press_event",   self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event",  self._on_motion)

    # ================================================================== #
    #  API pública                                                         #
    # ================================================================== #

    def _aplicar_titulo(self, config: dict):
        """
        Pone (o saca) el título del gráfico según lo que haya elegido el usuario.

        config['titulo']         → texto escrito en la GUI ("" = sin título)
        config['mostrar_titulo'] → False oculta el título sin borrar el texto

        Ya no se usa el nombre del archivo como título automático: si el campo
        está vacío el gráfico sale sin título, que es lo cómodo para pegarlo en
        un informe donde el epígrafe va aparte.
        """
        if not config.get("mostrar_titulo", True):
            self.eje.set_title("")
            return
        titulo = str(config.get("titulo") or "").strip()
        self.eje.set_title(titulo, color=COLOR_TEXTO, fontsize=12)

    def _etiqueta(self, config: dict, nombre: str) -> str:
        """
        Nombre con el que se muestra una curva en la leyenda.
        Si el usuario le puso un nombre propio se usa ese; si no, el nombre
        original del canal.
        """
        etiqueta = str(config.get("etiquetas", {}).get(nombre, "") or "").strip()
        return etiqueta or nombre

    def set_cursor_activo(self, tipo: str, numero: int):
        """
        Indica qué cursor recibirá el próximo clic/drag.
        tipo   : 'cx' o 'cy'
        numero : 1 o 2
        Si tipo es None, desactiva los cursores.
        """
        if tipo is None:
            self._cursor_activo = None
        else:
            self._cursor_activo = (tipo, numero)

    def set_canal_cursor(self, numero: int, nombre_canal: str):
        """
        Asigna un canal a un cursor X para la interpolación de Y.
        numero       : 1 o 2
        nombre_canal : nombre del canal (ej: '1', '2') o None
        """
        self._canal_cx[numero] = nombre_canal
        self._actualizar_marcadores()
        self._notificar()
        self.canvas.draw_idle()

    def limpiar_cursores(self):
        """Elimina todos los cursores del gráfico."""
        for n in (1, 2):
            # Borrar línea CX
            for obj in (self._linea_cx[n], self._texto_cx[n], self._marker_cx[n]):
                if obj is not None:
                    try: obj.remove()
                    except Exception: pass
            self._linea_cx[n]  = None
            self._texto_cx[n]  = None
            self._marker_cx[n] = None
            self._pos_cx[n]    = None
            # Borrar línea CY
            for obj in (self._linea_cy[n], self._texto_cy[n]):
                if obj is not None:
                    try: obj.remove()
                    except Exception: pass
            self._linea_cy[n]  = None
            self._texto_cy[n]  = None
            self._pos_cy[n]    = None
        self._notificar()
        self.canvas.draw_idle()

    # ================================================================== #
    #  Actualización principal del gráfico                                #
    # ================================================================== #

    def actualizar(self, datos: dict, config: dict):
        """
        Redibuja el gráfico completo.

        Si config['lista_archivos'] tiene más de un elemento, entra en modo
        superposición y grafica todos los archivos visibles en el mismo eje.
        Si solo hay uno (o lista_archivos está vacía), comportamiento normal.
        """
        self.eje.cla()
        for n in (1, 2):
            self._linea_cx[n] = None
            self._linea_cy[n] = None
            self._marker_cx[n] = None
            self._texto_cx[n]  = None
            self._texto_cy[n]  = None
        self._eje_secundario = None

        self._datos  = datos
        self._config = config

        lista = config.get("lista_archivos", [])

        if len(lista) > 1:
            # ---- Modo superposición ----
            formato = datos.get("formato", FORMATO_TIEMPO)
            if formato in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
                self._graficar_bode_superpuesto(lista, config)
            else:
                self._graficar_tiempo_superpuesto(lista, config)
        else:
            # ---- Modo normal (un solo archivo) ----
            formato = datos.get("formato", FORMATO_TIEMPO)
            if formato in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
                self._graficar_bode(datos, config)
            else:
                self._graficar_tiempo(datos, config)

        self._redibujar_cursores()


    # ================================================================== #
    #  Modo superposición                                                  #
    # ================================================================== #

    def _graficar_bode_superpuesto(self, lista: list, config: dict):
        """
        Grafica múltiples Bodes en el mismo eje.
        Cada item de lista tiene: datos, visible, color, etiqueta.
        - Ganancia: todas en el eje izquierdo (línea sólida)
        - Fase: todas en el eje derecho (línea punteada)
        """
        for ax in self.figura.get_axes():
            if ax is not self.eje:
                ax.remove()

        COLOR_EJES = COLOR_TEXTO
        usar_log_x = config.get("eje_x_log", True)

        # Curvas activadas desde el panel (por ejemplo, se puede sacar la fase)
        ver_ganancia = config.get("canales_visibles", {}).get("ganancia", True)
        ver_fase     = config.get("canales_visibles", {}).get("fase", True)

        eje_fase   = None
        hay_fase   = ver_fase and any(item["datos"].get("fase_deg")
                                      for item in lista if item["visible"])

        if hay_fase:
            eje_fase = self.eje.twinx()
            eje_fase.set_facecolor(COLOR_FONDO_EJE)
            eje_fase.set_ylabel("Fase [°]", color=COLOR_EJES, fontsize=11)
            eje_fase.tick_params(axis="y", colors=COLOR_EJES, labelcolor=COLOR_EJES)
            for spine in eje_fase.spines.values():
                spine.set_edgecolor(COLOR_BORDE)
            self._eje_secundario = eje_fase

        for item in lista:
            if not item["visible"]:
                continue
            datos      = item["datos"]
            color      = item["color"]
            etiqueta   = item["etiqueta"]
            frecuencia = datos["frecuencia"]
            ganancia   = datos["ganancia_db"]
            fase       = datos.get("fase_deg", [])
            # La etiqueta es editable desde el panel, así que se usa tal cual
            label_g    = etiqueta

            # Escala y offset por archivo (útil para ajustar referencias)
            escala_file = item.get("escala", 1.0)
            offset_file = item.get("offset", 0.0)
            ganancia_adj = [g * escala_file + offset_file for g in ganancia]

            if ver_ganancia:
                self.eje.plot(frecuencia, ganancia_adj,
                              color=color, linewidth=1.8, label=label_g)

            if fase and eje_fase:
                eje_fase.plot(frecuencia, fase,
                              color=color, linewidth=1.2, linestyle="--",
                              alpha=0.7, label=f"{etiqueta} fase")

        # Estilo eje izquierdo (ganancia)
        self.eje.set_xlabel("Frecuencia [Hz]", color=COLOR_EJES, fontsize=11)
        self.eje.set_ylabel("Ganancia [dB]",   color=COLOR_EJES, fontsize=11)
        self.eje.tick_params(axis="y", colors=COLOR_EJES, labelcolor=COLOR_EJES)
        self.eje.tick_params(axis="x", colors=COLOR_EJES, labelcolor=COLOR_EJES)
        for spine in self.eje.spines.values():
            spine.set_edgecolor(COLOR_BORDE)
        self.eje.axhline(0, color=COLOR_EJES, linewidth=0.6, linestyle="--", alpha=0.5)

        # Escala X
        self.eje.set_xscale("log" if usar_log_x else "linear")
        if eje_fase:
            eje_fase.set_xscale("log" if usar_log_x else "linear")
            for ref in [0, -90, -180]:
                eje_fase.axhline(ref, color=COLOR_GRILLA, linewidth=0.6,
                                 linestyle=":", alpha=0.9)

        if config.get("grilla", True):
            self.eje.grid(True, which="both", color=COLOR_GRILLA,
                          linestyle="--", linewidth=0.6)

        self._aplicar_titulo(config)

        # Leyenda combinada
        l1, lb1 = self.eje.get_legend_handles_labels()
        l2, lb2 = eje_fase.get_legend_handles_labels() if eje_fase else ([], [])
        if l1 or l2:
            self.eje.legend(l1 + l2, lb1 + lb2,
                            facecolor=COLOR_FONDO_EJE, edgecolor=COLOR_BORDE,
                            labelcolor=COLOR_EJES, fontsize=8)

        self.figura.tight_layout()
        self.canvas.draw()

    def _graficar_tiempo_superpuesto(self, lista: list, config: dict):
        """
        Grafica múltiples señales de tiempo en el mismo eje.
        Cada canal de cada archivo se grafica con el color del archivo,
        diferenciando canales por intensidad/estilo de línea.
        """
        for ax in self.figura.get_axes():
            if ax is not self.eje:
                ax.remove()

        estilos = ["-", "--", "-.", ":"]

        for item in lista:
            if not item["visible"]:
                continue
            datos    = item["datos"]
            color    = item["color"]
            etiqueta = item["etiqueta"]
            ft       = datos["factor_tiempo"]
            fv       = datos["factor_tension"]
            tiempo   = [t * ft for t in datos["tiempo"]]
            # Escala y offset por archivo (configurados en el panel de superposición)
            escala_file = item.get("escala", 1.0)
            offset_file = item.get("offset", 0.0)

            for j, (nombre, valores_raw) in enumerate(datos["canales"].items()):
                valores = [v * fv * escala_file + offset_file for v in valores_raw]
                estilo  = estilos[j % len(estilos)]
                label   = f"{etiqueta} — {nombre}"
                self.eje.plot(tiempo, valores, color=color,
                              linewidth=1.2, linestyle=estilo, label=label)

        ut = datos["unidad_tiempo"] if lista else "s"
        uv = datos["unidad_tension"] if lista else "V"
        self.eje.set_xlabel(f"Tiempo [{ut}]",  color=COLOR_TEXTO, fontsize=11)
        self.eje.set_ylabel(f"Tensión [{uv}]", color=COLOR_TEXTO, fontsize=11)
        self._aplicar_titulo(config)
        self.eje.tick_params(colors=COLOR_TEXTO)
        for spine in self.eje.spines.values():
            spine.set_edgecolor(COLOR_BORDE)
        if self.eje.get_legend_handles_labels()[0]:
            self.eje.legend(facecolor=COLOR_FONDO_EJE, edgecolor=COLOR_BORDE,
                            labelcolor=COLOR_TEXTO, fontsize=8)

        if config.get("grilla", True):
            self.eje.grid(True, color=COLOR_GRILLA, linestyle="--", linewidth=0.6)

        self.figura.tight_layout()
        self.canvas.draw()

    # ================================================================== #
    #  Gráfico de Bode                                                     #
    # ================================================================== #

    def _graficar_bode(self, datos: dict, config: dict):
        frecuencia  = datos["frecuencia"]
        ganancia_db = datos["ganancia_db"]
        fase_deg    = datos["fase_deg"]
        nombre_nodo = datos.get("nombre_nodo", "")

        for ax in self.figura.get_axes():
            if ax is not self.eje:
                ax.remove()

        color_gan  = config.get("colores", {}).get("ganancia", COLORES_DEFECTO[0])
        color_fase = config.get("colores", {}).get("fase", COLORES_DEFECTO[1])
        COLOR_EJES = COLOR_TEXTO

        # Curvas activadas desde el panel (por ejemplo, se puede sacar la fase)
        ver_ganancia = config.get("canales_visibles", {}).get("ganancia", True)
        ver_fase     = config.get("canales_visibles", {}).get("fase", True)

        # Nombre de la curva: el que haya puesto el usuario, o el automático
        label_gan = self._etiqueta(config, "ganancia")
        if label_gan == "ganancia":
            label_gan = f"Ganancia — {nombre_nodo}" if nombre_nodo else "Ganancia (dB)"
        if ver_ganancia:
            self.eje.plot(frecuencia, ganancia_db,
                          color=color_gan, linewidth=1.8, label=label_gan)
        self.eje.set_xlabel("Frecuencia [Hz]", color=COLOR_EJES, fontsize=11)
        self.eje.set_ylabel("Ganancia [dB]",   color=COLOR_EJES, fontsize=11)
        self.eje.tick_params(axis="y", colors=COLOR_EJES, labelcolor=COLOR_EJES)
        self.eje.tick_params(axis="x", colors=COLOR_EJES, labelcolor=COLOR_EJES)
        for spine in self.eje.spines.values():
            spine.set_edgecolor(COLOR_BORDE)
        self.eje.axhline(0, color=COLOR_EJES, linewidth=0.6, linestyle="--", alpha=0.5)

        if config.get("mostrar_maxmin", False) and ganancia_db and ver_ganancia:
            for idx_fn, etiqueta, marker in [
                (int(np.argmax(ganancia_db)), "MAX", "^"),
                (int(np.argmin(ganancia_db)), "MIN", "v"),
            ]:
                self.eje.plot(frecuencia[idx_fn], ganancia_db[idx_fn],
                              marker, color=color_gan, markersize=8, zorder=5)
                self.eje.annotate(
                    f"{etiqueta}\n{ganancia_db[idx_fn]:.2f} dB\n@ {frecuencia[idx_fn]:.0f} Hz",
                    xy=(frecuencia[idx_fn], ganancia_db[idx_fn]),
                    xytext=(10, 10 if etiqueta == "MAX" else -30),
                    textcoords="offset points",
                    color=color_gan, fontsize=8,
                    arrowprops=dict(arrowstyle="->", color=color_gan, lw=0.8),
                )

        label_fase = self._etiqueta(config, "fase")
        if label_fase == "fase":
            label_fase = "Fase (°)"

        eje_fase = None
        if fase_deg and ver_fase:
            eje_fase = self.eje.twinx()
            eje_fase.set_facecolor(COLOR_FONDO_EJE)
            eje_fase.plot(frecuencia, fase_deg,
                          color=color_fase, linewidth=1.4,
                          linestyle="--", label=label_fase)
            eje_fase.set_ylabel("Fase [°]", color=COLOR_EJES, fontsize=11)
            eje_fase.tick_params(axis="y", colors=COLOR_EJES, labelcolor=COLOR_EJES)
            for spine in eje_fase.spines.values():
                spine.set_edgecolor(COLOR_BORDE)
            for ref in [0, -90, -180]:
                eje_fase.axhline(ref, color=color_fase, linewidth=0.6,
                                 linestyle=":", alpha=0.5)
            self._eje_secundario = eje_fase

        usar_log_x = config.get("eje_x_log", True)
        self.eje.set_xscale("log" if usar_log_x else "linear")
        if eje_fase:
            eje_fase.set_xscale("log" if usar_log_x else "linear")

        if config.get("grilla", True):
            self.eje.grid(True, which="both", color=COLOR_GRILLA,
                          linestyle="--", linewidth=0.6)

        self._aplicar_titulo(config)

        lineas1, labels1 = self.eje.get_legend_handles_labels()
        lineas2, labels2 = eje_fase.get_legend_handles_labels() if eje_fase else ([], [])
        if lineas1 or lineas2:
            self.eje.legend(lineas1 + lineas2, labels1 + labels2,
                            facecolor=COLOR_FONDO_EJE, edgecolor=COLOR_BORDE,
                            labelcolor=COLOR_EJES)

        self.figura.tight_layout()
        self.canvas.draw()

    # ================================================================== #
    #  Gráfico de señales en el tiempo                                    #
    # ================================================================== #

    def _graficar_tiempo(self, datos: dict, config: dict):
        for ax in self.figura.get_axes():
            if ax is not self.eje:
                ax.remove()

        tiempo_raw  = datos["tiempo"]
        canales     = datos["canales"]
        ft          = datos["factor_tiempo"]
        fv          = datos["factor_tension"]
        ut          = datos["unidad_tiempo"]
        uv          = datos["unidad_tension"]

        tiempo = [t * ft for t in tiempo_raw]

        if config.get("modo_xy", False):
            self._graficar_lissajous(tiempo, canales, config, fv, uv)
            return

        for i, (nombre, valores_raw) in enumerate(canales.items()):
            if not config.get("canales_visibles", {}).get(nombre, True):
                continue
            escala  = config.get("escala", {}).get(nombre, 1.0)
            offset  = config.get("offset", {}).get(nombre, 0.0)
            valores = [(v * fv * escala) + offset for v in valores_raw]
            color   = config.get("colores", {}).get(nombre, COLORES_DEFECTO[i % len(COLORES_DEFECTO)])
            # Nombre editable de la curva (por defecto, el del canal)
            self.eje.plot(tiempo, valores, color=color, linewidth=1.2,
                          label=self._etiqueta(config, nombre))

            if config.get("mostrar_maxmin", False):
                self._marcar_maxmin(tiempo, valores, nombre, color)

        self.eje.set_xlabel(f"Tiempo [{ut}]",  color=COLOR_TEXTO, fontsize=11)
        self.eje.set_ylabel(f"Tensión [{uv}]", color=COLOR_TEXTO, fontsize=11)
        self._aplicar_titulo(config)
        self.eje.tick_params(colors=COLOR_TEXTO)
        for spine in self.eje.spines.values():
            spine.set_edgecolor(COLOR_BORDE)
        if self.eje.get_legend_handles_labels()[0]:
            self.eje.legend(facecolor=COLOR_FONDO_EJE, edgecolor=COLOR_BORDE,
                            labelcolor=COLOR_TEXTO)

        if config.get("eje_x_log", False):
            self.eje.set_xscale("log")
        if config.get("eje_y_log", False):
            self.eje.set_yscale("log")

        self.figura.tight_layout()

        if config.get("grilla", True):
            self.eje.xaxis.set_major_locator(ticker.AutoLocator())
            self.eje.yaxis.set_major_locator(ticker.AutoLocator())
            self.eje.grid(True, color=COLOR_GRILLA, linestyle="--", linewidth=0.6)
        else:
            self.eje.xaxis.set_major_locator(ticker.AutoLocator())
            self.eje.yaxis.set_major_locator(ticker.AutoLocator())
            self.eje.grid(False)

        self.canvas.draw()

    # ================================================================== #
    #  Lissajous                                                           #
    # ================================================================== #

    def _graficar_lissajous(self, tiempo, canales, config, fv, uv):
        nombres = list(canales.keys())
        if len(nombres) < 2:
            self.eje.text(0.5, 0.5, "Se necesitan al menos 2 canales para Lissajous",
                          ha="center", va="center", color=COLOR_TEXTO,
                          transform=self.eje.transAxes)
            self.canvas.draw()
            return
        nombre_x = config.get("canal_x_lissajous", nombres[0])
        nombre_y = config.get("canal_y_lissajous", nombres[1] if len(nombres) > 1 else nombres[0])
        if nombre_x not in canales or nombre_y not in canales:
            nombre_x, nombre_y = nombres[0], nombres[1]
        datos_x = [v * fv for v in canales[nombre_x]]
        datos_y = [v * fv for v in canales[nombre_y]]
        puntos    = np.array([datos_x, datos_y]).T.reshape(-1, 1, 2)
        segmentos = np.concatenate([puntos[:-1], puntos[1:]], axis=1)
        from matplotlib.collections import LineCollection
        # Se recorta el tramo final del colormap (amarillo claro) porque sobre
        # el fondo blanco casi no se ve.
        lc = LineCollection(segmentos, colors=plt.cm.plasma(np.linspace(0, 0.85, len(segmentos))),
                            linewidth=1.2)
        self.eje.add_collection(lc)
        self.eje.autoscale()
        self.eje.set_xlabel(f"{self._etiqueta(config, nombre_x)} [{uv}]",
                            color=COLOR_TEXTO, fontsize=11)
        self.eje.set_ylabel(f"{self._etiqueta(config, nombre_y)} [{uv}]",
                            color=COLOR_TEXTO, fontsize=11)
        self._aplicar_titulo(config)
        self.eje.tick_params(colors=COLOR_TEXTO)
        for spine in self.eje.spines.values():
            spine.set_edgecolor(COLOR_BORDE)
        self.figura.tight_layout()
        self.canvas.draw()

    # ================================================================== #
    #  Máx / Mín                                                           #
    # ================================================================== #

    def _marcar_maxmin(self, tiempo, valores, nombre, color):
        if not valores:
            return
        for idx_fn, etiqueta, marker in [
            (int(np.argmax(valores)), "MAX", "^"),
            (int(np.argmin(valores)), "MIN", "v"),
        ]:
            self.eje.plot(tiempo[idx_fn], valores[idx_fn],
                          marker=marker, markersize=8, color=color, zorder=5)
            self.eje.annotate(
                f"{etiqueta}\n{valores[idx_fn]:.3g}",
                xy=(tiempo[idx_fn], valores[idx_fn]),
                xytext=(10, 10 if etiqueta == "MAX" else -20),
                textcoords="offset points",
                color=color, fontsize=8,
                arrowprops=dict(arrowstyle="->", color=color, lw=0.8),
            )

    # ================================================================== #
    #  Guardar                                                             #
    # ================================================================== #

    def guardar_figura(self, ruta: str, dpi: int = 300):
        """
        Guarda la figura actual en disco.

        El formato sale de la extensión de `ruta`:
          .png / .jpg          → mapa de bits (se usa `dpi`, por defecto 300)
          .pdf / .svg / .eps   → vectorial: el gráfico no pierde resolución
                                 al ampliarlo o imprimirlo en el informe.

        En los formatos vectoriales el `dpi` solo afecta a los elementos que
        sí son rasterizados (prácticamente ninguno acá), así que el texto y
        las curvas quedan como vectores.
        """
        self.figura.savefig(ruta, dpi=dpi, bbox_inches="tight",
                            facecolor=self.figura.get_facecolor())

    # ================================================================== #
    #  SISTEMA DE CURSORES                                                 #
    # ================================================================== #

    def _ejes_validos(self) -> list:
        """Devuelve los ejes (Axes) sobre los que se pueden colocar cursores."""
        ejes = [self.eje]
        if self._eje_secundario is not None:
            ejes.append(self._eje_secundario)
        return ejes

    def _coords_evento(self, evento):
        """
        Traduce la posición de un evento de mouse a coordenadas de datos
        del eje PRINCIPAL (self.eje), sin importar si el evento llegó desde
        self.eje o desde el eje secundario (twinx, usado para la fase en
        los diagramas de Bode). Ambos ejes comparten el mismo espacio en
        pantalla, así que se puede convertir usando las coordenadas de
        pixel del evento.
        """
        if evento.inaxes is self.eje:
            return evento.xdata, evento.ydata
        if evento.inaxes is self._eje_secundario and evento.x is not None and evento.y is not None:
            try:
                x, y = self.eje.transData.inverted().transform((evento.x, evento.y))
                return float(x), float(y)
            except Exception:
                return None, None
        return None, None

    def _on_press(self, evento):
        """Clic del mouse: inicia colocación o drag del cursor activo."""
        if evento.inaxes not in self._ejes_validos() or self._cursor_activo is None:
            return
        if evento.button != 1:
            return

        tipo, numero = self._cursor_activo
        x, y = self._coords_evento(evento)
        if x is None or y is None:
            return

        # Ver si el clic está cerca de un cursor existente → drag
        if self._cerca_de_cursor(tipo, numero, x, y):
            self._dragging = True
        else:
            # Colocar cursor en la posición del clic
            self._mover_cursor(tipo, numero, x, y)
            self._dragging = True

        self._drag_start_x = x
        self._drag_start_y = y

    def _on_release(self, evento):
        """Suelta el mouse: termina el drag."""
        self._dragging = False

    def _on_motion(self, evento):
        """Movimiento del mouse con botón apretado: arrastra el cursor."""
        if not self._dragging or evento.inaxes not in self._ejes_validos():
            return
        if self._cursor_activo is None:
            return
        tipo, numero = self._cursor_activo
        x, y = self._coords_evento(evento)
        if x is None or y is None:
            return
        self._mover_cursor(tipo, numero, x, y)

    def _cerca_de_cursor(self, tipo: str, numero: int, x: float, y: float) -> bool:
        """Devuelve True si (x,y) está cerca del cursor dado (para iniciar drag)."""
        TOL = 0.03  # 3% del rango del eje
        if tipo == "cx":
            pos = self._pos_cx[numero]
            if pos is None:
                return False
            xmin, xmax = self.eje.get_xlim()
            return abs(x - pos) < TOL * abs(xmax - xmin)
        else:
            pos = self._pos_cy[numero]
            if pos is None:
                return False
            ymin, ymax = self.eje.get_ylim()
            return abs(y - pos) < TOL * abs(ymax - ymin)

    def _mover_cursor(self, tipo: str, numero: int, x: float, y: float):
        """Actualiza la posición de un cursor y lo redibuja."""
        if tipo == "cx":
            self._pos_cx[numero] = x
            self._dibujar_cx(numero)
            self._actualizar_marcadores()
        else:
            self._pos_cy[numero] = y
            self._dibujar_cy(numero)

        self._notificar()
        self.canvas.draw_idle()

    def _dibujar_cx(self, numero: int):
        """Dibuja o mueve la línea vertical del cursor CX."""
        pos = self._pos_cx[numero]
        color = _COLOR_CX[numero]
        # Borrar línea anterior
        if self._linea_cx[numero] is not None:
            try: self._linea_cx[numero].remove()
            except Exception: pass
        # Borrar texto anterior (el cartel "CX1"/"CX2")
        if self._texto_cx[numero] is not None:
            try: self._texto_cx[numero].remove()
            except Exception: pass
            self._texto_cx[numero] = None
        if pos is None:
            self._linea_cx[numero] = None
            return
        linea = self.eje.axvline(x=pos, color=color, linewidth=1.5,
                                  linestyle="--", alpha=0.9, zorder=10)
        # Etiqueta con número del cursor — se guarda para poder borrarla al mover
        ymin, ymax = self.eje.get_ylim()
        texto = self.eje.text(pos, ymax - (ymax - ymin) * 0.04,
                      f" CX{numero}", color=color, fontsize=8,
                      va="top", zorder=11,
                      bbox=dict(boxstyle="round,pad=0.1",
                                facecolor=COLOR_FONDO_FIG, edgecolor=color, alpha=0.8))
        self._linea_cx[numero] = linea
        self._texto_cx[numero] = texto

    def _dibujar_cy(self, numero: int):
        """Dibuja o mueve la línea horizontal del cursor CY."""
        pos = self._pos_cy[numero]
        color = _COLOR_CY[numero]
        if self._linea_cy[numero] is not None:
            try: self._linea_cy[numero].remove()
            except Exception: pass
        # Borrar texto anterior
        if self._texto_cy[numero] is not None:
            try: self._texto_cy[numero].remove()
            except Exception: pass
            self._texto_cy[numero] = None
        if pos is None:
            self._linea_cy[numero] = None
            return
        linea = self.eje.axhline(y=pos, color=color, linewidth=1.5,
                                  linestyle="--", alpha=0.9, zorder=10)
        xmin, xmax = self.eje.get_xlim()
        texto = self.eje.text(xmin + (xmax - xmin) * 0.01, pos,
                      f" CY{numero}", color=color, fontsize=8,
                      va="bottom", zorder=11,
                      bbox=dict(boxstyle="round,pad=0.1",
                                facecolor=COLOR_FONDO_FIG, edgecolor=color, alpha=0.8))
        self._linea_cy[numero] = linea
        self._texto_cy[numero] = texto

    def _actualizar_marcadores(self):
        """Dibuja el punto de intersección entre CX y la señal asignada."""
        for n in (1, 2):
            # Borrar marcador anterior
            if self._marker_cx[n] is not None:
                try:
                    self._marker_cx[n].remove()
                except Exception:
                    pass
                self._marker_cx[n] = None

            pos_x = self._pos_cx[n]
            canal = self._canal_cx[n]
            if pos_x is None or canal is None or self._datos is None:
                continue

            y_interp = self._interpolar_y(canal, pos_x)
            if y_interp is None:
                continue

            color = _COLOR_CX[n]
            marker, = self.eje.plot(pos_x, y_interp, "o",
                                     color=color, markersize=8,
                                     markeredgecolor=COLOR_TEXTO, markeredgewidth=0.8,
                                     zorder=12)
            self._marker_cx[n] = marker

    def _interpolar_y(self, nombre_canal: str, x: float):
        """
        Interpola el valor Y de un canal en la posición X del cursor.
        Retorna float o None si no es posible.
        """
        if self._datos is None:
            return None
        datos = self._datos
        fmt   = datos.get("formato", FORMATO_TIEMPO)

        if fmt in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
            xs = np.array(datos["frecuencia"])
            if nombre_canal == "ganancia":
                ys = np.array(datos["ganancia_db"])
            elif nombre_canal == "fase":
                ys = np.array(datos["fase_deg"])
            else:
                return None
        else:
            ft = datos["factor_tiempo"]
            fv = datos["factor_tension"]
            xs = np.array([t * ft for t in datos["tiempo"]])
            if nombre_canal not in datos["canales"]:
                return None
            cfg    = self._config or {}
            escala = cfg.get("escala", {}).get(nombre_canal, 1.0)
            offset = cfg.get("offset", {}).get(nombre_canal, 0.0)
            ys = np.array([v * fv * escala + offset for v in datos["canales"][nombre_canal]])

        if len(xs) < 2:
            return None
        return float(np.interp(x, xs, ys))

    def _redibujar_cursores(self):
        """Redibuja todos los cursores después de un actualizar() completo."""
        for n in (1, 2):
            if self._pos_cx[n] is not None:
                self._dibujar_cx(n)
            if self._pos_cy[n] is not None:
                self._dibujar_cy(n)
        self._actualizar_marcadores()

    def _notificar(self):
        """
        Calcula la información de cursores y llama al callback de la GUI.
        El dict tiene:
          cx1_x, cx1_y, cx2_x, cx2_y   : posición y valor interpolado
          cy1_y, cy2_y                  : posición Y de cursores horizontales
          delta_x, delta_y              : diferencias
        """
        if self.on_cursor_update is None:
            return

        def _fmt_cx(n):
            x = self._pos_cx[n]
            if x is None:
                return None, None
            canal = self._canal_cx[n]
            y = self._interpolar_y(canal, x) if canal else None
            return x, y

        cx1_x, cx1_y = _fmt_cx(1)
        cx2_x, cx2_y = _fmt_cx(2)
        cy1_y = self._pos_cy[1]
        cy2_y = self._pos_cy[2]

        # Δx
        if cx1_x is not None and cx2_x is not None:
            delta_x = abs(cx2_x - cx1_x)
        else:
            delta_x = None

        # Δy (entre CY1 y CY2, o vs 0 si solo hay uno)
        if cy1_y is not None and cy2_y is not None:
            delta_y = abs(cy2_y - cy1_y)
        elif cy1_y is not None:
            delta_y = abs(cy1_y)   # vs 0
        elif cy2_y is not None:
            delta_y = abs(cy2_y)   # vs 0
        else:
            delta_y = None

        self.on_cursor_update({
            "cx1_x": cx1_x, "cx1_y": cx1_y,
            "cx2_x": cx2_x, "cx2_y": cx2_y,
            "cy1_y": cy1_y,
            "cy2_y": cy2_y,
            "delta_x": delta_x,
            "delta_y": delta_y,
        })
