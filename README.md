# Multi-Style Character-Sheet & Icon Rendering Pipeline  
*Version 2025-05-12 (major update)*

---

## Table of Contents
1. System Goals  
2. Governance & Versioning  
3. Architectural Overview  
4. Cost Model and Hosting Decision  
5. Windows 11 Prerequisites  
6. Installing the Local Toolchain  
7. Project Repository Layout  
8. Building the Docker Image  
9. Style-Specific Rendering Specs  
10. Orchestrator Service  
11. Prompt & Rendering Spec Overview  
12. Preparing the Prompt Queue  
13. Launching a RunPod Session  
14. Day-to-Day Operations  
15. Monitoring and Troubleshooting  
16. Security, Secrets, and Compliance  
17. Asset Lifecycle & Storage  
18. Quality & Testing  
19. Future-Proofing & Scale  
20. Appendix A – Rendering Spec Documents  
21. Appendix B – Prompt Spec (ASCII schema)  
22. Appendix C – Addendum Spec (Medieval World)  
23. Appendix D – Medieval Addendum (50 rows)  
24. Appendix E – GitHub Actions Workflows  
25. Appendix F – Handy One-Liners  

---

## 1  System Goals
* Deterministic output: *prompt + seed + style* → identical PNG always.  
* Dual compliance: each row passes **Prompt Spec**; each image passes **Rendering Spec**.  
* Infinite reproducibility: every historical graph/spec is archived—no purges.  
* Elastic cost: GPU pod runs only while rendering; idle < USD 1/mo.  
* Single image containing **six** styles: `flat3t, lowpoly, albion, handpt, real, anime`.  
* All content, including names and descriptions, restricted to 7-bit ASCII for maximal toolchain safety.

---

## 2  Governance & Versioning
| Topic | Decision |
|-------|----------|
| Version scheme | **SemVer-calendar hybrid** `<YYYY>.<MM>.<patch>` for both Prompt Spec and each Rendering Spec. |
| Deprecation window | Specs are never deleted; orchestrator keeps every historical graph forever (cold-storage after 12 months). |
| Change approval | Single maintainer (you). PRs auto-merge when authored by the repo owner. |
| Golden prompts | 10 reference prompts per style stored in `/tests/golden/`; CI fails if MD5 hash of output PNG changes. |

---

## 3  Architectural Overview
```
GitHub Actions CI                 RunPod RTX A6000 Pod
-----------------                 ----------------------
build.yml  ─┐                ┌─>  ghcr.io/spec-render:<sha>
            │                │        │
render.yml ─┴───> queue      │        ▼
                              │   ComfyUI graph_<style>.json
Workstation (8 GB)            │   audits → sheet.png / meta.json
(edit code & addendums)       └─>  self-stop, sync results → S3
```

---

## 4  Cost Model and Hosting Decision
* RunPod Community A6000: USD 0.33/hr.  
* For burst loads > 70 k prompts, spin **n** pods concurrently (configurable).

---

## 5  Windows 11 Prerequisites (optional)
* Any Windows 11 PC with Git and VS Code.  
* WSL 2 + Docker Desktop only if you want local dry-runs.

---

## 6  Installing the Local Toolchain
```bash
# Inside WSL (optional)
sudo apt update && sudo apt install git python3-pip -y
pip install --user runpod runpodctl
```
No Docker build needed locally—CI does it.

---

## 7  Project Repository Layout
```
spec-render-pipeline/
├─ .github/workflows/        build.yml, render.yml
├─ addendums/                medieval_v1.ndjson
├─ prompts/                  (generated, git-ignored)
├─ specs/
│  ├─ rendering/             six Markdown specs (see Appendix A)
│  ├─ prompt/                prompt-v2025-05-11.md
│  └─ addendum/              medieval-v2025-05-12.md
├─ graphs/                   six ComfyUI JSON graphs
├─ scripts/                  merge_prompts.py, validate_prompts.py, launch_pod_cli.py
├─ Dockerfile, requirements.txt, orchestrator.py
└─ README.md
```

---

## 8  Building the Docker Image
* CI builds **one** image containing every graph, checkpoint, and LoRA.  
* SBOM generated with Syft → `spec-render-<sha>.spdx.json` for supply-chain audit.

