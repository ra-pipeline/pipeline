/**
 * Initialize Viewer.js (MIT License) for all documentation figures and images.
 * Features:
 *  - Rich technical inspection toolbar: Zoom In (+), Zoom Out (-), 1:1 Actual Size, Reset, Rotate, Flip
 *  - High-precision mouse wheel zooming and drag-to-pan
 *  - Keyboard navigation (Esc, Arrow keys, +, -)
 *  - Seamless gallery navigation and caption display
 */
(function () {
    'use strict';

    function initViewer() {
        if (typeof Viewer === 'undefined') {
            return;
        }

        var container = document.querySelector('article') || document.querySelector('.content') || document.querySelector('main') || document.body;
        if (!container) return;

        // Prevent parent <a> tags on figures from navigating away
        var figureLinks = container.querySelectorAll('figure a.image-reference, .figure a.image-reference, figure a.reference, .figure a.reference');
        figureLinks.forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
            });
        });

        // Initialize Viewer on the document content container
        new Viewer(container, {
            // Filter out non-content images like brand logos and icons
            filter: function (img) {
                if (img.classList.contains('no-zoom') || img.classList.contains('brand-logo') || img.classList.contains('icon')) {
                    return false;
                }
                return true;
            },
            // Use high-resolution source from parent <a> link if available
            url: function (img) {
                var parentLink = img.closest('a');
                return (parentLink && parentLink.href) ? parentLink.href : (img.currentSrc || img.src);
            },
            // Extract captions from <figcaption> or alt text
            title: function (img) {
                var figure = img.closest('figure') || img.closest('.figure');
                if (figure) {
                    var figcaption = figure.querySelector('figcaption');
                    if (figcaption) {
                        return figcaption.innerText.trim();
                    }
                }
                var alt = img.getAttribute('alt') || '';
                return alt.startsWith('../_images/') ? '' : alt;
            },
            toolbar: {
                zoomIn: 1,
                zoomOut: 1,
                oneToOne: 1,
                reset: 1,
                prev: 1,
                play: 0,
                next: 1,
                rotateLeft: 1,
                rotateRight: 1,
                flipHorizontal: 1,
                flipVertical: 1,
                download: function () {
                    var viewerInstance = this.viewer;
                    var currentImg = viewerInstance.image;
                    if (currentImg && currentImg.src) {
                        var a = document.createElement('a');
                        a.href = currentImg.src;
                        a.download = currentImg.src.split('/').pop().split('?')[0] || 'image.png';
                        a.target = '_blank';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                    }
                },
            },
            navbar: true,
            tooltip: true,
            movable: true,
            zoomable: true,
            rotatable: true,
            scalable: true,
            transition: true,
            fullscreen: true,
            keyboard: true,
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initViewer);
    } else {
        initViewer();
    }
})();
