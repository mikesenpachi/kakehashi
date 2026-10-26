// Crop box tools on the shot page: draw a box, test it, use it for this shot only,
// save or clear it for the game (new shots only), or hide and show the outline.
// The outline shows the box that this shot's text came from.
// Hide box is per game: the choice is kept in this browser (localStorage), so every shot of the game opens the same way.
// Enlarge shows the image in a full-window viewer.
// Also saves manual edits of the text and of the translation, translates the text, renames the game,
// and copies the text, the translation or the image to the clipboard.
// A box is [left, top, right, bottom] as fractions of the image, 0 to 1.

const frame = document.getElementById("frame");
const saved = document.getElementById("saved");
const drawn = document.getElementById("drawn");
const values = document.getElementById("values");
const result = document.getElementById("result");
const testButton = document.getElementById("test");
const useButton = document.getElementById("use");
const saveButton = document.getElementById("save");
const clearButton = document.getElementById("clear");
const toggleButton = document.getElementById("toggle");
const translateButton = document.getElementById("translate");
const translation = document.getElementById("translation");
const copyTranslationButton = document.getElementById("copy-translation");
const editTranslationButton = document.getElementById("edit-translation");
const renameButton = document.getElementById("rename");
const copyButton = document.getElementById("copy");
const copyTextButton = document.getElementById("copy-text");
const gameName = document.getElementById("game-name");
const text = document.getElementById("text");
const shotId = frame.dataset.shot;
const game = frame.dataset.game;

let start = null;
let box = null;

function point(event) {
  const rect = frame.getBoundingClientRect();
  const clamp = (value) => Math.min(1, Math.max(0, value));
  return [clamp((event.clientX - rect.left) / rect.width), clamp((event.clientY - rect.top) / rect.height)];
}

function place(element, [left, top, right, bottom]) {
  element.style.left = `${left * 100}%`;
  element.style.top = `${top * 100}%`;
  element.style.width = `${(right - left) * 100}%`;
  element.style.height = `${(bottom - top) * 100}%`;
  element.hidden = false;
}

frame.addEventListener("pointerdown", (event) => {
  start = point(event);
  frame.setPointerCapture(event.pointerId);
});

frame.addEventListener("pointermove", (event) => {
  if (!start) return;
  const [x, y] = point(event);
  const round = (value) => Math.round(value * 1000) / 1000;
  box = [Math.min(start[0], x), Math.min(start[1], y), Math.max(start[0], x), Math.max(start[1], y)].map(round);
  place(drawn, box);
});

frame.addEventListener("pointerup", () => {
  start = null;
  if (!box || box[0] === box[2] || box[1] === box[3]) return;
  values.textContent = `Box: ${box.join(", ")}`;
  testButton.disabled = useButton.disabled = saveButton.disabled = false;
});

// Sends a change. A refused change (for example from another device without the token) shows why and stops.
async function send(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
  const answer = await response.json();
  if (!response.ok) {
    result.textContent = `Not done: ${answer.detail}`;
    throw new Error(answer.detail);
  }
  return answer;
}

testButton.addEventListener("click", async () => {
  result.textContent = "Reading...";
  const data = await send("POST", `/shot/${shotId}/test`, { box });
  result.textContent = `Test: ${data.text}`;
});

useButton.addEventListener("click", async () => {
  result.textContent = "Reading...";
  const data = await send("POST", `/shot/${shotId}/test`, { box });
  text.innerText = lastText = data.text;
  await send("POST", `/shot/${shotId}/text`, { text: data.text, box });
  place(saved, box);
  showSavedBox(true);
  toggleButton.hidden = false;
  result.textContent = "Text replaced with the box text, for this shot only. A game box will not overwrite it.";
});

const keepOld = "Old shots keep their text. To read one again with the box, draw it there and click Use for this shot.";

const hideKey = `hideBox:${game}`;

function showSavedBox(visible) {
  saved.hidden = !visible;
  toggleButton.textContent = visible ? "Hide box" : "Show box";
  if (visible) localStorage.removeItem(hideKey);
  else localStorage.setItem(hideKey, "1");
}

if (!toggleButton.hidden && localStorage.getItem(hideKey)) showSavedBox(false);

saveButton.addEventListener("click", async () => {
  await send("PUT", `/games/${game}/box`, { box });
  clearButton.hidden = false;
  saveButton.disabled = true;
  result.textContent = `Saved. New shots of this game use this box. ${keepOld}`;
});

