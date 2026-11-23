"""Noticias de última hora: lee las Hot Stories / Latest Stories de Forex Factory y guarda solo las de
impacto ALTO (la carpeta roja) que afectan al Nasdaq en ultima-hora.json. Las que se añadieron a mano (sin "src") no se tocan.
Las guardadas no se borran nunca: sirven para el backtest."""
import json, re, html, sys, datetime as dt, urllib.request

URL = "https://www.forexfactory.com/news"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
MADRID = None
try:
    from zoneinfo import ZoneInfo
    MADRID = ZoneInfo("Europe/Madrid")
except Exception:
    pass

# Solo lo que mueve el Nasdaq: EEUU (Fed, Trump, datos, aranceles...), grandes tecnológicas/IA/chips,
# Banco de Japón y geopolítica gorda. Lo de otros países (UK, Europa, Canadá...) se descarta.
SI = re.compile(r"\b(fed|fomc|powell|warsh|federal reserve|treasur(y|ies)|bessent|trump|white house|wall street|nasdaq|s&p|dow jones|"
                r"united states|americans?|washington|congress|senate|shutdown|debt ceiling|tariffs?|sanctions?|trade war|"
                r"payrolls?|nfp|cpi|pce|ism|jobless|jobs report|"
                r"nvidia|nvda|apple|microsoft|amazon|alphabet|google|meta|tesla|broadcom|amd|tsmc|netflix|openai|anthropic|"
                r"ai|artificial intelligence|chips?|semiconductors?|tech stocks|"
                r"boj|bank of japan|china|chinese|beijing|xi jinping|taiwan|"
                r"war|invasion|missiles?|strikes?|attack|nuclear|iran|israel|russia|ukraine|opec|oil)\b", re.I)
EEUU = re.compile(r"(?<![A-Za-z])U\.?S\.?(?![A-Za-z])")   # "US", "U.S." (en mayúsculas, para no confundir con "us")
OTROS = re.compile(r"^(uk|eurozone|euro area|ecb|boe|germany|german|france|french|italy|spain|canada|canadian|australia|australian|rba|rbnz|"
                   r"new zealand|nz|snb|swiss|switzerland|sweden|norway|india|brazil|mexico|turkey|south africa)\b", re.I)

def importa(titulo):
    titulo = re.sub(r"\bU\.?S\.? ?dollar\b", "dollar", titulo, flags=re.I)   # "contra el dólar" no es noticia de EEUU
    if EEUU.search(titulo) or SI.search(titulo):
        # Titulares que empiezan por otro país solo cuentan si hablan claramente de EEUU
        if OTROS.search(titulo) and not EEUU.search(titulo) and not re.search(r"\b(fed|trump|tariffs?|nasdaq|wall street|united states)\b", titulo, re.I):
            return False
        return True
    return False

def descargar():
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")

def limpiar(t):
    t = t.replace("\\/", "/").replace('\\"', '"')
    t = html.unescape(html.unescape(t))
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", t).strip()

def historias(pagina):
    s = html.unescape(pagina)
    vistas = {}
    for m in re.finditer(r'"id":(\d+),"dateline":(\d+),"url":"([^"]+)","hit_url":"[^"]*","title":"((?:[^"\\]|\\.)*)"', s):
        cola = s[m.end():m.end() + 4000]
        imp = re.search(r'"impact":"([^"]*)"', cola)
        if not imp or imp.group(1) != "high":
            continue
        sid, t = int(m.group(1)), int(m.group(2))
        prev = vistas.get(sid)
        if prev and prev["t"] <= t:
            continue
        vistas[sid] = {"t": t, "url": "https://www.forexfactory.com" + m.group(3).replace("\\/", "/"), "title": limpiar(m.group(4))}
    return vistas

def main():
    try:
        pagina = descargar()
    except Exception as e:
        print("No se pudo descargar Forex Factory:", e); sys.exit(1)
    if '"dateline"' not in html.unescape(pagina):
        print("La página no trae noticias (¿bloqueo o cambio de web?)", len(pagina), pagina[:300].replace(chr(10), " ")); sys.exit(1)
    try:
        datos = json.load(open("ultima-hora.json", encoding="utf-8"))
    except Exception:
        datos = []
    ya = {x.get("ff_id") for x in datos if x.get("ff_id")}
    nuevas = 0
    for sid, h in historias(pagina).items():
        if sid in ya or not h["title"] or not importa(h["title"]):
            continue
        cuando = dt.datetime.fromtimestamp(h["t"], dt.timezone.utc)
        local = cuando.astimezone(MADRID) if MADRID else cuando
        datos.append({"date": local.date().isoformat(), "ts": cuando.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "title": h["title"], "url": h["url"], "ff_id": sid, "src": "ff"})
        nuevas += 1
    datos.sort(key=lambda x: x.get("ts") or x.get("date"))
    json.dump(datos, open("ultima-hora.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(nuevas, "nuevas ·", len(datos), "en total")

if __name__ == "__main__":
    main()
