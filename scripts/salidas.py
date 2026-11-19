"""Grandes salidas a bolsa (IPO) en EEUU, del calendario de Nasdaq.com, para el Diario de Disciplina.

Escribe salidas.json: [{"date","name","ticker","exchange","price","amount","status"}].
Solo guarda las grandes (por defecto >= 2.000 millones de dólares), que son las que pueden mover el mercado.
"""
import json, re, sys, time, datetime as dt, urllib.request

MIN_AMOUNT = 2_000_000_000
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
       "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def money(v):
    try: return float(re.sub(r"[^0-9.]", "", str(v)) or 0)
    except Exception: return 0.0

def parse_date(v):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try: return dt.datetime.strptime(str(v).strip(), fmt).date()
        except Exception: pass
    return None

def rows_of(block, *path):
    cur = block or {}
    for p in path: cur = (cur or {}).get(p) if isinstance(cur, dict) else None
    return cur or []

def main():
    today = dt.date.today()
    months = sorted({today.strftime("%Y-%m"), (today.replace(day=1) + dt.timedelta(days=40)).strftime("%Y-%m"),
                     (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")})
    out, ok = {}, False
    for ym in months:
        try:
            d = (get(f"https://api.nasdaq.com/api/ipo/calendar?date={ym}") or {}).get("data") or {}
            ok = True
        except Exception as e:
            print(ym, "ERROR", e); continue
        groups = [("priced", rows_of(d, "priced", "rows")), ("upcoming", rows_of(d, "upcoming", "upcomingTable", "rows"))]
        for status, rows in groups:
            print(ym, status, len(rows))
            for r in rows:
                amount = money(r.get("dollarValueOfSharesOffered"))
                if amount < MIN_AMOUNT: continue
                day = parse_date(r.get("pricedDate") or r.get("expectedPriceDate"))
                if not day: continue
                name = (r.get("companyName") or "").strip()
                tick = (r.get("proposedTickerSymbol") or "").strip()
                print("  >>", day, name, tick, amount, status)
                out[(tick or name, day.isoformat())] = {"date": day.isoformat(), "name": name, "ticker": tick,
                    "exchange": (r.get("proposedExchange") or "").strip(), "price": (r.get("proposedSharePrice") or "").strip(),
                    "amount": amount, "status": status}
        time.sleep(2)
    if not ok:
        print("::warning::Nasdaq no ha respondido; se mantienen las salidas anteriores."); sys.exit(3)
    try: prev = json.load(open("salidas.json"))
    except Exception: prev = []
    cutoff = (today - dt.timedelta(days=120)).isoformat()
    for e in prev:
        k = (e.get("ticker") or e.get("name"), e.get("date"))
        # Una salida que ya estaba guardada no se borra nunca por desaparecer de la lista de Nasdaq
        # (al cotizar pasa de "upcoming" a "priced" y a veces cambia de formato); solo caduca a los 120 días.
        if k not in out and e.get("date", "") >= cutoff: out[k] = e
    data = sorted(out.values(), key=lambda e: e["date"])
    json.dump(data, open("salidas.json", "w"), ensure_ascii=False, indent=1)
    print(len(data), "salidas grandes guardadas")

if __name__ == "__main__":
    main()
