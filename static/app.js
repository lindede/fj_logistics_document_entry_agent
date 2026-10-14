/** 中文标签（key 顺序以 /api/schemas/booking_data 为准） */
const FIELD_LABELS = {
  shipper: "发货人",
  consignee: "收货人",
  notify_party: "通知方",
  vessel: "船名",
  voyage: "航次",
  port_of_loading: "装货港",
  port_of_discharge: "目的港",
  containers: "箱型箱量",
  container_type: "箱型",
  container_qty: "箱量",
  packages_qty: "件数",
  packages_unit: "包装单位",
  goods_desc: "品名",
  gross_weight: "毛重",
  weight_unit: "重量单位",
  measurement: "体积",
  measurement_unit: "体积单位",
  hs_code: "HS CODE",
  marks: "唛头",
  freight: "运费条款",
};

/** fallback：schema 未加载时仍可展示 */
let KEY_FIELDS = Object.keys(FIELD_LABELS)
  .filter((k) => !["containers", "container_type", "container_qty"].includes(k))
  .map((k) => [k, FIELD_LABELS[k]]);

/** 来自 GET /api/schemas/booking_data */
let BOOKING_SCHEMA = null;

let state = { status: "Idle" };
let confirmResolver = null;

function propOf(key) {
  return (BOOKING_SCHEMA && BOOKING_SCHEMA.properties && BOOKING_SCHEMA.properties[key]) || {};
}

function typeList(prop) {
  const t = prop.type;
  if (Array.isArray(t)) return t;
  if (t == null) return ["string"];
  return [t];
}

function allowsNull(prop) {
  return typeList(prop).includes("null");
}

function isUiRequired(key, prop) {
  if (key === "voyage" || key === "containers") return false;
  if (allowsNull(prop)) return false;
  const req = BOOKING_SCHEMA?.required || [];
  if (!req.includes(key)) return false;
  return true;
}

function labelHtml(key, label, confTxt) {
  const prop = propOf(key);
  const star = isUiRequired(key, prop)
    ? `<span class="req" title="必填">*</span>`
    : allowsNull(prop)
      ? `<span class="opt" title="可空">可空</span>`
      : "";
  return `${label}${star}${confTxt}`;
}

function controlHtml(key, value, { readonly = false } = {}) {
  const prop = propOf(key);
  const types = typeList(prop);
  const req = isUiRequired(key, prop);
  const reqAttr = req && !readonly ? "required" : "";
  const roAttr = readonly ? "readonly disabled" : "";
  const title = prop.description || "";

  if (prop.enum) {
    const opts = prop.enum
      .filter((x) => x !== null && x !== undefined)
      .map((x) => {
        const sel = String(value ?? "") === String(x) ? " selected" : "";
        return `<option value="${esc(x)}"${sel}>${esc(x)}</option>`;
      })
      .join("");
    const emptySel = value == null || value === "" ? " selected" : "";
    const emptyOpt = allowsNull(prop)
      ? `<option value=""${emptySel}>（空）</option>`
      : "";
    return `<select data-key="${key}" ${reqAttr} ${roAttr} title="${esc(title)}">${emptyOpt}${opts}</select>`;
  }

  if (types.includes("integer")) {
    const min = prop.minimum != null ? `min="${prop.minimum}"` : "";
    return `<input data-key="${key}" type="number" step="1" ${min} ${reqAttr} ${roAttr} value="${esc(value ?? "")}" title="${esc(title)}" />`;
  }
  if (types.includes("number")) {
    const min =
      prop.exclusiveMinimum != null
        ? `min="${prop.exclusiveMinimum}"`
        : prop.minimum != null
          ? `min="${prop.minimum}"`
          : "";
    const ex =
      prop.exclusiveMinimum != null
        ? `data-exclusive-min="${prop.exclusiveMinimum}"`
        : "";
    return `<input data-key="${key}" type="number" step="any" ${min} ${reqAttr} ${roAttr} value="${esc(value ?? "")}" title="${esc(title)}" ${ex} />`;
  }

  const minLen = prop.minLength != null && req && !readonly ? `minlength="${prop.minLength}"` : "";
  return `<input data-key="${key}" type="text" ${minLen} ${reqAttr} ${roAttr} value="${esc(value ?? "")}" title="${esc(title)}" />`;
}

