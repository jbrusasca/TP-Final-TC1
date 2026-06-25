"""
gui.py
------
Interfaz gráfica principal del Visor CSV de Osciloscopio.

Panel izquierdo — dos modos:
  • MODO CANALES  : controles por canal (color, escala, offset, visibilidad)
  • MODO CURSORES : 4 cursores (CX1, CX2, CY1, CY2) con tabla de valores en
                   tiempo real y cálculo de Δx / Δy

Panel central    : gráfico matplotlib embebido
Panel inferior   : opciones globales (grilla, log, máx/mín, modo XY)

Formatos soportados: señales de tiempo, Autobode Keysight, Bode LTSpice

Modo superposición: hasta 8 Bodes o señales de tiempo en el mismo gráfico.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import os

from lector_csv import leer_csv, ErrorCSV, FORMATO_AUTOBODE, FORMATO_LTSPICE
from graficador import Graficador, COLORES_DEFECTO


# ------------------------------------------------------------------ #
#  Tema visual                                                         #
# ------------------------------------------------------------------ #
FONDO        = "#1e1e2e"
FONDO2       = "#2a2a3e"
ACENTO       = "#7c7cff"
TEXTO        = "#cdd6f4"
TEXTO_DIMMED = "#888899"
BORDE        = "#444466"
BOTON_BG     = "#313244"
BOTON_HOVER  = "#45475a"

# Colores de cursores (deben coincidir con graficador.py)
COLOR_CX1 = "#FFFF00"
COLOR_CX2 = "#FF9900"
COLOR_CY1 = "#00FFCC"
COLOR_CY2 = "#FF44FF"


class AplicacionOsciloscopio:
    """Ventana principal de la aplicación."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Osciloscopio CSV — TP Circuitos I")
        self.root.geometry("1340x760")
        self.root.configure(bg=FONDO)
        self.root.minsize(950, 620)

        # Datos CSV cargados
        self._datos = None          # archivo "activo" (último cargado o seleccionado)
        self._lista_archivos = []   # lista de dicts para superposición
                                    # cada item: {'datos': dict, 'visible': BooleanVar,
                                    #             'color_override': str o None,
                                    #             'etiqueta': str}

        # ---- Variables de canal ----
        self._vars_visibles = {}
        self._vars_escala   = {}
        self._vars_offset   = {}
        self._colores       = {}

        # ---- Variables globales ----
        self._var_grilla     = tk.BooleanVar(value=True)
        self._idx_paso_x     = None
        self._idx_paso_y     = None
        self._var_log_x      = tk.BooleanVar(value=False)
        self._var_log_y      = tk.BooleanVar(value=False)
        self._var_maxmin     = tk.BooleanVar(value=False)
        self._var_modo_xy    = tk.BooleanVar(value=False)
        self._var_canal_x_xy = tk.StringVar(value="")
        self._var_canal_y_xy = tk.StringVar(value="")

        # ---- Estado del modo del panel izquierdo ----
        # "canales" o "cursores"
        self._modo_panel = "canales"

        # ---- Variables de cursores X (canal asignado) ----
        self._var_canal_cx = {1: tk.StringVar(value="—"),
                               2: tk.StringVar(value="—")}

        # ---- Labels de valores de cursor (se actualizan en tiempo real) ----
        self._lbl_cursor = {}   # se crean en _construir_panel_cursores

        self._construir_ui()
        self._habilitar_drag_drop()

    # ================================================================== #
    #  Construcción de la UI                                               #
    # ================================================================== #

    def _construir_ui(self):
        self._construir_barra_superior()

        contenedor = tk.Frame(self.root, bg=FONDO)
        contenedor.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Panel izquierdo
        self._panel_izq = tk.Frame(contenedor, bg=FONDO2, width=270)
        self._panel_izq.pack(side="left", fill="y", padx=(0, 6))
        self._panel_izq.pack_propagate(False)
        self._mostrar_panel_vacio()

        tk.Frame(contenedor, bg=BORDE, width=1).pack(side="left", fill="y")

        # Panel derecho
        panel_der = tk.Frame(contenedor, bg=FONDO)
        panel_der.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self._frame_grafico = tk.Frame(panel_der, bg=FONDO)
        self._frame_grafico.pack(fill="both", expand=True)

        self._construir_panel_opciones(panel_der)

        self._graficador = Graficador(self._frame_grafico)
        # Registrar callback de cursores
        self._graficador.on_cursor_update = self._on_cursor_update

    def _construir_barra_superior(self):
        barra = tk.Frame(self.root, bg=FONDO2, height=48)
        barra.pack(fill="x")
        barra.pack_propagate(False)

        tk.Label(barra, text="📊  Visor CSV", bg=FONDO2, fg=ACENTO,
                 font=("Courier New", 13, "bold")).pack(side="left", padx=14)

        tk.Button(barra, text="📂  Abrir CSV", command=self._abrir_archivo,
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  activeforeground=TEXTO, relief="flat", padx=14, pady=6,
                  font=("Courier New", 10), cursor="hand2").pack(side="left", padx=8, pady=8)

        tk.Button(barra, text="💾  Guardar PNG", command=self._guardar_png,
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  activeforeground=TEXTO, relief="flat", padx=14, pady=6,
                  font=("Courier New", 10), cursor="hand2").pack(side="left", padx=4, pady=8)

        tk.Button(barra, text="➕  Agregar CSV", command=self._agregar_archivo,
                  bg="#2d4a2d", fg="#88ff88", activebackground="#3d6a3d",
                  activeforeground="#aaffaa", relief="flat", padx=14, pady=6,
                  font=("Courier New", 10), cursor="hand2").pack(side="left", padx=4, pady=8)

        tk.Button(barra, text="✖  Limpiar todo", command=self._limpiar_todo,
                  bg="#4a2d2d", fg="#ff8888", activebackground="#6a3d3d",
                  activeforeground="#ffaaaa", relief="flat", padx=14, pady=6,
                  font=("Courier New", 10), cursor="hand2").pack(side="left", padx=4, pady=8)

        self._label_archivo = tk.Label(barra, text="Ningún archivo cargado",
                                        bg=FONDO2, fg=TEXTO_DIMMED,
                                        font=("Courier New", 9))
        self._label_archivo.pack(side="left", padx=16)

        tk.Label(barra, text="(o arrastrá y soltá el .csv)",
                 bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="right", padx=12)

    # ------------------------------------------------------------------ #
    #  Panel izquierdo — selector de modo                                  #
    # ------------------------------------------------------------------ #

    def _mostrar_panel_vacio(self):
        """Panel antes de cargar un archivo."""
        self._limpiar_panel_izq()
        tk.Label(self._panel_izq, text="Canales", bg=FONDO2, fg=ACENTO,
                 font=("Courier New", 11, "bold")).pack(pady=(14, 4), padx=10, anchor="w")
        tk.Label(self._panel_izq, text="Cargá un CSV para\nver los controles",
                 bg=FONDO2, fg=TEXTO_DIMMED, font=("Courier New", 9),
                 justify="left").pack(pady=20, padx=10, anchor="w")

    def _limpiar_panel_izq(self):
        for w in self._panel_izq.winfo_children():
            w.destroy()

    def _construir_tabs_panel(self) -> tk.Frame:
        """
        Construye la barra de tabs Canales / Cursores en la parte superior
        del panel izquierdo. Retorna el frame de contenido.
        """
        self._limpiar_panel_izq()

        # Barra de tabs
        barra_tabs = tk.Frame(self._panel_izq, bg=FONDO2)
        barra_tabs.pack(fill="x", padx=0, pady=0)

        self._btn_tab_canales = tk.Button(
            barra_tabs, text="Canales",
            command=lambda: self._cambiar_tab("canales"),
            relief="flat", bd=0, padx=8, pady=5,
            font=("Courier New", 9, "bold"), cursor="hand2",
        )
        self._btn_tab_canales.pack(side="left", fill="x", expand=True)

        self._btn_tab_cursores = tk.Button(
            barra_tabs, text="Cursores",
            command=lambda: self._cambiar_tab("cursores"),
            relief="flat", bd=0, padx=8, pady=5,
            font=("Courier New", 9, "bold"), cursor="hand2",
        )
        self._btn_tab_cursores.pack(side="left", fill="x", expand=True)

        tk.Frame(self._panel_izq, bg=BORDE, height=1).pack(fill="x")

        # Frame de contenido (debajo de los tabs)
        self._frame_contenido_panel = tk.Frame(self._panel_izq, bg=FONDO2)
        self._frame_contenido_panel.pack(fill="both", expand=True)

        self._actualizar_estilo_tabs()
        return self._frame_contenido_panel

    def _actualizar_estilo_tabs(self):
        """Resalta el tab activo."""
        if self._modo_panel == "canales":
            self._btn_tab_canales.config(bg=ACENTO,   fg="#ffffff")
            self._btn_tab_cursores.config(bg=BOTON_BG, fg=TEXTO_DIMMED)
        else:
            self._btn_tab_canales.config(bg=BOTON_BG, fg=TEXTO_DIMMED)
            self._btn_tab_cursores.config(bg=ACENTO,   fg="#ffffff")

    def _cambiar_tab(self, modo: str):
        self._modo_panel = modo
        self._actualizar_estilo_tabs()
        for w in self._frame_contenido_panel.winfo_children():
            w.destroy()
        if modo == "canales":
            self._poblar_tab_canales(self._frame_contenido_panel)
        else:
            self._poblar_tab_cursores(self._frame_contenido_panel)

    # ------------------------------------------------------------------ #
    #  Tab CANALES                                                          #
    # ------------------------------------------------------------------ #

    def _construir_panel_canales(self, nombres_canales: list):
        """Reconstruye el panel izquierdo con tabs para un CSV de señales."""
        self._vars_visibles = {}
        self._vars_escala   = {}
        self._vars_offset   = {}
        self._colores       = {}

        contenido = self._construir_tabs_panel()
        self._modo_panel = "canales"
        self._actualizar_estilo_tabs()
        self._poblar_tab_canales(contenido)

        # Actualizar opciones de canal en cursores X
        self._nombres_canales_actuales = nombres_canales
        for n in (1, 2):
            self._var_canal_cx[n].set(nombres_canales[0] if nombres_canales else "—")

        # Inicializar vars de canal
        for i, nombre in enumerate(nombres_canales):
            self._colores[nombre]       = COLORES_DEFECTO[i % len(COLORES_DEFECTO)]
            self._vars_visibles[nombre] = tk.BooleanVar(value=True)
            self._vars_escala[nombre]   = tk.DoubleVar(value=1.0)
            self._vars_offset[nombre]   = tk.DoubleVar(value=0.0)

        # Actualizar menús de Lissajous
        self._var_canal_x_xy.set(nombres_canales[0])
        self._var_canal_y_xy.set(nombres_canales[1] if len(nombres_canales) > 1
                                  else nombres_canales[0])
        if hasattr(self, "_menu_canal_x"):
            self._menu_canal_x["menu"].delete(0, "end")
            self._menu_canal_y["menu"].delete(0, "end")
            for n in nombres_canales:
                self._menu_canal_x["menu"].add_command(
                    label=n, command=lambda v=n: self._var_canal_x_xy.set(v))
                self._menu_canal_y["menu"].add_command(
                    label=n, command=lambda v=n: self._var_canal_y_xy.set(v))

    def _poblar_tab_canales(self, parent: tk.Frame):
        """Llena el frame con los controles de canal."""
        canvas_s = tk.Canvas(parent, bg=FONDO2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas_s.yview)
        frame_s = tk.Frame(canvas_s, bg=FONDO2)
        frame_s.bind("<Configure>",
                     lambda e: canvas_s.configure(scrollregion=canvas_s.bbox("all")))
        canvas_s.create_window((0, 0), window=frame_s, anchor="nw")
        canvas_s.configure(yscrollcommand=scrollbar.set)
        canvas_s.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i, nombre in enumerate(list(self._vars_visibles.keys())):
            self._crear_bloque_canal(frame_s, nombre, i)

    def _crear_bloque_canal(self, parent, nombre: str, indice: int):
        frame = tk.Frame(parent, bg=FONDO, highlightbackground=BORDE,
                         highlightthickness=1)
        frame.pack(fill="x", padx=8, pady=5, ipady=4)

        # Fila 1: color + checkbox
        fila1 = tk.Frame(frame, bg=FONDO)
        fila1.pack(fill="x", padx=6, pady=(4, 2))
        btn_color = tk.Button(fila1, bg=self._colores[nombre], width=2, height=1,
                              relief="flat", cursor="hand2",
                              command=lambda n=nombre: self._elegir_color(n))
        btn_color.pack(side="left", padx=(0, 6))
        setattr(self, f"_btn_color_{nombre}", btn_color)
        tk.Checkbutton(fila1, text=f"Canal {nombre}",
                       variable=self._vars_visibles[nombre],
                       bg=FONDO, fg=TEXTO, selectcolor=FONDO2,
                       activebackground=FONDO, font=("Courier New", 9, "bold"),
                       command=self._redibujar).pack(side="left")

        # Fila 2: escala
        fila2 = tk.Frame(frame, bg=FONDO)
        fila2.pack(fill="x", padx=6, pady=2)
        tk.Label(fila2, text="Escala ×", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")
        sp = ttk.Spinbox(fila2, from_=-100.0, to=100.0, increment=0.5,
                         textvariable=self._vars_escala[nombre],
                         width=7, font=("Courier New", 9), command=self._redibujar)
        sp.pack(side="left", padx=4)
        sp.bind("<Return>", lambda e: self._redibujar())
        sp.bind("<FocusOut>", lambda e: self._redibujar())

        # Fila 3: offset
        fila3 = tk.Frame(frame, bg=FONDO)
        fila3.pack(fill="x", padx=6, pady=(2, 4))
        tk.Label(fila3, text="Offset", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")
        sp2 = ttk.Spinbox(fila3, from_=-999.0, to=999.0, increment=0.5,
                          textvariable=self._vars_offset[nombre],
                          width=7, font=("Courier New", 9), command=self._redibujar)
        sp2.pack(side="left", padx=4)
        sp2.bind("<Return>", lambda e: self._redibujar())
        sp2.bind("<FocusOut>", lambda e: self._redibujar())

    # ------------------------------------------------------------------ #
    #  Tab BODE (Keysight / LTSpice)                                       #
    # ------------------------------------------------------------------ #

    def _construir_panel_bode(self, datos: dict):
        """Panel izquierdo para archivos de Bode."""
        contenido = self._construir_tabs_panel()
        self._modo_panel = "canales"
        self._actualizar_estilo_tabs()

        # Guardar canales de bode para los cursores
        self._nombres_canales_actuales = ["ganancia", "fase"]

        frecuencia = datos.get("frecuencia", [])
        ganancia   = datos.get("ganancia_db", [])
        fase       = datos.get("fase_deg", [])

        info_lines = [
            f"Puntos:   {len(frecuencia)}",
            f"F mín:    {frecuencia[0]:.1f} Hz"  if frecuencia else "F mín:  —",
            f"F máx:    {frecuencia[-1]:.1f} Hz" if frecuencia else "F máx:  —",
        ]
        if ganancia:
            info_lines += [f"G máx:    {max(ganancia):.2f} dB",
                           f"G mín:    {min(ganancia):.2f} dB"]
        if fase:
            info_lines += [f"Fase máx: {max(fase):.1f}°",
                           f"Fase mín: {min(fase):.1f}°"]

        for linea in info_lines:
            tk.Label(contenido, text=linea, bg=FONDO2, fg=TEXTO,
                     font=("Courier New", 9), anchor="w").pack(padx=14, pady=2, anchor="w")

        tk.Frame(contenido, bg=BORDE, height=1).pack(fill="x", padx=10, pady=8)
        tk.Label(contenido,
                 text="— Azul:  Ganancia (dB)\n— Rojo:  Fase (°)\n\n"
                      "Eje X logarítmico\npor defecto.\n\n"
                      "Usá el tab Cursores\npara medir valores.",
                 bg=FONDO2, fg=TEXTO_DIMMED, font=("Courier New", 8),
                 justify="left").pack(padx=14, pady=4, anchor="w")

        # Cursores de bode usan "ganancia" y "fase" como canales
        for n in (1, 2):
            self._var_canal_cx[n].set("ganancia")

    # ------------------------------------------------------------------ #
    #  Tab CURSORES                                                         #
    # ------------------------------------------------------------------ #

    def _poblar_tab_cursores(self, parent: tk.Frame):
        """
        Construye el panel de cursores con:
        - 4 botones de selección (CX1, CX2, CY1, CY2)
        - Selector de canal para CX1 y CX2
        - Tabla de valores en tiempo real
        - Botón limpiar
        """
        canales = getattr(self, "_nombres_canales_actuales", [])

        # ---- Título ----
        tk.Label(parent, text="Cursores", bg=FONDO2, fg=ACENTO,
                 font=("Courier New", 11, "bold")).pack(pady=(10, 6), padx=10, anchor="w")

        tk.Label(parent,
                 text="Activá un cursor y hacé\nclic en el gráfico.\nDrag para mover.",
                 bg=FONDO2, fg=TEXTO_DIMMED, font=("Courier New", 8),
                 justify="left").pack(padx=10, anchor="w")

        tk.Frame(parent, bg=BORDE, height=1).pack(fill="x", padx=8, pady=8)

        # ---- Cursores X ----
        tk.Label(parent, text="Cursores X (verticales)",
                 bg=FONDO2, fg=TEXTO, font=("Courier New", 9, "bold")).pack(padx=10, anchor="w")

        self._var_cursor_activo = tk.StringVar(value="ninguno")

        for num, color in [(1, COLOR_CX1), (2, COLOR_CX2)]:
            frame = tk.Frame(parent, bg=FONDO2)
            frame.pack(fill="x", padx=8, pady=3)

            # Botón activar
            rb = tk.Radiobutton(
                frame, text=f"CX{num}",
                variable=self._var_cursor_activo, value=f"cx{num}",
                command=self._on_cursor_seleccionado,
                bg=FONDO2, fg=color, selectcolor=FONDO,
                activebackground=FONDO2,
                font=("Courier New", 9, "bold"),
                indicatoron=False, relief="flat",
                bd=1, padx=8, pady=4,
                cursor="hand2", width=4,
            )
            rb.pack(side="left", padx=(0, 6))

            # Selector de canal
            if canales:
                tk.Label(frame, text="señal:", bg=FONDO2, fg=TEXTO_DIMMED,
                         font=("Courier New", 8)).pack(side="left")
                menu = tk.OptionMenu(frame, self._var_canal_cx[num], *canales,
                                     command=lambda v, n=num: self._on_canal_cx_cambiado(n))
                menu.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                            activebackground=BOTON_HOVER, font=("Courier New", 8),
                            width=5)
                menu.pack(side="left", padx=2)

        tk.Frame(parent, bg=BORDE, height=1).pack(fill="x", padx=8, pady=6)

        # ---- Cursores Y ----
        tk.Label(parent, text="Cursores Y (horizontales)",
                 bg=FONDO2, fg=TEXTO, font=("Courier New", 9, "bold")).pack(padx=10, anchor="w")

        for num, color in [(1, COLOR_CY1), (2, COLOR_CY2)]:
            frame = tk.Frame(parent, bg=FONDO2)
            frame.pack(fill="x", padx=8, pady=3)
            rb = tk.Radiobutton(
                frame, text=f"CY{num}",
                variable=self._var_cursor_activo, value=f"cy{num}",
                command=self._on_cursor_seleccionado,
                bg=FONDO2, fg=color, selectcolor=FONDO,
                activebackground=FONDO2,
                font=("Courier New", 9, "bold"),
                indicatoron=False, relief="flat",
                bd=1, padx=8, pady=4,
                cursor="hand2", width=4,
            )
            rb.pack(side="left")

        tk.Frame(parent, bg=BORDE, height=1).pack(fill="x", padx=8, pady=8)

        # ---- Tabla de valores ----
        tk.Label(parent, text="Mediciones", bg=FONDO2, fg=TEXTO,
                 font=("Courier New", 9, "bold")).pack(padx=10, anchor="w", pady=(0, 4))

        tabla = tk.Frame(parent, bg=FONDO2)
        tabla.pack(fill="x", padx=8)

        filas_def = [
            ("cx1_x",  f"CX1 x",    COLOR_CX1),
            ("cx1_y",  f"CX1 y",    COLOR_CX1),
            ("cx2_x",  f"CX2 x",    COLOR_CX2),
            ("cx2_y",  f"CX2 y",    COLOR_CX2),
            ("cy1_y",  f"CY1 y",    COLOR_CY1),
            ("cy2_y",  f"CY2 y",    COLOR_CY2),
            ("delta_x", "Δx",       "#ffffff"),
            ("delta_y", "Δy",       "#ffffff"),
        ]

        self._lbl_cursor = {}
        for clave, etiqueta, color in filas_def:
            fila = tk.Frame(tabla, bg=FONDO2)
            fila.pack(fill="x", pady=1)
            tk.Label(fila, text=f"{etiqueta}:", bg=FONDO2, fg=color,
                     font=("Courier New", 8), width=7, anchor="w").pack(side="left")
            lbl = tk.Label(fila, text="—", bg=FONDO, fg=color,
                           font=("Courier New", 9, "bold"),
                           width=10, anchor="e",
                           relief="flat", padx=4)
            lbl.pack(side="left", fill="x", expand=True)
            self._lbl_cursor[clave] = lbl

        tk.Frame(parent, bg=BORDE, height=1).pack(fill="x", padx=8, pady=8)

        # ---- Botón limpiar ----
        tk.Button(parent, text="🗑  Limpiar cursores",
                  command=self._limpiar_cursores,
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  relief="flat", padx=8, pady=4,
                  font=("Courier New", 9), cursor="hand2").pack(padx=10, pady=4, fill="x")

    # ------------------------------------------------------------------ #
    #  Eventos de cursores                                                  #
    # ------------------------------------------------------------------ #

    def _on_cursor_seleccionado(self):
        """Informa al graficador qué cursor está activo."""
        valor = self._var_cursor_activo.get()
        if valor == "ninguno":
            self._graficador.set_cursor_activo(None, None)
        else:
            tipo   = valor[:2]   # "cx" o "cy"
            numero = int(valor[2])
            self._graficador.set_cursor_activo(tipo, numero)
            # Informar también el canal asignado
            if tipo == "cx":
                canal = self._var_canal_cx[numero].get()
                self._graficador.set_canal_cursor(numero, canal)

    def _on_canal_cx_cambiado(self, numero: int):
        """El usuario cambió el canal asignado a un cursor X."""
        canal = self._var_canal_cx[numero].get()
        self._graficador.set_canal_cursor(numero, canal)

    def _limpiar_cursores(self):
        self._graficador.limpiar_cursores()
        self._var_cursor_activo.set("ninguno")
        self._graficador.set_cursor_activo(None, None)
        # Resetear labels
        for lbl in self._lbl_cursor.values():
            lbl.config(text="—")

    def _on_cursor_update(self, info: dict):
        """
        Callback llamado por el graficador cada vez que un cursor se mueve.
        Actualiza los labels de medición del panel izquierdo.
        """
        if not self._lbl_cursor:
            return

        def fmt(valor, decimales=4):
            if valor is None:
                return "—"
            return f"{valor:.{decimales}g}"

        claves_map = {
            "cx1_x":  ("cx1_x",  info.get("cx1_x")),
            "cx1_y":  ("cx1_y",  info.get("cx1_y")),
            "cx2_x":  ("cx2_x",  info.get("cx2_x")),
            "cx2_y":  ("cx2_y",  info.get("cx2_y")),
            "cy1_y":  ("cy1_y",  info.get("cy1_y")),
            "cy2_y":  ("cy2_y",  info.get("cy2_y")),
            "delta_x":("delta_x",info.get("delta_x")),
            "delta_y":("delta_y",info.get("delta_y")),
        }
        for clave, (_, valor) in claves_map.items():
            if clave in self._lbl_cursor:
                self._lbl_cursor[clave].config(text=fmt(valor))

    # ------------------------------------------------------------------ #
    #  Panel opciones globales (inferior)                                  #
    # ------------------------------------------------------------------ #

    def _construir_panel_opciones(self, parent):
        panel = tk.Frame(parent, bg=FONDO2, height=70)
        panel.pack(fill="x", pady=(6, 0))
        panel.pack_propagate(False)

        # Grilla
        tk.Checkbutton(panel, text="Grilla", variable=self._var_grilla,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=(12, 4), pady=10)

        # Grilla X
        tk.Label(panel, text="Grilla X:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left", padx=(4, 2))
        tk.Button(panel, text="−", command=lambda: self._ajustar_paso("x", -1),
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  relief="flat", width=2, font=("Courier New", 9),
                  cursor="hand2").pack(side="left")
        self._label_paso_x = tk.Label(panel, text="Auto", bg=BOTON_BG, fg=ACENTO,
                                       font=("Courier New", 9), width=6, anchor="center")
        self._label_paso_x.pack(side="left", padx=2)
        tk.Button(panel, text="+", command=lambda: self._ajustar_paso("x", +1),
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  relief="flat", width=2, font=("Courier New", 9),
                  cursor="hand2").pack(side="left")

        # Grilla Y
        tk.Label(panel, text="Y:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left", padx=(8, 2))
        tk.Button(panel, text="−", command=lambda: self._ajustar_paso("y", -1),
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  relief="flat", width=2, font=("Courier New", 9),
                  cursor="hand2").pack(side="left")
        self._label_paso_y = tk.Label(panel, text="Auto", bg=BOTON_BG, fg=ACENTO,
                                       font=("Courier New", 9), width=6, anchor="center")
        self._label_paso_y.pack(side="left", padx=2)
        tk.Button(panel, text="+", command=lambda: self._ajustar_paso("y", +1),
                  bg=BOTON_BG, fg=TEXTO, activebackground=BOTON_HOVER,
                  relief="flat", width=2, font=("Courier New", 9),
                  cursor="hand2").pack(side="left")

        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Log X / Y
        tk.Checkbutton(panel, text="Log X", variable=self._var_log_x,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)
        tk.Checkbutton(panel, text="Log Y", variable=self._var_log_y,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)

        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Máx/Mín
        tk.Checkbutton(panel, text="Marcar Máx/Mín", variable=self._var_maxmin,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)

        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Modo XY
        tk.Checkbutton(panel, text="Modo XY", variable=self._var_modo_xy,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)
        tk.Label(panel, text="X:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_x = tk.OptionMenu(panel, self._var_canal_x_xy, "")
        self._menu_canal_x.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER, font=("Courier New", 8))
        self._menu_canal_x.pack(side="left", padx=2)
        tk.Label(panel, text="Y:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_y = tk.OptionMenu(panel, self._var_canal_y_xy, "")
        self._menu_canal_y.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER, font=("Courier New", 8))
        self._menu_canal_y.pack(side="left", padx=2)

        # Botón actualizar
        tk.Button(panel, text="↺ Actualizar", command=self._redibujar,
                  bg=ACENTO, fg="#ffffff", activebackground="#9999ff",
                  relief="flat", padx=10, pady=4,
                  font=("Courier New", 9), cursor="hand2").pack(side="right", padx=12, pady=10)

    # ================================================================== #
    #  Apertura de archivos                                                #
    # ================================================================== #



    def _cargar_csv(self, ruta: str, agregar: bool = False):
        """
        Carga un CSV.
        agregar=False → reemplaza todo (comportamiento original)
        agregar=True  → agrega a la lista de superposición
        """
        try:
            datos = leer_csv(ruta)
        except ErrorCSV as e:
            messagebox.showerror("Archivo inválido", f"No se pudo cargar:\n\n{e}")
            return
        except Exception as e:
            messagebox.showerror("Error inesperado", f"Error al leer el archivo:\n\n{e}")
            return

        if not agregar:
            # Modo normal: limpiar lista y cargar solo este archivo
            self._lista_archivos.clear()
            self._vars_visibles = {}
            self._vars_escala   = {}
            self._vars_offset   = {}
            self._colores       = {}

        # Asignar color automático según posición en la lista
        idx_color = len(self._lista_archivos) % len(COLORES_DEFECTO)
        color     = COLORES_DEFECTO[idx_color]

        item = {
            "datos":          datos,
            "visible":        tk.BooleanVar(value=True),
            "color_override": color,
            "etiqueta":       datos["nombre_archivo"],
            "escala_var":     tk.DoubleVar(value=1.0),
            "offset_var":     tk.DoubleVar(value=0.0),
        }
        self._lista_archivos.append(item)
        self._datos = datos   # último cargado = activo

        fmt = datos.get("formato", "tiempo")
        n_archivos = len(self._lista_archivos)

        if fmt in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
            self._var_log_x.set(True)
            if n_archivos == 1:
                self._construir_panel_bode(datos)
            else:
                self._construir_panel_superposicion()
        else:
            self._var_log_x.set(False)
            if n_archivos == 1:
                self._construir_panel_canales(list(datos["canales"].keys()))
            else:
                self._construir_panel_superposicion()

        # Label de barra superior
        if n_archivos == 1:
            self._label_archivo.config(
                text=f"{datos['nombre_archivo']}  |  {fmt.upper()}", fg=TEXTO)
        else:
            self._label_archivo.config(
                text=f"{n_archivos} archivos cargados  |  Modo superposición", fg="#88ff88")

        self._redibujar()

    # ================================================================== #
    #  Redibujar                                                           #
    # ================================================================== #

    def _redibujar(self):
        if self._datos is None:
            return
        config = {
            "canales_visibles":  {n: v.get() for n, v in self._vars_visibles.items()},
            "escala":            {n: v.get() for n, v in self._vars_escala.items()},
            "offset":            {n: v.get() for n, v in self._vars_offset.items()},
            "colores":           dict(self._colores),
            "grilla":            self._var_grilla.get(),
            "paso_grilla_x":     _paso_desde_indice(self._idx_paso_x, "x"),
            "paso_grilla_y":     _paso_desde_indice(self._idx_paso_y, "y"),
            "eje_x_log":         self._var_log_x.get(),
            "eje_y_log":         self._var_log_y.get(),
            "mostrar_maxmin":    self._var_maxmin.get(),
            "modo_xy":           self._var_modo_xy.get(),
            "canal_x_lissajous": self._var_canal_x_xy.get(),
            "canal_y_lissajous": self._var_canal_y_xy.get(),
            # Superposición: lista de todos los archivos cargados
            "lista_archivos":    [
                {
                    "datos":    item["datos"],
                    "visible":  item["visible"].get(),
                    "color":    item["color_override"],
                    "etiqueta": item["etiqueta"],
                    "escala":   item["escala_var"].get(),
                    "offset":   item["offset_var"].get(),
                }
                for item in self._lista_archivos
            ],
        }
        self._graficador.actualizar(self._datos, config)

    # ================================================================== #
    #  Grilla paso +/-                                                     #
    # ================================================================== #

    def _ajustar_paso(self, eje: str, direccion: int):
        pasos = _pasos_grilla(eje)
        n = len(pasos)
        idx = self._idx_paso_x if eje == "x" else self._idx_paso_y

        if idx is None:
            nuevo = 0 if direccion == 1 else None
        else:
            nuevo = idx + direccion
            if nuevo < 0:
                nuevo = None
            elif nuevo >= n:
                nuevo = n - 1

        if eje == "x":
            self._idx_paso_x = nuevo
            self._label_paso_x.config(text=_label_paso(nuevo, pasos))
        else:
            self._idx_paso_y = nuevo
            self._label_paso_y.config(text=_label_paso(nuevo, pasos))
        self._redibujar()

    # ================================================================== #
    #  Color de canal                                                      #
    # ================================================================== #

    def _elegir_color(self, nombre: str):
        resultado = colorchooser.askcolor(color=self._colores.get(nombre, "#ffffff"),
                                          title=f"Color — Canal {nombre}")
        if resultado and resultado[1]:
            self._colores[nombre] = resultado[1]
            btn = getattr(self, f"_btn_color_{nombre}", None)
            if btn:
                btn.config(bg=resultado[1])
            self._redibujar()

    # ================================================================== #
    #  Apertura / gestión de múltiples archivos                           #
    # ================================================================== #

    def _abrir_archivo(self):
        """Abre un CSV reemplazando todo (modo normal)."""
        ruta = filedialog.askopenfilename(
            title="Abrir archivo CSV",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if ruta:
            self._cargar_csv(ruta, agregar=False)

    def _agregar_archivo(self):
        """Agrega un CSV a la superposición actual."""
        ruta = filedialog.askopenfilename(
            title="Agregar CSV a superposición",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if ruta:
            self._cargar_csv(ruta, agregar=True)

    def _limpiar_todo(self):
        """Elimina todos los archivos cargados."""
        self._lista_archivos.clear()
        self._datos = None
        self._vars_visibles = {}
        self._vars_escala   = {}
        self._vars_offset   = {}
        self._colores       = {}
        self._mostrar_panel_vacio()
        self._label_archivo.config(text="Ningún archivo cargado", fg=TEXTO_DIMMED)
        self._graficador.eje.cla()
        self._graficador.canvas.draw()

    def _construir_panel_superposicion(self):
        """
        Panel izquierdo en modo superposición: muestra la lista de archivos
        cargados con checkbox de visibilidad, cuadrado de color y botón de
        eliminación individual para cada uno.
        """
        contenido = self._construir_tabs_panel()
        self._modo_panel = "canales"
        self._actualizar_estilo_tabs()

        tk.Label(contenido, text="Archivos superpuestos",
                 bg=FONDO2, fg=ACENTO,
                 font=("Courier New", 10, "bold")).pack(pady=(10, 4), padx=10, anchor="w")

        # Frame scrollable
        canvas_s  = tk.Canvas(contenido, bg=FONDO2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(contenido, orient="vertical", command=canvas_s.yview)
        frame_s   = tk.Frame(canvas_s, bg=FONDO2)
        frame_s.bind("<Configure>",
                     lambda e: canvas_s.configure(scrollregion=canvas_s.bbox("all")))
        canvas_s.create_window((0, 0), window=frame_s, anchor="nw")
        canvas_s.configure(yscrollcommand=scrollbar.set)
        canvas_s.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i, item in enumerate(self._lista_archivos):
            self._crear_fila_superposicion(frame_s, item, i)

    def _crear_fila_superposicion(self, parent, item: dict, indice: int):
        """Fila de un archivo en el panel de superposición."""
        frame = tk.Frame(parent, bg=FONDO, highlightbackground=BORDE,
                         highlightthickness=1)
        frame.pack(fill="x", padx=6, pady=4, ipady=3)

        # Fila 1: color + visibilidad + eliminar
        fila1 = tk.Frame(frame, bg=FONDO)
        fila1.pack(fill="x", padx=4, pady=(3, 1))

        # Cuadrado de color (clickeable)
        btn_c = tk.Button(
            fila1, bg=item["color_override"], width=2, height=1,
            relief="flat", cursor="hand2",
            command=lambda it=item, idx=indice: self._elegir_color_superposicion(it, idx),
        )
        btn_c.pack(side="left", padx=(0, 4))
        item["_btn_color"] = btn_c

        # Checkbox visibilidad
        tk.Checkbutton(
            fila1, variable=item["visible"],
            bg=FONDO, selectcolor=FONDO2, activebackground=FONDO,
            command=self._redibujar,
        ).pack(side="left")

        # Botón eliminar
        tk.Button(
            fila1, text="✖", fg="#ff6666", bg=FONDO,
            activebackground=FONDO, relief="flat", cursor="hand2",
            font=("Courier New", 8),
            command=lambda idx=indice: self._eliminar_archivo(idx),
        ).pack(side="right", padx=2)

        # Fila 2: nombre del archivo (truncado)
        nombre = item["etiqueta"]
        if len(nombre) > 28:
            nombre = "…" + nombre[-26:]
        tk.Label(frame, text=nombre, bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 7), anchor="w").pack(
            fill="x", padx=6, pady=(0, 1))

        # Fila 3: Escala × y Offset
        fila_esc = tk.Frame(frame, bg=FONDO)
        fila_esc.pack(fill="x", padx=4, pady=(0, 1))

        tk.Label(fila_esc, text="×", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=2).pack(side="left")
        sp_esc = ttk.Spinbox(fila_esc, from_=-100.0, to=100.0, increment=0.5,
                             textvariable=item["escala_var"],
                             width=5, font=("Courier New", 8),
                             command=self._redibujar)
        sp_esc.pack(side="left", padx=2)
        sp_esc.bind("<Return>",   lambda e: self._redibujar())
        sp_esc.bind("<FocusOut>", lambda e: self._redibujar())

        tk.Label(fila_esc, text="+", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=2).pack(side="left", padx=(4, 0))
        sp_off = ttk.Spinbox(fila_esc, from_=-999.0, to=999.0, increment=0.5,
                             textvariable=item["offset_var"],
                             width=5, font=("Courier New", 8),
                             command=self._redibujar)
        sp_off.pack(side="left", padx=2)
        sp_off.bind("<Return>",   lambda e: self._redibujar())
        sp_off.bind("<FocusOut>", lambda e: self._redibujar())

    def _elegir_color_superposicion(self, item: dict, indice: int):
        """Abre el selector de color para un archivo de la superposición."""
        resultado = colorchooser.askcolor(
            color=item["color_override"], title="Color de la curva")
        if resultado and resultado[1]:
            item["color_override"] = resultado[1]
            if "_btn_color" in item:
                item["_btn_color"].config(bg=resultado[1])
            self._redibujar()

    def _eliminar_archivo(self, indice: int):
        """Elimina un archivo de la lista de superposición y reconstruye el panel."""
        if 0 <= indice < len(self._lista_archivos):
            self._lista_archivos.pop(indice)

        if not self._lista_archivos:
            self._limpiar_todo()
            return

        self._datos = self._lista_archivos[-1]["datos"]

        if len(self._lista_archivos) == 1:
            # Volver al panel normal
            datos = self._lista_archivos[0]["datos"]
            fmt   = datos.get("formato", "tiempo")
            if fmt in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
                self._construir_panel_bode(datos)
            else:
                self._construir_panel_canales(list(datos["canales"].keys()))
            self._label_archivo.config(
                text=datos["nombre_archivo"], fg=TEXTO)
        else:
            self._construir_panel_superposicion()
            self._label_archivo.config(
                text=f"{len(self._lista_archivos)} archivos  |  Superposición", fg="#88ff88")
        self._redibujar()

    # ================================================================== #
    #  Guardar PNG                                                         #
    # ================================================================== #

    def _guardar_png(self):
        if self._datos is None:
            messagebox.showinfo("Sin datos", "Primero cargá un archivo CSV.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("Todos", "*.*")],
            initialfile=self._datos["nombre_archivo"].replace(".csv", ".png"),
        )
        if ruta:
            self._graficador.guardar_figura(ruta)
            messagebox.showinfo("Guardado", f"Imagen guardada en:\n{ruta}")

    # ================================================================== #
    #  Drag & Drop                                                         #
    # ================================================================== #

    def _habilitar_drag_drop(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, evento):
        ruta = evento.data.strip()
        if ruta.startswith("{") and ruta.endswith("}"):
            ruta = ruta[1:-1]
        ruta = ruta.split("} {")[0].strip("{}")
        self._cargar_csv(ruta)


# ------------------------------------------------------------------ #
#  Helpers de grilla                                                   #
# ------------------------------------------------------------------ #

_PASOS_X = [0.001,0.002,0.005,0.01,0.02,0.05,0.1,0.2,0.5,
             1,2,5,10,20,50,100,200,500,1000]
_PASOS_Y = [0.001,0.002,0.005,0.01,0.02,0.05,0.1,0.2,0.5,
             1,2,5,10,20,50,100]

def _pasos_grilla(eje: str) -> list:
    return _PASOS_X if eje == "x" else _PASOS_Y

def _paso_desde_indice(idx, eje: str):
    if idx is None:
        return None
    return _pasos_grilla(eje)[idx]

def _label_paso(idx, pasos: list) -> str:
    if idx is None:
        return "Auto"
    v = pasos[idx]
    return str(int(v)) if v >= 1 and v == int(v) else str(v)