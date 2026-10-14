import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { build } from "vite";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const buildDir = mkdtempSync(join(tmpdir(), "wow-dashboard-tests-"));
let code = 1;
try {
  const compiled = spawnSync(process.execPath, [join(root, "node_modules/typescript/bin/tsc"), "-p", "tsconfig.test.json", "--outDir", buildDir], { cwd: root, stdio: "inherit" });
  if (compiled.status === 0) {
    const live = process.argv.includes("--live");
    if (!live) {
      // Bundle the real App/client; only the backend URL is replaced for tests.
      // External React keeps the mounted App and the test on one React instance.
      await build({
        root, configFile: false, logLevel: "silent",
        define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify("http://test.invalid") },
        build: {
          outDir: buildDir, emptyOutDir: false, minify: false,
          lib: { entry: join(root, "src/App.tsx"), formats: ["cjs"], fileName: () => "App.cjs" },
          rollupOptions: { external: ["react", "react/jsx-runtime", "react-dom", "react-dom/client"] },
        },
      });
    }
    code = 0;
    for (const suite of live ? ["live.test.mjs"] : ["market.test.mjs", "app.test.mjs"]) {
      const tested = spawnSync(process.execPath, [join(root, "tests", suite)], {
        cwd: root, stdio: "inherit", env: { ...process.env, NODE_ENV: "test", TEST_BUILD_DIR: buildDir, NODE_PATH: join(root, "node_modules") },
      });
      if (tested.status !== 0) code = tested.status ?? 1;
    }
  }
} finally {
  if (resolve(dirname(buildDir)) !== resolve(tmpdir()) || !basename(buildDir).startsWith("wow-dashboard-tests-")) throw new Error("Unsafe test cleanup path");
  rmSync(buildDir, { recursive: true, force: true });
}
process.exitCode = code;
