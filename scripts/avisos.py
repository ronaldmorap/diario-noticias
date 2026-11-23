"""Notificaciones push al móvil (Web Push) para el Diario de Disciplina.

Uso:
  python3 scripts/avisos.py ultima      -> avisa de las noticias de última hora nuevas (lee nuevas.json)
  python3 scripts/avisos.py domingo     -> resumen de las noticias importantes de la semana que viene
  python3 scripts/avisos.py lunes       -> recordatorio del lunes por la mañana
  python3 scripts/avisos.py bienvenida  -> confirma a los dispositivos recién activados

Necesita el secreto FIREBASE_SA (la clave de la cuenta de servicio de Firebase, en JSON).
Sin él, no hace nada y sale sin error (secreto añadido el 23 nov 2026).
Los dispositivos se guardan en Firestore (colección pushSubs) desde la app; las claves VAPID en push/config
(se crean solas la primera vez).
"""
import os, sys, json, re, base64, datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
ET = ZoneInfo("America/New_York")
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
APP = "https://diario-de-trading-5675a.web.app/"


def b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class Firestore:
    def __init__(self, info):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/datastore"])
        self.s = AuthorizedSession(creds)
        self.base = f"https://firestore.googleapis.com/v1/projects/{info['project_id']}/databases/(default)/documents"

    @staticmethod
    def _val(v):
        if isinstance(v, bool): return {"booleanValue": v}
        if isinstance(v, int): return {"integerValue": str(v)}
        if isinstance(v, float): return {"doubleValue": v}
        if isinstance(v, dict): return {"mapValue": {"fields": {k: Firestore._val(x) for k, x in v.items()}}}
        if v is None: return {"nullValue": None}
        return {"stringValue": str(v)}

    @staticmethod
    def _py(v):
        if "stringValue" in v: return v["stringValue"]
        if "integerValue" in v: return int(v["integerValue"])
        if "doubleValue" in v: return v["doubleValue"]
        if "booleanValue" in v: return v["booleanValue"]
        if "mapValue" in v: return {k: Firestore._py(x) for k, x in v["mapValue"].get("fields", {}).items()}
        return None

    def get(self, path):
        r = self.s.get(f"{self.base}/{path}")
        if r.status_code == 404: return None
        r.raise_for_status()
        return {k: self._py(v) for k, v in r.json().get("fields", {}).items()}

    def list(self, col):
        out, token = [], None
        while True:
            r = self.s.get(f"{self.base}/{col}", params={"pageSize": 300, **({"pageToken": token} if token else {})})
            if r.status_code == 404: return out
            r.raise_for_status()
            d = r.json()
            for doc in d.get("documents", []):
                out.append((doc["name"].rsplit("/", 1)[1], {k: self._py(v) for k, v in doc.get("fields", {}).items()}))
            token = d.get("nextPageToken")
            if not token: return out

    def set(self, path, data, merge_fields=None):
        params = [("updateMask.fieldPaths", f) for f in merge_fields] if merge_fields else None
        r = self.s.patch(f"{self.base}/{path}", params=params, json={"fields": {k: self._val(v) for k, v in data.items()}})
        r.raise_for_status()

    def delete(self, path):
        self.s.delete(f"{self.base}/{path}")


def vapid(fs):
    """Claves VAPID: se crean una vez y se guardan en Firestore (push/config). La app lee la pública de ahí."""
    cfg = fs.get("push/config")
    if cfg and cfg.get("publicKey") and cfg.get("privateKey"):
        return cfg
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    k = ec.generate_private_key(ec.SECP256R1())
    priv = b64u(k.private_numbers().private_value.to_bytes(32, "big"))
    pub = b64u(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    cfg = {"publicKey": pub, "privateKey": priv, "createdAt": dt.datetime.now(dt.timezone.utc).isoformat()}
    fs.set("push/config", cfg)
    print("Claves de notificaciones creadas")
    return cfg


def enviar(fs, cfg, titulo, cuerpo, url=APP + "#noticias", tag=None, solo=None):
    from pywebpush import webpush, WebPushException
    subs = fs.list("pushSubs")
    if solo is not None:
        subs = [s for s in subs if s[0] in solo]
    datos = json.dumps({"title": titulo, "body": cuerpo, "url": url, "tag": tag or titulo[:40]}, ensure_ascii=False)
    ok = 0
    for sid, s in subs:
        if not s.get("endpoint") or not isinstance(s.get("keys"), dict):
            continue
        try:
            webpush(subscription_info={"endpoint": s["endpoint"], "keys": s["keys"]}, data=datos,
                    vapid_private_key=cfg["privateKey"], vapid_claims={"sub": APP.rstrip("/")}, ttl=6 * 3600)
            ok += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):   # el dispositivo ya no existe (desinstalada o permiso quitado)
                fs.delete(f"pushSubs/{sid}")
                print("Dispositivo caducado, borrado")
            else:
                print("No se pudo enviar a un dispositivo:", code)
        except Exception as e:
            print("Error al enviar:", type(e).__name__)
    print(f"Enviado a {ok} dispositivo(s): {titulo}")
    return ok


# ---------------- contenido ----------------

def ultima(fs, cfg):
    try:
        nuevas = json.load(open("nuevas.json", encoding="utf-8"))
    except Exception:
        return
    ahora = dt.datetime.now(dt.timezone.utc)
    for x in nuevas:
        try:
            t = dt.datetime.fromisoformat(x["ts"].replace("Z", "+00:00"))
        except Exception:
            continue
        if ahora - t > dt.timedelta(hours=3):   # tras un parón largo no se avisan noticias viejas
            continue
        hora = t.astimezone(TZ).strftime("%H:%M")
        enviar(fs, cfg, "⚡ Última hora", f"{x.get('title_es') or x['title']} ({hora})", tag=f"ff{x.get('ff_id', '')}")


