/* ==========================================================================
   Bookmarks — front-end core: state, helpers, API, settings, auth
   ========================================================================== */

import { t, tp, setLang, getLang } from "./i18n.js";

const VERSION = document.querySelector('meta[name="bookmarks-version"]')?.content || "1.0.0";

/* Public repository — shown as a link in the "About" dialog. */
const REPO_URL = "https://github.com/evgeniy7f2/Bookmarks";

/* The accent color is part of the active theme palette (see theme.js).
   This helper reads the currently applied value for avatar fallbacks. */
function currentAccent() {
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim();
    if (value) return value;
  } catch {
    /* ignore */
  }
  return "#58a6ff";
}

const AVATAR_COLORS = [
  "#6366f1", "#8b5cf6", "#d946ef", "#ec4899", "#f43f5e", "#f97316",
  "#f59e0b", "#84cc16", "#22c55e", "#10b981", "#14b8a6", "#06b6d4",
  "#0ea5e9", "#3b82f6", "#64748b", "#a16207",
];

const GROUP_ICONS = [
  "📁", "💼", "🏠", "🛠️", "🎨", "📚", "🎵", "🎮", "🌍", "🧪", "💡", "📷",
  "🍿", "🏋️", "✈️", "🛒", "💰", "🎓", "🐾", "🌱", "☕", "⭐", "🔒", "🧩",
];

const SETTINGS_DEFAULTS = {
  theme: "github",
  colorScheme: "system",
  fontSize: 16,
  radius: 18,
  glow: true,
  lang: "ru",
  hover: true,
  hover_scale: 1.05,
  animations: true,
  layout: "grid",
  sort: "created",
  sort_dir: "desc",
  show_favicons: true,
  quicklinks: [],
};

const SETTINGS_KEY = "bms.settings";
const SORT_KEYS = ["created", "title", "visits", "updated"];
const LAYOUT_KEYS = ["rows", "wide", "tiles", "grid"];

const SORT_LABELS = {
  created: "sort.shortCreated",
  title: "sort.shortTitle",
  visits: "sort.shortVisits",
  updated: "sort.shortUpdated",
};

const state = {
  user: null,
  groups: [],
  bookmarks: [],
  tags: [],
  stats: null,
  admin: null, // { summary, users, defaults } — filled in the Admin view
  settings: { ...SETTINGS_DEFAULTS },
  view: { type: "home", groupId: null, tag: null, q: "" },
  loading: false,
  loadingMore: false,
  bookmarksRequest: 0,
  total: 0,
  hasMore: false,
  metaLoading: false,
  draggingBookmark: null,
  draggingGroup: null,
  popoverAnchor: null,
};

const PAGE_SIZE = 100;

let authMode = "login";
let settingsSaveTimer = null;
let metaTimer = null;
let metaRequest = 0;
let lastSessionNotice = 0;

/* ----------------------------- tiny helpers ----------------------------- */

function $(selector, root = document) {
  return root.querySelector(selector);
}

function $$(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

function el(id) {
  return document.getElementById(id);
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] || "";
  const second = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + second).toUpperCase();
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return String(url || "").replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "");
  }
}

function debounce(fn, wait) {
  let timer = null;
  return function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

function plural(base, n) {
  return tp(base, n);
}

/* ----------------------------- dates ----------------------------- */

const dateFormats = new Map();

function dateFormat(long = false) {
  const lang = getLang();
  const key = `${lang}:${long ? "long" : "short"}`;
  let formatter = dateFormats.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-US", long
      ? { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }
      : { day: "numeric", month: "short", year: "numeric" });
    dateFormats.set(key, formatter);
  }
  return formatter;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function fmtDate(value, long = false) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000);
  if (!long && days === 0) return t("common.today");
  if (!long && days === 1) return t("common.yesterday");
  return dateFormat(long).format(date);
}

/* ----------------------------- API ----------------------------- */

class ApiError extends Error {
  constructor(code, status, payload) {
    super(code || "generic");
    this.name = "ApiError";
    this.code = code || "generic";
    this.status = status || 0;
    this.payload = payload || null;
  }
}

async function api(path, options = {}) {
  const init = {
    method: options.method || "GET",
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("network", 0);
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    if (response.status === 401 && state.user) {
      handleUnauthorized();
    }
    throw new ApiError(data?.error || "generic", response.status, data);
  }
  return data || {};
}

function errorText(error) {
  const code = error?.code || "generic";
  const key = `err.${code}`;
  const translated = t(key);
  if (translated !== key) return translated;
  return t("err.generic");
}

function handleUnauthorized() {
  state.user = null;
  state.groups = [];
  state.bookmarks = [];
  state.tags = [];
  state.stats = null;
  showAuth();
  const now = Date.now();
  if (now - lastSessionNotice > 4000) {
    lastSessionNotice = now;
    toast(t("err.unauthorized"), "error");
  }
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to legacy path */
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}

/* ----------------------------- toasts ----------------------------- */

function toast(message, kind = "default", options = {}) {
  const host = el("toasts");
  if (!host) return () => {};
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.innerHTML = `<span class="toast-dot" aria-hidden="true"></span><span class="toast-msg"></span>`;
  $(".toast-msg", node).textContent = message;

  const close = () => {
    if (!node.isConnected) return;
    node.classList.add("leaving");
    setTimeout(() => node.remove(), 230);
  };

  if (options.action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = options.action;
    button.addEventListener("click", async () => {
      close();
      try {
        await options.onAction?.();
      } catch (error) {
        toast(errorText(error), "error");
      }
    });
    node.appendChild(button);
  }

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "toast-close";
  closeButton.setAttribute("aria-label", t("common.close"));
  closeButton.textContent = "✕";
  closeButton.addEventListener("click", close);
  node.appendChild(closeButton);

  host.appendChild(node);
  const duration = options.duration ?? (options.action ? 7000 : 3400);
  setTimeout(close, duration);
  return close;
}

/* ----------------------------- settings ----------------------------- */

function readCachedSettings() {
  try {
    const raw = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
    if (raw && typeof raw === "object") {
      const merged = { ...SETTINGS_DEFAULTS, ...raw };
      /* Migrate pre-1.0.2 values: the old "theme" key doubled as the color scheme. */
      if (merged.theme === "light" || merged.theme === "dark") {
        merged.colorScheme = merged.colorScheme || merged.theme;
        merged.theme = SETTINGS_DEFAULTS.theme;
      } else if (merged.theme === "flexoki") {
        merged.colorScheme = merged.colorScheme || "dark";
      }
      delete merged.accent;
      delete merged.scale;
      return merged;
    }
  } catch {
    /* ignore broken cache */
  }
  return { ...SETTINGS_DEFAULTS };
}

function persistSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
  } catch {
    /* storage may be disabled */
  }
}

function resolvedDark(scheme = state.settings.colorScheme) {
  if (scheme === "dark") return true;
  if (scheme === "light") return false;
  return Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches);
}

function applySettings(options = {}) {
  const { persist = true, resave = true } = options;
  const settings = state.settings;
  const root = document.documentElement;
  const previousLang = getLang();
  const themeName = window.THEMES?.[settings.theme] ? settings.theme : "github";
  const dark = resolvedDark(settings.colorScheme);
  const palette = (window.THEMES?.[themeName] || window.THEMES?.github || {})[dark ? "d" : "l"];

  root.dataset.theme = themeName;
  root.dataset.scheme = dark ? "dark" : "light";
  if (palette && window.THEME_VARS) {
    window.THEME_VARS.forEach((name, i) => root.style.setProperty(name, palette[i]));
  }
  const themeMeta = $('meta[name="theme-color"]');
  if (themeMeta && palette) themeMeta.content = palette[0];
  const colorSchemeMeta = $('meta[name="color-scheme"]');
  if (colorSchemeMeta) colorSchemeMeta.content = dark ? "dark light" : "light dark";

  const fontSize = Math.min(19, Math.max(13, Math.round(Number(settings.fontSize) || 16)));
  root.style.setProperty("--radius", `${Math.round(Number(settings.radius) || 18)}px`);
  root.style.setProperty("--font-size", `${fontSize}px`);
  root.dataset.glow = settings.glow === false ? "off" : "on";
  root.dataset.hover = settings.hover === false ? "off" : "on";
  root.dataset.anim = settings.animations === false ? "off" : "on";
  const hoverScale = Number(settings.hover_scale);
  root.style.setProperty(
    "--card-scale",
    (Number.isFinite(hoverScale) ? Math.min(1.5, Math.max(1, hoverScale)) : 1.05).toFixed(2),
  );
  document.body.classList.toggle("no-favicons", settings.show_favicons === false);

  setLang(settings.lang === "en" ? "en" : "ru");
  root.lang = settings.lang === "en" ? "en" : "ru";

  if (persist) persistSettings();

  const languageChanged = previousLang !== getLang();
  if (languageChanged) {
    localizeStatic();
    renderUser();
    renderSidebar();
    renderHead();
    renderFilters();
    updateSearchMeta();
    renderList();
    renderStatus();
    if (authMode) setAuthMode(authMode);
  }

  if (resave && state.user) scheduleSettingsSave();
}

function scheduleSettingsSave() {
  clearTimeout(settingsSaveTimer);
  settingsSaveTimer = setTimeout(async () => {
    try {
      const result = await api("/settings", { method: "PUT", body: state.settings });
      if (result.settings) {
        state.settings = { ...state.settings, ...result.settings };
        persistSettings();
      }
    } catch (error) {
      if (error.status !== 401) toast(errorText(error), "error");
    }
  }, 420);
}

