import os
import json
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from dotenv import load_dotenv
import google.generativeai as genai

# INIT ------------
load_dotenv()

gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)

app = FastAPI(title="Gasolineras IA API", version="1.0.0")
api_url = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"

# FUNCTIONS ------------
def parse_price(val):
    return float(val.replace(",", ".")) if val else None

def normalize_station(station):
    return {
        "id": station.get("IDEESS"),
        "label": station.get("Rótulo", None).strip(),
        "city": station.get("Municipio", None).strip(),
        "prov": station.get("Provincia", "").strip(),
        "cp": station.get("C.P.", None),
        "address": station.get("Dirección", None).strip(),
        "longitude": station.get("Longitud (WGS84)", None),
        "latitude": station.get("Latitud", None),
        "prices": {
            "adblue": parse_price(station.get("Precio Adblue", None)),
            "amoniaco": parse_price(station.get("Precio Amoniaco", None)),
            "biodiesel": parse_price(station.get("Precio Biodiesel", None)),
            "bioetanol": parse_price(station.get("Precio Bioetanol", None)),
            "biogas_natural_comprimido": parse_price(station.get("Precio Biogas Natural Comprimido", None)),
            "biogas_natural_licuado": parse_price(station.get("Precio Biogas Natural Licuado", None)),
            "diesel_renovable": parse_price(station.get("Precio Diésel Renovable", None)),
            "gas_natural_comprimido": parse_price(station.get("Precio Gas Natural Comprimido", None)),
            "gas_natural_licuado": parse_price(station.get("Precio Gas Natural Licuado", None)),
            "gases_licuados_del_petroleo": parse_price(station.get("Precio Gases licuados del petróleo", None)),
            "gasoleo_a": parse_price(station.get("Precio Gasoleo A", None)),
            "gasoleo_b": parse_price(station.get("Precio Gasoleo B", None)),
            "gasoleo_premium": parse_price(station.get("Precio Gasoleo Premium", None)),
            "gasolina_95_e10": parse_price(station.get("Precio Gasolina 95 E10", None)),
            "gasolina_95_e25": parse_price(station.get("Precio Gasolina 95 E25", None)),
            "gasolina_95_e5": parse_price(station.get("Precio Gasolina 95 E5", None)),
            "gasolina_95_e5_premium": parse_price(station.get("Precio Gasolina 95 E5 Premium", None)),
            "gasolina_95_e85": parse_price(station.get("Precio Gasolina 95 E85", None)),
            "gasolina_98_e10": parse_price(station.get("Precio Gasolina 98 E10", None)),
            "gasolina_98_e5": parse_price(station.get("Precio Gasolina 98 E5", None)),
            "gasolina_renovable": parse_price(station.get("Precio Gasolina Renovable", None)),
            "hidrogeno": parse_price(station.get("Precio Hidrogeno", None)),
            "metanol": parse_price(station.get("Precio Metanol", None)),
        },
        "hours": station.get("Horario", None).strip(),
    }


# ROUTES ------------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "FastAPI + Gemini on Vercel"}

@app.get("/api/stations/{prov}/report")
def get_province_ai_report(
    prov: str = "madrid", 
    gasoline_type: str = "gasolina_95_e5"
):

    response = requests.get(api_url)
    if response.status_code == 200:
        data = response.json()
        stationsFilter, error = [normalize_station(station) for station in data.get("ListaEESSPrecio", []) if station.get("Provincia", "").strip().lower() == prov.lower()], None
        if error:
            raise HTTPException(status_code=500, detail=error)

        if not stationsFilter:
            return {"error": f"No se encontraron estaciones en {prov}"}

        valid_stations = [s for s in stationsFilter if s["prices"].get(gasoline_type) is not None]
        top_baratas = sorted(valid_stations, key=lambda x: x["prices"][gasoline_type])[:10]

        prompt = f"""
        Eres un asistente experto en ahorro de combustible y analista de mercado.
        A continuación tienes un listado de las 10 gasolineras más baratas en la provincia de {prov.upper()} para el combustible '{gasoline_type}':

        {top_baratas}

        En formato JSON solo para parsear con json.loads:
        1. **best_option**: La mejor opción absoluta: Nombre, dirección, municipio, precio, horario y link en google maps.
        2. **alternative_options**: 2 opciones destacadas (por ejemplo, por horario 24h o marcas reconocidas).
        3. **saving_advice**: un breve comentario sobre la diferencia de precio entre la más barata y la más cara del TOP 10. También añade aquí cuantos km es factible recorrer para repostar en la más barata.
        4. **complete_info**: genera un informe breve y estructurado en español orientado al usuario final con los campos anteriores.

        Mantén un tono profesional, claro y directo.
        """

        try:
            model = genai.GenerativeModel("gemini-3.6-flash")
            ai_response = model.generate_content(prompt)

            return {
                "province": prov,
                "combustible_analizado": gasoline_type,
                "total_estaciones_provincia": len(stationsFilter),
                "ia": json.loads(ai_response.text),
                "top_10_estaciones": top_baratas
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al generar informe con IA: {str(e)}")

@app.get("/api/cron/update-data")
def cron_update_gas_stations(authorization: Optional[str] = Header(None)):
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="No autorizado")

    # TODO: BBDD
    return {"status": "success", "message": "Proceso de actualización ejecutado"}