clearButton.addEventListener("click", async () => {
  await send("DELETE", `/games/${game}/box`);
  clearButton.hidden = true;
  result.textContent = `Cleared. New shots of this game are read on the full screen. ${keepOld}`;
});

toggleButton.addEventListener("click", () => showSavedBox(saved.hidden));

// Delete game: after a confirm, delete the game (its shots, their image files, its name and box), then go home.
const deleteButton = document.getElementById("delete-game");
deleteButton.addEventListener("click", async () => {
  const name = gameName.textContent;
  const count = deleteButton.dataset.count;
  const shots = count === "1" ? "its 1 shot" : `all ${count} shots`;
  if (!confirm(`Delete the game ${name}? This deletes ${shots} (images and text), the game name and its crop box. This cannot be undone.`)) return;
  await send("DELETE", `/games/${game}`);
  location.href = "/";
});

// Delete shot: after a confirm, delete this shot and its image file, then open the next older shot of the game,
// or the home page when none is left.
document.getElementById("delete-shot").addEventListener("click", async () => {
  if (!confirm("Delete this shot? Its image and text are deleted from this computer. This cannot be undone.")) return;
  const reply = await send("DELETE", `/shot/${frame.dataset.shot}`);
  location.href = reply.next ? `/shot/${reply.next}` : "/";
});

// Enlarge: show the image as large as the window allows. A click anywhere or Esc closes it.
const viewer = document.getElementById("viewer");
document.getElementById("enlarge").addEventListener("click", () => viewer.showModal());
viewer.addEventListener("click", () => viewer.close());

// Translates the text as shown, with manual edits. The server saves the translation; a new click replaces it.
translateButton.addEventListener("click", async () => {
  if (!text.innerText.trim()) return;
  translation.textContent = "Translating...";
  const response = await fetch(`/shot/${shotId}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.innerText }),
  });
  const answer = await response.json();
  translation.textContent = response.ok ? answer.translation : `Cannot translate: ${answer.detail}`;
});

// Edit translation: the first click makes the translation editable, the second click saves it.
// An empty translation is saved as empty. A new "Translate" click replaces the edit.
editTranslationButton.addEventListener("click", async () => {
  if (!translation.isContentEditable) {
    translation.contentEditable = "true";
    translation.focus();
    editTranslationButton.textContent = "Save translation";
    return;
  }
  const answer = await send("POST", `/shot/${shotId}/translation`, { translation: translation.innerText });
  translation.contentEditable = "false";
  translation.textContent = answer.translation;
  editTranslationButton.textContent = "Edit translation";
});

// Shows a check sign on the button for 1.5 s. No message, so the image does not move.
function showCopied(button) {
  const label = (button.dataset.label ??= button.textContent);
  button.textContent = `${label} ✓`;
  setTimeout(() => (button.textContent = label), 1500);
}

// Copies a text to the clipboard and shows a check sign on the button.
async function copyText(button, value) {
  if (!window.isSecureContext) {
    result.textContent = "The browser allows copy only on http://localhost:8766, not on a network address.";
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    showCopied(button);
  } catch (error) {
    result.textContent = `Cannot copy the text: ${error.message}`;
  }
}

copyTextButton.addEventListener("click", () => copyText(copyTextButton, text.innerText));
copyTranslationButton.addEventListener("click", () => copyText(copyTranslationButton, translation.innerText));

// The clipboard takes PNG, so the image goes through a canvas. Browsers allow the clipboard
// only on secure pages: http://localhost works, http://<LAN address> does not.
copyButton.addEventListener("click", async () => {
  if (!window.isSecureContext) {
    result.textContent = "The browser allows copy only on http://localhost:8766, not on a network address.";
    return;
  }
  const image = frame.querySelector("img");
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.getContext("2d").drawImage(image, 0, 0);
  const png = new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
    showCopied(copyButton);
  } catch (error) {
    result.textContent = `Cannot copy the image: ${error.message}`;
  }
});

renameButton.addEventListener("click", async () => {
  const name = prompt(`Name for ${game}:`, gameName.textContent);
  if (!name || !name.trim()) return;
  await send("PUT", `/games/${game}/name`, { name });
  location.reload();
});

let lastText = text.innerText;
text.addEventListener("blur", async () => {
  if (text.innerText === lastText) return;
  lastText = text.innerText;
  await send("POST", `/shot/${shotId}/text`, { text: lastText });
  result.textContent = "Text saved. A new box will not overwrite it.";
});
