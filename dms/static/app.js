const byId = (id) => document.getElementById(id);
const state = {
  token: sessionStorage.getItem("dms-token"),
  user: null,
  fields: [],
  catalog: false,
  editingField: null,
  detailsId: null,
};

const statusLabels = {
  own_division: "Your division", approved: "Approved", restricted: "Approval required",
  pending: "Pending", rejected: "Rejected",
};

async function api(path, { method = "GET", body, download = false } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(`/api${path}`, { method, headers, body });
  if (download && response.ok) return response.blob();
  const result = await response.json().catch(() => ({}));
  if (response.status === 401 && state.token && path !== "/auth/login") {
    showAuth("Your session expired. Sign in again.", true);
  }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function setMessage(id, text = "", error = false) {
  const node = byId(id);
  node.textContent = text;
  node.classList.toggle("error", error);
  node.hidden = !text;
}

async function run(action, { message = "app-message", buttons = [] } = {}) {
  setMessage(message);
  buttons.forEach((button) => { button.disabled = true; });
  try {
    await action();
  } catch (error) {
    setMessage(message, error.message, true);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function submit(id, handle, message = "app-message") {
  byId(id).addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const buttons = event.submitter ? [event.submitter] : [];
    run(() => handle(data), { message, buttons });
  });
}

function authMode(signup) {
  byId("auth-heading").textContent = signup ? "Create account" : "Sign in";
  byId("login-form").hidden = signup;
  byId("signup-form").hidden = !signup;
  byId("login-tab").setAttribute("aria-pressed", !signup);
  byId("signup-tab").setAttribute("aria-pressed", signup);
  setMessage("auth-message");
}

function showAuth(message = "", error = false) {
  sessionStorage.removeItem("dms-token");
  state.token = null;
  state.user = null;
  state.catalog = false;
  for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
  for (const form of document.querySelectorAll("form")) form.reset();
  byId("application").hidden = true;
  byId("auth").hidden = false;
  authMode(false);
  setMessage("auth-message", message, error);
}

async function showApplication(user) {
  state.user = user;
  byId("auth").hidden = true;
  byId("application").hidden = false;
  byId("avatar").textContent = [...user.username][0].toUpperCase();
  byId("account-name").textContent = user.username;
  byId("account-division").textContent = user.division;
  if (!location.hash) history.replaceState(null, "", "#documents");
  await route();
}

function inputField(label, name, placeholder, options = [], id = "") {
  const wrapper = element("label", label);
  const input = element("input");
  input.name = name;
  input.placeholder = placeholder;
  input.maxLength = 500;
  wrapper.append(input);
  if (options.length) {
    const values = element("datalist");
    values.id = id;
    input.setAttribute("list", id);
    for (const option of options) {
      const item = element("option");
      item.value = option;
      values.append(item);
    }
    wrapper.append(values);
  }
  return wrapper;
}

function renderFilters(id) {
  const container = byId(id);
  container.replaceChildren(inputField("Division", "Division", "All divisions"));
  for (const field of state.fields) {
    container.append(inputField(field.label, field.label, "Any value", field.options, `${id}-${field.id}`));
  }
}

function table(target, headings, rows, emptyMessage) {
  if (!rows.length) {
    target.replaceChildren(element("p", emptyMessage));
    return;
  }
  const grid = element("table");
  const heading = grid.createTHead().insertRow();
  for (const label of headings) {
    const cell = element("th", label);
    cell.scope = "col";
    heading.append(cell);
  }
  const body = grid.createTBody();
  for (const values of rows) {
    const row = body.insertRow();
    for (const value of values) {
      const cell = row.insertCell();
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value;
    }
  }
  target.replaceChildren(grid);
}

function statusPill(status) {
  return element("span", statusLabels[status], `pill ${status}`);
}

function documentLink(title, id) {
  const link = element("a", title);
  link.href = `#documents/${encodeURIComponent(id)}`;
  return link;
}

function formatDate(date) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(date));
}

function showDocumentRows(target, documents, emptyMessage, catalog = false) {
  const headings = catalog ? ["Title", "Division", "Access"] : ["Title", "Division", "Access", "Uploaded"];
  const rows = documents.map((doc) => {
    const row = [documentLink(doc.title, doc.id), doc.division, statusPill(doc.access_status)];
    if (!catalog) row.push(formatDate(doc.created_at));
    return row;
  });
  table(byId(target), headings, rows, emptyMessage);
}

function filterQuery(data) {
  const params = new URLSearchParams();
  for (const [name, value] of data) {
    if (value.trim()) params.set(name, value.trim());
  }
  return params.toString();
}

