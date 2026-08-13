from docutils import nodes
from sphinx import addnodes

from sphinx.util import logging

logger = logging.getLogger(__name__)

def promote_to_sections(app, doctree):
    """
    Convert Sphinx field lists and rubrics into real docutils sections
    so they appear in the Furo right-hand Table of Contents.
    Only applies to CLI task documentation.
    """
    docname = app.env.docname
    if not (docname.startswith('_autosummary/pipeline.') and '.cli.' in docname):
        return

    # Initialize the tracking dict on env (persisted in the Sphinx pickle).
    # Always reset the entry for this document so stale sections are cleared
    # when the docstring changes.
    if not hasattr(app.env, 'cli_sections'):
        app.env.cli_sections = {}
    app.env.cli_sections[docname] = set()

    # 1. Promote Parameter field_lists to sections
    for field_list in list(doctree.traverse(nodes.field_list)):
        has_params = False
        for field in field_list:
            field_name = field[0].astext().lower()
            if field_name == 'parameters' or field_name.startswith('param '):
                has_params = True
                break
                
        if has_params:
            sec_id = 'parameters'
            sec = nodes.section('', ids=[sec_id], names=[sec_id])
            sec += nodes.title('', 'Parameters')
            
            # Remove the field_list from its original place
            field_list.parent.remove(field_list)
            sec += field_list
            
            # Set up the section properly for docutils/Sphinx
            sec.document = doctree.document
            doctree.document.note_implicit_target(sec)
            
            # Find the root section (usually the first child of the document)
            root_section = doctree[0] if isinstance(doctree[0], nodes.section) else doctree
            root_section.append(sec)
            app.env.cli_sections[docname].add(sec_id)

    # 2. Promote rubrics (Examples, Notes) to sections
    for rubric in list(doctree.traverse(nodes.rubric)):
        title_text = rubric.astext()
        if title_text.lower() in ('examples', 'notes'):
            sec_id = nodes.make_id(title_text)
            sec = nodes.section('', ids=[sec_id], names=[sec_id])
            
            title_node = nodes.title('', title_text)
            sec += title_node
            
            parent = rubric.parent
            idx = parent.index(rubric)
            
            # Move all following siblings into the section until we hit another rubric/section
            siblings_to_move = []
            for sibling in parent[idx+1:]:
                if isinstance(sibling, (nodes.rubric, nodes.section, nodes.field_list)):
                    break
                siblings_to_move.append(sibling)
                
            # Remove the rubric itself
            parent.remove(rubric)
            
            for sibling in siblings_to_move:
                parent.remove(sibling)
                sec += sibling
                
            # Set up the section properly
            sec.document = doctree.document
            doctree.document.note_implicit_target(sec)
            
            # Append to the root section
            root_section = doctree[0] if isinstance(doctree[0], nodes.section) else doctree
            root_section.append(sec)
            app.env.cli_sections[docname].add(sec_id)

def update_tocs(app, env):
    """
    Add TOC entries for promoted sections to the Sphinx per-page TOCs.
    Only injects entries for sections that were actually promoted (tracked
    in env.cli_sections), so tasks without Notes/Examples don't get dead links.
    env.cli_sections is persisted in the Sphinx pickle, so it works correctly
    across incremental builds.
    """
    cli_sections = getattr(env, 'cli_sections', {})

    for docname in env.tocs:
        if not (docname.startswith('_autosummary/pipeline.') and '.cli.' in docname):
            continue

        promoted = cli_sections.get(docname, set())
        if not promoted:
            continue

        toc = env.tocs[docname]
        
        # toc is a bullet_list.
        # Its first item is usually the top-level section (e.g. hif_makeimages)
        if not toc.children:
            continue
            
        top_item = toc[0]
        # top_item is a list_item. It should have a bullet_list for sub-sections.
        sub_list = None
        for child in top_item:
            if isinstance(child, nodes.bullet_list):
                sub_list = child
                break
                
        if sub_list is None:
            sub_list = nodes.bullet_list('')
            top_item += sub_list
            
        # Inject only entries for sections that were actually promoted.
        # Note: Returns is excluded — Sphinx renders "Return type" as part of
        # the Parameters field_list (not a separate rubric), so no #returns anchor.
        for sec_id, title_str in [('parameters', 'Parameters'), ('notes', 'Notes'), ('examples', 'Examples')]:
            if sec_id not in promoted:
                continue
            ref = nodes.reference('', '')
            ref['refid'] = sec_id
            ref['anchorname'] = '#' + sec_id
            ref.append(nodes.Text(title_str))
            
            para = addnodes.compact_paragraph('', '', ref)
            item = nodes.list_item('', para)
            sub_list.append(item)

def merge_cli_sections(app, env, docnames, other):
    """
    Merge cli_sections from a parallel reader worker env into the main env.
    Required when parallel_read_safe=True — without this, attributes set on
    worker envs are lost and never reach update_tocs.
    """
    if not hasattr(env, 'cli_sections'):
        env.cli_sections = {}
    if hasattr(other, 'cli_sections'):
        env.cli_sections.update(other.cli_sections)


def purge_cli_sections(app, env, docname):
    """
    Remove a document's cli_sections entry when Sphinx purges it
    (e.g. before re-reading a changed file on incremental builds).
    """
    if hasattr(env, 'cli_sections'):
        env.cli_sections.pop(docname, None)


def setup(app):
    app.connect('doctree-read', promote_to_sections)
    app.connect('env-merge-info', merge_cli_sections)
    app.connect('env-purge-doc', purge_cli_sections)
    app.connect('env-updated', update_tocs)
    return {
        'version': '0.1',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
