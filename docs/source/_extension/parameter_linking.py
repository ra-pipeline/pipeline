"""Sphinx extension to create parameter links between function signatures and parameter documentation.

This extension post-processes HTML files after the build to:
1. Add ID anchors to parameter documentation entries
2. Wrap signature parameters in links pointing to those anchors

This creates clickable links from function signature parameters to their documentation.
"""

import logging
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def process_html_file(filepath: Path) -> bool:
    """Process a single HTML file to add parameter links.

    Args:
        filepath: Path to the HTML file to process

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')

        modified = False

        # Find all function/method signatures
        signatures = soup.find_all('dt', class_='sig')

        for sig in signatures:
            # Only process if it has an ID (function definition)
            if not sig.get('id'):
                continue

            # Find the corresponding description (next dd sibling)
            dd = sig.find_next_sibling('dd')
            if not dd:
                continue

            # Find the Parameters field in the description
            param_items = find_parameter_items(dd)
            if not param_items:
                continue

            # Add ID anchors to parameter documentation
            param_names = add_parameter_anchors(param_items)
            if not param_names:
                continue

            # Add links from signature parameters to documentation
            if add_signature_links(sig, param_names):
                modified = True

        # Add CSS for parameter links if any modifications were made
        if modified:
            add_inline_css(soup)

        # Save modified HTML if changes were made
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            return True

    except (OSError, AttributeError, ValueError) as e:
        logger.warning('parameter_linking: could not process %s: %s', filepath, e)

    return False


def find_parameter_items(dd_element):
    """Find parameter documentation items in a function description.

    Args:
        dd_element: BeautifulSoup dd element containing function description

    Returns:
        List of li elements containing parameter docs, or None if not found
    """
    # Look for field-list containing Parameters in the standard location (inside dd)
    field_list = dd_element.find('dl', class_='field-list')
    
    # If not found inside dd, check if it was promoted to a top-level section by toc_sections.py
    if not field_list:
        # Check if there is a section id="parameters" in the document
        soup = dd_element.find_parent('html') or dd_element.find_parent('body') or dd_element.find_parent()
        # Find the root object
        while soup.parent:
            soup = soup.parent
            
        param_section = soup.find('section', id='parameters')
        if param_section:
            field_list = param_section.find('dl', class_='field-list')

    if not field_list:
        return None

    # Find the Parameters or Args field
    for dt in field_list.find_all('dt', class_=['field-odd', 'field-even']):
        if dt.get_text().strip().startswith('Parameters') or dt.get_text().strip().startswith('Args'):
            # Get the corresponding dd
            dd = dt.find_next_sibling('dd')
            if dd:
                # Find the ul element containing parameter items
                ul = dd.find('ul')
                if ul:
                    # Find all parameter items (li elements) within the ul
                    param_items = ul.find_all('li', recursive=False)
                    if param_items:
                        return param_items

    return None


def add_parameter_anchors(param_items):
    """Add ID anchors to parameter documentation items and make param names clickable.
    
    This function transforms Napoleon-rendered parameter documentation from:
        <li><p><strong>name</strong> -- <p>description</p><p>Examples: ...</p></li>
    
    Into inline format with clickable anchors:
        <li id="param-name"><a><strong>name</strong></a> <strong>:</strong> description<p>Examples: ...</p></li>

    Args:
        param_items: List of li elements containing parameter docs

    Returns:
        Set of parameter names that were processed
    """
    param_names = set()

    for li in param_items:
        # Find the parameter name (in strong tag)
        strong = li.find('strong')
        if not strong or not strong.get_text().strip():
            continue
            
        param_name = strong.get_text().strip()
        
        # Add ID anchor to the li element for URL fragment linking
        li['id'] = f'param-{param_name}'
        param_names.add(param_name)
        
        # Wrap parameter name in clickable anchor for easy copying
        new_link = li.new_tag('a', href=f'#param-{param_name}')
        new_link['class'] = 'param-name-link'
        strong.wrap(new_link)
        
        # Step 1: Flatten <p> parent wrapper around parameter name
        # Napoleon sometimes wraps: <p><strong>name</strong> -- desc</p>
        # We want: <strong>name</strong> -- desc (inline, no block element)
        first_p = strong.find_parent('p')
        if first_p and first_p.parent == li:
            for child in list(first_p.children):
                first_p.insert_before(child)
            first_p.extract()
        
        # Step 2: Replace ' -- ' separator with ' <strong>:</strong> '
        # This makes the colon bold and visually clearer
        for text_node in li.find_all(string=True):
            if text_node.parent.name != 'strong' and ' -- ' in str(text_node):
                parts = str(text_node).split(' -- ', 1)
                parent = text_node.parent
                node_index = list(parent.children).index(text_node)
                text_node.extract()
                
                # Insert: "text " + <strong>:</strong> + " remaining text"
                parent.insert(node_index, parts[0])
                parent.insert(node_index + 1, ' ')
                
                strong_tag = li.new_tag('strong')
                strong_tag.string = ':'
                parent.insert(node_index + 2, strong_tag)
                
                parent.insert(node_index + 3, ' ' + parts[1])
                break
        
        # Step 3: Flatten first <p> sibling (the description paragraph)
        # Structure after Step 1 & 2: <a><strong>name</strong></a> <strong>:</strong> <p>description</p><p>Examples:</p>
        # We want: <a><strong>name</strong></a> <strong>:</strong> description<p>Examples:</p>
        # Only flatten the FIRST <p> (description), preserve subsequent <p> tags (section headers)
        anchor = strong.parent
        for sibling in list(anchor.next_siblings):
            if hasattr(sibling, 'name') and sibling.name == 'p':
                # Flatten by moving children out and removing the <p> wrapper
                for child in list(sibling.children):
                    sibling.insert_before(child)
                sibling.extract()
                break  # Stop after first <p> to preserve "Examples:", "Options:", etc.

    return param_names


def add_signature_links(sig_element, param_names):
    """Add links from signature parameters to their documentation.

    Args:
        sig_element: BeautifulSoup dt element containing function signature
        param_names: Set of parameter names that have documentation

    Returns:
        True if any links were added, False otherwise
    """
    modified = False

    # Find all signature parameters
    sig_params = sig_element.find_all('em', class_='sig-param')

    for param in sig_params:
        # Find the parameter name span
        name_span = param.find('span', class_='n')
        if not name_span:
            continue

        # Get the innermost span with the actual name
        pre_span = name_span.find('span', class_='pre')
        if not pre_span:
            continue

        param_name = pre_span.get_text().strip()

        # Only add link if this parameter has documentation
        if param_name in param_names:
            # Check if already wrapped in a link
            if pre_span.parent.name == 'a':
                continue

            # Create a new anchor element using BeautifulSoup
            # Get the soup object from the existing element
            if hasattr(pre_span, 'find_parent'):
                root = pre_span.find_parent()
                while root.parent is not None:
                    root = root.parent
                soup_obj = root
            else:
                from bs4 import BeautifulSoup as BS

                soup_obj = BS('', 'html.parser')

            new_link = soup_obj.new_tag('a', href=f'#param-{param_name}')
            new_link['class'] = 'param-link'

            # Wrap the pre_span in the link
            pre_span.wrap(new_link)
            modified = True

    return modified


def add_inline_css(soup):
    """Add inline CSS for parameter link styling to the HTML document.

    Args:
        soup: BeautifulSoup object representing the HTML document
    """
    css_content = """
