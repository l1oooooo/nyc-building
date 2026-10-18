const root = document.querySelector("#root");
const viewer = document.querySelector("#building");
const themeButton = document.querySelector("#theme");
const timelineButton = document.querySelector("#timeline");
const wrap = document.querySelector("#strip-wrap");
const strip = document.querySelector("#strip");
const track = document.querySelector("#track");
const picker = document.querySelector("#picker");
const place = document.querySelector("#place");
const flyer = document.querySelector("#flyer");

const SHARED_NIGHT = {
  Glass: "textures/glass-night.png",
  Metal: "textures/metal-night.png",
  Wood: "textures/wood-night.png",
  Roof: "textures/roof-night.png",
  Plaza: "textures/plaza-night.png",
};

const BUILDINGS = [
  {
    id: "perry",
    name: "Perry Street",
    who: "A brownstone",
    at: Date.parse("2026-10-12T12:00:00"),
    src: "models/perry.gltf",
    alt: "Clay model of a Perry Street brownstone",
    posterDay: "textures/perry-poster-day.png",
    posterNight: "textures/perry-poster-night.png",
    night: { Stone: "textures/perry-stone-night.png", ...SHARED_NIGHT },
    orbit: "26deg 76deg 48m",
    minOrbit: "-180deg 62deg 48m",
    maxOrbit: "180deg 96deg 48m",
    target: "0m 5.4m 0m",
    fov: "28deg",
  },
  {
    id: "lispenard",
    name: "Lispenard Tower",
    who: "A setback tower",
    at: Date.parse("2026-10-18T12:00:00"),
    src: "models/lispenard.gltf",
    alt: "Clay model of Lispenard Tower",
    posterDay: "textures/lispenard-poster-day.png",
    posterNight: "textures/lispenard-poster-night.png",
    night: {
      Podium: "textures/podium-night.png",
      Shaft: "textures/shaft-night.png",
      Crown: "textures/crown-night.png",
      ...SHARED_NIGHT,
    },
    orbit: "32deg 78deg 96m",
    minOrbit: "-180deg 64deg 96m",
    maxOrbit: "180deg 98deg 96m",
    target: "0m 18m 0m",
    fov: "30deg",
  },
];

const FLIGHT = "cubic-bezier(0.83, 0, 0.17, 1)";
const FLIGHT_MS = 450;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

let active = 1;
let marker = 1;
let flight = null;
let glide = 0;
const dayTextures = new Map();
const nightTextures = new Map();