function localizeStatic() {
  $$("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  $$("[data-i18n-placeholder]").forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  $$("[data-tooltip]").forEach((node) => {
    if (!node.dataset.tip) node.dataset.tip = node.dataset.tooltip;
    if (node.dataset.tip === "literal") return; // dynamic text, not a key
    const key = node.dataset.tip.includes(".") ? node.dataset.tip : `tooltip.${node.dataset.tip}`;
    node.dataset.tip = key;
    node.dataset.tooltip = t(key);
  });
  const authLangBtn = el("authLangBtn");
  if (authLangBtn) authLangBtn.textContent = getLang() === "ru" ? "EN" : "RU";
}



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
  state.admin = null;
  state.view = { type: "home", groupId: null, tag: null, q: "" };
  state.loading = false;
  state.loadingMore = false;
  state.total = 0;
  state.hasMore = false;
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
  if (authMode === "register" && password.length < 8) {
    if (errorBox) {
      errorBox.textContent = t("err.weak_password");
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

function bookmarksParams(offset = 0) {
  const params = viewParams();
  params.set("limit", String(PAGE_SIZE));
  if (offset > 0) params.set("offset", String(offset));
  return params.toString();
}

function renderBookmarkList() {
  renderHead();
  renderFilters();
  updateSearchMeta();
  renderList();
  markNavActive();
}

async function loadBookmarks(options = {}) {
  state.loading = true;
  state.loadingMore = false;
  if (options.skeleton) renderSkeleton();
  // Every load bumps the token: a slow response from a previous view (or a
  // previous keystroke) is dropped instead of overwriting fresher data.
  const requestId = ++state.bookmarksRequest;
  try {
    const result = await api(`/bookmarks?${bookmarksParams(0)}`);
    if (requestId !== state.bookmarksRequest) return;
    state.bookmarks = result.bookmarks || [];
    state.total = Number(result.total) || 0;
    state.hasMore = Boolean(result.has_more);
    renderBookmarkList();
  } catch (error) {
    if (requestId !== state.bookmarksRequest) return;
    if (error.status === 401) return;
    renderError(error);
  } finally {
    if (requestId === state.bookmarksRequest) state.loading = false;
  }
}

async function loadMoreBookmarks() {
  if (state.loading || state.loadingMore || !state.hasMore) return;
  state.loadingMore = true;
  const requestId = ++state.bookmarksRequest;
  try {
    const result = await api(`/bookmarks?${bookmarksParams(state.bookmarks.length)}`);
    if (requestId !== state.bookmarksRequest) return;
    const seen = new Set(state.bookmarks.map((bookmark) => bookmark.id));
    for (const bookmark of result.bookmarks || []) {
      if (!seen.has(bookmark.id)) {
        seen.add(bookmark.id);
        state.bookmarks.push(bookmark);
      }
    }
    state.total = Number(result.total) || state.total;
    state.hasMore = Boolean(result.has_more);
    renderBookmarkList();
  } catch (error) {
    if (requestId !== state.bookmarksRequest) return;
    if (error.status !== 401) toast(errorText(error), "error");
  } finally {
    if (requestId === state.bookmarksRequest) state.loadingMore = false;
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
    admin: view.type === "admin",
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
  // The Admin item is visible only for administrators.
  const adminNav = el("adminNav");
  if (adminNav) adminNav.hidden = !user.is_admin;
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
  if (view.type === "admin") {
    return { title: t("admin.title"), subtitle: t("admin.subtitle"), icon: "🛡️" };
  }
  if (view.type === "tags") {
    return { title: t("tags.title"), subtitle: t("tags.subtitle"), icon: "🏷️" };
  }
  if (view.type === "tag") {
    return {
      title: t("tags.filterTitle", { tag: view.tag || "" }),
      subtitle: tp("links", state.total),
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
  } else if (view.type === "admin") {
    actions.push(
      `<button type="button" class="btn subtle" data-view-action="admin-refresh">↻ <span>${t(
        "admin.refresh",
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
    count.textContent = state.view.q ? t("search.found", { n: state.total }) : "";
  }
  if (clear) clear.hidden = !(el("searchInput")?.value || "").trim();
}



/* ----------------------------- icons ----------------------------- */

const ICON_PATHS = {
  open: '<path d="M7 17 17 7M9 7h8v8"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.2"/><path d="M5 15V5.5A2.5 2.5 0 0 1 7.5 3H15"/>',
  edit: '<path d="m4.5 19.5 4.3-.9L19.2 8.2a2.1 2.1 0 0 0-3-3L5.8 15.6l-1.3 3.9Z"/><path d="m14.5 6.5 3 3"/>',
  flame: '<path d="M12 3c.4 3 2 4.2 3.4 6.1A6.4 6.4 0 0 1 17 13a5 5 0 0 1-10 .2c0-1.7.7-3 1.8-4.2.3 1 .9 1.8 1.7 2.2.1-3 .8-5.6 1.5-8.2Z"/>',
  trash: '<path d="M4 7h16M9.5 7V4h5v3M6.4 7l.9 13h9.4l.9-13"/><path d="M10 11v5.5M14 11v5.5"/>',
  restore: '<path d="M4.5 10a7.5 7.5 0 1 1 2.3 7.4"/><path d="M4.2 4.2v6h6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  add: '<path d="M12 5v14M5 12h14"/>',
};

function svgIcon(name, size = 16) {
  return `<svg class="ico" viewBox="0 0 24 24" width="${size}" height="${size}"
    fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
    stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}

/* ----------------------------- cards ----------------------------- */

function tagChips(tags) {
  if (!tags || !tags.length) return "";
  return `<span class="card-tags">${tags
    .map(
      (tag) =>
        `<button type="button" class="tag-chip" data-action="tag" data-tag="${esc(
          tag,
        )}">#${esc(tag)}</button>`,
    )
    .join("")}</span>`;
}

function renderCard(bookmark) {
  const trashed = Boolean(bookmark.deleted_at);
  const fav = Boolean(bookmark.favorited);
  const isFavoritesCopy = bookmark.group_kind === "favorites";
  const title = bookmark.title || t("add.untitled");
  const host = hostOf(bookmark.url);
  const dateValue = trashed ? bookmark.deleted_at : bookmark.created_at;
  const dateLabel = trashed
    ? t("bookmark.deletedAt", { date: fmtDate(dateValue) })
    : t("bookmark.added", { date: fmtDate(dateValue) });
  const visits = Number(bookmark.visits) || 0;
  let favicon = "";
  if (state.settings.show_favicons !== false) {
    if (bookmark.icon) {
      favicon = `<img class="card-favicon card-favicon-custom" src="${bookmark.icon}" alt="" loading="lazy" decoding="async">`;
    } else {
      favicon = `<img class="card-favicon" src="/api/icon?u=${encodeURIComponent(
        bookmark.url,
      ).replaceAll("'", "%27")}" alt="" loading="lazy" decoding="async">`;
    }
  }
  const showGroup = state.view.type === "home" || state.view.type === "search";

  const titleNode = trashed
    ? `<span class="card-title" title="${esc(title)}">${esc(title)}</span>`
    : `<a class="card-title" href="/go/${bookmark.id}" target="_blank" rel="noopener noreferrer"
        title="${esc(title)}">${esc(title)}</a>`;

  const actions = trashed
    ? `<button type="button" class="card-action" data-action="restore" title="${esc(
        t("common.restore"),
      )}" aria-label="${esc(t("common.restore"))}">${svgIcon("restore")}</button>
       <button type="button" class="card-action" data-action="copy" title="${esc(
         t("bookmark.copyTitle"),
       )}" aria-label="${esc(t("bookmark.copyTitle"))}">${svgIcon("copy")}</button>
       <button type="button" class="card-action danger" data-action="purge" title="${esc(
         t("trash.deleteForever"),
       )}" aria-label="${esc(t("trash.deleteForever"))}">${svgIcon("trash")}</button>`
    : `<button type="button" class="card-action ${fav ? "is-fav" : ""}" data-action="favorite"
        title="${esc(fav ? t("bookmark.unfavorite") : t("bookmark.favorite"))}"
        aria-label="${esc(fav ? t("bookmark.unfavorite") : t("bookmark.favorite"))}"
        aria-pressed="${fav}">${svgIcon("flame")}</button>
       <button type="button" class="card-action" data-action="copy" title="${esc(
         t("bookmark.copyTitle"),
       )}" aria-label="${esc(t("bookmark.copyTitle"))}">${svgIcon("copy")}</button>
       <button type="button" class="card-action" data-action="edit" title="${esc(
         t("common.edit"),
       )}" aria-label="${esc(t("common.edit"))}">${svgIcon("edit")}</button>
       <button type="button" class="card-action danger" data-action="delete" title="${esc(
         t("bookmark.deleteAction"),
       )}" aria-label="${esc(t("bookmark.deleteAction"))}">${svgIcon("trash")}</button>`;

  return `<article class="card ${bookmark.pinned ? "pinned" : ""} ${fav ? "favorited" : ""} ${
    isFavoritesCopy ? "favorites-copy" : ""
  } ${trashed ? "trashed" : ""}" data-bookmark-id="${bookmark.id}">
    <div class="card-icon" aria-hidden="true">
      ${favicon}
      <span class="card-fallback">${esc((host || "?").slice(0, 1).toUpperCase())}</span>
    </div>
    <div class="card-main">
      <div class="card-title-row">
        ${titleNode}
        ${bookmark.pinned ? `<span class="card-pin" title="${esc(t("bookmark.pinned"))}">📌</span>` : ""}
      </div>
      <div class="card-desc ${bookmark.description ? "" : "is-empty"}">${esc(
        bookmark.description || t("bookmark.noDescription"),
      )}</div>
      <div class="card-meta">
        <span class="card-host" title="${esc(bookmark.url)}">${esc(host)}</span>
        ${
          showGroup && bookmark.group_name
            ? `<span class="card-group">${esc(bookmark.group_icon || "📁")} ${esc(
                bookmark.group_kind === "favorites" ? t("sidebar.favorites") : bookmark.group_name,
              )}</span>`
            : ""
        }
        <span class="card-date">${esc(dateLabel)}</span>
        ${
          visits
            ? `<span class="card-visits">👁 ${esc(tp("visits", visits))}</span>`
            : ""
        }
        ${tagChips(bookmark.tags)}
      </div>
    </div>
    <div class="card-actions">${actions}</div>
  </article>`;
}

function renderSkeleton() {
  const list = el("list");
  if (!list) return;
  list.className = `list view-${state.settings.layout}`;
  list.innerHTML = Array.from(
    { length: 6 },
    () => `<div class="skel-card" aria-hidden="true">
      <span class="skel skel-icon"></span>
      <div class="skel-lines">
        <span class="skel skel-title"></span>
        <span class="skel skel-text"></span>
        <span class="skel skel-meta"></span>
      </div>
    </div>`,
  ).join("");
}

function emptyState(kind) {
  const view = state.view;
  let icon = "🗂️";
  let title = t("home.emptyTitle");
  let hint = t("home.emptyHint");
  let action = `<button type="button" class="btn primary" data-action="focus-add">➕ ${t(
    "home.emptyAction",
  )}</button>`;

  if (view.type === "search") {
    icon = "🔍";
    title = t("search.none");
    hint = t("search.noneHint");
    action = `<button type="button" class="btn" data-action="search-add">➕ ${esc(
      t("search.addLink", { q: view.q || "" }),
    )}</button>`;
  } else if (view.type === "favorites") {
    icon = "🔥";
    title = t("favorites.empty");
    hint = t("favorites.emptyHint");
    action = "";
  } else if (view.type === "trash") {
    icon = "🗑️";
    title = t("trash.empty");
    hint = t("trash.emptyHint");
    action = "";
  } else if (view.type === "tags" || view.type === "tag") {
    icon = "🏷️";
    title = t("tags.empty");
    hint = t("tags.emptyHint");
    action = "";
  } else if (view.type === "group") {
    icon = "📁";
    title = t("group.empty");
    hint = t("group.emptyHint");
    action = `<button type="button" class="btn primary" data-action="focus-add">➕ ${t(
      "group.addLink",
    )}</button>`;
  } else if (kind === "error") {
    icon = "⚠️";
    title = t("common.error");
    hint = t("err.network");
    action = `<button type="button" class="btn" data-action="retry">↻ ${t("common.retry")}</button>`;
  }

  return `<div class="empty-state">
    <span class="empty-ico" aria-hidden="true">${icon}</span>
    <h2>${esc(title)}</h2>
    <p>${esc(hint)}</p>
    ${action}
  </div>`;
}

function renderTagCloud() {
  if (!state.tags.length) return emptyState("tags");
  const tiles = state.tags
    .map(
      (tag) => `<div class="tag-tile" data-name="${esc(tag.name.toLowerCase())}">
        <button type="button" class="tag-main" data-action="tag" data-tag="${esc(tag.name)}">
          <span class="tag-hash">#</span>
          <span class="tag-name">${esc(tag.name)}</span>
          <span class="tag-count">${tag.count}</span>
        </button>
        <button type="button" class="tag-del" data-delete-tag="${tag.id}"
          data-tag-name="${esc(tag.name)}" title="${esc(t("tags.delete"))}"
          aria-label="${esc(t("tags.delete"))}">✕</button>
      </div>`,
    )
    .join("");
  return `<div class="tag-cloud-wrap">
      <div class="tag-search">
        <span aria-hidden="true">🔍</span>
        <input id="tagSearch" type="search" autocomplete="off" placeholder="${esc(
          t("tags.search"),
        )}" aria-label="${esc(t("tags.search"))}">
      </div>
      <div class="tag-cloud">${tiles}</div>
    </div>`;
}

/* ------------------------------------------------------------------ *
 *  Admin panel: server statistics and the user directory
 * ------------------------------------------------------------------ */

function fmtBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const en = state.settings?.lang === "en";
  const units = en ? ["KB", "MB", "GB"] : ["КБ", "МБ", "ГБ"];
  let value = n / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function fmtUptime(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const en = state.settings?.lang === "en";
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return en ? `${d}d ${h}h` : `${d} дн ${h} ч`;
  if (h > 0) return en ? `${h}h ${m}m` : `${h} ч ${m} мин`;
  return en ? `${m}m` : `${m} мин`;
}

async function loadAdmin() {
  if (!state.user?.is_admin) {
    navigateHome();
    return;
  }
  try {
    const [summary, usersResult] = await Promise.all([api("/admin/summary"), api("/admin/users")]);
    state.admin = {
      summary,
      users: usersResult.users || [],
      defaults: usersResult.defaults || {},
    };
    renderBookmarkList();
  } catch (error) {
    if (error.status === 401) return;
    renderError(error);
  }
}

function adminUserById(id) {
  return (state.admin?.users || []).find((user) => Number(user.id) === Number(id)) || null;
}

function renderAdminCards() {
  const s = state.admin?.summary;
  if (!s) return "";
  const cards = [
    { icon: "👥", label: t("admin.card.users"), value: s.users_total, extra: s.users_disabled ? ` · ${s.users_disabled} ${state.settings?.lang === "en" ? "blocked" : "заблок."}` : "" },
    { icon: "📈", label: t("admin.card.active"), value: s.users_active_30d },
    { icon: "🔗", label: t("admin.card.links"), value: s.bookmarks },
    { icon: "🗑️", label: t("admin.card.trash"), value: s.trash },
    { icon: "📁", label: t("admin.card.groups"), value: s.groups },
    { icon: "🏷️", label: t("admin.card.tags"), value: s.tags },
    { icon: "🗄️", label: t("admin.card.db"), value: fmtBytes(s.db_size_bytes) },
    { icon: "⏱️", label: t("admin.card.uptime"), value: fmtUptime(s.uptime_seconds) },
  ];
  return `<div class="admin-cards">` +
    cards.map((card) => `<div class="admin-card">
      <span class="admin-card-ico" aria-hidden="true">${card.icon}</span>
      <span class="admin-card-label">${esc(card.label)}</span>
      <span class="admin-card-value">${esc(card.value)}${card.extra ? `<small>${esc(card.extra)}</small>` : ""}</span>
    </div>`).join("") +
    `</div>`;
}

function renderAdminRow(user) {
  const me = Number(user.id) === Number(state.user?.id);
  const en = state.settings?.lang === "en";
  const role = user.is_admin ? t("admin.role.admin") : t("admin.role.user");
  const status = user.disabled ? t("admin.status.blocked") : t("admin.status.active");
  const custom = user.custom_limits || {};
  const limits = [custom.bookmarks ?? "—", custom.tags ?? "—", custom.groups ?? "—"].join(" / ");
  const lastLogin = user.last_login ? fmtDate(user.last_login) : "—";
  const created = user.created_at ? fmtDate(user.created_at) : "—";
  const actions = me
    ? `<span class="admin-me">${esc(t("admin.me"))}</span>`
    : `<button type="button" class="btn subtle sm" data-action="admin-settings" data-user-id="${user.id}" title="${esc(t("admin.actions.settings"))}">⚙️</button>
       <button type="button" class="btn subtle sm" data-action="admin-password" data-user-id="${user.id}" title="${esc(t("admin.actions.password"))}">🔄</button>`;
  return `<div class="admin-row" data-user-id="${user.id}">
    <div class="admin-row-main">
      <span class="admin-row-user">
        <span class="avatar sm" style="--avatar-color:${esc(user.avatar_color || "#5b7cfa")}">${esc((user.display_name || user.username || "?").slice(0, 1).toUpperCase())}</span>
        <span class="admin-row-name">
          <strong>${esc(user.display_name || user.username)}${user.is_admin ? ' <span class="admin-badge">🛡️</span>' : ""}</strong>
          <small>@${esc(user.username)}${me ? ` · ${en ? "you" : "вы"}` : ""}</small>
        </span>
      </span>
      <span class="admin-row-meta">${esc(role)} · <span class="${user.disabled ? "admin-status-blocked" : "admin-status-active"}">${esc(status)}</span></span>
    </div>
    <div class="admin-cell"><span class="admin-cell-label">${esc(t("admin.col.usage"))}</span>
      <span>${esc(t("admin.usageFmt", { bookmarks: user.bookmarks, tags: user.tags, groups: user.groups }))}</span></div>
    <div class="admin-cell"><span class="admin-cell-label">${esc(t("admin.col.limits"))}</span>
      <span class="admin-limits">${esc(limits)}</span>
      <small>${limits.includes("—") ? esc(t("admin.limitDefault")) : ""}</small></div>
    <div class="admin-cell"><span class="admin-cell-label">${esc(t("admin.col.lastLogin"))}</span>
      <span>${esc(lastLogin)}</span><small>${esc(created)}</small></div>
    <div class="admin-cell admin-cell-actions">${actions}</div>
  </div>`;
}

