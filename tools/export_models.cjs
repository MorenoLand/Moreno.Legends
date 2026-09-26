const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("../build/automation/node_modules/playwright");
const root = path.resolve(__dirname, "..");
const dat = path.join(root, "build", "disc-assets", "DAT");
const inputDir = process.env.MML2_ASSET_DIR || dat;
const mode = process.argv[2] || "--list";
const wanted = process.argv[3] || "";
function writeIfChanged(file, bytes) {
    if (fs.existsSync(file) && fs.statSync(file).size === bytes.length && fs.readFileSync(file).equals(bytes)) return false;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const temporary = file + ".tmp";
    fs.writeFileSync(temporary, bytes);
    fs.renameSync(temporary, file);
    return true;
}

async function main() {
    const files = fs.readdirSync(inputDir).filter(name => name.toUpperCase().endsWith(".BIN")).sort().map(name => path.join(inputDir, name));
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    page.on("pageerror", error => process.stderr.write(error.message + "\n"));
    page.on("console", message => { if (message.type() === "error") process.stderr.write(message.text() + "\n"); });
    try {
        const response = await page.goto("http://127.0.0.1:8765/");
        if (!response || !response.ok()) throw new Error("DashGL viewer did not load");
        await page.locator("#files").setInputFiles(files);
        await page.waitForFunction(() => document.querySelectorAll("#archive_list li").length > 0, null, { timeout: 120000 });
        const archives = await page.locator("#archive_list li").allTextContents();
        if (mode === "--list") {
            process.stdout.write(archives.join("\n") + "\n");
            return;
        }
        const selectedArchives = mode === "--all" ? archives : [archives.find(name => name.trim().toUpperCase() === wanted.toUpperCase())].filter(Boolean);
        if (!selectedArchives.length) throw new Error("archive not found: " + wanted);
        if (mode === "--inspect") {
            const archive = selectedArchives[0].trim();
            await page.locator("#archive_list li").filter({ hasText: archive }).first().click();
            await page.waitForFunction(() => document.getElementById("asset_list")?.classList.contains("open") && document.querySelectorAll("#model_list li").length > 0, null, { timeout: 30000 });
            process.stdout.write(JSON.stringify(await page.evaluate(() => Object.fromEntries(["archive_file_name", "archive_list", "asset_list", "model_list"].map(id => [id, document.getElementById(id)?.innerHTML]))), null, 2) + "\n");
            return;
        }
        for (let archiveIndex = 0; archiveIndex < selectedArchives.length; archiveIndex++) {
            const archive = selectedArchives[archiveIndex].trim();
            await page.locator("#archive_list li").filter({ hasText: archive }).first().click();
            await page.waitForFunction(() => document.getElementById("asset_list")?.classList.contains("open") && document.querySelectorAll("#model_list li").length > 0, null, { timeout: 30000 });
            const models = await page.locator("#model_list li").allTextContents();
            process.stdout.write(`${archive}: ${models.map(name => name.trim()).join(", ")}\n`);
            for (let modelIndex = 0; modelIndex < models.length; modelIndex++) {
                const rawName = models[modelIndex];
                const model = rawName.trim();
                if (!model) continue;
                const name = `${path.parse(archive).name}_${model.replace(/[^A-Za-z0-9_-]/g, "_")}`;
                await page.locator("#model_list li").nth(modelIndex).click();
                if (mode === "--preview") {
                    const previewDir = path.join(root, "build", "model-previews");
                    writeIfChanged(path.join(previewDir, `${name}.png`), await page.locator("#main").screenshot());
                    continue;
                }
                await page.locator("#export_name").fill(name);
                const upload = page.waitForResponse(r => r.url().includes("/upload/") && r.request().method() === "POST", { timeout: 30000 });
                await page.locator("#export_model").click();
                const result = await upload;
                if (!result.ok()) throw new Error(`${name}: export rejected (${result.status()})`);
                process.stdout.write(`${name}.glb\n`);
            }
            if (archiveIndex + 1 < selectedArchives.length) {
                await page.locator("#back").click();
                await page.waitForFunction(() => !document.getElementById("asset_list")?.classList.contains("open") && document.querySelectorAll("#archive_list li").length > 0, null, { timeout: 30000 });
            }
        }
    } finally {
        await browser.close();
    }
}

main().catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
