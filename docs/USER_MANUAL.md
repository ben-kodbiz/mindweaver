# MindWeaver — User Manual

A friendly guide to using MindWeaver, written for everyday readers.
No programming knowledge needed.

---

## 1. Welcome

MindWeaver turns your PDF books and documents into a **living mind map** — a
picture of the main topics and ideas inside each document — and lets you:

- **See** what a book is about at a glance,
- **Dig into** any topic on the map,
- **Jump straight** from an idea to the exact page it came from,
- **Grow** the map yourself by highlighting passages,
- **Add your own** notes, colours and personal ideas without ever changing the
  original document.

Everything happens **on your own computer**. Your documents are never uploaded
to the internet.

### How it works, in one picture

```text
You add a PDF
      ↓
MindWeaver reads it (including scanned pages)
      ↓
It draws a mind map of the main topics
      ↓
You explore, ask, highlight and grow the map
      ↓
Every idea links back to the exact page it came from
```

---

## 2. Getting started

### What you need

- A computer with MindWeaver installed.
- A web browser (Firefox, Chrome, Edge — any modern browser).

### Starting MindWeaver

MindWeaver has two parts that run quietly on your computer: the **program**
(that does the reading and thinking) and the **screen** (that you see in your
browser). Whoever set up MindWeaver for you starts them like this:

```sh
make dev-api    # starts the program
make dev-web    # opens the screen
```

Then open your browser at: **http://localhost:5173**

> Tip: if you started MindWeaver yourself and walked away, simply repeat those
> two commands after turning your computer back on.

### Stopping

Press **Ctrl + C** twice in the window where you ran the commands. Nothing is
lost — all your books and notes stay saved.

---

## 3. The Library — your home screen

When you open the address above you land on the **Library** screen. It shows:

| Area | What it does |
|---|---|
| **Add a PDF** | Choose a PDF from your computer and press *Add to library* |
| **Documents** | Every PDF you have added, with its current state |

At the top it also greets you with a green *"Backend connected"* line when
MindWeaver is running properly.

---

## 4. Adding a PDF

1. On the Library screen, find the **Add a PDF** section.
2. Click the file chooser and pick any PDF from your computer.
3. Click **Add to library**.
4. Wait a few moments while MindWeaver reads the file. You will see one of
   these messages:
   - *Added "yourfile.pdf"* — success! It now appears in your Documents list.
   - *That PDF is already in your library* — MindWeaver recognised it as a
     copy (it checks fingerprints, not titles).
   - *Sorry — that PDF could not be added…* — the file is probably damaged or
     not really a PDF.

Your book is now being read automatically. Watch the **status** next to its
name change:

| Status | Meaning | What to do |
|---|---|---|
| **Added** | Received and stored | Nothing — wait |
| **Waiting / Reading** | Being analysed | Nothing — usually seconds |
| **Needs OCR** | Some pages are pictures (a scan), so they must be "read aloud" by the built-in reader first | Click the orange **Read scanned pages** button |
| **Reading scanned pages** | OCR in progress | Wait |
| **Ready** | Done — the mind map is ready | Click the name to open it |
| **Failed** | Something went wrong (usually a damaged file) | Try re-saving/exporting the PDF and adding it again |

> **Scanned books?** No problem. When you see *Needs OCR*, press the orange
> **Read scanned pages** button once. MindWeaver will look at every page image
> and recover the words. This can take a little longer than normal reading.

---

## 5. Opening a book — the Mind Map

Click any document's name in the list. You arrive at the **mind map**: your
book drawn as a tree.

### Reading the map

- The big **dark node** on the left is the whole book.
- **Blue nodes** are the main chapters/topics.
- **Purple nodes** are the key concepts found inside each chapter.

Lines show how ideas connect: book → chapter → concept. Each concept only
appears if it was actually found in the text, and behind the scenes every node
remembers which page(s) it came from.

---

## 6. Moving around the map

| I want to… | Do this |
|---|---|
| Move the whole map | Click and hold anywhere on the empty background, then drag |
| Zoom in / out | Roll the mouse wheel, or use the **+** / **−** buttons |
| Fold a branch away | Click a node — its children hide (the node shows a **+**) |
| Unfold again | Click it once more (it shows a **−**) |
| Find a word | Type it in the **Search** box, then press **Next** to hop between matches |
| Start over | Press **Reset** (also re-folds everything) |
| See everything at once | Press **Expand** |

The map always stays small and readable — MindWeaver deliberately shows only
the most important concepts per chapter rather than thousands of dots.

---

## 7. Working with a selected idea

Click any blue or purple node once. A **panel** appears in the corner showing
what it is: its type, the chapter/section it came from, and the pages involved.
Four buttons give you superpowers:

### 🔍 Expand

Asks MindWeaver to look harder around this idea and pull out further related
concepts from the text, growing fresh branches under the node. Great when a
chapter looks thin. (If there is nothing genuinely new to find, nothing is
added — the map never fills up with junk.)

### 💬 Explain

Produces a short, plain-language explanation of this concept **using only the
book itself**, followed by the *related* ideas the map connects it to.

### 📄 Evidence

Lists exactly where the idea lives: which pages, which sections. Use this when
you want proof before trusting a claim.

### 📖 Open PDF

Opens the **original PDF** beside the map and flips it straight to the first
page where this idea occurs. Anything MindWeaver knows the location of is
marked with a yellow highlight.

---

## 8. Reading along in the original PDF

When the PDF panel is open you can read the real book next to your map.

### The toolbar

