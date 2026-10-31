

/* ----------------------------- auth screen ----------------------------- */

function setAuthMode(mode) {
  authMode = mode === "register" ? "register" : "login";
  const registering = authMode === "register";
  const title = el("authTitle");
  const subtitle = el("authSubtitle");
  const submitText = el("authSubmitText");
  const switchText = el("authSwitchText");
  const switchBtn = el("authSwitchBtn");
  const pass = el("authPass");
  const errorBox = el("authError");
  if (title) title.textContent = registering ? t("auth.registerTitle") : t("auth.loginTitle");
  if (subtitle) subtitle.textContent = registering ? t("auth.registerSubtitle") : t("auth.loginSubtitle");
  if (submitText) submitText.textContent = registering ? t("auth.register") : t("auth.login");
  if (switchText) switchText.textContent = registering ? t("auth.toLogin") : t("auth.toRegister");
  if (switchBtn) switchBtn.textContent = registering ? t("auth.toLoginBtn") : t("auth.toRegisterBtn");
  if (pass) pass.autocomplete = registering ? "new-password" : "current-password";
  if (errorBox) {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }
  $$(".reg-only").forEach((node) => {
    node.hidden = !registering;
  });
  $$(".login-only").forEach((node) => {
    node.hidden = registering;
  });
  const authScreen = el("authScreen");
  if (authScreen) authScreen.classList.toggle("register-mode", registering);
}

function updateAuthThemeButton() {
  const button = el("authThemeBtn");
  if (!button) return;
  const dark = resolvedDark();
  button.textContent = dark ? "☀️" : "🌙";
  button.dataset.tooltip = t("tooltip.theme");
  button.dataset.tip = "tooltip.theme";
}

function showAuth() {
  el("authScreen").hidden = false;
  el("app").hidden = true;
  document.body.classList.add("auth-mode");
  document.body.classList.remove("app-mode");
  updateAuthThemeButton();
  localizeStatic();
  setTimeout(() => {
    try {
      el("authUser")?.focus({ preventScroll: true });
    } catch {
      /* ignore */
    }
  }, 80);
}

function showApp() {
  el("authScreen").hidden = true;
  el("app").hidden = false;
  document.body.classList.remove("auth-mode");
  document.body.classList.add("app-mode");
}

function resetState() {
  state.user = null;
  state.groups = [];
  state.bookmarks = [];
  state.tags = [];
  state.stats = null;
  state.view = { type: "home", groupId: null, tag: null, q: "" };
  state.draggingBookmark = null;
  state.draggingGroup = null;
}

async function enterApp() {
  showApp();
  renderUser();
  applySettings({ resave: false });
  renderStatus();
  closePopover();
  await loadAll({ skeleton: true });
}

async function doLogout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch {
    /* log out locally anyway */
  }
  resetState();
  showAuth();
  toast(t("auth.logout"), "success");
}

async function submitAuth(event) {
  event.preventDefault();
  const button = el("authSubmit");
  const errorBox = el("authError");
  const username = el("authUser").value.trim();
  const password = el("authPass").value;
  const displayName = el("authName").value.trim();
  if (errorBox) errorBox.hidden = true;
  if (!username) {
    if (errorBox) {
      errorBox.textContent = t("err.username_required");
      errorBox.hidden = false;
    }
    el("authUser")?.focus();
    return;
  }
  if (!password) {
    if (errorBox) {
      errorBox.textContent = t("err.password_required");
      errorBox.hidden = false;
    }
    el("authPass")?.focus();
    return;
  }
  setButtonBusy(button, true);
  try {
    const path = authMode === "register" ? "/auth/register" : "/auth/login";
    const body = { username, password };
    if (authMode === "register") {
      body.display_name = displayName;
      body.lang = getLang();
    } else {
      body.remember = Boolean(el("remember")?.checked);
    }
    const result = await api(path, { method: "POST", body });
    state.user = result.user;
    state.settings = { ...SETTINGS_DEFAULTS, ...(result.user?.settings || {}) };
    el("authForm").reset();
    if (errorBox) errorBox.hidden = true;
    await enterApp();
  } catch (error) {
    if (errorBox) {
      errorBox.textContent = errorText(error);
      errorBox.hidden = false;
    }
  } finally {
    setButtonBusy(button, false);
  }
}

