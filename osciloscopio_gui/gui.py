"""
gui.py
------
Módulo principal de la interfaz gráfica.

Construye la ventana con:
  - Panel izquierdo: controles por canal (visibilidad, escala, offset, color)
  - Panel central:   área de graficado (matplotlib embebido)
  - Panel inferior:  opciones globales (grilla, escala log, máx/mín, modo XY)

Soporta:
  - Abrir CSV con botón o arrastrar y soltar (drag & drop)
  - Validación silenciosa de archivos no-CSV
  - Actualización en tiempo real de todos los parámetros
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import os

from lector_csv import leer_csv, ErrorCSV
from graficador import COLORES_DEFECTO
from graficador import Graficador


# ------------------------------------------------------------------ #
#  Colores del tema oscuro                                             #
# ------------------------------------------------------------------ #
FONDO        = "#1e1e2e"
FONDO2       = "#2a2a3e"
ACENTO       = "#7c7cff"
TEXTO        = "#cdd6f4"
TEXTO_DIMMED = "#888899"
BORDE        = "#444466"
BOTON_BG     = "#313244"
BOTON_HOVER  = "#45475a"


class AplicacionOsciloscopio:
    """
    Clase principal de la aplicación.
    Maneja la ventana, los widgets y la lógica de interacción.
    """

    def __init__(self, root: tk.Tk):
        """
        Inicializa la ventana principal y todos los widgets.

        Parámetros
        ----------
        root : tk.Tk
            La ventana raíz de tkinter.
        """
        self.root = root
        self.root.title("Osciloscopio CSV — TP Circuitos I")
        self.root.geometry("1300x750")
        self.root.configure(bg=FONDO)
        self.root.minsize(900, 600)

        # Datos cargados actualmente
        self._datos = None

        # Configuración dinámica por canal (se crea al cargar un CSV)
        self._vars_visibles = {}   # { nombre: BooleanVar }
        self._vars_escala   = {}   # { nombre: DoubleVar }
        self._vars_offset   = {}   # { nombre: DoubleVar }
        self._colores       = {}   # { nombre: str (hex) }

        # Configuración global
        self._var_grilla     = tk.BooleanVar(value=True)
        self._var_paso_x     = tk.StringVar(value="")
        self._var_paso_y     = tk.StringVar(value="")
        self._var_log_x      = tk.BooleanVar(value=False)
        self._var_log_y      = tk.BooleanVar(value=False)
        self._var_maxmin     = tk.BooleanVar(value=False)
        self._var_modo_xy    = tk.BooleanVar(value=False)
        self._var_canal_x_xy = tk.StringVar(value="")
        self._var_canal_y_xy = tk.StringVar(value="")

        # Construir la UI
        self._construir_ui()

        # Habilitar drag & drop si está disponible
        self._habilitar_drag_drop()

    # ================================================================== #
    #  Construcción de la interfaz                                        #
    # ================================================================== #

    def _construir_ui(self):
        """Construye todos los paneles de la ventana."""

        # ---- Barra superior ----
        self._construir_barra_superior()

        # ---- Contenedor principal (panel izquierdo + área de gráfico) ----
        contenedor = tk.Frame(self.root, bg=FONDO)
        contenedor.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Panel izquierdo: controles de canales
        self._panel_canales = tk.Frame(contenedor, bg=FONDO2, width=260,
                                       relief="flat", bd=0)
        self._panel_canales.pack(side="left", fill="y", padx=(0, 6))
        self._panel_canales.pack_propagate(False)
        self._construir_panel_canales_vacio()

        # Separador vertical
        sep = tk.Frame(contenedor, bg=BORDE, width=1)
        sep.pack(side="left", fill="y")

        # Panel derecho: gráfico + opciones globales
        panel_derecho = tk.Frame(contenedor, bg=FONDO)
        panel_derecho.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Área del gráfico
        self._frame_grafico = tk.Frame(panel_derecho, bg=FONDO)
        self._frame_grafico.pack(fill="both", expand=True)

        # Opciones globales inferiores
        self._construir_panel_opciones(panel_derecho)

        # Crear graficador
        self._graficador = Graficador(self._frame_grafico)

    def _construir_barra_superior(self):
        """Crea la barra con el botón de abrir y el nombre del archivo."""
        barra = tk.Frame(self.root, bg=FONDO2, height=48)
        barra.pack(fill="x", padx=0, pady=0)
        barra.pack_propagate(False)

        # Logo / título
        tk.Label(barra, text="📊  Visor CSV", bg=FONDO2,
                 fg=ACENTO, font=("Courier New", 13, "bold")).pack(side="left", padx=14)

        # Botón abrir archivo
        btn_abrir = tk.Button(
            barra, text="📂  Abrir CSV",
            command=self._abrir_archivo,
            bg=BOTON_BG, fg=TEXTO,
            activebackground=BOTON_HOVER, activeforeground=TEXTO,
            relief="flat", bd=0, padx=14, pady=6,
            font=("Courier New", 10),
            cursor="hand2",
        )
        btn_abrir.pack(side="left", padx=8, pady=8)

        # Botón guardar imagen
        btn_guardar = tk.Button(
            barra, text="💾  Guardar PNG",
            command=self._guardar_png,
            bg=BOTON_BG, fg=TEXTO,
            activebackground=BOTON_HOVER, activeforeground=TEXTO,
            relief="flat", bd=0, padx=14, pady=6,
            font=("Courier New", 10),
            cursor="hand2",
        )
        btn_guardar.pack(side="left", padx=4, pady=8)

        # Label con nombre de archivo actual
        self._label_archivo = tk.Label(
            barra, text="Ningún archivo cargado",
            bg=FONDO2, fg=TEXTO_DIMMED,
            font=("Courier New", 9),
        )
        self._label_archivo.pack(side="left", padx=16)

        # Instrucción drag & drop
        tk.Label(barra, text="(o arrastrá y soltá el .csv aquí)",
                 bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="right", padx=12)

    def _construir_panel_canales_vacio(self):
        """Muestra un mensaje cuando no hay archivo cargado."""
        for widget in self._panel_canales.winfo_children():
            widget.destroy()

        tk.Label(
            self._panel_canales,
            text="Canales",
            bg=FONDO2, fg=ACENTO,
            font=("Courier New", 11, "bold"),
        ).pack(pady=(14, 4), padx=10, anchor="w")

        tk.Label(
            self._panel_canales,
            text="Cargá un CSV para\nver los controles",
            bg=FONDO2, fg=TEXTO_DIMMED,
            font=("Courier New", 9),
            justify="left",
        ).pack(pady=20, padx=10, anchor="w")

    def _construir_panel_canales(self, nombres_canales: list):
        """
        Construye los controles dinámicos por canal.
        Se llama cada vez que se carga un nuevo CSV.
        """
        for widget in self._panel_canales.winfo_children():
            widget.destroy()

        # Reiniciar variables de canal
        self._vars_visibles = {}
        self._vars_escala   = {}
        self._vars_offset   = {}
        self._colores       = {}

        # Título
        tk.Label(
            self._panel_canales, text="Canales",
            bg=FONDO2, fg=ACENTO,
            font=("Courier New", 11, "bold"),
        ).pack(pady=(10, 4), padx=10, anchor="w")

        # Scrollable frame para muchos canales
        canvas_scroll = tk.Canvas(self._panel_canales, bg=FONDO2,
                                   highlightthickness=0)
        scrollbar = ttk.Scrollbar(self._panel_canales,
                                   orient="vertical", command=canvas_scroll.yview)
        frame_scroll = tk.Frame(canvas_scroll, bg=FONDO2)

        frame_scroll.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(
                scrollregion=canvas_scroll.bbox("all"))
        )
        canvas_scroll.create_window((0, 0), window=frame_scroll, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Un bloque de controles por cada canal
        for i, nombre in enumerate(nombres_canales):
            color_defecto = COLORES_DEFECTO[i % len(COLORES_DEFECTO)]
            self._colores[nombre]       = color_defecto
            self._vars_visibles[nombre] = tk.BooleanVar(value=True)
            self._vars_escala[nombre]   = tk.DoubleVar(value=1.0)
            self._vars_offset[nombre]   = tk.DoubleVar(value=0.0)

            self._crear_bloque_canal(frame_scroll, nombre, i)

        # Actualizar XY dropdowns
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

    def _crear_bloque_canal(self, parent, nombre: str, indice: int):
        """
        Crea el bloque visual de controles para un canal individual.
        Incluye: checkbox visibilidad, escala, offset, botón de color.
        """
        frame = tk.Frame(parent, bg=FONDO, relief="flat",
                         bd=1, highlightbackground=BORDE,
                         highlightthickness=1)
        frame.pack(fill="x", padx=8, pady=5, ipady=4)

        # --- Fila 1: visibilidad + nombre + color ---
        fila1 = tk.Frame(frame, bg=FONDO)
        fila1.pack(fill="x", padx=6, pady=(4, 2))

        # Indicador de color (cuadrado clickeable)
        color = self._colores[nombre]
        btn_color = tk.Button(
            fila1, bg=color, width=2, height=1,
            relief="flat", bd=0, cursor="hand2",
            command=lambda n=nombre: self._elegir_color(n),
        )
        btn_color.pack(side="left", padx=(0, 6))
        # Guardar referencia para actualizar color luego
        setattr(self, f"_btn_color_{nombre}", btn_color)

        # Checkbox de visibilidad
        chk = tk.Checkbutton(
            fila1, text=f"Canal {nombre}",
            variable=self._vars_visibles[nombre],
            bg=FONDO, fg=TEXTO,
            selectcolor=FONDO2, activebackground=FONDO,
            font=("Courier New", 9, "bold"),
            command=self._redibujar,
        )
        chk.pack(side="left")

        # --- Fila 2: Escala ---
        fila2 = tk.Frame(frame, bg=FONDO)
        fila2.pack(fill="x", padx=6, pady=2)

        tk.Label(fila2, text="Escala ×", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")

        spin_escala = ttk.Spinbox(
            fila2,
            from_=-100.0, to=100.0, increment=0.5,
            textvariable=self._vars_escala[nombre],
            width=7, font=("Courier New", 9),
            command=self._redibujar,
        )
        spin_escala.pack(side="left", padx=4)
        spin_escala.bind("<Return>", lambda e: self._redibujar())
        spin_escala.bind("<FocusOut>", lambda e: self._redibujar())

        # --- Fila 3: Offset ---
        fila3 = tk.Frame(frame, bg=FONDO)
        fila3.pack(fill="x", padx=6, pady=(2, 4))

        tk.Label(fila3, text="Offset", bg=FONDO, fg=TEXTO_DIMMED,
                 font=("Courier New", 8), width=8, anchor="w").pack(side="left")

        spin_offset = ttk.Spinbox(
            fila3,
            from_=-999.0, to=999.0, increment=0.5,
            textvariable=self._vars_offset[nombre],
            width=7, font=("Courier New", 9),
            command=self._redibujar,
        )
        spin_offset.pack(side="left", padx=4)
        spin_offset.bind("<Return>", lambda e: self._redibujar())
        spin_offset.bind("<FocusOut>", lambda e: self._redibujar())

    def _construir_panel_opciones(self, parent):
        """Crea el panel inferior con las opciones globales del gráfico."""
        panel = tk.Frame(parent, bg=FONDO2, height=70)
        panel.pack(fill="x", pady=(6, 0))
        panel.pack_propagate(False)

        # ---- Grilla ----
        tk.Checkbutton(
            panel, text="Grilla",
            variable=self._var_grilla,
            bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
            activebackground=FONDO2, font=("Courier New", 9),
            command=self._redibujar,
        ).pack(side="left", padx=(12, 4), pady=10)

        # Paso X
        tk.Label(panel, text="Paso X:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        entry_px = tk.Entry(panel, textvariable=self._var_paso_x,
                            width=5, bg=BOTON_BG, fg=TEXTO,
                            insertbackground=TEXTO, relief="flat",
                            font=("Courier New", 9))
        entry_px.pack(side="left", padx=4)
        entry_px.bind("<Return>", lambda e: self._redibujar())

        # Paso Y
        tk.Label(panel, text="Paso Y:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left", padx=(8, 0))
        entry_py = tk.Entry(panel, textvariable=self._var_paso_y,
                            width=5, bg=BOTON_BG, fg=TEXTO,
                            insertbackground=TEXTO, relief="flat",
                            font=("Courier New", 9))
        entry_py.pack(side="left", padx=4)
        entry_py.bind("<Return>", lambda e: self._redibujar())

        # Separador
        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y",
                                                 padx=10, pady=6)

        # Escala logarítmica X
        tk.Checkbutton(
            panel, text="Log X",
            variable=self._var_log_x,
            bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
            activebackground=FONDO2, font=("Courier New", 9),
            command=self._redibujar,
        ).pack(side="left", padx=4)

        # Escala logarítmica Y
        tk.Checkbutton(
            panel, text="Log Y",
            variable=self._var_log_y,
            bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
            activebackground=FONDO2, font=("Courier New", 9),
            command=self._redibujar,
        ).pack(side="left", padx=4)

        # Separador
        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y",
                                                 padx=10, pady=6)

        # Máx/Mín
        tk.Checkbutton(
            panel, text="Marcar Máx/Mín",
            variable=self._var_maxmin,
            bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
            activebackground=FONDO2, font=("Courier New", 9),
            command=self._redibujar,
        ).pack(side="left", padx=4)

        # Separador
        tk.Frame(panel, bg=BORDE, width=1).pack(side="left", fill="y",
                                                 padx=10, pady=6)

        # Modo XY (Lissajous)
        tk.Checkbutton(
            panel, text="Modo XY",
            variable=self._var_modo_xy,
            bg=FONDO2, fg=TEXTO, selectcolor=FONDO,
            activebackground=FONDO2, font=("Courier New", 9),
            command=self._redibujar,
        ).pack(side="left", padx=4)

        tk.Label(panel, text="X:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_x = tk.OptionMenu(
            panel, self._var_canal_x_xy, "",
        )
        self._menu_canal_x.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER,
                                   font=("Courier New", 8))
        self._menu_canal_x.pack(side="left", padx=2)

        tk.Label(panel, text="Y:", bg=FONDO2, fg=TEXTO_DIMMED,
                 font=("Courier New", 8)).pack(side="left")
        self._menu_canal_y = tk.OptionMenu(
            panel, self._var_canal_y_xy, "",
        )
        self._menu_canal_y.config(bg=BOTON_BG, fg=TEXTO, relief="flat",
                                   activebackground=BOTON_HOVER,
                                   font=("Courier New", 8))
        self._menu_canal_y.pack(side="left", padx=2)

        # Botón redibujar manual
        tk.Button(
            panel, text="↺ Actualizar",
            command=self._redibujar,
            bg=ACENTO, fg="#ffffff",
            activebackground="#9999ff", activeforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=4,
            font=("Courier New", 9), cursor="hand2",
        ).pack(side="right", padx=12, pady=10)

        # Tip cursores
        tk.Label(
            panel,
            text="Clic derecho en el gráfico: colocar cursores (2 max.)",
            bg=FONDO2, fg=TEXTO_DIMMED,
            font=("Courier New", 7),
        ).pack(side="right", padx=8)

    # ================================================================== #
    #  Lógica de apertura de archivos                                      #
    # ================================================================== #

    def _abrir_archivo(self):
        """Abre el diálogo para seleccionar un archivo CSV."""
        ruta = filedialog.askopenfilename(
            title="Abrir archivo CSV de osciloscopio",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            self._cargar_csv(ruta)

    def _cargar_csv(self, ruta: str):
        """
        Intenta cargar el CSV dado. Si falla, muestra un mensaje de error
        sin crashear la aplicación.
        """
        try:
            datos = leer_csv(ruta)
        except ErrorCSV as e:
            # Error esperado (formato incorrecto, no es CSV, etc.)
            messagebox.showerror(
                "Archivo inválido",
                f"No se pudo cargar el archivo:\n\n{e}",
            )
            return
        except Exception as e:
            # Error inesperado
            messagebox.showerror(
                "Error inesperado",
                f"Ocurrió un error al leer el archivo:\n\n{e}",
            )
            return

        # Guardar datos y actualizar UI
        self._datos = datos
        self._label_archivo.config(
            text=f"Archivo: {datos['nombre_archivo']}  |  "
                 f"{len(datos['canales'])} canal(es)  |  "
                 f"{len(datos['tiempo'])} muestras",
            fg=TEXTO,
        )

        # Reconstruir panel de canales
        self._construir_panel_canales(list(datos["canales"].keys()))

        # Graficar
        self._redibujar()

    # ================================================================== #
    #  Redibujar                                                           #
    # ================================================================== #

    def _redibujar(self):
        """Recolecta la configuración actual y actualiza el gráfico."""
        if self._datos is None:
            return

        # Parsear paso de grilla (puede estar vacío)
        try:
            paso_x = float(self._var_paso_x.get()) if self._var_paso_x.get().strip() else None
        except ValueError:
            paso_x = None
        try:
            paso_y = float(self._var_paso_y.get()) if self._var_paso_y.get().strip() else None
        except ValueError:
            paso_y = None

        config = {
            "canales_visibles":   {n: v.get() for n, v in self._vars_visibles.items()},
            "escala":             {n: v.get() for n, v in self._vars_escala.items()},
            "offset":             {n: v.get() for n, v in self._vars_offset.items()},
            "colores":            dict(self._colores),
            "grilla":             self._var_grilla.get(),
            "paso_grilla_x":      paso_x,
            "paso_grilla_y":      paso_y,
            "eje_x_log":          self._var_log_x.get(),
            "eje_y_log":          self._var_log_y.get(),
            "mostrar_maxmin":     self._var_maxmin.get(),
            "modo_xy":            self._var_modo_xy.get(),
            "canal_x_lissajous":  self._var_canal_x_xy.get(),
            "canal_y_lissajous":  self._var_canal_y_xy.get(),
        }

        self._graficador.actualizar(self._datos, config)

    # ================================================================== #
    #  Elegir color                                                        #
    # ================================================================== #

    def _elegir_color(self, nombre: str):
        """
        Abre el selector de color para el canal dado y actualiza el gráfico.
        """
        color_actual = self._colores.get(nombre, "#ffffff")
        resultado = colorchooser.askcolor(color=color_actual,
                                          title=f"Color para canal {nombre}")
        if resultado and resultado[1]:
            nuevo_color = resultado[1]
            self._colores[nombre] = nuevo_color
            # Actualizar el botón de color
            btn = getattr(self, f"_btn_color_{nombre}", None)
            if btn:
                btn.config(bg=nuevo_color)
            self._redibujar()

    # ================================================================== #
    #  Guardar PNG                                                         #
    # ================================================================== #

    def _guardar_png(self):
        """Exporta la figura actual como imagen PNG."""
        if self._datos is None:
            messagebox.showinfo("Sin datos", "Primero cargá un archivo CSV.")
            return

        ruta = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("Imagen PNG", "*.png"), ("Todos los archivos", "*.*")],
            initialfile=self._datos["nombre_archivo"].replace(".csv", ".png"),
        )
        if ruta:
            self._graficador.guardar_figura(ruta)
            messagebox.showinfo("Guardado", f"Imagen guardada en:\n{ruta}")

    # ================================================================== #
    #  Drag & Drop                                                         #
    # ================================================================== #

    def _habilitar_drag_drop(self):
        """
        Intenta habilitar drag & drop usando tkinterdnd2.
        Si no está instalado, lo ignora silenciosamente.
        """
        try:
            # tkinterdnd2 es una librería opcional
            from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            # Si no está disponible, simplemente no hay drag & drop
            pass

    def _on_drop(self, evento):
        """
        Maneja el evento de soltar un archivo sobre la ventana.
        Soporta múltiples archivos (usa solo el primero).
        """
        # El evento.data puede contener múltiples rutas entre llaves
        ruta_raw = evento.data.strip()

        # En Windows las rutas con espacios van entre llaves: {C:/mi archivo.csv}
        if ruta_raw.startswith("{") and ruta_raw.endswith("}"):
            ruta_raw = ruta_raw[1:-1]

        # Si hay múltiples rutas, tomar la primera
        ruta = ruta_raw.split("} {")[0].strip("{}")

        self._cargar_csv(ruta)