const viewer = document.querySelector("#building");
const button = document.querySelector("#theme");

const NIGHT = {
  Podium: "textures/podium-night.png",
  Shaft: "textures/shaft-night.png",
  Crown: "textures/crown-night.png",
  Glass: "textures/glass-night.png",
  Metal: "textures/metal-night.png",
  Wood: "textures/wood-night.png",
  Roof: "textures/roof-night.png",
  Plaza: "textures/plaza-night.png",
};

const dayTextures = new Map();
const nightTextures = new Map();

function systemDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function isDark() {
  const theme = document.documentElement.dataset.theme;
  return theme ? theme === "dark" : systemDark();
}

function syncButton() {
  const dark = isDark();
  button.textContent = dark ? "Day" : "Night";
  button.setAttribute("aria-pressed", dark ? "true" : "false");
}

async function textureFor(material, dark) {
  const current = material.pbrMetallicRoughness.baseColorTexture;
  if (current && !dayTextures.has(material.name)) {
    dayTextures.set(material.name, current.texture);
  }
  if (!dark) return dayTextures.get(material.name);
  const url = NIGHT[material.name];
  if (!url) return dayTextures.get(material.name);
  if (!nightTextures.has(material.name)) {
    nightTextures.set(material.name, viewer.createTexture(url));
  }
  return nightTextures.get(material.name);
}

async function applyTheme() {
  syncButton();
  if (!viewer.model) return;
  const dark = isDark();
  viewer.exposure = dark ? 0.9 : 1.05;
  viewer.shadowIntensity = dark ? 0.28 : 0.55;
  const materials = viewer.model.materials;
  await Promise.all(
    materials.map(async (material) => {
      const info = material.pbrMetallicRoughness.baseColorTexture;
      const texture = await textureFor(material, dark);
      if (info && texture) info.setTexture(texture);
    }),
  );
}

button.addEventListener("click", () => {
  document.documentElement.dataset.theme = isDark() ? "light" : "dark";
  applyTheme();
});

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (!document.documentElement.dataset.theme) applyTheme();
});

viewer.addEventListener("load", () => {
  applyTheme();
});

syncButton();