/* ----------------------------- data loading ----------------------------- */

function viewParams() {
  const params = new URLSearchParams();
  const view = state.view;
  if (view.type === "trash") params.set("view", "trash");
  if (view.type === "favorites") params.set("favorites", "1");
  if (view.type === "group" && view.groupId) params.set("group_id", String(view.groupId));
  if (view.type === "tag" && view.tag) params.set("tag", view.tag);
  if (view.q) params.set("q", view.q);
  params.set("sort", SORT_KEYS.includes(state.settings.sort) ? state.settings.sort : "created");
  params.set("sort_dir", state.settings.sort_dir === "asc" ? "asc" : "desc");
  return params;
}

async function loadAll(options = {}) {
  const skeleton = options.skeleton !== false;
  try {
    const [groupsResult, tagsResult, statsResult] = await Promise.all([
      api("/groups"),
      api("/tags"),
      api("/stats"),
    ]);
    state.groups = groupsResult.groups || [];
    state.tags = tagsResult.tags || [];
    state.stats = statsResult;
    syncAddGroupSelect();
    renderSidebar();
    renderUser();
    renderStatus();
  } catch (error) {
    if (error.status === 401) return;
    renderError(error);
    return;
  }
  await loadBookmarks({ skeleton });
}

async function refreshAll(options = {}) {
  await loadAll({ skeleton: options.skeleton === true });
}

async function loadBookmarks(options = {}) {
  state.loading = true;
  if (options.skeleton) renderSkeleton();
  try {
    const result = await api(`/bookmarks?${viewParams().toString()}`);
    state.bookmarks = result.bookmarks || [];
    renderHead();
    renderFilters();
    updateSearchMeta();
    renderList();
    markNavActive();
  } catch (error) {
    if (error.status === 401) return;
    renderError(error);
  } finally {
    state.loading = false;
  }
}