function renderAdminPanel() {
  if (!state.admin) return emptyState("error");
  return `${renderAdminCards()}
    <div class="admin-table-wrap">
      <div class="admin-table-head">
        <span>${esc(t("admin.tableTitle"))}</span>
        <span class="admin-table-count">${state.admin.users.length}</span>
      </div>
      <div class="admin-table">
        <div class="admin-table-col">
          <span>${esc(t("admin.col.user"))}</span><span>${esc(t("admin.col.role"))} / ${esc(t("admin.col.status"))}</span>
        </div>
        <div class="admin-table-col"><span>${esc(t("admin.col.usage"))}</span></div>
        <div class="admin-table-col"><span>${esc(t("admin.col.limits"))}</span></div>
        <div class="admin-table-col"><span>${esc(t("admin.col.lastLogin"))}</span></div>
        <div class="admin-table-col admin-table-col-actions"><span>${esc(t("admin.col.actions"))}</span></div>
      </div>
      ${state.admin.users.map(renderAdminRow).join("")}
    </div>`;
}

function renderList() {
  const list = el("list");
  if (!list) return;
  if (state.view.type === "admin") {
    list.className = "list admin-mode";
    list.innerHTML = renderAdminPanel();
    return;
  }
  if (state.view.type === "tags" && !state.view.tag) {
    list.className = "list tags-mode";
    list.innerHTML = renderTagCloud();
    return;
  }
  list.className = `list view-${state.settings.layout}`;
  if (state.view.type === "trash") list.classList.add("is-trash");
  if (!state.bookmarks.length) {
    list.innerHTML = emptyState();
    return;
  }
  const remaining = Math.max(0, state.total - state.bookmarks.length);
  const more = state.hasMore
    ? `<div class="load-more">
        <button type="button" class="btn" data-action="more"${state.loadingMore ? " disabled" : ""}>
          ${state.loadingMore ? "···" : `↻ ${esc(t("list.loadMore", { n: remaining }))}`}
        </button>
      </div>`
    : "";
  list.innerHTML = state.bookmarks.map(renderCard).join("") + more;
}

function renderError(error) {
  const list = el("list");
  if (list) {
    list.className = "list";
    list.innerHTML = emptyState("error");
  }
  const info = el("viewHead");
  if (info) info.innerHTML = "";
  const filters = el("filters");
  if (filters) filters.hidden = true;
  if (error && error.status !== 401) {
    /* Keep a toast for the first failure so the message is visible. */
    if (!list?.dataset.errorShown) {
      if (list) list.dataset.errorShown = "1";
      toast(errorText(error), "error");
    }
  }
}

/* ----------------------------- add group select ----------------------------- */

function syncAddGroupSelect(forceValue) {
  const select = el("addGroupSelect");
  if (!select) return;
  const previous = forceValue !== undefined ? String(forceValue) : select.value;
  const previousExists = state.groups.some((group) => String(group.id) === previous);
  let selected = previousExists ? previous : "";
  if (!previousExists && !forceValue) {
    const view = state.view;
    if (view.type === "group" && view.groupId) selected = String(view.groupId);
    if (view.type === "favorites") {
      const favorites = state.groups.find((group) => group.kind === "favorites");
      if (favorites) selected = String(favorites.id);
    }
  }
  select.innerHTML = groupOptions(selected);
}



/* ----------------------------- navigation ----------------------------- */

function closeSidebar() {
  el("app")?.classList.remove("sidebar-open");
  const backdrop = el("sidebarBackdrop");
  if (backdrop) backdrop.hidden = true;
}

function openSidebar() {
  el("app")?.classList.add("sidebar-open");
  const backdrop = el("sidebarBackdrop");
  if (backdrop) backdrop.hidden = false;
}

function hideSearchPanel(clear = true) {
  const panel = el("searchPanel");
  if (panel) panel.hidden = true;
  if (clear) {
    const input = el("searchInput");
    if (input) input.value = "";
    state.view.q = "";
    const clearBtn = el("searchClear");
    if (clearBtn) clearBtn.hidden = true;
  }
}

async function navigate(view, options = {}) {
  state.view = { type: view.type || "home", groupId: view.groupId ?? null, tag: view.tag ?? null, q: view.q ?? "" };
  if (state.view.type !== "search") hideSearchPanel();
  if (state.view.type === "group" && state.view.groupId != null) {
    syncAddGroupSelect(state.view.groupId);
  } else if (state.view.type === "favorites") {
    const favorites = state.groups.find((group) => group.kind === "favorites");
    if (favorites) syncAddGroupSelect(favorites.id);
  }
  renderHead();
  renderFilters();
  updateSearchMeta();
  markNavActive();
  closeSidebar();
  closePopover();
  if (state.view.type === "admin") {
    await loadAdmin();
    return;
  }
  await loadBookmarks({ skeleton: options.skeleton !== false });
}

function navigateHome() {
  return navigate({ type: "home" });
}

function navigateGroup(groupId) {
  return navigate({ type: "group", groupId });
}

function navigateFavorites() {
  return navigate({ type: "favorites" });
}

function navigateTrash() {
  return navigate({ type: "trash" });
}

function navigateTags() {
  return navigate({ type: "tags" });
}

function navigateTag(name) {
  return navigate({ type: "tag", tag: name });
}

function navigateAdmin() {
  if (!state.user?.is_admin) return navigateHome();
  return navigate({ type: "admin" });
}

/* ----------------------------- search ----------------------------- */

function openSearch(options = {}) {
  const panel = el("searchPanel");
  if (panel) panel.hidden = false;
  const input = el("searchInput");
  if (state.view.type !== "search") {
    state.view = { type: "search", groupId: null, tag: null, q: input?.value.trim() || "" };
  }
  renderHead();
  renderFilters();
  markNavActive();
  loadBookmarks({ skeleton: false });
  if (options.focus !== false) {
    setTimeout(() => {
      try {
        input?.focus({ preventScroll: true });
        input?.select();
      } catch {
        /* ignore */
      }
    }, 40);
  }
}

function runSearch() {
  const input = el("searchInput");
  const q = (input?.value || "").trim();
  state.view = { type: "search", groupId: null, tag: null, q };
  renderHead();
  renderFilters();
  updateSearchMeta();
  markNavActive();
  loadBookmarks({ skeleton: false });
}

const runSearchDebounced = debounce(runSearch, 260);

function clearSearch() {
  const input = el("searchInput");
  if (input) {
    input.value = "";
    input.focus();
  }
  runSearch();
}

/* ----------------------------- quick add ----------------------------- */

function focusAdd(options = {}) {
  const dialog = el("addDialog");
  const urlInput = el("addUrl");
  if (!dialog || !urlInput) return;
  if (!dialog.open) {
    syncAddGroupSelect();
    dialog.showModal();
  }
  if (options.url !== undefined) urlInput.value = options.url;
  if (options.title !== undefined) {
    const titleInput = el("addTitle");
    if (titleInput) titleInput.value = options.title;
  }
  setTimeout(() => {
    try {
      urlInput.focus();
      urlInput.select();
    } catch {
      /* ignore */
    }
  }, 60);
}

function fetchUrl(raw) {
  const value = String(raw || "").trim();
  if (!value) return null;
  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`;
  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (!parsed.hostname.includes(".") && parsed.hostname !== "localhost") return null;
    return parsed.toString();
  } catch {
    return null;
  }
}

function setFetchBadge(stateName, text = "") {
  const badge = el("fetchBadge");
  if (!badge) return;
  badge.hidden = !stateName;
  badge.dataset.state = stateName || "";
  badge.textContent = text;
  badge.title =
    stateName === "loading" ? t("meta.fetching") : stateName === "error" ? t("meta.failed") : t("meta.fetch");
}

async function fetchMetadata() {
  const urlInput = el("addUrl");
  const url = fetchUrl(urlInput?.value);
  if (!url) {
    setFetchBadge("");
    return;
  }
  const requestId = ++metaRequest;
  state.metaLoading = true;
  setFetchBadge("loading", "···");
  try {
    const info = await api(`/metadata?url=${encodeURIComponent(url)}`);
    if (requestId !== metaRequest) return;
    const titleInput = el("addTitle");
    const descInput = el("addDesc");
    if (titleInput && !titleInput.value.trim() && info.title) titleInput.value = info.title;
    if (descInput && !descInput.value.trim() && info.description) descInput.value = info.description;
    setFetchBadge("success", "✓");
    setTimeout(() => {
      if (requestId === metaRequest) setFetchBadge("");
    }, 2600);
  } catch {
    if (requestId === metaRequest) {
      setFetchBadge("error", "!");
      setTimeout(() => {
        if (requestId === metaRequest) setFetchBadge("");
      }, 3200);
    }
  } finally {
    if (requestId === metaRequest) state.metaLoading = false;
  }
}

const fetchMetadataDebounced = debounce(() => {
  const titleInput = el("addTitle");
  if (titleInput && titleInput.value.trim()) return;
  fetchMetadata();
}, 650);

function resetAddForm() {
  ["addUrl", "addTitle", "addDesc", "addTags"].forEach((id) => {
    const input = el(id);
    if (input) input.value = "";
  });
  setFetchBadge("");
  metaRequest += 1;
  state.metaLoading = false;
}

async function submitAdd(event, options = {}) {
  event?.preventDefault();
  const button = el("addSubmit");
  const url = el("addUrl").value.trim();
  if (!url) {
    el("addUrl")?.focus();
    return;
  }
  const payload = {
    url,
    title: el("addTitle").value.trim(),
    description: el("addDesc").value.trim(),
    tags: el("addTags").value.trim(),
    group_id: el("addGroupSelect").value || null,
  };
  if (options.allowDuplicate) payload.allow_duplicate = true;
  setButtonBusy(button, true);
  try {
    await api("/bookmarks", { method: "POST", body: payload });
    const groupId = payload.group_id;
    resetAddForm();
    if (groupId) syncAddGroupSelect(groupId);
    toast(t("add.saved"), "success");
    el("addDialog")?.close();
    await refreshAll();
  } catch (error) {
    if (error.code === "duplicate") {
      const existing = error.payload?.existing || {};
      const groupText = existing.group_name
        ? t("add.duplicateGroup", { group: existing.group_name })
        : "";
      const confirmed = await confirmDialog({
        icon: "🔁",
        title: t("add.duplicate"),
        message: t("add.duplicateHint", {
          title: existing.title || url,
          group: groupText,
        }),
        confirmText: t("add.saveAnyway"),
        danger: false,
      });
      if (confirmed) {
        setButtonBusy(button, false);
        await submitAdd(null, { allowDuplicate: true });
        return;
      }
    } else if (error.status !== 401) {
      toast(errorText(error), "error");
    }
  } finally {
    setButtonBusy(button, false);
  }
}

/* ----------------------------- bookmark actions ----------------------------- */

function findBookmark(id) {
  return state.bookmarks.find((bookmark) => Number(bookmark.id) === Number(id));
}

async function toggleFavorite(bookmark) {
  if (!bookmark) return;
  try {
    const result = await api(`/bookmarks/${bookmark.id}/favorite`, { method: "POST" });
    toast(result.favorited ? t("bookmark.favAdded") : t("bookmark.favRemoved"), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function trashBookmark(bookmark) {
  if (!bookmark) return;
  try {
    await api(`/bookmarks/${bookmark.id}`, { method: "DELETE" });
    toast(t("bookmark.trashed"), "warning", {
      action: t("common.undo"),
      onAction: async () => {
        await api(`/bookmarks/${bookmark.id}/restore`, { method: "POST" });
        toast(t("bookmark.restored"), "success");
        await refreshAll();
      },
    });
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function restoreBookmark(bookmark) {
  if (!bookmark) return;
  try {
    await api(`/bookmarks/${bookmark.id}/restore`, { method: "POST" });
    toast(t("bookmark.restored"), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function purgeBookmark(bookmark) {
  if (!bookmark) return;
  const confirmed = await confirmDialog({
    icon: "🗑️",
    title: t("bookmark.purgeTitle"),
    message: t("bookmark.purgeText", { title: bookmark.title }),
    confirmText: t("trash.deleteForever"),
  });
  if (!confirmed) return;
  try {
    await api(`/bookmarks/${bookmark.id}/purge`, { method: "DELETE" });
    toast(t("bookmark.purged"), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function moveBookmark(bookmark, groupId) {
  if (!bookmark) return;
  const group = state.groups.find((entry) => Number(entry.id) === Number(groupId)) || null;
  if (group && group.kind === "favorites") {
    if (!bookmark.favorited) await toggleFavorite(bookmark);
    return;
  }
  try {
    await api(`/bookmarks/${bookmark.id}`, {
      method: "PATCH",
      body: { group_id: groupId || null },
    });
    toast(t("bookmark.moved"), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function handleCardAction(action, bookmark) {
  if (action === "open") {
    if (bookmark) window.open(`/go/${bookmark.id}`, "_blank", "noopener,noreferrer");
    return;
  }
  if (action === "copy") {
    if (!bookmark) return;
    const ok = await copyText(bookmark.url);
    toast(ok ? t("common.copied") : t("err.generic"), ok ? "success" : "error");
    return;
  }
  if (action === "edit") {
    if (bookmark) openEditDialog(bookmark);
    return;
  }
  if (action === "favorite") {
    await toggleFavorite(bookmark);
    return;
  }
  if (action === "delete") {
    await trashBookmark(bookmark);
    return;
  }
  if (action === "restore") {
    await restoreBookmark(bookmark);
    return;
  }
  if (action === "purge") {
    await purgeBookmark(bookmark);
  }
}

async function emptyTrash() {
  const count = state.stats?.trash || 0;
  const confirmed = await confirmDialog({
    icon: "🗑️",
    title: t("trash.emptyTitle"),
    message: t("trash.emptyText", { n: count }),
    confirmText: t("trash.emptyAction"),
  });
  if (!confirmed) return;
  try {
    await api("/trash/empty", { method: "POST" });
    toast(t("trash.emptyDone"), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function restoreAllTrash() {
  try {
    const result = await api("/trash/restore-all", { method: "POST" });
    toast(t("trash.restoredAll", { n: result.restored || 0 }), "success");
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}

async function moveGroup(groupId, delta) {
  const customs = state.groups.filter(
    (group) => group.kind !== "favorites" && group.kind !== "secret",
  );
  const index = customs.findIndex((group) => Number(group.id) === Number(groupId));
  const target = index + delta;
  if (index < 0 || target < 0 || target >= customs.length) return;
  const reordered = [...customs];
  const [moved] = reordered.splice(index, 1);
  reordered.splice(target, 0, moved);
  await saveGroupOrder(reordered.map((group) => group.id));
}

async function saveGroupOrder(ids) {
  try {
    await api("/groups/reorder", { method: "POST", body: { ids } });
    await refreshAll();
  } catch (error) {
    if (error.status !== 401) toast(errorText(error), "error");
  }
}



/* ----------------------------- popovers ----------------------------- */

function closePopover() {
  const popover = el("popover");
  if (!popover || popover.hidden) return;
  popover.hidden = true;
  popover.innerHTML = "";
  state.popoverAnchor = null;
}

function positionPopover(anchor) {
  const popover = el("popover");
  if (!popover || !anchor) return;
  const rect = anchor.getBoundingClientRect();
  const box = popover.getBoundingClientRect();
  const margin = 8;
  let left = rect.right - box.width;
  if (left < margin) left = margin;
  if (left + box.width > window.innerWidth - margin) left = window.innerWidth - box.width - margin;
  let top = rect.bottom + 7;
  if (top + box.height > window.innerHeight - margin) top = rect.top - box.height - 7;
  if (top < margin) top = margin;
  popover.style.left = `${Math.max(margin, left)}px`;
  popover.style.top = `${Math.max(margin, top)}px`;
}

function openPopover(anchor, html) {
  const popover = el("popover");
  if (!popover || !anchor) return null;
  popover.innerHTML = html;
  popover.hidden = false;
  state.popoverAnchor = anchor;
  positionPopover(anchor);
  return popover;
}

function openSortPopover() {
  const anchor = el("sortBtn");
  const sortOptions = [
    ["created", "🕒", "sort.created"],
    ["title", "🔤", "sort.titleField"],
    ["visits", "👁", "sort.visits"],
    ["updated", "✎", "sort.updated"],
  ];
  const html = `<div class="pop-label">${t("sort.title")}</div>
    ${sortOptions
      .map(
        ([key, icon, label]) => `<button type="button" class="pop-item" data-sort="${key}">
          <span class="pop-ico">${icon}</span><span>${t(label)}</span>
          ${state.settings.sort === key ? '<span class="pop-check">✓</span>' : ""}
        </button>`,
      )
      .join("")}
    <div class="pop-sep"></div>
    <button type="button" class="pop-item" data-sort-dir="desc">
      <span class="pop-ico">↓</span><span>${t("sort.desc")}</span>
      ${state.settings.sort_dir !== "asc" ? '<span class="pop-check">✓</span>' : ""}
    </button>
    <button type="button" class="pop-item" data-sort-dir="asc">
      <span class="pop-ico">↑</span><span>${t("sort.asc")}</span>
      ${state.settings.sort_dir === "asc" ? '<span class="pop-check">✓</span>' : ""}
    </button>`;
  const popover = openPopover(anchor, html);
  if (!popover) return;
  popover.querySelectorAll("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      state.settings.sort = button.dataset.sort;
      renderStatus();
      scheduleSettingsSave();
      closePopover();
      loadBookmarks({ skeleton: false });
    });
  });
  popover.querySelectorAll("[data-sort-dir]").forEach((button) => {
    button.addEventListener("click", () => {
      state.settings.sort_dir = button.dataset.sortDir;
      renderStatus();
      scheduleSettingsSave();
      closePopover();
      loadBookmarks({ skeleton: false });
    });
  });
}

function avatarMarkup(user, className = "avatar") {
  const color = user?.avatar_color || currentAccent();
  if (user?.avatar_photo) {
    return `<img class="${className} avatar-photo" src="${user.avatar_photo}" alt="${esc(
      user?.display_name || user?.username || "",
    )}">`;
  }
  return `<span class="${className}" style="--avatar-color:${esc(color)}">${esc(
    initials(user?.display_name || user?.username || "?"),
  )}</span>`;
}

