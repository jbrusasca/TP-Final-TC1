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
COLOR_CX1 = "#C99700"
COLOR_CX2 = "#E8590C"
COLOR_CY1 = "#00897B"
COLOR_CY2 = "#D6336C"


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
        self._var_log_x      = tk.BooleanVar(value=False)
        self._var_log_y      = tk.BooleanVar(value=False)
        self._var_maxmin     = tk.BooleanVar(value=False)
        self._var_modo_xy    = tk.BooleanVar(value=False)
        self._var_canal_x_xy = tk.StringVar(value="")
        self._var_canal_y_xy = tk.StringVar(value="")

        # ---- Título del gráfico (editable; vacío = sin título) ----
        self._var_titulo         = tk.StringVar(value="")
        self._var_mostrar_titulo = tk.BooleanVar(value=True)

        # ---- Nombres editables de las curvas: {canal: StringVar} ----
        self._vars_etiquetas = {}

        # ---- Estado del modo del panel izquierdo ----
        # "canales" o "cursores"
        self._modo_panel = "canales"

        # ---- Variables de cursores X (canal asignado) ----
        self._var_canal_cx = {1: tk.StringVar(value="—"),
                               2: tk.StringVar(value="—")}

        # ---- Labels de valores de cursor (se actualizan en tiempo real) ----
        self._lbl_cursor = {}   # se crean en _construir_panel_cursores

        self._construir_ui()

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

        tk.Button(barra, text="📄  Guardar PDF", command=self._guardar_pdf,
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
        if modo == "cursores":
            self._actualizar_estilo_tabs()
            for w in self._frame_contenido_panel.winfo_children():
                w.destroy()
            self._poblar_tab_cursores(self._frame_contenido_panel)
            return
        # Al volver a "Canales" se reconstruye el panel que corresponde al
        # archivo cargado (canales, bode o superposición). Las variables de
        # cada curva se conservan, así no se pierde lo que el usuario configuró.
        self._reconstruir_panel_izquierdo()

    def _reconstruir_panel_izquierdo(self):
        """Arma el panel izquierdo según lo que haya cargado en ese momento."""
        if self._datos is None:
            self._mostrar_panel_vacio()
            return
        if len(self._lista_archivos) > 1:
            self._construir_panel_superposicion()
            return
        if self._datos.get("formato", "tiempo") in (FORMATO_AUTOBODE, FORMATO_LTSPICE):
            self._construir_panel_bode(self._datos)
        else:
            self._construir_panel_canales(list(self._datos["canales"].keys()))

    def _sincronizar_vars_curvas(self, claves: list, etiquetas: dict = None,
                                 colores: dict = None):
        """
        Deja listas las variables de cada curva (visibilidad, escala, offset,
        nombre y color) para las claves indicadas.

        Las que ya existen se conservan —así reconstruir el panel no borra lo
        que el usuario configuró— y las de curvas que ya no están se descartan.
        """
        etiquetas = etiquetas or {}
        colores   = colores or {}
        for dic in (self._vars_visibles, self._vars_escala, self._vars_offset,
                    self._vars_etiquetas, self._colores):
            for clave in list(dic):
                if clave not in claves:
                    del dic[clave]
        for i, clave in enumerate(claves):
            self._colores.setdefault(
                clave, colores.get(clave, COLORES_DEFECTO[i % len(COLORES_DEFECTO)]))
            self._vars_visibles.setdefault(clave,  tk.BooleanVar(value=True))
            self._vars_escala.setdefault(clave,    tk.DoubleVar(value=1.0))
            self._vars_offset.setdefault(clave,    tk.DoubleVar(value=0.0))
            self._vars_etiquetas.setdefault(
                clave, tk.StringVar(value=etiquetas.get(clave, clave)))

    # ------------------------------------------------------------------ #
    #  Tab CANALES                                                          #
    # ------------------------------------------------------------------ #

    def _construir_panel_canales(self, nombres_canales: list):
        """Reconstruye el panel izquierdo con tabs para un CSV de señales."""
        # Las variables se preparan antes de dibujar los bloques, que las usan
        self._sincronizar_vars_curvas(nombres_canales)

        contenido = self._construir_tabs_panel()
        self._modo_panel = "canales"
        self._actualizar_estilo_tabs()
        self._poblar_tab_canales(contenido)

        # Actualizar opciones de canal en cursores X
        self._nombres_canales_actuales = nombres_canales
        for n in (1, 2):
            self._var_canal_cx[n].set(nombres_canales[0] if nombres_canales else "—")

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

        # Fila 1b: nombre con el que aparece la curva en la leyenda
        fila_nom = tk.Frame(frame, bg=FONDO)
        fila_nom.pack(fill="x", padx=6, pady=2)
        tk.Label(fila_nom, text="Nombre", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")
        ent_nom = tk.Entry(fila_nom, textvariable=self._vars_etiquetas[nombre],
                           bg=FONDO2, fg=TEXTO, insertbackground=TEXTO,
                           relief="flat", font=("Courier New", 9), width=14)
        ent_nom.pack(side="left", padx=4, ipady=2)
        ent_nom.bind("<Return>",   lambda e: self._redibujar())
        ent_nom.bind("<FocusOut>", lambda e: self._redibujar())

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
        self._nombres_canales_actuales = ["ganancia"]
        if datos.get("fase_deg"):
            self._nombres_canales_actuales.append("fase")

        frecuencia = datos.get("frecuencia", [])
        ganancia   = datos.get("ganancia_db", [])
        fase       = datos.get("fase_deg", [])

        # ---- Curvas: color, activar/desactivar y nombre editable ----
        # En los Bode de LTSpice el nombre del nodo va en la leyenda
        nodo = datos.get("nombre_nodo", "")
        etq_ganancia = f"Ganancia — {nodo}" if nodo else "Ganancia (dB)"

        #        clave       texto del checkbox   nombre inicial de la curva
        curvas = [("ganancia", "Ganancia (dB)", etq_ganancia, COLORES_DEFECTO[0])]
        if fase:
            curvas.append(("fase", "Fase (°)", "Fase (°)", COLORES_DEFECTO[1]))

        tk.Label(contenido, text="Curvas", bg=FONDO2, fg=ACENTO,
                 font=("Courier New", 10, "bold")).pack(pady=(10, 4), padx=10, anchor="w")

        self._sincronizar_vars_curvas(
            [c[0] for c in curvas],
            etiquetas={c[0]: c[2] for c in curvas},
            colores={c[0]: c[3] for c in curvas},
        )
        for clave, texto_check, _etiqueta_inicial, _color in curvas:
            self._crear_bloque_curva_bode(contenido, clave, texto_check)

        tk.Frame(contenido, bg=BORDE, height=1).pack(fill="x", padx=10, pady=6)

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
                 text="Eje X logarítmico\npor defecto.\n\n"
                      "Usá el tab Cursores\npara medir valores.",
                 bg=FONDO2, fg=TEXTO_DIMMED, font=("Courier New", 8),
                 justify="left").pack(padx=14, pady=4, anchor="w")

        # Cursores de bode usan "ganancia" y "fase" como canales
        for n in (1, 2):
            self._var_canal_cx[n].set("ganancia")

    def _crear_bloque_curva_bode(self, parent, clave: str, nombre_visible: str):
        """
        Bloque de una curva del Bode (ganancia o fase) con:
        cuadrado de color, checkbox para mostrarla/ocultarla y nombre editable.
        """
        frame = tk.Frame(parent, bg=FONDO, highlightbackground=BORDE,
                         highlightthickness=1)
        frame.pack(fill="x", padx=8, pady=4, ipady=3)

        fila1 = tk.Frame(frame, bg=FONDO)
        fila1.pack(fill="x", padx=6, pady=(4, 2))

        btn = tk.Button(fila1, bg=self._colores[clave], width=2, height=1,
                        relief="flat", cursor="hand2",
                        command=lambda c=clave: self._elegir_color(c))
        btn.pack(side="left", padx=(0, 6))
        setattr(self, f"_btn_color_{clave}", btn)

        tk.Checkbutton(fila1, text=nombre_visible,
                       variable=self._vars_visibles[clave],
                       bg=FONDO, fg=TEXTO, selectcolor=FONDO2,
                       activebackground=FONDO, font=("Courier New", 9, "bold"),
                       command=self._redibujar).pack(side="left")

        fila2 = tk.Frame(frame, bg=FONDO)
        fila2.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(fila2, text="Nombre", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")
        ent = tk.Entry(fila2, textvariable=self._vars_etiquetas[clave],
                       bg=FONDO2, fg=TEXTO, insertbackground=TEXTO,
                       relief="flat", font=("Courier New", 9), width=14)
        ent.pack(side="left", padx=4, ipady=2)
        ent.bind("<Return>",   lambda e: self._redibujar())
        ent.bind("<FocusOut>", lambda e: self._redibujar())

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
        panel = tk.Frame(parent, bg=FONDO2, height=104)
        panel.pack(fill="x", pady=(6, 0))
        panel.pack_propagate(False)

        # Fila 1: opciones de graficado
        fila1 = tk.Frame(panel, bg=FONDO2)
        fila1.pack(fill="x")

        # Grilla
        tk.Checkbutton(fila1, text="Grilla", variable=self._var_grilla,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=(12, 4), pady=10)

        tk.Frame(fila1, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Log X / Y
        tk.Checkbutton(fila1, text="Log X", variable=self._var_log_x,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)
        tk.Checkbutton(fila1, text="Log Y", variable=self._var_log_y,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)

        tk.Frame(fila1, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Máx/Mín
        tk.Checkbutton(fila1, text="Marcar Máx/Mín", variable=self._var_maxmin,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)

        tk.Frame(fila1, bg=BORDE, width=1).pack(side="left", fill="y", padx=10, pady=6)

        # Modo XY
        tk.Checkbutton(fila1, text="Modo XY", variable=self._var_modo_xy,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=4)
        tk.Label(fila1, text="X:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_x = tk.OptionMenu(fila1, self._var_canal_x_xy, "")
        self._menu_canal_x.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER, font=("Courier New", 8))
        self._menu_canal_x.pack(side="left", padx=2)
        tk.Label(fila1, text="Y:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_y = tk.OptionMenu(fila1, self._var_canal_y_xy, "")
        self._menu_canal_y.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER, font=("Courier New", 8))
        self._menu_canal_y.pack(side="left", padx=2)

        # Botón actualizar
        tk.Button(fila1, text="↺ Actualizar", command=self._redibujar,
                  bg=ACENTO, fg="#ffffff", activebackground="#9999ff",
                  relief="flat", padx=10, pady=4,
                  font=("Courier New", 9), cursor="hand2").pack(side="right", padx=12, pady=10)

        # Fila 2: título del gráfico (editable y ocultable)
        fila2 = tk.Frame(panel, bg=FONDO2)
        fila2.pack(fill="x")

        tk.Checkbutton(fila2, text="Título:", variable=self._var_mostrar_titulo,
                       bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                       activebackground=FONDO2, font=("Courier New", 9),
                       command=self._redibujar).pack(side="left", padx=(12, 2))

        entrada_titulo = tk.Entry(fila2, textvariable=self._var_titulo,
                                  bg=FONDO, fg=TEXTO, insertbackground=TEXTO,
                                  relief="flat", font=("Courier New", 9))
        entrada_titulo.pack(side="left", padx=4, ipady=3, fill="x", expand=True)
        entrada_titulo.bind("<Return>",   lambda e: self._redibujar())
        entrada_titulo.bind("<FocusOut>", lambda e: self._redibujar())

        tk.Label(fila2, text="(vacío = sin título)", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left", padx=(4, 12))

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
            self._vars_visibles  = {}
            self._vars_escala    = {}
            self._vars_offset    = {}
            self._vars_etiquetas = {}
            self._colores        = {}
            # El título es del gráfico anterior: se arranca sin título
            self._var_titulo.set("")

        # Asignar color automático según posición en la lista
        idx_color = len(self._lista_archivos) % len(COLORES_DEFECTO)
        color     = COLORES_DEFECTO[idx_color]

        item = {
            "datos":          datos,
            "visible":        tk.BooleanVar(value=True),
            "color_override": color,
            "etiqueta":       datos["nombre_archivo"],
            # Nombre editable con el que el archivo aparece en la leyenda
            "etiqueta_var":   tk.StringVar(value=os.path.splitext(
                                  datos["nombre_archivo"])[0]),
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
            "eje_x_log":         self._var_log_x.get(),
            "eje_y_log":         self._var_log_y.get(),
            "mostrar_maxmin":    self._var_maxmin.get(),
            "modo_xy":           self._var_modo_xy.get(),
            "canal_x_lissajous": self._var_canal_x_xy.get(),
            "canal_y_lissajous": self._var_canal_y_xy.get(),
            "titulo":            self._var_titulo.get(),
            "mostrar_titulo":    self._var_mostrar_titulo.get(),
            "etiquetas":         {n: v.get() for n, v in self._vars_etiquetas.items()},
            # Superposición: lista de todos los archivos cargados
            "lista_archivos":    [
                {
                    "datos":    item["datos"],
                    "visible":  item["visible"].get(),
                    "color":    item["color_override"],
                    "etiqueta": item["etiqueta_var"].get() or item["etiqueta"],
                    "escala":   item["escala_var"].get(),
                    "offset":   item["offset_var"].get(),
                }
                for item in self._lista_archivos
            ],
        }
        self._graficador.actualizar(self._datos, config)

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
        self._vars_visibles  = {}
        self._vars_escala    = {}
        self._vars_offset    = {}
        self._vars_etiquetas = {}
        self._colores        = {}
        self._var_titulo.set("")
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

        # Si son Bodes, se pueden activar/desactivar ganancia y fase globalmente;
        # los canales de un archivo suelto no aplican en este modo.
        formato = (self._datos or {}).get("formato", "tiempo")
        es_bode = formato in (FORMATO_AUTOBODE, FORMATO_LTSPICE)
        self._sincronizar_vars_curvas(["ganancia", "fase"] if es_bode else [])

        if es_bode:
            tk.Label(contenido, text="Curvas", bg=FONDO2, fg=ACENTO,
                     font=("Courier New", 10, "bold")).pack(pady=(10, 2), padx=10,
                                                            anchor="w")
            fila_curvas = tk.Frame(contenido, bg=FONDO2)
            fila_curvas.pack(fill="x", padx=10, pady=(0, 4))
            for clave, texto in [("ganancia", "Ganancia"), ("fase", "Fase")]:
                tk.Checkbutton(fila_curvas, text=texto,
                               variable=self._vars_visibles[clave],
                               bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
                               activebackground=FONDO2, font=("Courier New", 9),
                               command=self._redibujar).pack(side="left", padx=(0, 8))

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

        # Fila 2: nombre con el que la curva aparece en la leyenda (editable)
        ent_nom = tk.Entry(frame, textvariable=item["etiqueta_var"],
                           bg=FONDO2, fg=TEXTO, insertbackground=TEXTO,
                           relief="flat", font=("Courier New", 8))
        ent_nom.pack(fill="x", padx=6, pady=(0, 2), ipady=2)
        ent_nom.bind("<Return>",   lambda e: self._redibujar())
        ent_nom.bind("<FocusOut>", lambda e: self._redibujar())

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
    #  Guardar / exportar el gráfico                                       #
    # ================================================================== #

    def _nombre_sugerido(self, extension: str) -> str:
        """Nombre por defecto para el archivo exportado, con la extensión dada."""
        base = os.path.splitext(self._datos["nombre_archivo"])[0]
        return base + extension

    def _guardar_png(self):
        """Exporta el gráfico como imagen de mapa de bits (PNG, 300 dpi)."""
        self._exportar(
            extension=".png",
            filetypes=[("PNG", "*.png"), ("Todos", "*.*")],
            titulo="Guardar gráfico como PNG",
        )

    def _guardar_pdf(self):
        """
        Exporta el gráfico en formato vectorial (PDF por defecto, SVG opcional).
        Al ser vectorial no pierde resolución al insertarlo en un informe, ni
        al ampliarlo o imprimirlo.
        """
        self._exportar(
            extension=".pdf",
            filetypes=[("PDF (vectorial)", "*.pdf"), ("SVG (vectorial)", "*.svg"),
                       ("Todos", "*.*")],
            titulo="Guardar gráfico como PDF",
        )

    def _exportar(self, extension: str, filetypes: list, titulo: str):
        """Lógica común de exportación: pide la ruta y guarda la figura."""
        if self._datos is None:
            messagebox.showinfo("Sin datos", "Primero cargá un archivo CSV.")
            return
        ruta = filedialog.asksaveasfilename(
            title=titulo,
            defaultextension=extension,
            filetypes=filetypes,
            initialfile=self._nombre_sugerido(extension),
        )
        if not ruta:
            return
        # Si el usuario escribió el nombre sin extensión, se usa la del botón.
        if not os.path.splitext(ruta)[1]:
            ruta += extension
        try:
            self._graficador.guardar_figura(ruta)
        except Exception as e:
            messagebox.showerror("Error al guardar",
                                 f"No se pudo guardar el archivo:\n{e}")
            return
        messagebox.showinfo("Guardado", f"Gráfico guardado en:\n{ruta}")