---

## 9  Style-Specific Rendering Specs
| Key | Rendering Spec ID | Reference Look |
|-----|------------------|----------------|
| flat3t | flat3t-v2025-04-24 | Legacy 3-tone sheet |
| lowpoly | lowpoly-v2025-05-12 | Synty-style low-poly |
| albion | albion-v2025-05-12 | Albion Online MMO |
| handpt | handpainted-v2025-05-12 | WoW hand-painted |
| real | realistic-v2025-05-12 | Assassin’s Creed realistic |
| anime | anime-v2025-05-12 | Castlevania anime |

Full documents in Appendix A.

---

## 10  Orchestrator Service
* Dynamic lookup tables map `style` → graph JSON → audit function.  
* SHA256 manifest (`manifest.txt`) written per batch for provenance.  
* Borderline audits (score within 2 % of threshold) flagged for **manual QA**.

---

## 11  Prompt & Rendering Spec Overview
* **Prompt Spec** ensures each row is ASCII, has required keys, valid enum values.  
* **Rendering Spec** (per style) defines prompt flags, graph, audits.  
* CI step `validate_prompts.py` rejects bad rows before merging.

---

## 12  Preparing the Prompt Queue
```bash
cat addendums/*.ndjson | python scripts/merge_prompts.py > prompts/prompts.ndjson
```
`merge_prompts.py` validates against Prompt Spec, stamps the correct Rendering Spec version, and wraps the block in triple back-ticks.

---

## 13  Launching a RunPod Session
In GitHub **Actions → Launch Render Batch → Run**.  
Inputs: `image_tag` (default latest), `prompt_glob` (default all).

---

## 14  Day-to-Day Operations
1. Edit or add `addendums/*.ndjson`.  
2. Commit & push → CI lint + (if needed) rebuild container.  
3. Trigger **Launch Render Batch**.  
4. Review S3 results; fix any `"audit":"FAIL"` prompts and re-queue.

---

## 15  Monitoring and Troubleshooting
* Live pod logs → `runpodctl pod logs`.  
* CI build cache uses a self-hosted runner to avoid GitHub minute limits.  
* Prometheus exporter in orchestrator pushes audit stats to Grafana.

---

## 16  Security, Secrets, and Compliance
| Area | Policy |
|------|--------|
| Secrets rotation | Rotate RunPod API, GHCR PAT, AWS keys **quarterly**. |
| Least privilege | CI runner IAM role limited to `s3:PutObject` on `spec-sheets/*`. |
| SBOM | SPDX output per build, stored with image artifact. |
| Model licensing | Each Rendering Spec lists license (MIT, CC-BY, etc.). |
| Third-party IP | Red-flag audit: reject prompts containing trademark keywords list. |

---

## 17  Asset Lifecycle & Storage
| Artifact | Retention | Storage class after TTL |
|----------|-----------|-------------------------|
| Raw prompt queues | 30 days | Glacier Instant |
| meta.json audit logs | 90 days | Glacier Instant |
| Final PNGs | **forever** | S3 Standard-IA after 12 months |
| Container images | 2 years | GHCR retention policy |

---

## 18  Quality & Testing
* **Golden prompts**: 10 per style, hashed; any drift fails CI.  
* **Unit tests**: synthetic fixtures for each audit rule run in `pytest`.  
* **Manual QA**: images flagged borderline are copied to `results/needs_review/`.

---

## 19  Future-Proofing & Scale
* **Pods per batch**: Launch `ceil(queue_len / 5000)` pods in parallel.  
* **Fallback GPU**: if community queue wait > 30 min, switch to on-demand A6000.  
* **Reserved fields**: Prompt Spec already contains `reserved` object for future 360° turntable params.  
* **Style mixing**: not yet supported—requires explicit new Rendering Spec.

---

## Appendix A – Rendering Spec Documents

