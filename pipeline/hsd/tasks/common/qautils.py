"""
SingleDish tools related to QA

QAScoreProperiesRegistry: Holds the parameters to control the behavior
QAScoreFormatter: Holds methods to re-format QA scores
QAScoreAggregator: Aggregates messages in QA score
"""
from __future__ import annotations

import copy
import functools
import math
from operator import attrgetter
from typing import TYPE_CHECKING, Callable

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.pipelineqa as pqa

if TYPE_CHECKING:
    from pipeline.infrastructure.api import Results
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.get_logger(__name__)


class QAScorePropertiesRegistry:
    """
    Class to hold QAScore formats
    """
    def __init__(self):
        """
        Construct QAScorePropertiesRegistry instance
        """
        self.longmsg_format_dict = {}
        self.keys_dict = {}
        self.to_aggregate_dict = {}
        self.excludes = []

    def register_longmsg_format(self, metric_name: str, template: str):
        """
        Register longmsg_format with metric_name as a key

        Args:
            metric_name : QA score metric name
            template    : longmsg format
        """
        self.longmsg_format_dict[metric_name] = template

    def register_longmsg_keys(self, metric_name: str, keys: list[str]):
        """
        Register longmsg_keys with metric_name as a key

        Args:
            metric_name : QA score metric name
            keys        : longmsg_ksys
        """
        self.keys_dict[metric_name] = keys

    def register_keys_to_aggregate(self, metric_name: str, keys: list[str]):
        """
        Register keys_to_aggregate with metric_name as a key

        Args:
            metric_name : QA score metric name
            keys        : longmsg_ksys
        """
        self.to_aggregate_dict[metric_name] = keys

    def register_excludes(self, metric_names: list[str]):
        """
        Register metric_name to excludes list

        Args:
            metric_names : List of QA score metric names to exclude
        """
        self.excludes = metric_names

    def get_longmsg_format(self, metric_name: str) -> str | None:
        """
        Get the QA score template associated with metric_name

        Args:
            metric_name : QA score metric name
        Returns:
            longmsg_format associated with the metric_name
            None if the longmsg_format associated with the metric_name is not registered
        """
        return self.longmsg_format_dict.get(metric_name)

    def get_longmsg_keys(self, metric_name: str) -> str | None:
        """
        Get the keys associated with metric_name

        Args:
            metric_name : QA score metric name
        Returns:
            longmsg_keys associated with the metric_name
            None if the longmsg_keys associated with the metric_name is not registered
        """
        return self.keys_dict.get(metric_name)

    def get_keys_to_aggregate(self, metric_name: str) -> str | None:
        """
        Get the keys_to_aggregate associated with metric_name

        Args:
            metric_name : QA score metric name
        Returns:
            longmsg_keys associated with the metric_name
            None if the longmsg_keys associated with the metric_name is not registered
        """
        return self.to_aggregate_dict.get(metric_name)

    def get_excludes(self) -> list[str]:
        """
        Get the metric_names to exclude

        Returns:
            List of metric_names to exclude
        """
        return self.excludes


