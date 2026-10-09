# Weblog Static Resources

This directory contains the static frontend assets (JavaScript, CSS, fonts, and images) used by the Pipeline HTML Weblog.

To allow weblogs to render completely offline and be preserved in scientific data archives indefinitely, all third-party dependencies are vendored locally rather than loaded from external CDNs.

---

## Directory Structure

```text
resources/
├── css/      # Stylesheets and LESS sources (Bootstrap 3, Select2, Fancybox, Font Awesome)
├── js/       # JavaScript libraries and custom weblog controller scripts
├── fonts/    # Icon and glyph web fonts (Font Awesome 4, Glyphicons Halflings)
└── img/      # Observatory logos (ALMA, VLA, EVLA, NRO) and UI spinners
```

---

## 1. Third-Party / Vendor-Derived Inventory

The following third-party assets are vendored within this directory:

### JavaScript Libraries (`js/`)

| File | Library & Version | Upstream / Author | License | Description & Pipeline Role |
| :--- | :--- | :--- | :--- | :--- |
| **`jquery-3.3.1.js`** | jQuery v3.3.1 | [jQuery Foundation](https://jquery.com/) | MIT | Core DOM manipulation and event engine; base for Bootstrap, Fancybox, and `pipeline.js`. |
| **`bootstrap.js`** | Bootstrap v3.3.7 | [Twitter, Inc.](https://getbootstrap.com/) | MIT | Layout framework providing top navigation bar, tabs, collapsible panels, and modals. |
| **`d3.v3.js`** | D3.js v3.5.17 | [Mike Bostock](https://d3js.org/) | BSD-3-Clause | Data visualization library powering interactive histograms and score brushing on detail plot pages. |
| **`holder.js`** | Holder v2.9.4+cabil | [Ivan Malopinsky](http://holderjs.com/) | MIT | Generates client-side image placeholders when plots or thumbnails are missing or pending. |
| **`jquery.fancybox.js`** | fancyBox v3.2.10 | [fancyApps](http://fancyapps.com/fancybox/) | GPLv3 (open source) | Lightbox modal viewer providing image zooming, plot cycling, and CASA command inspection panes. |
| **`lazyload.js`** | Lazy Load v2.0.0-beta.2 | [Mika Tuupola](https://appelsiini.net/projects/lazyload) | MIT | Defers off-screen image loading until scrolled into view, optimizing initial weblog page load times. |
| **`purl.js`** | Purl v2.3.1 | [Mark Perkins](https://github.com/allmarkedup/jQuery-URL-Parser) | MIT | URL parsing library used to manage query parameters and active state across sidebar links and tabs. |
| **`select2.js`** | Select2 v4.0.5 | [Kevin Brown et al.](https://select2.github.io/) | MIT | Searchable multi-select dropdown widget used for antenna, spw, field, and score filters on detail plot pages. |

### Stylesheets & Themes (`css/`)

| File | Library / Theme & Version | Upstream / Author | License | Description & Pipeline Role |
| :--- | :--- | :--- | :--- | :--- |
| **`font-awesome.css`** | Font Awesome v4.1.0 | [Dave Gandy](https://fontawesome.com/) | SIL OFL 1.1 / MIT | Vector icon styles; references icon web fonts in `../fonts/fontawesome-webfont.*`. |
| **`jquery.fancybox.css`** | fancyBox v3.2.10 | [fancyApps](http://fancyapps.com/fancybox/) | GPLv3 | Stylesheet for image lightboxes, galleries, toolbars, and CASA plot command overlays. |
| **`select2.css`** | Select2 v4.0.5 | [Select2](https://select2.github.io/) | MIT | Core styling for multi-select dropdown menus and input fields. |
| **`select2-bootstrap.css`** | Select2 Bootstrap Theme v0.1.0-beta.10 | [Florian Kissling](https://select2.github.io/select2-bootstrap-theme/) | MIT | Adapts Select2 widgets to match Bootstrap 3 styling. |
| **`pipeline.css`** | Bootswatch v3.3.2 (Paper theme) + customizations | [Thomas Park](https://bootswatch.com/) + NRAO | MIT / LGPL-3.0+ | Primary weblog stylesheet based on Bootswatch "Paper" (Bootstrap 3.3.2) with custom Pipeline rules. |
| **`paper-pipeline.css`** | Bootswatch v3.3.2 (Paper variant) | [Thomas Park](https://bootswatch.com/) | MIT | Reference Bootswatch Paper stylesheet. |
| **`bootswatch.less`** | Bootswatch LESS overrides | NRAO Pipeline | LGPL-3.0+ | LESS mixins for body padding, fixed navigation bar, circular badge alerts, and task list layout. |
| **`variables.less`** | Bootstrap LESS variables | NRAO Pipeline | LGPL-3.0+ | Palette and sizing definitions for compiling the custom Bootstrap theme. |

### Web Fonts (`fonts/`)

| Files | Family & Version | Upstream / License | Description |
| :--- | :--- | :--- | :--- |
| `fontawesome-webfont.*`, `FontAwesome.otf` | Font Awesome v4.1.0 | SIL OFL 1.1 | Scalable icon fonts for warning signs, task badges, and buttons. |
| `glyphicons-halflings-regular.*` | Glyphicons Halflings | Apache 2.0 / MIT (via Bootstrap 3) | Standard UI glyphs included with Bootstrap 3. |

---

## 2. Pipeline Custom Frontend Modules

Located in `js/`:

- **`pipeline.js`**: Core client-side JavaScript module controlling weblog interactions: page lifecycle initialization, QA notes rendering, table sorting, sidebar navigation, and detail plot filtering pipelines.
- **`plotcmd.js`**: Custom fancybox plugin providing a button and overlay showing the originating CASA plot command for figures.
- **`tcleancmd.js`**: Custom fancybox plugin providing a button and overlay showing the originating CASA `tclean` command for synthesis imaging plots.

---

## 3. Asset Bundling & Minification

To minimize weblog size and browser requests, source files are bundled and minified into production distributions:

| Target Production Bundle | Source Files Combined | Compression Tool |
| :--- | :--- | :--- |
| **`css/all.min.css`** | `font-awesome.css` + `jquery.fancybox.css` + `select2.css` + `select2-bootstrap.css` + `pipeline.css` | `csscompressor` |
| **`js/pipeline_common.min.js`** | `jquery-3.3.1.js` + `holder.js` + `lazyload.js` + `jquery.fancybox.js` + `plotcmd.js` + `tcleancmd.js` + `purl.js` + `bootstrap.js` + `pipeline.js` | `jsmin` |
| **`js/pipeline_plots.min.js`** | `select2.js` + `d3.v3.js` | `jsmin` |

### Building and Verifying Bundles

Bundles are generated via `scripts/bundle_assets.py`:

```bash
# Regenerate all bundles:
pixi run bundle-assets
# or: python scripts/bundle_assets.py

# Verify bundles on disk are up to date with source files (CI check):
python scripts/bundle_assets.py --check
```

---

## 4. Template Integration & Debugging Fallback

Mako templates (`pipeline/infrastructure/renderer/templates/base.mako` and `detail_plots_basetemplate.mako`) dynamically inspect whether the `.min.js` and `.min.css` bundles exist:

- **Production Mode (Default)**: When minified bundles are present, the weblog loads the 3 compressed bundles (`all.min.css`, `pipeline_common.min.js`, `pipeline_plots.min.js`).
- **Development & Debugging Mode**: If the minified bundles are removed or `use_minified_js` is disabled in `htmlrenderer.py` / `basetemplates.py`, templates automatically fall back to loading the individual unminified files. This preserves comments and original line numbers for browser DevTools debugging.

