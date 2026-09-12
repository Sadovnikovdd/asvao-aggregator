"use strict";

const views = {
  inbox: { title: "Входящие прайс-листы", short: "Входящие", eyebrow: "01 / ПРИЁМ И ПРОВЕРКА", description: "От исходного файла к проверенному каталогу. Новый формат всегда проходит через настройку." },
  catalog: { title: "Текущий каталог", short: "Каталог", eyebrow: "02 / АКТУАЛЬНЫЕ ДАННЫЕ", description: "Позиции из активных снимков поставщиков. Исходные значения и происхождение доступны для каждой строки." },
  shipments: { title: "История поставок", short: "История поставок", eyebrow: "03 / НЕИЗМЕНЯЕМЫЕ СНИМКИ", description: "Каждая обработка сохраняется отдельно. Проверьте результат, разберите исключения или вернитесь к прошлому снимку." },
  profiles: { title: "Профили форматов", short: "Профили форматов", eyebrow: "04 / ПРОВЕРЕННЫЕ ПРАВИЛА", description: "Границы, сопоставления и политики в неизменяемых ревизиях. Совпадение отпечатка проверяется на сервере." },
  system: { title: "Система и аудит", short: "Система и аудит", eyebrow: "05 / НАБЛЮДАЕМОСТЬ", description: "Фактические возможности сервиса, ограничения модулей и журнал принятых решений." }
};
const statusLabels = {
  review: "Нужна настройка", needs_review: "Нужна проверка", accepted: "Принято", quarantine: "Карантин", quarantined: "Карантин", rejected: "Отклонено", failed: "Ошибка", error: "Ошибка", duplicate: "Дубликат", deduplicated: "Уже загружен", uploaded: "Загружен", pending: "Ожидает", processing: "Обработка", active: "Активен", approved: "Подтверждено", inactive: "Неактивен", ok: "В порядке", unsupported: "Не поддерживается"
};
const targetOptions = [
  ["article", "Артикул"], ["name", "Наименование"], ["brand", "Бренд"], ["qty", "Количество"], ["price", "Цена"], ["barcode", "Штрихкод"], ["oem", "Номер OEM"], ["pack", "Фасовка"], ["currency", "Валюта"], ["availability", "Наличие"], ["extra", "Дополнительное поле"], ["drop", "Исключить с обоснованием"]
];
const modeOptions = [["", "Выберите режим явно"], ["replace_all", "Полная замена источника"], ["append", "Добавление к текущему снимку"], ["delta", "Изменения по ключам"]];
const modeDescriptions = {
  "": "Режим не выбран. Полная замена никогда не подставляется автоматически.",
  replace_all: "После успешной проверки новый снимок полностью заменит каталог этого источника.",
  append: "Сервер добавит позиции к текущему снимку источника. Проверьте, как ваш профиль задаёт ключи позиций.",
  delta: "Изменения применяются по заданным ключам и полю операции. Укажите их ниже; допустимость проверит сервер."
};
const policyFields = [
  { key: "hidden_rows", label: "Скрытые строки", options: [["include", "Включать"], ["skip", "Пропускать с записью причины"], ["quarantine", "Отправлять в карантин"]], value: "quarantine" },
  { key: "negative_price", label: "Отрицательная цена", options: [["quarantine", "Карантин"], ["accept", "Принимать"]], value: "quarantine" },
  { key: "empty_price", label: "Пустая цена", options: [["quarantine", "Карантин"], ["accept", "Принимать без цены"]], value: "quarantine" },
  { key: "multiple_prices", label: "Несколько цен", options: [["items", "Отдельная позиция для каждой цены"], ["extra", "Основная цена + дополнительные поля"]], value: "items" },
  { key: "hidden_cost", label: "Скрытая закупочная цена", options: [["quarantine", "Карантин"], ["drop", "Исключить с записью причины"]], value: "quarantine" }
];
let snapshot = { files: [], profiles: [], shipments: [], sources: [], settings: {}, capabilities: {} };
let currentView = "inbox";
let selectedFileId = null;
let fileDetail = null;
let draft = null;
let previewSignature = null;
let lastPreview = null;
let evidenceInput = null;
let fileRequest = 0;
let catalogRequest = 0;
let shipmentRequest = 0;
let profileRequest = 0;
let catalogOffset = 0;
let shipmentOffset = 0;
let selectedShipmentId = null;
let selectedProfileId = null;
let selectedProfileRevision = null;
let stateBusy = false;
let wizardBusy = false;
let draftChanged = false;
const pageSize = 100;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function sequence(value) {
  return Array.isArray(value) ? value : [];
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  return String(value);
}

function numberText(value) {
  const number = Number(value);
  return value !== null && value !== undefined && value !== "" && Number.isFinite(number) ? number.toLocaleString("ru-RU") : "—";
}

function dateText(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function bytesText(value) {
  const size = Number(value);
  if (!Number.isFinite(size)) return "—";
  return size >= 1048576 ? `${(size / 1048576).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} МБ` : `${Math.max(1, Math.round(size / 1024)).toLocaleString("ru-RU")} КБ`;
}

function columnLabel(index) {
  let label = "";
  for (let remaining = Number(index); remaining > 0; remaining = Math.floor((remaining - 1) / 26)) label = String.fromCharCode(65 + (remaining - 1) % 26) + label;
  return label;
}

function button(text, kind, action) {
  const element = node("button", `button ${kind || "button-secondary"}`, text);
  element.type = "button";
  if (action) element.addEventListener("click", action);
  return element;
}

function badge(status, label) {
  const value = String(status || "");
  const element = node("span", "badge", label || statusLabels[value] || value || "Статус не передан");
  if (["accepted", "approved", "active", "ok"].includes(value)) element.dataset.tone = "success";
  else if (["quarantine", "quarantined", "review", "needs_review", "pending"].includes(value)) element.dataset.tone = "warning";
  else if (["error", "failed", "rejected"].includes(value)) element.dataset.tone = "danger";
  else if (["processing", "uploaded"].includes(value)) element.dataset.tone = "info";
  return element;
}

function notice(text, tone = "info") {
  const element = node("div", "notice", text);
  element.dataset.tone = tone;
  element.setAttribute("role", tone === "danger" ? "alert" : "status");
  return element;
}

function announce(text, tone = "info") {
  const element = document.getElementById("global-message");
  element.textContent = text;
  element.dataset.tone = tone;
  element.setAttribute("role", tone === "danger" ? "alert" : "status");
  element.hidden = false;
}

function loading(container, text = "Загрузка…") {
  container.replaceChildren(node("p", "loading", text));
  container.setAttribute("aria-busy", "true");
}

function detailsJson(value, label = "Все поля и исходные значения") {
  const details = node("details", "evidence-details");
  details.append(node("summary", "", label), node("pre", "code-block", JSON.stringify(value, null, 2)));
  return details;
}

function input(type, value, attributes = {}) {
  const control = document.createElement("input");
  control.type = type;
  control.value = value ?? "";
  for (const [key, item] of Object.entries(attributes)) {
    if (item !== undefined && item !== null) control.setAttribute(key, String(item));
  }
  return control;
}

function select(options, value) {
  const control = document.createElement("select");
  const choices = options.slice();
  if (value !== undefined && value !== null && value !== "" && !choices.some(([key]) => key === String(value))) choices.push([String(value), String(value)]);
  for (const [key, title] of choices) {
    const option = node("option", "", title);
    option.value = key;
    control.append(option);
  }
  control.value = value ?? "";
  return control;
}

function field(label, control, hint, className = "") {
  const wrapper = node("label", `field ${className}`.trim());
  wrapper.append(node("span", "", label), control);
  if (hint) wrapper.append(node("span", "field-hint", hint));
  return wrapper;
}

function sectionHeading(title, step) {
  const heading = node("div", "section-heading");
  const label = node("h3");
  if (step) label.append(node("span", "section-number", step));
  label.append(document.createTextNode(title));
  heading.append(label);
  return heading;
}

function metadata(entries) {
  const list = node("dl", "metadata");
  for (const [label, value] of entries) {
    list.append(node("dt", "", label));
    const detail = node("dd");
    detail.append(value instanceof Node ? value : document.createTextNode(displayValue(value)));
    list.append(detail);
  }
  return list;
}

function table(headers, rows, label) {
  const wrapper = node("div", "table-scroll");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", label);
  const grid = node("table", "data-table");
  const head = node("thead");
  const header = node("tr");
  for (const text of headers) {
    const cell = node("th", "", text);
    cell.scope = "col";
    header.append(cell);
  }
  head.append(header);
  const body = node("tbody");
  for (const values of rows) {
    const row = node("tr");
    for (const value of values) {
      const cell = node("td");
      cell.append(value instanceof Node ? value : document.createTextNode(displayValue(value)));
      row.append(cell);
    }
    body.append(row);
  }
  grid.append(head, body);
  wrapper.append(grid);
  return wrapper;
}

function errorText(payload) {
  const detail = record(payload).detail ?? payload;
  if (Array.isArray(detail)) return detail.map(item => {
    const entry = record(item);
    return `${sequence(entry.loc).join(" → ")}: ${entry.msg || displayValue(item)}`;
  }).join("; ");
  if (typeof detail === "string") return detail;
  return JSON.stringify(detail);
}

async function request(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { Accept: "application/json", ...options.headers } });
  const text = await response.text();
  let body = text;
  if (text && (response.headers.get("content-type") || "").includes("json")) {
    try { body = JSON.parse(text); }
    catch { throw new Error("Сервер вернул повреждённый JSON. Действие не подтверждено."); }
  }
  if (!response.ok) throw new Error(errorText(body) || `Ошибка сервера: ${response.status}`);
  return body;
}

async function post(url, body) {
  return request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

async function runAction(control, text, action, destination) {
  const originalText = control.textContent;
  const originalDisabled = control.disabled;
  control.disabled = true;
  control.textContent = text;
  control.setAttribute("aria-busy", "true");
  try { await action(); }
  catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (destination) destination.replaceChildren(notice(message, "danger"));
    else announce(message, "danger");
  } finally {
    control.textContent = originalText;
    control.disabled = originalDisabled;
    control.removeAttribute("aria-busy");
  }
}

