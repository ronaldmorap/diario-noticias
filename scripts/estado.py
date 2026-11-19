"""Apunta en estado.json cuándo se actualizó bien cada fuente (lo lee la app para avisar si algo lleva días sin actualizarse)."""
import json, sys, datetime as dt
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
try: st = json.load(open("estado.json"))
except Exception: st = {}
for src in sys.argv[1:]:
    st[src] = now
st["revisado"] = now
json.dump(st, open("estado.json", "w"), indent=1)
print("estado:", st)