function issuesByField(issues) {
  const map = {};
  for (const i of issues || []) {
    let f = i.field;
    if (!f || f.startsWith("_")) continue;
    if (f === "containers" || f.startsWith("containers")) f = "containers";
    if (!map[f]) map[f] = [];
    map[f].push(i);
  }
  return map;
}

function worstLevel(list) {
  if ((list || []).some((i) => i.level === "FAIL")) return "fail";
  if ((list || []).some((i) => i.level === "WARN")) return "warn";
  return "";
}

function fieldErrorText(list) {
  return (list || [])
    .map((i) => `${i.level}: ${i.message || i.rule || ""}`)
    .join(" · ");
}

async function loadBookingSchema() {
  try {
    const schema = await api("/api/schemas/booking_data");
    BOOKING_SCHEMA = schema;
    const keys = Object.keys(schema.properties || {});
    KEY_FIELDS = keys.map((k) => [k, FIELD_LABELS[k] || k]);
  } catch (_) {
    /* 保留 fallback */
  }
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      try {
        detail = await res.text();
      } catch (_) {}
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function mapStep(status) {
  if (status === "Idle") return "Idle";
  if (status === "Parsing" || status === "Validating") return "Processing";
  if (status === "AwaitConfirm" || status === "AwaitHuman") return "Await";
  if (status === "Done") return "Done";
  return "Idle";
}

function isBusyStatus(st) {
  return st && st !== "Idle" && st !== "Done";
}

const STEP_ORDER = ["Idle", "Processing", "Await", "Done"];

function paintStepper(status, justDone) {
  const cur = justDone ? "Done" : mapStep(status);
  const idx = Math.max(0, STEP_ORDER.indexOf(cur));
  document.querySelectorAll(".step").forEach((el) => {
    const i = STEP_ORDER.indexOf(el.dataset.step);
    el.classList.toggle("active", i === idx);
    el.classList.toggle("done", i >= 0 && i < idx);
  });
  document.querySelectorAll(".step-line").forEach((el, i) => {
    el.classList.toggle("filled", i < idx);
  });
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderIdle(s) {
  const note = s.message
    ? `<p class="sub">${esc(s.message)}</p>`
    : `<p class="sub">也可在底部输入「开票」并上传；提交或撤销后回到空闲。</p>`;
  return `<div class="dropzone" id="idle-dropzone" role="button" tabindex="0">
    <strong>拖入托运单 PDF</strong>
    <p class="sub">或点击此处 / 左下角选择文件</p>
    ${note}
  </div>`;
}

function renderProcessing(s) {
  return `<div class="loading">
    <div class="spinner"></div>
    <div>处理中… ${esc(s.filename || "")}</div>
    <div>${esc(s.message || "")}</div>
  </div>`;
}

function firstContainer(data) {
  const arr = data.containers;
  if (Array.isArray(arr) && arr.length) return arr[0];
  return { type: "", qty: "" };
}

function renderContainerFields(
  data,
  report,
  fieldIssues,
  { readonly = false, highlight = false, showIssues = true } = {}
) {
  const c0 = firstContainer(data);
  const conf = (report.field_confidence || {}).containers;
  const confTxt =
    conf == null || readonly
      ? ""
      : ` <span style="color:#999">(${Number(conf).toFixed(2)})</span>`;
  const star = readonly ? "" : `<span class="req" title="必填">*</span>`;
  const iss = fieldIssues.containers || [];
  const lvl = showIssues ? worstLevel(iss) : "";
  const err = showIssues ? fieldErrorText(iss) : "";
  const roAttr = readonly ? "readonly disabled" : "";
  const reqAttr = readonly ? "" : "required minlength=\"1\"";
  const qtyReq = readonly ? "" : "required min=\"1\"";
  const amended = highlight ? " field-amended" : "";
  const extra =
    Array.isArray(data.containers) && data.containers.length > 1
      ? `<div class="field-hint">另有 ${data.containers.length - 1} 组箱型箱量，提交时保留</div>`
      : "";
  return `<div class="field-block">
      <div class="field-row field-row-containers ${lvl ? `has-${lvl}` : ""}${amended}" data-issue-field="containers">
        <label>${FIELD_LABELS.container_type}${star}${confTxt}</label>
        <input data-ui="container_type" ${reqAttr} ${roAttr} value="${esc(c0.type ?? "")}" placeholder="如 40HQ" />
        <label class="field-label-qty">${FIELD_LABELS.container_qty}${star}${confTxt}</label>
        <input data-ui="container_qty" type="number" ${qtyReq} step="1" ${roAttr} value="${esc(c0.qty ?? "")}" placeholder="数量" />
        ${err ? `<div class="field-error">${esc(err)}</div>` : ""}
      </div>
      ${extra}
    </div>`;
}

function actionButtonsHtml(s) {
  const overall = (s.validation_report || {}).overall || "";
  const st = s.status || "";
  if (st === "Done") {
    return "";
  }
  const awaitOk = st === "AwaitConfirm" || st === "AwaitHuman";
  // 无问题才能普通提交；WARN/FAIL 走强制提交
  const canSubmit = awaitOk && overall === "PASS";
  const canForce = awaitOk && (overall === "WARN" || overall === "FAIL");
  const canVoid = awaitOk;
  return `<div class="actions">
    <button type="button" id="btn-submit" ${canSubmit ? "" : "disabled"}>提交</button>
    <button type="button" id="btn-force" class="secondary" ${canForce ? "" : "disabled"}>强制提交</button>
    <button type="button" id="btn-void" class="secondary" ${canVoid ? "" : "disabled"}>撤销</button>
  </div>`;
}

function renderResult(s) {
  const data = s.validated_data || {};
  const report = s.validation_report || {};
  const overall = report.overall || "?";
  const issues = report.issues || [];
  const fieldIssues = issuesByField(issues);
  const isDone = s.status === "Done";
  const isHuman = s.status === "AwaitHuman";
  const statusLabel = isDone ? "已完成" : isHuman ? "待人工处理" : "待确认";
  const highlight = new Set(s.highlight_fields || []);
  const errorFields = new Set(s.error_fields || []);
  const showDoneIssues = isDone && (issues.length > 0 || highlight.size > 0 || errorFields.size > 0);
  const rows = KEY_FIELDS.map(([k, label]) => {
    if (k === "containers") {
      return renderContainerFields(data, report, fieldIssues, {
        readonly: isDone,
        highlight: highlight.has("containers"),
        showIssues: !isDone || showDoneIssues,
      });
    }
    const conf = (report.field_confidence || {})[k];
    const confTxt =
      conf == null || isDone
        ? ""
        : ` <span style="color:#999">(${Number(conf).toFixed(2)})</span>`;
    const val = data[k];
    const iss = fieldIssues[k] || [];
    const lvl = !isDone || showDoneIssues ? worstLevel(iss) : "";
    const err = !isDone || showDoneIssues ? fieldErrorText(iss) : "";
    const amended = highlight.has(k) ? " field-amended" : "";
    const errMark = errorFields.has(k) && !lvl ? " has-fail" : "";
    const labelPart = isDone ? esc(label) : labelHtml(k, label, confTxt);
    return `<div class="field-row">
      <label for="f-${k}">${labelPart}</label>
      <div class="field-control ${lvl ? `has-${lvl}` : ""}${errMark}${amended}" data-issue-field="${k}">
        ${controlHtml(k, val, { readonly: isDone })}
        ${err ? `<div class="field-error">${esc(err)}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const fieldIssueCount = Object.keys(fieldIssues).length;
  const issueHtml = issues
    .map(
      (i) => `<div class="issue"><span class="badge ${i.level}">${i.level}</span>
      <strong>${esc(i.rule)}</strong> · ${esc(i.field)} — ${esc(i.message)}</div>`
    )
    .join("") || `<div class="issue">无规则问题</div>`;

  const hist = (s.history || [])
    .slice(-8)
    .map((h) => `${esc(h.at)} ${esc(h.action)}/${esc(h.actor)}`)
    .join("<br/>");

  const statusBar = isDone
    ? ""
    : `<div style="margin-bottom:12px">
        <span class="badge ${overall}">${overall}</span>
        <span style="margin-left:8px;color:#6b6560">${esc(statusLabel)}</span>
        <span class="schema-legend"><span class="req">*</span> 必填 · <span class="opt">可空</span> 可为空</span>
      </div>`;

  let amendBanner = "";
  if (isDone && s.message) {
    const kind =
      s.amend_written === true
        ? "ok"
        : s.amend_written === false
          ? "fail"
          : "info";
    amendBanner = `<div class="amend-banner amend-${kind}" role="status">${esc(s.message)}</div>`;
  }

  const trace = s.amend_trace;
  let traceHtml = "";
  if (isDone && trace && Array.isArray(trace.steps)) {
    const lines = trace.steps
      .map((st) => {
        const ok = st.ok === true ? "✓" : st.ok === false ? "✗" : "·";
        const name = st.step || "?";
        const extra =
          st.summary ||
          (st.patches ? JSON.stringify(st.patches) : "") ||
          st.error ||
          st.raw_arguments ||
          "";
        const short =
          typeof extra === "string"
            ? extra.slice(0, 160)
            : extra
              ? JSON.stringify(extra).slice(0, 160)
              : "";
        return `<div class="trace-line"><span class="trace-ok">${ok}</span> <code>${esc(name)}</code>${
          short ? ` — ${esc(short)}` : ""
        }</div>`;
      })
      .join("");
    const dump = trace.dump_path
      ? `<div class="trace-dump">落盘：${esc(trace.dump_path)}</div>`
      : "";
    const understood =
      s.understood && typeof s.understood === "object"
        ? `<div class="trace-understood"><strong>分析结果</strong> ${esc(
            JSON.stringify(s.understood)
          )}</div>`
        : "";
    traceHtml = `<div class="amend-trace">
      <div><strong>指令轨迹</strong> <span style="color:#999">${esc(trace.text_model || "")}</span></div>
      <div class="trace-user"><strong>原指令</strong>「${esc(trace.user_text || "")}」</div>
      ${understood}
      ${lines}${dump}
    </div>`;
  }

  return `<div class="grid">
    <div>
      ${statusBar}
      ${amendBanner}
      <form id="booking-form" class="fields ${isDone ? "fields-readonly" : ""}" novalidate>${rows}</form>
      ${actionButtonsHtml(s)}
    </div>
    <div class="report">
      <div><strong>校验报告</strong></div>
      <div style="margin:8px 0;color:#6b6560">${esc(report.suggested_action || "")}</div>
      <div class="issue-summary">${fieldIssueCount ? `${fieldIssueCount} 个字段有问题（悬停字段可查看）` : "字段无问题"}</div>
      ${issueHtml}
      ${traceHtml}
      <div class="history">${hist}</div>
    </div>
  </div>`;
}

function setReplaceModal(open) {
  const modal = document.getElementById("replace-modal");
  if (!modal) return;
  modal.hidden = !open;
}

function openConfirm({ title, body, okLabel, okClass }) {
  return new Promise((resolve) => {
    const modal = document.getElementById("confirm-modal");
    const t = document.getElementById("confirm-modal-title");
    const b = document.getElementById("confirm-modal-body");
    const ok = document.getElementById("confirm-ok");
    if (!modal || !ok) {
      resolve(false);
      return;
    }
    confirmResolver = resolve;
    t.textContent = title || "确认";
    b.textContent = body || "";
    ok.textContent = okLabel || "确认";
    ok.className = okClass || "";
    modal.hidden = false;
  });
}

function closeConfirm(result) {
  const modal = document.getElementById("confirm-modal");
  if (modal) modal.hidden = true;
  const r = confirmResolver;
  confirmResolver = null;
  if (r) r(result);
}

function bindIdleDropzone() {
  const dz = document.getElementById("idle-dropzone");
  const file = document.getElementById("file");
  if (!dz || !file) return;
  const openPicker = () => file.click();
  dz.addEventListener("click", openPicker);
  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.remove("drag");
    })
  );
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f) uploadFile(f);
  });
}

