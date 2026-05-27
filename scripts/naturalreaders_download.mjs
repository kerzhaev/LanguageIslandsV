import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const EMAIL = process.env.NR_EMAIL;
const PASSWORD = process.env.NR_PASSWORD;
const TARGET_DIR = process.argv[2];
const PROFILE_DIR = path.resolve(".nr-chrome-profile");

if (!EMAIL || !PASSWORD) {
  console.error("Missing NR_EMAIL or NR_PASSWORD.");
  process.exit(1);
}

if (!TARGET_DIR) {
  console.error("Usage: node scripts/naturalreaders_download.mjs <target-dir>");
  process.exit(1);
}

const targetDir = path.resolve(TARGET_DIR);
const onceInput = (await fs.readdir(targetDir)).find((name) => name.endsWith("__04a__shadowing_en__naturalreaders_input.txt"));
const repeatInput = (await fs.readdir(targetDir)).find((name) => name.endsWith("__06a__shadowing_en_repeat__naturalreaders_input.txt"));

if (!onceInput || !repeatInput) {
  console.error("NaturalReaders input txt files not found.");
  process.exit(1);
}

const onceText = await fs.readFile(path.join(targetDir, onceInput), "utf-8");
const repeatText = await fs.readFile(path.join(targetDir, repeatInput), "utf-8");

const onceMp3 = onceInput.replace("__04a__shadowing_en__naturalreaders_input.txt", "__04__shadowing_en.mp3");
const repeatMp3 = repeatInput.replace("__06a__shadowing_en_repeat__naturalreaders_input.txt", "__06__shadowing_en_repeat.mp3");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function clickIfVisible(page, locator) {
  if (await locator.count()) {
    const first = locator.first();
    if (await first.isVisible()) {
      await first.click();
      return true;
    }
  }
  return false;
}

async function removeWelcomeOverlay(page) {
  await page.evaluate(() => {
    document.querySelector("app-pw-single-page")?.remove();
  }).catch(() => {});
}

async function dismissWelcome(page) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  if (/GO TO A\.I\. TEXT TO SPEECH/i.test(bodyText) || /Welcome to NaturalReader/i.test(bodyText)) {
    const languageSelect = page.locator("select").first();
    if (await languageSelect.count()) {
      await languageSelect.selectOption({ label: "English (US)" }).catch(() => {});
      await sleep(500);
    }

    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const next =
        buttons.find((b) => (b.textContent || "").trim() === "Next") || buttons[buttons.length - 1];
      if (next) next.click();
    });
    await sleep(2500);

    const personalButton = page.locator("a.nr-btn").first();
    if (await personalButton.count()) {
      await personalButton.click();
      await sleep(4000);
    }
  }
}

async function isLoggedIn(page) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  return /Library\s+\d+/i.test(bodyText) || /Welcome back to NaturalReader!/i.test(bodyText);
}

async function openLoginDialog(page) {
  await page.evaluate(() => {
    const loginButton = Array.from(document.querySelectorAll("button")).find(
      (btn) => (btn.textContent || "").trim() === "Login",
    );
    if (loginButton) loginButton.click();
  });
}

