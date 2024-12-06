
import abc
import collections
import enum
import operator
from typing import Optional, Set

# QAOrigin holds information to help understand how and from where the QA scores are derived
QAOrigin = collections.namedtuple('QAOrigin', 'metric_name metric_score metric_units')

# Default origin for QAScores that do not define their own origin
NULL_ORIGIN = QAOrigin(metric_name='Unknown metric',
                       metric_score='N/A',
                       metric_units='')

class TargetDataSelection:
    """
    TargetDataSelection is a struct to hold data selection metadata. Its various
    properties (vis, scan, spw, etc.) should be set to specify to which subset of
    data something applies.
    """
    def __init__(self, session: Set[str] = None, vis: Set[str] = None, scan: Set[int] = None,
                 spw: Set[int] = None, field: Set[int] = None, intent: Set[str] = None,
                 ant: Set[int] = None, pol: Set[str] = None):
        if session is None:
            session = set()
        if vis is None:
            vis = set()
        if scan is None:
            scan = set()
        if spw is None:
            spw = set()
        if field is None:
            field = set()
        if intent is None:
            intent = set()
        if ant is None:
            ant = set()
        if pol is None:
            pol = set()

        self.session = session
        self.vis = vis
        self.scan = scan
        self.spw = spw
        self.field = field
        self.intent = intent
        self.ant = ant
        self.pol = pol

    def __str__(self):
        attr_names = ['session', 'vis', 'scan', 'spw', 'field', 'intent', 'ant', 'pol']
        attr_strs = []
        for attr_name in attr_names:
            val = getattr(self, attr_name)
            if not val:
                continue
            msg = '{}={}'.format(attr_name, ','.join([str(o) for o in sorted(val)]))
            attr_strs.append(msg)
        all_attrs = ', '.join(attr_strs)
        return f'TargetDataSelection({all_attrs})'


class QAScore(object):
    def __init__(self, score, longmsg='', shortmsg='', vis=None, origin=NULL_ORIGIN, hierarchy='',
                 applies_to: Optional[TargetDataSelection]=None):
        """
        QAScore represent a normalised assessment of data quality.

        The QA score is normalised to the range 0.0 to 1.0. Any score outside
        this range will be truncated at presentation time to lie within this
        range.

        The long message may be rendered on the task detail page, depending on
        whether this score is considered significant and the rendering hints
        given by the weblog_location argument.

        The short message associated with a QA score is used on the task
        summary page when this task is considered representative for the stage.

        A QAScore is derived from an unnormalised metric, which should be
        provided as the 'origin' argument when available. These metrics may be
        exported to the AQUA report, depending on their significance to the
        task QA and whether AQUA metric export is enabled for the particular
        task.

        The weblog_location and hierarchy attributes are intended to be used
        together, set by appropriate task-specific aggregation logic in the
        QAPlugin code, to specify how this score should be aggregated in
        overall score calculations and if/how it should be presented in the
        weblog.

        The hierarchy attribute should be in dotted string format, e.g.,
        'amp_vs_freq.amp.slope'. QAPlugins use this metadata to organise how
        the score should be grouped for processing and aggregation.

        :param score: numeric QA score, in range 0.0 to 1.0
        :param longmsg: verbose textual description of this score
        :param shortmsg: concise textual summary of this score
        :param vis: name of measurement set assessed by this QA score (DEPRECATED)
        :param origin: metric from which this score was calculated
        :param weblog_location: destination for web log presentation of this
            score
        :param hierarchy: location in QA hierarchy, in dot-separated format
        :param applies_to: data selection covered by this QA assessment
        """
        self.score = score
        self.longmsg = longmsg
        self.shortmsg = shortmsg

        if applies_to is None:
            applies_to = TargetDataSelection()

        # if the 'vis' deprecated argument is supplied, add it to the data selection
        # TODO refactor all old uses of QAScore to supply applies_to rather than vis
        if vis is not None:
            applies_to.vis.add(vis)
        self.applies_to = applies_to

        self.origin = origin
        self.hierarchy = hierarchy

    def __str__(self):
        return 'QAScore(%r, %r, %r, %s)'.format(self.score, self.longmsg, self.shortmsg, self.applies_to)

    def __repr__(self):
        origin = None if self.origin is NULL_ORIGIN else self.origin

        return 'QAScore({!s}, longmsg={!r}, shortmsg={!r}, origin={!r}, applies_to={!s})'.format(
            self.score, self.longmsg, self.shortmsg, origin, self.applies_to)