function bindResultActions() {
  const sub = document.getElementById("btn-submit");
  const force = document.getElementById("btn-force");
  const vo = document.getElementById("btn-void");
  if (sub) sub.onclick = () => submitWithPatches({ force: false });
  if (force) {
    force.onclick = async () => {
      const overall = (state?.validation_report || {}).overall || "";
      const detail =
        overall === "FAIL"
          ? "当前校验未通过（FAIL），存在错误项。"
          : "当前存在校验警告（WARN）。";
      const ok = await openConfirm({
        title: "确认强制提交？",
        body: `${detail}强制提交将带问题入库，请确认业务可接受。`,
        okLabel: "确认强制提交",
        okClass: "",
      });
      if (ok) submitWithPatches({ force: true });
    };
  }
  if (vo) {
    vo.onclick = async () => {
      const ok = await openConfirm({
        title: "确认撤销？",
        body: "将作废当前单据并回到空闲，未提交内容不会保留。",
        okLabel: "确认撤销",
        okClass: "",
      });
      if (ok) act({ action: "void" });
    };
  }
}

function render(s, justDone = false) {
  state = s;
  const st = s.status || "Idle";
  paintStepper(st, justDone || st === "Done");
  const main = document.getElementById("main");
  if (st === "Idle") main.innerHTML = renderIdle(s);
  else if (st === "Parsing" || st === "Validating") main.innerHTML = renderProcessing(s);
  else main.innerHTML = renderResult(s);

  const footerMsg = document.getElementById("msg");
  // 空闲不在底栏重复喊话；有业务消息时再显示
  if (st === "Idle") {
    footerMsg.textContent = "";
  } else {
    footerMsg.textContent = s.message || "";
  }
  setReplaceModal(Boolean(s.replace_pending));

  if (st === "Idle") bindIdleDropzone();
  else if (st === "AwaitConfirm" || st === "AwaitHuman") bindResultActions();
  syncSendButton();
}

