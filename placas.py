import os
import sys
import time
import json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

CARPETA_SALIDA = os.path.join(base_dir, "placas_mapa")
os.makedirs(CARPETA_SALIDA, exist_ok=True)

ANCHO_PLACA = 1080
ALTO_PLACA = 1350

COLOR_FONDO = (15, 23, 42)
COLOR_TEXTO = (255, 255, 255)
COLOR_SUBTEXTO = (148, 163, 184)
COLOR_ALERTA_AMARILLO = (234, 179, 8)
COLOR_ALERTA_NARANJA = (249, 115, 22)
COLOR_ALERTA_ROJO = (239, 68, 68)

ENCABEZADO_ALTO = 200
MAPA_ALTO = 780
FOOTER_ALTO = 370

def obtener_fuente(tamano, bold=False):
    fuentes_posibles = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "DejaVuSans.ttf",
        "arial.ttf"
    ]
    for ruta in fuentes_posibles:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                continue
    return ImageFont.load_default()

def procesar_generacion(idx_dia):
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()

    f0 = base_fecha
    f1 = base_fecha + timedelta(days=1)
    f2 = base_fecha + timedelta(days=2)

    labels = [
        f"{dias_semana[f0.weekday()]} {f0.day}",
        f"{dias_semana[f1.weekday()]} {f1.day}",
        f"{dias_semana[f2.weekday()]} {f2.day}"
    ]

    dia_elegido = labels[idx_dia]
    prefijos_arch = {0: "Hoy", 1: "Manana", 2: "Pasado"}
    prefijo = prefijos_arch[idx_dia]

    print(f"\n[+] Conectando al SMN para {dia_elegido.upper()}...")

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "security.mixed_content.block_active_content": False,
                "security.mixed_content.block_display_content": False,
                "dom.webdriver.enabled": False
            }
        )
        context = browser.new_context(
            viewport={"width": 720, "height": 1100},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            locale="es-AR"
        )
        page = context.new_page()
        page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        url_smn = "https://www.smn.gob.ar/alertas"
        try:
            page.goto(url_smn, wait_until="networkidle", timeout=60000)
            time.sleep(5)
        except Exception as e:
            print(f"[-] Error al cargar {url_smn}: {e}")

        if idx_dia > 0:
            try:
                botones_dias = page.query_selector_all("button.btn-dia, .nav-item button, .nav-tabs button")
                if len(botones_dias) > idx_dia:
                    botones_dias[idx_dia].click()
                    time.sleep(4)
            except Exception as e:
                print(f"[-] No se pudo alternar el botón de día en web: {e}")

        regiones = ["Norte", "Centro", "Sur"]
        for region in regiones:
            nombre_salida = f"Alerta_{prefijo}_{region}.png"
            ruta_salida = os.path.join(CARPETA_SALIDA, nombre_salida)

            captura_temporal = os.path.join(base_dir, f"temp_{nombre_salida}")
            try:
                mapa_elem = page.query_selector("#mapa, #map, .leaflet-container")
                if mapa_elem:
                    mapa_elem.screenshot(path=captura_temporal)
                else:
                    page.screenshot(path=captura_temporal)
            except Exception as e:
                print(f"[-] Falló la captura de {nombre_salida}: {e}")
                page.screenshot(path=captura_temporal)

            img_final = Image.new("RGB", (ANCHO_PLACA, ALTO_PLACA), COLOR_FONDO)
            draw = ImageDraw.Draw(img_final)

            font_titulo = obtener_fuente(46, bold=True)
            font_sub = obtener_fuente(28, bold=False)
            draw.text((50, 40), f"SISTEMA DE ALERTA TEMPRANA - {dia_elegido.upper()}", font=font_titulo, fill=COLOR_TEXTO)
            draw.text((50, 110), f"Región: {region} | Servicio Meteorológico Nacional", font=font_sub, fill=COLOR_SUBTEXTO)

            if os.path.exists(captura_temporal):
                try:
                    with Image.open(captura_temporal) as map_img:
                        map_img = map_img.resize((ANCHO_PLACA - 100, MAPA_ALTO), Image.Resampling.LANCZOS)
                        img_final.paste(map_img, (50, ENCABEZADO_ALTO))
                except Exception as e:
                    print(f"[-] Error montando mapa: {e}")
                finally:
                    if os.path.exists(captura_temporal):
                        os.remove(captura_temporal)

            font_footer = obtener_fuente(24, bold=False)
            draw.rectangle([(50, ENCABEZADO_ALTO + MAPA_ALTO + 20), (ANCHO_PLACA - 50, ALTO_PLACA - 40)], fill=(30, 41, 59))
            draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 40), "Niveles de Alerta:", font=obtener_fuente(26, bold=True), fill=COLOR_TEXTO)
            draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 90), "• Amarillo: Posibles fenómenos con capacidad de daño", font=font_footer, fill=COLOR_ALERTA_AMARILLO)
            draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 130), "• Naranja: Se esperan fenómenos peligrosos para la sociedad", font=font_footer, fill=COLOR_ALERTA_NARANJA)
            draw.text((70, ENCABEZADO_ALTO + MAPA_ALTO + 170), "• Rojo: Fenómenos excepcionales con potencial de provocar desastres", font=font_footer, fill=COLOR_ALERTA_ROJO)

            img_final.save(ruta_salida, format="PNG")
            print(f"[✓] Placa generada: {ruta_salida}")

        browser.close()

if __name__ == "__main__":
    for dia in range(3):
        procesar_generacion(dia)
