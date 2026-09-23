"""
Estilos y paleta visual estilo Custos / macOS Dark Indigo Glassmorphism para Algor.
"""
from PyQt6.QtWidgets import QApplication

# Tamaño de fuente base por defecto cuando no hay override del usuario ni
# aplicación Qt disponible todavía (p. ej. al importar este módulo).
_FALLBACK_BASE_PT = 10


class Theme:
    # Colores Principales (Inspirados en la estética Custos)
    BG_DARK = "#0d0f1a"
    BG_PANEL = "#14172a"
    BG_CARD = "#191d34"
    BG_CARD_HOVER = "#232847"
    BG_INPUT = "#1b1f38"
    BG_PILL_CONTAINER = "#131627"
    
    # Bordes
    BORDER_SUBTLE = "#232742"
    BORDER_LIGHT = "#32385c"
    BORDER_ACCENT = "#5346e0"
    
    # Acentos (Indigo / Violeta Custos + Neones)
    INDIGO = "#5346e0"
    INDIGO_LIGHT = "#6366f1"
    INDIGO_HOVER = "#4338ca"
    MINT_GREEN = "#10b981"
    EMERALD = "#10b981"
    CYAN = "#00f0ff"
    PURPLE = "#8b5cf6"
    AMBER = "#f59e0b"
    CORAL = "#f43f5e"
    BLUE = "#3b82f6"
    
    # Textos
    TEXT_WHITE = "#ffffff"
    TEXT_TITLE = "#f1f3f9"
    TEXT_MUTED = "#8e92a8"
    TEXT_DIM = "#5a5e78"

    # Fuente monoespaciada para valores numéricos (estilo Custos)
    FONT_MONO = '"JetBrains Mono", "SF Mono", "Cascadia Code", Consolas, monospace'

    # Tamaño de fuente base en puntos elegido por el usuario en Ajustes.
    # None = automático: se usa el tamaño por defecto que Qt calculó para esta
    # pantalla (respeta QT_FONT_DPI y el factor de escala de texto del sistema).
    _override_pt: int | None = None

    @classmethod
    def set_font_override(cls, point_size: int | None) -> None:
        cls._override_pt = point_size

    @classmethod
    def base_pt(cls) -> int:
        """Tamaño base: el elegido en Ajustes o, si es automático, el que Qt
        ya calculó para esta pantalla al construir la QApplication."""
        if cls._override_pt:
            return cls._override_pt
        app = QApplication.instance()
        if app is not None:
            size = app.font().pointSize()
            if size > 0:
                return size
        return _FALLBACK_BASE_PT

    @classmethod
    def pt(cls, delta: int = 0) -> int:
        """Tamaño relativo al base, en puntos (escala con la DPI/el sistema
        porque `pt`, a diferencia de `px`, sí es DPI-aware en Qt Style Sheets)."""
        return max(7, cls.base_pt() + delta)

    @classmethod
    def build_stylesheet(cls) -> str:
        """Genera la hoja de estilo global. Se reconstruye (no se cachea) porque
        depende del tamaño de fuente, que puede cambiar en Ajustes."""
        return cls._stylesheet_template()

    @classmethod
    def _stylesheet_template(cls) -> str:
        base = cls.pt(0)
        title = cls.pt(5)
        return f"""
    QMainWindow {{
        background: transparent;
        color: {cls.TEXT_WHITE};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", sans-serif;
    }}

    QDialog {{
        background-color: {cls.BG_DARK};
        color: {cls.TEXT_WHITE};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", sans-serif;
    }}

    QWidget {{
        color: {cls.TEXT_WHITE};
        font-size: {base}pt;
    }}

    /* Contenedor raíz transparente: revela el escritorio en los márgenes de la ventana */
    QWidget#Root {{
        background: transparent;
    }}

    /* Tarjeta flotante "glass" que envuelve toda la interfaz, estilo Custos */
    QFrame#Glass {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(19, 22, 39, 250),
            stop:0.55 rgba(13, 15, 26, 250),
            stop:1 rgba(24, 20, 42, 250));
        border: 1px solid rgba(255, 255, 255, 30);
        border-radius: 22px;
    }}

    /* Tarjetas de fondo Glass con bordes redondeados */
    QFrame#Card {{
        background-color: {cls.BG_PANEL};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 14px;
    }}

    QFrame#Card:hover {{
        border: 1px solid {cls.BORDER_LIGHT};
    }}

    QFrame#InnerCard {{
        background-color: {cls.BG_CARD};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 12px;
    }}

    /* Contenedor Segmentado de Pestañas / Pastilla */
    QFrame#SegmentedContainer {{
        background-color: {cls.BG_PILL_CONTAINER};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 12px;
        padding: 4px;
    }}

    /* Botones Normales */
    QPushButton {{
        background-color: {cls.BG_CARD};
        color: {cls.TEXT_TITLE};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: {base}pt;
    }}

    QPushButton:hover {{
        background-color: {cls.BG_CARD_HOVER};
        border-color: {cls.INDIGO_LIGHT};
        color: {cls.TEXT_WHITE};
    }}

    QPushButton:pressed {{
        background-color: #101222;
    }}

    /* Botón Primario Estilo Custos con Gradiente Azul a Violeta */
    QPushButton#PrimaryBtn {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:0.5 #5b5bf0, stop:1 #8b5cf6);
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: bold;
        font-size: {base}pt;
    }}

    QPushButton#PrimaryBtn:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:0.5 #4f46e5, stop:1 #7c3aed);
    }}

    QPushButton#PrimaryBtn:pressed {{
        background: #4338ca;
    }}

    /* Botones de Perfil / Pastilla Activa Estilo Custos (Pill Button) */
    QPushButton#PillActive, QPushButton#ActiveProfileBtn {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #5e5ce6);
        color: #ffffff;
        border: 1px solid #6366f1;
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 700;
    }}

    QPushButton#PillInactive {{
        background-color: transparent;
        color: {cls.TEXT_MUTED};
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
    }}

    QPushButton#PillInactive:hover {{
        background-color: {cls.BG_CARD};
        color: {cls.TEXT_WHITE};
        border: 1px solid {cls.BORDER_SUBTLE};
    }}

    /* Nota: los botones semáforo (cerrar/minimizar/maximizar) ya no usan QPushButton+QSS
       — se pintan directamente con QPainter en TrafficLightButton (main_window.py),
       porque el estilo nativo Breeze no rellenaba de forma confiable botones QSS tan
       pequeños. Ver esa clase para sus colores. */

    /* Barra de Navegación Segmentada estilo Custos (Tabs) */
    QTabWidget::pane {{
        border: none;
        background: transparent;
        padding-top: 6px;
    }}

    QTabBar {{
        background-color: {cls.BG_PILL_CONTAINER};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 12px;
        qproperty-drawBase: 0;
        padding: 3px;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {cls.TEXT_MUTED};
        padding: 8px 18px;
        font-size: {base}pt;
        font-weight: 600;
        border-radius: 9px;
        margin: 2px 3px;
        border: none;
    }}

    QTabBar::tab:hover {{
        color: {cls.TEXT_WHITE};
        background: {cls.BG_CARD};
    }}

    QTabBar::tab:selected {{
        color: #ffffff;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #5e5ce6);
        font-weight: 700;
        border: 1px solid #6366f1;
    }}

    /* Sliders Modernos Estilo Custos */
    QSlider::groove:horizontal {{
        border: 1px solid {cls.BORDER_SUBTLE};
        height: 6px;
        background: {cls.BG_INPUT};
        border-radius: 3px;
    }}

    QSlider::sub-page:horizontal {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #5b5bf0);
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background: {cls.TEXT_WHITE};
        border: 3px solid #5b5bf0;
        width: 18px;
        margin-top: -6px;
        margin-bottom: -6px;
        border-radius: 9px;
    }}

    QSlider::handle:horizontal:hover {{
        background: #ffffff;
        border-color: #7c3aed;
    }}

    /* CheckBox estilo Custos */
    QCheckBox {{
        spacing: 10px;
        color: {cls.TEXT_TITLE};
        font-size: {base}pt;
    }}

    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 1px solid {cls.BORDER_SUBTLE};
        background-color: {cls.BG_INPUT};
    }}

    QCheckBox::indicator:hover {{
        border-color: {cls.INDIGO_LIGHT};
    }}

    QCheckBox::indicator:checked {{
        background-color: #5d5fef;
        border: 1px solid #6366f1;
        image: none;
    }}

    /* QScrollArea transparente (evita el fondo claro por defecto de Qt) */
    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    /* Scrollbars elegantes */
    QScrollBar:vertical {{
        border: none;
        background: {cls.BG_DARK};
        width: 8px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical {{
        background: {cls.BORDER_LIGHT};
        border-radius: 4px;
        min-height: 20px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {cls.INDIGO_LIGHT};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* ComboBox */
    QComboBox {{
        background-color: {cls.BG_INPUT};
        border: 1px solid {cls.BORDER_SUBTLE};
        border-radius: 10px;
        padding: 6px 14px;
        color: {cls.TEXT_TITLE};
        min-height: 26px;
    }}

    QComboBox:hover {{
        border-color: {cls.BORDER_LIGHT};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {cls.BG_PANEL};
        border: 1px solid {cls.BORDER_SUBTLE};
        selection-background-color: {cls.BG_CARD_HOVER};
        selection-color: #ffffff;
        color: {cls.TEXT_WHITE};
        padding: 4px;
        border-radius: 8px;
    }}

    /* Etiquetas */
    QLabel {{
        color: {cls.TEXT_TITLE};
    }}

    QLabel#Title {{
        font-size: {title}pt;
        font-weight: bold;
        color: {cls.TEXT_WHITE};
    }}

    QLabel#Subtitle {{
        font-size: {base}pt;
        color: {cls.TEXT_MUTED};
    }}
    """
