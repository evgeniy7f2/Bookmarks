

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

  list?.addEventListener(
    "error",
    (event) => {
      if (event.target.classList?.contains("card-favicon")) {
        event.target.closest(".card-icon")?.classList.add("favicon-failed");
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