function showError(err) {
  const msg = err?.message || String(err);
  document.getElementById("msg").textContent = `出错：${msg}`;
  const main = document.getElementById("main");
  main.innerHTML = `<div class="hint"><p><strong>请求失败</strong></p><p>${esc(msg)}</p>
    <p>常见原因：大模型限流(429)、网络超时。可稍后重试，或点「撤销」清空会话。</p>
    <div class="actions"><button id="btn-retry-refresh" type="button">刷新状态</button></div></div>`;
  const b = document.getElementById("btn-retry-refresh");
  if (b) b.onclick = () => refresh().catch((e) => showError(e));
}

async function refresh() {
  const s = await api("/api/session");
  render(s);
}

function applyUiPatches(patches) {
  if (!patches || typeof patches !== "object") return;
  Object.entries(patches).forEach(([k, v]) => {
    if (k.startsWith("_")) return;
    if (k === "containers") {
      const c0 = Array.isArray(v) && v[0] ? v[0] : {};
      const t = document.querySelector('[data-ui="container_type"]');
      const q = document.querySelector('[data-ui="container_qty"]');
      if (t) t.value = c0.type == null ? "" : String(c0.type);
      if (q) q.value = c0.qty == null ? "" : String(c0.qty);
      return;
    }
    const el = document.querySelector(`[data-key="${CSS.escape(k)}"]`);
    if (!el) return;
    if (v != null && typeof v === "object") {
      el.value = JSON.stringify(v);
    } else {
      el.value = v == null ? "" : String(v);
    }
  });
}