let documentLoad = 0;
async function loadDocuments(data = new FormData(byId("document-filters"))) {
  const load = ++documentLoad;
  const catalog = state.catalog;
  byId("document-filters").hidden = catalog;
  byId("catalog-note").hidden = !catalog;
  byId("accessible-tab").setAttribute("aria-pressed", !catalog);
  byId("catalog-tab").setAttribute("aria-pressed", catalog);
  byId("documents-list").replaceChildren(element("p", "Loading documents…"));
  const path = catalog ? "/documents/catalog" : `/documents?${filterQuery(data)}`;
  const { documents } = await api(path);
  if (load !== documentLoad) return;
  const empty = catalog ? "There are no documents from other divisions yet." : "No accessible documents match these filters.";
  showDocumentRows("documents-list", documents, empty, catalog);
}

function actionButton(text, className, handle) {
  const button = element("button", text, className);
  button.type = "button";
  button.addEventListener("click", () => run(handle, { buttons: [button] }));
  return button;
}

function metadataValue(value) {
  if (Array.isArray(value)) return value.map(metadataValue).join(", ") || "—";
  return value === null || value === "" ? "—" : String(value);
}

async function showDetails(id) {
  state.detailsId = id;
  byId("detail-title").textContent = "Document details";
  byId("detail-division").textContent = "Loading document…";
  const actions = byId("detail-actions");
  actions.replaceChildren();
  byId("detail-panel").hidden = true;
  const { document: doc } = await api(`/documents/${encodeURIComponent(id)}`);
  if (state.detailsId !== id) return;
  byId("detail-title").textContent = doc.title;
  byId("detail-division").textContent = doc.division;
  const details = byId("detail-metadata");
  const status = byId("detail-status");
  details.replaceChildren();
  status.hidden = true;

  if (doc.can_download) {
    actions.append(actionButton("Download", "primary", async () => {
      const file = await api(`/documents/${id}/download`, { download: true });
      const url = URL.createObjectURL(file);
      const link = element("a");
      link.href = url;
      link.download = doc.filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }));
    const entries = [["File name", doc.filename], ["Uploaded", formatDate(doc.created_at)], ...Object.entries(doc.metadata)];
    for (const [label, value] of entries) {
      const item = element("div");
      item.append(element("dt", label), element("dd", metadataValue(value)));
      details.append(item);
    }
  } else {
    actions.append(statusPill(doc.access_status));
    const messages = {
      restricted: "Request access to see the document’s metadata and download the file.",
      pending: "Your request is awaiting a decision from the owning division.",
      rejected: "The owning division rejected your request.",
    };
    status.textContent = messages[doc.access_status];
    status.hidden = false;
    if (doc.access_status === "restricted") {
      actions.append(actionButton("Request access", "primary", async () => {
        await api("/access/request", { method: "POST", body: { doc_id: id } });
        await showDetails(id);
        setMessage("app-message", "Access request sent.");
      }));
    }
  }
  byId("detail-panel").hidden = false;
}

async function loadInbox() {
  byId("requests-list").replaceChildren(element("p", "Loading access requests…"));
  const { requests } = await api("/access/requests");
  const rows = requests.map((item) => {
    const actions = element("div", undefined, "actions");
    if (item.status === "pending") {
      for (const decision of ["Approve", "Reject"]) {
        actions.append(actionButton(decision, decision === "Approve" ? "primary" : "secondary", async () => {
          await api(`/access/${decision.toLowerCase()}`, { method: "POST", body: { request_id: item.id } });
          await loadInbox();
        }));
      }
    }
    return [documentLink(item.title, item.doc_id), item.requester, item.requester_division,
      formatDate(item.created_at), statusPill(item.status), actions];
  });
  table(byId("requests-list"), ["Document", "Requested by", "Division", "Requested", "Status", "Decision"],
    rows, "No incoming access requests.");
}

function openField(field) {
  state.editingField = field?.id || null;
  byId("field-heading").textContent = field ? "Edit field" : "Add field";
  const inputs = byId("field-form").elements;
  inputs.namedItem("label").value = field?.label || "";
  inputs.namedItem("options").value = field?.options.join("\n") || "";
  setMessage("field-message");
  byId("field-dialog").showModal();
}

async function loadSettings() {
  const [{ fields }, { user }] = await Promise.all([api("/fields"), api("/auth/me")]);
  state.fields = fields;
  state.user = user;
  const admin = user.role === "admin";
  byId("add-field").hidden = !admin;
  const rows = fields.map((field) => {
    const row = [field.label, field.options.join(", ") || "Free text"];
    if (admin) row.push(actionButton("Edit", "secondary", () => openField(field)));
    return row;
  });
  table(byId("fields-list"), admin ? ["Field", "Suggested values", "Actions"] : ["Field", "Suggested values"], rows,
    "No custom fields are configured.");
}