function systemDark() {
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

function isDark() {
  const theme = document.documentElement.dataset.theme;
  return theme ? theme === "dark" : systemDark();
}

function current() {
  return BUILDINGS[active];
}

function posterFor(building) {
  return isDark() ? building.posterNight : building.posterDay;
}

function dayLabel(time) {
  const start = (value) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((start(new Date()) - start(new Date(time))) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days === -1) return "Tomorrow";
  return new Date(time).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function syncButton() {
  const dark = isDark();
  themeButton.textContent = dark ? "Light" : "Dark";
  themeButton.setAttribute("aria-pressed", dark ? "true" : "false");
}

function syncPosters() {
  for (const img of track.querySelectorAll("img")) {
    img.src = posterFor(BUILDINGS[Number(img.dataset.index)]);
  }
  if (!flyer.hidden && flight) flyer.src = posterFor(current());
}

async function textureFor(material, dark) {
  const key = `${current().id}:${material.name}`;
  const info = material.pbrMetallicRoughness.baseColorTexture;
  if (info && !dayTextures.has(key)) dayTextures.set(key, info.texture);
  if (!dark) return dayTextures.get(key);
  const url = current().night[material.name];
  if (!url) return dayTextures.get(key);
  if (!nightTextures.has(key)) nightTextures.set(key, viewer.createTexture(url));
  return nightTextures.get(key);
}

async function applyTheme() {
  syncButton();
  syncPosters();
  if (!viewer.model) return;
  const dark = isDark();
  viewer.exposure = dark ? 0.9 : 1.05;
  viewer.shadowIntensity = dark ? 0.28 : 0.55;
  await Promise.all(
    viewer.model.materials.map(async (material) => {
      const info = material.pbrMetallicRoughness.baseColorTexture;
      const texture = await textureFor(material, dark);
      if (info && texture) info.setTexture(texture);
    }),
  );
}

function applyCamera(building) {
  viewer.minFieldOfView = "0deg";
  viewer.maxFieldOfView = "180deg";
  viewer.fieldOfView = building.fov;
  viewer.minFieldOfView = building.fov;
  viewer.maxFieldOfView = building.fov;
  viewer.minCameraOrbit = "auto auto auto";
  viewer.maxCameraOrbit = "auto auto auto";
  viewer.cameraTarget = building.target;
  viewer.cameraOrbit = building.orbit;
  viewer.minCameraOrbit = building.minOrbit;
  viewer.maxCameraOrbit = building.maxOrbit;
  viewer.alt = building.alt;
}

function loadBuilding(index) {
  const building = BUILDINGS[index];
  const changed = index !== active;
  active = index;
  marker = index;
  place.textContent = building.name;
  document.title = building.name;
  applyCamera(building);
  if (!changed || String(viewer.src).endsWith(building.src)) {
    applyTheme();
    return;
  }
  viewer.src = building.src;
}

function renderStrip() {
  track.replaceChildren();
  BUILDINGS.forEach((building, index) => {
    const item = document.createElement("figure");
    item.className = "strip-item";
    item.dataset.index = String(index);
    item.innerHTML = `
      <p class="strip-when"></p>
      <button class="strip-button" type="button"></button>
      <figcaption>
        <span class="strip-place"></span>
        <span class="strip-friends"></span>
      </figcaption>
    `;
    item.querySelector(".strip-when").textContent = dayLabel(building.at);
    item.querySelector(".strip-place").textContent = building.name;
    item.querySelector(".strip-friends").textContent = building.who;
    const button = item.querySelector(".strip-button");
    button.setAttribute("aria-label", `View the ${building.name} model`);
    const img = document.createElement("img");
    img.alt = building.alt;
    img.dataset.index = String(index);
    img.src = posterFor(building);
    button.append(img);
    button.addEventListener("click", () => choose(index));
    item.querySelector(".strip-when").addEventListener("click", () => glideTo(index));
    track.append(item);
  });
}

function itemImage(index) {
  return track.querySelector(`.strip-item[data-index="${index}"] img`);
}

function centerDelta(index) {
  const img = itemImage(index);
  if (!img) return 0;
  const port = strip.getBoundingClientRect();
  const box = img.getBoundingClientRect();
  return box.left + box.width / 2 - (port.left + port.width / 2);
}

function glideTo(index, mode = "jump") {
  marker = index;
  picker.setAttribute("aria-valuenow", String(index + 1));
  picker.setAttribute("aria-valuetext", BUILDINGS[index].name);
  layoutTicks(index);
  const from = strip.scrollLeft;
  const to = from + centerDelta(index);
  if (reduce || Math.abs(to - from) < 1) {
    strip.scrollLeft = to;
    return;
  }
  const distance = Math.abs(to - from);
  const duration = mode === "scrub" ? 280 : mode === "step" ? 380 : Math.min(950, Math.max(520, 460 + distance * 0.08));
  const start = performance.now();
  cancelAnimationFrame(glide);
  const frame = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = t * t * t * (t * (t * 6 - 15) + 10);
    strip.scrollLeft = from + (to - from) * eased;
    if (t < 1) glide = requestAnimationFrame(frame);
  };
  glide = requestAnimationFrame(frame);
}

function layoutTicks(hot = marker) {
  const width = picker.clientWidth || 1;
  picker.replaceChildren();
  const date = document.createElement("span");
  date.className = "tl-date";
  date.textContent = dayLabel(BUILDINGS[hot].at);
  const count = BUILDINGS.length;
  const span = Math.max(1, count - 1);
  const left = 28;
  const right = width - 28;
  BUILDINGS.forEach((building, index) => {
    const tick = document.createElement("i");
    tick.className = "tl-tick";
    const x = count === 1 ? width / 2 : left + ((right - left) * index) / span;
    const distance = Math.abs(index - hot);
    const height = distance === 0 ? 34 : 22;
    tick.style.left = `${x}px`;
    tick.style.height = `${height}px`;
    tick.style.opacity = distance === 0 ? "1" : "0.72";
    picker.append(tick);
    if (index === hot) date.style.left = `${x}px`;
  });
  picker.append(date);
}

function indexFromPicker(clientX) {
  const bounds = picker.getBoundingClientRect();
  const t = Math.min(1, Math.max(0, (clientX - bounds.left) / bounds.width));
  return Math.round(t * (BUILDINGS.length - 1));
}

function heroFrame() {
  const width = Math.min(window.innerWidth * 0.34, 420);
  const height = width * (520 / 360);
  return new DOMRect((window.innerWidth - width) / 2, (window.innerHeight - height) / 2 - 12, width, height);
}

function placeFlyer(rect, building) {
  flyer.hidden = false;
  flyer.src = posterFor(building);
  flyer.alt = "";
  flyer.style.left = `${rect.left}px`;
  flyer.style.top = `${rect.top}px`;
  flyer.style.width = `${rect.width}px`;
  flyer.style.height = `${rect.height}px`;
  flyer.style.transform = "none";
}

function stopFlight() {
  flight?.cancel();
  flight = null;
}

function fadeDuringFlight(expanding) {
  const delay = Math.max(0, FLIGHT_MS - 250);
  if (expanding) {
    for (const el of [strip, picker]) {
      el.animate([{ opacity: 0 }, { opacity: 1 }], { delay, duration: 250, easing: "ease", fill: "none" });
    }
    return;
  }
  wrap.animate([{ opacity: 1 }, { opacity: 0 }], { delay, duration: 250, easing: "ease", fill: "forwards" });
}

function fly(from, to, expanding) {
  stopFlight();
  if (from.width < 1 || to.width < 1) {
    flyer.hidden = true;
    finishFlight(expanding);
    return;
  }
  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  const sx = to.width / from.width;
  const sy = to.height / from.height;
  placeFlyer(from, current());
  fadeDuringFlight(expanding);
  if (reduce) {
    flyer.hidden = true;
    finishFlight(expanding);
    return;
  }
  flight = flyer.animate(
    [
      { transform: "translate(0px, 0px) scale(1, 1)" },
      { transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
    ],
    { duration: FLIGHT_MS, easing: FLIGHT, fill: "forwards" },
  );
  flight.onfinish = () => {
    flight = null;
    flyer.hidden = true;
    wrap.getAnimations().forEach((animation) => animation.cancel());
    finishFlight(expanding);
  };
}

function finishFlight(expanding) {
  root.dataset.flying = "false";
  const img = itemImage(active);
  if (img) img.style.visibility = "";
  if (expanding) {
    root.dataset.settled = "true";
    root.dataset.heroHidden = "true";
    layoutTicks(active);
    return;
  }
  delete root.dataset.expanded;
  delete root.dataset.collapsing;
  delete root.dataset.settled;
  delete root.dataset.heroHidden;
  wrap.inert = true;
  timelineButton.inert = false;
  timelineButton.setAttribute("aria-expanded", "false");
  document.documentElement.style.overflow = "";
}

function openTimeline(immediate = false) {
  if (root.dataset.expanded === "true" && root.dataset.collapsing !== "true") return;
  renderStrip();
  root.dataset.expanded = "true";
  delete root.dataset.collapsing;
  delete root.dataset.settled;
  wrap.inert = false;
  timelineButton.inert = true;
  timelineButton.setAttribute("aria-expanded", "true");
  document.documentElement.style.overflow = "hidden";
  requestAnimationFrame(() => {
    strip.scrollLeft += centerDelta(active);
    layoutTicks(active);
    const img = itemImage(active);
    if (!img) return;
    const target = img.getBoundingClientRect();
    img.style.visibility = "hidden";
    if (immediate || reduce) {
      root.dataset.settled = "true";
      root.dataset.heroHidden = "true";
      img.style.visibility = "";
      return;
    }
    root.dataset.flying = "true";
    fly(heroFrame(), target, true);
  });
}

function closeTimeline() {
  if (root.dataset.expanded !== "true" || root.dataset.collapsing === "true") return;
  const img = itemImage(active);
  root.dataset.collapsing = "true";
  root.dataset.settled = "false";
  root.dataset.heroHidden = "false";
  if (!img || reduce) {
    finishFlight(false);
    return;
  }
  const from = img.getBoundingClientRect();
  img.style.visibility = "hidden";
  root.dataset.flying = "true";
  fly(from, heroFrame(), false);
}

function choose(index) {
  const img = itemImage(index);
  loadBuilding(index);
  if (root.dataset.expanded !== "true") return;
  root.dataset.collapsing = "true";
  root.dataset.settled = "false";
  root.dataset.heroHidden = "false";
  if (!img || reduce) {
    finishFlight(false);
    return;
  }
  const from = img.getBoundingClientRect();
  img.style.visibility = "hidden";
  root.dataset.flying = "true";
  fly(from, heroFrame(), false);
}

function reverseFlight(event) {
  if (!flight || flight.playState !== "running") return;
  const box = flyer.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) return;
  event.preventDefault();
  event.stopPropagation();
  const expanding = root.dataset.collapsing === "true";
  stopFlight();
  flyer.hidden = true;
  const img = itemImage(active);
  if (img) img.style.visibility = "";
  if (expanding) openTimeline();
  else closeTimeline();
}

themeButton.addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  const run = () => {
    document.documentElement.dataset.theme = next;
    applyTheme();
  };
  if (!reduce && document.startViewTransition) document.startViewTransition(run);
  else run();
});

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (!document.documentElement.dataset.theme) applyTheme();
});

