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

ZONAS_CONFIG = [
    {
        "id": "Norte",
        "centro": [-25.5, -63.0],
        "zoom": 5.5
    },
    {
        "id": "Centro",
        "centro": [-33.8, -64.2],
        "zoom": 5.5
    },
    {
        "id": "Sur",
        "centro": [-44.5, -68.5],
        "zoom": 5.0
    }
]

def obtener_fuente(archivo, tamano):
    for f in [archivo, "arialbd.ttf" if "bd" in archivo else "arial.ttf", "segoeui.ttf"]:
        try:
            return ImageFont.truetype(f, tamano)
        except Exception:
            continue
    return ImageFont.load_default()

def armar_placa(img_path, zona_id, datos_alerta, idx_dia, labels_dias):
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    bar_x = w - 315
    bar_y = 12
    bar_w = 300
    bar_h = 40

    draw.rounded_rectangle([(bar_x - 1, bar_y - 1), (bar_x + bar_w + 1, bar_y + bar_h + 1)], radius=7, fill=(0, 0, 0, 45))
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=6, fill=(255, 255, 255, 255))
    font_tab = obtener_fuente("arialbd.ttf", 14)

    ancho_tab = int(bar_w / 3)

    for i in range(3):
        x_ini = bar_x + (i * ancho_tab)
        x_fin = x_ini + ancho_tab
        activo = (i == idx_dia)

        bg_col = (65, 139, 202) if activo else (255, 255, 255)
        tx_col = (255, 255, 255) if activo else (70, 70, 70)

        draw.rounded_rectangle([(x_ini + 2, bar_y + 2), (x_fin - 2, bar_y + bar_h - 2)], radius=5, fill=bg_col)

        txt = labels_dias[i]
        bbox_t = draw.textbbox((0, 0), txt, font=font_tab)
        tw = bbox_t[2] - bbox_t[0]
        th = bbox_t[3] - bbox_t[1]
        tx_pos = x_ini + (ancho_tab - tw) / 2 - bbox_t[0]
        ty_pos = bar_y + (bar_h - th) / 2 - bbox_t[1]
        draw.text((tx_pos, ty_pos), txt, font=font_tab, fill=tx_col)

        if i < 2 and not activo and (i + 1 != idx_dia):
            draw.line([(x_fin, bar_y + 7), (x_fin, bar_y + bar_h - 7)], fill=(220, 220, 220), width=1)

    nivel = datos_alerta.get("nivel", "VERDE").upper()
    tiene_alerta = (nivel in ["AMARILLO", "NARANJA", "ROJO"])

    if nivel == "ROJO":
        color_badge = (215, 45, 40)
        texto_badge_col = (255, 255, 255)
        texto_badge = "ROJO"
    elif nivel == "NARANJA":
        color_badge = (245, 130, 20)
        texto_badge_col = (20, 20, 20)
        texto_badge = "NARANJA"
    elif nivel == "AMARILLO":
        color_badge = (245, 190, 10)
        texto_badge_col = (20, 20, 20)
        texto_badge = "AMARILLO"
    else:
        color_badge = (46, 170, 100)
        texto_badge_col = (255, 255, 255)
        texto_badge = "SIN ALERTA"

    margen_x = 15
    z_h = 86
    z_y = h - z_h - 15
    x1, y1 = margen_x, z_y
    x2, y2 = w - margen_x, z_y + z_h

    draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=12, fill=(18, 24, 34, 245), outline=(55, 70, 90), width=2)

    b_w = 145
    b_h = 44
    b_x1 = x1 + 14
    b_y1 = y1 + int((z_h - b_h) / 2)
    b_x2 = b_x1 + b_w
    b_y2 = b_y1 + b_h

    draw.rounded_rectangle([(b_x1, b_y1), (b_x2, b_y2)], radius=7, fill=color_badge)
    font_badge = obtener_fuente("arialbd.ttf", 17 if len(texto_badge) > 8 else 18)
    bbox_b = draw.textbbox((0, 0), texto_badge, font=font_badge)
    tw_b = bbox_b[2] - bbox_b[0]
    th_b = bbox_b[3] - bbox_b[1]
    draw.text((b_x1 + (b_w - tw_b)/2 - bbox_b[0], b_y1 + (b_h - th_b)/2 - bbox_b[1]), texto_badge, font=font_badge, fill=texto_badge_col)

    area_texto_x = b_x2 + 18
    ancho_max = (x2 - 16) - area_texto_x

    if tiene_alerta:
        fenomenos = datos_alerta.get("fenomenos", "ALERTA METEOROLÓGICA")
        titulo = f"ALERTA POR {fenomenos.upper()} - REGIÓN {zona_id.upper()}"
        subtitulo = datos_alerta.get("descripcion", "Se esperan fenómenos con capacidad de daño")
    else:
        titulo = f"SIN ALERTAS VIGENTES - REGIÓN {zona_id.upper()}"
        subtitulo = "No se esperan fenómenos meteorológicos que impliquen riesgo"

    tam_tit = 21
    font_tit = obtener_fuente("arialbd.ttf", tam_tit)
    while tam_tit > 13:
        bbox_t = draw.textbbox((0, 0), titulo, font=font_tit)
        if (bbox_t[2] - bbox_t[0]) <= ancho_max:
            break
        tam_tit -= 1
        font_tit = obtener_fuente("arialbd.ttf", tam_tit)

    draw.text((area_texto_x, y1 + 17), titulo, font=font_tit, fill=(255, 255, 255))

    font_sub = obtener_fuente("arial.ttf", 16)
    bbox_s = draw.textbbox((0, 0), subtitulo, font=font_sub)
    if (bbox_s[2] - bbox_s[0]) > ancho_max:
        font_sub = obtener_fuente("arial.ttf", 14)

    draw.text((area_texto_x, y1 + 49), subtitulo, font=font_sub, fill=(195, 210, 230))
    return img

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

        page.goto("https://www.smn.gob.ar/alertas", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)

        if idx_dia > 0:
            target_el = page.locator(f"text='{dia_elegido}'").first
            if target_el.count() > 0:
                box = target_el.bounding_box()
                if box:
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            time.sleep(4)

        page.evaluate("""() => {
            let quitar = [
                'header', 'footer', '#navbar', '.navbar', '.region-header', 
                '#block-system-main > h1', '.breadcrumb',
                '.leaflet-top.leaflet-left .leaflet-control-layers',
                '.leaflet-top.leaflet-left .leaflet-bar:last-child',
                '.leaflet-top.leaflet-right'
            ];
            quitar.forEach(sel => {
                document.querySelectorAll(sel).forEach(e => e.style.display = 'none');
            });
            if (window.map) {
                let tileLabels = "https://wms.ign.gob.ar/geoserver/gwc/service/tms/1.0.0/capabaseargenmap@EPSG%3A3857@png/{z}/{x}/{-y}.png";
                L.tileLayer(tileLabels, { maxZoom: 18, opacity: 0.85, zIndex: 1000 }).addTo(window.map);
            }
        }""")
        time.sleep(2)

        for zona in ZONAS_CONFIG:
            zona_id = zona["id"]
            lat, lon = zona["centro"]
            zoom = zona["zoom"]

            page.evaluate(f"""() => {{
                if (window.map) {{
                    window.map.setView([{lat}, {lon}], {zoom});
                    window.map.invalidateSize();
                }}
            }}""")
            time.sleep(3)

            if idx_dia == 2:
                datos_alerta = {
                    "nivel": "VERDE",
                    "fenomenos": "SIN ALERTA",
                    "descripcion": "No se esperan fenómenos meteorológicos que impliquen riesgo"
                }
            elif idx_dia == 1:
                if zona_id == "Norte":
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "TORMENTAS", "descripcion": "Lluvias intensas, actividad eléctrica y ráfagas aisladas"}
                elif zona_id == "Centro":
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "TORMENTAS", "descripcion": "Lluvias intensas con ráfagas y ocasional granizo"}
                else:
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "VIENTOS FUERTES", "descripcion": "Vientos del oeste con ráfagas superiores a 80 km/h"}
            else:
                if zona_id == "Norte":
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "TORMENTAS", "descripcion": "Lluvias intensas, actividad eléctrica y ráfagas aisladas"}
                elif zona_id == "Centro":
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "TORMENTAS Y VIENTO ZONDA", "descripcion": "Tormentas al este | Zonda con polvo y baja visibilidad al oeste"}
                else:
                    datos_alerta = {"nivel": "AMARILLO", "fenomenos": "LLUVIAS", "descripcion": "Precipitaciones persistentes y abundantes sobre Chubut"}

            mapa_el = page.query_selector("#map") or page.query_selector(".leaflet-container")
            temp_img = f"temp_{zona_id}.png"
            if mapa_el:
                mapa_el.screenshot(path=temp_img)
            else:
                page.screenshot(path=temp_img)

            if os.path.exists(temp_img):
                img_final = armar_placa(temp_img, zona_id, datos_alerta, idx_dia, labels)
                nombre_archivo = f"Alerta_{prefijo}_{zona_id}.png"
                salida = os.path.join(CARPETA_SALIDA, nombre_archivo)
                img_final.save(salida)
                os.remove(temp_img)
                etiqueta = "SIN ALERTA" if datos_alerta["nivel"] == "VERDE" else datos_alerta["nivel"]
                print(f" -> Guardada: {nombre_archivo} [{etiqueta}]")

        browser.close()

    print(f"\n[OK] Placas listas en '{CARPETA_SALIDA}/'.")

def menu_principal():
    dias_semana = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
    base_fecha = datetime.now()
    d0 = f"{dias_semana[base_fecha.weekday()]} {base_fecha.day}"
    d1 = f"{dias_semana[(base_fecha + timedelta(days=1)).weekday()]} {(base_fecha + timedelta(days=1)).day}"
    d2 = f"{dias_semana[(base_fecha + timedelta(days=2)).weekday()]} {(base_fecha + timedelta(days=2)).day}"

    while True:
        print("\n" + "=" * 50)
        print("       SISTEMA DE GENERACIÓN DE ALERTAS SMN       ")
        print("=" * 50)
        print(f"1. Generar alertas para HOY ({d0})")
        print(f"2. Generar alertas para MAÑANA ({d1})")
        print(f"3. Generar alertas para PASADO MAÑANA ({d2})")
        print("4. Salir")
        print("-" * 50)
        op = input("Seleccione opción (1-4): ").strip()
        if op == "1":
            procesar_generacion(0)
        elif op == "2":
            procesar_generacion(1)
        elif op == "3":
            procesar_generacion(2)
        elif op == "4":
            print("Saliendo.")
            break
        else:
            print("Opción inválida.")

if __name__ == "__main__":
    menu_principal()
