import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const TARGET_DIR = process.argv[2];
const PROFILE_DIR = path.resolve(".nr-chrome-profile");

if (!TARGET_DIR) {
  console.error("Usage: node scripts/nr_spanish_download.mjs <target-dir>");
  process.exit(1);
}

const targetDir = path.resolve(TARGET_DIR);
const files = await fs.readdir(targetDir);

const onceInput = files.find((name) => name.endsWith("__04a__shadowing_es__naturalreaders_input.txt"));
const repeatInput = files.find((name) => name.endsWith("__06a__shadowing_es_repeat__naturalreaders_input.txt"));

if (!onceInput || !repeatInput) {
  console.error("Spanish NaturalReaders input txt files not found in:", targetDir);
  console.error("Files found:", files.join(", "));
  process.exit(1);
}

const onceText = await fs.readFile(path.join(targetDir, onceInput), "utf-8");
const repeatText = await fs.readFile(path.join(targetDir, repeatInput), "utf-8");

const onceMp3 = onceInput.replace("__04a__shadowing_es__naturalreaders_input.txt", "__04__shadowing_es.mp3");
const repeatMp3 = repeatInput.replace("__06a__shadowing_es_repeat__naturalreaders_input.txt", "__06__shadowing_es_repeat.mp3");

console.log("Once MP3 target:", onceMp3);
console.log("Repeat MP3 target:", repeatMp3);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isLoggedIn(page) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  return /Library\s+\d+/i.test(bodyText) || /Welcome back/i.test(bodyText) || /Personal/i.test(bodyText);
}

async function removeOverlays(page) {
  await page.evaluate(() => {
    document.querySelectorAll("app-pw-single-page, .cdk-overlay-backdrop, .modal-overlay").forEach((el) => el.remove());
  }).catch(() => {});
}

async function dismissWelcome(page) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  if (/GO TO A\.I\. TEXT TO SPEECH/i.test(bodyText) || /Welcome to NaturalReader/i.test(bodyText)) {
    const languageSelect = page.locator("select").first();
    if (await languageSelect.count()) {
      await languageSelect.selectOption({ label: "Spanish (Spain)" }).catch(() => {});
      await sleep(500);
    }
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll("button"));
      const next = buttons.find((b) => (b.textContent || "").trim() === "Next") || buttons[buttons.length - 1];
      if (next) next.click();
    });
    await sleep(2500);
    const personalButton = page.locator("a.nr-btn, button").filter({ hasText: /Personal/i }).first();
    if (await personalButton.count()) {
      await personalButton.click();
      await sleep(4000);
    }
  }
}

async function ensureReadingMode(page) {
  // "Add Text" is the most reliable way to force the editor open
  // in the current NaturalReaders UI.
  const addTextBtn = page.locator("button, a, [role='button']").filter({ hasText: /^Add Text$/i }).first();
  if (await addTextBtn.count()) {
    await addTextBtn.click({ force: true }).catch(async () => {
      await addTextBtn.evaluate((el) => el.click());
    });
    await sleep(2500);
  }

  const readingNav = page.locator("button, a, [role='button']").filter({ hasText: /^Reading$/i }).first();
  if (await readingNav.count() && await readingNav.isVisible()) {
    await readingNav.click().catch(() => {});
    await sleep(1500);
  }

  await page.waitForFunction(
    () => !!document.querySelector("#inputDiv"),
    undefined,
    { timeout: 10000 },
  ).catch(() => {});
}

async function setLanguageToSpanish(page) {
  console.log("Setting language to Spanish (Spain)...");

  const voiceListBtn = page.locator("#voiceListBtn").first();
  if (await voiceListBtn.count()) {
    await voiceListBtn.click().catch(() => {});
    await sleep(1200);
  }

  const bodyText = await page.locator("body").innerText().catch(() => "");
  if (/Spanish \(Spain\)/i.test(bodyText)) {
    console.log("Language confirmed: Spanish (Spain)");
  } else {
    console.log("WARNING: Language may not be set correctly");
  }
}