async function act(body) {
  try {
    const s = await api("/api/session/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    render(s, s.status === "Done");
    return s;
  } catch (err) {
    showError(err);
    return null;
  }
}

function collectContainersPatch() {
  const typeEl = document.querySelector('[data-ui="container_type"]');
  const qtyEl = document.querySelector('[data-ui="container_qty"]');
  if (!typeEl && !qtyEl) return undefined;
  const type = (typeEl?.value || "").trim();
  const qtyRaw = (qtyEl?.value || "").trim();
  const qty = qtyRaw === "" ? null : Number(qtyRaw);
  const rest = Array.isArray(state.validated_data?.containers)
    ? state.validated_data.containers.slice(1)
    : [];
  if (!type && (qty == null || Number.isNaN(qty))) {
    return rest.length ? rest : null;
  }
  const first = {
    type: type || "",
    qty: qty != null && !Number.isNaN(qty) ? qty : 1,
  };
  return [first, ...rest];
}

function buildPatchesFromForm() {
  const patches = {};
  document.querySelectorAll("[data-key]").forEach((el) => {
    const k = el.dataset.key;
    const prop = propOf(k);
    let v = el.value;
    const types = typeList(prop);
    if ((types.includes("integer") || types.includes("number")) && v !== "") {
      v = Number(v);
      if (types.includes("integer")) v = Math.trunc(v);
    }
    if (v === "") v = allowsNull(prop) || k === "voyage" ? (k === "voyage" ? "" : null) : v;
    if (v === "" && allowsNull(prop)) v = null;
    patches[k] = v;
  });
  const containers = collectContainersPatch();
  if (containers !== undefined) patches.containers = containers;
  return patches;
}

function validateFormAgainstSchema() {
  const form = document.getElementById("booking-form");
  if (!form) return true;
  if (!form.checkValidity()) {
    form.reportValidity();
    return false;
  }
  for (const el of form.querySelectorAll("[data-exclusive-min]")) {
    const ex = el.dataset.exclusiveMin;
    if (ex === "" || ex == null) continue;
    const n = Number(el.value);
    if (el.value !== "" && !(n > Number(ex))) {
      el.setCustomValidity(`须大于 ${ex}`);
      el.reportValidity();
      el.setCustomValidity("");
      return false;
    }
  }
  const typeEl = document.querySelector('[data-ui="container_type"]');
  const qtyEl = document.querySelector('[data-ui="container_qty"]');
  if (typeEl && !typeEl.checkValidity()) {
    typeEl.reportValidity();
    return false;
  }
  if (qtyEl && !qtyEl.checkValidity()) {
    qtyEl.reportValidity();
    return false;
  }
  return true;
}

async function submitWithPatches({ force }) {
  if (!force && !validateFormAgainstSchema()) return;
  const patches = buildPatchesFromForm();
  const afterPatch = await act({ action: "patch", patches });
  if (!afterPatch) return;
  const overall = afterPatch.validation_report?.overall;
  if (!force && overall !== "PASS") {
    const msg = document.getElementById("msg");
    if (msg) {
      msg.textContent =
        afterPatch.message ||
        `仍有 ${overall || "问题"}，请修正字段或使用强制提交`;
    }
    return;
  }
  await act({ action: "submit", force: !!force });
}

/** PDF 按钮已确认放弃时置 true，避免选文件后再弹一次 */
let skipAbandonConfirmOnce = false;

async function confirmAbandonIfBusy() {
  const st = state.status || "Idle";
  if (!isBusyStatus(st)) return true;
  return openConfirm({
    title: "放弃当前单据？",
    body: "上传新 PDF 将作废当前进行中的单据并重新解析。",
    okLabel: "确认放弃并上传",
    okClass: "",
  });
}

async function uploadFile(file) {
  const busy = isBusyStatus(state.status || "Idle");
  if (skipAbandonConfirmOnce) {
    skipAbandonConfirmOnce = false;
  } else {
    const ok = await confirmAbandonIfBusy();
    if (!ok) return;
  }
  const fd = new FormData();
  fd.append("file", file);
  render({
    status: "Parsing",
    filename: file.name,
    message: "上传并调用大模型解析中（约 10–60 秒；遇限流会自动重试）…",
  });
  try {
    const s = await api("/api/session/upload", { method: "POST", body: fd });
    // 进行中已确认放弃：后端若返回 replace_pending，自动确认换票
    if (s.replace_pending && busy) {
      setReplaceModal(false);
      await act({ action: "confirm_replace" });
      return;
    }
    render(s);
  } catch (err) {
    showError(err);
  }
}

function bindConfirmModal() {
  const cancel = document.getElementById("confirm-cancel");
  const ok = document.getElementById("confirm-ok");
  const backdrop = document.querySelector("#confirm-modal [data-confirm-cancel]");
  if (cancel) cancel.onclick = () => closeConfirm(false);
  if (ok) ok.onclick = () => closeConfirm(true);
  if (backdrop) backdrop.onclick = () => closeConfirm(false);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const modal = document.getElementById("confirm-modal");
      if (modal && !modal.hidden) closeConfirm(false);
    }
  });
}