function openAvatarPopover() {
  const anchor = el("avatarBtn");
  const user = state.user;
  const html = `<div class="pop-profile">
      ${avatarMarkup(user)}
      <div class="pop-profile-text">
        <strong>${esc(user?.display_name || user?.username || "")}</strong>
        <span>@${esc(user?.username || "")}</span>
      </div>
    </div>
    <div class="pop-sep"></div>
    <button type="button" class="pop-item" data-profile>
      <span class="pop-ico">👤</span><span>${t("profile.title")}</span>
    </button>
    <button type="button" class="pop-item" data-settings>
      <span class="pop-ico">⚙️</span><span>${t("settings.title")}</span>
    </button>
    <button type="button" class="pop-item" data-about>
      <span class="pop-ico">🔖</span><span>${t("about.title")}</span>
    </button>
    <div class="pop-sep"></div>
    <button type="button" class="pop-item danger" data-logout>
      <span class="pop-ico">↪</span><span>${t("profile.logout")}</span>
    </button>`;
  const popover = openPopover(anchor, html);
  if (!popover) return;
  $("[data-profile]", popover)?.addEventListener("click", () => {
    closePopover();
    openProfileDialog();
  });
  $("[data-settings]", popover)?.addEventListener("click", () => {
    closePopover();
    openSettings();
  });
  $("[data-about]", popover)?.addEventListener("click", () => {
    closePopover();
    openAboutDialog();
  });
  $("[data-logout]", popover)?.addEventListener("click", () => {
    closePopover();
    doLogout();
  });
}

function openGroupMenu(groupId, anchor) {
  const group = state.groups.find((entry) => Number(entry.id) === Number(groupId));
  if (!group || group.kind === "favorites") return;
  const secret = group.kind === "secret";
  // The Secret group is pinned right after Favorites: it takes part in
  // neither reordering nor deletion.
  const customs = state.groups.filter(
    (entry) => entry.kind !== "favorites" && entry.kind !== "secret",
  );
  const index = customs.findIndex((entry) => Number(entry.id) === Number(group.id));
  const html = `<div class="pop-label">${esc(groupDisplayName(group))}</div>
    <button type="button" class="pop-item" data-group-edit><span class="pop-ico">${
      secret ? "🔐" : "✎"
    }</span><span>${secret ? t("secret.setPassword") : t("common.edit")}</span></button>
    ${
      secret
        ? ""
        : `<button type="button" class="pop-item" data-group-up ${index <= 0 ? "disabled" : ""}>
          <span class="pop-ico">↑</span><span>${t("common.moveUp")}</span></button>
        <button type="button" class="pop-item" data-group-down ${
          index >= customs.length - 1 ? "disabled" : ""
        }><span class="pop-ico">↓</span><span>${t("common.moveDown")}</span></button>
        <div class="pop-sep"></div>
        <button type="button" class="pop-item danger" data-group-delete>
          <span class="pop-ico">🗑</span><span>${t("common.delete")}</span></button>`
    }`;
  const popover = openPopover(anchor, html);
  if (!popover) return;
  $("[data-group-edit]", popover)?.addEventListener("click", () => {
    closePopover();
    if (group.kind === "secret" && !group.unlocked) {
      // The password can only be changed while the group is open.
      openSecretPrompt(group);
      return;
    }
    openGroupDialog(group);
  });
  $("[data-group-up]", popover)?.addEventListener("click", () => {
    closePopover();
    moveGroup(group.id, -1);
  });
  $("[data-group-down]", popover)?.addEventListener("click", () => {
    closePopover();
    moveGroup(group.id, 1);
  });
  $("[data-group-delete]", popover)?.addEventListener("click", () => {
    closePopover();
    deleteGroup(group);
  });
}

/* ----------------------------- settings drawer ----------------------------- */

function rangeStyle(value, min, max) {
  const pct = ((Number(value) - min) / (max - min)) * 100;
  return `--pct:${Math.max(0, Math.min(100, pct)).toFixed(1)}%`;
}

function switchRow(key, labelKey, hintKey = "") {
  const on = state.settings[key] !== false;
  return `<div class="setting-row">
    <div class="setting-text"><strong>${t(labelKey)}</strong>${
      hintKey ? `<small>${t(hintKey)}</small>` : ""
    }</div>
    <button type="button" class="switch" role="switch" aria-checked="${on}"
      data-toggle="${key}" aria-label="${esc(t(labelKey))}"></button>
  </div>`;
}

const THEME_LABELS = {
  aura: "Aura",
  ayu: "Ayu",
  carbonfox: "Carbonfox",
  cobalt2: "Cobalt 2",
  cursor: "Cursor",
  dracula: "Dracula",
  everforest: "Everforest",
  flexoki: "Flexoki",
  catppuccin: "Catppuccin (Mocha)",
  "catppuccin-frappe": "Catppuccin (Frappe)",
  "catppuccin-macchiato": "Catppuccin (Macchiato)",
  github: "GitHub",
  gruvbox: "Gruvbox",
  kanagawa: "Kanagawa",
  material: "Material",
  matrix: "Matrix",
  mercury: "Mercury",
  monokai: "Monokai",
  nightowl: "Night Owl",
  nord: "Nord",
  "one-dark": "One Dark",
  opencode: "OpenCode",
  orng: "Orng",
  "lucent-orng": "Lucent Orng",
  "osaka-jade": "Osaka Jade",
  palenight: "Pale Night",
  rosepine: "Rosé Pine",
  solarized: "Solarized",
  synthwave84: "Synthwave '84",
  tokyonight: "Tokyo Night",
  vercel: "Vercel",
  vesper: "Vesper",
  zenburn: "Zenburn",
};

