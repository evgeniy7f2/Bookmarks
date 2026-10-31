

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
          toast(
            `${t("settings.importDone")} — ${t("settings.imported", {
              n: result.imported || 0,
              m: result.skipped || 0,
            })}`,
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
