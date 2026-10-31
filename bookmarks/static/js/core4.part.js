

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
  const customs = state.groups.filter((group) => group.kind !== "favorites");
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
