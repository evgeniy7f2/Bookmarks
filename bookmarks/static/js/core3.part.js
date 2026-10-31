

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

function renderList() {
  const list = el("list");
  if (!list) return;
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
  list.innerHTML = state.bookmarks.map(renderCard).join("");
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