function sourceNames() {
  const names = new Set();
  for (const source of snapshot.sources) {
    const name = typeof source === "string" ? source : source.name ?? source.source;
    if (name) names.add(String(name));
  }
  for (const profile of snapshot.profiles) if (profile.source) names.add(String(profile.source));
  return [...names].sort((a, b) => a.localeCompare(b, "ru"));
}

function renderSources() {
  const names = sourceNames();
  const datalist = document.getElementById("source-names");
  datalist.replaceChildren(...names.map(name => {
    const option = node("option");
    option.value = name;
    return option;
  }));
  for (const id of ["catalog-source", "shipment-source"]) {
    const control = document.getElementById(id);
    const previous = control.value;
    control.replaceChildren(...[["", "Все источники"], ...names.map(name => [name, name])].map(([value, label]) => {
      const option = node("option", "", label);
      option.value = value;
      return option;
    }));
    if (names.includes(previous)) control.value = previous;
  }
}

async function refreshState() {
  if (stateBusy) return;
  stateBusy = true;
  const connection = document.getElementById("connection-status");
  connection.textContent = "Обновление…";
  try {
    const data = record(await request("/api/state"));
    if (!Array.isArray(data.files) || !Array.isArray(data.profiles) || !Array.isArray(data.shipments)) throw new Error("Ответ сервера не содержит списки файлов, профилей и поставок.");
    snapshot = { ...data, files: data.files, profiles: data.profiles, shipments: data.shipments, sources: sequence(data.sources), settings: record(data.settings), capabilities: record(data.capabilities) };
    connection.textContent = "Сервер доступен";
    connection.dataset.tone = "success";
    document.getElementById("state-updated").textContent = `Обновлено ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
    renderSources();
    renderFiles();
    renderShipmentList();
    renderProfileList();
    renderSystemState();
    const count = snapshot.files.filter(file => ["review", "needs_review"].includes(file.status)).length;
    const badgeElement = document.getElementById("review-count");
    badgeElement.textContent = numberText(count);
    badgeElement.hidden = !count;
  } catch (error) {
    connection.textContent = "Нет связи с сервером";
    connection.dataset.tone = "danger";
    announce(`Не удалось обновить состояние. ${error instanceof Error ? error.message : String(error)}`, "danger");
    if (!snapshot.files.length) document.getElementById("file-list").replaceChildren(node("p", "empty", "Список не получен. Проверьте сервис и нажмите «Обновить»."));
  } finally { stateBusy = false; }
}

function renderFiles() {
  const search = document.getElementById("file-search").value.trim().toLocaleLowerCase("ru");
  const filter = document.getElementById("file-status");
  const previousStatus = filter.value;
  const statuses = [...new Set(snapshot.files.map(file => file.status).filter(Boolean))];
  filter.replaceChildren(...[["", "Все статусы"], ...statuses.map(status => [status, statusLabels[status] || status])].map(([value, label]) => {
    const option = node("option", "", label);
    option.value = value;
    return option;
  }));
  if (statuses.includes(previousStatus)) filter.value = previousStatus;
  const files = snapshot.files.filter(file => (!search || `${file.original_name || file.filename || ""} ${file.source || ""}`.toLocaleLowerCase("ru").includes(search)) && (!filter.value || file.status === filter.value));
  document.getElementById("files-count").textContent = `${numberText(files.length)} / ${numberText(snapshot.files.length)}`;
  const list = document.getElementById("file-list");
  list.replaceChildren();
  if (!files.length) {
    list.append(node("p", "empty", snapshot.files.length ? "Нет файлов по этому фильтру. Измените название или статус." : "Загрузите первый прайс-лист. Неизвестный формат можно настроить вручную."));
    return;
  }
  for (const file of files) {
    const item = node("button", "file-item");
    item.type = "button";
    item.setAttribute("aria-pressed", String(String(file.id) === String(selectedFileId)));
    item.append(node("span", "file-item-name", file.original_name || file.filename || `Файл ${file.id}`));
    item.append(node("span", "file-item-meta", [file.source, bytesText(file.size), dateText(file.uploaded_at)].filter(Boolean).join(" · ")));
    item.append(badge(file.status));
    if (file.reason) item.append(node("span", "file-item-reason", file.reason));
    item.addEventListener("click", () => openFile(file.id));
    list.append(item);
  }
}

async function uploadFiles(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const control = document.getElementById("upload-button");
  const results = document.getElementById("upload-results");
  await runAction(control, "Загрузка и проверка…", async () => {
    loading(results, "Передаём оригиналы. Сервер проверяет формат и совпадение с утверждёнными профилями…");
    const data = record(await request("/api/upload", { method: "POST", body: new FormData(form) }));
    results.replaceChildren();
    const entries = sequence(data.results);
    if (!entries.length) throw new Error("Сервер не вернул результаты загрузки. Обновите список перед повторной отправкой.");
    const rows = entries.map(result => {
      const actions = node("div", "field-row");
      if (result.file_id !== undefined) actions.append(button("Открыть", "button-quiet button-small", () => openFile(result.file_id)));
      if (result.shipment_id !== undefined && result.shipment_id !== null) actions.append(button("Поставка", "button-quiet button-small", () => navigateShipment(result.shipment_id)));
      return [result.original_name || result.filename || `Файл ${result.file_id ?? "—"}`, badge(result.status), result.reason || "—", actions];
    });
    results.append(table(["Файл", "Результат сервера", "Причина", "Действия"], rows, "Результаты загрузки"));
    document.getElementById("upload-files").value = "";
    document.getElementById("selected-files-label").textContent = "Оригиналы не изменяются.";
    await refreshState();
    const review = entries.find(result => result.file_id !== undefined && ["review", "needs_review"].includes(result.status));
    if (review && !draftChanged) await openFile(review.file_id);
  }, results);
  results.removeAttribute("aria-busy");
}

function normalizedProfile(value) {
  const outer = record(value);
  const body = record(outer.profile || outer.body || outer);
  const copy = structuredClone(body);
  if (outer.id !== undefined && outer.id !== null) copy.id = outer.id;
  copy.name = copy.name || "";
  copy.source = copy.source || "";
  copy.ingest_mode = copy.ingest_mode || "";
  copy.policies = { ...Object.fromEntries(policyFields.map(policy => [policy.key, policy.value])), merged_fill: false, quarantine_threshold: 0.15, ...record(copy.policies) };
  copy.tables = sequence(copy.tables).map(tableSpec => ({ ...tableSpec, columns: sequence(tableSpec.columns).map(mapping => ({ ...mapping })) }));
  copy.delta = { key_fields: [], operation_field: "", ...record(copy.delta) };
  for (const key of ["revision", "created_at", "fingerprint", "profile_id", "body", "profile"]) delete copy[key];
  return copy;
}

async function openFile(id, force = false) {
  if (wizardBusy) { announce("Дождитесь результата проверки или сохранения перед сменой файла.", "warning"); return; }
  if (draftChanged && !force && String(id) !== String(selectedFileId) && !window.confirm("В форме есть несохранённые изменения. Перейти к другому файлу и оставить их?")) return;
  const token = ++fileRequest;
  selectedFileId = id;
  selectedShipmentId = null;
  const workspace = document.getElementById("file-workspace");
  loading(workspace, "Читаем структуру и оригинальные значения…");
  renderFiles();
  try {
    const response = record(await request(`/api/files/${encodeURIComponent(id)}`));
    if (token !== fileRequest) return;
    fileDetail = response;
    draftChanged = false;
    lastPreview = null;
    previewSignature = null;
    evidenceInput = null;
    const file = record(response.file);
    draft = response.profile ? normalizedProfile(response.profile) : normalizedProfile({ name: `${file.original_name || file.filename || "Новый"} · формат`, source: file.source || "", ingest_mode: "", tables: [] });
    renderWorkspace();
  } catch (error) {
    if (token === fileRequest) {
      workspace.replaceChildren(notice(`Не удалось открыть файл. ${error instanceof Error ? error.message : String(error)}`, "danger"));
      const download = node("a", "button button-secondary", "Скачать оригинал");
      download.href = `/api/files/${encodeURIComponent(id)}/raw`;
      workspace.append(download, button("Повторить", "button button-quiet", () => openFile(id, true)));
    }
  } finally { if (token === fileRequest) workspace.removeAttribute("aria-busy"); }
}

function currentSheets() {
  return sequence(record(fileDetail?.inspection).sheets);
}

function markDraftChanged() {
  draftChanged = true;
  previewSignature = null;
  const result = document.getElementById("preview-stale");
  if (result && lastPreview) result.hidden = false;
  updateApproval();
  const json = document.getElementById("draft-json");
  if (json) json.textContent = JSON.stringify(draft, null, 2);
}

function updateApproval() {
  const control = document.getElementById("approve-profile");
  if (!control) return;
  const fields = document.getElementById("wizard-fields");
  if (fields) fields.disabled = wizardBusy;
  control.disabled = wizardBusy || !draft || !previewSignature || lastPreview?.valid !== true || JSON.stringify(draft) !== previewSignature;
  const hint = document.getElementById("approval-hint");
  if (hint) hint.textContent = control.disabled ? "Сначала выполните успешный предпросмотр. Любое изменение настроек требует повторной проверки." : "Предпросмотр подтверждён сервером. Сохранение повторно проверит настройки и обработает весь файл до активации.";
}

function renderWorkspace() {
  const workspace = document.getElementById("file-workspace");
  workspace.replaceChildren();
  const file = record(fileDetail.file);
  const inspection = record(fileDetail.inspection);
  const heading = node("div", "section-heading");
  heading.append(node("h2", "workspace-title", file.original_name || file.filename || `Файл ${selectedFileId}`));
  const download = node("a", "button button-secondary button-small", "Скачать оригинал");
  download.href = `/api/files/${encodeURIComponent(selectedFileId)}/raw`;
  heading.append(download);
  const summary = node("div", "workspace-summary");
  summary.append(badge(file.status), node("span", "small muted", `${displayValue(inspection.format)} · ${bytesText(file.size)}`));
  workspace.append(heading, summary);
  if (file.reason) workspace.append(notice(file.reason, ["error", "rejected"].includes(file.status) ? "danger" : "warning"));
  if (fileDetail.inspection_error || inspection.error) workspace.append(notice(fileDetail.inspection_error || inspection.error, "danger"));
  if (sequence(fileDetail.quarantine).length) {
    const issues = node("details", "disclosure");
    issues.append(node("summary", "", `Ошибки последней обработки файла (${fileDetail.quarantine.length})`), evidenceTable(fileDetail.quarantine, "quarantine"));
    workspace.append(issues);
  }
  for (const warning of sequence(inspection.warnings)) workspace.append(notice(displayValue(warning), "warning"));
  if (!currentSheets().length) {
    workspace.append(notice("Сервер не предоставил листы и ячейки этого файла. Настройка и подтверждение недоступны: сначала требуется поддерживаемый, читаемый исходник.", "warning"));
    return;
  }
  if (!fileDetail.profile) workspace.append(notice("Сервер не предоставил подходящий профиль. Кандидаты ниже — только предложения. Для новой обработки настройте форму или выберите сохранённую ревизию.", "warning"));
  else workspace.append(notice("Сервер вернул подходящий профиль. Его можно использовать как основу новой ревизии; существующая ревизия не изменится."));
  renderRawSection(workspace);
  const form = node("form");
  form.id = "profile-form";
  form.addEventListener("submit", event => event.preventDefault());
  const fields = node("fieldset", "wizard-fields");
  fields.id = "wizard-fields";
  fields.append(node("legend", "sr-only", "Настройки профиля и таблиц"));
  const identity = node("section", "workspace-section");
  identity.append(sectionHeading("Профиль и способ загрузки", "02"));
  const metadataGrid = node("div", "field-grid");
  const name = input("text", draft.name, { required: "", autocomplete: "off" });
  name.addEventListener("input", () => { draft.name = name.value; markDraftChanged(); });
  const source = input("text", draft.source, { required: "", list: "source-names", autocomplete: "off" });
  source.addEventListener("input", () => { draft.source = source.value; markDraftChanged(); });
  const mode = select(modeOptions, draft.ingest_mode);
  mode.required = true;
  const modeHint = node("p", "section-note", modeDescriptions[draft.ingest_mode] || "Режим из профиля проверит сервер.");
  modeHint.id = "mode-hint";
  mode.setAttribute("aria-describedby", "mode-hint");
  mode.addEventListener("change", () => {
    draft.ingest_mode = mode.value;
    modeHint.textContent = modeDescriptions[mode.value] || "Режим из профиля проверит сервер.";
    document.getElementById("delta-settings").hidden = mode.value !== "delta";
    markDraftChanged();
  });
  metadataGrid.append(field("Название профиля", name), field("Источник", source), field("Режим загрузки — обязательно", mode, null, "wide"));
  identity.append(metadataGrid, modeHint, renderDeltaSettings(), renderPolicySettings());
  if (snapshot.profiles.length) identity.append(renderProfileReuse());
  fields.append(identity);
  const tablesSection = node("section", "workspace-section");
  const tablesHeading = sectionHeading("Таблицы и сопоставления", "03");
  tablesHeading.append(button("Добавить таблицу", "button-secondary button-small", () => addTable()));
  tablesSection.append(tablesHeading, node("p", "section-note", "Одна карточка — одна область. Для нескольких островов или листов добавьте отдельные таблицы. Сопоставьте полезные поля, прочие сохраните как дополнительные или явно исключите с причиной."));
  const tablesContainer = node("div");
  tablesContainer.id = "table-editors";
  tablesSection.append(tablesContainer);
  fields.append(tablesSection);
  form.append(fields);
  const actions = node("div", "wizard-actions");
  const preview = button("Проверить первые 100 строк", "button-secondary", runPreview);
  preview.id = "preview-profile";
  const approve = button("Сохранить профиль и активировать", "button-primary", approveProfile);
  approve.id = "approve-profile";
  approve.disabled = true;
  const hint = node("p", "field-hint");
  hint.id = "approval-hint";
  actions.append(preview, approve, hint);
  form.append(actions);
  const feedback = node("div");
  feedback.id = "wizard-feedback";
  feedback.setAttribute("aria-live", "polite");
  form.append(feedback);
  const previewResult = node("section", "preview-section");
  previewResult.id = "preview-results";
  previewResult.setAttribute("aria-label", "Результат проверки первых ста строк");
  form.append(previewResult);
  const advanced = node("details", "disclosure");
  advanced.append(node("summary", "", "Техническое представление профиля — только чтение"));
  const advancedBody = node("div", "disclosure-body");
  const json = node("pre", "code-block", JSON.stringify(draft, null, 2));
  json.id = "draft-json";
  advancedBody.append(node("p", "section-note", "Все настройки редактируются в форме выше. Этот снимок помогает проверить точный запрос к серверу."), json);
  advanced.append(advancedBody);
  form.append(advanced);
  workspace.append(form);
  renderTableEditors();
  updateApproval();
}

function renderRawSection(workspace) {
  const section = node("section", "workspace-section");
  section.append(sectionHeading("Оригинальные ячейки", "01"));
  const sheets = currentSheets();
  const picker = select(sheets.map(sheet => [sheet.name, `${sheet.name} · ${numberText(sheet.rows)} строк × ${numberText(sheet.cols)} столбцов`]), sheets[0]?.name);
  const rawBody = node("div");
  const candidates = node("div", "candidate-list");
  section.append(field("Лист исходного файла", picker), node("p", "field-hint", "Показан фрагмент, предоставленный сервером. Координаты, формулы и скрытые ячейки сохранены. Выберите поле «Цитата», затем ячейку для вставки доказательства."), rawBody, candidates);
  const render = () => {
    const sheet = sheets.find(item => item.name === picker.value);
    renderRawGrid(rawBody, sheet);
    candidates.replaceChildren(node("h4", "", "Предложения областей"));
    const entries = sequence(sheet?.candidates);
    if (!entries.length) candidates.append(node("p", "section-note", "Кандидаты не найдены. Добавьте таблицу вручную и укажите её границы; неизвестная структура не считается ошибочно распознанной."));
    for (const [index, candidate] of entries.entries()) {
      const row = node("div", "candidate-row");
      const text = node("div");
      text.append(node("p", "", `Область ${index + 1} · ${columnLabel(candidate.start_col)}${candidate.header_start ?? "?"}:${columnLabel(candidate.end_col)}${candidate.header_end ?? "?"}`));
      text.append(node("p", "muted small", `Данные с ${displayValue(candidate.data_start)} · полей: ${numberText(sequence(candidate.columns).length)} · ${orientationLabel(candidate.orientation)}`));
      if (candidate.reason) text.append(node("p", "muted small", candidate.reason));
      row.append(text, button("Добавить область", "button-secondary button-small", () => addTable({ ...candidate, sheet: candidate.sheet || sheet.name })));
      candidates.append(row);
    }
  };
  picker.addEventListener("change", render);
  render();
  workspace.append(section);
}

function renderRawGrid(container, sheet) {
  container.replaceChildren();
  const rows = sequence(sheet?.preview);
  if (!rows.length) { container.append(node("p", "empty", "Сервер не передал ячейки этого листа. Скачайте оригинал для просмотра границ и цитат.")); return; }
  const colSet = new Set();
  for (const row of rows) for (const cell of sequence(row.cells)) colSet.add(Number(cell.col));
  const columns = [...colSet].filter(Number.isFinite).sort((a, b) => a - b);
  const wrapper = node("div", "table-scroll raw-scroll");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", `Ячейки листа ${sheet.name}; прокручиваемая таблица`);
  const grid = node("table", "data-table raw-table");
  const head = node("thead");
  const heading = node("tr");
  const corner = node("th", "", "Строка");
  corner.scope = "col";
  heading.append(corner);
  for (const col of columns) {
    const label = node("th", "", `${columnLabel(col)} · ${col}`);
    label.scope = "col";
    heading.append(label);
  }
  head.append(heading);
  const body = node("tbody");
  for (const row of rows) {
    const line = node("tr");
    const rowNumber = node("th", "", row.row);
    rowNumber.scope = "row";
    line.append(rowNumber);
    const byColumn = new Map(sequence(row.cells).map(cell => [Number(cell.col), cell]));
    for (const col of columns) {
      const cell = byColumn.get(col);
      const td = node("td");
      if (cell) {
        const coordinate = cell.coordinate || `${columnLabel(col)}${row.row}`;
        const pick = button("", "raw-cell", () => {
          if (!evidenceInput || !document.contains(evidenceInput)) { announce(`Ячейка ${coordinate}: ${displayValue(cell.value)}. Для переноса выберите поле «Цитата» в сопоставлении.`, "info"); return; }
          evidenceInput.value = `${coordinate}=${JSON.stringify(String(cell.value ?? ""))}`;
          evidenceInput.dispatchEvent(new Event("input", { bubbles: true }));
          evidenceInput.focus({ preventScroll: true });
          announce(`Доказательство из ${coordinate} перенесено в выбранное сопоставление. Повторите предпросмотр после изменений.`, "success");
        });
        pick.className = "raw-cell";
        if (cell.hidden || row.hidden) pick.classList.add("raw-cell-hidden");
        pick.setAttribute("aria-label", `${coordinate}: ${displayValue(cell.value)}${cell.hidden || row.hidden ? "; скрытая ячейка" : ""}. Использовать как цитату`);
        pick.append(node("code", "", coordinate), node("span", "raw-cell-value", displayValue(cell.value)));
        if (cell.formula) pick.append(node("span", "raw-cell-formula", `Формула: ${displayValue(cell.formula)}`));
        if (cell.hidden || row.hidden) pick.append(node("span", "field-hint", "Скрыто в оригинале"));
        td.append(pick);
      }
      line.append(td);
    }
    body.append(line);
  }
  grid.append(head, body);
  wrapper.append(grid);
  container.append(node("p", "field-hint", `Получено строк: ${rows.length}; размер листа: ${numberText(sheet.rows)} × ${numberText(sheet.cols)}. Значение «—» обозначает пустую ячейку.`), wrapper);
}

function renderDeltaSettings() {
  const body = node("div", "field-grid");
  body.id = "delta-settings";
  body.hidden = draft.ingest_mode !== "delta";
  const keys = input("text", sequence(draft.delta.key_fields).join(", "), { placeholder: "article, brand, pack" });
  keys.addEventListener("input", () => { draft.delta.key_fields = keys.value.split(",").map(value => value.trim()).filter(Boolean); markDraftChanged(); });
  const operation = input("text", draft.delta.operation_field, { placeholder: "extra.operation" });
  operation.addEventListener("input", () => { draft.delta.operation_field = operation.value.trim(); markDraftChanged(); });
  body.append(field("Ключи изменений", keys, "Технические имена полей через запятую. Например: article, brand, pack."), field("Поле операции", operation, "Сопоставьте столбец операций с дополнительным полем. Значения операций проверит сервер."));
  return body;
}

function renderPolicySettings() {
  const details = node("details", "disclosure");
  details.append(node("summary", "", "Политики обработки и допустимый карантин"));
  const body = node("div", "disclosure-body");
  body.append(node("p", "section-note", "Это действующие настройки профиля, а не демонстрационные переключатели. Поддержка стратегий P1–P11 приведена ниже и в разделе «Система»."));
  const grid = node("div", "policy-grid");
  for (const policy of policyFields) {
    const control = select(policy.options, draft.policies[policy.key]);
    control.addEventListener("change", () => { draft.policies[policy.key] = control.value; markDraftChanged(); });
    grid.append(field(policy.label, control));
  }
  const threshold = input("number", draft.policies.quarantine_threshold, { min: "0", max: "1", step: "0.01", required: "" });
  threshold.addEventListener("input", () => { draft.policies.quarantine_threshold = threshold.value === "" ? null : Number(threshold.value); markDraftChanged(); });
  grid.append(field("Порог карантина всего файла", threshold, "Доля от 0 до 1: 0,15 = 15%. При достижении порога полный импорт не активируется. Первый предпросмотр должен быть без ошибок."));
  const merged = input("checkbox", "");
  merged.checked = draft.policies.merged_fill === true;
  merged.addEventListener("change", () => { draft.policies.merged_fill = merged.checked; markDraftChanged(); });
  const mergedLabel = node("label", "check-field wide");
  mergedLabel.append(merged, node("span", "", "Распространять значения объединённых ячеек внутри таблицы. Это не заполнение произвольных пустых строк."));
  grid.append(mergedLabel);
  body.append(grid);
  const support = node("div", "policy-grid");
  support.append(...policySupportNodes());
  body.append(support);
  details.append(body);
  return details;
}

function renderProfileReuse() {
  const details = node("details", "disclosure");
  details.append(node("summary", "", "Взять существующую ревизию за основу или повторить обработку"));
  const body = node("div", "disclosure-body");
  const revisions = new Map(snapshot.profiles.map((profile, index) => [String(index), profile]));
  const picker = select([["", "Выберите ревизию"], ...[...revisions].map(([key, profile]) => [key, `${profile.name || "Профиль"} · ${profile.source || "—"} · рев. ${profile.revision ?? profile.id}`])], "");
  const actions = node("div", "field-row");
  const use = button("Загрузить в форму", "button-secondary", async () => {
    if (!picker.value) return;
    if (draftChanged && !window.confirm("Заменить несохранённые настройки выбранной ревизией?")) return;
    await runAction(use, "Загрузка…", async () => {
      const saved = revisions.get(picker.value);
      const profile = await request(`/api/profiles/${encodeURIComponent(saved.id)}${saved.revision !== undefined ? `?revision=${encodeURIComponent(saved.revision)}` : ""}`);
      draft = normalizedProfile(profile);
      lastPreview = null;
      previewSignature = null;
      draftChanged = true;
      renderWorkspace();
      announce("Ревизия скопирована в форму. Исходный профиль не изменён. Настройте отличия и проверьте файл.");
    });
  });
  const reprocess = button("Обработать последней ревизией", "button-secondary", async () => {
    if (wizardBusy || !picker.value || !window.confirm("Повторно обработать файл последней сохранённой ревизией выбранного профиля? Будет создана новая поставка; настройки формы не используются.")) return;
    await runAction(reprocess, "Обработка…", async () => {
      wizardBusy = true;
      updateApproval();
      try {
        const result = record(await post(`/api/files/${encodeURIComponent(selectedFileId)}/reprocess`, { profile_id: revisions.get(picker.value).id }));
        announce(`Повторная обработка: ${statusLabels[result.status] || result.status || "сервер вернул результат"}. Поставка: ${displayValue(result.shipment_id)}.`, result.status === "accepted" ? "success" : "warning");
        await refreshState();
        if (result.shipment_id !== undefined && result.shipment_id !== null) navigateShipment(result.shipment_id);
      } finally { wizardBusy = false; updateApproval(); }
    });
  });
  use.disabled = true;
  reprocess.disabled = true;
  picker.addEventListener("change", () => { use.disabled = !picker.value; reprocess.disabled = !picker.value; });
  actions.append(field("Подтверждённый профиль", picker), use, reprocess);
  body.append(node("p", "section-note", "В форму копируется именно выбранная ревизия. Повторная обработка использует последнюю ревизию профиля по правилам сервера, а не несохранённые правки формы. Для повторения старых настроек скопируйте их в форму и проверьте заново."), actions);
  details.append(body);
  return details;
}

function orientationLabel(value) {
  if (value === "vertical") return "Поля по строкам";
  if (value === "crosstab") return "Перекрёстная таблица";
  return value === "rows" ? "Позиции по строкам" : displayValue(value);
}

function addTable(candidate) {
  if (wizardBusy) return;
  const sheet = currentSheets()[0];
  const next = candidate ? structuredClone(candidate) : { sheet: sheet?.name || "", header_start: 1, header_end: 1, data_start: 2, data_end: null, start_col: 1, end_col: Math.max(1, Number(sheet?.cols) || 1), orientation: "rows", columns: [], currency: "" };
  next.columns = sequence(next.columns).map(mapping => ({ ...mapping, quote: quoteText(mapping.quote) }));
  next.orientation = next.orientation || "rows";
  next.currency = next.currency || "";
  draft.tables.push(next);
  markDraftChanged();
  renderTableEditors();
  const editors = document.getElementById("table-editors");
  editors.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function quoteText(value) {
  if (typeof value === "string") return value;
  const evidence = record(value);
  if (evidence.coordinate) return `${evidence.coordinate}=${JSON.stringify(String(evidence.literal ?? evidence.value ?? ""))}`;
  return value ? JSON.stringify(value) : "";
}

function suggestedQuote(spec, mapping) {
  const sheet = currentSheets().find(item => item.name === spec.sheet);
  for (const row of sequence(sheet?.preview)) {
    if (spec.orientation === "vertical" ? Number(row.row) !== Number(mapping.row) : Number(row.row) < Number(spec.header_start) || Number(row.row) > Number(spec.header_end)) continue;
    for (const cell of sequence(row.cells)) {
      const matches = spec.orientation === "vertical" ? Number(cell.col) < Number(spec.start_col) : Number(cell.col) === Number(mapping.col);
      if (matches && cell.value !== null && cell.value !== undefined && cell.value !== "") return `${cell.coordinate || `${columnLabel(cell.col)}${row.row}`}=${JSON.stringify(String(cell.value))}`;
    }
  }
  return "";
}

function renderTableEditors() {
  const container = document.getElementById("table-editors");
  if (!container) return;
  container.replaceChildren();
  evidenceInput = null;
  if (!draft.tables.length) container.append(notice("Таблиц пока нет. Добавьте предложенную область над формой или создайте таблицу вручную.", "warning"));
  draft.tables.forEach((spec, index) => container.append(renderTableCard(spec, index)));
}

function renderTableCard(spec, index) {
  const card = node("details", "table-card");
  card.open = true;
  const summary = node("summary");
  const title = node("span", "table-card-title", `Таблица ${index + 1} · ${spec.sheet || "Лист не выбран"}`);
  summary.append(title, node("span", "small muted", orientationLabel(spec.orientation)));
  card.append(summary);
  const body = node("div", "table-card-body");
  const grid = node("div", "field-grid");
  const sheet = select(currentSheets().map(item => [item.name, item.name]), spec.sheet);
  sheet.addEventListener("change", () => { spec.sheet = sheet.value; title.textContent = `Таблица ${index + 1} · ${spec.sheet}`; markDraftChanged(); });
  const orientation = select([["rows", "Позиции по строкам"], ["vertical", "Поля по строкам (вертикально)"], ["crosstab", "Перекрёстная таблица (матрица)"]], spec.orientation);
  orientation.addEventListener("change", () => { spec.orientation = orientation.value; markDraftChanged(); renderTableEditors(); });
  grid.append(field("Лист", sheet), field("Ориентация", orientation));
  const vertical = spec.orientation === "vertical";
  const bounds = [
    ["header_start", "Первая строка заголовка", 1], ["header_end", "Последняя строка заголовка", 1],
    ["data_start", "Первая строка данных", 1], ["data_end", "Последняя строка данных", 1],
    ["start_col", vertical ? "Первый столбец позиций (номер)" : "Первый столбец области (номер)", 1], ["end_col", vertical ? "Последний столбец позиций (номер)" : "Последний столбец области (номер)", 1]
  ];
  for (const [key, label, minimum] of bounds) {
    const control = input("number", spec[key], { min: minimum, step: 1, ...(key === "data_end" ? { placeholder: "До конца" } : { required: "" }) });
    if (vertical && (key === "data_start" || key === "data_end")) control.disabled = true;
    control.addEventListener("input", () => { spec[key] = control.value === "" ? null : Number(control.value); markDraftChanged(); });
    grid.append(field(label, control, vertical && key.startsWith("data_") ? "Не используется: позиции ограничены столбцами, поля — номерами строк ниже." : key === "data_end" ? "Пусто — до конца области по правилам сервера." : key.endsWith("col") ? "Нумерация с 1: A = 1, B = 2, …" : null));
  }
  const currency = input("text", spec.currency, { list: "currency-values", placeholder: "RUB, USD…" });
  currency.addEventListener("input", () => { spec.currency = currency.value.trim(); markDraftChanged(); });
  grid.append(field("Валюта таблицы", currency, "Не пересчитывается. Значение поля или цены имеет приоритет."));
  body.append(grid);
  body.append(node("p", "orientation-note", vertical ? "Вертикальная ориентация: один столбец позиций — один товар. Укажите первый и последний столбцы позиций, а ниже — строку каждого поля и цитату подписи. Границы строк данных в этом режиме не применяются." : spec.orientation === "crosstab" ? "Матрица: сопоставьте ключевые поля и каждый ценовой столбец. Для цены задайте вид, валюту и измерение (например, размер) из заголовка; оно сохранится в дополнительных данных." : "Обычная таблица: каждое сопоставление выбирает столбец. Цитата должна содержать координату и буквальное значение из оригинального заголовка."));
  const mappingContainer = node("div");
  const renderMappings = () => {
    mappingContainer.replaceChildren();
    if (!spec.columns.length) { mappingContainer.append(node("p", "empty", "Добавьте сопоставления для артикула, названия, цены и остальных полей этой области.")); return; }
    const wrapper = node("div", "table-scroll mapping-table");
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", `Сопоставления таблицы ${index + 1}`);
    const grid = node("table", "data-table");
    const head = node("thead");
    const headings = node("tr");
    for (const label of [vertical ? "Строка поля" : "Столбец", "Назначение", "Цитата из оригинала", "Параметры цены", "Причина исключения", "Действия"]) {
      const th = node("th", "", label);
      th.scope = "col";
      headings.append(th);
    }
    head.append(headings);
    const tbody = node("tbody");
    spec.columns.forEach((mapping, mappingIndex) => tbody.append(renderMappingRow(spec, mapping, index, mappingIndex, renderMappings)));
    grid.append(head, tbody);
    wrapper.append(grid);
    mappingContainer.append(wrapper);
  };
  renderMappings();
  body.append(mappingContainer);
  const actions = node("div", "table-card-actions");
  actions.append(button("Добавить сопоставление", "button-secondary button-small", () => {
    const locationKey = vertical ? "row" : "col";
    const occupied = new Set(spec.columns.map(mapping => Number(mapping[locationKey])));
    let position = vertical ? Number(spec.header_start) || 1 : Number(spec.start_col) || 1;
    while (occupied.has(position)) position += 1;
    const mapping = { col: vertical ? Number(spec.start_col) || 1 : position, target: "extra.new_field", quote: "", price_kind: "unknown", currency: "", reason: "" };
    if (vertical) mapping.row = position;
    mapping.quote = suggestedQuote(spec, mapping);
    spec.columns.push(mapping);
    markDraftChanged();
    renderMappings();
  }), button("Удалить таблицу", "button-danger button-small", () => {
    if (!window.confirm(`Удалить таблицу ${index + 1} из формы? Оригинал не изменится.`)) return;
    draft.tables.splice(index, 1);
    markDraftChanged();
    renderTableEditors();
  }));
  body.append(actions);
  card.append(body);
  return card;
}

function renderMappingRow(spec, mapping, tableIndex, mappingIndex, rerender) {
  const row = node("tr");
  const prefix = `Таблица ${tableIndex + 1}, поле ${mappingIndex + 1}: `;
  const vertical = spec.orientation === "vertical";
  const locationKey = vertical ? "row" : "col";
  const position = input("number", mapping[locationKey], { min: 1, step: 1, required: "", "aria-label": `${prefix}${vertical ? "строка" : "столбец"}` });
  const positionHint = node("span", "field-hint", vertical ? "Номер строки" : columnLabel(mapping.col));
  position.addEventListener("input", () => {
    mapping[locationKey] = position.value === "" ? null : Number(position.value);
    positionHint.textContent = vertical ? "Номер строки" : columnLabel(mapping.col);
    markDraftChanged();
  });
  const positionCell = node("td", "mapping-location");
  positionCell.append(position, positionHint);
  const extraTarget = String(mapping.target || "").startsWith("extra.");
  const target = select([["", "Выберите поле"], ...targetOptions], extraTarget ? "extra" : mapping.target || "");
  target.required = true;
  target.setAttribute("aria-label", `${prefix}назначение`);
  const extra = input("text", extraTarget ? mapping.target.slice(6) : "", { placeholder: "Название дополнительного поля", "aria-label": `${prefix}имя дополнительного поля` });
  extra.className = "extra-field";
  extra.hidden = !extraTarget;
  extra.required = extraTarget;
  extra.addEventListener("input", () => { mapping.target = `extra.${extra.value.trim()}`; markDraftChanged(); });
  const targetCell = node("td", "mapping-target");
  targetCell.append(target, extra);
  const quote = node("textarea");
  quote.value = quoteText(mapping.quote);
  quote.rows = 2;
  quote.required = true;
  quote.placeholder = "A1=\"Заголовок\"";
  quote.setAttribute("aria-label", `${prefix}цитата из оригинала`);
  quote.addEventListener("focus", () => { evidenceInput = quote; });
  quote.addEventListener("input", () => { mapping.quote = quote.value; markDraftChanged(); });
  const quoteCell = node("td", "mapping-evidence");
  quoteCell.append(quote, button("Взять из заголовка", "button-quiet button-small", () => {
    const evidence = suggestedQuote(spec, mapping);
    if (!evidence) { announce("В переданном фрагменте нет непустой ячейки заголовка для этого поля. Укажите цитату из оригинала вручную.", "warning"); return; }
    quote.value = evidence;
    mapping.quote = evidence;
    markDraftChanged();
  }));
  const priceCell = node("td", "mapping-target");
  const priceFields = node("div", "field");
  const kind = input("text", mapping.price_kind || "", { list: "price-kinds", placeholder: "Вид цены, например wholesale", "aria-label": `${prefix}вид цены` });
  kind.addEventListener("input", () => { mapping.price_kind = kind.value.trim(); markDraftChanged(); });
  const currency = input("text", mapping.currency || "", { list: "currency-values", placeholder: "Валюта цены", "aria-label": `${prefix}валюта цены` });
  currency.addEventListener("input", () => { mapping.currency = currency.value.trim(); markDraftChanged(); });
  priceFields.append(kind, currency);
  if (spec.orientation === "crosstab") {
    const dimension = input("text", mapping.dimension || "", { placeholder: "Измерение: размер, период…", "aria-label": `${prefix}измерение матрицы` });
    dimension.addEventListener("input", () => { mapping.dimension = dimension.value; markDraftChanged(); });
    priceFields.append(dimension);
  }
  const priceHint = node("span", "field-hint", "Для ценового поля");
  priceCell.append(priceFields, priceHint);
  const reason = node("textarea");
  reason.value = mapping.reason || "";
  reason.rows = 2;
  reason.placeholder = "Почему поле исключается";
  reason.required = mapping.target === "drop";
  reason.setAttribute("aria-label", `${prefix}причина исключения`);
  reason.addEventListener("input", () => { mapping.reason = reason.value; markDraftChanged(); });
  const reasonCell = node("td", "mapping-evidence");
  reasonCell.append(reason);
  const updateTarget = () => {
    priceFields.hidden = target.value !== "price";
    priceHint.hidden = target.value === "price";
    reason.disabled = target.value !== "drop";
    reason.required = target.value === "drop";
    extra.hidden = target.value !== "extra";
    extra.required = target.value === "extra";
  };
  target.addEventListener("change", () => {
    mapping.target = target.value === "extra" ? `extra.${extra.value.trim()}` : target.value;
    updateTarget();
    markDraftChanged();
  });
  updateTarget();
  const actions = node("td", "mapping-action");
  actions.append(button("Убрать", "button-quiet button-small", () => {
    spec.columns.splice(mappingIndex, 1);
    if (evidenceInput === quote) evidenceInput = null;
    markDraftChanged();
    rerender();
  }));
  row.append(positionCell, targetCell, quoteCell, priceCell, reasonCell, actions);
  return row;
}

async function runPreview() {
  if (wizardBusy || !draft) return;
  const form = document.getElementById("profile-form");
  if (!form.reportValidity()) return;
  if (!draft.ingest_mode || !draft.tables.length) { announce("Выберите режим загрузки и добавьте хотя бы одну таблицу.", "warning"); return; }
  const control = document.getElementById("preview-profile");
  const resultContainer = document.getElementById("preview-results");
  const requestedProfile = structuredClone(draft);
  const signature = JSON.stringify(requestedProfile);
  previewSignature = null;
  lastPreview = null;
  wizardBusy = true;
  updateApproval();
  await runAction(control, "Проверяем первые 100 строк…", async () => {
    loading(resultContainer, "Сервер проверяет профиль и разбирает первые 100 исходных строк. Каталог и история не изменяются.");
    const result = record(await post(`/api/files/${encodeURIComponent(selectedFileId)}/preview`, requestedProfile));
    lastPreview = result;
    if (result.valid === true && JSON.stringify(draft) === signature) previewSignature = signature;
    renderPreview(resultContainer, result);
    document.getElementById("preview-stale").hidden = JSON.stringify(draft) === signature;
    resultContainer.scrollIntoView({ behavior: "smooth", block: "start" });
  }, resultContainer);
  resultContainer.removeAttribute("aria-busy");
  wizardBusy = false;
  updateApproval();
}

async function approveProfile() {
  if (wizardBusy || !previewSignature || lastPreview?.valid !== true || JSON.stringify(draft) !== previewSignature) return;
  const form = document.getElementById("profile-form");
  if (!form.reportValidity()) return;
  const control = document.getElementById("approve-profile");
  const feedback = document.getElementById("wizard-feedback");
  const requestedProfile = structuredClone(draft);
  const fileId = selectedFileId;
  wizardBusy = true;
  updateApproval();
  document.getElementById("preview-profile").disabled = true;
  await runAction(control, "Обрабатываем весь файл…", async () => {
    loading(feedback, "Проверяем весь файл до сохранения ревизии и смены текущего снимка. Не закрывайте страницу.");
    const result = record(await post(`/api/files/${encodeURIComponent(fileId)}/approve`, requestedProfile));
    previewSignature = null;
    draftChanged = JSON.stringify(draft) !== JSON.stringify(requestedProfile);
    const accepted = result.status === "accepted";
    if (accepted && result.profile_id !== undefined && result.profile_id !== null) {
      draft.id = result.profile_id;
      const json = document.getElementById("draft-json");
      if (json) json.textContent = JSON.stringify(draft, null, 2);
    }
    feedback.replaceChildren(notice(accepted ? "Сервер принял полную обработку. Результат сохранён; текущий снимок и его состав доступны в каталоге и истории." : `Сервер завершил обработку со статусом «${statusLabels[result.status] || result.status || "не передан"}». Не считайте поставку активной без подтверждения в истории.`, accepted ? "success" : "warning"));
    if (result.reason) feedback.append(notice(result.reason, "warning"));
    feedback.append(renderCounts(result.counts));
    const links = node("div", "field-row");
    if (result.shipment_id !== undefined && result.shipment_id !== null) links.append(button("Открыть поставку", "button-secondary", () => navigateShipment(result.shipment_id)));
    if (result.profile_id !== undefined && result.profile_id !== null) links.append(button("Посмотреть ревизию", "button-quiet", () => navigateProfile(result.profile_id, result.profile_revision ?? result.revision)));
    feedback.append(links);
    await refreshState();
  }, feedback);
  feedback.removeAttribute("aria-busy");
  wizardBusy = false;
  document.getElementById("preview-profile").disabled = false;
  updateApproval();
}

function countValue(counts, keys) {
  const values = record(counts);
  for (const key of keys) if (values[key] !== undefined && values[key] !== null) return values[key];
  return null;
}

function renderCounts(counts) {
  const container = node("div", "preview-counts");
  for (const [title, keys] of [["исходных строк", ["source_rows"]], ["принято строк", ["accepted_rows", "accepted"]], ["в карантине", ["quarantined_rows", "quarantined", "quarantine"]], ["исключено", ["dropped_rows", "dropped"]], ["позиций", ["items", "total_items"]]]) {
    const item = node("div", "count-item");
    item.append(node("strong", "", numberText(countValue(counts, keys))), node("span", "muted", title));
    container.append(item);
  }
  return container;
}

function renderPreview(container, result) {
  container.replaceChildren(sectionHeading("Результат предпросмотра", "04"));
  const stale = notice("Настройки изменились после запроса. Этот результат устарел; выполните новый предпросмотр.", "warning");
  stale.id = "preview-stale";
  stale.hidden = true;
  container.append(stale);
  if (result.valid === true) container.append(notice("Первые 100 исходных строк прошли проверку. Это ещё не полный импорт: сервер повторно проверит весь файл при подтверждении.", "success"));
  else container.append(notice(result.reason || "Сервер не подтвердил допустимость профиля. Исправьте ошибки или сопоставления и повторите проверку. Сохранение отключено.", "warning"));
  const summary = node("div", "workspace-summary");
  summary.append(badge(result.status));
  if (result.fingerprint) summary.append(node("span", "small muted", `Отпечаток: ${result.fingerprint}`));
  container.append(summary, renderCounts(result.counts));
  if (result.errors) container.append(detailsJson(result.errors, "Ошибки проверки профиля"));
  for (const warning of sequence(result.warnings)) container.append(notice(displayValue(warning), "warning"));
  container.append(renderResultTabs(result));
}

function itemTable(items, label) {
  if (!items.length) return node("p", "empty", "В этом результате нет канонических позиций. Проверьте границы данных, фильтры и карантин.");
  const rows = items.map(item => {
    const evidence = detailsJson(item, "Исходные данные и происхождение");
    return [item.article, item.name, item.brand, item.pack, item.qty, item.price, item.currency, item.price_kind, item.source, evidence];
  });
  return table(["Артикул", "Наименование", "Бренд", "Фасовка", "Количество", "Цена", "Валюта", "Вид цены", "Источник", "Доказательства"], rows, label);
}

function evidenceTable(entries, type) {
  if (!entries.length) return node("p", "empty", type === "quarantine" ? "Для показанной части результата карантинных записей нет." : "Для показанной части результата исключений нет.");
  return table(["Лист / таблица", "Строка / координата", "Причина", "Исходные значения и доказательства"], entries.map(entry => [entry.source_sheet ?? entry.sheet ?? entry.source_table ?? entry.table ?? record(entry.provenance).sheet, entry.coordinate ?? entry.source_row ?? entry.row ?? record(entry.provenance).row, entry.reason ?? entry.error ?? entry.code ?? entry.reasons, detailsJson(entry, "Показать исходную запись")]), type === "quarantine" ? "Карантинные записи" : "Исключённые данные");
}

function renderResultTabs(result) {
  const container = node("div");
  const actions = node("div", "result-tabs");
  actions.setAttribute("aria-label", "Представление результата");
  const content = node("div");
  const choices = [
    ["items", `Позиции (${sequence(result.items).length})`], ["quarantine", `Карантин (${sequence(result.quarantine).length})`], ["dropped", `Исключения (${sequence(result.dropped).length})`], ["raw", "Полный ответ сервера"]
  ];
  const controls = new Map();
  const activate = key => {
    for (const [name, control] of controls) control.setAttribute("aria-pressed", String(name === key));
    content.replaceChildren(key === "raw" ? node("pre", "code-block", JSON.stringify(result, null, 2)) : key === "items" ? itemTable(sequence(result.items), "Канонические позиции") : evidenceTable(sequence(result[key]), key));
  };
  for (const [key, label] of choices) {
    const control = button(label, "button-secondary button-small", () => activate(key));
    controls.set(key, control);
    actions.append(control);
  }
  container.append(actions, content);
  activate("items");
  return container;
}

function pagination(offset, total, count, onPage) {
  const container = node("div", "pagination");
  const knownTotal = typeof total === "number" && Number.isFinite(total);
  const start = count ? offset + 1 : 0;
  const end = count ? offset + count : 0;
  container.append(node("span", "", `${numberText(start)}–${numberText(end)}${knownTotal ? ` из ${numberText(total)}` : " · итог не передан сервером"}`));
  const controls = node("div", "pagination-controls");
  const previous = button("Назад", "button-secondary button-small", () => onPage(Math.max(0, offset - pageSize)));
  const next = button("Далее", "button-secondary button-small", () => onPage(offset + pageSize));
  previous.disabled = offset === 0;
  next.disabled = knownTotal ? offset + pageSize >= total : count < pageSize;
  controls.append(previous, next);
  container.append(controls);
  return container;
}

async function loadCatalog() {
  const token = ++catalogRequest;
  const container = document.getElementById("catalog-results");
  loading(container, "Читаем активные снимки…");
  const offset = catalogOffset;
  const params = new URLSearchParams({ offset: String(offset), limit: String(pageSize) });
  const source = document.getElementById("catalog-source").value;
  const query = document.getElementById("catalog-query").value.trim();
  if (source) params.set("source", source);
  if (query) params.set("q", query);
  try {
    const result = record(await request(`/api/catalog?${params}`));
    if (token !== catalogRequest) return;
    if (!Array.isArray(result.items)) throw new Error("Сервер не вернул список позиций каталога.");
    container.replaceChildren();
    if (!result.items.length) container.append(node("p", "empty", query || source ? "По этим условиям позиций не найдено. Измените запрос или источник." : "Активный каталог пока пуст. Настройте файл, выполните предпросмотр и подтвердите поставку во «Входящих»."));
    else container.append(itemTable(result.items, "Текущий каталог"));
    container.append(pagination(offset, result.total, result.items.length, next => { catalogOffset = next; loadCatalog(); }));
  } catch (error) {
    if (token === catalogRequest) container.replaceChildren(notice(`Каталог не получен. ${error instanceof Error ? error.message : String(error)}`, "danger"), button("Повторить запрос", "button-secondary", loadCatalog));
  } finally { if (token === catalogRequest) container.removeAttribute("aria-busy"); }
}

function shipmentIsCurrent(shipment) {
  if (shipment.is_current === true) return true;
  const source = snapshot.sources.find(item => typeof item === "object" && item !== null && (item.name ?? item.source) === shipment.source);
  return source?.current_shipment_id !== undefined && source.current_shipment_id !== null && String(source.current_shipment_id) === String(shipment.id);
}

function renderShipmentList() {
  const container = document.getElementById("shipment-list");
  const selectedSource = document.getElementById("shipment-source").value;
  const shipments = snapshot.shipments.filter(shipment => !selectedSource || shipment.source === selectedSource);
  if (!shipments.length) {
    container.replaceChildren(node("p", "empty", selectedSource ? "У этого источника пока нет поставок. Выберите другой источник или обработайте файл." : "История появится после первой полной обработки. Предпросмотр не создаёт поставку."));
    return;
  }
  container.replaceChildren(table(["Поставка", "Источник", "Создана", "Ревизия / запуск", "Результат", "Позиции", "Текущий снимок", "Действия"], shipments.map(shipment => [
    shipment.id, shipment.source, dateText(shipment.created_at ?? shipment.processed_at),
    `${displayValue(shipment.profile_revision ?? shipment.profile_id)} / ${displayValue(shipment.generation)}`,
    badge(shipment.status), numberText(countValue(shipment.counts, ["items", "total_items"]) ?? shipment.item_count),
    shipmentIsCurrent(shipment) ? badge("active", "Текущий") : "—",
    button("Подробности", "button-quiet button-small", () => openShipment(shipment.id))
  ]), "История поставок"));
}

function navigateShipment(id) {
  selectedShipmentId = id;
  shipmentOffset = 0;
  if (currentView !== "shipments") window.location.hash = "shipments";
  else openShipment(id);
}

async function openShipment(id, offset = 0) {
  const token = ++shipmentRequest;
  selectedShipmentId = id;
  shipmentOffset = offset;
  const container = document.getElementById("shipment-detail");
  container.hidden = false;
  loading(container, "Читаем неизменяемую поставку и доказательства…");
  try {
    const result = record(await request(`/api/shipments/${encodeURIComponent(id)}?offset=${offset}&limit=${pageSize}`));
    if (token !== shipmentRequest) return;
    const shipment = record(result.shipment);
    if (shipment.id === undefined) throw new Error("Сервер не передал реквизиты поставки.");
    container.replaceChildren();
    const heading = sectionHeading(`Поставка ${shipment.id}`);
    heading.append(button("Закрыть детали", "button-quiet button-small", () => {
      ++shipmentRequest;
      selectedShipmentId = null;
      container.hidden = true;
    }));
    container.append(heading, metadata([
      ["Источник", shipment.source], ["Создана", dateText(shipment.created_at ?? shipment.processed_at)],
      ["Результат", badge(shipment.status)], ["Текущий снимок", shipmentIsCurrent(shipment) ? "Да" : "Нет по текущему состоянию сервера"],
      ["Профиль", shipment.profile_id ?? shipment.profile_revision], ["Запуск обработки", shipment.generation],
      ["Режим загрузки", modeOptions.find(([key]) => key === shipment.ingest_mode)?.[1] || shipment.ingest_mode],
      ["Причина", shipment.reason]
    ]), renderCounts(shipment.counts));
    const links = node("div", "field-row");
    if (shipment.file_id !== undefined && shipment.file_id !== null) {
      const download = node("a", "button button-secondary button-small", "Скачать исходный файл");
      download.href = `/api/files/${encodeURIComponent(shipment.file_id)}/raw`;
      links.append(download, button("Открыть файл", "button-quiet button-small", async () => {
        if (currentView !== "inbox") window.location.hash = "inbox";
        await openFile(shipment.file_id);
      }));
    }
    if (shipment.profile_id !== undefined && shipment.profile_id !== null) links.append(button("Ревизия профиля", "button-quiet button-small", () => navigateProfile(shipment.profile_id, shipment.profile_revision)));
    container.append(links, node("p", "section-note", "Ниже — страница позиций, карантина и исключений. В каждой записи доступны исходные значения, координаты и причины."), renderResultTabs(result));
    const knownTotals = [result.total_items, result.total_quarantine, result.total_dropped].filter(value => typeof value === "number" && Number.isFinite(value));
    const visibleCount = Math.max(sequence(result.items).length, sequence(result.quarantine).length, sequence(result.dropped).length);
    container.append(pagination(offset, knownTotals.length ? Math.max(...knownTotals) : undefined, visibleCount, next => openShipment(id, next)));
    container.append(detailsJson(shipment, "Все реквизиты неизменяемой поставки"));
    renderRollback(container, shipment);
    if (offset === 0) container.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (token === shipmentRequest) container.replaceChildren(notice(`Поставка не получена. ${error instanceof Error ? error.message : String(error)}`, "danger"), button("Повторить", "button-secondary", () => openShipment(id, offset)));
  } finally { if (token === shipmentRequest) container.removeAttribute("aria-busy"); }
}

function renderRollback(container, shipment) {
  const form = node("form", "rollback-form");
  form.append(node("h3", "", "Вернуться к этому снимку"));
  if (shipmentIsCurrent(shipment)) {
    form.append(node("p", "section-note", "Этот снимок уже текущий. Повторная активация не требуется."));
    container.append(form);
    return;
  }
  if (shipment.status !== "accepted" && shipment.can_activate !== true) {
    form.append(notice("Активация недоступна: сервер не сообщил, что эта поставка допустима для текущего каталога. Карантин не заменяет текущий снимок.", "warning"));
    container.append(form);
    return;
  }
  form.append(node("p", "section-note", "Текущий указатель источника переключится на этот неизменяемый снимок. Более новые поставки останутся в истории. Причина обязательна и попадёт в аудит."));
  const row = node("div", "field-row");
  const reason = input("text", "", { required: "", placeholder: "Причина возврата к этой поставке", minlength: "3" });
  const confirm = input("checkbox", "");
  confirm.required = true;
  const agreement = node("label", "check-field");
  agreement.append(confirm, node("span", "", `Подтверждаю смену текущего снимка источника «${shipment.source || "—"}».`));
  const activate = button("Активировать этот снимок", "button-danger");
  activate.type = "submit";
  row.append(field("Причина отката", reason), activate);
  const feedback = node("div");
  feedback.setAttribute("aria-live", "polite");
  form.append(agreement, row, feedback);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (!reason.value.trim()) { reason.focus(); return; }
    await runAction(activate, "Переключаем снимок…", async () => {
      const result = await post(`/api/shipments/${encodeURIComponent(shipment.id)}/activate`, { reason: reason.value.trim() });
      feedback.replaceChildren(notice("Сервер подтвердил активацию. Обновляем текущий указатель и каталог.", "success"));
      if (record(result).reason) feedback.append(node("p", "small", result.reason));
      await refreshState();
      await openShipment(shipment.id);
      announce(`Текущий снимок источника «${shipment.source}» переключён на поставку ${shipment.id}. Причина сохранена в аудите.`, "success");
    }, feedback);
  });
  container.append(form);
}

function renderProfileList() {
  const container = document.getElementById("profile-list");
  if (!snapshot.profiles.length) {
    container.replaceChildren(node("p", "empty", "Подтверждённых профилей пока нет. Создайте первый из файла во «Входящих»; новая ревизия появится только после успешной проверки."));
    return;
  }
  container.replaceChildren(table(["Профиль", "Источник", "Ревизия", "Режим", "Создана", "Действие"], snapshot.profiles.map(profile => [
    profile.name, profile.source, profile.revision ?? profile.id,
    modeOptions.find(([key]) => key === (profile.ingest_mode ?? record(profile.body).ingest_mode))?.[1] || profile.ingest_mode || record(profile.body).ingest_mode,
    dateText(profile.created_at), button("Посмотреть ревизию", "button-quiet button-small", () => openProfile(profile.id, profile.revision))
  ]), "Неизменяемые ревизии профилей"));
}

function navigateProfile(id, revision = null) {
  selectedProfileId = id;
  selectedProfileRevision = revision;
  if (currentView !== "profiles") window.location.hash = "profiles";
  else openProfile(id, revision);
}

async function openProfile(id, revision = null) {
  const token = ++profileRequest;
  selectedProfileId = id;
  selectedProfileRevision = revision;
  const container = document.getElementById("profile-detail");
  container.hidden = false;
  loading(container, "Загружаем сохранённую ревизию…");
  try {
    const response = record(await request(`/api/profiles/${encodeURIComponent(id)}${revision !== null && revision !== undefined ? `?revision=${encodeURIComponent(revision)}` : ""}`));
    if (token !== profileRequest) return;
    const profile = { ...response, ...record(response.profile || response.body) };
    container.replaceChildren();
    const heading = sectionHeading(profile.name || `Профиль ${id}`);
    const download = node("a", "button button-secondary button-small", "Скачать YAML");
    const exportedRevision = revision ?? profile.revision;
    download.href = `/api/profiles/${encodeURIComponent(id)}/yaml${exportedRevision !== undefined && exportedRevision !== null ? `?revision=${encodeURIComponent(exportedRevision)}` : ""}`;
    heading.append(download);
    heading.append(badge("approved", `Ревизия ${profile.revision ?? id}`), button("Закрыть", "button-quiet button-small", () => {
      ++profileRequest;
      selectedProfileId = null;
      container.hidden = true;
    }));
    container.append(heading, metadata([
      ["Источник", profile.source], ["Режим", modeOptions.find(([key]) => key === profile.ingest_mode)?.[1] || profile.ingest_mode],
      ["Создана", dateText(profile.created_at)], ["Отпечаток", profile.fingerprint], ["Идентификатор", profile.id ?? id]
    ]), node("p", "section-note", "Ревизия доступна только для чтения. Чтобы изменить настройки, откройте исходный файл и загрузите эту ревизию в форму как основу новой."));
    for (const [index, spec] of sequence(profile.tables).entries()) {
      const section = node("section", "workspace-section");
      section.append(sectionHeading(`Таблица ${index + 1} · ${spec.sheet}`), metadata([
        ["Ориентация", orientationLabel(spec.orientation)], ["Строки заголовка", `${displayValue(spec.header_start)}–${displayValue(spec.header_end)}`],
        ["Данные", `${displayValue(spec.data_start)}–${spec.data_end ?? "до конца"}`], ["Столбцы области", `${columnLabel(spec.start_col)}–${columnLabel(spec.end_col)}`], ["Валюта", spec.currency]
      ]));
      section.append(table(["Координата поля", "Назначение", "Цитата", "Вид цены / валюта", "Измерение", "Причина"], sequence(spec.columns).map(mapping => [
        spec.orientation === "vertical" ? `Строка ${mapping.row}` : `${columnLabel(mapping.col)} · ${mapping.col}`,
        String(mapping.target || "").startsWith("extra.") ? `Доп.: ${mapping.target.slice(6)}` : targetOptions.find(([key]) => key === mapping.target)?.[1] || mapping.target,
        quoteText(mapping.quote), `${displayValue(mapping.price_kind)} / ${displayValue(mapping.currency)}`, mapping.dimension, mapping.reason
      ]), `Сохранённые сопоставления таблицы ${index + 1}`));
      container.append(section);
    }
    const policies = node("section", "workspace-section");
    policies.append(sectionHeading("Сохранённые политики"), metadata([
      ...policyFields.map(definition => [definition.label, definition.options.find(([key]) => key === record(profile.policies)[definition.key])?.[1] || record(profile.policies)[definition.key]]),
      ["Заполнение объединённых ячеек", record(profile.policies).merged_fill],
      ["Порог карантина", record(profile.policies).quarantine_threshold]
    ]));
    container.append(policies, detailsJson(response, "Полная неизменяемая ревизия"));
    container.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (token === profileRequest) container.replaceChildren(notice(`Ревизия не получена. ${error instanceof Error ? error.message : String(error)}`, "danger"), button("Повторить", "button-secondary", () => openProfile(id, revision)));
  } finally { if (token === profileRequest) container.removeAttribute("aria-busy"); }
}

function policySupportNodes() {
  const policies = snapshot.capabilities.policies;
  return Array.from({ length: 11 }, (_, index) => {
    const key = `P${index + 1}`;
    const raw = Array.isArray(policies) ? policies.find(item => item?.id === key || item?.code === key) : record(policies)[key];
    const policy = record(raw);
    const section = node("section", "policy-rule");
    const title = node("h3");
    title.append(node("code", "", key), document.createTextNode(policy.label || policy.title || policy.name || "Стратегия обработки"));
    section.append(title);
    const supported = typeof raw === "boolean" ? raw : policy.supported ?? policy.enabled;
    section.append(badge(supported === true ? "accepted" : supported === false ? "unsupported" : "", supported === true ? "Поддерживается" : supported === false ? "Недоступна" : "Поддержка не заявлена"));
    section.append(node("p", "", policy.description || policy.desc || policy.reason || (typeof raw === "string" ? raw : "Сервер не предоставил описание и перечень поддерживаемых действий.")));
    const actions = sequence(policy.actions ?? policy.supported_actions);
    if (actions.length) section.append(node("p", "", `Действия сервера: ${actions.map(displayValue).join("; ")}`));
    if (policy.config_key) section.append(node("p", "", `Поле настройки: ${policy.config_key}`));
    return section;
  });
}

function renderSystemState() {
  const settingsLabels = {
    data_dir: "Каталог данных", storage: "Хранилище", database: "База данных", database_backend: "Тип базы данных", port: "Порт",
    max_upload_mb: "Максимальный файл, МБ", max_upload_bytes: "Максимальный файл, байт", max_decompressed_bytes: "Лимит распаковки, байт",
    max_cells: "Лимит ячеек", max_files: "Лимит файлов", bind: "Адрес сервера", host: "Адрес сервера", quarantine_threshold: "Порог карантина", quarantine_threshold_default: "Порог карантина по умолчанию", loopback_only: "Доступ только с этого компьютера"
  };
  const entries = Object.entries(snapshot.settings).map(([key, value]) => [settingsLabels[key] || key, value]);
  document.getElementById("system-settings").replaceChildren(entries.length ? metadata(entries) : node("p", "empty", "Сервер не передал настройки."));
  const adapters = record(snapshot.capabilities.adapters);
  const capabilities = new Map(Object.entries(adapters));
  for (const [key, value] of Object.entries(snapshot.capabilities)) {
    if (!["adapters", "policies", "formats", "limits", "ingest_modes", "features"].includes(key)) capabilities.set(key, value);
  }
  const optional = [["llm", "Языковая модель"], ["mail", "Почтовый приём"], ["postgres", "PostgreSQL"], ["remote_urls", "Загрузка по внешним ссылкам"]];
  for (const [key] of optional) if (!capabilities.has(key)) capabilities.set(key, { supported: null, description: "Не заявлен сервером. В интерфейсе подключения нет." });
  const names = { xlsx: "Книги XLSX", xls: "Книги XLS", csv: "Таблицы CSV", tsv: "Таблицы TSV", json: "Файлы JSON", yaml: "Файлы YAML", html: "Таблицы HTML", xml: "Файлы XML", sqlite: "Локальная SQLite", llm: "Языковая модель", mail: "Почтовый приём", email: "Почтовый приём", postgres: "PostgreSQL", remote_urls: "Загрузка по внешним ссылкам", pdf: "Документы PDF", ocr: "Распознавание изображений" };
  const list = node("div", "capability-list");
  for (const [key, raw] of capabilities) {
    const value = record(raw);
    const supported = typeof raw === "boolean" ? raw : value.supported ?? value.enabled;
    const row = node("div", "capability-row");
    const description = node("div");
    description.append(node("strong", "", value.label || value.name || names[key] || key));
    const reason = value.description || value.reason || value.note;
    if (reason) description.append(node("p", "", displayValue(reason)));
    else if (typeof raw === "string") description.append(node("p", "", raw));
    row.append(description, badge(supported === true ? "accepted" : "unsupported", supported === true ? "Доступен" : supported === false ? "Отключён" : "Не заявлен"));
    list.append(row);
  }
  const formats = sequence(snapshot.capabilities.formats);
  if (formats.length) list.prepend(node("p", "section-note", `Форматы, заявленные сервером: ${formats.map(format => typeof format === "object" ? format.name || format.format || displayValue(format) : format).join(", ")}`));
  list.append(detailsJson(snapshot.capabilities, "Точный ответ о возможностях сервера"));
  document.getElementById("system-capabilities").replaceChildren(list);
  const policies = node("div", "policy-list");
  policies.append(...policySupportNodes());
  document.getElementById("system-policies").replaceChildren(policies);
}

async function loadAudit() {
  const container = document.getElementById("audit-content");
  loading(container, "Читаем последние события…");
  try {
    const result = await request("/api/audit");
    const events = Array.isArray(result) ? result : sequence(record(result).events ?? record(result).audit ?? record(result).items);
    if (!events.length) container.replaceChildren(node("p", "empty", "Сервер не вернул событий. После загрузки, подтверждения или отката обновите журнал."));
    else container.replaceChildren(table(["Время", "Действие", "Объект", "Причина / сведения", "Доказательства"], events.map(event => [
      dateText(event.created_at ?? event.timestamp ?? event.ts ?? event.at), event.action ?? event.event_type ?? event.event,
      event.entity_id ?? event.target_id ?? event.shipment_id ?? event.file_id,
      event.reason ?? record(event.details).reason ?? event.message,
      detailsJson(event, "Полная запись")
    ]), "Последние события аудита"));
  } catch (error) { container.replaceChildren(notice(`Журнал не получен. ${error instanceof Error ? error.message : String(error)}`, "danger")); }
  finally { container.removeAttribute("aria-busy"); }
}

const jobStateLabels = { pending: "Ожидает", running: "Выполняется", completed: "Завершено", failed: "Не удалось" };
const jobStateTones = { pending: "", running: "warning", completed: "accepted", failed: "danger" };

async function loadJobs() {
  const container = document.getElementById("jobs-content");
  loading(container, "Читаем журнал заданий…");
  try {
    const result = await request("/api/jobs");
    const jobs = sequence(record(result).jobs ?? record(result).items);
    if (!jobs.length) container.replaceChildren(node("p", "empty", "Заданий пока нет. Подтверждение профиля или повторный разбор создают запись здесь."));
    else container.replaceChildren(table(["Задание", "Состояние", "Попытки", "Повторов", "Файл", "Обновлено", "Ошибка"], jobs.map(job => {
      const file = job.file_id
        ? (() => { const a = node("a", "text-link", job.file_id.slice(0, 8)); a.href = "#inbox"; a.title = "Открыть файл"; a.addEventListener("click", event => { event.preventDefault(); if (currentView !== "inbox") window.location.hash = "inbox"; openFile(job.file_id); }); return a; })()
        : "—";
      return [
        node("code", "", job.id.slice(0, 12)),
        badge(jobStateTones[job.state] || "", jobStateLabels[job.state] || job.state),
        displayValue(job.attempts),
        displayValue(record(job.result).retry_count ?? job.retry_count ?? 0),
        file,
        dateText(job.updated_at ?? job.created_at),
        job.error ? node("span", "small", `Тип: ${job.error}`) : "—"
      ];
    }), "Импорты с восстановлением после сбоев"));
  } catch (error) { container.replaceChildren(notice(`Журнал заданий не получен. ${error instanceof Error ? error.message : String(error)}`, "danger")); }
  finally { container.removeAttribute("aria-busy"); }
}

async function loadSystem() {
  renderSystemState();
  const health = document.getElementById("health-status");
  const metrics = document.getElementById("metrics-content");
  health.textContent = "Проверка…";
  health.removeAttribute("data-tone");
  metrics.textContent = "Получаем метрики…";
  await Promise.all([
    request("/health").then(result => {
      const status = record(result).status;
      health.textContent = statusLabels[status] || status || "Статус не передан";
      health.dataset.tone = status === "ok" ? "success" : "warning";
    }).catch(error => { health.textContent = `Недоступен: ${error.message}`; health.dataset.tone = "danger"; }),
    request("/metrics", { headers: { Accept: "text/plain" } }).then(result => { metrics.textContent = typeof result === "string" ? result : JSON.stringify(result, null, 2); }).catch(error => { metrics.textContent = `Не удалось получить метрики: ${error.message}`; }),
    loadAudit(),
    loadJobs()
  ]);
}

function switchView() {
  const name = window.location.hash.slice(1);
  currentView = Object.hasOwn(views, name) ? name : "inbox";
  const view = views[currentView];
  for (const [key] of Object.entries(views)) document.getElementById(`view-${key}`).hidden = key !== currentView;
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === currentView) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.getElementById("page-title").textContent = view.title;
  document.getElementById("page-description").textContent = view.description;
  document.getElementById("page-eyebrow").textContent = view.eyebrow;
  document.getElementById("breadcrumb-current").textContent = view.short;
  document.title = `${view.short} — Свод`;
  if (currentView === "catalog") loadCatalog();
  if (currentView === "shipments") {
    renderShipmentList();
    if (selectedShipmentId !== null) openShipment(selectedShipmentId, shipmentOffset);
  }
  if (currentView === "profiles") {
    renderProfileList();
    if (selectedProfileId !== null) openProfile(selectedProfileId, selectedProfileRevision);
  }
  if (currentView === "system") loadSystem();
}

document.getElementById("upload-form").addEventListener("submit", uploadFiles);
document.getElementById("upload-files").addEventListener("change", event => {
  const files = [...event.target.files];
  document.getElementById("selected-files-label").textContent = files.length ? `Выбрано файлов: ${files.length} · ${bytesText(files.reduce((total, file) => total + file.size, 0))}` : "Оригиналы не изменяются.";
});
document.getElementById("file-search").addEventListener("input", renderFiles);
document.getElementById("file-status").addEventListener("change", renderFiles);
document.getElementById("catalog-filter").addEventListener("submit", event => {
  event.preventDefault();
  catalogOffset = 0;
  loadCatalog();
});
document.getElementById("shipment-source").addEventListener("change", renderShipmentList);
document.getElementById("refresh-audit").addEventListener("click", event => runAction(event.currentTarget, "Обновление…", loadAudit));
document.getElementById("refresh-jobs").addEventListener("click", event => runAction(event.currentTarget, "Обновление…", loadJobs));
document.getElementById("refresh-state").addEventListener("click", event => runAction(event.currentTarget, "Обновление…", async () => {
  await refreshState();
  if (currentView === "catalog") await loadCatalog();
  if (currentView === "system") await loadSystem();
}));
window.addEventListener("hashchange", switchView);
window.addEventListener("beforeunload", event => {
  if (draftChanged || wizardBusy) { event.preventDefault(); event.returnValue = ""; }
});
switchView();
refreshState();