/* Parameter link styling */
a.param-link {
    color: inherit;
    text-decoration: none;
}

a.param-link:hover {
    text-decoration: underline;
}

/* Parameter name links (in parameter documentation) */
a.param-name-link {
    color: inherit;
    text-decoration: none;
    cursor: pointer;
}

a.param-name-link:hover {
    text-decoration: underline;
    color: var(--color-brand-primary, #0066cc);
}

/* Highlight parameter when targeted via URL hash - fades after 3 seconds */
li[id^="param-"]:target {
    border-left: 3px solid var(--color-brand-primary, #0066cc);
    padding-left: 0.5em;
    margin-left: -0.5em;
    animation: highlight-fade 3s ease-out;
}

@keyframes highlight-fade {
    0% { 
        background-color: var(--color-highlighted-background, #fffacd);
    }
    100% { 
        background-color: transparent;
    }
}

/* Furo theme compatibility */
html[data-theme="light"] li[id^="param-"]:target {
    animation: highlight-fade-light 3s ease-out;
}

html[data-theme="dark"] li[id^="param-"]:target {
    animation: highlight-fade-dark 3s ease-out;
}

@keyframes highlight-fade-light {
    0% { background-color: #fffacd; }
    100% { background-color: transparent; }
}

@keyframes highlight-fade-dark {
    0% { background-color: #3a3a2a; }
    100% { background-color: transparent; }
}
"""

    # Find the head element
    head = soup.find('head')
    if head:
        # Create a style tag
        style_tag = soup.new_tag('style')
        style_tag.string = css_content
        head.append(style_tag)


def process_all_html_files(app, exception):
    """
    Post-process all HTML files after the build completes.

    This is called by Sphinx's 'build-finished' event.

    Args:
        app: Sphinx application instance
        exception: Any exception that occurred during build (None if successful)
    """
    if exception:
        # Don't process if build failed
        return

    if app.builder.format != 'html':
        # Only process HTML builds
        return

    build_dir = Path(app.builder.outdir)

    # Find all HTML files in _autosummary (where CLI function docs are generated)
    autosummary_dir = build_dir / '_autosummary'
    if not autosummary_dir.exists():
        return

    html_files = list(autosummary_dir.glob('*.html'))

    if not html_files:
        return

    logger.info('parameter_linking: processing %d HTML files for parameter links...', len(html_files))

    modified_count = 0
    for html_file in html_files:
        if process_html_file(html_file):
            modified_count += 1

    if modified_count > 0:
        logger.info('parameter_linking: added parameter links to %d files', modified_count)


def setup(app) -> dict[str, Any]:
    """Setup the Sphinx extension.

    Args:
        app: Sphinx application instance

    Returns:
        Extension metadata
    """
    # Connect to build-finished event for HTML post-processing
    app.connect('build-finished', process_all_html_files)

    return {
        'version': '1.0.0',
        'parallel_read_safe': True,
        'parallel_write_safe': False,  # We modify HTML files, so disable parallel writes
    }