async function selectPlusVoice(page) {
  console.log("Selecting Plus voice...");

  const voiceListBtn = page.locator("#voiceListBtn").first();
  if (await voiceListBtn.count()) {
    await voiceListBtn.click().catch(() => {});
    await sleep(1200);
  } else {
    const voiceSelector = page.locator("button, div, [role='button']").filter({ hasText: /voice|Voice/i }).first();
    if (await voiceSelector.count() && await voiceSelector.isVisible()) {
      await voiceSelector.click();
      await sleep(1500);
    }
  }

  // Find and click on "Plus" voices tab/filter
  const plusTab = page.locator("button, tab, [role='tab'], div, span, li")
    .filter({ hasText: /^Plus$/i })
    .first();
  if (await plusTab.count()) {
    await plusTab.click();
    await sleep(1000);
  }

  // Prefer Arabella (Spain), which is the target Plus voice for this project.
  const arabella = page.locator(".pw-voices-cell, .voice-card, .voice-item, [class*='voice-'], li, button, div")
    .filter({ hasText: /Arabella\\s*\\(Spain\\)/i })
    .first();
  if (await arabella.count()) {
    await arabella.click();
    await sleep(1000);
    console.log("Selected Arabella (Spain)");
    await page.keyboard.press("Escape").catch(() => {});
    await sleep(500);
    return;
  }

  const plusVoice = page.locator(".pw-voices-cell, .voice-card, .voice-item, [class*='voice-'], li, button, div")
    .filter({ hasText: /\\(Spain\\)/i })
    .first();
  if (await plusVoice.count()) {
    await plusVoice.click();
    await sleep(1000);
    console.log("Selected first available Spain voice");
    await page.keyboard.press("Escape").catch(() => {});
    await sleep(500);
  }
}

async function typeIntoEditor(page, text) {
  if (!(await page.locator("#inputDiv").count())) {
    const addTextBtn = page.locator("button, a, [role='button']").filter({ hasText: /^Add Text$/i }).first();
    if (await addTextBtn.count()) {
      await addTextBtn.click({ force: true }).catch(() => {});
      await sleep(1500);
    }
  }

  // NaturalReaders now keeps the primary editor in #inputDiv.
  const inputDiv = page.locator("#inputDiv").first();
  if (await inputDiv.count()) {
    console.log("Found #inputDiv");
    await inputDiv.click({ force: true }).catch(() => {});
    await page.evaluate((value) => {
      const el = document.querySelector("#inputDiv");
      const ce = document.querySelector('[contenteditable="true"]');
      if (el) {
        el.innerHTML = "";
        el.textContent = value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (ce) {
        ce.innerHTML = value.replace(/\n/g, "<br>");
        ce.dispatchEvent(new Event("input", { bubbles: true }));
        ce.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }, text);
    await sleep(1200);

    // Select all text because MP3 Download expects a selected range.
    await inputDiv.click({ force: true }).catch(() => {});
    await page.keyboard.press("Control+A").catch(() => {});
    await sleep(300);

    const content = await inputDiv.innerText().catch(() => "");
    if (content.length > 10) {
      console.log("Text entered into #inputDiv, length:", content.length);
      return true;
    }
  }

  // Fallback: contenteditable
  const editable = page.locator('[contenteditable="true"]').first();
  if (await editable.count()) {
    console.log("Found contenteditable editor");
    await editable.click();
    await page.keyboard.press("Control+A");
    await page.keyboard.press("Backspace");
    await page.keyboard.type(text, { delay: 5 });
    await sleep(1000);
    console.log("Text entered into contenteditable");
    return true;
  }

  // Fallback: textarea
  const textarea = page.locator("textarea").first();
  if (await textarea.count()) {
    await textarea.fill(text);
    await sleep(1000);
    console.log("Text entered into textarea");
    return true;
  }

  console.error("Could not find text input area");
  return false;
}

async function clickConvertNow(page) {
  const convertBtn = page.locator('button[aria-label="convert now button"]').first();
  if (await convertBtn.count()) {
    await convertBtn.click({ force: true }).catch(async () => {
      await convertBtn.evaluate((el) => el.click());
    });
    console.log("Clicked Convert Now");
    return true;
  }
  return false;
}

async function waitForAndDownload(page, filename) {
  console.log("Waiting for conversion and download link...");

  const deadline = Date.now() + 300000; // 5 minutes max

  while (Date.now() < deadline) {
    await sleep(3000);

    // Check for direct mp3 URL in DOM
    const href = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll("a[href]"));
      const mp3Link = links.find((link) => {
        const href = link.getAttribute("href") || "";
        return /^https?:/i.test(href) && /\.mp3(?:$|\?)/i.test(href);
      });
      return mp3Link?.getAttribute("href") || null;
    }).catch(() => null);

    if (href) {
      console.log("Found direct MP3 URL:", href.substring(0, 80) + "...");
      const response = await page.request.get(href, { timeout: 120000 });
      if (response.ok()) {
        const body = await response.body();
        await fs.writeFile(path.join(targetDir, filename), body);
        console.log("Downloaded via direct URL:", filename, "size:", body.length);
        return true;
      }
    }

    // Check for download button
    const downloadBtn = page.locator("button, a, [role='button']")
      .filter({ hasText: /download/i })
      .first();

    if (await downloadBtn.count() && await downloadBtn.isVisible()) {
      console.log("Found download button");
      try {
        const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
        await downloadBtn.click();
        const download = await downloadPromise;
        await download.saveAs(path.join(targetDir, filename));
        console.log("Downloaded via button:", filename);
        return true;
      } catch (e) {
        console.log("Download button click failed, retrying...", e.message);
      }
    }

    // Check for "Converting" state - still processing
    const bodyText = await page.locator("body").innerText().catch(() => "");
    if (/converting/i.test(bodyText)) {
      console.log("Still converting...");
      continue;
    }

    // Check if email notification
    if (/email|mailbox|inbox|sent to/i.test(bodyText)) {
      console.error("Audio was deferred to email by NaturalReaders");
      return false;
    }

    // Check for "Go to Audio Library" link
    const libraryBtn = page.locator("button, a").filter({ hasText: /audio library/i }).first();
    if (await libraryBtn.count() && await libraryBtn.isVisible()) {
      console.log("Found 'Go to Audio Library' button");
      await libraryBtn.click();
      await sleep(5000);

      // Try to find download in library
      const libDownload = page.locator("button, a").filter({ hasText: /download/i }).first();
      if (await libDownload.count()) {
        try {
          const downloadPromise = page.waitForEvent("download", { timeout: 120000 });
          await libDownload.click();
          const download = await downloadPromise;
          await download.saveAs(path.join(targetDir, filename));
          console.log("Downloaded from library:", filename);
          return true;
        } catch (e) {
          console.log("Library download failed:", e.message);
        }
      }
    }
  }

  console.error("Timeout waiting for MP3");
  return false;
}

