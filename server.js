// Emergency response dashboard - local server
// Serves the website. Built the same way as Doorstep: plain files, no npm install.
// Needs Node.js 18 or newer.

const http = require("http");
const fs = require("fs");
const path = require("path");

// Port 4000, so it can run next to Doorstep (which uses 3000).
const PORT = parseInt(process.env.PORT || "4000", 10);

const [major] = process.versions.node.split(".").map(Number);
if (major < 18) {
  console.error("\nThis app needs Node.js 18 or newer. You have " + process.version + ".");
  console.error("Download the LTS version from https://nodejs.org and try again.\n");
  process.exit(1);
}

// Only the site's own files are served: index.html plus the css, js, pages and assets folders.
// Everything else (server.js, data/) is never sent to the browser.
const SITE_DIRS = ["css", "js", "pages", "assets"];
const TYPES = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".webp": "image/webp", ".gif": "image/gif", ".ico": "image/x-icon"
};

function siteFile(pathname) {
  let p;
  try { p = decodeURIComponent(pathname); } catch { return null; }
  if (/[\\\0]/.test(p)) return null; // no backslashes (Windows paths) or null bytes
  if (p.endsWith("/")) p += "index.html";
  const rel = path.posix.normalize(p).replace(/^\/+/, "");
  if (rel.split("/").some(part => part === ".." || part.startsWith("."))) return null;
  const inSite = rel === "index.html" || (rel.includes("/") && SITE_DIRS.includes(rel.split("/")[0]));
  if (!inSite || !TYPES[path.extname(rel).toLowerCase()]) return null;
  return path.join(__dirname, rel);
}

function send(res, status, obj) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(obj));
}

function handle(req, res) {
  const url = new URL(req.url, "http://localhost");

  if (req.method === "GET" && url.pathname === "/api/health") {
    return send(res, 200, { ok: true, time: new Date().toISOString() });
  }

  if (req.method === "GET" || req.method === "HEAD") {
    const file = siteFile(url.pathname);
    if (file) {
      return fs.readFile(file, (err, buf) => {
        if (err) { res.writeHead(404, { "Content-Type": "text/plain" }); return res.end("Not found"); }
        res.writeHead(200, { "Content-Type": TYPES[path.extname(file).toLowerCase()], "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff" });
        res.end(req.method === "HEAD" ? undefined : buf);
      });
    }
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not found");
}

const server = http.createServer(handle);

server.on("error", e => {
  if (e.code === "EADDRINUSE") {
    console.error("\n  Port " + PORT + " is already in use. An older copy is probably still running.");
    console.error("  Close its window, or on a Mac run:  lsof -ti :" + PORT + " | xargs kill\n");
    process.exit(1);
  }
  throw e;
});

server.listen(PORT, () => {
  console.log("\n  Emergency response dashboard is running.");
  console.log("  Open this in your browser:  http://localhost:" + PORT);
  console.log("  Keep this window open while you use the site. Press Ctrl+C to stop.\n");
});
