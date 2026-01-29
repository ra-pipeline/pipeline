"""
Created on 11 Sep 2014

@author: sjw
"""

from importlib.resources import files

import pipeline.infrastructure.renderer.weblog as weblog

weblog.register_mako_templates(str(files(__name__)), prefix='hifv')