function openSettings() {
  const settings = state.settings;
  const schemes = [
    ["light", "settings.themeLight"],
    ["dark", "settings.themeDark"],
    ["system", "settings.themeSystem"],
  ];
  const themeName = window.THEMES?.[settings.theme] ? settings.theme : "github";
  const themeNames = window.THEME_NAMES || Object.keys(window.THEMES || {});
  const languages = [
    ["ru", "Русский"],
    ["en", "English"],
  ];
  const html = `${dialogHead("⚙️", t("settings.title"), t("settings.autosave"))}
    <div class="dlg-body">
      <section class="settings-section">
        <h3>${t("settings.appearance")}</h3>
        <div class="setting-stack">
          <div class="setting-stack-head"><strong>${t("settings.colorScheme")}</strong></div>
          <div class="segmented" role="group">
            ${schemes
              .map(
                ([value, label]) =>
                  `<button type="button" data-scheme-option="${value}" class="${
                    settings.colorScheme === value ? "active" : ""
                  }">${t(label)}</button>`,
              )
              .join("")}
          </div>
        </div>
        <div class="setting-stack">
          <div class="setting-stack-head"><strong>${t("settings.theme")}</strong></div>
          <select id="themeSelect" class="theme-select">
            ${themeNames
              .map(
                (name) =>
                  `<option value="${name}" ${name === themeName ? "selected" : ""}>${THEME_LABELS[name] || name}</option>`,
              )
              .join("")}
          </select>
        </div>
        <div class="setting-stack">
          <div class="setting-stack-head">
            <strong>${t("settings.fontSize")}</strong>
            <output id="fontSizeValue">${Math.min(19, Math.max(13, Math.round(Number(settings.fontSize) || 16)))} px</output>
          </div>
          <div class="slider-wrap">
            <span>13</span>
            <input id="settingFontSize" type="range" min="13" max="19" step="1"
              value="${Math.min(19, Math.max(13, Math.round(Number(settings.fontSize) || 16)))}" style="${rangeStyle(
                Math.min(19, Math.max(13, Math.round(Number(settings.fontSize) || 16))),
                13,
                19,
              )}">
            <span>19</span>
          </div>
        </div>
        <div class="setting-stack">
          <div class="setting-stack-head">
            <strong>${t("settings.radius")}</strong>
            <output id="radiusValue">${Math.round(settings.radius)} px</output>
          </div>
          <div class="slider-wrap">
            <span>0</span>
            <input id="settingRadius" type="range" min="0" max="30" step="1"
              value="${Math.round(settings.radius)}" style="${rangeStyle(settings.radius, 0, 30)}">
            <span>30</span>
          </div>
        </div>
        ${switchRow("glow", "settings.glow")}
        ${switchRow("hover", "settings.hover")}
        <div class="setting-stack">
          <div class="setting-stack-head">
            <strong>${t("settings.hover_scale")}</strong>
            <output id="hoverScaleValue">${Number(settings.hover_scale).toFixed(2)}×</output>
          </div>
          <div class="slider-wrap">
            <span>1.00</span>
            <input id="settingHoverScale" type="range" min="1" max="1.5" step="0.01"
              value="${Number(settings.hover_scale).toFixed(2)}" style="${rangeStyle(
                settings.hover_scale,
                1,
                1.5,
              )}">
            <span>1.50</span>
          </div>
          <p class="data-hint">${t("settings.hover_scale_hint")}</p>
        </div>
        ${switchRow("animations", "settings.animations")}
        ${switchRow("show_favicons", "settings.favicons")}
      </section>

      <section class="settings-section">
        <h3>${t("settings.language")}</h3>
        <div class="setting-row">
          <div class="setting-text"><strong>${t("settings.language")}</strong></div>
          <div class="segmented">
            ${languages
              .map(
                ([value, label]) =>
                  `<button type="button" data-lang-option="${value}" class="${
                    settings.lang === value ? "active" : ""
                  }">${label}</button>`,
              )
              .join("")}
          </div>
        </div>
      </section>

      <section class="settings-section">
        <h3>${t("settings.data")}</h3>
        <div class="setting-stack">
          <div class="setting-stack-head"><strong>${t("settings.export")}</strong></div>
          <div class="data-actions">
            <a class="btn" href="/api/export?format=json" download>⤓ ${t("settings.exportJson")}</a>
            <a class="btn" href="/api/export?format=html" download>⤓ ${t("settings.exportHtml")}</a>
          </div>
          <p class="data-hint">${t("settings.exportHint")}</p>
        </div>
        <div class="setting-stack">
          <div class="setting-stack-head"><strong>${t("settings.import")}</strong></div>
          <div class="data-actions">
            <button type="button" class="btn" data-import-pick>⤒ ${t("settings.importFile")}</button>
          </div>
          <input id="importFile" type="file" accept=".json,.html,.htm,application/json,text/html" hidden>
          <p class="data-hint">${t("settings.importHint")}</p>
        </div>
        <div class="setting-stack">
          <div class="data-actions">
            <button type="button" class="btn" data-reset-settings>↺ ${t("settings.reset")}</button>
            <button type="button" class="btn" data-open-about>🔖 ${t("settings.about")}</button>
          </div>
        </div>
      </section>

      <p class="settings-foot-note">${t("settings.autosave")}</p>
    </div>`;

  openDialog(html, {
    drawer: true,
    onMount(dialog) {
      const syncSchemes = () => {
        dialog.querySelectorAll("[data-scheme-option]").forEach((button) => {
          button.classList.toggle("active", button.dataset.schemeOption === state.settings.colorScheme);
        });
      };
      dialog.querySelectorAll("[data-scheme-option]").forEach((button) => {
        button.addEventListener("click", () => {
          state.settings.colorScheme = button.dataset.schemeOption;
          applySettings();
          syncSchemes();
          updateAuthThemeButton();
        });
      });
      const themeSelect = $("#themeSelect", dialog);
      themeSelect?.addEventListener("change", () => {
        if (!window.THEMES?.[themeSelect.value]) return;
        state.settings.theme = themeSelect.value;
        applySettings();
      });
      const fontSize = $("#settingFontSize", dialog);
      const fontSizeValue = $("#fontSizeValue", dialog);
      fontSize?.addEventListener("input", () => {
        state.settings.fontSize = Math.min(19, Math.max(13, Number(fontSize.value)));
        fontSize.style.cssText = rangeStyle(fontSize.value, 13, 19);
        if (fontSizeValue) fontSizeValue.textContent = `${Math.round(fontSize.value)} px`;
        applySettings();
      });
      const radius = $("#settingRadius", dialog);
      const radiusValue = $("#radiusValue", dialog);
      radius?.addEventListener("input", () => {
        state.settings.radius = Number(radius.value);
        radius.style.cssText = rangeStyle(radius.value, 0, 30);
        if (radiusValue) radiusValue.textContent = `${Math.round(radius.value)} px`;
        applySettings();
      });
      const hoverScale = $("#settingHoverScale", dialog);
      const hoverScaleValue = $("#hoverScaleValue", dialog);
      hoverScale?.addEventListener("input", () => {
        state.settings.hover_scale = Math.min(1.5, Math.max(1, Number(hoverScale.value)));
        hoverScale.style.cssText = rangeStyle(hoverScale.value, 1, 1.5);
        if (hoverScaleValue) hoverScaleValue.textContent = `${Number(hoverScale.value).toFixed(2)}×`;
        applySettings();
      });
      dialog.querySelectorAll("[data-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.dataset.toggle;
          const next = button.getAttribute("aria-checked") !== "true";
          button.setAttribute("aria-checked", String(next));
          state.settings[key] = next;
          applySettings();
          if (key === "show_favicons") renderList();
        });
      });
      dialog.querySelectorAll("[data-lang-option]").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.dataset.langOption === state.settings.lang) return;
          state.settings.lang = button.dataset.langOption;
          applySettings();
          openSettings();
        });
      });
      const fileInput = $("#importFile", dialog);
      $("[data-import-pick]", dialog)?.addEventListener("click", () => fileInput?.click());
      fileInput?.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        if (!file) return;
        if (file.size > 12_000_000) {
          toast(t("err.file_too_large"), "error");
          fileInput.value = "";
          return;
        }
        try {
          const content = await file.text();
          const format = /\.html?$/i.test(file.name) ? "html" : "json";
          const result = await api("/import", { method: "POST", body: { format, content } });
          let restored = "";
          // A v2 full backup also restores settings and the profile: sync
          // the local state before the refresh so the new interface applies.
          if (result.settings) state.settings = { ...SETTINGS_DEFAULTS, ...result.settings };
          if (result.user) state.user = { ...state.user, ...result.user };
          if (result.settings || result.user) {
            applySettings({ persist: false, resave: false });
            updateAuthThemeButton();
            restored = ` · ${t("settings.restoreDone")}`;
          }
          toast(
            `${t("settings.importDone")} — ${t("settings.imported", {
              n: result.imported || 0,
              m: result.skipped || 0,
            })}${restored}`,
            "success",
          );
          dialog.close();
          await refreshAll();
        } catch (error) {
          toast(errorText(error), "error");
        } finally {
          fileInput.value = "";
        }
      });
      $("[data-reset-settings]", dialog)?.addEventListener("click", async () => {
        const confirmed = await confirmDialog({
          icon: "↺",
          title: t("settings.resetTitle"),
          message: t("settings.resetText"),
          confirmText: t("settings.reset"),
          danger: false,
        });
        if (!confirmed) {
          // The settings drawer was closed before the confirmation opened;
          // "cancel" means "go back to it", not "leave the settings".
          openSettings();
          return;
        }
        state.settings = { ...SETTINGS_DEFAULTS };
        applySettings();
        updateAuthThemeButton();
        openSettings();
        toast(t("settings.resetDone"), "success");
      });
      $("[data-open-about]", dialog)?.addEventListener("click", () => {
        dialog.close();
        openAboutDialog();
      });
    },
  });
}



/* ----------------------------- drag & drop ----------------------------- */

function clearDropHints() {
  $$("#groupList .group-item.drop-target").forEach((item) => item.classList.remove("drop-target"));
}

function bindDragAndDrop() {
  const list = el("list");
  const groupList = el("groupList");

  list?.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".card[data-bookmark-id]");
    if (!card || state.view.type === "trash") return;
    state.draggingBookmark = Number(card.dataset.bookmarkId);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-bms-bookmark", String(state.draggingBookmark));
      event.dataTransfer.setData("text/plain", findBookmark(state.draggingBookmark)?.url || "");
    }
    requestAnimationFrame(() => card.classList.add("dragging"));
  });

  list?.addEventListener("dragend", () => {
    state.draggingBookmark = null;
    $$("#list .card.dragging").forEach((card) => card.classList.remove("dragging"));
    clearDropHints();
  });

  groupList?.addEventListener("dragstart", (event) => {
    const item = event.target.closest('.group-item[draggable="true"]');
    if (!item) return;
    state.draggingGroup = Number(item.dataset.groupId);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-bms-group", String(state.draggingGroup));
    }
    requestAnimationFrame(() => item.classList.add("dragging"));
  });

  groupList?.addEventListener("dragend", () => {
    state.draggingGroup = null;
    $$("#groupList .group-item.dragging").forEach((item) => item.classList.remove("dragging"));
    clearDropHints();
  });

  groupList?.addEventListener("dragover", (event) => {
    const item = event.target.closest(".group-item");
    if (!item) return;
    if (!state.draggingBookmark && !state.draggingGroup) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    clearDropHints();
    item.classList.add("drop-target");
  });

  groupList?.addEventListener("dragleave", (event) => {
    const item = event.target.closest(".group-item");
    if (!item) return;
    if (!item.contains(event.relatedTarget)) item.classList.remove("drop-target");
  });

  groupList?.addEventListener("drop", async (event) => {
    const item = event.target.closest(".group-item");
    if (!item) return;
    event.preventDefault();
    const targetId = Number(item.dataset.groupId);
    clearDropHints();

    if (state.draggingBookmark) {
      const bookmark = findBookmark(state.draggingBookmark);
      state.draggingBookmark = null;
      if (bookmark) await moveBookmark(bookmark, targetId);
      return;
    }

    if (state.draggingGroup) {
      const draggedId = state.draggingGroup;
      state.draggingGroup = null;
      const customs = state.groups.filter((group) => group.kind !== "favorites");
      const from = customs.findIndex((group) => Number(group.id) === draggedId);
      const to = customs.findIndex((group) => Number(group.id) === targetId);
      if (from < 0 || to < 0 || from === to) return;
      const [moved] = customs.splice(from, 1);
      customs.splice(to, 0, moved);
      await saveGroupOrder(customs.map((group) => group.id));
    }
  });
}

/* ----------------------------- password strength ----------------------------- */

function passwordScore(value) {
  if (!value) return 0;
  let score = 0;
  if (value.length >= 8) score += 1;
  if (value.length >= 12) score += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
  if (/\d/.test(value) || /[^A-Za-z0-9]/.test(value)) score += 1;
  return Math.min(4, score);
}

const STRENGTH_LABELS = ["weak", "weak", "fair", "good", "strong"];

function renderPassStrength(input) {
  const meter = input?.closest(".field-group")?.querySelector(".pass-strength");
  if (!meter) return;
  const value = input.value;
  const score = passwordScore(value);
  meter.hidden = !value;
  meter.classList.remove("s1", "s2", "s3", "s4");
  if (value && score > 0) meter.classList.add(`s${score}`);
  meter.querySelectorAll(".pass-strength-bars span").forEach((bar, i) => {
    bar.classList.toggle("on", i < score);
  });
  const label = meter.querySelector(".pass-strength-label");
  if (label) label.textContent = value ? t(`auth.strength.${STRENGTH_LABELS[score]}`) : "";
}

/* ----------------------------- event binding ----------------------------- */

function bindEvents() {
  /* auth */
  el("authForm")?.addEventListener("submit", submitAuth);
  el("authSwitchBtn")?.addEventListener("click", () => {
    setAuthMode(authMode === "login" ? "register" : "login");
    setTimeout(() => el(authMode === "register" ? "authName" : "authUser")?.focus(), 40);
  });
  el("authEye")?.addEventListener("click", () => {
    const pass = el("authPass");
    const button = el("authEye");
    if (!pass) return;
    const show = pass.type === "password";
    pass.type = show ? "text" : "password";
    if (button) {
      button.textContent = show ? "🙈" : "👁";
      button.title = show ? t("auth.hidePassword") : t("auth.showPassword");
    }
  });
  el("authPass")?.addEventListener("input", () => renderPassStrength(el("authPass")));
  el("authThemeBtn")?.addEventListener("click", () => {
    state.settings.colorScheme = resolvedDark() ? "light" : "dark";
    applySettings({ resave: false });
    updateAuthThemeButton();
  });
  el("authLangBtn")?.addEventListener("click", () => {
    state.settings.lang = getLang() === "ru" ? "en" : "ru";
    applySettings({ resave: false });
    setAuthMode(authMode);
    updateAuthThemeButton();
  });

  /* navigation */
  $$("#mainNav [data-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      const nav = button.dataset.nav;
      if (nav === "home") navigateHome();
      else if (nav === "search") openSearch();
      else if (nav === "trash") navigateTrash();
      else if (nav === "tags") navigateTags();
      else if (nav === "admin") navigateAdmin();
    });
  });
  el("sidebarBrand")?.addEventListener("click", navigateHome);
  el("addGroupBtn")?.addEventListener("click", () => openGroupDialog());

  /* quick links */
  el("quickLinksEdit")?.addEventListener("click", () => openQuickLinksDialog());
  el("quickLinksRow")?.addEventListener("click", (event) => {
    const slot = event.target.closest(".ql-slot");
    if (!slot) return;
    if (slot.dataset.qlEmpty !== undefined) {
      openQuickLinksDialog();
      return;
    }
    const link = quickLinks()[Number(slot.dataset.qlIndex)];
    if (link?.url) window.open(link.url, "_blank", "noopener,noreferrer");
  });

  el("menuBtn")?.addEventListener("click", openSidebar);
  el("sidebarClose")?.addEventListener("click", closeSidebar);
  el("sidebarBackdrop")?.addEventListener("click", closeSidebar);
  el("mobileSearchBtn")?.addEventListener("click", () => {
    closeSidebar();
    openSearch();
  });

  el("groupList")?.addEventListener("click", (event) => {
    const menu = event.target.closest("[data-group-menu]");
    if (menu) {
      event.stopPropagation();
      openGroupMenu(Number(menu.dataset.groupMenu), menu);
      return;
    }
    const item = event.target.closest(".group-item");
    if (!item) return;
    const id = Number(item.dataset.groupId);
    const group = state.groups.find((entry) => Number(entry.id) === id);
    if (!group) return;
    if (group.kind === "favorites") navigateFavorites();
    else if (group.kind === "secret") secretItemClick(group, event);
    else navigateGroup(id);
  });

  el("groupList")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest("button")) return;
    const item = event.target.closest(".group-item");
    if (!item) return;
    event.preventDefault();
    item.click();
  });

  /* search */
  const searchInput = el("searchInput");
  searchInput?.addEventListener("input", () => {
    const clear = el("searchClear");
    if (clear) clear.hidden = !searchInput.value.trim();
    runSearchDebounced();
  });
  searchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });
  el("searchClear")?.addEventListener("click", clearSearch);
  el("searchPanel")?.addEventListener("click", (event) => {
    if (event.target.closest("#searchClear")) return;
    searchInput?.focus();
  });

  /* add dialog */
  const addClose = el("addClose");
  if (addClose) {
    addClose.setAttribute("aria-label", t("common.close"));
    addClose.addEventListener("click", () => el("addDialog")?.close());
  }
  el("addForm")?.addEventListener("submit", (event) => submitAdd(event));
  const addUrl = el("addUrl");
  addUrl?.addEventListener("input", () => {
    if (addUrl.value.trim()) fetchMetadataDebounced();
    else setFetchBadge("");
  });
  addUrl?.addEventListener("paste", () => {
    setTimeout(() => fetchMetadataDebounced(), 120);
  });
  addUrl?.addEventListener("blur", () => {
    const title = el("addTitle");
    if (addUrl.value.trim() && (!title || !title.value.trim()) && !state.metaLoading) {
      fetchMetadata();
    }
  });
  el("addTitle")?.addEventListener("input", () => setFetchBadge(""));

  /* status bar */
  el("sortBtn")?.addEventListener("click", (event) => {
    event.stopPropagation();
    const popover = el("popover");
    if (!popover.hidden && state.popoverAnchor === el("sortBtn")) closePopover();
    else openSortPopover();
  });
  el("avatarBtn")?.addEventListener("click", (event) => {
    event.stopPropagation();
    const popover = el("popover");
    if (!popover.hidden && state.popoverAnchor === el("avatarBtn")) closePopover();
    else openAvatarPopover();
  });
  el("addBtn")?.addEventListener("click", () => focusAdd());
  $$("#layoutSwitch [data-layout]").forEach((button) => {
    button.addEventListener("click", () => {
      state.settings.layout = button.dataset.layout;
      renderStatus();
      renderList();
      scheduleSettingsSave();
    });
  });

  /* view head + filters */
  el("viewHead")?.addEventListener("click", (event) => {
    const calNav = event.target.closest("[data-cal-nav]");
    if (calNav) {
      calOffset = Math.max(-24, Math.min(24, calOffset + (Number(calNav.dataset.calNav) || 0)));
      renderMiniCal();
      return;
    }
    const viewAction = event.target.closest("[data-view-action]");
    if (viewAction) {
      const action = viewAction.dataset.viewAction;
      if (action === "restore-all") restoreAllTrash();
      else if (action === "empty-trash") emptyTrash();
      else if (action === "admin-refresh") loadAdmin();
      else if (action === "edit-group") {
        const group = state.groups.find(
          (entry) => Number(entry.id) === Number(state.view.groupId),
        );
        if (group) openGroupDialog(group);
      }
      return;
    }
    const addAction = event.target.closest('[data-action="focus-add"]');
    if (addAction) focusAdd();
  });

  el("filters")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-filter-clear]");
    if (!chip) return;
    if (chip.dataset.filterClear === "search") {
      const input = el("searchInput");
      if (input) input.value = "";
      runSearch();
      input?.focus();
    } else if (chip.dataset.filterClear === "tag") {
      navigateTags();
    }
  });

  /* bookmark list */
  const list = el("list");
  list?.addEventListener("click", async (event) => {
    const deleteTagButton = event.target.closest("[data-delete-tag]");
    if (deleteTagButton) {
      event.preventDefault();
      event.stopPropagation();
      await deleteTag(Number(deleteTagButton.dataset.deleteTag), deleteTagButton.dataset.tagName);
      return;
    }

    const actionNode = event.target.closest("[data-action]");
    if (actionNode) {
      event.preventDefault();
      event.stopPropagation();
      const action = actionNode.dataset.action;
      if (action === "tag") {
        navigateTag(actionNode.dataset.tag);
        return;
      }
      if (action === "focus-add") {
        focusAdd();
        return;
      }
      if (action === "search-add") {
        const q = state.view.q || "";
        const url = fetchUrl(q);
        focusAdd(url ? { url } : { title: q });
        return;
      }
      if (action === "retry") {
        refreshAll({ skeleton: true });
        return;
      }
      if (action === "more") {
        await loadMoreBookmarks();
        return;
      }
      if (action === "admin-settings" || action === "admin-password") {
        const row = actionNode.closest("[data-user-id]");
        const user = adminUserById(row?.dataset.userId);
        if (action === "admin-settings") openAdminSettings(user);
        else openAdminPassword(user);
        return;
      }
      const card = actionNode.closest("[data-bookmark-id]");
      const bookmark = card ? findBookmark(card.dataset.bookmarkId) : null;
      await handleCardAction(action, bookmark);
      return;
    }

    if (state.view.type !== "trash" && !window.getSelection()?.toString()) {
      const card = event.target.closest(".card[data-bookmark-id]");
      if (!card || event.target.closest("a,button,input,textarea,select")) return;
      window.open(`/go/${card.dataset.bookmarkId}`, "_blank", "noopener,noreferrer");
    }
  });

  list?.addEventListener("input", (event) => {
    if (event.target.id !== "tagSearch") return;
    const query = event.target.value.trim().toLowerCase();
    $$(".tag-tile", list).forEach((tile) => {
      tile.hidden = Boolean(query) && !tile.dataset.name.includes(query);
    });
  });

  /* Favicon state. The host-letter fallback is always rendered under the
     <img>; it must be hidden as soon as the icon has loaded, otherwise it
     shows through transparent favicons (a leftover from the previous icon
     after replacing it with a custom one). Neither "load" nor "error"
     bubbles, so both listeners sit on the list in the capture phase. */
  list?.addEventListener(
    "load",
    (event) => {
      if (event.target.classList?.contains("card-favicon")) {
        event.target.closest(".card-icon")?.classList.add("favicon-loaded");
      }
    },
    true,
  );

  list?.addEventListener(
    "error",
    (event) => {
      if (event.target.classList?.contains("card-favicon")) {
        const icon = event.target.closest(".card-icon");
        icon?.classList.add("favicon-failed");
        icon?.classList.remove("favicon-loaded");
      }
    },
    true,
  );

  /* popovers */
  document.addEventListener("pointerdown", (event) => {
    const popover = el("popover");
    if (!popover || popover.hidden) return;
    if (popover.contains(event.target)) return;
    if (state.popoverAnchor?.contains(event.target)) return;
    closePopover();
  });
  window.addEventListener("resize", closePopover);
  el("listScroll")?.addEventListener("scroll", closePopover, { passive: true });

  /* dialog */
  const dialog = el("dialog");
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  /* drag and drop */
  bindDragAndDrop();

  /* keyboard */
  document.addEventListener("keydown", (event) => {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (state.user && !el("app").hidden) openSearch();
      return;
    }

    const dialogOpen = Boolean(el("dialog")?.open);
    if (dialogOpen) {
      if (mod && event.key === "Enter") {
        event.preventDefault();
        const form = event.target.closest("form") || $("form", el("dialog"));
        form?.requestSubmit();
      }
      return;
    }

    if (mod && event.key === "Enter") {
      const form = event.target.closest("form");
      if (form) {
        event.preventDefault();
        form.requestSubmit();
      }
      return;
    }

    if (event.key === "Escape") {
      if (!el("popover").hidden) {
        closePopover();
        return;
      }
      if (el("app").classList.contains("sidebar-open")) {
        closeSidebar();
        return;
      }
      if (!el("searchPanel").hidden) {
        hideSearchPanel();
        navigateHome();
      }
      return;
    }

    const typing = event.target.closest("input, textarea, select, [contenteditable]");
    if (typing || mod || event.altKey) return;

    if (event.key === "n" || event.key === "N") {
      event.preventDefault();
      focusAdd();
    } else if (event.key === "h" || event.key === "H") {
      event.preventDefault();
      navigateHome();
    } else if (event.key === "/") {
      event.preventDefault();
      openSearch();
    }
  });

  /* system theme */
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (media) {
    const onChange = () => {
      if (state.settings.colorScheme !== "system") return;
      applySettings({ resave: false });
      updateAuthThemeButton();
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }
}

/* ----------------------------- init ----------------------------- */

async function init() {
  state.settings = { ...SETTINGS_DEFAULTS, ...readCachedSettings() };
  bindEvents();
  setAuthMode("login");
  localizeStatic();
  applySettings({ persist: false, resave: false });
  updateAuthThemeButton();
  const authScreen = el("authScreen");
  if (authScreen) authScreen.hidden = false;

  try {
    const me = await api("/auth/me");
    if (me.user) {
      state.user = me.user;
      state.settings = {
        ...SETTINGS_DEFAULTS,
        ...state.settings,
        ...(me.user.settings || {}),
      };
      applySettings({ persist: true, resave: false });
      await enterApp();
    } else {
      showAuth();
    }
  } catch (error) {
    showAuth();
    if (error.code === "network") toast(t("err.network"), "error");
  }
}

init();

/* --------------------------------------------------------------------------
   Dialogs
   -------------------------------------------------------------------------- */

function dialogHead(icon, title, subtitle = "") {
  return `<div class="dlg-head">
    <div class="dlg-head-text">
      <h2><span aria-hidden="true">${esc(icon)}</span><span>${esc(title)}</span></h2>
      ${subtitle ? `<p>${esc(subtitle)}</p>` : ""}
    </div>
    <button type="button" class="icon-btn" data-close aria-label="${t("common.close")}">✕</button>
  </div>`;
}

let dialogSeq = 0;

function openDialog(html, options = {}) {
  const dialog = el("dialog");
  const seq = ++dialogSeq;
  const show = () => {
    if (seq !== dialogSeq) return; // a newer openDialog call has taken over
    dialog.className = `dialog${options.drawer ? " drawer" : ""}${
      options.className ? ` ${options.className}` : ""
    }`;
    dialog.innerHTML = html;
    dialog.showModal();
    dialog.querySelectorAll("[data-close]").forEach((button) => {
      button.addEventListener("click", () => dialog.close());
    });
    if (options.onMount) options.onMount(dialog);
    const focusable = dialog.querySelector(
      "[autofocus], .dlg-body input:not([type=checkbox]):not([type=hidden]), .dlg-body textarea, .dlg-body select",
    );
    if (focusable) {
      setTimeout(() => {
        try {
          focusable.focus({ preventScroll: true });
        } catch {
          /* ignore */
        }
      }, 60);
    }
  };
  if (dialog.open) {
    dialog.close();
    // The `close` event is delivered asynchronously (as a task). Wait for it
    // to land before mounting the new content: otherwise the stale close
    // event of the previous content is delivered to the new listeners. That
    // broke confirmDialog opened on top of another dialog (e.g. "reset
    // settings" from the settings drawer): its auto-resolve `close`
    // listener consumed the stale event, so by the time the user pressed
    // "OK" or "Cancel" the promise was already settled and the buttons
    // did nothing.
    dialog.addEventListener("close", show, { once: true });
  } else {
    show();
  }
  return dialog;
}

function setButtonBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  const spinner = $(".btn-spinner", button);
  if (spinner) spinner.hidden = !busy;
}

function dialogError(dialog, message) {
  const box = $(".form-error", dialog);
  if (!box) return;
  box.textContent = message;
  box.hidden = false;
}

function confirmDialog(options = {}) {
  const {
    title = t("confirm.title"),
    message = "",
    confirmText = t("common.confirm"),
    icon = "⚠️",
    danger = true,
  } = options;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
      const dialog = el("dialog");
      if (dialog.open) dialog.close();
    };
    openDialog(
      `${dialogHead(icon, title)}
       <div class="dlg-body">
         <p class="confirm-text">${esc(message)}</p>
       </div>
       <div class="dlg-foot">
         <button type="button" class="btn" data-confirm-cancel>${t("common.cancel")}</button>
         <button type="button" class="btn ${danger ? "danger" : "primary"}" data-confirm-ok>${esc(
           confirmText,
         )}</button>
       </div>`,
      {
        onMount(dialog) {
          $("[data-confirm-ok]", dialog)?.addEventListener("click", () => finish(true));
          $("[data-confirm-cancel]", dialog)?.addEventListener("click", () => finish(false));
          dialog.addEventListener(
            "close",
            () => {
              if (!settled) {
                settled = true;
                resolve(false);
              }
            },
            { once: true },
          );
        },
      },
    );
  });
}

function groupOptions(selectedId) {
  const options = [`<option value="">${esc(t("add.noGroup"))}</option>`];
  state.groups.forEach((group) => {
    let name = group.name;
    let icon = group.icon || "📁";
    if (group.kind === "favorites") {
      name = t("sidebar.favorites");
      icon = "🔥";
    } else if (group.kind === "secret") {
      name = t("sidebar.secret");
      icon = group.unlocked ? "🔓" : "🔐";
    }
    options.push(
      `<option value="${group.id}" ${String(group.id) === String(selectedId) ? "selected" : ""}>${esc(
        `${icon}  ${name}`,
      )}</option>`,
    );
  });
  return options.join("");
}

/* ----------------------------- edit link ----------------------------- */

function openEditDialog(bookmark) {
  openDialog(
    `<form id="editForm" class="dialog-form">
      ${dialogHead("✎", t("bookmark.editTitle"), hostOf(bookmark.url))}
      <div class="dlg-body">
        <div class="form-grid">
          <div class="field-group">
            <label for="editUrl">${t("bookmark.url")}</label>
            <input id="editUrl" value="${esc(bookmark.url)}" required>
          </div>
          <div class="field-group">
            <label for="editTitle">${t("bookmark.name")}</label>
            <input id="editTitle" maxlength="300" value="${esc(bookmark.title)}">
          </div>
          <div class="field-group">
            <label for="editDesc">${t("bookmark.description")}</label>
            <textarea id="editDesc" rows="3" maxlength="2000">${esc(bookmark.description)}</textarea>
          </div>
          <div class="form-row">
            <div class="field-group">
              <label for="editTags">${t("bookmark.tags")}</label>
              <input id="editTags" maxlength="300" value="${esc(bookmark.tags.join(", "))}"
                placeholder="${esc(t("bookmark.tagsPlaceholder"))}">
            </div>
            <div class="field-group">
              <label for="editGroup">${t("bookmark.group")}</label>
              <select id="editGroup">${groupOptions(bookmark.group_id)}</select>
            </div>
          </div>
          <div class="setting-row pin-row">
            <div class="setting-text">
              <strong>${t("bookmark.pinAction")}</strong>
            </div>
            <button type="button" class="switch" id="editPinned" role="switch"
              aria-checked="${bookmark.pinned}" aria-label="${t("bookmark.pinAction")}"></button>
          </div>
          <div class="field-group">
            <label>${t("bookmark.icon")}</label>
            <div class="file-row">
              <span class="file-thumb" id="editIconThumb" hidden></span>
              <input type="file" id="editIconFile" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml,image/x-icon" hidden>
              <button type="button" class="btn" id="editIconBrowse">${t("bookmark.iconChoose")}</button>
              <button type="button" class="btn danger" id="editIconClear" hidden>${t("bookmark.iconRemove")}</button>
              <span class="hint">${t("bookmark.iconHint")}</span>
            </div>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn danger" data-delete-bookmark>${t(
          "bookmark.deleteAction",
        )}</button>
        <span class="spacer"></span>
        <button type="button" class="btn" data-close>${t("common.cancel")}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${t("common.save")}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        let pinned = bookmark.pinned;
        const pinButton = $("#editPinned", dialog);
        pinButton?.addEventListener("click", () => {
          pinned = !pinned;
          pinButton.setAttribute("aria-checked", String(pinned));
        });
        $("[data-delete-bookmark]", dialog)?.addEventListener("click", () => {
          dialog.close();
          trashBookmark(bookmark);
        });
        let iconValue = bookmark.icon || null;
        const iconThumb = $("#editIconThumb", dialog);
        const iconClear = $("#editIconClear", dialog);
        const iconFile = $("#editIconFile", dialog);
        const syncIconUI = () => {
          if (iconValue) {
            iconThumb.innerHTML = `<img src="${iconValue}" alt="">`;
            iconThumb.hidden = false;
            iconClear.hidden = false;
          } else {
            iconThumb.hidden = true;
            iconClear.hidden = true;
          }
        };
        $("#editIconBrowse", dialog)?.addEventListener("click", () => iconFile?.click());
        iconFile?.addEventListener("change", () => {
          const file = iconFile.files && iconFile.files[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = () => {
            iconValue = String(reader.result);
            syncIconUI();
          };
          reader.readAsDataURL(file);
        });
        iconClear?.addEventListener("click", () => {
          iconValue = null;
          iconFile.value = "";
          syncIconUI();
        });
        syncIconUI();
        $("#editForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter || $('button[type="submit"]', dialog);
          const errorBox = $(".form-error", dialog);
          if (errorBox) errorBox.hidden = true;
          setButtonBusy(button, true);
          try {
            await api(`/bookmarks/${bookmark.id}`, {
              method: "PATCH",
              body: {
                url: $("#editUrl", dialog).value.trim(),
                title: $("#editTitle", dialog).value.trim(),
                description: $("#editDesc", dialog).value.trim(),
                tags: $("#editTags", dialog).value.trim(),
                group_id: $("#editGroup", dialog).value || null,
                pinned,
                icon: iconValue,
              },
            });
            dialog.close();
            toast(t("bookmark.updated"), "success");
            await refreshAll({ skeleton: false });
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

/* ----------------------------- secret group ----------------------------- */

function patchGroup(group, patch) {
  const entry = state.groups.find((item) => Number(item.id) === Number(group.id));
  if (entry) Object.assign(entry, patch);
  renderSidebar();
}

function secretItemClick(group, event) {
  const toggle = event.target.closest("[data-secret-toggle]");
  if (toggle) {
    event.stopPropagation();
    secretToggle(group);
    return;
  }
  if (!group.unlocked) openSecretPrompt(group);
  else navigateGroup(group.id);
}

async function secretToggle(group) {
  if (!group.unlocked) {
    openSecretPrompt(group);
    return;
  }
  if (!group.password_set) {
    // The group is open because no password is set: offer to set one.
    openSecretGroupDialog(group);
    return;
  }
  try {
    await api(`/groups/${group.id}/lock`, { method: "POST" });
  } catch (error) {
    toast(errorText(error), "error");
    return;
  }
  patchGroup(group, { unlocked: false });
  toast(t("secret.locked"), "success");
  if (state.view.type === "group" && Number(state.view.groupId) === Number(group.id)) {
    await navigateHome();
  }
}

function openSecretPrompt(group) {
  openDialog(
    `<form id="secretForm" class="dialog-form">
      ${dialogHead("🔐", t("secret.promptTitle"), groupDisplayName(group))}
      <div class="dlg-body">
        <div class="form-grid">
          <div class="field-group">
            <label for="secretPass">${esc(t("secret.password"))}</label>
            <input id="secretPass" type="password" autocomplete="current-password"
              maxlength="200" required>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${esc(t("common.cancel"))}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${esc(t("secret.unlockBtn"))}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        const input = $("#secretPass", dialog);
        $("#secretForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const password = input?.value || "";
          if (!password) {
            dialogError(dialog, t("err.password_required"));
            return;
          }
          setButtonBusy(button, true);
          try {
            await api(`/groups/${group.id}/unlock`, {
              method: "POST",
              body: { password },
            });
            patchGroup(group, { unlocked: true });
            dialog.close();
            navigateGroup(group.id);
          } catch (error) {
            if (error.code === "wrong_password") {
              dialogError(dialog, t("err.wrong_password"));
              input?.select();
            } else {
              dialogError(dialog, errorText(error));
            }
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

function openSecretGroupDialog(group) {
  const hasPassword = Boolean(group.password_set);
  openDialog(
    `<form id="secretGroupForm" class="dialog-form">
      ${dialogHead("🔐", t("secret.dlgTitle"), groupDisplayName(group))}
      <div class="dlg-body">
        <p class="dlg-hint">${esc(hasPassword ? t("secret.dlgHintSet") : t("secret.dlgHintNone"))}</p>
        <div class="form-grid">
          <div class="field-group">
            <label for="secretNewPass">${esc(hasPassword ? t("secret.newPassword") : t("secret.password"))}</label>
            <input id="secretNewPass" type="password" autocomplete="new-password"
              maxlength="200" ${hasPassword ? "" : "required"} placeholder="${esc(
              hasPassword ? t("secret.placeholderReplace") : t("secret.placeholderNew"),
            )}">
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${esc(t("common.cancel"))}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${esc(t("common.save"))}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        const input = $("#secretNewPass", dialog);
        $("#secretGroupForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const password = input?.value || "";
          if (!password && !hasPassword) {
            dialogError(dialog, t("err.password_required"));
            return;
          }
          if (password && password.length < 8) {
            dialogError(dialog, t("err.secret_password_short"));
            return;
          }
          setButtonBusy(button, true);
          try {
            const result = await api(`/groups/${group.id}`, {
              method: "PATCH",
              body: { password },
            });
            const saved = result.group || {};
            patchGroup(group, {
              password_set: saved.password_set,
              unlocked: saved.unlocked,
            });
            dialog.close();
            toast(hasPassword ? (password ? t("secret.saved") : t("secret.removed")) : t("secret.saved"), "success");
            await refreshAll({ skeleton: false });
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

/* ----------------------------- group modal ----------------------------- */

function openGroupDialog(group = null) {
  const editing = Boolean(group);
  const secret = Boolean(group && group.kind === "secret");
  let selectedIcon = group?.icon || "📁";
  if (secret) {
    openSecretGroupDialog(group);
    return;
  }
  openDialog(
    `<form id="groupForm" class="dialog-form">
      ${dialogHead(
        editing ? "✎" : "➕",
        editing ? t("group.edit") : t("group.new"),
        editing ? group.name : "",
      )}
      <div class="dlg-body">
        <div class="form-grid">
          <div class="field-group">
            <label for="groupName">${t("group.name")}</label>
            <input id="groupName" maxlength="40" value="${esc(group?.name || "")}"
              placeholder="${esc(t("group.namePlaceholder"))}" required>
          </div>
          <div class="field-group">
            <label>${t("group.icon")}</label>
            <div class="icon-picker">
              ${GROUP_ICONS.map(
                (icon) =>
                  `<button type="button" class="icon-option ${
                    icon === selectedIcon ? "active" : ""
                  }" data-icon="${icon}" aria-label="${icon}" aria-pressed="${
                    icon === selectedIcon
                  }">${icon}</button>`,
              ).join("")}
            </div>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${t("common.cancel")}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${editing ? t("common.save") : t("common.create")}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        dialog.querySelectorAll(".icon-option").forEach((button) => {
          button.addEventListener("click", () => {
            selectedIcon = button.dataset.icon;
            dialog.querySelectorAll(".icon-option").forEach((node) => {
              const active = node === button;
              node.classList.toggle("active", active);
              node.setAttribute("aria-pressed", String(active));
            });
          });
        });
        $("#groupForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const name = $("#groupName", dialog).value.trim();
          if (!name) {
            dialogError(dialog, t("err.group_name_required"));
            return;
          }
          setButtonBusy(button, true);
          try {
            if (editing) {
              await api(`/groups/${group.id}`, {
                method: "PATCH",
                body: { name, icon: selectedIcon },
              });
              toast(t("group.saved"), "success");
              dialog.close();
              await refreshAll({ skeleton: false });
            } else {
              const result = await api("/groups", {
                method: "POST",
                body: { name, icon: selectedIcon },
              });
              toast(t("group.created"), "success");
              dialog.close();
              await refreshAll({ skeleton: false });
              const select = el("addGroupSelect");
              if (select) {
                select.value = String(result.group.id);
                select.dataset.initialized = "1";
              }
              navigateGroup(result.group.id);
            }
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

/* ----------------------------- admin dialogs ----------------------------- */

function openAdminSettings(user) {
  if (!user) return;
  const me = Number(user.id) === Number(state.user?.id);
  const custom = user.custom_limits || {};
  openDialog(
    `<form id="adminSettingsForm" class="dialog-form">
      ${dialogHead("⚙️", t("admin.settingsTitle", { name: user.display_name || user.username }), t("admin.settingsSubtitle"))}
      <div class="dlg-body">
        <div class="admin-switch">
          <div>
            <label for="adminIsAdmin">${t("admin.isAdmin")}</label>
            <p>${t("admin.isAdminHint")}</p>
          </div>
          <label class="tgl">
            <input id="adminIsAdmin" type="checkbox" ${user.is_admin ? "checked" : ""} ${me ? "disabled" : ""}>
            <span class="tgl-track" aria-hidden="true"></span>
          </label>
        </div>
        <div class="admin-switch">
          <div>
            <label for="adminDisabled">${t("admin.isBlocked")}</label>
            <p>${t("admin.isBlockedHint")}</p>
          </div>
          <label class="tgl">
            <input id="adminDisabled" type="checkbox" ${user.disabled ? "checked" : ""} ${me ? "disabled" : ""}>
            <span class="tgl-track" aria-hidden="true"></span>
          </label>
        </div>
        <div class="form-grid">
          <h3 class="dlg-subtitle">${t("admin.limitsTitle")}</h3>
          <div class="field-group">
            <label for="adminLimitBookmarks">${t("admin.limitsBookmarks")}</label>
            <input id="adminLimitBookmarks" type="number" min="1" max="100000" inputmode="numeric"
              value="${custom.bookmarks ?? ""}" placeholder="${user.limits?.bookmarks ?? ""}">
            <small>${t("admin.limitEmptyHint", { value: user.limits?.bookmarks ?? "" })}</small>
          </div>
          <div class="field-group">
            <label for="adminLimitTags">${t("admin.limitsTags")}</label>
            <input id="adminLimitTags" type="number" min="1" max="5000" inputmode="numeric"
              value="${custom.tags ?? ""}" placeholder="${user.limits?.tags ?? ""}">
            <small>${t("admin.limitEmptyHint", { value: user.limits?.tags ?? "" })}</small>
          </div>
          <div class="field-group">
            <label for="adminLimitGroups">${t("admin.limitsGroups")}</label>
            <input id="adminLimitGroups" type="number" min="1" max="500" inputmode="numeric"
              value="${custom.groups ?? ""}" placeholder="${user.limits?.groups ?? ""}">
            <small>${t("admin.limitEmptyHint", { value: user.limits?.groups ?? "" })}</small>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${t("common.cancel")}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${t("common.save")}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        $("#adminSettingsForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const body = {};
          if (!me) {
            body.is_admin = $("#adminIsAdmin", dialog).checked;
            body.disabled = $("#adminDisabled", dialog).checked;
          }
          for (const [id, field] of [
            ["adminLimitBookmarks", "max_bookmarks"],
            ["adminLimitTags", "max_tags"],
            ["adminLimitGroups", "max_groups"],
          ]) {
            const raw = $(`#${id}`, dialog).value.trim();
            body[field] = raw === "" ? null : raw;
          }
          setButtonBusy(button, true);
          try {
            const result = await api(`/admin/users/${user.id}`, { method: "PATCH", body });
            if (state.admin) {
              const index = state.admin.users.findIndex((entry) => Number(entry.id) === Number(user.id));
              if (index !== -1) state.admin.users[index] = result.user;
              if (Number(result.user.id) === Number(state.user?.id)) {
                state.user = { ...state.user, is_admin: result.user.is_admin };
                renderUser();
              }
            }
            toast(t("admin.updated"), "success");
            dialog.close();
            if (state.view.type === "admin") renderBookmarkList();
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

function openAdminPassword(user) {
  if (!user) return;
  openDialog(
    `<form id="adminPasswordForm" class="dialog-form">
      ${dialogHead("🔄", t("admin.passTitle"), t("admin.passSubtitle"))}
      <div class="dlg-body">
        <div class="form-grid">
          <div class="field-group">
            <label for="adminNewPassword">${t("admin.passLabel")}</label>
            <input id="adminNewPassword" type="password" minlength="8" maxlength="200"
              autocomplete="new-password" required>
            <small>8–200</small>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${t("common.cancel")}</button>
        <button type="submit" class="btn primary">
          <span class="btn-spinner" hidden></span>
          <span>${t("common.save")}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        $("#adminNewPassword", dialog)?.focus();
        $("#adminPasswordForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const password = $("#adminNewPassword", dialog).value;
          setButtonBusy(button, true);
          try {
            await api(`/admin/users/${user.id}/password`, { method: "POST", body: { password } });
            toast(t("admin.passChanged"), "success");
            dialog.close();
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

async function deleteGroup(group) {
  if (!group || group.kind === "favorites") return;
  const count = group.count || 0;
  const confirmed = await confirmDialog({
    icon: "🗑️",
    title: t("group.deleteTitle"),
    message: count
      ? t("group.deleteText", { name: group.name, n: count })
      : t("group.deleteEmpty", { name: group.name }),
    confirmText: t("common.delete"),
  });
  if (!confirmed) return;
  try {
    await api(`/groups/${group.id}`, { method: "DELETE" });
    toast(t("group.deleted"), "success");
    if (state.view.type === "group" && state.view.groupId === group.id) {
      await navigateHome();
      await refreshAll({ skeleton: false });
    } else {
      await refreshAll({ skeleton: false });
    }
  } catch (error) {
    toast(errorText(error), "error");
  }
}

async function deleteTag(tagId, tagName) {
  const confirmed = await confirmDialog({
    icon: "🏷️",
    title: t("tags.deleteTitle", { tag: tagName }),
    message: t("tags.deleteText"),
    confirmText: t("common.delete"),
  });
  if (!confirmed) return;
  try {
    await api(`/tags/${tagId}`, { method: "DELETE" });
    toast(t("tags.deleted"), "success");
    const inCurrentTag =
      state.view.type === "tag" &&
      (state.view.tag || "").toLowerCase() === tagName.toLowerCase();
    await refreshAll({ skeleton: false });
    if (inCurrentTag) navigateTags();
  } catch (error) {
    toast(errorText(error), "error");
  }
}

/* ----------------------------- profile ----------------------------- */

function openProfileDialog() {
  const user = state.user;
  if (!user) return;
  let color = user.avatar_color || currentAccent();
  openDialog(
    `${dialogHead("👤", t("profile.title"), t("profile.subtitle"))}
     <div class="dlg-body">
       <div class="profile-head">
         <div class="avatar-preview" id="profileAvatar" style="--avatar-color:${esc(
           color,
         )}">${
            user.avatar_photo
              ? `<img class="avatar-photo" src="${user.avatar_photo}" alt="">`
              : esc(initials(user.display_name))
          }</div>
         <div class="profile-meta">
           <strong id="profileMetaName">${esc(user.display_name)}</strong>
           <span id="profileMetaUser">@${esc(user.username)}</span>
         </div>
         <div class="profile-head-actions">
           <button type="submit" form="profileForm" class="btn primary">
             <span class="btn-spinner" hidden></span>
             <span>${t("profile.save")}</span>
           </button>
         </div>
       </div>
       <form id="profileForm" class="form-grid">
         <div class="form-row">
           <div class="field-group">
             <label for="profileName">${t("profile.displayName")}</label>
             <input id="profileName" maxlength="48" value="${esc(user.display_name)}" required>
           </div>
           <div class="field-group">
             <label for="profileUser">${t("profile.username")}</label>
             <input id="profileUser" maxlength="32" value="${esc(user.username)}" required>
           </div>
         </div>
         <div class="field-group">
           <label>${t("profile.avatar")}</label>
           <div class="swatches">
             ${AVATAR_COLORS.map(
               (hex) =>
                 `<button type="button" class="swatch ${
                   hex === color ? "active" : ""
                 }" data-avatar-color="${hex}" style="background:${hex}" aria-label="${hex}"></button>`,
             ).join("")}
           </div>
         </div>
         <div class="field-group">
           <label>${t("profile.photo")}</label>
           <div class="file-row">
             <input type="file" id="profilePhotoFile" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml" hidden>
             <button type="button" class="btn" id="profilePhotoBrowse">${t("profile.photoChoose")}</button>
             <button type="button" class="btn danger" id="profilePhotoClear" hidden>${t("profile.photoRemove")}</button>
             <span class="hint">${t("profile.photoHint")}</span>
           </div>
         </div>
         <p class="form-error" hidden></p>
       </form>

       <div class="dlg-sep"></div>

       <div class="profile-limits">
          <h3 class="section-title">📊 ${esc(t("profile.limits"))}</h3>
          <p>${esc(
            t("profile.limitsFmt", {
              used: state.stats?.bookmarks ?? 0,
              bookmarks: user.limits?.bookmarks ?? "…",
              usedTags: state.stats?.tags ?? 0,
              tags: user.limits?.tags ?? "…",
              usedGroups: state.stats?.groups ?? 0,
              groups: user.limits?.groups ?? "…",
            }),
          )}</p>
        </div>

        <div class="dlg-sep"></div>

        <form id="passwordForm" class="form-grid">
         <div class="section-head">
           <h3 class="section-title">${t("profile.password")}</h3>
           <button type="submit" class="btn">
             <span class="btn-spinner" hidden></span>
             <span>${t("profile.changePassword")}</span>
           </button>
         </div>
         <div class="field-group">
           <label for="currentPassword">${t("profile.currentPassword")}</label>
           <input id="currentPassword" type="password" autocomplete="current-password" required>
         </div>
         <div class="form-row">
           <div class="field-group">
             <label for="newPassword">${t("profile.newPassword")}</label>
             <input id="newPassword" type="password" autocomplete="new-password" required>
             <div class="pass-strength" hidden>
               <div class="pass-strength-bars" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
               <span class="pass-strength-label"></span>
             </div>
           </div>
           <div class="field-group">
             <label for="confirmPassword">${t("profile.confirmPassword")}</label>
             <input id="confirmPassword" type="password" autocomplete="new-password" required>
           </div>
         </div>
         <p class="form-error" hidden></p>
       </form>

       <div class="dlg-sep"></div>

       <div class="danger-zone">
         <h3>${t("profile.danger")}</h3>
         <p>${t("profile.deleteHint")}</p>
         <button type="button" class="btn danger" data-delete-account>${t(
           "profile.deleteAccount",
         )}</button>
       </div>
     </div>
     <div class="dlg-foot">
       <button type="button" class="btn" data-logout>${t("profile.logout")}</button>
       <span class="spacer"></span>
       <button type="button" class="btn primary" data-close>${t("common.done")}</button>
     </div>`,
    {
      onMount(dialog) {
        const preview = $("#profileAvatar", dialog);
        const nameInput = $("#profileName", dialog);
        const userInput = $("#profileUser", dialog);
        let photoValue = user.avatar_photo || null;
        const photoClear = $("#profilePhotoClear", dialog);
        const photoFile = $("#profilePhotoFile", dialog);
        const syncPhotoUI = () => {
          photoClear.hidden = !photoValue;
        };
        const refreshPreview = () => {
          if (photoValue) {
            preview.innerHTML = `<img class="avatar-photo" src="${photoValue}" alt="">`;
          } else {
            preview.textContent = initials(nameInput.value || userInput.value);
          }
          preview.style.setProperty("--avatar-color", color);
          $("#profileMetaName", dialog).textContent = nameInput.value || userInput.value;
          $("#profileMetaUser", dialog).textContent = `@${userInput.value}`;
        };
        nameInput.addEventListener("input", refreshPreview);
        userInput.addEventListener("input", refreshPreview);
        $("#profilePhotoBrowse", dialog)?.addEventListener("click", () => photoFile?.click());
        photoFile?.addEventListener("change", () => {
          const file = photoFile.files && photoFile.files[0];
          if (!file) return;
          const reader = new FileReader();
          reader.onload = () => {
            photoValue = String(reader.result);
            syncPhotoUI();
            refreshPreview();
          };
          reader.readAsDataURL(file);
        });
        photoClear?.addEventListener("click", () => {
          photoValue = null;
          photoFile.value = "";
          syncPhotoUI();
          refreshPreview();
        });
        syncPhotoUI();
        dialog.querySelectorAll("[data-avatar-color]").forEach((button) => {
          button.addEventListener("click", () => {
            color = button.dataset.avatarColor;
            dialog.querySelectorAll("[data-avatar-color]").forEach((node) => {
              node.classList.toggle("active", node === button);
            });
            refreshPreview();
          });
        });
        $("#profileForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const errorBox = $("#profileForm .form-error", dialog);
          if (errorBox) errorBox.hidden = true;
          setButtonBusy(button, true);
          try {
            const result = await api("/account", {
              method: "PATCH",
              body: {
                display_name: nameInput.value.trim(),
                username: userInput.value.trim(),
                avatar_color: color,
                photo: photoValue,
                remove_photo: photoValue === null,
              },
            });
            state.user = result.user;
            renderUser();
            renderHead();
            toast(t("profile.saved"), "success");
            dialog.close();
          } catch (error) {
            if (errorBox) {
              errorBox.textContent = errorText(error);
              errorBox.hidden = false;
            }
          } finally {
            setButtonBusy(button, false);
          }
        });
        $("#passwordForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          const errorBox = $("#passwordForm .form-error", dialog);
          if (errorBox) errorBox.hidden = true;
          const current = $("#currentPassword", dialog).value;
          const next = $("#newPassword", dialog).value;
          const confirm = $("#confirmPassword", dialog).value;
          if (next !== confirm) {
            if (errorBox) {
              errorBox.textContent = t("err.password_mismatch");
              errorBox.hidden = false;
            }
            return;
          }
          if (next.length < 8) {
            if (errorBox) {
              errorBox.textContent = t("err.weak_password");
              errorBox.hidden = false;
            }
            return;
          }
          setButtonBusy(button, true);
          try {
            const result = await api("/account", {
              method: "PATCH",
              body: { current_password: current, new_password: next },
            });
            state.user = result.user;
            toast(t("profile.passwordChanged"), "success");
            $("#passwordForm", dialog).reset();
            renderPassStrength($("#newPassword", dialog));
          } catch (error) {
            if (errorBox) {
              errorBox.textContent = errorText(error);
              errorBox.hidden = false;
            }
          } finally {
            setButtonBusy(button, false);
          }
        });
        $("#newPassword", dialog)?.addEventListener("input", () => {
          renderPassStrength($("#newPassword", dialog));
        });
        $("[data-delete-account]", dialog)?.addEventListener("click", () => {
          dialog.close();
          setTimeout(openDeleteAccountDialog, 60);
        });
        $("[data-logout]", dialog)?.addEventListener("click", () => {
          dialog.close();
          doLogout();
        });
      },
    },
  );
}

function openDeleteAccountDialog() {
  const username = state.user?.username || "";
  openDialog(
    `<form id="deleteAccountForm" class="dialog-form">
      ${dialogHead("⚠️", t("profile.deleteTitle"))}
      <div class="dlg-body">
        <div class="form-grid">
          <p class="form-note">${esc(t("profile.deleteText", { username }))}</p>
          <div class="field-group">
            <label for="confirmUsername">${t("profile.confirmUsername")}</label>
            <input id="confirmUsername" autocomplete="off" placeholder="${esc(username)}" required>
          </div>
          <div class="field-group">
            <label for="deletePassword">${t("auth.password")}</label>
            <input id="deletePassword" type="password" autocomplete="current-password" required>
          </div>
          <p class="form-error" hidden></p>
        </div>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn" data-close>${t("common.cancel")}</button>
        <button type="submit" class="btn danger">
          <span class="btn-spinner" hidden></span>
          <span>${t("profile.deleteConfirm")}</span>
        </button>
      </div>
    </form>`,
    {
      onMount(dialog) {
        $("#deleteAccountForm", dialog)?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const button = event.submitter;
          setButtonBusy(button, true);
          try {
            await api("/account", {
              method: "DELETE",
              body: {
                password: $("#deletePassword", dialog).value,
                confirm: $("#confirmUsername", dialog).value.trim(),
              },
            });
            dialog.close();
            state.user = null;
            state.groups = [];
            state.bookmarks = [];
            state.tags = [];
            state.stats = null;
            showAuth();
            toast(t("profile.accountDeleted"), "success");
          } catch (error) {
            dialogError(dialog, errorText(error));
          } finally {
            setButtonBusy(button, false);
          }
        });
      },
    },
  );
}

function openAboutDialog() {
  const isAdmin = !!state.user?.is_admin;
  const updateSection = isAdmin
    ? `
        <div class="settings-section">
          <h3>${t("about.updates")}</h3>
          <div class="update-row">
            <span class="update-status" id="updateStatus">${esc(t("about.update.idle"))}</span>
            <span class="update-actions">
              <button type="button" class="btn" id="btnUpdateCheck">${t("about.update.check")}</button>
              <button type="button" class="btn primary" id="btnUpdateRun" disabled>${t("about.update.run")}</button>
            </span>
          </div>
        </div>`
    : "";
  openDialog(
    `${dialogHead("🔖", t("about.title"))}
     <div class="dlg-body">
       <div class="about-hero">
         <span class="logo-badge">🔖</span>
         <div>
           <h3>Bookmarks</h3>
           <p>${esc(t("about.version", { v: VERSION }))}</p>
         </div>
       </div>
       <p class="about-desc">${esc(t("about.description"))}</p>
       <div class="settings-section">
         <h3>${t("about.shortcuts")}</h3>
         <div class="shortcut-list">
           <div class="shortcut-row"><span>${t("about.shortcutSearch")}</span><kbd>Ctrl / ⌘ + K</kbd></div>
           <div class="shortcut-row"><span>${t("about.shortcutNew")}</span><kbd>N</kbd></div>
           <div class="shortcut-row"><span>${t("about.shortcutSave")}</span><kbd>Ctrl / ⌘ + Enter</kbd></div>
           <div class="shortcut-row"><span>${t("about.shortcutHome")}</span><kbd>H</kbd></div>
           <div class="shortcut-row"><span>${t("about.shortcutClose")}</span><kbd>Esc</kbd></div>
         </div>
       </div>
       ${updateSection}
       <p class="about-repo">
         <a href="${REPO_URL}" target="_blank" rel="noopener noreferrer">${t("about.github")}</a>
       </p>
       <p class="about-made">${esc(t("about.made"))}<br>${esc(t("about.license"))}</p>
     </div>
     <div class="dlg-foot">
       <button type="button" class="btn primary" data-close>${t("common.close")}</button>
     </div>`,
    isAdmin ? { onMount: (dialog) => mountUpdateSection(dialog) } : undefined,
  );
}

function mountUpdateSection(dialog) {
  const status = dialog.querySelector("#updateStatus");
  const btnCheck = dialog.querySelector("#btnUpdateCheck");
  const btnRun = dialog.querySelector("#btnUpdateRun");
  const set = (text, busy) => {
    status.textContent = text;
    btnCheck.disabled = busy;
    if (busy) btnRun.disabled = true;
  };
  const check = async () => {
    set(t("about.update.checking"), true);
    try {
      const r = await api("/update/check");
      if (r.available) {
        set(t("about.update.available", { v: r.latest }), false);
        btnRun.disabled = false;
      } else {
        set(t("about.update.uptodate", { v: r.current }), false);
      }
    } catch (error) {
      set(t("about.update.error", { detail: errorText(error) }), false);
    }
  };
  const run = async () => {
    set(t("about.update.running"), true);
    try {
      await api("/update/run", { method: "POST" });
      const deadline = Date.now() + 180_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        try {
          const health = await fetch("/health").then((response) => response.json());
          if (health && health.ok) {
            window.location.reload();
            return;
          }
        } catch {
          /* the server is still restarting */
        }
      }
      set(t("about.update.timeout"), false);
      btnCheck.disabled = false;
    } catch (error) {
      set(t("about.update.error", { detail: errorText(error) }), false);
    }
  };
  btnCheck.addEventListener("click", check);
  btnRun.addEventListener("click", () => {
    if (confirm(t("about.update.confirm"))) void run();
  });
}