class QAScoreFormatter:
    """
    Class to re-format the QA scores
    """
    def __init__(self):
        """
        Construct QAScoreFormatterr instance
        """
        pass

    def update_longmsg(self,
                       qascore: pqa.QAScore,
                       longmsg_format: str | None = None,
                       longmsg_keys: list[str] | None = None,
                       force_update: bool = False):
        """
        Update longmsg of QA score with asocciated keys in applies_to

        If no template is provided, the default template will be generated in this method.

        Args:
            qascore: QA score
            longmsg_format:        Template of the longmsg
                                       Default is to apply the format registered in the registry
                                       if no format is pre-registered for the metric_name,
                                       the standard format will be used
            longmsg_keys:          List of keys to show on the updated longmsg of QA score,
                                       default is None which applies all keys in applies_to of QA score
                                       longmsg_format will be used regardless the longmsg_keys if longmsg_format is specified
            force_update:          True to Update the longmsg even if TargetDataSelection is empty
                                       default is False which inhibits to update longmsg for an empty TargetDataSelection
        """
        # skip formatting if the metric_name is in the excludes list
        if qascore.origin.metric_name in registry.get_excludes():
            return

        # if longmsg_keys is not specified, try to get it from the registry
        if longmsg_keys is None:
            longmsg_keys = registry.get_longmsg_keys(qascore.origin.metric_name)
            # apply all keys in TargetDataSelection if longmsg_keys still does not exist
            if longmsg_keys is None:
                longmsg_keys = list(vars(qascore.applies_to).keys())

        # inhibit formatting if 1) everything associated with longmsg_keys are empty and 2) force_update is False
        # this will prevent longmsg from being unintentionally overwritten with shortmsg
        if all(len(getattr(qascore.applies_to, key)) == 0 for key in longmsg_keys) and not force_update:
            return

        # if longmsg_format is not specified, try to get it from the registry
        if longmsg_format is None:
            longmsg_format = registry.get_longmsg_format(qascore.origin.metric_name)
            # compose the standard format form longmsg_keys if longmsg_format is still undefined
            if longmsg_format is None:
                longmsg_format = '{shortmsg}'   # template always starts with the shortmsg.
                for key in longmsg_keys:
                    match key:
                        case "vis":
                            longmsg_format +=  '  MS: {vis}' if len(qascore.applies_to.vis) > 0 else ''
                        case "ant":
                            longmsg_format +=  '  Antenna: {ant}' if len(qascore.applies_to.ant) > 0 else ''
                        case _:
                            longmsg_format += f'  {key.capitalize()}: {{{key}}}' if len(getattr(qascore.applies_to, key)) > 0 else ''
        # compose and update the longmsg
        qascore.longmsg = longmsg_format.format(shortmsg=qascore.shortmsg,
                                                score_metric=qascore.origin.metric_name,
                                                vis=', '.join(sorted(qascore.applies_to.vis)),
                                                field=', '.join(sorted(qascore.applies_to.field)),
                                                intent=', '.join(sorted(qascore.applies_to.intent)),
                                                spw=', '.join(sorted([str(v) for v in qascore.applies_to.spw], key=smartsort)),
                                                ant=', '.join(sorted(qascore.applies_to.ant)),
                                                pol=', '.join(sorted(qascore.applies_to.pol)),
                                                scan=', '.join(sorted([str(v) for v in qascore.applies_to.scan], key=smartsort)))


