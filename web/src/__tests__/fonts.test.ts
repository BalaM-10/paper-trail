// @vitest-environment node
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const web = fileURLToPath(new URL("../../", import.meta.url));
const read = (...parts: string[]) => readFileSync(join(web, ...parts), "utf8");

describe("the printing font is self-hosted and openly licensed", () => {
  it("is a dependency, and is imported by the app", () => {
    const pkg = JSON.parse(read("package.json"));
    expect(Object.keys(pkg.dependencies)).toContain("@fontsource/doto");
    expect(read("src", "main.tsx")).toMatch(/import "@fontsource\/doto\/latin-900\.css";/);
  });

  it("is under the SIL Open Font Licence, and its files are in the package", () => {
    const dir = join(web, "node_modules", "@fontsource", "doto");
    expect(JSON.parse(readFileSync(join(dir, "package.json"), "utf8")).license).toBe("OFL-1.1");
    const stylesheet = readFileSync(join(dir, "latin-900.css"), "utf8");
    expect(stylesheet).toMatch(/font-family:\s*'?"?Doto/);
    expect(stylesheet).toMatch(/font-weight:\s*900/);
    const files = [...stylesheet.matchAll(/url\(\.\/files\/([^)]+\.woff2?)\)/g)].map((m) => m[1]);
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) expect(existsSync(join(dir, "files", file)), file).toBe(true);
  });

  it("is named first in the print font stack, with Courier as a fallback", () => {
    const css = read("src", "styles", "paper.css");
    expect(css).toMatch(/--font-print:\s*"Doto", "Courier New", Courier, monospace;/);
  });

  it("is not loaded from anywhere else", () => {
    const sources: string[] = [join(web, "index.html")];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === "__tests__") continue;
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(css|tsx?|html)$/.test(entry.name)) sources.push(full);
      }
    };
    walk(join(web, "src"));
    expect(sources.length).toBeGreaterThan(15);

    const external = /(fonts\.googleapis|fonts\.gstatic|use\.typekit|use\.fontawesome|cdnjs|unpkg|jsdelivr|@import\s+url\(\s*['"]?https?:)/i;
    for (const file of sources) {
      const text = readFileSync(file, "utf8");
      expect(text, relative(web, file).split(sep).join("/")).not.toMatch(external);
    }
  });
});

describe("package scripts", () => {
  it("has dev, build, test and preview", () => {
    const { scripts } = JSON.parse(read("package.json"));
    expect(scripts.dev).toBe("vite");
    expect(scripts.preview).toBe("vite preview");
    expect(scripts.test).toBe("vitest run");
    expect(scripts.build).toMatch(/vite build$/);
  });
});
