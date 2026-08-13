/**
 * furo_layout.js
 *
 * Adds a collapse/expand toggle button to the right-side TOC drawer in the
 * Furo Sphinx theme. The collapsed state is persisted in localStorage so it
 * survives page navigation.
 *
 * Only activates on wide screens (>82em) where Furo shows the TOC inline.
 * On smaller screens Furo's own mobile TOC overlay takes over.
 */
(function () {
    'use strict';

    function init() {
        var tocDrawer = document.querySelector('.toc-drawer');
        if (!tocDrawer) return;

        // Pages with no local TOC auto-expand via CSS — no button needed.
        if (tocDrawer.classList.contains('no-toc')) return;

        // Only install on wide screens where the inline TOC is visible.
        if (!window.matchMedia('(min-width: 83em)').matches) return;

        var btn = document.createElement('button');
        btn.className = 'toc-toggle-btn';
        btn.setAttribute('aria-label', 'Toggle table of contents');
        btn.setAttribute('title', 'Toggle table of contents');
        // chevron pointing right = TOC is visible, click to collapse
        btn.textContent = '\u276F';
        // Append to body so fixed positioning is straightforward.
        document.body.appendChild(btn);

        // Position the button at the left edge of the TOC drawer.
        function positionBtn() {
            var rect = tocDrawer.getBoundingClientRect();
            btn.style.right = (document.documentElement.clientWidth - rect.left) + 'px';
        }
        positionBtn();
        window.addEventListener('resize', positionBtn);

        // Restore saved state.
        if (localStorage.getItem('furo-toc-collapsed') === 'true') {
            tocDrawer.classList.add('toc-collapsed');
            var mainEl = tocDrawer.parentElement;
            if (mainEl) mainEl.classList.add('toc-collapsed');
            btn.textContent = '\u276E';  // chevron left = click to expand
            // Re-position continuously during CSS transition (~200ms).
            var start = performance.now();
            function trackPosition() {
                positionBtn();
                if (performance.now() - start < 320) {
                    requestAnimationFrame(trackPosition);
                }
            }
            requestAnimationFrame(trackPosition);
        }

        btn.addEventListener('click', function () {
            var collapsed = tocDrawer.classList.toggle('toc-collapsed');
            var mainEl = tocDrawer.parentElement;
            if (mainEl) mainEl.classList.toggle('toc-collapsed', collapsed);
            localStorage.setItem('furo-toc-collapsed', collapsed);
            btn.textContent = collapsed ? '\u276E' : '\u276F';
            
            // Re-position continuously during CSS transition (~200ms).
            var start = performance.now();
            function trackPosition() {
                positionBtn();
                if (performance.now() - start < 320) {
                    requestAnimationFrame(trackPosition);
                }
            }
            requestAnimationFrame(trackPosition);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // --- Mermaid reset-zoom buttons ---
    // sphinxcontrib-mermaid with mermaid_d3_zoom=True wraps each diagram in a
    // <div class="mermaid-d3pan"> that owns an internal SVG managed by d3-zoom.
    // We inject a small reset button that calls svg.__zoom.invert() to restore
    // the identity transform.
    function addMermaidResetButtons() {
        document.querySelectorAll('.mermaid').forEach(function (container) {
            // Avoid double-injection on re-renders.
            if (container.parentElement.querySelector('.mermaid-reset-btn')) return;

            var btn = document.createElement('button');
            btn.className = 'mermaid-reset-btn';
            btn.setAttribute('title', 'Reset zoom');
            btn.textContent = '\u21BA';  // ↺
            btn.addEventListener('click', function () {
                var svg = container.querySelector('svg');
                if (!svg) return;
                var g = svg.querySelector('g');
                if (g) g.setAttribute('transform', 'translate(0,0) scale(1)');
                if (svg.__zoom) svg.__zoom = window.d3 ? window.d3.zoomIdentity : {k:1, x:0, y:0};
            });

            var wrapper = document.createElement('div');
            wrapper.className = 'mermaid-zoom-wrapper';
            container.parentNode.insertBefore(wrapper, container);
            wrapper.appendChild(container);
            wrapper.appendChild(btn);
        });
    }

    // Mermaid renders asynchronously; poll briefly until diagrams appear.
    function waitForMermaid() {
        var attempts = 0;
        var interval = setInterval(function () {
            if (document.querySelector('.mermaid svg') || ++attempts > 40) {
                clearInterval(interval);
                addMermaidResetButtons();
            }
        }, 250);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', waitForMermaid);
    } else {
        waitForMermaid();
    }
}());