### 1.  `specs/rendering/flat3t-v2025-04-24.md`
```
Rendering Spec : flat3t-v2025-04-24
Reference      : Legacy three-tone character sheet
Base Checkpoint: sdxl_turbo.safetensors
Prompt Flags   :
  --flat-three-tone
  --strict-orthographic
  --draw-eyes outline<=0.8px iris-gray pupil-black highlight
Audits:
  * Canvas 1536x864 or 1536x1024
  * 3 equal columns, gutters 0.02
  * Max 4 tone clusters for skin and hair
  * Eye outline 0.5–0.8 px, ellipse ratio 1.1–1.4
  * Background RGB 245 245 240 ±5
License: StabilityAI Non-Commercial (SDXL-Turbo)
```

---

### 2.  `specs/rendering/lowpoly-v2025-05-12.md`
```
Rendering Spec : lowpoly-v2025-05-12
Reference      : Synty low-poly, flat colours, hard edges
Base Checkpoint: lowpoly.safetensors
Prompt Flags   :
  --lowpoly
  --tri-count<=3000
  --flat-lighting
  --strict-orthographic
Audits:
  * Palette ≤ 256 colours
  * No gradients (RGB delta ≤ 5)
  * Canvas 1536x864, gutters 0.02
  * Outline weight 1.2–1.6 px (single tier)
License: MIT
```

---

### 3.  `specs/rendering/albion-v2025-05-12.md`
```
Rendering Spec : albion-v2025-05-12
Reference      : Albion Online MMO style (cell tone + outline)
Base Checkpoint: albion_lora.safetensors
Prompt Flags   :
  --albion
  --toon-outline
  --flat-four-tone
  --strict-orthographic
Audits:
  * Outline tiers: outer 2.0 px, inner 1.2 px ±15 %
  * Tone clusters 4–6
  * Slight paper-grain allowed (value variance ≤ 5 %)
License: CC-BY 4.0
```

---

### 4.  `specs/rendering/handpainted-v2025-05-12.md`
```
Rendering Spec : handpainted-v2025-05-12
Reference      : World of Warcraft hand-painted look
Base Checkpoint: handpainted.safetensors
Prompt Flags   :
  --handpaint
  --brushstroke-emulation
  --soft-specular
  --strict-orthographic
Audits:
  * Visible brushstroke texture present
  * Tone clusters 5–8
  * Hue range rich but saturation < 85 %
  * Outline weight ±15 % of 1.6 px
License: CC-BY 4.0
```

---

### 5.  `specs/rendering/realistic-v2025-05-12.md`
```
Rendering Spec : realistic-v2025-05-12
Reference      : Assassin's Creed realistic PBR
Base Checkpoint: realistic_photo_v2.safetensors
Prompt Flags   :
  --realistic
  --pbr-shader
  --micro-detail
  --strict-orthographic
Audits:
  * Physically correct shading (no toon outlines)
  * Global contrast ratio 1.4–1.9
  * Gradient smoothness sigma ≥ 6 px
  * Background RGB 245 245 240 ±5
License: Commercial-friendly SDXL-Photoreal 2.0
```

---

### 6.  `specs/rendering/anime-v2025-05-12.md`
```
Rendering Spec : anime-v2025-05-12
Reference      : Castlevania anime gothic
Base Checkpoint: anime_castlevania.safetensors
Prompt Flags   :
  --anime-cel
  --dramatic-light
  --hard-shadow
  --strict-orthographic
Audits:
  * Black outline 1.8 px ±10 %
  * Flat cel shading (exactly 3 tones per region)
  * Max 10 % of canvas may exceed value 240 (specular)
  * Eye highlights mandatory, 1–2 pixels
License: CC-BY-SA
```

---

## Appendix B – Prompt Spec (`specs/prompt/prompt-v2025-05-11.md`)
```
Prompt Spec v2025-05-11 (ASCII-only)
Required keys:
  id:str           unique, ASCII
  name:str         ASCII letters, spaces, apostrophes
  heads:float      5.0–10.0
  skin:str         fair|olive|ruddy|dark
  hair:str         ASCII
  clothing:str     ASCII, ≤60 chars
  desc:str         ASCII, ≤160 chars
  seed:int         0–4294967295
  style:enum       flat3t|lowpoly|albion|handpt|real|anime
Optional key:
  reserved:object  future fields
```

---

