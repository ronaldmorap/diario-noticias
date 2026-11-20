"""Histórico de noticias fuertes (desde noviembre de 2025) para el calendario del backtesting.

Lee, día a día, el calendario económico y el de resultados de Nasdaq.com y se queda solo con lo que mueve
el Nasdaq: datos macro clave de EEUU, la Fed y los resultados de las grandes del Nasdaq 100.
Escribe historico.json: [{"date","time","title","kind"}]  (kind: macro | fed | resultados | salida).
Las grandes salidas a bolsa (>= 2.000 M$) salen del calendario de IPOs de Nasdaq y de salidas.json, y nunca se borran.
"""
import json, re, sys, time, datetime as dt, urllib.request

START = dt.date(2025, 11, 1)
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
       "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
SYMS = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet (Google)",
        "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom", "NFLX": "Netflix", "AMD": "AMD", "TSM": "TSMC"}
# (regex on the Nasdaq event name, Spanish title, kind)
KEY = [
    (r"^CPI\b|Consumer Price Index", "IPC (CPI) – inflación", "macro"),
    (r"Nonfarm Payrolls|Non-Farm Payrolls|Employment Situation", "Nóminas no agrícolas (NFP) – empleo", "macro"),
    (r"^PPI\b|Producer Price Index", "IPP (PPI) – precios de producción", "macro"),
    (r"Retail Sales", "Ventas minoristas", "macro"),
    (r"^GDP\b|Gross Domestic Product", "PIB (GDP)", "macro"),
    (r"PCE Price|Core PCE|Personal Consumption Expenditures", "PCE – inflación preferida por la Fed", "macro"),
    (r"ISM Manufacturing PMI|ISM Manufacturing Index", "ISM manufacturero", "macro"),
    (r"ISM (Non-Manufacturing|Services) (PMI|Index)", "ISM servicios", "macro"),
    (r"JOLTS", "Ofertas de empleo (JOLTS)", "macro"),
    (r"Fed Interest Rate Decision|FOMC (Rate|Statement)|Federal Funds Rate", "Fed: decisión de tipos (FOMC)", "fed"),
    (r"FOMC (Meeting )?Minutes", "Fed: actas del FOMC", "fed"),
    (r"(Fed Chair|Powell).*(Speaks|Testifies|Press Conference)|FOMC Press Conference", "Fed: habla el presidente", "fed"),
]

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def macro_for(day):
    d = (get(f"https://api.nasdaq.com/api/calendar/economicevents?date={day.isoformat()}") or {}).get("data") or {}
    rows = d.get("rows") or []
    out, seen = [], set()
    for r in rows:
        if (r.get("country") or "").strip().lower() not in ("united states", "us", "usa", "u.s."): continue
        name = (r.get("eventName") or "").strip()
        for rx, title, kind in KEY:
            if re.search(rx, name, re.I) and title not in seen:
                seen.add(title)
                out.append({"date": day.isoformat(), "time": (r.get("gmt") or "").strip(), "title": title, "kind": kind, "src": name})
                break
    return out, len(rows)

def earnings_for(day):
    d = (get(f"https://api.nasdaq.com/api/calendar/earnings?date={day.isoformat()}") or {}).get("data") or {}
    out = []
    for r in (d.get("rows") or []):
        sym = r.get("symbol")
        if sym in SYMS:
            t = (r.get("time") or "").lower()
            out.append({"date": day.isoformat(), "time": "amc" if "after" in t else "bmo" if "pre" in t else "",
                        "title": f"Resultados de {SYMS[sym]}", "kind": "resultados", "sym": sym})
    return out

MIN_IPO = 2_000_000_000

def ipo_title(name, tick):
    name = re.sub(r",? (Inc|PBC|Corp|Corporation|Ltd|plc|Holdings?)\.?$", "", (name or "").strip(), flags=re.I)
    if name.isupper(): name = name.title()
    return f"Salida a bolsa de {name}" + (f" ({tick})" if tick else "")

def money(v):
    try: return float(re.sub(r"[^0-9.]", "", str(v)) or 0)
    except Exception: return 0.0

def ipos(today):
    """Grandes salidas a bolsa ya hechas, mes a mes desde START, más las que guardó salidas.json."""
    found, ym = {}, START.replace(day=1)
    while ym <= today:
        try:
            d = (get(f"https://api.nasdaq.com/api/ipo/calendar?date={ym:%Y-%m}") or {}).get("data") or {}
            rows = ((d.get("priced") or {}).get("rows") or [])
            for r in rows:
                amount = money(r.get("dollarValueOfSharesOffered"))
                try: day = dt.datetime.strptime(str(r.get("pricedDate")).strip(), "%m/%d/%Y").date()
                except Exception: continue
                if amount < MIN_IPO or day >= today: continue
                tick = (r.get("proposedTickerSymbol") or "").strip()
                found[(tick or r.get("companyName"), day.isoformat())] = {"date": day.isoformat(), "time": "", "kind": "salida",
                    "title": ipo_title(r.get("companyName"), tick), "sym": tick, "amount": amount}
            print(f"{ym:%Y-%m} salidas cotizadas: {len(rows)}")
        except Exception as e:
            print(f"{ym:%Y-%m} salidas ERROR", e)
        time.sleep(1)
        ym = (ym + dt.timedelta(days=32)).replace(day=1)
    try:
        for x in json.load(open("salidas.json")):
            if x.get("date", "") < today.isoformat() and (x.get("amount") or 0) >= MIN_IPO:
                found.setdefault((x.get("ticker") or x.get("name"), x["date"]), {"date": x["date"], "time": "", "kind": "salida",
                    "title": ipo_title(x.get("name"), x.get("ticker")), "sym": x.get("ticker") or "", "amount": x.get("amount")})
    except Exception as e:
        print("salidas.json no disponible", e)
    return found

def main():
    try: old = json.load(open("historico.json"))
    except Exception: old = []
    have = {e["date"] for e in old}
    today = dt.date.today()
    day, out, fails, probe = START, list(old), 0, 0
    while day < today:
        if day.weekday() < 5 and day.isoformat() not in have:
            try:
                ev, n = macro_for(day); time.sleep(0.7)
                ev += earnings_for(day); time.sleep(0.7)
                if probe < 3: print(day, "filas Nasdaq:", n, "->", [e["title"] for e in ev]); probe += 1
                out += ev
                if not ev: out.append({"date": day.isoformat(), "kind": "none"})
            except Exception as e:
                fails += 1; print(day, "ERROR", e)
                if fails > 15: print("::warning::Demasiados fallos; se guarda lo conseguido."); break
                time.sleep(5)
        day += dt.timedelta(days=1)
    # Salidas a bolsa: se añaden las nuevas y nunca se quita ninguna ya guardada
    have_ipo = {(e.get("sym") or e.get("title"), e["date"]) for e in out if e.get("kind") == "salida"}
    for k, e in ipos(today).items():
        if (e.get("sym") or e.get("title"), e["date"]) not in have_ipo: out.append(e); print("  + ", e["date"], e["title"])
    out.sort(key=lambda e: (e["date"], e.get("time") or ""))
    json.dump(out, open("historico.json", "w"), ensure_ascii=False, indent=0)
    print(len([e for e in out if e.get("kind") != "none"]), "eventos en el histórico")

if __name__ == "__main__":
    main()
