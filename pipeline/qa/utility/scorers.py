#!/usr/bin/env python

'''Generic scorer classes.'''

import numpy as np
from scipy.special import erf


class erfScorer(object):

    def __init__(self, good_level, bad_level, lowest_score=0.0):
        """
        Error function based scorer between two levels with
        optional lower score limit so that the QA score ranges
        from lowest_score to 1.0.
        """

        assert 0.0 <= lowest_score < 1.0, "Erf scorer lowest score must be in [0,1)."

        self.good_level = good_level
        self.bad_level = bad_level
        self.lowest_score = lowest_score
        self.slope = 6.0 / np.sqrt(2.0) / (good_level - bad_level)
        self.offset = 3.0 / np.sqrt(2.0) * (1.0 - 2.0 * good_level / (good_level - bad_level))

    def __call__(self, x):
        return (1.0 - self.lowest_score) * (erf(x * self.slope + self.offset) + 1.0) / 2.0 + self.lowest_score


class gaussScorer(object):

    def __init__(self, x0, sigma):
        self.x0 = x0
        self.sigma = sigma

    def __call__(self, x):
        return np.exp(-4.0 * np.log(2.0) * np.power((x - self.x0) / self.sigma, 2))
