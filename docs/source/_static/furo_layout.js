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

    // --- Mermaid Pan/Zoom and Toolbar Controls ---
    function setupMermaidControls() {
        // 1. Process all in-page mermaid containers
        document.querySelectorAll('.mermaid-container').forEach(function (container) {
            var svg = container.querySelector('.mermaid svg') || container.querySelector('svg');
            if (!svg) return;

            // Ensure diagram is centered in container
            svg.style.display = 'block';
            svg.style.marginLeft = 'auto';
            svg.style.marginRight = 'auto';

            // Prevent mouse wheel from hijacking normal web page scrolling:
            // Remove wheel.zoom listener ONLY on in-page diagrams.
            // Click & drag panning and double-click zoom remain fully active!
            if (window.d3) {
                window.d3.select(svg).on('wheel.zoom', null);
            }

            // Avoid duplicate reset button
            if (container.querySelector('.mermaid-reset-btn')) return;

            var resetBtn = document.createElement('button');
            resetBtn.className = 'mermaid-reset-btn';
            resetBtn.setAttribute('title', 'Reset pan/zoom');
            resetBtn.setAttribute('aria-label', 'Reset diagram pan and zoom');
            resetBtn.textContent = '\u21BA'; // ↺

            resetBtn.addEventListener('click', function () {
                var g = svg.querySelector('g.wrapper') || svg.querySelector('g');
                if (g) g.setAttribute('transform', 'translate(0,0) scale(1)');
                if (window.d3) {
                    window.d3.select(svg).call(window.d3.zoom().transform, window.d3.zoomIdentity);
                } else if (svg.__zoom) {
                    svg.__zoom = { k: 1, x: 0, y: 0 };
                }
            });

            // Insert reset button right next to the fullscreen button in the same container
            var fsBtn = container.querySelector('.mermaid-fullscreen-btn');
            if (fsBtn) {
                container.insertBefore(resetBtn, fsBtn);
            } else {
                container.appendChild(resetBtn);
            }
        });
    }

    // Add reset button inside fullscreen lightbox modal when opened
    document.addEventListener('click', function (e) {
        if (e.target && e.target.closest('.mermaid-fullscreen-btn')) {
            setTimeout(function () {
                var modalContainer = document.querySelector('.mermaid-container-fullscreen');
                if (!modalContainer || modalContainer.querySelector('.mermaid-modal-reset-btn')) return;

                var resetModalBtn = document.createElement('button');
                resetModalBtn.className = 'mermaid-modal-reset-btn';
                resetModalBtn.setAttribute('title', 'Reset pan/zoom');
                resetModalBtn.setAttribute('aria-label', 'Reset pan and zoom');
                resetModalBtn.textContent = '\u21BA'; // ↺
                resetModalBtn.addEventListener('click', function () {
                    var modalSvg = modalContainer.querySelector('svg');
                    if (!modalSvg) return;
                    var g = modalSvg.querySelector('g.wrapper') || modalSvg.querySelector('g');
                    if (g) g.setAttribute('transform', 'translate(0,0) scale(1)');
                    if (window.d3) {
                        window.d3.select(modalSvg).call(window.d3.zoom().transform, window.d3.zoomIdentity);
                    }
                });
                modalContainer.appendChild(resetModalBtn);
            }, 150);
        }
    });

    // Mermaid renders asynchronously; poll briefly until diagrams appear.
    function waitForMermaid() {
        var attempts = 0;
        var interval = setInterval(function () {
            if (document.querySelector('.mermaid-container svg') || ++attempts > 40) {
                clearInterval(interval);
                setupMermaidControls();
            }
        }, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', waitForMermaid);
    } else {
        waitForMermaid();
    }
}());
