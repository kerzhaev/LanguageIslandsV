import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const PROFILE_DIR = path.resolve(".nr-chrome-profile");
const targetDirs = process.argv.slice(2).map((arg) => path.resolve(arg));

if (!targetDirs.length) {
  console.error("Usage: node scripts/nr_english_profile_download_current.mjs <target-dir> [<target-dir>...]");
  process.exit(1);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fileExists(p) {
  return fs.stat(p).then(() => true).catch(() => false);
}

async function readJob(targetDir) {
  const files = await fs.readdir(targetDir);
  const onceInput = files.find((name) => name.endsWith("__04a__shadowing_en__naturalreaders_input.txt"));
  const repeatInput = files.find((name) => name.endsWith("__06a__shadowing_en_repeat__naturalreaders_input.txt"));
  if (!onceInput || !repeatInput) {
    throw new Error(`English NaturalReaders inputs not found in ${targetDir}`);
  }

  return {
    targetDir,
    onceText: await fs.readFile(path.join(targetDir, onceInput), "utf-8"),
    repeatText: await fs.readFile(path.join(targetDir, repeatInput), "utf-8"),
    onceMp3: path.join(
      targetDir,
      onceInput.replace("__04a__shadowing_en__naturalreaders_input.txt", "__04__shadowing_en.mp3"),
    ),
    repeatMp3: path.join(
      targetDir,
      repeatInput.replace("__06a__shadowing_en_repeat__naturalreaders_input.txt", "__06__shadowing_en_repeat.mp3"),
    ),
  };
}

async function backupIfExists(filePath) {
  if (!(await fileExists(filePath))) return null;
  const bak = `${filePath}.bak-before-nr`;
  if (await fileExists(bak)) {
    await fs.unlink(bak);
  }
  await fs.rename(filePath, bak);
  return bak;
}

async function restoreBackupIfMissing(originalPath, backupPath) {
  if (!backupPath) return;
  if (await fileExists(originalPath)) return;
  if (await fileExists(backupPath)) {
    await fs.rename(backupPath, originalPath);
  }
}

async function discardBackupIfSuccess(originalPath, backupPath) {
  if (!backupPath) return;
  if (await fileExists(originalPath) && await fileExists(backupPath)) {
    await fs.unlink(backupPath);
  }
}

async function openEditor(page) {
  await page.goto("https://www.naturalreaders.com/online/", { waitUntil: "domcontentloaded" });
  await sleep(6000);

  const addTextBtn = page.locator("button, a, [role='button']").filter({ hasText: /^Add Text$/i }).first();
  if (!(await addTextBtn.count())) {
    throw new Error("Add Text button not found");
  }
  await addTextBtn.click({ force: true }).catch(async () => {
    await addTextBtn.evaluate((el) => el.click());
  });
  await sleep(2500);

  await page.waitForFunction(() => !!document.querySelector("#inputDiv"), undefined, { timeout: 15000 });
}

async function openVoiceDialog(page) {
  const voiceListBtn = page.locator("#voiceListBtn").first();
  if (!(await voiceListBtn.count())) {
    throw new Error("Voice list button not found");
  }
  await voiceListBtn.click({ force: true }).catch(async () => {
    await voiceListBtn.evaluate((el) => el.click());
  });
  await sleep(1500);
}

async function selectEnglishUsAva(page) {
  await openVoiceDialog(page);

  const langTrigger = page.locator(".btn-language-trigger, .pw-voices-header-lang").first();
  if (!(await langTrigger.count())) {
    throw new Error("Language trigger not found in voice dialog");
  }
  await langTrigger.click({ force: true }).catch(async () => {
    await langTrigger.evaluate((el) => el.click());
  });
  await sleep(1500);

  await page.evaluate(() => {
    const items = Array.from(
      document.querySelectorAll(".lan-text, .mat-list-text, .mat-list-item-content, button, div, span"),
    );
    const target = items.find((el) => (el.textContent || "").trim() === "English (US)");
    if (target) target.click();
  });
  await sleep(2500);

  const bodyAfterLang = await page.locator("body").innerText().catch(() => "");
  if (!/English \(US\)/i.test(bodyAfterLang)) {
    throw new Error("English (US) language was not selected");
  }

  const plusTab = page.locator("button").filter({ hasText: /^Plus$/i }).first();
  if (await plusTab.count()) {
    await plusTab.click({ force: true }).catch(async () => {
      await plusTab.evaluate((el) => el.click());
    });
    await sleep(800);
  }

  const ava = page.locator(".pw-voices-cell").filter({ hasText: /^Ava\s*\(US\)/i }).first();
  if (!(await ava.count())) {
    throw new Error("Ava (US) Plus voice not found");
  }
  await ava.click({ force: true }).catch(async () => {
    await ava.evaluate((el) => el.click());
  });
  await sleep(1000);

  await page.keyboard.press("Escape").catch(() => {});
  await sleep(600);
}

async function fillText(page, text) {
  await page.evaluate((value) => {
    const inputDiv = document.querySelector("#inputDiv");
    const contentEditable = document.querySelector('[contenteditable="true"]');
    if (inputDiv) {
      inputDiv.innerHTML = "";
      inputDiv.textContent = value;
      inputDiv.dispatchEvent(new Event("input", { bubbles: true }));
      inputDiv.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (contentEditable) {
      contentEditable.innerHTML = value.replace(/\n/g, "<br>");
      contentEditable.dispatchEvent(new Event("input", { bubbles: true }));
      contentEditable.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }, text);
  await sleep(1200);

  const editor = page.locator("#inputDiv").first();
  await editor.click({ force: true }).catch(() => {});
  await page.evaluate(() => {
    const el = document.querySelector("#inputDiv");
    if (!el) return;
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    selection?.removeAllRanges();
    selection?.addRange(range);
  }).catch(() => {});
  await page.keyboard.press("Control+A").catch(() => {});
  await sleep(300);

  const content = await editor.innerText().catch(() => "");
  if (content.length < 10) {
    throw new Error("Text was not inserted into #inputDiv");
  }
}

async function triggerMp3Dialog(page) {
  const mp3Button = page.locator("button, [role='button']").filter({ hasText: /^MP3 Download$/i }).first();
  if (!(await mp3Button.count())) {
    throw new Error("MP3 Download button not found");
  }
  await mp3Button.click({ force: true }).catch(async () => {
    await mp3Button.evaluate((el) => el.click());
  });
  await sleep(1200);

  const convertNow = page.locator('button[aria-label="convert now button"]').first();
  if (!(await convertNow.count())) {
    return;
  }
  await convertNow.click({ force: true }).catch(async () => {
    await convertNow.evaluate((el) => el.click());
  });
}

async function waitForAndDownload(page, outputPath) {
  const deadline = Date.now() + 480000;

  while (Date.now() < deadline) {
    await sleep(3000);

    const directHref = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll("a[href]"));
      const preferred = links.find((a) => {
        const href = a.getAttribute("href") || "";
        const text = (a.textContent || "").trim();
        return /^https?:/i.test(href) && (/\.mp3(?:$|\?)/i.test(href) || /^download$/i.test(text));
      });
      return preferred?.getAttribute("href") || null;
    }).catch(() => null);

    if (directHref) {
      const response = await page.request.get(directHref, { timeout: 180000 });
      if (!response.ok()) {
        throw new Error(`Direct MP3 request failed: ${response.status()}`);
      }
      const body = await response.body();
      await fs.writeFile(outputPath, body);
      return;
    }

    const downloadBtn = page.locator("button, a, [role='button']").filter({ hasText: /^Download$/i }).first();
    if (await downloadBtn.count()) {
      const downloadPromise = page.waitForEvent("download", { timeout: 120000 }).catch(() => null);
      await downloadBtn.click({ force: true }).catch(async () => {
        await downloadBtn.evaluate((el) => el.click());
      });
      const download = await downloadPromise;
      if (download) {
        await download.saveAs(outputPath);
        return;
      }
    }

    const bodyText = await page.locator("body").innerText().catch(() => "");
    if (/email|mailbox|inbox|sent to/i.test(bodyText)) {
      throw new Error("NaturalReaders deferred the audio to email");
    }
  }

  const debugText = await page.locator("body").innerText().catch(() => "");
  const debugHtml = await page.content().catch(() => "");
  const debugLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("a[href]")).map((a) => ({
      text: (a.textContent || "").trim(),
      href: a.getAttribute("href") || "",
    }));
  }).catch(() => []);
  await fs.writeFile(`${outputPath}.timeout.txt`, debugText, "utf-8");
  await fs.writeFile(`${outputPath}.timeout.html`, debugHtml, "utf-8");
  await fs.writeFile(`${outputPath}.timeout.links.json`, JSON.stringify(debugLinks, null, 2), "utf-8");

  throw new Error("Timed out waiting for MP3 download");
}