async function route() {
  if (!state.user) return;
  const [page, id] = location.hash.slice(1).split("/");
  const active = id && page === "documents" ? "details" : (["search", "settings", "requests"].includes(page) ? page : "documents");
  state.detailsId = null;
  setMessage("app-message");
  for (const view of document.querySelectorAll(".view")) view.hidden = view.id !== active;
  for (const link of document.querySelectorAll("[data-page]")) {
    if (link.dataset.page === (active === "details" ? "documents" : active)) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }

  if (active === "details") await showDetails(id);
  if (active === "requests") await loadInbox();
  if (active === "settings") await loadSettings();
  if (active === "documents" || active === "search") {
    const { fields } = await api("/fields");
    state.fields = fields;
    if (active === "documents") {
      renderFilters("document-field-filters");
      await loadDocuments();
    } else {
      byId("search-form").reset();
      renderFilters("search-field-filters");
      byId("search-results").replaceChildren(element("p", "Enter search terms or select a filter."));
    }
  }
}

byId("login-tab").addEventListener("click", () => authMode(false));
byId("signup-tab").addEventListener("click", () => authMode(true));
byId("sign-out").addEventListener("click", () => {
  history.replaceState(null, "", location.pathname);
  showAuth();
});
window.addEventListener("hashchange", () => run(route));

submit("login-form", async (data) => {
  const { token, user } = await api("/auth/login", { method: "POST", body: Object.fromEntries(data) });
  state.token = token;
  sessionStorage.setItem("dms-token", token);
  byId("login-form").reset();
  await run(() => showApplication(user));
}, "auth-message");

submit("signup-form", async (data) => {
  const body = Object.fromEntries(data);
  if (!body.email) delete body.email;
  await api("/auth/register", { method: "POST", body });
  authMode(false);
  byId("signup-form").reset();
  byId("login-form").elements.namedItem("username").value = body.username;
  byId("login-form").elements.namedItem("password").focus();
  setMessage("auth-message", "Account created. You can sign in now.");
}, "auth-message");

byId("accessible-tab").addEventListener("click", () => { state.catalog = false; run(loadDocuments); });
byId("catalog-tab").addEventListener("click", () => { state.catalog = true; run(loadDocuments); });
submit("document-filters", loadDocuments);
submit("search-form", async (data) => {
  byId("search-results").replaceChildren(element("p", "Searching…"));
  const { results } = await api(`/search?${filterQuery(data)}`);
  showDocumentRows("search-results", results, "No accessible documents match your search.");
});

for (const button of document.querySelectorAll("[data-reset]")) {
  button.addEventListener("click", () => {
    const form = byId(button.dataset.reset);
    form.reset();
    form.querySelector("button:not([type=button])").click();
  });
}
for (const button of document.querySelectorAll("[data-close]")) {
  button.addEventListener("click", () => byId(button.dataset.close).close());
}

byId("open-upload").addEventListener("click", () => {
  byId("upload-form").reset();
  byId("upload-division").value = state.user.division;
  byId("upload-fields").replaceChildren(...state.fields.map((field) =>
    inputField(field.label, `field:${field.id}`, "Optional", field.options, `upload-${field.id}`)));
  setMessage("upload-message");
  byId("upload-dialog").showModal();
});

submit("upload-form", async (data) => {
  const fields = Object.create(null);
  for (const field of state.fields) {
    const key = `field:${field.id}`;
    const value = data.get(key)?.trim();
    if (value) fields[field.label] = value;
    data.delete(key);
  }
  data.set("metadata", JSON.stringify(fields));
  setMessage("upload-message", "Uploading and extracting text…");
  const { doc_id: id } = await api("/documents/upload", { method: "POST", body: data });
  byId("upload-dialog").close();
  state.catalog = false;
  location.hash = `documents/${id}`;
}, "upload-message");

byId("add-field").addEventListener("click", () => openField(null));
submit("field-form", async (data) => {
  const field = state.editingField;
  const body = { label: data.get("label"), options: data.get("options").split("\n").map((value) => value.trim()).filter(Boolean) };
  await api(field ? `/fields/${field}` : "/fields", { method: field ? "PATCH" : "POST", body });
  byId("field-dialog").close();
  await run(loadSettings);
}, "field-message");

async function start() {
  if (!state.token) {
    showAuth();
    return;
  }
  try {
    const { user } = await api("/auth/me");
    await run(() => showApplication(user));
  } catch (error) {
    showAuth(error.message, true);
  }
}

start();
