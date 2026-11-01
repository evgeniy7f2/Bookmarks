/* Pre-translates the static markup before the first paint so EN users do not
   see Russian strings flashing while the i18n module is loading.
   Runs as a classic script at the end of <body>, right before app.js. */
(function () {
  var settings = {};
  try {
    settings = JSON.parse(localStorage.getItem("bms.settings") || "{}") || {};
  } catch (error) {
    settings = {};
  }
  if (settings.lang !== "en") return;

  var EN = {
    "auth.slogan": "A beautiful home for the links you love.",
    "auth.feature1": "Groups, tags, favorites and trash",
    "auth.feature2": "Search titles, URLs and tags",
    "auth.feature3": "Works on your network and every device",
    "auth.footer": "Self-hosted · Python + SQLite",
    "auth.username": "Username",
    "auth.usernameHint": "3–32 characters: letters, digits, _ . -",
    "auth.displayName": "Display name",
    "auth.password": "Password",
    "auth.passwordHint": "At least 8 characters",
    "auth.remember": "Remember me",
    "auth.login": "Sign in",
    "app.tagline": "Every link you care about",
    "nav.home": "Home",
    "nav.search": "Search",
    "nav.trash": "Trash",
    "nav.tags": "Tags",
    "sidebar.addGroup": "Add group",
    "sidebar.groups": "Groups",
    "sidebar.noGroups": "No groups yet",
    "search.placeholder": "Title, URL or tag…",
    "search.scope": "Searching all bookmarks",
    "add.title": "Add a new link",
    "add.subtitle": "Paste a URL — title and description fill in automatically",
    "add.url": "Link",
    "add.group": "Group",
    "add.save": "Save",
    "add.name": "Title",
    "add.namePlaceholder": "e.g. A great article about Python",
    "add.tags": "Tags",
    "add.tagsPlaceholder": "work, python, ideas",
    "add.description": "Description",
    "add.descriptionPlaceholder": "A few words about this link…",
    "add.statusHint": "Hotkey — N",
    "settings.title": "Settings"
  };

  document.querySelectorAll("[data-i18n]").forEach(function (node) {
    var text = EN[node.getAttribute("data-i18n")];
    if (text) node.textContent = text;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function (node) {
    var text = EN[node.getAttribute("data-i18n-placeholder")];
    if (text) node.setAttribute("placeholder", text);
  });

  var authTitle = document.getElementById("authTitle");
  if (authTitle) authTitle.textContent = "Sign in";
  var authLangBtn = document.getElementById("authLangBtn");
  if (authLangBtn) authLangBtn.textContent = "RU";
})();