async function generateOne(page, text, outputPath) {
  await openEditor(page);
  await selectEnglishUsAva(page);
  await fillText(page, text);
  await triggerMp3Dialog(page);
  await waitForAndDownload(page, outputPath);
}

const jobs = await Promise.all(targetDirs.map(readJob));
const context = await chromium.launchPersistentContext(PROFILE_DIR, {
  channel: "chrome",
  headless: false,
  acceptDownloads: true,
  viewport: { width: 1440, height: 900 },
});
const page = context.pages()[0] || await context.newPage();

try {
  for (const job of jobs) {
    console.log(`\n=== ${job.targetDir} ===`);

    const onceBak = await backupIfExists(job.onceMp3);
    const repeatBak = await backupIfExists(job.repeatMp3);

    try {
      await generateOne(page, job.onceText, job.onceMp3);
      await generateOne(page, job.repeatText, job.repeatMp3);
      await discardBackupIfSuccess(job.onceMp3, onceBak);
      await discardBackupIfSuccess(job.repeatMp3, repeatBak);
      console.log(`Completed ${job.targetDir}`);
    } catch (error) {
      await restoreBackupIfMissing(job.onceMp3, onceBak);
      await restoreBackupIfMissing(job.repeatMp3, repeatBak);
      throw error;
    }
  }
} finally {
  await context.close();
}