function bindReplaceModal() {
  const confirmBtn = document.getElementById("modal-confirm-replace");
  const cancelBtn = document.getElementById("modal-cancel-replace");
  const backdrop = document.querySelector("#replace-modal [data-modal-cancel]");
  if (confirmBtn) {
    confirmBtn.onclick = () => {
      setReplaceModal(false);
      render({
        ...state,
        replace_pending: false,
        status: "Parsing",
        message: "已确认换票，正在解析新 PDF…",
      });
      act({ action: "confirm_replace" });
    };
  }
  const cancel = () => act({ action: "cancel_replace" });
  if (cancelBtn) cancelBtn.onclick = cancel;
  if (backdrop) backdrop.onclick = cancel;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.replace_pending) cancel();
  });
}

function syncComposerVisibility() {
  const bottom = document.querySelector(".chrome-bottom");
  const composer = document.getElementById("composer");
  const btnPdf = document.getElementById("btn-pdf");
  const cmd = document.getElementById("cmd");
  const send = document.getElementById("send");
  if (!cmd || !send) return;
  const st = state.status || "Idle";
  // 底栏仅 Done：PDF + 指令；Idle/处理中整栏隐藏；Await 只留消息条
  const showChat = st === "Done";
  const showMsgOnly = st === "AwaitConfirm" || st === "AwaitHuman";
  if (btnPdf) btnPdf.hidden = !showChat;
  cmd.hidden = !showChat;
  send.hidden = !showChat;
  if (!showChat) cmd.value = "";
  else cmd.placeholder = "用指令修正已提交数据，如：毛重单位从 KGS 换成 TON";
  if (composer) {
    composer.classList.remove("composer-pdf-only");
    composer.hidden = !showChat;
  }
  if (bottom) {
    bottom.hidden = !(showChat || showMsgOnly);
    bottom.classList.toggle("chrome-msg-only", showMsgOnly);
  }
  const hasText = Boolean(cmd.value.trim());
  send.disabled = !(showChat && hasText);
}