viewer.addEventListener("load", () => {
  applyTheme();
});

let pointer = null;
viewer.addEventListener(
  "pointerdown",
  (event) => {
    if (event.button !== 0 || root.dataset.expanded === "true") return;
    pointer = { x: event.clientX, y: event.clientY, id: event.pointerId };
  },
  true,
);
viewer.addEventListener(
  "pointerup",
  (event) => {
    if (!pointer || pointer.id !== event.pointerId || root.dataset.expanded === "true") return;
    const moved = Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y);
    pointer = null;
    if (moved < 10) openTimeline();
  },
  true,
);
viewer.addEventListener("pointercancel", () => {
  pointer = null;
}, true);

timelineButton.addEventListener("click", () => {
  if (root.dataset.expanded !== "true") openTimeline();
});

wrap.addEventListener(
  "wheel",
  (event) => {
    if (event.target.closest(".tl-zone")) return;
    event.preventDefault();
    const delta = (Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY) * (event.deltaMode === 1 ? 24 : 1);
    strip.scrollLeft += delta;
  },
  { passive: false },
);

strip.addEventListener("scroll", () => {
  let nearest = 0;
  let best = Infinity;
  const mid = strip.getBoundingClientRect().left + strip.clientWidth / 2;
  BUILDINGS.forEach((_, index) => {
    const img = itemImage(index);
    if (!img) return;
    const box = img.getBoundingClientRect();
    const distance = Math.abs(box.left + box.width / 2 - mid);
    if (distance < best) {
      best = distance;
      nearest = index;
    }
  });
  if (nearest !== marker) {
    marker = nearest;
    layoutTicks(nearest);
  }
}, { passive: true });