## Appendix C – Addendum Spec (`specs/addendum/medieval-v2025-05-12.md`)
```
Domain        : Low-magic medieval (late 13th-century Europe)
Allowed styles : lowpoly, albion, handpt, real, anime
Field bounds  :
  heads   6.5–8.5   (heroes up to 8.8)
  skin    fair|olive|ruddy|dark
  clothing must be era-appropriate (gambeson, tabard, surcoat, etc.)
  desc    ≤160 chars, third-person impersonal
ASCII rule  : All text fields 7-bit ASCII
```

---

## Appendix D – Medieval Addendum (`addendums/medieval_v1.ndjson`)
```ndjson
{"id":"m-001","name":"Sir Aldric","heads":7.8,"skin":"fair","hair":"blond short","clothing":"steel half-plate and crimson surcoat","desc":"landed knight sworn to House Carron","seed":2001,"style":"real"}
{"id":"m-002","name":"Lady Ysabel","heads":7.3,"skin":"olive","hair":"dark braided","clothing":"brocade gown with ermine trim","desc":"court diplomat fluent in four tongues","seed":2002,"style":"handpt"}
{"id":"m-003","name":"Father Berengar","heads":7.1,"skin":"ruddy","hair":"brown tonsure","clothing":"worn wool cassock and oak staff","desc":"traveling priest chronicling miracles","seed":2003,"style":"albion"}
{"id":"m-004","name":"Garin the Miller","heads":7.0,"skin":"fair","hair":"sandy mop","clothing":"linen shirt with flour stains","desc":"cheerful miller who controls river tolls","seed":2004,"style":"lowpoly"}
{"id":"m-005","name":"Anika the Falconer","heads":7.4,"skin":"olive","hair":"black ponytail","clothing":"leather jerkin and hawking glove","desc":"castle falconer training gyrfalcons","seed":2005,"style":"anime"}
{"id":"m-006","name":"Brother Corbin","heads":7.2,"skin":"fair","hair":"shaved","clothing":"grey novice robe","desc":"scribe copying royal ledgers","seed":2006,"style":"lowpoly"}
{"id":"m-007","name":"Duke Rowan","heads":8.0,"skin":"ruddy","hair":"auburn fringe","clothing":"purple velvet doublet with fox trim","desc":"young duke guarding the mountain pass","seed":2007,"style":"handpt"}
{"id":"m-008","name":"Iseult the Herbalist","heads":7.1,"skin":"dark","hair":"tight curls","clothing":"coarse sackcloth apron","desc":"village healer versed in roots and balms","seed":2008,"style":"albion"}
{"id":"m-009","name":"Perrin Swift","heads":7.5,"skin":"fair","hair":"light brown shag","clothing":"green brigandine and short bow","desc":"scout who maps enemy roads","seed":2009,"style":"real"}
{"id":"m-010","name":"Old Marta","heads":6.8,"skin":"olive","hair":"grey bun","clothing":"patched wool cloak","desc":"storyteller keeping hearth myths alive","seed":2010,"style":"anime"}
{"id":"m-011","name":"Sir Owyn Black","heads":7.9,"skin":"fair","hair":"black cropped","clothing":"blackened mail and raven crest shield","desc":"grim knight with unknown patron","seed":2011,"style":"real"}
{"id":"m-012","name":"Squire Joran","heads":7.2,"skin":"fair","hair":"blond fringe","clothing":"padded gambeson and bucket helm","desc":"eager squire seeking first tourney","seed":2012,"style":"lowpoly"}
{"id":"m-013","name":"Elric Forgehand","heads":7.3,"skin":"ruddy","hair":"red beard","clothing":"sooty leather apron","desc":"blacksmith famed for riversteel blades","seed":2013,"style":"handpt"}
{"id":"m-014","name":"Faye of the Glen","heads":7.0,"skin":"fair","hair":"brown waves","clothing":"green hood and ash stave","desc":"wandering archer raised in deep woods","seed":2014,"style":"albion"}
{"id":"m-015","name":"Captain Harlan","heads":7.6,"skin":"dark","hair":"shaved sides","clothing":"steel cuirass and blue plume","desc":"city guard captain rooting out smugglers","seed":2015,"style":"real"}
{"id":"m-016","name":"Abbot Silvan","heads":7.1,"skin":"olive","hair":"grey fringe","clothing":"white linen habit","desc":"abbot guarding relic of Saint Remy","seed":2016,"style":"anime"}
{"id":"m-017","name":"Mina Threadgold","heads":6.9,"skin":"fair","hair":"blond braid","clothing":"simple linen dress, sewing kit","desc":"seamstress who knows every gossip","seed":2017,"style":"lowpoly"}
{"id":"m-018","name":"Gregor Stonejaw","heads":7.7,"skin":"ruddy","hair":"dark beard","clothing":"chain shirt and war pick","desc":"miner turned mercenary guarding caravans","seed":2018,"style":"handpt"}
{"id":"m-019","name":"Seraphin the Piper","heads":7.0,"skin":"fair","hair":"light brown curls","clothing":"colorful patchwork jerkin","desc":"travelling bard famed for silver flute","seed":2019,"style":"albion"}
{"id":"m-020","name":"Helga Brewmaster","heads":7.2,"skin":"ruddy","hair":"red braids","clothing":"stout leather bodice","desc":"innkeeper brewing spiced ale","seed":2020,"style":"real"}
{"id":"m-021","name":"Wulfric Tanner","heads":7.3,"skin":"olive","hair":"black stubble","clothing":"hide apron and tanning knife","desc":"leathermaker supplying castle armory","seed":2021,"style":"lowpoly"}
{"id":"m-022","name":"Lysa Dove","heads":7.1,"skin":"fair","hair":"brown bob","clothing":"white coif and messenger satchel","desc":"royal courier who rides dawn to dusk","seed":2022,"style":"anime"}
{"id":"m-023","name":"Cedric Longbow","heads":7.5,"skin":"fair","hair":"dark ponytail","clothing":"elm longbow and leather vambrace","desc":"forest hunter feeding four villages","seed":2023,"style":"handpt"}
{"id":"m-024","name":"Merek Cutpurse","heads":7.0,"skin":"dark","hair":"short curls","clothing":"dark hooded cloak","desc":"thief plying trade in crowded fairs","seed":2024,"style":"albion"}
{"id":"m-025","name":"Doria Glass","heads":7.4,"skin":"fair","hair":"silver braid","clothing":"apprentice alchemist smock","desc":"glassblower perfecting clear flasks","seed":2025,"style":"real"}
{"id":"m-026","name":"Brother Abel","heads":7.2,"skin":"olive","hair":"black tonsure","clothing":"sand-colored robe","desc":"monk keeping celestial charts","seed":2026,"style":"lowpoly"}
{"id":"m-027","name":"Sir Roland Grey","heads":7.9,"skin":"fair","hair":"grey cropped","clothing":"aged plate with faded crest","desc":"retired knight mentoring squires","seed":2027,"style":"handpt"}
{"id":"m-028","name":"Tilda Farrow","heads":6.8,"skin":"ruddy","hair":"red pixie cut","clothing":"wheat-colored tunic","desc":"farmer saving coin for new plough","seed":2028,"style":"albion"}
{"id":"m-029","name":"Viktor the Sailmaker","heads":7.4,"skin":"dark","hair":"shaved top","clothing":"linen vest with sail needles","desc":"river barge sail craftsman","seed":2029,"style":"real"}
{"id":"m-030","name":"Esme Lantern","heads":7.0,"skin":"fair","hair":"blond waves","clothing":"traveler cloak and lantern pole","desc":"guides pilgrims through marsh fogs","seed":2030,"style":"anime"}
{"id":"m-031","name":"Otto Barrelgut","heads":7.5,"skin":"ruddy","hair":"brown beard","clothing":"cooper's apron, oak hammer","desc":"barrel maker whose ale casks never leak","seed":2031,"style":"lowpoly"}
{"id":"m-032","name":"Joan Ironhand","heads":7.6,"skin":"fair","hair":"dark bun","clothing":"chain gloves and war hammer","desc":"castle guard famed for crushing blows","seed":2032,"style":"handpt"}
{"id":"m-033","name":"Rafe Quickstep","heads":7.1,"skin":"olive","hair":"black fringe","clothing":"soft boots and rapier","desc":"duelist teaching nobles blade etiquette","seed":2033,"style":"albion"}
{"id":"m-034","name":"Bryn Weaver","heads":7.0,"skin":"fair","hair":"light brown curls","clothing":"loom-dust tunic","desc":"weaver crafting intricate tapestries","seed":2034,"style":"real"}
{"id":"m-035","name":"Edel Harrow","heads":7.2,"skin":"ruddy","hair":"auburn braid","clothing":"leather quiver and ash arrows","desc":"hinterland ranger guarding wild herds","seed":2035,"style":"anime"}
{"id":"m-036","name":"Miles Torch","heads":7.3,"skin":"fair","hair":"brown mop","clothing":"oil cloth jacket","desc":"night watch lighting city beacons","seed":2036,"style":"lowpoly"}
{"id":"m-037","name":"Agnes Crest","heads":7.1,"skin":"olive","hair":"dark braid","clothing":"ink-stained gown","desc":"cartographer mapping lost forts","seed":2037,"style":"handpt"}
{"id":"m-038","name":"Baldric Oak","heads":7.4,"skin":"ruddy","hair":"bald","clothing":"heavy woodsman's coat","desc":"lumberjack famed for one-stroke fells","seed":2038,"style":"albion"}
{"id":"m-039","name":"Sabin Sellsword","heads":7.7,"skin":"dark","hair":"black beard","clothing":"patched mail and broad sword","desc":"roving mercenary selling blade to highest bidder","seed":2039,"style":"real"}
{"id":"m-040","name":"Clara Hearth","heads":6.9,"skin":"fair","hair":"light curls","clothing":"floury apron","desc":"baker whose rye bread draws nobility","seed":2040,"style":"anime"}
{"id":"m-041","name":"Kendrick Moor","heads":7.5,"skin":"olive","hair":"short fringe","clothing":"mud-spattered boots","desc":"swamp guide knowing every hidden path","seed":2041,"style":"lowpoly"}
{"id":"m-042","name":"Lothar Pike","heads":7.8,"skin":"ruddy","hair":"red beard","clothing":"steel helm and long pike","desc":"veteran pikeman from border wars","seed":2042,"style":"handpt"}
{"id":"m-043","name":"Maeve Candle","heads":7.0,"skin":"fair","hair":"brown braid","clothing":"wax-flecked dress","desc":"chandler mixing lavender oils","seed":2043,"style":"albion"}
{"id":"m-044","name":"Edric Page","heads":7.1,"skin":"fair","hair":"blond locks","clothing":"royal blue page livery","desc":"page running messages across castle grounds","seed":2044,"style":"real"}
{"id":"m-045","name":"Gwen Needle","heads":6.8,"skin":"olive","hair":"dark pixie","clothing":"dyer smock splashed with indigo","desc":"dyer perfecting deep blue hues","seed":2045,"style":"anime"}
{"id":"m-046","name":"Hugo Flint","heads":7.6,"skin":"ruddy","hair":"grey stubble","clothing":"iron pot helm and mace","desc":"village reeve enforcing tax law","seed":2046,"style":"lowpoly"}
{"id":"m-047","name":"Iona Reed","heads":7.2,"skin":"fair","hair":"light braid","clothing":"green reed cloak","desc":"fisherwoman setting eel nets at dawn","seed":2047,"style":"handpt"}
{"id":"m-048","name":"Torin Ash","heads":7.3,"skin":"dark","hair":"black bun","clothing":"charcoal-streaked smock","desc":"charcoal burner supplying forges","seed":2048,"style":"albion"}
{"id":"m-049","name":"Rosa Gale","heads":7.0,"skin":"fair","hair":"red curls","clothing":"scarlet hood, sling pouch","desc":"messenger racing storm fronts","seed":2049,"style":"real"}
{"id":"m-050","name":"Walt Stone","heads":7.4,"skin":"ruddy","hair":"brown beard","clothing":"granite-dust tunic","desc":"mason carving cathedral gargoyles","seed":2050,"style":"anime"}
```

---

## Appendix E – GitHub Actions Workflows
*See earlier editions for full YAML; lint script now validates ASCII and six-style enum.*

---

## Appendix F – Handy One-Liners
```bash
# Trigger render for this medieval addendum only
gh workflow run render.yml -f prompt_glob='addendums/medieval_v1.ndjson'
```

---

*End of Runbook 2025-05-12*