function syncSendButton() {
  syncComposerVisibility();
}

function bindComposer() {
  const composer = document.getElementById("composer");
  const file = document.getElementById("file");
  const btnPdf = document.getElementById("btn-pdf");
  const cmd = document.getElementById("cmd");
  const send = document.getElementById("send");

  if (btnPdf) {
    btnPdf.addEventListener("click", async () => {
      const busy = isBusyStatus(state.status || "Idle");
      if (busy) {
        const ok = await confirmAbandonIfBusy();
        if (!ok) return;
        skipAbandonConfirmOnce = true;
      }
      file.click();
    });
  }

  file.addEventListener("change", () => {
    if (file.files?.[0]) {
      uploadFile(file.files[0]);
      file.value = "";
    }
  });
  send.addEventListener("click", async () => {
    const text = cmd.value.trim();
    if (!text || send.disabled) return;
    cmd.value = "";
    send.disabled = true;
    const footerMsg = document.getElementById("msg");
    if (footerMsg) footerMsg.textContent = "指令识别与执行中…";
    const banner = document.querySelector(".amend-banner");
    if (banner) {
      banner.className = "amend-banner amend-info";
      banner.textContent = "指令识别与执行中…";
    }
    const s = await act({ action: "chat", text });
    if (s?.highlight_fields?.length) {
      const first = s.highlight_fields[0];
      const el =
        document.querySelector(`[data-issue-field="${CSS.escape(first)}"]`) ||
        document.querySelector(`[data-key="${CSS.escape(first)}"]`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    syncSendButton();
  });
  cmd.addEventListener("input", syncSendButton);
  cmd.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send.click();
  });
  syncSendButton();

  ["dragenter", "dragover"].forEach((ev) =>
    composer.addEventListener(ev, (e) => {
      e.preventDefault();
      composer.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    composer.addEventListener(ev, (e) => {
      e.preventDefault();
      composer.classList.remove("drag");
    })
  );
  composer.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f) uploadFile(f);
  });
}

bindConfirmModal();
bindReplaceModal();
bindComposer();
loadBookingSchema()
  .then(() => refresh())
  .catch((e) => {
    document.getElementById("main").innerHTML = `<div class="hint">后端未就绪：${esc(e.message)}</div>`;
  });
