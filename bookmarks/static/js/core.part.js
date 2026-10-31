/* ==========================================================================
   Bookmarks — front-end core: state, helpers, API, settings, auth
   ========================================================================== */

import { t, tp, setLang, getLang } from "./i18n.js";

const VERSION = document.querySelector('meta[name="bookmarks-version"]')?.content || "1.0.0";

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
  settings: { ...SETTINGS_DEFAULTS },
  view: { type: "home", groupId: null, tag: null, q: "" },
  loading: false,
  metaLoading: false,
  draggingBookmark: null,
  draggingGroup: null,
  popoverAnchor: null,
};

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
