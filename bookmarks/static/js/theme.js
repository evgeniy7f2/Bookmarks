/* Theme palettes + early-apply of cached appearance settings before the
   first paint to avoid flashes. Exposes window.THEMES / window.THEME_VARS
   which app.js reuses in applySettings().

   Each palette is a 15-value array:
   [bg, bg2, surface, surfaceSolid, surface2, surface3, surfaceHover,
    text, text2, muted, border, borderStrong, accent, accent2, onAccent]
*/
(function () {
  var THEMES = {
    aura: {
      l: ["#f3f4fb", "#eceef8", "rgba(255,255,255,.78)", "#ffffff", "#eef0f9", "#e3e6f4", "#eaecf7", "#1c1f33", "#41465f", "#6f7490", "rgba(28,31,51,.08)", "rgba(28,31,51,.16)", "#7c6cf0", "#f0768f", "#ffffff"],
      d: ["#0d0e1a", "#10121f", "rgba(24,26,42,.74)", "#181a2a", "#1e2133", "#262a40", "#2a2f47", "#eceef8", "#c2c6dc", "#878da8", "rgba(255,255,255,.07)", "rgba(255,255,255,.14)", "#8b7cf7", "#f58ba0", "#ffffff"]
    },
    ayu: {
      l: ["#fcf6ea", "#f6efdc", "rgba(255,255,255,.78)", "#ffffff", "#f5efdd", "#ece4cf", "#f0ead8", "#5c6155", "#6c7060", "#8b8d77", "rgba(92,97,85,.1)", "rgba(92,97,85,.2)", "#f07178", "#ffb454", "#ffffff"],
      d: ["#0a0e1a", "#0f1420", "rgba(16,21,33,.76)", "#101521", "#16202f", "#1e2a3d", "#223047", "#cbccc6", "#aab0c6", "#787f97", "rgba(203,204,198,.09)", "rgba(203,204,198,.18)", "#e6b455", "#f07178", "#ffffff"]
    },
    carbonfox: {
      l: ["#f5f6fa", "#eef0f7", "rgba(255,255,255,.8)", "#ffffff", "#eef1f7", "#e2e6ef", "#e8ebf3", "#242938", "#454d63", "#6d7488", "rgba(36,41,56,.08)", "rgba(36,41,56,.16)", "#7aa2f7", "#bb9af7", "#ffffff"],
      d: ["#111219", "#14161f", "rgba(24,26,37,.74)", "#181a25", "#1e212e", "#262a3a", "#2a2e40", "#dfe2f0", "#b6bcd2", "#83899f", "rgba(223,226,240,.08)", "rgba(223,226,240,.16)", "#7dcfff", "#bb9af7", "#10121a"]
    },
    cobalt2: {
      l: ["#eef3fb", "#e5ecf8", "rgba(255,255,255,.8)", "#ffffff", "#eaf0fa", "#dde6f4", "#e4ecf8", "#16233c", "#35476b", "#64749b", "rgba(22,35,60,.09)", "rgba(22,35,60,.18)", "#2563eb", "#38bdf8", "#ffffff"],
      d: ["#0b1220", "#0e1628", "rgba(17,26,47,.74)", "#111c33", "#16233d", "#1d2d4d", "#213354", "#e2e9f6", "#b4c2dd", "#7e8db0", "rgba(226,233,246,.08)", "rgba(226,233,246,.16)", "#3b82f6", "#60a5fa", "#ffffff"]
    },
    cursor: {
      l: ["#f7f8fa", "#f1f2f5", "rgba(255,255,255,.85)", "#ffffff", "#f2f3f6", "#e8eaee", "#edeff2", "#17181c", "#3c3f47", "#6b6f7a", "rgba(23,24,28,.08)", "rgba(23,24,28,.16)", "#17181c", "#52555e", "#ffffff"],
      d: ["#0e0f13", "#121317", "rgba(24,25,30,.76)", "#18191e", "#1e2026", "#262830", "#2a2c34", "#ececf1", "#c6c8d1", "#8b8e99", "rgba(236,236,241,.08)", "rgba(236,236,241,.16)", "#f5f6f8", "#9ca1ad", "#101116"]
    },
    dracula: {
      l: ["#f5f6fa", "#eef0f6", "rgba(255,255,255,.82)", "#ffffff", "#eef0f6", "#e4e7f0", "#eaedf5", "#282a36", "#44475a", "#737689", "rgba(40,42,54,.09)", "rgba(40,42,54,.18)", "#6c5ce7", "#e91e63", "#ffffff"],
      d: ["#191a21", "#21222c", "rgba(33,34,44,.78)", "#21222c", "#2a2b38", "#32333f", "#363745", "#f8f8f2", "#d5d6cf", "#9a9bad", "rgba(248,248,242,.08)", "rgba(248,248,242,.16)", "#bd93f9", "#ff79c6", "#282a36"]
    },
    everforest: {
      l: ["#e9e7dc", "#e2e0d2", "rgba(255,255,255,.72)", "#f7f6f0", "#e4e2d5", "#d9d7c8", "#e0ded1", "#5c5848", "#6b675c", "#8a8578", "rgba(92,88,72,.1)", "rgba(92,88,72,.2)", "#7698a3", "#a7c080", "#ffffff"],
      d: ["#232629", "#2c2e32", "rgba(50,53,59,.74)", "#32353b", "#3a3d44", "#43464d", "#474a51", "#d3d7c9", "#b5b9ac", "#7f8779", "rgba(211,215,201,.08)", "rgba(211,215,201,.17)", "#a7c080", "#d69d85", "#1c2026"]
    },
    flexoki: {
      l: ["#b9c2ca", "#b0bac3", "rgba(255,255,255,.55)", "#cdd5dd", "#c2ccd4", "#b5c0c9", "#c8d1d9", "#2f3542", "#5b6479", "#6f7889", "rgba(47,53,66,.12)", "rgba(47,53,66,.24)", "#d35400", "#2563eb", "#ffffff"],
      d: ["#101114", "#191a1d", "rgba(37,39,44,.74)", "#25272c", "#2a2d34", "#33363d", "#33363d", "#c5cdd9", "#9094ad", "#6b7089", "rgba(144,148,173,.14)", "rgba(144,148,173,.34)", "#ff9e64", "#a6c8f6", "#101114"]
    },
    catppuccin: {
      l: ["#eff1f5", "#e6e9ef", "rgba(255,255,255,.8)", "#ffffff", "#e6e9ef", "#dce0e8", "#e2e5ec", "#4c4f69", "#5c5f77", "#7c7f93", "rgba(76,79,105,.09)", "rgba(76,79,105,.18)", "#1e66f5", "#fe640b", "#ffffff"],
      d: ["#1e1e2e", "#181825", "rgba(49,50,68,.74)", "#313244", "#3b3c50", "#44455a", "#494a60", "#cdd6f4", "#bac2de", "#8c8fa3", "rgba(205,214,244,.08)", "rgba(205,214,244,.16)", "#89b4fa", "#fab387", "#1e1e2e"]
    },
    "catppuccin-frappe": {
      l: ["#e8eaf3", "#dfe2ee", "rgba(255,255,255,.75)", "#f2f4fa", "#e3e6f0", "#d7dae8", "#dfe2ed", "#303446", "#4b4f66", "#6c7089", "rgba(48,52,70,.1)", "rgba(48,52,70,.2)", "#4a5fc1", "#d97757", "#ffffff"],
      d: ["#232428", "#292c3c", "rgba(42,45,58,.76)", "#303446", "#3a3e51", "#444859", "#474b5e", "#c6d0f5", "#b3bddd", "#838ba2", "rgba(198,208,245,.08)", "rgba(198,208,245,.16)", "#8caaee", "#ef9f76", "#232428"]
    },
    "catppuccin-macchiato": {
      l: ["#e6e9ef", "#dde0e8", "rgba(255,255,255,.75)", "#eff1f6", "#e0e3ea", "#d3d7e1", "#dbe0e8", "#363a4f", "#4f5470", "#6e7390", "rgba(54,58,79,.1)", "rgba(54,58,79,.2)", "#3e5ec6", "#d97e54", "#ffffff"],
      d: ["#1c1e2b", "#24273a", "rgba(46,49,62,.76)", "#2e313e", "#383b4b", "#424555", "#454859", "#cad3f5", "#b8c2e0", "#8089a8", "rgba(202,211,245,.08)", "rgba(202,211,245,.16)", "#8aadf4", "#f5a97f", "#1c1e2b"]
    },
    github: {
      l: ["#f6f8fa", "#eef1f5", "rgba(255,255,255,.85)", "#ffffff", "#f2f5f9", "#e8edf3", "#edf1f6", "#1f2328", "#444c56", "#6e7781", "rgba(31,35,40,.09)", "rgba(31,35,40,.18)", "#0969da", "#8250df", "#ffffff"],
      d: ["#0d1117", "#10141b", "rgba(22,27,34,.74)", "#161b22", "#1c2230", "#232b3b", "#263041", "#e6edf3", "#adbac7", "#7d8590", "rgba(255,255,255,.075)", "rgba(255,255,255,.15)", "#58a6ff", "#d2a8ff", "#ffffff"]
    },
    gruvbox: {
      l: ["#fbf1c7", "#f4e9b8", "rgba(255,255,255,.6)", "#fdf6e3", "#f4e9c0", "#e8dcae", "#f0e5bb", "#3c3836", "#504945", "#7c6f64", "rgba(60,56,54,.12)", "rgba(60,56,54,.24)", "#cc241d", "#d79921", "#ffffff"],
      d: ["#1d2021", "#282828", "rgba(40,40,40,.76)", "#282828", "#32302f", "#3c3836", "#403d3b", "#ebdbb2", "#d5c4a1", "#98877a", "rgba(235,219,178,.09)", "rgba(235,219,178,.18)", "#fabd2f", "#fe8019", "#1d2021"]
    },
    kanagawa: {
      l: ["#eff2f5", "#e6eaef", "rgba(255,255,255,.8)", "#ffffff", "#e8ecf1", "#dde3ea", "#e2e8ef", "#101422", "#39415a", "#6a7391", "rgba(16,20,34,.08)", "rgba(16,20,34,.17)", "#2e77f2", "#d7447e", "#ffffff"],
      d: ["#0f111a", "#151725", "rgba(21,23,36,.74)", "#151725", "#1b1e2e", "#222538", "#262941", "#c7c8cc", "#9ca7b9", "#767e93", "rgba(199,200,204,.08)", "rgba(199,200,204,.16)", "#59c2ff", "#f47067", "#0f111a"]
    },
    material: {
      l: ["#fafafa", "#f1f3f4", "rgba(255,255,255,.85)", "#ffffff", "#f3f4f6", "#e9ebee", "#eef0f2", "#212121", "#42454b", "#6b6f76", "rgba(33,33,33,.09)", "rgba(33,33,33,.18)", "#6200ee", "#018786", "#ffffff"],
      d: ["#121212", "#1a1a1a", "rgba(30,30,30,.76)", "#1e1e1e", "#262626", "#2e2e2e", "#323232", "#e0e0e0", "#b8bcc2", "#8f949b", "rgba(224,224,224,.08)", "rgba(224,224,224,.16)", "#bb86fc", "#03dac6", "#121212"]
    },
    matrix: {
      l: ["#eef7ef", "#e4f2e5", "rgba(255,255,255,.8)", "#ffffff", "#e7f3e8", "#d8ecd9", "#def0df", "#0b3d1a", "#1d5c33", "#4f7d63", "rgba(11,61,26,.1)", "rgba(11,61,26,.2)", "#00a827", "#00c853", "#ffffff"],
      d: ["#050a06", "#0a120c", "rgba(15,26,15,.76)", "#0f1a0f", "#142414", "#1a2e1a", "#1d341d", "#3ddc64", "#2bb352", "#2a8a48", "rgba(61,220,100,.1)", "rgba(61,220,100,.22)", "#00ff41", "#7dffa8", "#03210d"]
    },
    mercury: {
      l: ["#f5f5f7", "#ececee", "rgba(255,255,255,.85)", "#ffffff", "#f3f3f5", "#e8e8ed", "#eff0f3", "#1d1d1f", "#3f3f46", "#6e6e73", "rgba(29,29,31,.09)", "rgba(29,29,31,.18)", "#0071e3", "#ff9500", "#ffffff"],
      d: ["#050506", "#0a0a0c", "rgba(28,28,30,.76)", "#1c1c1e", "#242426", "#2c2c2e", "#303032", "#f5f5f7", "#d4d4d8", "#8e8e93", "rgba(245,245,247,.09)", "rgba(245,245,247,.18)", "#0a84ff", "#ff9f0a", "#ffffff"]
    },
    monokai: {
      l: ["#f5f5f5", "#ececec", "rgba(255,255,255,.82)", "#ffffff", "#f0f0f0", "#e6e6e6", "#ececec", "#272822", "#49483e", "#76756b", "rgba(39,40,34,.1)", "rgba(39,40,34,.2)", "#d63369", "#3f9c35", "#ffffff"],
      d: ["#21221d", "#272822", "rgba(47,49,41,.76)", "#2f3129", "#35372e", "#3d3f35", "#404237", "#f8f8f2", "#d6d6ce", "#98968c", "rgba(248,248,242,.08)", "rgba(248,248,242,.16)", "#f92672", "#a6e22e", "#272822"]
    },
    nightowl: {
      l: ["#f4f6fb", "#eaeef6", "rgba(255,255,255,.82)", "#ffffff", "#eef1f8", "#e2e7f1", "#e8ecf5", "#242b3d", "#414a66", "#6b7392", "rgba(36,43,61,.09)", "rgba(36,43,61,.18)", "#3d5afe", "#00acc1", "#ffffff"],
      d: ["#011627", "#081f30", "rgba(10,37,51,.76)", "#0a2533", "#103048", "#163a54", "#1a405c", "#d6deeb", "#a8b2c8", "#7a8499", "rgba(214,222,235,.08)", "rgba(214,222,235,.16)", "#82aaff", "#78dce8", "#011627"]
    },
    nord: {
      l: ["#eceff4", "#e1e5ec", "rgba(255,255,255,.8)", "#ffffff", "#e8ebf0", "#dfe3e9", "#e5e8ee", "#2e3440", "#434c5e", "#6b7385", "rgba(46,52,64,.09)", "rgba(46,52,64,.18)", "#5e81ac", "#81a1c1", "#ffffff"],
      d: ["#2e3440", "#292e38", "rgba(59,66,82,.76)", "#3b4252", "#434c5e", "#4c566a", "#4f5a70", "#eceff4", "#d8dee9", "#9aa5b5", "rgba(236,239,244,.08)", "rgba(236,239,244,.16)", "#88c0d0", "#81a1c1", "#2e3440"]
    },
    "one-dark": {
      l: ["#f5f6f7", "#eceef0", "rgba(255,255,255,.85)", "#ffffff", "#eef0f2", "#e3e6ea", "#e9ecf0", "#383a42", "#5a5d68", "#7a7d88", "rgba(56,58,66,.09)", "rgba(56,58,66,.18)", "#4078f2", "#a626a4", "#ffffff"],
      d: ["#21252b", "#282c34", "rgba(33,37,43,.76)", "#21252b", "#2c313a", "#333945", "#363d4a", "#abb2bf", "#9da5b4", "#788299", "rgba(171,178,191,.08)", "rgba(171,178,191,.16)", "#61afef", "#c678dd", "#282c34"]
    },
    opencode: {
      l: ["#f4f7f6", "#eaeef0", "rgba(255,255,255,.85)", "#ffffff", "#edf2f0", "#e1e9e6", "#e7ede9", "#17201d", "#37453f", "#64736c", "rgba(23,32,29,.09)", "rgba(23,32,29,.17)", "#0d9488", "#7c3aed", "#ffffff"],
      d: ["#0a0b0d", "#101214", "rgba(18,20,22,.76)", "#141619", "#1b1e21", "#232629", "#272b2f", "#f2f3f5", "#c9ccd1", "#8b9097", "rgba(242,243,245,.08)", "rgba(242,243,245,.16)", "#34d399", "#a78bfa", "#06120d"]
    },
    orng: {
      l: ["#faf5ec", "#f3ebdc", "rgba(255,255,255,.8)", "#ffffff", "#f5efe2", "#eadfc9", "#f0e8d6", "#2a1a05", "#4d3a1d", "#7d6a4d", "rgba(42,26,5,.1)", "rgba(42,26,5,.2)", "#e85d04", "#f77f00", "#ffffff"],
      d: ["#14110c", "#1a160f", "rgba(30,25,18,.76)", "#1e1912", "#272015", "#302819", "#342c1c", "#f5ede0", "#d9cbb4", "#9c8d72", "rgba(245,237,224,.08)", "rgba(245,237,224,.16)", "#ff8c1a", "#ffc46b", "#2b1500"]
    },
    "lucent-orng": {
      l: ["#fff7ed", "#fdeeda", "rgba(255,255,255,.8)", "#ffffff", "#fef3e2", "#fde8c8", "#fdf0da", "#431407", "#7c2d12", "#8a5a2b", "rgba(67,20,7,.09)", "rgba(67,20,7,.18)", "#ea580c", "#f97316", "#ffffff"],
      d: ["#1c1006", "#241505", "rgba(66,30,8,.72)", "#33190a", "#3d200d", "#47270f", "#4b2b10", "#ffedd5", "#fed7aa", "#b97f4e", "rgba(255,237,213,.09)", "rgba(255,237,213,.18)", "#fb923c", "#fdba74", "#241102"]
    },
    "osaka-jade": {
      l: ["#f0f7f3", "#e6f2ec", "rgba(255,255,255,.82)", "#ffffff", "#eaf4ef", "#dcebe2", "#e2efe7", "#12301f", "#2f5c42", "#5f8471", "rgba(18,48,31,.1)", "rgba(18,48,31,.2)", "#059669", "#34d399", "#ffffff"],
      d: ["#0c1210", "#101915", "rgba(19,28,24,.76)", "#131c18", "#182420", "#1f2e28", "#22332c", "#d9e8dd", "#b3cabb", "#7fa08c", "rgba(217,232,221,.08)", "rgba(217,232,221,.16)", "#22d3aa", "#86efac", "#06130e"]
    },
    palenight: {
      l: ["#eef1f8", "#e4e8f4", "rgba(255,255,255,.82)", "#ffffff", "#e8ebf5", "#dde2f0", "#e2e6f2", "#292d3e", "#464c6b", "#6f7494", "rgba(41,45,62,.09)", "rgba(41,45,62,.18)", "#3b6fd4", "#8e4ec6", "#ffffff"],
      d: ["#202336", "#292d3e", "rgba(37,40,57,.76)", "#252839", "#2d3045", "#353952", "#383d58", "#c9d1e3", "#aab4d0", "#7e88a8", "rgba(201,209,227,.08)", "rgba(201,209,227,.16)", "#82aaff", "#c792ea", "#1f2233"]
    },
    rosepine: {
      l: ["#f4f1f6", "#ebe6f0", "rgba(255,255,255,.82)", "#ffffff", "#efeaf3", "#e4ddec", "#e8e2ee", "#5e5467", "#726a80", "#8e869c", "rgba(94,84,103,.1)", "rgba(94,84,103,.2)", "#8e68c9", "#4fa89a", "#ffffff"],
      d: ["#121019", "#191724", "rgba(38,35,58,.74)", "#26233a", "#2e2b44", "#37344e", "#3a3753", "#e0def4", "#c8c6e2", "#9492ab", "rgba(224,222,244,.08)", "rgba(224,222,244,.16)", "#c5a9ff", "#9ccfd1", "#191724"]
    },
    solarized: {
      l: ["#fdf6e3", "#f4ecd4", "rgba(255,255,255,.7)", "#fffdf5", "#f4ecd4", "#eee3c0", "#f0e6c9", "#586e75", "#6d8087", "#859599", "rgba(88,110,117,.12)", "rgba(88,110,117,.24)", "#268bd2", "#b58900", "#ffffff"],
      d: ["#002b36", "#003441", "rgba(7,54,66,.76)", "#073642", "#0d4250", "#124e5e", "#155465", "#93a1a1", "#839496", "#586e75", "rgba(147,161,161,.1)", "rgba(147,161,161,.22)", "#268bd2", "#b58900", "#002b36"]
    },
    synthwave84: {
      l: ["#f4f1fb", "#ebe6f8", "rgba(255,255,255,.8)", "#ffffff", "#efeafa", "#e4ddf4", "#eae4f7", "#322b45", "#4e4568", "#7a6f96", "rgba(50,43,69,.1)", "rgba(50,43,69,.2)", "#e040a5", "#00b3ad", "#ffffff"],
      d: ["#1a1626", "#262335", "rgba(38,35,53,.76)", "#262335", "#2e2a42", "#383350", "#3b3657", "#f7f2ff", "#d9d2f0", "#9d94b8", "rgba(247,242,255,.08)", "rgba(247,242,255,.16)", "#ff7edb", "#36f9f6", "#26102b"]
    },
    tokyonight: {
      l: ["#e8e9ed", "#dfe1e8", "rgba(255,255,255,.8)", "#f2f3f7", "#e3e5ec", "#d7dae4", "#dde0e8", "#2f3b52", "#46557a", "#71809f", "rgba(47,59,82,.1)", "rgba(47,59,82,.2)", "#345d9b", "#904350", "#ffffff"],
      d: ["#16161e", "#1a1b26", "rgba(36,40,59,.74)", "#24283b", "#2b3044", "#333953", "#363d5a", "#c0caf5", "#a5b1d8", "#7883a8", "rgba(192,202,245,.08)", "rgba(192,202,245,.16)", "#7aa2f7", "#bb9af7", "#1a1b26"]
    },
    vercel: {
      l: ["#ffffff", "#f5f5f5", "rgba(255,255,255,.9)", "#ffffff", "#fafafa", "#f0f0f0", "#f5f5f5", "#0a0a0a", "#333333", "#737373", "rgba(10,10,10,.1)", "rgba(10,10,10,.2)", "#000000", "#525252", "#ffffff"],
      d: ["#000000", "#0a0a0a", "rgba(17,17,17,.76)", "#111111", "#181818", "#1f1f1f", "#232323", "#fafafa", "#d4d4d4", "#a3a3a3", "rgba(250,250,250,.09)", "rgba(250,250,250,.18)", "#ffffff", "#a1a1aa", "#000000"]
    },
    vesper: {
      l: ["#eef1fb", "#e4e8f8", "rgba(255,255,255,.82)", "#ffffff", "#e8ebf8", "#dde2f4", "#e2e7f5", "#1c2340", "#333d66", "#61709f", "rgba(28,35,64,.09)", "rgba(28,35,64,.18)", "#4660d8", "#8a5cf6", "#ffffff"],
      d: ["#0b0e1a", "#101425", "rgba(20,26,46,.74)", "#141a2e", "#1a2138", "#212a45", "#252e4c", "#dfe5ff", "#b7c2e8", "#7e8bb5", "rgba(223,229,255,.08)", "rgba(223,229,255,.16)", "#5b7cfa", "#b18cff", "#0b0e1a"]
    },
    zenburn: {
      l: ["#efece3", "#e6e2d5", "rgba(255,255,255,.75)", "#f7f5ee", "#e9e5d8", "#ddd8c7", "#e3dfd0", "#3f3f3f", "#57544e", "#827f75", "rgba(63,63,63,.11)", "rgba(63,63,63,.22)", "#a8514e", "#9a7b32", "#ffffff"],
      d: ["#323232", "#3f3f3f", "rgba(68,68,68,.76)", "#444444", "#4c4c4c", "#545454", "#585858", "#dcdccc", "#bdbdae", "#8f8f82", "rgba(220,220,204,.09)", "rgba(220,220,204,.18)", "#dca3a3", "#e0cf9f", "#323232"]
    }
  };

  var THEME_VARS = [
    "--bg", "--bg-2", "--surface", "--surface-solid", "--surface-2",
    "--surface-3", "--surface-hover", "--text", "--text-2", "--muted",
    "--border", "--border-strong", "--accent", "--accent-2", "--on-accent"
  ];
  var THEME_NAMES = Object.keys(THEMES);
  var DEFAULT_THEME = "github";

  window.THEMES = THEMES;
  window.THEME_VARS = THEME_VARS;
  window.THEME_NAMES = THEME_NAMES;
  window.DEFAULT_THEME = DEFAULT_THEME;

  var settings = {};
  try {
    settings = JSON.parse(localStorage.getItem("bms.settings") || "{}") || {};
  } catch (error) {
    settings = {};
  }

  /* Resolve theme + color scheme (also migrates pre-1.0.2 values where the
     single "theme" key doubled as color scheme). */
  var theme = DEFAULT_THEME;
  var scheme = "system";
  if (THEMES[settings.theme]) {
    theme = settings.theme;
  } else if (settings.theme === "flexoki") {
    theme = "flexoki";
    scheme = "dark";
  } else if (settings.theme === "light" || settings.theme === "dark") {
    scheme = settings.theme;
  }
  if (settings.colorScheme === "light" || settings.colorScheme === "dark" || settings.colorScheme === "system") {
    scheme = settings.colorScheme;
  }

  var dark;
  if (scheme === "dark") dark = true;
  else if (scheme === "light") dark = false;
  else dark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);

  var root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.scheme = dark ? "dark" : "light";

  var palette = (THEMES[theme] || THEMES[DEFAULT_THEME])[dark ? "d" : "l"];
  for (var i = 0; i < THEME_VARS.length; i++) {
    root.style.setProperty(THEME_VARS[i], palette[i]);
  }

  var fontSize = Math.min(19, Math.max(13, Math.round(Number(settings.fontSize) || 16)));
  root.style.setProperty("--font-size", fontSize + "px");
  var radius = Math.round(Number(settings.radius) || 18);
  root.style.setProperty("--radius", radius + "px");
  root.dataset.glow = settings.glow === false ? "off" : "on";

  var themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) themeMeta.content = palette[0];
})();