class QAScoreAggregator:
    """
    Class for QA score aggregation
    """
    def __init__(self,
                 keys_to_aggregate: list[str] | None = None,
                 preserve_original: bool = False,
                 precision: int = 2,
                 always_update_longmsg: bool = True):
        """
        Construct QAScoreAggregator instance

        keys_to_aggregate:     List of keys to aggregate.
                                   Hierarchial matches will be done in the order of the list
                                   (list is higher to lower hierarchy)
                                   defalt is None to apply [ 'vis', 'field', 'spw', 'ant', 'pol' ]
        preserve_original:     Whether to attach the list of original QA scores with WebLogLocation.HIDDEN. Default is False.
        precision:             Number of decimal places to round score values. Default is 2.
        always_update_longmsg: Update longmsg and round the score regardless the aggregation. Default is True.
        """
        self.keys_to_aggregate = ['vis', 'field', 'spw', 'ant', 'pol'] \
            if keys_to_aggregate is None else keys_to_aggregate
        self.preserve_original = preserve_original
        self.precision = precision
        self.always_update_longmsg = always_update_longmsg

    def update_origin(self,
                      destination: pqa.QAScore,
                      qascores: list[pqa.QAScore],
                      matched_idxes: list[int],
                      metric_scores_func: Callable[[list[float]], float] | None = None):
        """
        Update origin of a QA score to accommodate aggregated metric_scores

        The aggregation will simply concatinate the metric scores with commas

        Args:
            destination:        QA score to update origin field
            qascores:           List of QA scores
            matched_idxes:      List of indexes of QA scores to aggregate
            metric_scores_func: Function to calculate the metric_score when aggregating.
                                Default is None, which concatenates the metric_scores as a string.
        """
        names   = [qascores[idx].origin.metric_name for idx in matched_idxes]
        mscores = [qascores[idx].origin.metric_score for idx in matched_idxes]
        units   = [qascores[idx].origin.metric_units for idx in matched_idxes]

        assert len(set(names)) == 1
        assert len(set(units)) == 1
        if metric_scores_func is None:
            newscore = ", ".join(str(s) for s in mscores)
        else:
            newscore = metric_scores_func(mscores)
        new_origin = pqa.QAOrigin(metric_name=names[0],
                                  metric_score=newscore,
                                  metric_units=units[0])
        destination.origin = new_origin

    def _compare_applies_to(self,
                            qascore1: pqa.QAScore,
                            qascore2: pqa.QAScore,
                            keys_to_compare: list[str]) -> bool:
        """
        Compare the specific attribute in applies_to of qascores

        Args:
            qascore1, qascore2: QAScores to compare.
            keys_to_compare:    List of keys to participate in the comparizon.
        Returns:
            Whether specified attributes in two QAScores agree.
        """
        return all(getattr(qascore1.applies_to, key) == getattr(qascore2.applies_to, key)
                   for key in keys_to_compare)

    def _aggregate_qascores(self,
                            qascores: list[pqa.QAScore],
                            metric_name: str,
                            metric_scores_func: Callable[[list[float]], float] | None = None) -> list[pqa.QAScore]:
        """
        Aggregate and recompose longmsg-es of QA scores with specified metric_name

        Aggregates the QA scores with provided metric_name dependent parameters,
        such as keys_to_aggregate and keys_to_show.
        This method is coded to respect the original 'order' of QA scores during the aggregation.

        Aggregation happens within QA scores whose score, shortmsg, metric_name, and metric_units match:
        attributes in TargetDataSelection (applies_to) are merged, meric_value will be concateneted with commas

        Args:
            qascores:    list of QA scores
            metric_name: metric_name to target
            metric_scores_func: Function to calculate the metric_score when aggregating.
                                Default is None, which concatenates the metric_scores as a string.
        Returns:
            Aggregated QA scores
        """
        # torelance is set to smaller than the precision for 1 digit
        eps = pow(10, -(1 + self.precision))
        # prepare the formatter
        formatter = QAScoreFormatter()

        # all keys in QAScore applies_to
        all_keys = list(vars(qascores[0].applies_to).keys())

        # set the aggregation parameters from metric_name
        keys_to_aggregate = registry.get_keys_to_aggregate(metric_name)
        if keys_to_aggregate is None:
            keys_to_aggregate = all_keys

        # keys to show on accordion
        keys_to_show = registry.get_longmsg_keys(metric_name)
        if keys_to_show is None:
            keys_to_show = all_keys

        # Now parameters are ready. Start aggergating with each keys in keys_to_aggregate
        for key in reversed(keys_to_aggregate):   # do keys in lower hierarchy first
            # set keys to use to match QA scores
            keys_to_compare = keys_to_show.copy()
            keys_to_compare.remove(key)

            # first preseve a copy of "qascores" at this point to use it for looping
            # since "qascores" evolves during the following loop.
            original_qascores = qascores[:]

            # scan through original_qascores
            for target_qascore in original_qascores:
                # go next if the target_qascore is already removed during former aggregation during the loop
                if target_qascore not in qascores:
                    continue

                # skip qascores with metric_name registered as excludes
                if target_qascore.origin.metric_name in registry.get_excludes():
                    continue

                # filter out qascores with different metric_name
                if target_qascore.origin.metric_name != metric_name:
                    continue

                # skip if none of the keys of 'keys_to_aggregate' exist in target_qascore
                if all(len(getattr(target_qascore.applies_to, key)) == 0 for key in keys_to_aggregate):
                    formatter.update_longmsg(target_qascore)
                    continue

                # now the target qascore is selected
                target_idx = qascores.index(target_qascore)

                # go through qascores and find matches to aggregate
                matched_keys = []
                matched_idxes = []
                for idx, qascore in enumerate(qascores):
                    if idx < target_idx:  # always search forward from target_qascore
                        continue
                    if math.fabs(qascore.score - target_qascore.score) < eps \
                       and qascore.origin.metric_name == target_qascore.origin.metric_name \
                       and qascore.origin.metric_units == target_qascore.origin.metric_units \
                       and qascore.shortmsg == target_qascore.shortmsg:
                        if self._compare_applies_to(qascore, target_qascore, keys_to_compare):
                            matched_keys.append(getattr(qascore.applies_to, key))
                            matched_idxes.append(idx)

                # process if matches are found
                if len(matched_idxes) > 1:
                    # replace the first matched QAScore with the aggregated one, remove the other matches
                    setattr(qascores[matched_idxes[0]].applies_to, key, set().union(*matched_keys))
                    self.update_origin(qascores[matched_idxes[0]], qascores, matched_idxes, metric_scores_func=metric_scores_func)
                    formatter.update_longmsg(qascores[matched_idxes[0]])
                    # remove
                    for idx in reversed(matched_idxes[1:]):   # remove in reversed order to conserve the index
                        qascores.pop(idx)
                elif self.always_update_longmsg:
                    formatter.update_longmsg(target_qascore)

        return qascores

    def aggregate_qascores(self,
                           orig_qascores: list[pqa.QAScore],
                           metric_scores_func: Callable[[list[float]], float] | None = None) -> list[pqa.QAScore]:
        """
        Aggregate QA scores

        Picks all the metric_name-s from the list of QA scores,
        and do the aggregation for each metric_name.
        This is because the behaviour defined in the registry depends on metric_name.
        Scores (QAScore.score) are rounded to the specified precision

        Args:
            orig_qascores: Original list of QA scores
            metric_scores_func: Function to calculate the metric_score when aggregating.
                                Default is None, which concatenates the metric_scores as a string.
        Returns:
            Aggregated List of QA scores (and, if requested, the original QA scores with WegLogLocation.HIDDEN)
        """
        # round score values
        qascores = copy.deepcopy(orig_qascores)
        for qascore in qascores:
            qascore.score = round(qascore.score, self.precision)

        # collect metric_names
        metric_names = []
        for qascore in orig_qascores:
            if qascore.origin.metric_name not in metric_names:
                metric_names.append(qascore.origin.metric_name)

        # actual aggregation for each metric_name
        for metric_name in metric_names:
            qascores = self._aggregate_qascores(qascores, metric_name, metric_scores_func=metric_scores_func)

        # attach original qascores if requested
        if self.preserve_original:
            for qascore in orig_qascores:
                qascore.weblog_location = pqa.WebLogLocation.HIDDEN
                qascores.append(qascore)

        return qascores