| Control | Action |
|---|---|
| **← Prev / Next →** | Go one page back or forward |
| Page number box | Type a page and press Enter to jump |
| **+** / **−** | Make the page bigger or smaller |
| **Close** | Hide the PDF and return to full-screen map |

### From an idea to the exact spot

The chain always works the same way:

```text
Click a node  →  press Open PDF  →  correct page opens  →  yellow highlights mark the passage
```

---

## 9. Turn any passage into part of your map

This is where MindWeaver becomes truly yours.

1. In the PDF, **select some text** with your mouse (drag across a sentence or
   paragraph).
2. An **Add selection to mind map** button appears at the top. Click it.
3. MindWeaver reads your selection and proposes one or more **new concepts**
   for the map.
4. Look at the proposal box:
   - Happy? Press **Add to mind map** — the new idea joins the graph.
   - Changed your mind? Press **Cancel** — nothing is added.

New additions appear in the graph view immediately and are treated as *yours*
(see the next chapter).

---

## 10. Graph view — see how ideas connect

The mind map is a tree. Sometimes you want to see the **web**: which ideas
influence which, what supports what, where two sources disagree.

Switch views using the **Mind Map | Graph** buttons at the top.

In Graph view:

- **Circles are concepts** — bigger circles are more connected ones.
- **Lines are relationships**, labelled with their type (*affects*, *supports*,
  *explains*, *contradicts*…) and colour-coded.
- **Dashed lines** are educated guesses MindWeaver made without a direct quote
  in the text — treat them lightly.
- **Click a circle** to spotlight it and its direct neighbours (everything else
  fades). The panel on the top-right opens for editing (next chapter).
- **Click empty space** to un-dim everything.

### Filters

Above the graph:

- **Node types** — tick boxes to show/hide people, events, claims, etc.
- **Relations** — choose which link types to draw.
- Changes apply instantly.

### Finding things

Type in the **Search** box; matching concepts light up orange and the view
glides to them. Press **Focus** to keep only that concept's neighbourhood on
screen, or **Reset focus** to see everything again.

---

## 11. Make it yours — notes, colours and personal ideas

With a node selected in Graph view, the **edit panel** lets you annotate and
restructure. Everything you do here survives even if the book is re-analysed
later, because your layer is kept separate from the machine's.

### Add your voice to an existing idea

| Button | What it does |
|---|---|
| **Save** (after editing Note / Tags) | Stores a free-text note and comma-separated tags on the node |
| **★ Important** | Marks the idea with a star — flip it again to remove |
| **🔖 Bookmark** | Bookmarks the node for quick finding later |
| **Rename** | Gives the idea a label you prefer |

Notes, tags and colours are private annotations — the original book is never
touched.

### Add completely new ideas of your own

Press **+ Node** in the toolbar and type a label. Your personal node appears
as a first-class citizen of the graph, ready to be connected.

### Connect two ideas

1. Select the first node.
2. Press **Connect…**
3. Click the second node.

A relationship line appears between them. To delete a line, press **Remove
link** and follow the prompts.

### Tidy up

| Button | Effect |
|---|---|
| **Merge into…** | Folds the selected node into another one (their notes, tags and connections combine). Useful for duplicates like "Recall" vs "Retrieval". |
| **Delete** | Removes the node and all its lines. Source-derived nodes can come back if the book is ever re-analysed — personal ones never do. |

### Made a mistake?

**Undo** and **Redo** sit in the toolbar and take the whole graph back or
forward one step at a time — including merges and deletions.

---

## 12. Going back to your library

Press **← Documents** in the top-left corner at any time. Your position, zoom
level and collapsed branches are remembered per book.

---

## 13. Tips for best results

- **Native digital PDFs work best.** Scans still work, but expect to press
  *Read scanned pages* and slightly lower accuracy.
- **One book per file.** Multi-volume scans are easier to manage separately.
- Grow slowly. Expand one chapter at a time; the map stays meaningful.
- Use ★ Important sparingly — it is your "shortlist".
- Colours and tags are searchable by eye in Graph view; pick a scheme (for
  example red = disagree, green = mastered) and stick to it.
- Trust but verify: purple concepts always carry their page numbers in the
  side panel — jump to the source before quoting anything.

---

## 14. If something goes wrong

| Symptom | Likely cause & fix |
|---|---|
| *"Backend not reachable…"* on the home screen | The program isn't running. Ask whoever set it up to run `make dev-api`, then reload the page. |
| Upload says the file could not be added | The file may be corrupted or password-protected. Remove the password (or re-save the PDF) and try again. |
| Status stuck at *Needs OCR* | Press the orange **Read scanned pages** button. |
| *Expand* does nothing | There was nothing genuinely new near that idea, or no AI model is configured. Everything else keeps working. |
| *Explain* shows an error | The AI model isn't reachable. Other features are unaffected; ask your installer to check the model setting. |
| A node disappeared | Did you press Undo too many times? Press **Redo** in Graph view. |
| Yellow highlights missing in the PDF | That location is known only by page, not by coordinates. The page still opens correctly. |

---

## 15. Small dictionary

| Word | Meaning here |
|---|---|
| **Node** | One bubble on the map/graph — a book, chapter or concept |
| **Concept** | An idea extracted from the text ("Memory", "Consolidation"…) |
| **Evidence** | The exact place in the PDF an idea came from |
| **OCR** | "Optical character recognition" — reading words out of page pictures |
| **Personal node** | An idea you added yourself; never removed by re-analysis |
| **Merge** | Folding two nodes into one, combining their notes and links |
| **Graph** | The web-like view of relationships between ideas |

---

*Enjoy your books — now with a map.*
