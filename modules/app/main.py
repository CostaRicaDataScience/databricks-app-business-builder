"""FastAPI application entry point."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from modules.app.schemas import (
    BuildPlanRequest,
    DiscoveryConfirmRequest,
    DiscoveryIntakeRequest,
    DiscoveryRunRequest,
    GenerateRequest,
    ProvisionRequest,
    RunPipelineRequest,
    StyleReferenceInputModel,
)
from modules.app.services import FoundationModelGateway, OrchestratorService
from modules.core.config import load_settings
from modules.core.logging import log
from modules.domain.models import DiscoveryIntake, StyleReferenceInput
from modules.infra.auth import AuthProvider
from modules.infra.databricks_client import DatabricksApiClient
from modules.infra.tagging import TaggingPolicy

# composer.* is importable because modules.app.services puts ``src`` on sys.path
# at import time (above). The OBO resolver reads Databricks Apps forwarded
# headers to build a per-request, on-behalf-of-user auth context.
from composer.databricks.obo import RequestAuth, resolve_request_auth

app = FastAPI(title='Databricks App business builder')
settings = load_settings()
auth_provider = AuthProvider(settings)
auth_context = auth_provider.resolve()
dbx_client = DatabricksApiClient(auth_context)
genai_gateway = FoundationModelGateway(settings)
tagging_policy = TaggingPolicy()
orchestrator = OrchestratorService(
    settings=settings,
    dbx_client=dbx_client,
    genai_gateway=genai_gateway,
    tagging_policy=tagging_policy,
)


def _request_auth(request: Request) -> RequestAuth:
    """Resolve per-request auth from Databricks Apps forwarded headers.

    Falls back to the configured auth mode/host when no forwarded user token is
    present (local dev / not deployed as an App).
    """
    return resolve_request_auth(
        request.headers,
        fallback_mode=settings.auth_mode,
        fallback_host=settings.databricks_host,
    )


@app.get('/health')
def health() -> dict:
    log.info('health_check')
    return {
        'status': 'ok',
        'auth_mode': auth_context.mode,
        'foundation_model_provider': settings.foundation_model_provider,
        'preferred_model': settings.preferred_model,
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _HOME_HTML


@app.get('/auth/status')
def auth_status(request: Request) -> dict:
    """Report Databricks connection + the permissions we will request.

    Honors Databricks Apps OBO: when ``X-Forwarded-Access-Token`` is present,
    status reflects the signed-in user (``auth_mode='databricks_app_obo'``).
    """
    return orchestrator.auth_status(_request_auth(request))


@app.post('/auth/connect')
def auth_connect(request: Request) -> dict:
    """Attempt to connect to the Databricks workspace and report the result."""
    return orchestrator.connect(_request_auth(request))


@app.get('/dev/preflight')
def dev_preflight() -> dict:
    """Local dev environment preflight (Databricks CLI + valid profile + aitools).

    Intended for local development; in a deployed Databricks App there is no CLI,
    so this returns ``cli_installed=False`` and is informational only.
    """
    from composer.deploy.local_dev import local_dev_preflight

    return local_dev_preflight()


@app.post('/run')
def run_pipeline(payload: RunPipelineRequest, request: Request) -> dict:
    """Single entrypoint: run intake -> discovery -> autofix -> plan -> generate.

    Runs as the signed-in user (OBO) when a forwarded token is present, so
    discovery/Genie/codegen use that user's real permissions. Returns a
    human-friendly summary; granular endpoints remain for power users.
    """
    style_reference = _to_style_reference(payload.style_reference)
    intake = DiscoveryIntake(
        primary_use_case_description=payload.primary_use_case_description,
        user_stories=payload.user_stories,
        gold_tables=payload.gold_tables,
        existing_genies=payload.existing_genies,
        workflow_requirements=payload.workflow_requirements,
        style_preferences=payload.style_preferences,
        access_requirements=payload.access_requirements,
        style_reference=style_reference,
    )
    try:
        return orchestrator.run_pipeline(intake, _request_auth(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post('/discovery-intake')
def discovery_intake(payload: DiscoveryIntakeRequest) -> dict:
    style_reference = _to_style_reference(payload.style_reference)
    intake = DiscoveryIntake(
        primary_use_case_description=payload.primary_use_case_description,
        user_stories=payload.user_stories,
        gold_tables=payload.gold_tables,
        existing_genies=payload.existing_genies,
        workflow_requirements=payload.workflow_requirements,
        style_preferences=payload.style_preferences,
        access_requirements=payload.access_requirements,
        style_reference=style_reference,
    )
    intake_id = orchestrator.submit_intake(intake)
    return {'intake_id': intake_id}


@app.post('/discovery-run')
def discovery_run(payload: DiscoveryRunRequest) -> dict:
    try:
        report = orchestrator.run_discovery(payload.intake_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(report)


@app.post('/discovery-confirm')
def discovery_confirm(payload: DiscoveryConfirmRequest) -> dict:
    try:
        return orchestrator.confirm_discovery_autofix(payload.intake_id, payload.report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post('/build-plan')
def build_plan(payload: BuildPlanRequest) -> dict:
    try:
        plan = orchestrator.build_plan(
            intake_id=payload.intake_id,
            dry_run=payload.dry_run,
            run_provisioning=payload.run_provisioning,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(plan)


@app.post('/generate')
def generate(payload: GenerateRequest) -> dict:
    try:
        artifact = orchestrator.generate(payload.plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(artifact)


@app.post('/provision')
def provision(payload: ProvisionRequest) -> dict:
    try:
        result = orchestrator.provision(
            intake_id=payload.intake_id,
            environment=payload.environment,
            owner=payload.owner,
            use_case_slug=payload.use_case_slug,
            resources=payload.resources,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(result)


@app.get('/discovery-report/{report_id}')
def get_discovery_report(report_id: str) -> dict:
    try:
        report = orchestrator.get_discovery_report(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(report)


@app.get('/tagging-report/{operation_id}')
def get_tagging_report(operation_id: str) -> dict:
    try:
        report = orchestrator.get_tagging_report(operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return asdict(report)


@app.get('/operations/{operation_id}')
def get_operation(operation_id: str) -> dict:
    try:
        return orchestrator.get_operation(operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _to_style_reference(model: StyleReferenceInputModel | None) -> StyleReferenceInput | None:
    if model is None:
        return None
    return StyleReferenceInput(
        source_type=model.source_type,
        source_path_or_url=model.source_path_or_url,
        style_guidelines_notes=model.style_guidelines_notes,
    )


# Guided, plain-language UI. Designed with the ux-ui-design skill:
# no raw IDs as headline, jargon-free labels, explicit connect/permission step,
# named progress steps, and a single auto-run flow as the default action.
# (raw string so the embedded JS keeps its own backslash escapes intact)
_HOME_HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Databricks App Business Builder</title>
  <style>
    :root {
      --bg: #11181C;
      --card: #171F26;
      --card-2: #1B252C;
      --text: #E9EDF1;
      --muted: #A7B3BE;
      --border: #2D3943;
      --primary: #FF4C24;
      --primary-dark: #CE4A2C;
      --success: #008558;
      --warn: #C98A00;
      --danger: #D92626;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      color: var(--text);
      background:
        linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px),
        var(--bg);
      background-size: 18px 28px, 18px 28px, auto;
    }
    .page { max-width: 1100px; margin: 0 auto; padding: 34px 20px 60px; }
    .hero { text-align: center; padding-top: 16px; padding-bottom: 12px; }
    .hero h1 { margin: 0 0 10px; font-size: clamp(1.9rem, 3.8vw, 3rem); line-height: 1.15; }
    .hero .accent { color: var(--primary); }
    .hero p { margin: 0 auto; max-width: 760px; color: var(--muted); font-size: 1.05rem; }

    .stepper { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 22px 0 8px; }
    .stepper .step {
      display: flex; align-items: center; gap: 8px;
      border: 1px solid var(--border); background: rgba(255,255,255,0.03);
      border-radius: 999px; padding: 7px 13px; font-size: 0.86rem; color: var(--muted);
    }
    .stepper .step .num {
      width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
      background: var(--border); color: var(--text); font-size: 0.78rem; font-weight: 700;
    }
    .stepper .step.active { border-color: var(--primary); color: var(--text); }
    .stepper .step.active .num { background: var(--primary); }
    .stepper .step.done .num { background: var(--success); }

    .layout { display: grid; gap: 18px; grid-template-columns: 1fr; margin-top: 18px; }
    @media (min-width: 980px) { .layout { grid-template-columns: 1.6fr 1fr; align-items: start; } }
    .card {
      border: 1px solid var(--border);
      background: linear-gradient(180deg, var(--card), var(--card-2));
      border-radius: 14px;
      box-shadow: 0 12px 24px rgba(0,0,0,0.22);
      margin-bottom: 18px;
    }
    .card-head { padding: 16px 18px; border-bottom: 1px solid var(--border); }
    .card-head h2 { margin: 0; font-size: 1.14rem; }
    .card-head p { margin: 6px 0 0; color: var(--muted); font-size: 0.92rem; }
    .card-body { padding: 16px 18px 18px; }

    label { display: block; margin-top: 14px; font-weight: 600; color: #dce4ec; font-size: 0.96rem; }
    textarea, input {
      width: 100%; margin-top: 6px; border: 1px solid var(--border);
      background: #0f161d; color: var(--text); border-radius: 10px; padding: 11px 12px; outline: none;
    }
    textarea:focus, input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(255,76,36,0.2); }
    textarea { min-height: 74px; resize: vertical; }
    .hint { font-size: 0.82rem; color: var(--muted); margin-top: 5px; }

    .btn {
      margin-top: 8px; border: 0; color: #fff; padding: 11px 15px; border-radius: 10px;
      cursor: pointer; font-weight: 700;
    }
    .btn-primary { background: var(--primary); width: 100%; margin-top: 20px; font-size: 1.02rem; }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-primary:disabled { background: #5a3a30; cursor: not-allowed; }
    .btn-secondary { background: #243039; border: 1px solid var(--border); }
    .btn-secondary:hover { border-color: var(--primary); }

    .status-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }
    .dot.ok { background: var(--success); }
    .dot.warn { background: var(--warn); }
    .dot.err { background: var(--danger); }
    .muted { color: var(--muted); font-size: 0.88rem; }
    .kv { color: var(--muted); font-size: 0.86rem; margin-top: 4px; }
    .kv b { color: var(--text); font-weight: 600; }

    .list { display: grid; gap: 9px; margin-top: 4px; }
    .perm {
      border: 1px solid var(--border); border-radius: 10px; background: rgba(255,255,255,0.03);
      padding: 9px 11px;
    }
    .perm .perm-top { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
    .perm .perm-label { font-size: 0.9rem; font-weight: 600; }
    .perm .perm-why { color: var(--muted); font-size: 0.82rem; margin-top: 3px; }
    .tag { font-size: 0.74rem; font-weight: 700; padding: 3px 8px; border-radius: 999px; }
    .tag.ok { background: rgba(0,133,88,0.18); color: #7be0bd; border: 1px solid rgba(0,133,88,0.4); }
    .tag.no { background: rgba(201,138,0,0.16); color: #ffd98a; border: 1px solid rgba(201,138,0,0.4); }

    .results { display: none; }
    .results.show { display: block; }
    .res-step { display: flex; align-items: flex-start; gap: 10px; padding: 9px 0; border-bottom: 1px dashed var(--border); }
    .res-step:last-child { border-bottom: 0; }
    .res-step .icon { font-size: 1rem; line-height: 1.4; }
    .res-step .body .t { font-weight: 600; font-size: 0.94rem; }
    .res-step .body .d { color: var(--muted); font-size: 0.84rem; margin-top: 2px; }
    .section-title { margin: 16px 0 6px; font-size: 0.95rem; font-weight: 700; color: #dce4ec; }
    .chip { display: inline-block; border: 1px solid var(--border); border-radius: 8px; padding: 4px 9px;
            margin: 3px 5px 0 0; font-size: 0.83rem; background: rgba(255,255,255,0.03); }
    .approve { border-color: rgba(201,138,0,0.5); color: #ffd98a; }
    details.tech { margin-top: 16px; border: 1px solid var(--border); border-radius: 10px; background: #0f161d; }
    details.tech summary { cursor: pointer; padding: 10px 12px; color: var(--muted); font-size: 0.85rem; }
    details.tech pre { margin: 0; padding: 0 12px 12px; font-size: 0.78rem; color: #b9c4ce; overflow-x: auto; }
    .banner { border-radius: 10px; padding: 11px 12px; font-size: 0.88rem; margin-top: 12px; }
    .banner.err { background: rgba(217,38,38,0.12); border: 1px solid rgba(217,38,38,0.5); }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Databricks App <span class="accent">Business Builder</span></h1>
      <p>Describe qué necesitas en lenguaje sencillo. Nosotros nos conectamos a tu
         workspace de Databricks, validamos permisos, revisamos tus datos y creamos tu app.</p>
    </section>

    <div class="stepper">
      <div class="step active" id="st-1"><span class="num">1</span> Cuéntanos qué necesitas</div>
      <div class="step" id="st-2"><span class="num">2</span> Conectar a Databricks</div>
      <div class="step" id="st-3"><span class="num">3</span> Revisar y crear</div>
    </div>

    <section class="layout">
      <div>
        <article class="card">
          <div class="card-head">
            <h2>Paso 1 · Cuéntanos qué necesitas</h2>
            <p>Responde con tus palabras. No necesitas conocer términos técnicos.</p>
          </div>
          <div class="card-body">
            <form id="run-form">
              <label for="use_case">¿Qué quieres lograr con esta app?</label>
              <textarea id="use_case" required placeholder="Ej: Ver y comparar las ventas por región para tomar decisiones."></textarea>

              <label for="stories">¿Qué tareas deben poder hacer las personas que la usen?</label>
              <textarea id="stories" required placeholder="Una idea por línea"></textarea>
              <div class="hint">Ej: "Como analista quiero comparar ventas por segmento."</div>

              <label for="gold_tables">¿Qué datos (tablas) debe mostrar?</label>
              <textarea id="gold_tables" required placeholder="Una tabla por línea, ej: sales.gold_orders"></textarea>
              <div class="hint">Si no estás seguro del nombre exacto, escribe el que conozcas.</div>

              <label for="genies">¿Ya existe un asistente de datos que quieras reutilizar? (opcional)</label>
              <textarea id="genies" placeholder='Escribe su nombre, o "no estoy seguro, busca" y lo buscamos por ti.'></textarea>
              <div class="hint">Si no lo conoces, pídenos que busquemos: revisaremos los asistentes de tu workspace.</div>

              <label for="workflow">¿Con qué frecuencia se actualizan los datos y quién aprueba los cambios?</label>
              <textarea id="workflow" required placeholder='Ej: "Se actualiza cada día; mi líder aprueba cambios grandes."'></textarea>

              <label for="access">¿Quién debe poder usar esta app y a qué datos accede?</label>
              <textarea id="access" required placeholder='Ej: "El equipo de ventas; lee las tablas de pedidos y clientes."'></textarea>

              <label for="style">¿Cómo te gustaría que se vea? (opcional)</label>
              <textarea id="style" placeholder="Ej: tema oscuro, simple, con gráficos de barras."></textarea>

              <button class="btn btn-primary" id="run-btn" type="submit">Crear mi app</button>
              <div class="hint" style="text-align:center;">Ejecutamos todo el proceso de principio a fin y te mostramos el resultado.</div>
            </form>
            <div id="form-error" class="banner err" style="display:none;"></div>
          </div>
        </article>

        <article class="card results" id="results">
          <div class="card-head">
            <h2>Resultado</h2>
            <p id="res-headline">—</p>
          </div>
          <div class="card-body" id="res-body"></div>
        </article>
      </div>

      <aside>
        <article class="card">
          <div class="card-head">
            <h2>Paso 2 · Conexión a Databricks y permisos</h2>
            <p>Este es el momento en que nos conectamos a tu workspace y pedimos accesos.</p>
          </div>
          <div class="card-body">
            <div class="status-row">
              <span class="dot" id="conn-dot"></span>
              <strong id="conn-state">Comprobando…</strong>
            </div>
            <div class="kv" id="conn-detail"></div>
            <button class="btn btn-secondary" id="connect-btn" type="button" style="margin-top:12px;">Conectar a Databricks</button>

            <div class="section-title">Permisos que vamos a solicitar</div>
            <div class="list" id="perm-list"><div class="muted">Cargando…</div></div>
            <div class="hint" style="margin-top:10px;">
              La conexión interactiva (OAuth) depende del entorno. Si falta configuración,
              te diremos exactamente qué definir (p. ej. <code>DATABRICKS_HOST</code>, <code>DATABRICKS_TOKEN</code>).
            </div>
          </div>
        </article>
      </aside>
    </section>
  </div>

  <script>
    function splitLines(value) {
      return value.split("\n").map(function (x) { return x.trim(); }).filter(function (x) { return x.length > 0; });
    }
    function setStep(n) {
      [1, 2, 3].forEach(function (i) {
        var el = document.getElementById("st-" + i);
        el.classList.remove("active", "done");
        if (i < n) el.classList.add("done");
        else if (i === n) el.classList.add("active");
      });
    }
    function esc(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function renderAuth(data) {
      var dot = document.getElementById("conn-dot");
      var state = document.getElementById("conn-state");
      var detail = document.getElementById("conn-detail");
      dot.className = "dot " + (data.connected ? "ok" : (data.credentials_present ? "warn" : "err"));
      state.textContent = data.connected ? "Conectado" : "Sin conexión";
      var bits = [];
      if (data.host) bits.push("<b>Workspace:</b> " + esc(data.host));
      if (data.principal) bits.push("<b>Usuario:</b> " + esc(data.principal));
      bits.push("<b>Modo:</b> " + esc(data.auth_mode));
      bits.push(esc(data.message));
      detail.innerHTML = bits.join("<br/>");

      var list = document.getElementById("perm-list");
      list.innerHTML = "";
      (data.permissions || []).forEach(function (p) {
        var div = document.createElement("div");
        div.className = "perm";
        div.innerHTML =
          '<div class="perm-top"><span class="perm-label">' + esc(p.label) + "</span>" +
          '<span class="tag ' + (p.satisfied ? "ok" : "no") + '">' +
          (p.satisfied ? "OK" : "requiere acceso") + "</span></div>" +
          '<div class="perm-why">' + esc(p.why) + "</div>";
        list.appendChild(div);
      });
      if (data.connected) setStep(3);
      else setStep(2);
    }

    async function loadAuth() {
      try {
        var r = await fetch("/auth/status");
        renderAuth(await r.json());
      } catch (e) {
        document.getElementById("conn-state").textContent = "No se pudo comprobar la conexión";
      }
    }

    document.getElementById("connect-btn").addEventListener("click", async function () {
      var btn = this;
      btn.disabled = true;
      btn.textContent = "Conectando…";
      try {
        var r = await fetch("/auth/connect", { method: "POST" });
        renderAuth(await r.json());
      } finally {
        btn.disabled = false;
        btn.textContent = "Conectar a Databricks";
      }
    });

    function chips(items, cls) {
      if (!items || !items.length) return '<span class="muted">Ninguno</span>';
      return items.map(function (x) { return '<span class="chip ' + (cls || "") + '">' + esc(x) + "</span>"; }).join("");
    }

    function renderSummary(s) {
      var results = document.getElementById("results");
      var body = document.getElementById("res-body");
      document.getElementById("res-headline").textContent = s.headline || "Listo.";
      var html = "";

      html += '<div>';
      (s.steps || []).forEach(function (st) {
        var icon = st.status === "done" ? "✅" : (st.status === "needs_attention" ? "⚠️" : "•");
        html += '<div class="res-step"><div class="icon">' + icon + "</div>" +
          '<div class="body"><div class="t">' + esc(st.title) + "</div>" +
          (st.detail ? '<div class="d">' + esc(st.detail) + "</div>" : "") + "</div></div>";
      });
      html += "</div>";

      var c = s.connection || {};
      html += '<div class="section-title">Conexión a Databricks</div>';
      html += '<div class="kv">' +
        (c.connected ? "Conectado" : "Sin conexión") +
        (c.host ? " · <b>" + esc(c.host) + "</b>" : "") +
        (c.principal ? " · " + esc(c.principal) : "") +
        "<br/>" + esc(c.message || "") + "</div>";

      var d = s.data || {};
      html += '<div class="section-title">Datos</div>';
      html += '<div class="kv">Encontradas: ' + chips(d.tables_found) + "</div>";
      html += '<div class="kv" style="margin-top:6px;">Mejoradas automáticamente: ' + chips(d.tables_improved) + "</div>";
      if (d.tables_unverified && d.tables_unverified.length) {
        html += '<div class="kv" style="margin-top:6px;">Sin verificar (requiere conexión): ' +
          chips(d.tables_unverified, "approve") + "</div>";
      }

      var a = s.assistants || {};
      html += '<div class="section-title">Asistentes (Genies)</div>';
      html += '<div class="kv">Reutilizados / encontrados: ' + chips(a.existing) + "</div>";
      html += '<div class="kv" style="margin-top:6px;">Por crear: ' + chips(a.to_create, "approve") + "</div>";
      if (a.unverified && a.unverified.length) {
        html += '<div class="kv" style="margin-top:6px;">No se pudo buscar (requiere conexión): ' +
          chips(a.unverified, "approve") + "</div>";
      }

      var g = s.generated_app || {};
      html += '<div class="section-title">App generada</div>';
      html += '<div class="kv"><b>Generada por:</b> ' + esc(g.generated_by || "—") + "</div>";
      html += '<div class="kv" style="margin-top:4px;"><b>Carpeta:</b> ' + esc(g.output_path) + " · " +
        ((g.files || []).length) + " archivo(s)</div>";
      if (g.preview) {
        html += '<details class="tech" style="margin-top:8px;"><summary>Ver vista previa del código (app.py)</summary><pre>' +
          esc(g.preview) + "</pre></details>";
      }

      var resMap = s.resources || {};
      var resKeys = Object.keys(resMap);
      if (resKeys.length) {
        html += '<div class="section-title">Recursos del workspace (GET)</div><div class="kv">';
        resKeys.forEach(function (k) {
          var info = resMap[k] || {};
          var ex = (info.existing && info.existing.length) ? info.existing.join(", ") : "—";
          var mark = info.checked ? "" : " (sin verificar)";
          html += "<div><b>" + esc(k) + "</b>" + esc(mark) + ": " + esc(ex) + "</div>";
        });
        html += "</div>";
      }

      if (s.to_create && s.to_create.length) {
        html += '<div class="section-title">Por crear (POST)</div><div class="kv">';
        s.to_create.forEach(function (it) {
          var v = it.verified ? "" : " · pendiente de verificar";
          var d = it.decision || "create";
          var icon = d === "reuse" ? "♻️" : (d === "skip" ? "⤫" : "➕");
          var badge = " <span class='muted'>[" + esc(d) + "]</span>";
          html += "<div>" + icon + " <b>" + esc(it.resource_type) + "</b> " + esc(it.name) +
            badge + " — " + esc(it.reason) + esc(v) + "</div>";
        });
        html += "</div>";
      }

      if (s.blockers && s.blockers.length) {
        html += '<div class="section-title">Bloqueos</div><div class="kv">';
        html += s.blockers.map(function (x) { return "⛔ " + esc(x); }).join("<br/>");
        html += "</div>";
      }

      var val = s.validation || null;
      if (val) {
        html += '<div class="section-title">Validación</div><div class="kv">';
        (val.checks || []).forEach(function (c) {
          html += "<div>" + (c.ok ? "✅" : "⚠️") + " <b>" + esc(c.name) + "</b> — " +
            esc(c.detail) + "</div>";
        });
        (val.fixes || []).forEach(function (f) {
          html += "<div>🔧 " + esc(f.fix) + "</div>";
        });
        if (val.should_redeploy) {
          html += "<div class='muted'>Sugerencia: corrige y vuelve a desplegar.</div>";
        }
        html += "</div>";
      }

      html += '<div class="section-title">Permisos solicitados</div><div class="list">';
      (s.permissions || []).forEach(function (p) {
        html += '<div class="perm"><div class="perm-top"><span class="perm-label">' + esc(p.label) +
          '</span><span class="tag ' + (p.satisfied ? "ok" : "no") + '">' +
          (p.satisfied ? "OK" : "requiere acceso") + "</span></div></div>";
      });
      html += "</div>";

      if (s.requires_approval && s.requires_approval.length) {
        html += '<div class="section-title">Requiere tu aprobación</div><div class="kv">';
        html += s.requires_approval.map(function (x) { return "⚠️ " + esc(x); }).join("<br/>");
        html += "</div>";
      }
      if (s.next_actions && s.next_actions.length) {
        html += '<div class="section-title">Próximos pasos</div><div class="kv">';
        html += s.next_actions.map(function (x) { return "→ " + esc(x); }).join("<br/>");
        html += "</div>";
      }

      html += '<details class="tech"><summary>Detalles técnicos (IDs)</summary><pre>' +
        esc(JSON.stringify(s.ids || {}, null, 2)) + "</pre></details>";

      body.innerHTML = html;
      results.classList.add("show");
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    document.getElementById("run-form").addEventListener("submit", async function (event) {
      event.preventDefault();
      var btn = document.getElementById("run-btn");
      var err = document.getElementById("form-error");
      err.style.display = "none";
      btn.disabled = true;
      btn.textContent = "Creando tu app…";
      var payload = {
        primary_use_case_description: document.getElementById("use_case").value.trim(),
        user_stories: splitLines(document.getElementById("stories").value),
        gold_tables: splitLines(document.getElementById("gold_tables").value),
        existing_genies: splitLines(document.getElementById("genies").value),
        workflow_requirements: document.getElementById("workflow").value.trim(),
        style_preferences: document.getElementById("style").value.trim() || "Tema oscuro, simple.",
        access_requirements: document.getElementById("access").value.trim()
      };
      try {
        var r = await fetch("/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        var data = await r.json();
        if (!r.ok) throw new Error((data && data.detail) ? data.detail : JSON.stringify(data));
        renderSummary(data);
        loadAuth();
      } catch (e) {
        err.textContent = "No pudimos completar el proceso: " + e.message;
        err.style.display = "block";
      } finally {
        btn.disabled = false;
        btn.textContent = "Crear mi app";
      }
    });

    loadAuth();
  </script>
</body>
</html>
"""