def sort_qascores(method: Callable) -> Callable:
    """
    Decorator to sort QAScores with their 'score's

    Args:
        method: original method to be decorated
    Returns:
        wrapper method for decorating
    """
    @functools.wraps(method)
    def wrapper(self, context: Context, result: Results) -> str:
        # sort QAScores with 'score's
        result.qa.pool.sort(key=attrgetter("score"))

        return method(self, context, result)

    return wrapper


def aggregate_qascores(method: Callable) -> Callable:
    """
    Decorator to add a feature to aggregate QAScores

    Args:
        method: original method to be decorated
    Returns:
        wrapper method for decorating
    """
    @functools.wraps(method)
    def wrapper(self, context: Context, result: Results) -> str:
        # aggregate QAScores
        aggregator = QAScoreAggregator()
        result.qa.pool = aggregator.aggregate_qascores(result.qa.pool)

        return method(self, context, result)

    return wrapper


def smartsort(x: any) -> tuple[int, any]:
    """
    Auxiliary method to sort a numerical value / str mixed list

    This can be used with sorted as: sorted(arr, key=smartsort)
    Numerical values stored as str are coverted to float for evaluation.
    ex)
     ['11.0', '6', '5.0deg', '4.3'] -> ['4.3', '6', '11.0', '5.0deg']

    Args:
        x : any value
        Returns:
            (0, float(x)) : if x is a numerical value
            (1, x)        : if x is not a numerical value (ex. str)
    """
    try:
        return (0, float(x))
    except ValueError:
        return (1, x)


registry = QAScorePropertiesRegistry()
