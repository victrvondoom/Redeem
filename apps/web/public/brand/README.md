# Partner brand assets (intro animation)

The intro shows a cube for **Bolna** (left) and one for **Wispr Flow** (right). Each cube displays the official logo if you place it here:

| File | Source |
|---|---|
| `bolna.svg` | official Bolna brand/press asset (https://www.bolna.ai) |
| `wispr-flow.svg` | official Wispr Flow brand/press asset (https://wisprflow.ai) |
| `ycombinator.svg` | official Y Combinator logo (https://www.ycombinator.com) |
| `wemakedevs.svg` | official WeMakeDevs logo (https://www.wemakedevs.org) |

Until a file exists, the cube shows the partner's **name as plain text**. Logos are never redrawn or approximated. The build sandbox had no access to these sites, so none could be fetched
(see docs/OPEN_BLOCKERS.md). Use only assets you are permitted to use; naming a partner does not imply endorsement.

After adding a file, list its name in `manifest.json` (`{"files": ["bolna.svg", "wispr-flow.svg"]}`) so the intro requests it (this avoids 404s for files that are not there).
