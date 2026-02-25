from importlib.resources import files

import pipeline.infrastructure.renderer.weblog as weblog

weblog.register_mako_templates(str(files(__name__)), prefix='hsdn')
