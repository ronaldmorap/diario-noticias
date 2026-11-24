// Despertador de los robots del Diario de Disciplina (Cloudflare Worker).
// - Cada 15 minutos (Cron Trigger) despierta el robot de "última hora"; una vez por hora, también el del calendario.
// - El botón "Actualizar" de la app llama a /actualizar y despierta los dos al momento.
// Necesita el secreto GH_TOKEN: una clave de GitHub (fine-grained) solo para el repo diario-noticias
// con el permiso "Actions: Read and write". La clave nunca sale de aquí.
const REPO = "ronaldmorap/diario-noticias";
const ORIGENES = ["https://diario-de-trading-5675a.web.app", "https://diario-de-trading-5675a.firebaseapp.com"];

async function despertar(env, flujos) {
  const out = {};
  for (const f of flujos) {
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${f}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "despertador-diario"
      },
      body: JSON.stringify({ ref: "main" })
    });
    out[f] = r.status; // 204 = despertado
  }
  return out;
}

function cors(req) {
  const o = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ORIGENES.includes(o) ? o : ORIGENES[0],
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8"
  };
}

export default {
  async scheduled(event, env, ctx) {
    const min = new Date(event.scheduledTime).getUTCMinutes();
    const flujos = ["ultima-hora.yml"];
    if (min < 15) flujos.push("noticias.yml");
    ctx.waitUntil(despertar(env, flujos));
  },

  async fetch(req, env) {
    const h = cors(req);
    if (req.method === "OPTIONS") return new Response(null, { headers: h });
    const url = new URL(req.url);
    if (url.pathname !== "/actualizar") return new Response(JSON.stringify({ ok: true, info: "despertador del Diario" }), { headers: h });
    if (!env.GH_TOKEN) return new Response(JSON.stringify({ ok: false, error: "falta GH_TOKEN" }), { status: 500, headers: h });
    // Freno: como mucho una vez cada 2 minutos (si no, cualquiera podría lanzar robots sin parar).
    const cache = caches.default;
    const llave = new Request("https://despertador.interno/ultimo");
    if (await cache.match(llave)) return new Response(JSON.stringify({ ok: true, reciente: true }), { headers: h });
    await cache.put(llave, new Response("1", { headers: { "Cache-Control": "max-age=120" } }));
    const res = await despertar(env, ["ultima-hora.yml", "noticias.yml"]);
    const ok = Object.values(res).every(s => s === 204);
    return new Response(JSON.stringify({ ok, res }), { status: ok ? 200 : 502, headers: h });
  }
};