EXTRA = [(r"\bGDP\b", "PIB (GDP)"), (r"Unemployment Claims", "Peticiones de paro semanales"),
         (r"FOMC Member|Fed .*Speaks", "Fed: habla un miembro del FOMC")]

def es_titulo(t):
    pre = " (preliminar)" if re.match(r"Prelim", t) else " (final)" if re.match(r"Final", t) else ""
    for rx, es in EXTRA:
        if re.search(rx, t, re.I) and not re.search(r"^CPI|Payrolls|PCE|PPI", t):
            if rx == r"\bGDP\b": return es + pre
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from historico import KEY
        for rx, es, _ in KEY:
            if re.search(rx, t, re.I):
                return es
    except Exception:
        pass
    return t


def semana(lunes):
    """Eventos importantes de lunes a viernes: datos rojos de EEUU, resultados de las grandes y salidas a bolsa."""
    viernes = lunes + dt.timedelta(days=4)
    ev = []
    try:
        ff = json.load(open("ff-semana.json", encoding="utf-8"))
    except Exception:
        ff = []
    vistos = set()
    for e in ff:
        if e.get("country") != "USD" or e.get("impact") not in ("High", "Holiday"):
            continue
        try:
            t = dt.datetime.fromisoformat(e["date"]).astimezone(TZ)
        except Exception:
            continue
        if not (lunes <= t.date() <= viernes):
            continue
        if e.get("impact") == "Holiday":
            k = (t.date(), "festivo")
            if k not in vistos:
                vistos.add(k); ev.append((t.date(), "~", "🇺🇸 Festivo en EEUU: bolsa cerrada o media sesión"))
            continue
        tit = es_titulo(e.get("title", ""))
        k = (t.date(), tit)
        if k in vistos: continue
        vistos.add(k)
        ev.append((t.date(), t.strftime("%H:%M"), tit))
    try:
        for r in json.load(open("resultados.json", encoding="utf-8")):
            d = dt.date.fromisoformat(r["date"])
            if lunes <= d <= viernes:
                cuando = "tras el cierre" if r.get("time") == "amc" else "antes de la apertura" if r.get("time") == "bmo" else ""
                ev.append((d, "~", f"Resultados de {r.get('name') or r.get('sym')}" + (f" ({cuando})" if cuando else "")))
    except Exception:
        pass
    try:
        for s in json.load(open("salidas.json", encoding="utf-8")):
            d = dt.date.fromisoformat(s["date"])
            if lunes <= d <= viernes:
                ev.append((d, "~", f"Sale a bolsa {s.get('name', '').replace(', PBC', '').replace(', Inc.', '')}"))
    except Exception:
        pass
    ev.sort(key=lambda x: (x[0], "99" if x[1] == "~" else x[1]))
    return ev, len(ff)


def lineas(ev, hoy=None):
    out = []
    for d, h, t in ev:
        dia = "Hoy" if hoy and d == hoy else DIAS[d.weekday()]
        out.append(f"{dia}{'' if h == '~' else ' ' + h} · {t}")
    return out


def resumen(fs, cfg, cual):
    hoy = dt.datetime.now(TZ).date()
    lunes = hoy + dt.timedelta(days=(7 - hoy.weekday()) % 7) if cual == "domingo" else hoy - dt.timedelta(days=hoy.weekday())
    ev, total = semana(lunes)
    if total == 0:
        print("No hay calendario de la semana todavía; no se envía nada"); return
    n = len([x for x in ev if "Festivo" not in x[2]])
    if cual == "domingo":
        titulo = f"📅 Tu semana: {n} noticia{'s' if n != 1 else ''} importante{'s' if n != 1 else ''}" if n else "📅 Semana tranquila"
    else:
        titulo = f"☀️ Buenos días · Esta semana: {n} noticia{'s' if n != 1 else ''} importante{'s' if n != 1 else ''}" if n else "☀️ Buenos días · Semana sin noticias rojas"
    cuerpo = "\n".join(lineas(ev, hoy if cual == "lunes" else None)) if ev else "No hay datos rojos de EEUU ni resultados grandes. Aun así, revisa la app."
    enviar(fs, cfg, titulo, cuerpo, tag=f"semana-{lunes.isoformat()}-{cual}")


def bienvenida(fs, cfg):
    nuevos = [sid for sid, s in fs.list("pushSubs") if not s.get("welcomed")]
    for sid in nuevos:
        if enviar(fs, cfg, "✅ Notificaciones activadas", "Te avisaré de las noticias de última hora, el domingo de la semana que viene y el lunes por la mañana.", solo={sid}):
            fs.set(f"pushSubs/{sid}", {"welcomed": True}, merge_fields=["welcomed"])


def main():
    que = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = os.environ.get("FIREBASE_SA", "").strip()
    if not raw:
        print("Sin la clave FIREBASE_SA todavía: no se envían notificaciones"); return
    try:
        fs = Firestore(json.loads(raw))
        cfg = vapid(fs)
        if que == "ultima": ultima(fs, cfg)
        elif que in ("domingo", "lunes"): resumen(fs, cfg, que)
        elif que == "bienvenida": bienvenida(fs, cfg)
        else: print("Uso: avisos.py ultima|domingo|lunes|bienvenida")
    except Exception as e:
        # No se imprime el detalle completo: el repo es público
        print("Error en las notificaciones:", type(e).__name__, str(e)[:200])
        sys.exit(1)


if __name__ == "__main__":
    main()
