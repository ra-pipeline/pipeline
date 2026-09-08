import os
from docutils import nodes

def bold_jira_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
    """
    A Sphinx role that returns the text wrapped in a strong (bold) node.
    Used for the public build where we do not want to hyperlink to internal Jira.
    """
    return [nodes.strong(rawtext, text)], []

def config_inited_handler(app, config):
    # Only inject the extlinks configuration if we are doing an internal build
    if os.environ.get("BUILD_INTERNAL_DOCS") == "1":
        if not hasattr(config, "extlinks"):
            config.extlinks = {}
        config.extlinks["jira"] = ("https://open-jira.nrao.edu/browse/%s", "%s")
        config.extlinks["alma"] = ("https://jira.alma.cl/browse/%s", "%s")

def setup(app):
    if os.environ.get("BUILD_INTERNAL_DOCS") == "1":
        # Internal Build: load extlinks
        app.setup_extension("sphinx.ext.extlinks")
        # Hook into config-inited to inject our specific URL template
        app.connect("config-inited", config_inited_handler)
    else:
        # Public Build: register the bold text role
        app.add_role("jira", bold_jira_role)
        app.add_role("alma", bold_jira_role)
    
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }