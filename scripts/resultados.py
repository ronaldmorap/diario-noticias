"""Fechas de resultados de las 7 magníficas (Nasdaq.com), para el Diario de Disciplina.

Escribe resultados.json: [{"sym","name","date","time"}], time = "amc" (después del cierre),
"bmo" (antes de la apertura) o "" (sin confirmar). Si una consulta falla, conserva lo anterior.
"""
import json, re, sys, time, datetime as dt, urllib.request

SYMS = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon",
        "GOOGL": "Alphabet (Google)", "META": "Meta", "TSLA": "Tesla"}
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
       "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}

def get(url):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def next_date(sym):
    d = get(f"https://api.nasdaq.com/api/analyst/{sym}/earnings-date")
    txt = json.dumps(d.get("data") or {})
    m = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4})", txt)
    return dt.datetime.strptime(m.group(1), "%b %d, %Y").date() if m else None

def time_of_day(sym, day):
    d = get(f"https://api.nasdaq.com/api/calendar/earnings?date={day.isoformat()}")
    for row in ((d.get("data") or {}).get("rows") or []):
        if row.get("symbol") == sym:
            t = (row.get("time") or "").lower()
            return "amc" if "after" in t else "bmo" if "pre" in t else ""
    return ""

def main():
    try: old = {e["sym"]: e for e in json.load(open("resultados.json"))}
    except Exception: old = {}
    out, ok = [], 0
    for sym, name in SYMS.items():
        try:
            day = next_date(sym)
            tod = time_of_day(sym, day) if day else ""
            print(sym, day, tod or "?")
            if day:
                out.append({"sym": sym, "name": name, "date": day.isoformat(), "time": tod}); ok += 1
            elif sym in old: out.append(old[sym])
        except Exception as e:
            print(sym, "ERROR", e)
            if sym in old: out.append(old[sym])
        time.sleep(2)
    if not ok:
        print("::warning::Nasdaq no ha respondido; se mantienen las fechas anteriores."); return
    # keep recent past reports (for the calendar history) that are no longer the "next" date
    seen = {(e["sym"], e["date"]) for e in out}
    cutoff = (dt.date.today() - dt.timedelta(days=120)).isoformat()
    try: prev = json.load(open("resultados.json"))
    except Exception: prev = []
    out += [e for e in prev if (e["sym"], e["date"]) not in seen and e["date"] >= cutoff and e["date"] < dt.date.today().isoformat()]
    out.sort(key=lambda e: (e["date"], e["sym"]))
    json.dump(out, open("resultados.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
