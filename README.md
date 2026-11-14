# Response Dashboard

An emergency response dashboard, built the same way as Doorstep: plain HTML, CSS and JavaScript plus a small Node.js server (`server.js`). No build step, no npm install.

## The page

1. **First 3 minutes changes lives** at the top.
2. **Answer** button. Clicking it shows the caller's phone number and, under **Location**, the latitude and longitude.
3. The responder then chooses **Drone 1**, **Drone 2** or **Drone 3** (one at a time; clicking another switches).
4. **Notes** on the right (under the call on a phone): a box the dispatcher types into during the call.

The call is demo data for now: `CALL` at the top of `js/call.js`. Notes are not saved yet. Reload the page to start over.

## Working on it together

1. Get a copy: `git clone <repo link>`, then `cd` into the folder.
2. Make a branch for your change: `git checkout -b my-change`.
3. Run it with `node server.js` and open http://localhost:4000.
4. Commit, push the branch (`git push -u origin my-change`) and open a pull request on GitHub.

Pull first (`git pull`) before you start, so you're working on the latest version.

## Run it

- **Mac:** double-click `start-mac.command` (the first time, right-click it and choose **Open**)
- **Windows:** double-click `start-windows.bat`
- **From a terminal:** run `node server.js` in this folder

Then open **http://localhost:4000**. It uses port 4000, so it can run at the same time as Doorstep (port 3000). Press **Ctrl+C** to stop it.

## Theme: Midnight Command

All colours are tokens at the top of `css/styles.css`. Each one has a single job:

| Token | Colour | Job |
|---|---|---|
| `--bg` | `#0B1220` | Page background |
| `--panel` | `#152238` | Panels |
| `--text` | `#F1F5F9` | Main text |
| `--muted` | `#94A3B8` | Secondary info; offline / unknown (always with a label) |
| `--accent` | `#22D3EE` | Selected item, active navigation, primary controls |
| `--critical` | `#F87171` | Critical alerts only |
| `--warning` | `#FBBF24` | Warnings, needs review |
| `--ok` | `#34D399` | Normal, available |

Rules that keep it readable:
- Status colours always come with a word, and Critical also gets an icon. Never colour alone.
- Timers, coordinates and counts use the monospace font (`.mono`), so changing numbers don't shift.
- Thin borders, 6–10 px corners, no flashing or glowing effects.

## Structure
    index.html          The call page (first page): Answer, call details, drones, notes
    server.js           Serves the site on port 4000
    css/styles.css      Theme tokens and the call page styles
    js/call.js          Answer button, caller details, drone choice (demo call data at the top)
    assets/favicon.svg  Tab icon
    pages/              Further pages go here
