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
          if (password && password.length < 4) {
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
         <div class="form-actions">
           <button type="submit" class="btn primary">
             <span class="btn-spinner" hidden></span>
             <span>${t("profile.save")}</span>
           </button>
         </div>
       </form>

       <div class="dlg-sep"></div>

       <form id="passwordForm" class="form-grid">
         <h3 class="section-title">${t("profile.password")}</h3>
         <div class="field-group">
           <label for="currentPassword">${t("profile.currentPassword")}</label>
           <input id="currentPassword" type="password" autocomplete="current-password" required>
         </div>
         <div class="form-row">
           <div class="field-group">
             <label for="newPassword">${t("profile.newPassword")}</label>
             <input id="newPassword" type="password" autocomplete="new-password" required>
           </div>
           <div class="field-group">
             <label for="confirmPassword">${t("profile.confirmPassword")}</label>
             <input id="confirmPassword" type="password" autocomplete="new-password" required>
           </div>
         </div>
         <p class="form-error" hidden></p>
         <div class="form-actions">
           <button type="submit" class="btn">
             <span class="btn-spinner" hidden></span>
             <span>${t("profile.changePassword")}</span>
           </button>
         </div>
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
          setButtonBusy(button, true);
          try {
            const result = await api("/account", {
              method: "PATCH",
              body: { current_password: current, new_password: next },
            });
            state.user = result.user;
            toast(t("profile.passwordChanged"), "success");
            $("#passwordForm", dialog).reset();
          } catch (error) {
            if (errorBox) {
              errorBox.textContent = errorText(error);
              errorBox.hidden = false;
            }
          } finally {
            setButtonBusy(button, false);
          }
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
       <p class="about-made">${esc(t("about.made"))}<br>${esc(t("about.license"))}</p>
     </div>
     <div class="dlg-foot">
       <button type="button" class="btn primary" data-close>${t("common.close")}</button>
     </div>`,
  );
}