let scrub = null;
picker.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  scrub = { x: event.clientX, moved: false, id: event.pointerId };
  picker.setPointerCapture(event.pointerId);
});
picker.addEventListener("pointermove", (event) => {
  if (!scrub || scrub.id !== event.pointerId) return;
  if (Math.abs(event.clientX - scrub.x) > 3) scrub.moved = true;
  if (scrub.moved) glideTo(indexFromPicker(event.clientX), "scrub");
});
function endScrub(event) {
  if (!scrub || (event && scrub.id !== event.pointerId)) return;
  const moved = scrub.moved;
  const x = event ? event.clientX : scrub.x;
  scrub = null;
  if (!moved) glideTo(indexFromPicker(x), "jump");
}
picker.addEventListener("pointerup", endScrub);
picker.addEventListener("pointercancel", endScrub);
picker.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight" || event.key === "ArrowUp") {
    event.preventDefault();
    glideTo(Math.min(BUILDINGS.length - 1, marker + 1), "step");
  } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
    event.preventDefault();
    glideTo(Math.max(0, marker - 1), "step");
  } else if (event.key === "Home") {
    event.preventDefault();
    glideTo(0, "jump");
  } else if (event.key === "End") {
    event.preventDefault();
    glideTo(BUILDINGS.length - 1, "jump");
  }
});

document.addEventListener("pointerdown", reverseFlight, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && root.dataset.expanded === "true" && root.dataset.settled === "true") {
    event.preventDefault();
    closeTimeline();
  }
});

window.addEventListener("hashchange", () => {
  if (location.hash === "#timeline" && root.dataset.expanded !== "true") openTimeline();
  else if (location.hash !== "#timeline" && root.dataset.settled === "true") closeTimeline();
});

renderStrip();
syncButton();
applyCamera(current());
layoutTicks(active);
if (location.hash === "#timeline") openTimeline(true);