async function clickButtonByText(page, text) {
  const escaped = text.replace(/"/g, '\\"');
  await page.evaluate((label) => {
    const candidates = Array.from(document.querySelectorAll("button, [role='button']"));
    const target = candidates.find((el) => ((el.textContent || "").trim() === label));
    if (target) {
      target.click();
    }
  }, text);
}

async function ensureLoggedIn(page) {
  await page.goto("https://www.naturalreaders.com/online/", { waitUntil: "domcontentloaded" });
  await sleep(5000);
  await dismissWelcome(page);
  await removeWelcomeOverlay(page);
  await sleep(1000);

  if (await isLoggedIn(page)) {
    return;
  }

  await openLoginDialog(page);
  await sleep(1500);

  const emailByType = page.locator('input[type="email"]').first();
  if (await emailByType.count()) {
    await emailByType.fill(EMAIL);
  } else {
    const emailByPlaceholder = page.getByPlaceholder("Your Email").first();
    if (await emailByPlaceholder.count()) await emailByPlaceholder.fill(EMAIL);
  }
  await clickButtonByText(page, "Next");
  await sleep(1500);

  const passwordByType = page.locator('input[type="password"]').first();
  if (await passwordByType.count()) {
    await passwordByType.fill(PASSWORD);
  } else {
    const passByPlaceholder = page.getByPlaceholder(/password/i).first();
    if (await passByPlaceholder.count()) await passByPlaceholder.fill(PASSWORD);
  }
  await clickButtonByText(page, "Next");
  await sleep(6000);
  await removeWelcomeOverlay(page);

  if (!(await isLoggedIn(page))) {
    throw new Error("NaturalReaders login did not complete.");
  }
}

async function clearAndTypeText(page, text) {
  const candidates = [
    page.locator("textarea").first(),
    page.locator("[contenteditable='true']").first(),
  ];
  for (const candidate of candidates) {
    if (await candidate.count()) {
      await candidate.click();
      if (candidate === candidates[0]) {
        await candidate.fill(text);
      } else {
        await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
        await page.keyboard.press("Backspace");
        await page.keyboard.type(text);
      }
      return;
    }
  }
  throw new Error("Text input area not found.");
}

async function ensureReadingPage(page) {
  const readingBack = page.locator('button[aria-label="reading button"]').first();
  if (await readingBack.count()) {
    await readingBack.click().catch(async () => {
      await readingBack.evaluate((el) => el.click());
    });
    await sleep(2000);
  }

  const readingButtons = page.locator("button, [role='button']").filter({ hasText: /^Reading$/i });
  if (await readingButtons.count()) {
    const first = readingButtons.first();
    await first.click().catch(async () => {
      await first.evaluate((el) => el.click());
    });
    await sleep(2000);
  }
}

async function clickConvertNow(page) {
  const convertButton = page
    .locator("button, [role='button'], .mat-button-wrapper, span, div")
    .filter({ hasText: /convert now/i })
    .first();
  if (!(await convertButton.count())) {
    throw new Error("Convert now button not found.");
  }
  await convertButton.click();
}

async function triggerDownload(page, filename) {
  const downloadPromise = page.waitForEvent("download", { timeout: 180000 });
  const audioLike = page.locator("button, a").filter({ hasText: /Download|MP3|Export|Save/i }).first();
  if (!(await audioLike.count())) {
    throw new Error("Download button not found after conversion.");
  }
  await audioLike.click();
  const download = await downloadPromise;
  await download.saveAs(path.join(targetDir, filename));
}

async function generateOne(page, text, filename) {
  await page.goto("https://www.naturalreaders.com/online/", { waitUntil: "domcontentloaded" });
  await sleep(5000);
  await dismissWelcome(page);
  await ensureReadingPage(page);
  let editable = page.locator('[contenteditable="true"]').first();
  if (!(await editable.count())) {
    const pasteText = page.locator('button[aria-label="paste text button [reading page]"]').first();
    if (await pasteText.count()) {
      await pasteText.click().catch(() => {});
      await sleep(2000);
      editable = page.locator('[contenteditable="true"]').first();
    }
  }
  if (!(await editable.count())) {
    throw new Error("Editable text area not found.");
  }
  await editable.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.press("Backspace");
  await page.keyboard.type(text, { delay: 10 });
  await sleep(1500);

  const mp3Menu = page.getByRole("button", { name: "MP3 Download", exact: true });
  if (!(await mp3Menu.count())) {
    throw new Error("MP3 Download button not found.");
  }
  await mp3Menu.click();
  await sleep(1500);

  await clickConvertNow(page);
  await sleep(5000);

  async function getDialogDownloadHref() {
    return page.evaluate(() => {
      const links = Array.from(document.querySelectorAll("mat-dialog-container a[href]"));
      const preferred = links.find((link) => {
        const text = (link.textContent || "").trim();
        const href = link.getAttribute("href") || "";
        return /download/i.test(text) && /^https?:/i.test(href);
      });
      if (preferred) return preferred.getAttribute("href");

      const mp3Link = links.find((link) => {
        const href = link.getAttribute("href") || "";
        return /^https?:/i.test(href) && /\.mp3(?:$|\?)/i.test(href);
      });
      return mp3Link?.getAttribute("href") || null;
    }).catch(() => null);
  }

  const directDownload = page.locator("a, button, [role='button']").filter({ hasText: /download/i }).first();
  const emailNotice = page.locator("body");
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const directHref = await getDialogDownloadHref();
    if (directHref || (await directDownload.count())) {
      break;
    }
    const bodyText = await emailNotice.innerText().catch(() => "");
    if (/email|mailbox|inbox|sent to/i.test(bodyText)) {
      throw new Error("Audio export was deferred to email by NaturalReaders.");
    }
    await sleep(3000);
  }

  if (!(await directDownload.count())) {
    const directHref = await getDialogDownloadHref();
    if (!directHref) {
      throw new Error("Download link not found after conversion.");
    }
  }

  const href = (await getDialogDownloadHref()) || (await directDownload.getAttribute("href"));
  if (href && /^https?:/i.test(href)) {
    const response = await page.request.get(href, { timeout: 180000 });
    if (!response.ok()) {
      throw new Error(`Download request failed with status ${response.status()}.`);
    }
    const body = await response.body();
    await fs.writeFile(path.join(targetDir, filename), body);
    return;
  }

  const downloadPromise = page.waitForEvent("download", { timeout: 180000 });
  await directDownload.click();
  const download = await downloadPromise;
  await download.saveAs(path.join(targetDir, filename));
}

const context = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: "chrome",
  headless: false,
  acceptDownloads: true,
  viewport: { width: 1440, height: 900 },
});
const pages = context.pages();
const page = pages.length ? pages[0] : await context.newPage();

try {
  await ensureLoggedIn(page);
  if (!(await fs.stat(path.join(targetDir, onceMp3)).then(() => true).catch(() => false))) {
    await generateOne(page, onceText, onceMp3);
  }
  if (!(await fs.stat(path.join(targetDir, repeatMp3)).then(() => true).catch(() => false))) {
    await generateOne(page, repeatText, repeatMp3);
  }
  console.log("Downloads finished.");
} finally {
  await context.close();
}