async function generateOne(page, text, filename) {
  console.log(`\n=== Generating: ${filename} ===`);

  // Navigate to fresh page
  await page.goto("https://www.naturalreaders.com/online/", { waitUntil: "domcontentloaded" });
  await sleep(6000);

  // Dismiss overlays
  await dismissWelcome(page);
  await removeOverlays(page);
  await sleep(1000);

  // Ensure reading mode
  await ensureReadingMode(page);
  await sleep(2000);

  // Set language
  await setLanguageToSpanish(page);

  // Select Plus voice
  await selectPlusVoice(page);

  // Type text
  const typed = await typeIntoEditor(page, text);
  if (!typed) {
    throw new Error("Could not enter text into editor");
  }

  // Click MP3 download button
  const mp3Btn = page.getByRole("button", { name: "MP3 Download", exact: true });
  if (!(await mp3Btn.count())) {
    // Try alternative button
    const altMp3 = page.locator("button, [role='button']").filter({ hasText: /MP3/i }).first();
    if (await altMp3.count()) {
      await altMp3.click();
    } else {
      throw new Error("MP3 Download button not found");
    }
  } else {
    await mp3Btn.click();
  }

  await sleep(2000);

  // Click Convert Now
  const converted = await clickConvertNow(page);
  if (!converted) {
    // Maybe download is directly available
    console.log("Convert Now button not found, looking for download...");
  }

  await sleep(5000);

  // Wait for and download
  const success = await waitForAndDownload(page, filename);
  if (!success) {
    throw new Error(`Failed to download ${filename}`);
  }

  // Verify file exists and has content
  const stat = await fs.stat(path.join(targetDir, filename));
  console.log(`File saved: ${filename} (${stat.size} bytes)`);
  return true;
}

// Main
console.log("Launching browser with persistent profile...");
const context = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: "chrome",
  headless: false,
  acceptDownloads: true,
  viewport: { width: 1440, height: 900 },
});

const pages = context.pages();
const page = pages.length ? pages[0] : await context.newPage();

try {
  // Check if already logged in
  await page.goto("https://www.naturalreaders.com/online/", { waitUntil: "domcontentloaded" });
  await sleep(6000);
  await dismissWelcome(page);
  await removeOverlays(page);

  const loggedIn = await isLoggedIn(page);
  if (!loggedIn) {
    console.error("Not logged in to NaturalReaders. Cannot proceed without credentials.");
    console.error("Please set NR_EMAIL and NR_PASSWORD environment variables.");
    process.exit(1);
  }

  console.log("Logged in to NaturalReaders");

  // Generate once MP3
  const onceExists = await fs.stat(path.join(targetDir, onceMp3)).then(() => true).catch(() => false);
  if (!onceExists) {
    await generateOne(page, onceText, onceMp3);
  } else {
    console.log("Once MP3 already exists, skipping");
  }

  // Generate repeat MP3
  const repeatExists = await fs.stat(path.join(targetDir, repeatMp3)).then(() => true).catch(() => false);
  if (!repeatExists) {
    await generateOne(page, repeatText, repeatMp3);
  } else {
    console.log("Repeat MP3 already exists, skipping");
  }

  console.log("\nAll downloads complete!");
} catch (e) {
  console.error("Error:", e.message);
  process.exit(1);
} finally {
  await context.close();
}
