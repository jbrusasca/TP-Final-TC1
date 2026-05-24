"""
main.py
-------
Punto de entrada de la aplicación. 
Inicializa la ventana principal y arranca el loop de la GUI.
"""

import tkinter as tk
from gui import AplicacionOsciloscopio


def main():
    """Función principal: crea la ventana raíz y lanza la app."""
    root = tk.Tk()
    app = AplicacionOsciloscopio(root)
    root.mainloop()


if __name__ == "__main__":
    main()