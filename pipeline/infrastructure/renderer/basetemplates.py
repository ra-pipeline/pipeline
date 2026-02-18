"""
Created on 8 Sep 2014

@author: sjw
"""
import collections
import contextlib
import glob
import hashlib
import json
import math
import os
from importlib.resources import files

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.utils as utils

from . import weblog
from .templates import resources

LOG = logging.get_logger(__name__)


class T2_4MDetailsDefaultRenderer(object):
    def __init__(self, uri='t2-4m_details-generic.mako',
                 description='No description set for this task',
                 always_rerender=False):
        self.uri = uri
        # TODO remove template access after conversion
        self.description = description
        self.always_rerender = always_rerender

    def get_display_context(self, context, result):
        mako_context = {'pcontext': context,
                        'result': result,
                        'casalog_url': self._get_log_url(context, result),
                        'dirname': 'stage%s' % result.stage_number}
        self.update_mako_context(mako_context, context, result)

        # CAS-8216: multi-ms in time order in all weblog stages
        time_ordered = time_order_dicts(mako_context, context)

        return time_ordered

    def _get_stage_number(self, result):
        if hasattr(result, 'stage_number'):
            return result.stage_number
        if isinstance(result, collections.abc.Iterable):
            return result[0].stage_number
        return None

    def _get_task_name(self, result):
        if hasattr(result, 'taskname'):
            return result.taskname
        if hasattr(result, 'task'):
            return result.task.__name__
        if isinstance(result, collections.abc.Iterable):
            return getattr(result[0].task, '__name__', 'unknown')
        return 'unknown'

    def _get_inputs_hash(self, result):
        inputs = getattr(result, 'inputs', None)
        if inputs is None and isinstance(result, collections.abc.Iterable):
            inputs = getattr(result[0], 'inputs', None)

        if inputs is None:
            return 'no-inputs'

        try:
            inputs_dict = inputs.as_dict() if hasattr(inputs, 'as_dict') else dict(inputs)
        except Exception:
            inputs_dict = {'inputs_repr': repr(inputs)}

        inputs_dict = self._get_stable_inputs_dict(inputs_dict, result)
        payload, _ = self._serialize_for_hash(inputs_dict)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _stable_hash(self, value):
        payload, _ = self._serialize_for_hash(value)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _serialize_for_hash(self, value):
        normalized = self._normalize_for_hash(value)
        try:
            payload = json.dumps(normalized, sort_keys=True, separators=(',', ':'), default=str)
        except TypeError:
            payload = repr(normalized)

        return payload, normalized

    def _normalize_for_hash(self, value):
        if isinstance(value, dict):
            return {str(k): self._normalize_for_hash(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            return [self._normalize_for_hash(v) for v in value]
        if isinstance(value, set):
            return [self._normalize_for_hash(v) for v in sorted(value, key=lambda v: str(v))]
        return value

    def _get_stable_inputs_dict(self, inputs_dict, result):
        task_name = self._get_task_name(result)
        if task_name != 'hifa_flagdata':
            return inputs_dict

        keep_keys = {
            'vis',
            'autocorr',
            'shadow',
            'tolerance',
            'scan',
            'scannumber',
            'intents',
            'edgespw',
            'fracspw',
            'fracspwfps',
            'online',
            'partialpol',
            'lowtrans',
            'mintransnonrepspws',
            'mintransrepspw',
            'fileonline',
            'template',
            'filetemplate',
            'hm_tbuff',
            'tbuff',
            'qa0',
            'qa2',
        }

        filtered = {key: inputs_dict.get(key) for key in keep_keys if key in inputs_dict}
        if 'vis' in filtered:
            filtered['vis'] = self._normalize_vis(filtered['vis'])

        return filtered or inputs_dict

    def _normalize_vis(self, vis_value):
        if isinstance(vis_value, (list, tuple, set)):
            vis_list = [os.path.basename(str(v)) for v in vis_value]
            return sorted(vis_list)
        return os.path.basename(str(vis_value))

    def _find_cached_path(self, context, result):
        cache_path = self._get_cache_path(context, result)
        if cache_path and os.path.exists(cache_path):
            return cache_path

        task_name = self._get_task_name(result)
        safe_task = ''.join([c if c.isalnum() or c in ('_', '-') else '_' for c in task_name])
        inputs_hash = self._get_inputs_hash(result)
        pattern = os.path.join(
            context.report_dir,
            'stage*',
            f't2-4m_details.{safe_task}.{inputs_hash}.json',
        )
        matches = glob.glob(pattern)
        if not matches:
            return cache_path

        return max(matches, key=os.path.getmtime)

    def _get_cache_path(self, context, result):
        stage_number = self._get_stage_number(result)
        if stage_number is None:
            return None

        task_name = self._get_task_name(result)
        safe_task = ''.join([c if c.isalnum() or c in ('_', '-') else '_' for c in task_name])
        inputs_hash = self._get_inputs_hash(result)
        stage_dir = os.path.join(context.report_dir, 'stage%s' % stage_number)
        return os.path.join(stage_dir, f't2-4m_details.{safe_task}.{inputs_hash}.json')

    def update_mako_context(self, mako_context, pipeline_context, result):
        LOG.trace('No-op update_mako_context for %s', self.__class__.__name__)

    def render(self, context, result):
        cache_path = self._find_cached_path(context, result)
        task_name = self._get_task_name(result)

        if cache_path:
            if self.always_rerender:
                LOG.debug('T2_4MDetails: always_rerender=True for %s, skipping cache', task_name)
            elif os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r') as cache_file:
                        cached = json.load(cache_file)
                    cached_html = cached.get('html')
                    if cached_html:
                        LOG.debug('T2_4MDetails cache hit for %s (path: %s)', task_name, cache_path)
                        return cached_html
                except Exception as e:
                    LOG.debug('Failed to load cached details page from %s: %s', cache_path, e)
            else:
                LOG.debug('T2_4MDetails cache miss for %s (path does not exist)', task_name)
        else:
            LOG.debug('T2_4MDetails: no cache_path computed for %s', task_name)

        LOG.debug('T2_4MDetails rendering %s (computing display context)', task_name)
        display_context = self.get_display_context(context, result)
        uri = self.uri
        template = weblog.TEMPLATE_LOOKUP.get_template(uri)
        rendered = template.render(**display_context)

        if cache_path and not self.always_rerender:
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                payload = {
                    'task': task_name,
                    'inputs_hash': self._get_inputs_hash(result),
                    'html': rendered,
                }
                with open(cache_path, 'w') as cache_file:
                    json.dump(payload, cache_file)
                LOG.debug('T2_4MDetails cached %s (wrote %s)', task_name, cache_path)
            except Exception as e:
                LOG.debug('Failed to write cached details page to %s: %s', cache_path, e)

        return rendered

    def _get_log_url(self, context, result):
        """
        Get the URL of the stage log relative to the report directory.
        """
        stagelog_path = os.path.join(context.report_dir,
                                     'stage%s' % result.stage_number,
                                     'casapy.log')

        if not os.path.exists(stagelog_path):
            return None

        return os.path.relpath(stagelog_path, context.report_dir)


class T2_4MDetailsFailedTaskRenderer(T2_4MDetailsDefaultRenderer):
    """
    Renders detailed HTML output for a failed task.
    """
    def __init__(self, uri='t2-4m_details-failed.mako',
                 description='Failed task',
                 always_rerender=False):
        super(T2_4MDetailsFailedTaskRenderer, self).__init__(
            uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, results):

        # Collect tracebacks from all failed results in result list.
        tracebacks = utils.get_tracebacks(results)

        # Update the mako context.
        mako_context.update({
            'tracebacks': tracebacks,
        })


def time_order_dicts(mako_context, pipeline_context):
    """
    Time-sort any MS-related entries in the Mako context dictionary.
    """
    time_ordered_data = sorted(pipeline_context.observing_run.measurement_sets,
                               key=lambda ms:ms.start_time['m0']['value'])

    order_mapping = {ms.name: i for i, ms in enumerate(time_ordered_data)}
    order_mapping.update({os.path.basename(k): v for k, v in order_mapping.items()})

    return reorder_dicts(order_mapping, mako_context)


def reorder_dicts(order_mapping, d):
    # Only reorder when it makes a difference. The test is not len(d)<2 as the
    # dict could be a single key pointing to another collection that needs
    # sorting.
    if len(d) == 0:
        return d

    # reorder any dict values first
    for k, v in d.items():
        if isinstance(v, dict):
            d[k] = reorder_dicts(order_mapping, v)

    # Now reorder this dict's keys, if necessary

    # only reorder dicts with string keys
    if not all((isinstance(k, str) for k in d)):
        return d

    # Only reorder dicts when all the keys begin with an MS name. An exact
    # match is not used as the keys could be caltable names, which only begin
    # with the MS name.
    if not all((any((key.startswith(o) for o in order_mapping)) for key in d)):
        return d

    # this dict is necessary as order_mapping stores ms names, whereas we may
    # need to reorder caltable names which would not be in the original map
    key_order = {key: order_mapping[o] for key in d for o in order_mapping if key.startswith(o)}

    # create the time-ordered collection
    ordered = collections.OrderedDict(sorted(d.items(), key=lambda t: key_order[t[0]]))

    return ordered


class CommonRenderer(object):
    def __init__(self, uri, context, result):
        self.uri = uri
        self.context = context
        self.result = result
        # this should be overwritten by the superclass constructor, otherwise
        # an exception will occur when the template is rendered
        self.path = None

        # when the calling context is rendering a page of plots for all MSes,
        # the constructor is given a list of results rather than a single
        # result
        if isinstance(result, collections.abc.Iterable):
            stage_number = result[0].stage_number
        else:
            stage_number = result.stage_number
        stage = 'stage%s' % stage_number

        self.dirname = os.path.join(context.report_dir, stage)

    def render(self):
        path_to_resources_pkg = str(files(resources.__name__))
        path_to_js = os.path.join(path_to_resources_pkg, 'js', 'pipeline_plots.min.js')
        use_minified_js = os.path.exists(path_to_js)

        mako_context = {
            'pcontext': self.context,
            'result': self.result,
            'dirname': self.dirname,
            'use_minified_js': use_minified_js,
        }
        self.update_mako_context(mako_context)
        t = weblog.TEMPLATE_LOOKUP.get_template(self.uri)
        return t.render(**mako_context)

    def update_mako_context(self, mako_context):
        pass

    def get_file(self):
        if self.path is None:
            LOG.error('No path specified for renderer')
            raise IOError()

        if not os.path.exists(self.dirname):
            os.makedirs(self.dirname)

        file_obj = open(self.path, 'w')
        return contextlib.closing(file_obj)


class JsonPlotRenderer(CommonRenderer):
    def __init__(self, uri, context, result, plots, title, outfile):
        super(JsonPlotRenderer, self).__init__(uri, context, result)
        self.plots = plots
        self.title = title
        self.path = os.path.join(self.dirname, outfile)

        # all values set on this dictionary will be written to the JSON file
        d = {}
        for plot in plots:
            # calculate the relative pathnames as seen from the browser
            thumbnail_relpath = os.path.relpath(plot.thumbnail,
                                                self.context.report_dir)
            image_relpath = os.path.relpath(plot.abspath,
                                            self.context.report_dir)
            json_dict_for_plot = {'thumbnail' : thumbnail_relpath}
            # push the most commonly used filter parameters directly into the
            # JSON dictionary to save the extending classes from doing it in
            # update_json_dict
            for param in ('vis', 'session', 'spw', 'scan', 'ant', 'baseband',
                          'field', 'pol'):
                if param in plot.parameters:
                    json_dict_for_plot[param] = str(plot.parameters[param])
            self.update_json_dict(json_dict_for_plot, plot)

            # Javascript JSON parser doesn't like Javascript floating point
            # constants (NaN, Infinity etc.), so convert them to null. We
            # do not omit the dictionary entry so that the plot is hidden
            # by the filters.
            for k, v in json_dict_for_plot.items():
                if isinstance(v, float):
                    if math.isnan(v) or math.isinf(v):
                        json_dict_for_plot[k] = 'null'

            d[image_relpath] = json_dict_for_plot

        self.json = json.dumps(d)

    def update_json_dict(self, d, plot):
        """
        Hook function that can be used by extending classes to extract extra
        parameters from the plot object and insert them into the JSON
        dictionary for that plot.
        """
        pass

    def update_mako_context(self, mako_context):
        super(JsonPlotRenderer, self).update_mako_context(mako_context)
        well_formed = self.json.replace("'", "\\'").replace('"', '&quot;')

        mako_context.update({'plots': self.plots,
                             'json': well_formed,
                             'plot_title': self.title})
