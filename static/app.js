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
  .filter((k) => k !== "containers")
  .map((k) => [k, FIELD_LABELS[k]]);

let state = { status: "Idle" };

async function loadBookingSchema() {
  try {
    const schema = await api("/api/schemas/booking_data");
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
  return "Idle";
}

function paintStepper(status, justDone) {
  const cur = justDone ? "Done" : mapStep(status);
  document.querySelectorAll(".step").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === cur);
  });
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderIdle(s) {
  return `<div class="hint">
    <p><strong>准备开票。</strong>拖入托运单 PDF，或点击左下角选择文件。</p>
    <p>也可输入「开票」并上传；提交后回到空闲。</p>
    <p class="msg">${esc(s.message || "")}</p>
  </div>`;
}

function renderProcessing(s) {
  return `<div class="loading">
    <div class="spinner"></div>
    <div>处理中… ${esc(s.filename || "")}</div>
    <div>${esc(s.message || "")}</div>
  </div>`;
}

function renderResult(s) {
  const data = s.validated_data || {};
  const report = s.validation_report || {};
  const overall = report.overall || "?";
  const issues = report.issues || [];
  const isHuman = s.status === "AwaitHuman";
  const rows = KEY_FIELDS.map(([k, label]) => {
    const conf = (report.field_confidence || {})[k];
    const confTxt = conf == null ? "" : ` <span style="color:#999">(${Number(conf).toFixed(2)})</span>`;
    let val = data[k];
    if (k === "containers" && Array.isArray(val)) val = JSON.stringify(val);
    return `<div class="field-row">
      <label>${label}${confTxt}</label>
      <input data-key="${k}" value="${esc(val ?? "")}" />
    </div>`;
  }).join("");

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

  return `<div class="grid">
    <div>
      <div style="margin-bottom:12px">
        <span class="badge ${overall}">${overall}</span>
        <span style="margin-left:8px;color:#6b6560">${isHuman ? "待人工处理" : "待确认"}</span>
      </div>
      <div class="fields">${rows}</div>
      <div class="actions">
        <button id="btn-revalidate">保存并再校验</button>
        <button id="btn-submit" class="${overall === "FAIL" ? "secondary" : ""}">提交</button>
        <button id="btn-void" class="secondary danger">作废</button>
      </div>
    </div>
    <div class="report">
      <div><strong>校验报告</strong></div>
      <div style="margin:8px 0;color:#6b6560">${esc(report.suggested_action || "")}</div>
      ${issueHtml}
      <div class="history">${hist}</div>
    </div>
  </div>
  <p class="msg">${esc(s.message || "")}</p>`;
}

function setReplaceModal(open) {
  const modal = document.getElementById("replace-modal");
  if (!modal) return;
  modal.hidden = !open;
}

function render(s, justDone = false) {
  state = s;
  paintStepper(s.status || "Idle", justDone);
  const main = document.getElementById("main");
  const st = s.status || "Idle";
  if (st === "Idle") main.innerHTML = renderIdle(s);
  else if (st === "Parsing" || st === "Validating") main.innerHTML = renderProcessing(s);
  else main.innerHTML = renderResult(s);

  document.getElementById("msg").textContent = s.message || "";
  setReplaceModal(Boolean(s.replace_pending));

  const re = document.getElementById("btn-revalidate");
  const sub = document.getElementById("btn-submit");
  const vo = document.getElementById("btn-void");
  if (re) re.onclick = saveAndRevalidate;
  if (sub) sub.onclick = () => act({ action: "submit" });
  if (vo) vo.onclick = () => act({ action: "void" });
}

function showError(err) {
  const msg = err?.message || String(err);
  document.getElementById("msg").textContent = `出错：${msg}`;
  const main = document.getElementById("main");
  main.innerHTML = `<div class="hint"><p><strong>请求失败</strong></p><p>${esc(msg)}</p>
    <p>常见原因：大模型限流(429)、网络超时。可稍后重试，或先点「作废」清空会话。</p>
    <div class="actions"><button id="btn-retry-refresh" type="button">刷新状态</button></div></div>`;
  const b = document.getElementById("btn-retry-refresh");
  if (b) b.onclick = () => refresh().catch((e) => showError(e));
}

async function refresh() {
  const s = await api("/api/session");
  render(s);
}

async function act(body) {
  try {
    const s = await api("/api/session/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const done =
      (body.action === "submit" || /已提交|已自动提交/.test(s.message || "")) &&
      s.status === "Idle";
    render(s, done);
    if (done) setTimeout(() => refresh().catch(() => {}), 1200);
  } catch (err) {
    showError(err);
  }
}

async function saveAndRevalidate() {
  const patches = {};
  document.querySelectorAll("[data-key]").forEach((el) => {
    const k = el.dataset.key;
    let v = el.value;
    if (["packages_qty", "gross_weight", "measurement"].includes(k) && v !== "") {
      v = Number(v);
    }
    if (k === "containers" && v) {
      try { v = JSON.parse(v); } catch (_) {}
    }
    if (v === "") v = null;
    patches[k] = v;
  });
  await act({ action: "patch", patches });
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  render({
    status: "Parsing",
    filename: file.name,
    message: "上传并调用大模型解析中（约 10–60 秒；遇限流会自动重试）…",
  });
  try {
    const s = await api("/api/session/upload", { method: "POST", body: fd });
    render(s);
  } catch (err) {
    showError(err);
  }
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

function bindComposer() {
  const composer = document.getElementById("composer");
  const file = document.getElementById("file");
  const cmd = document.getElementById("cmd");
  const send = document.getElementById("send");

  file.addEventListener("change", () => {
    if (file.files?.[0]) {
      uploadFile(file.files[0]);
      file.value = "";
    }
  });
  send.addEventListener("click", async () => {
    const text = cmd.value.trim();
    if (!text) return;
    cmd.value = "";
    await act({ action: "chat", text });
  });
  cmd.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send.click();
  });

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

bindReplaceModal();
bindComposer();
loadBookingSchema()
  .then(() => refresh())
  .catch((e) => {
    document.getElementById("main").innerHTML = `<div class="hint">后端未就绪：${esc(e.message)}</div>`;
  });