async function loadBookmarksQuiet() {
  try {
    const result = await api(`/bookmarks?${viewParams().toString()}`);
    state.bookmarks = result.bookmarks || [];
    renderHead();
    renderFilters();
    updateSearchMeta();
    renderList();
    markNavActive();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

/* ----------------------------- sidebar / status ----------------------------- */

function groupDisplayName(group) {
  if (group.kind === "favorites") return t("sidebar.favorites");
  if (group.kind === "secret") return t("sidebar.secret");
  return group.name;
}

function renderSidebar() {
  const list = el("groupList");
  if (!list) return;
  const stats = state.stats || { bookmarks: 0, trash: 0, groups: 0, tags: 0, favorites: 0 };
  const customGroups = state.groups.filter((group) => group.kind === "custom");

  list.innerHTML = state.groups
    .map((group) => {
      const favorites = group.kind === "favorites";
      const secret = group.kind === "secret";
      const locked = secret && !group.unlocked;
      const count = Number(group.count) || 0;
      const icon = secret
        ? locked
          ? "🔐"
          : "🔓"
        : esc(group.icon || (favorites ? "🔥" : "📁"));
      return `<div class="group-item ${favorites ? "is-favorites" : ""}${
        secret ? " is-secret" : ""
      }" data-group-id="${group.id}"
        role="button" tabindex="0" ${favorites || secret ? "" : 'draggable="true"'}>
        <span class="group-ico${secret ? " group-lock" : ""}" aria-hidden="true"
          ${
            secret
              ? `data-secret-toggle title="${esc(
                  locked
                    ? t("secret.lockHintClose")
                    : group.password_set
                      ? t("secret.lockHintOpen")
                      : t("secret.lockHintNone"),
                )}"`
              : ""
          }>${icon}</span>
        <span class="group-name">${esc(groupDisplayName(group))}</span>
        <span class="group-count">${count || ""}</span>
        ${
          favorites
            ? ""
            : `<button type="button" class="group-more" data-group-menu="${group.id}"
                aria-label="${esc(t("common.more"))}" title="${esc(t("common.more"))}">⋯</button>`
        }
      </div>`;
    })
    .join("");

  const noGroups = el("noGroups");
  if (noGroups) noGroups.hidden = customGroups.length > 0;

  const homeBadge = el("homeBadge");
  if (homeBadge) homeBadge.textContent = stats.bookmarks ? String(stats.bookmarks) : "";
  const trashBadge = el("trashBadge");
  if (trashBadge) {
    trashBadge.hidden = !stats.trash;
    trashBadge.textContent = stats.trash ? String(stats.trash) : "";
  }
  const tagsBadge = el("tagsBadge");
  if (tagsBadge) {
    tagsBadge.hidden = !stats.tags;
    tagsBadge.textContent = stats.tags ? String(stats.tags) : "";
  }

  const summary = el("sidebarSummary");
  if (summary) {
    summary.innerHTML = `<span>${esc(tp("links", stats.bookmarks || 0))}</span>
      <span class="summary-dot">·</span>
      <span>${esc(tp("groups", stats.groups || 0))}</span>`;
  }
  renderQuickLinks();
  markNavActive();
}

function markNavActive() {
  const view = state.view;
  const navItem = {
    home: view.type === "home",
    search: view.type === "search",
    trash: view.type === "trash",
    tags: view.type === "tags" || view.type === "tag",
  };
  $$("#mainNav [data-nav]").forEach((button) => {
    button.classList.toggle("active", Boolean(navItem[button.dataset.nav]));
  });
  $$("#groupList .group-item").forEach((item) => {
    const id = Number(item.dataset.groupId);
    const group = state.groups.find((entry) => Number(entry.id) === id);
    const active = group
      ? (view.type === "group" && Number(view.groupId) === id) ||
        (view.type === "favorites" && group.kind === "favorites")
      : false;
    item.classList.toggle("active", active);
  });
}

/* ------------------------------------------------------------------ *
 *  Quick links — five one-click shortcuts at the bottom of the sidebar
 * ------------------------------------------------------------------ */

const QUICK_LINKS_MAX = 5;

function quickLinks() {
  return Array.isArray(state.settings?.quicklinks) ? state.settings.quicklinks : [];
}

function renderQuickLinks() {
  const host = el("quickLinksRow");
  if (!host) return;
  const links = quickLinks();
  const slots = [];
  for (let i = 0; i < QUICK_LINKS_MAX; i++) {
    const link = links[i];
    const tipAnchor = i < 2 ? "left" : i > 2 ? "right" : "center";
    if (link && link.url) {
      const hostName = hostOf(link.url);
      const label = link.title || hostName;
      const icoSrc = link.icon
        ? link.icon
        : `/api/icon?u=${encodeURIComponent(link.url).replaceAll("'", "%27")}`;
      slots.push(
        `<button type="button" class="ql-slot" data-ql-index="${i}" data-ql-tip="${tipAnchor}"
          data-tooltip="${esc(label)}" data-tip="literal" aria-label="${esc(label)}">
          <img class="ql-ico" src="${esc(icoSrc)}"
            alt="" loading="lazy" decoding="async">
          <span class="ql-fallback" aria-hidden="true">${esc((hostName || "?").slice(0, 1).toUpperCase())}</span>
        </button>`,
      );
    } else {
      slots.push(
        `<button type="button" class="ql-slot empty" data-ql-empty data-ql-tip="${tipAnchor}"
          data-tooltip="${esc(t("tooltip.quickLinkAdd"))}" data-tip="tooltip.quickLinkAdd"
          aria-label="${esc(t("tooltip.quickLinkAdd"))}">
          <span class="ql-plus" aria-hidden="true">＋</span>
        </button>`,
      );
    }
  }
  host.innerHTML = slots.join("");
  $$(".ql-ico", host).forEach((img) => {
    img.addEventListener(
      "error",
      () => img.closest(".ql-slot")?.classList.add("no-ico"),
      { once: true },
    );
  });
}

function applyQuickLinks(next) {
  state.settings.quicklinks = next;
  applySettings({ persist: true, resave: true });
  renderQuickLinks();
}

function qlListHtml() {
  const links = quickLinks();
  if (!links.length) return `<p class="ql-list-empty">${esc(t("quickLinks.empty"))}</p>`;
  return links
    .map((link, i) => {
      const hostName = hostOf(link.url);
      const icoSrc = link.icon
        ? link.icon
        : `/api/icon?u=${encodeURIComponent(link.url).replaceAll("'", "%27")}`;
      return `<div class="ql-item">
        <span class="ql-item-ico">
          <img class="ql-ico" src="${esc(icoSrc)}" alt="">
          <span class="ql-fallback" aria-hidden="true">${esc((hostName || "?").slice(0, 1).toUpperCase())}</span>
        </span>
        <span class="ql-item-text">
          <strong>${esc(link.title || hostName)}</strong>
          <small>${esc(hostName)}</small>
        </span>
        <span class="ql-item-move">
          <button type="button" class="icon-btn sm tip-below" data-ql-up="${i}" ${i === 0 ? "disabled" : ""}
            data-tooltip="${esc(t("tooltip.quickLinkUp"))}" data-tip="tooltip.quickLinkUp"
            aria-label="${esc(t("tooltip.quickLinkUp"))}">↑</button>
          <button type="button" class="icon-btn sm tip-below" data-ql-down="${i}" ${
            i === links.length - 1 ? "disabled" : ""
          }
            data-tooltip="${esc(t("tooltip.quickLinkDown"))}" data-tip="tooltip.quickLinkDown"
            aria-label="${esc(t("tooltip.quickLinkDown"))}">↓</button>
        </span>
        <button type="button" class="icon-btn sm" data-ql-edit="${i}"
          aria-label="${esc(t("common.edit"))}">✎</button>
        <button type="button" class="icon-btn sm" data-ql-remove="${i}"
          aria-label="${esc(t("common.delete"))}">✕</button>
      </div>`;
    })
    .join("");
}

function bindQlList(dialog) {
  $$("[data-ql-edit]", dialog).forEach((button) => {
    button.addEventListener("click", () => startQlEdit(Number(button.dataset.qlEdit), dialog));
  });
  $$("[data-ql-remove]", dialog).forEach((button) => {
    button.addEventListener("click", () => removeQuickLink(Number(button.dataset.qlRemove), dialog));
  });
  $$("[data-ql-up]", dialog).forEach((button) => {
    button.addEventListener("click", () => moveQuickLink(Number(button.dataset.qlUp), -1, dialog));
  });
  $$("[data-ql-down]", dialog).forEach((button) => {
    button.addEventListener("click", () => moveQuickLink(Number(button.dataset.qlDown), 1, dialog));
  });
}

function moveQuickLink(index, dir, dialog) {
  const next = quickLinks().slice();
  const target = index + dir;
  if (target < 0 || target >= next.length) return;
  [next[index], next[target]] = [next[target], next[index]];
  applyQuickLinks(next);
  toast(t("quickLinks.updated"), "success");
  refreshQlDialog(dialog);
}

/* Custom icon (data-URI) of the quick link being added/edited.
   null = use the site favicon. */
let qlIconValue = null;

function syncQlIcon(dialog) {
  const prev = el("qlIconPrev", dialog);
  if (prev) {
    prev.innerHTML = qlIconValue
      ? `<img src="${esc(qlIconValue)}" alt="">`
      : `<span aria-hidden="true">🌐</span>`;
  }
  const clear = el("qlIconClear", dialog);
  if (clear) clear.hidden = !qlIconValue;
}

function showQlError(dialog, message) {
  const error = el("qlError", dialog);
  if (error) {
    error.textContent = message;
    error.hidden = false;
  }
}

function resetQlForm(dialog) {
  qlEditIndex = null;
  qlIconValue = null;
  const url = el("qlUrl");
  const name = el("qlName");
  if (url) url.value = "";
  if (name) name.value = "";
  const iconFile = el("qlIconFile", dialog);
  if (iconFile) iconFile.value = "";
  const error = el("qlError");
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  const save = el("qlSave");
  if (save) save.textContent = t("quickLinks.add");
  const cancel = el("qlCancel");
  if (cancel) cancel.hidden = true;
  syncQlIcon(dialog);
}

function startQlEdit(index, dialog) {
  const link = quickLinks()[index];
  if (!link) return;
  qlEditIndex = index;
  qlIconValue = link.icon || null;
  const url = el("qlUrl", dialog);
  const name = el("qlName", dialog);
  if (url) url.value = link.url;
  if (name) name.value = link.title || "";
  const iconFile = el("qlIconFile", dialog);
  if (iconFile) iconFile.value = "";
  const error = el("qlError", dialog);
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  const save = el("qlSave", dialog);
  if (save) save.textContent = t("quickLinks.update");
  const cancel = el("qlCancel", dialog);
  if (cancel) cancel.hidden = false;
  syncQlIcon(dialog);
  try {
    url?.focus({ preventScroll: true });
  } catch {
    /* ignore */
  }
}

function removeQuickLink(index, dialog) {
  const next = quickLinks().filter((_, i) => i !== index);
  if (qlEditIndex === index) resetQlForm(dialog);
  applyQuickLinks(next);
  toast(t("quickLinks.removed"), "success");
  refreshQlDialog(dialog);
}

function saveQuickLink(dialog) {
  const url = fetchUrl(el("qlUrl", dialog)?.value);
  if (!url) {
    const error = el("qlError", dialog);
    if (error) {
      error.textContent = t("quickLinks.invalidUrl");
      error.hidden = false;
    }
    return;
  }
  const title = (el("qlName", dialog)?.value || "").trim().slice(0, 200);
  const links = quickLinks();
  if (qlEditIndex == null && links.length >= QUICK_LINKS_MAX) {
    const error = el("qlError", dialog);
    if (error) {
      error.textContent = t("quickLinks.full");
      error.hidden = false;
    }
    return;
  }
  const next = links.slice();
  if (qlEditIndex == null) next.push({ url, title, icon: qlIconValue });
  else next[qlEditIndex] = { url, title, icon: qlIconValue };
  applyQuickLinks(next);
  toast(t("quickLinks.updated"), "success");
  resetQlForm(dialog);
  refreshQlDialog(dialog);
}

function refreshQlDialog(dialog) {
  const list = $(".ql-list", dialog);
  if (list) {
    list.innerHTML = qlListHtml();
    bindQlList(dialog);
  }
  const full = quickLinks().length >= QUICK_LINKS_MAX;
  let notice = $(".ql-full", dialog);
  if (full && !notice) {
    notice = document.createElement("p");
    notice.className = "ql-full";
    const body = $(".dlg-body", dialog);
    if (body) body.appendChild(notice);
  }
  if (notice) {
    notice.textContent = t("quickLinks.full");
    notice.hidden = !full;
  }
}

let qlEditIndex = null;

function openQuickLinksDialog() {
  const full = quickLinks().length >= QUICK_LINKS_MAX;
  qlEditIndex = null;
  qlIconValue = null;
  openDialog(
    `${dialogHead("⚡", t("quickLinks.title"), t("quickLinks.subtitle"))}
    <div class="dlg-body">
      <div class="ql-list">${qlListHtml()}</div>
      <form id="qlForm" class="ql-form" autocomplete="off" novalidate>
        <div class="field-group">
          <label for="qlUrl">${t("quickLinks.url")}</label>
          <input id="qlUrl" type="text" inputmode="url" spellcheck="false"
            placeholder="${esc(t("quickLinks.urlPlaceholder") || "https://example.com")}" required>
        </div>
        <div class="field-group">
          <label for="qlName">${t("quickLinks.name")} <span class="opt">${t("common.optional")}</span></label>
          <input id="qlName" type="text" maxlength="200"
            placeholder="${esc(t("quickLinks.namePlaceholder"))}">
        </div>
        <div class="field-group">
          <label>${t("quickLinks.icon")} <span class="opt">${t("common.optional")}</span></label>
          <div class="file-row">
            <span class="ql-icon-prev" id="qlIconPrev" aria-hidden="true"></span>
            <input type="file" id="qlIconFile" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml" hidden>
            <button type="button" class="btn" id="qlIconBrowse">${t("quickLinks.iconBrowse")}</button>
            <button type="button" class="btn danger" id="qlIconClear" hidden>${t("quickLinks.iconRemove")}</button>
            <span class="hint">${t("quickLinks.iconHint")}</span>
          </div>
        </div>
        <p id="qlError" class="form-error" hidden></p>
      </form>
    </div>
    <div class="dlg-foot">
      <button type="button" class="btn" data-close>${t("common.done")}</button>
      <button type="button" class="btn" id="qlCancel" hidden>${t("quickLinks.cancel")}</button>
      <button type="button" class="btn primary" id="qlSave">${t("quickLinks.add")}</button>
    </div>`,
    {
      onMount(dialog) {
        bindQlList(dialog);
        el("qlSave", dialog)?.addEventListener("click", () => saveQuickLink(dialog));
        el("qlCancel", dialog)?.addEventListener("click", () => resetQlForm(dialog));
        el("qlForm", dialog)?.addEventListener("submit", (event) => {
          event.preventDefault();
          saveQuickLink(dialog);
        });
        const iconFile = el("qlIconFile", dialog);
        el("qlIconBrowse", dialog)?.addEventListener("click", () => iconFile?.click());
        iconFile?.addEventListener("change", () => {
          const file = iconFile.files && iconFile.files[0];
          if (!file) return;
          if (!file.type.startsWith("image/")) {
            showQlError(dialog, t("quickLinks.iconType"));
            return;
          }
          if (file.size > 512 * 1024) {
            showQlError(dialog, t("quickLinks.iconTooBig"));
            return;
          }
          const reader = new FileReader();
          reader.onload = () => {
            qlIconValue = String(reader.result);
            syncQlIcon(dialog);
          };
          reader.onerror = () => showQlError(dialog, t("quickLinks.iconType"));
          reader.readAsDataURL(file);
        });
        el("qlIconClear", dialog)?.addEventListener("click", () => {
          qlIconValue = null;
          if (iconFile) iconFile.value = "";
          syncQlIcon(dialog);
        });
        refreshQlDialog(dialog);
      },
    },
  );
}

function renderUser() {
  const button = el("avatarBtn");
  if (!button) return;
  const user = state.user;
  if (!user) {
    button.textContent = "?";
    return;
  }
  if (user.avatar_photo) {
    button.innerHTML = `<img class="avatar-photo" src="${user.avatar_photo}" alt="">`;
  } else {
    button.textContent = initials(user.display_name || user.username);
  }
  button.style.setProperty("--avatar-color", user.avatar_color || currentAccent());
  button.dataset.tooltip = t("tooltip.profile");
  button.dataset.tip = "tooltip.profile";
  button.setAttribute("aria-label", `${t("profile.title")}: ${user.display_name || user.username}`);
}

function renderStatus() {
  const sortLabel = el("sortLabel");
  if (sortLabel) {
    const key = SORT_LABELS[state.settings.sort] || SORT_LABELS.created;
    sortLabel.textContent = t(key);
  }
  $$("#layoutSwitch [data-layout]").forEach((button) => {
    const active = button.dataset.layout === state.settings.layout;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

/* ----------------------------- view head / filters ----------------------------- */

function viewTitle() {
  const view = state.view;
  const stats = state.stats || { bookmarks: 0, trash: 0, tags: 0 };
  if (view.type === "home") {
    return {
      title: t("home.hello", { name: state.user?.display_name || state.user?.username || "" }),
      subtitle: t("home.subtitle", {
        links: tp("links", stats.bookmarks || 0),
        groups: tp("groups", stats.groups || 0),
        tags: tp("tags", stats.tags || 0),
      }),
      icon: "",
    };
  }
  if (view.type === "search") {
    return {
      title: t("search.results"),
      subtitle: view.q ? t("search.for", { q: view.q }) : t("search.scope"),
      icon: "🔍",
    };
  }
  if (view.type === "favorites") {
    return { title: t("favorites.title"), subtitle: t("favorites.subtitle"), icon: "🔥" };
  }
  if (view.type === "trash") {
    return {
      title: t("trash.title"),
      subtitle: stats.trash ? t("trash.emptyCount", { n: stats.trash }) : t("trash.subtitle"),
      icon: "🗑️",
    };
  }
  if (view.type === "tags") {
    return { title: t("tags.title"), subtitle: t("tags.subtitle"), icon: "🏷️" };
  }
  if (view.type === "tag") {
    return {
      title: t("tags.filterTitle", { tag: view.tag || "" }),
      subtitle: tp("links", state.bookmarks.length),
      icon: "🏷️",
    };
  }
  const group = state.groups.find((entry) => Number(entry.id) === Number(view.groupId));
  if (group?.kind === "secret") {
    return {
      title: groupDisplayName(group),
      subtitle: tp("links", group.count || 0),
      icon: group.unlocked ? "🔓" : "🔐",
    };
  }
  return {
    title: group ? groupDisplayName(group) : t("home.title"),
    subtitle: group ? tp("links", group.count || 0) : "",
    icon: group?.icon || "📁",
  };
}

function renderHead() {
  const host = el("viewHead");
  if (!host) return;
  const info = viewTitle();
  const view = state.view;
  const actions = [];

  if (view.type === "trash") {
    if ((state.stats?.trash || 0) > 0) {
      actions.push(
        `<button type="button" class="btn subtle" data-view-action="restore-all">↩ <span>${t(
          "trash.restoreAll",
        )}</span></button>`,
        `<button type="button" class="btn danger-soft" data-view-action="empty-trash">🗑 <span>${t(
          "trash.emptyAction",
        )}</span></button>`,
      );
    }
  } else if (view.type === "group") {
    /* Groups only keep the contextual "Edit" action; "Add link" is not
       repeated here either — the statusbar button and the N hotkey already
       do that (the add dialog has a group selector). */
    actions.push(
      `<button type="button" class="btn subtle" data-view-action="edit-group">✎ <span>${t(
        "common.edit",
      )}</span></button>`,
    );
  }

  /* Home / search / tag / group views no longer repeat the "Add link"
     button here — the statusbar button and the N hotkey already do that.
     The top-right slot belongs to the live clock instead. */

  host.innerHTML = `<div class="view-head-main">
      <h1>${info.icon ? `<span class="head-ico" aria-hidden="true">${esc(info.icon)}</span>` : ""}<span>${esc(
        info.title,
      )}</span></h1>
      <p>${esc(info.subtitle)}</p>
    </div>
    <div class="view-actions">${actions.join("")}${clockChip()}</div>`;
  startClock();
}

/* ------------------------------------------------------------------ *
 *  Header clock: live time + date in the top-right corner
 * ------------------------------------------------------------------ */
function clockChip() {
  return `<div class="clock-wrap">
    <div class="clock-chip" role="timer" aria-label="${esc(t("clock.label"))}">
      <span class="clock-time"><span class="clock-dot" aria-hidden="true"></span><span id="clockTime">--:--:--</span></span>
      <span class="clock-date" id="clockDate">&nbsp;</span>
    </div>
    <div class="mini-cal" id="miniCal" role="dialog" aria-label="${esc(t("calendar.label"))}">
      <div class="mc-head">
        <button type="button" class="mc-nav" data-cal-nav="-1" aria-label="${esc(t("calendar.prev"))}">‹</button>
        <span class="mc-title" id="calTitle">&nbsp;</span>
        <button type="button" class="mc-nav" data-cal-nav="1" aria-label="${esc(t("calendar.next"))}">›</button>
      </div>
      <div class="mc-grid" id="calGrid"></div>
    </div>
  </div>`;
}

let clockTimer = null;
let calOffset = 0; // months away from the current one (calendar popup)
let calLastKey = ""; // re-render the calendar only when the date actually changes

function clockTick() {
  const timeEl = el("clockTime");
  const dateEl = el("clockDate");
  if (!timeEl || !dateEl) return;
  const loc = state.settings?.lang === "en" ? "en-GB" : "ru-RU";
  const now = new Date();
  timeEl.textContent = new Intl.DateTimeFormat(loc, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(now);
  const dateParts = new Intl.DateTimeFormat(loc, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).formatToParts(now);
  const dv = (type) => dateParts.find((p) => p.type === type)?.value || "";
  dateEl.textContent = `${dv("weekday")}, ${dv("day")} ${dv("month").replace(/\.+$/, "")} ${dv("year")}`;
  const dayKey = `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}`;
  if (dayKey !== calLastKey) {
    calLastKey = dayKey;
    renderMiniCal();
  }
}

/* Mini calendar shown while hovering the clock chip. */
function renderMiniCal() {
  const grid = el("calGrid");
  const titleEl = el("calTitle");
  if (!grid || !titleEl) return;
  const loc = state.settings?.lang === "en" ? "en-GB" : "ru-RU";
  const now = new Date();
  const month = new Date(now.getFullYear(), now.getMonth() + calOffset, 1);
  titleEl.textContent = new Intl.DateTimeFormat(loc, {
    month: "long",
    year: "numeric",
  }).format(month);

  const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
  const lead = (firstDay.getDay() + 6) % 7; // Monday-first grid
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const prevMonthDays = new Date(month.getFullYear(), month.getMonth(), 0).getDate();
  const weeks = Math.ceil((lead + daysInMonth) / 7);

  // 2024-01-01 was a Monday — a stable reference for weekday names.
  const wdNames = Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(loc, { weekday: "short" }).format(new Date(2024, 0, 1 + i)),
  );

  const cells = wdNames.map((name) => `<span class="mc-wd" aria-hidden="true">${esc(name)}</span>`);
  for (let i = 0; i < weeks * 7; i++) {
    const dayNum = i - lead + 1;
    if (dayNum < 1) {
      cells.push(`<span class="mc-day out">${prevMonthDays + dayNum}</span>`);
    } else if (dayNum > daysInMonth) {
      cells.push(`<span class="mc-day out">${dayNum - daysInMonth}</span>`);
    } else {
      const isToday = calOffset === 0 && dayNum === now.getDate();
      cells.push(`<span class="mc-day${isToday ? " today" : ""}">${dayNum}</span>`);
    }
  }
  grid.innerHTML = cells.join("");
}

function startClock() {
  clockTick();
  renderMiniCal();
  if (!clockTimer) clockTimer = setInterval(clockTick, 1000);
}

function renderFilters() {
  const host = el("filters");
  if (!host) return;
  const chips = [];
  if (state.view.type === "search" && state.view.q) {
    chips.push(
      `<button type="button" class="filter-chip" data-filter-clear="search">🔍 ${esc(
        state.view.q,
      )}<span aria-hidden="true">✕</span></button>`,
    );
  }
  if (state.view.type === "tag" && state.view.tag) {
    chips.push(
      `<button type="button" class="filter-chip" data-filter-clear="tag">#${esc(
        state.view.tag,
      )}<span aria-hidden="true">✕</span></button>`,
    );
  }
  host.hidden = chips.length === 0;
  host.innerHTML = chips.join("");
}

function updateSearchMeta() {
  const count = el("searchCount");
  const scope = el("searchScope");
  const clear = el("searchClear");
  if (scope) scope.textContent = t("search.scope");
  if (count) {
    count.textContent = state.view.q ? t("search.found", { n: state.bookmarks.length }) : "";
  }
  if (clear) clear.hidden = !(el("searchInput")?.value || "").trim();
}
