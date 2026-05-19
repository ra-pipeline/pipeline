"""Test module for atmutil.py."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest
import numpy as np

from pipeline.infrastructure import casa_tools

from .atmutil import init_at, calc_airmass, calc_transmission
from .atmutil import get_dry_opacity, get_wet_opacity
from .atmutil import _test
from .atmutil import get_spw_spec, get_median_elevation, get_transmission
from .atmutil import AtmType

if TYPE_CHECKING:
    from numpy.typing import NDArray

defaultAtm = dict(humidity=20.0, temperature=270.0, pressure=560.0,
                  atmtype=AtmType.midLatitudeWinter, altitude=5000.0,
                  fcenter=100.0, nchan=4096, resolution=0.001)
vis = 'uid___A002_X85c183_X36f.ms'


def __update_atmparam(in_param: dict) -> dict:
    """
    Merge test specific atmospheric parameters with default ones.

    Args:
        in_param: A dictionary that specifies non-default parameters
            to initialize atmospheric model. The key is parameter
            name and value is corresponding parameter value. See
            parameters of atmutil.init_at for available parameters.

    Returns:
        A dictionary of atmospheric parameters to be used in init_at.
    """
    atmparam = defaultAtm.copy()
    atmparam.update(in_param)
    return atmparam


@pytest.mark.parametrize("in_param",
                         ({}, dict(humidity=10.0),
                          dict(pressure=590.0),
                          dict(atmtype=AtmType.midLatitudeSummer),
                          dict(atmtype=AtmType.tropical),
                          dict(atmtype=AtmType.subarcticSummer),
                          dict(atmtype=AtmType.midLatitudeWinter),
                          dict(fcenter=350.0), dict(nchan=128),
                          dict(resolution=0.000015)))
def test_init_at(in_param: dict):
    """
    Test init_at.

    Initialize atmosphere with various parameter values and validate
    parameters set to casa atmosphere tool.

    Args:
        in_param: A dictionary that specifies non-default parameters
            to initialize atmospheric model. The key is parameter
            name and value is corresponding parameter value. See
            parameters of atmutil.init_at for available parameters.
    """
    myat = casa_tools.atmosphere
    myqa = casa_tools.quanta
    # Merge default and test parameters.
    in_atmparam = __update_atmparam(in_param)
    # Invoke init_at with a given parameter set
    init_at(myat, **in_atmparam)
    # Obtain parameters set to atmosphere tool and compare it with inputs
    atmparams = myat.getBasicAtmParms()
    altitude = myqa.getvalue(myqa.convert(atmparams[1], 'm'))
    temperature = myqa.getvalue(myqa.convert(atmparams[2], 'K'))
    pressure = myqa.getvalue(myqa.convert(atmparams[3], 'mbar'))
    humidity = atmparams[5]
    nchan = myat.getNumChan(0)
    resolution = myqa.getvalue(myqa.convert(myat.getChanSep(0), 'GHz'))
    fcenter = myqa.getvalue(
        myqa.convert(myqa.add(myat.getChanFreq(0, 0),
                              myat.getChanFreq(nchan-1)), 'GHz')) * 0.5
    assert np.allclose(altitude, in_atmparam['altitude'])
    assert np.allclose(temperature, in_atmparam['temperature'])
    assert np.allclose(pressure, in_atmparam['pressure'])
    assert np.allclose(humidity, in_atmparam['humidity'])
    assert np.allclose(nchan, in_atmparam['nchan'])
    assert np.allclose(resolution, in_atmparam['resolution'])
    assert np.allclose(fcenter,  in_atmparam['fcenter'])


@pytest.mark.parametrize("elevation, expected_airmass",
                         ((1.0, 57.29868849855063),
                          (15., 3.8637033051562737),
                          (30., 2.0),
                          (45., math.sqrt(2.0)),
                          (60., 1.1547005383792515),
                          (75., 1.035276180410083),
                          (90., 1.0))
                         )
def test_calc_airmass(elevation: float, expected_airmass: float):
    """
    Test atmutil.calc_airmass for various elevation.

    Args:
        elevation: Input elevation.
        expected_airmass: Expected air mass for the elevation.
    """
    airmass = calc_airmass(elevation)
    assert np.allclose(airmass, expected_airmass, rtol=1.e-5, atol=0.0)


@pytest.mark.parametrize("in_param, expected",
                         (((1.0, 0.15, 0.10), 0.7788007830714049),
                          ((2.0, 0.15, 0.10), 0.6065306597126334),
                          ((2.0, np.array([0.075, 0.10]),
                           np.array([0.05, 0.15])),
                           np.array([0.7788007830714049, 0.6065306597126334]))
                          ))
def test_calc_transmission(in_param: tuple[float, float | NDArray,
                                           float | NDArray],
                           expected: float | NDArray):
    """
    Test calc_transmission.

    Args:
        in_param: A tuple of (airmass, dry_opacity, wet_opacity) to be used
            in calc_transmission.

        expected: Expected return values.
    """
    transmission = calc_transmission(in_param[0], in_param[1],
                                     in_param[2])
    assert np.allclose(transmission, expected, rtol=1.e-5, atol=0.0)


@pytest.mark.parametrize(
        "in_param, expected",
        (({}, 47.97799117173652),
         (dict(humidity=10.0), 47.97692204026754),
         (dict(pressure=590.0), 52.83346335445199),
         (dict(atmtype=AtmType.midLatitudeSummer), 47.699469623464736),
         (dict(atmtype=AtmType.tropical), 48.47759847965915),
         (dict(atmtype=AtmType.subarcticSummer), 47.177987716625275),
         (dict(atmtype=AtmType.midLatitudeWinter), 47.97799117173652),
         (dict(fcenter=350.0), 97.4814491261267),
         (dict(nchan=128), 1.3969374062965147),
         (dict(resolution=0.000015), 44.69951867516774)
         ))
def test_get_dry_opacity(in_param: dict, expected: float):
    """
    Test get_dry_opacity.

    Args:
        in_param: A dictionary that specifies non-default parameters
            to initialize atmospheric model. The key is parameter
            name and value is corresponding parameter value. See
            parameters of atmutil.init_at for available parameters.
        expected: Expected sum of dry opacity.
    """
    myat = casa_tools.atmosphere
    in_atmparam = __update_atmparam(in_param)
    init_at(myat, **in_atmparam)
    dry_arr = get_dry_opacity(myat)
    assert np.allclose(np.sum(dry_arr), expected, rtol=1.e-5, atol=0.0)


@pytest.mark.parametrize(
        "in_param, expected",
        (({}, 45.69641110432566),
         (dict(humidity=10.0), 22.863805083506872),
         (dict(pressure=590.0), 48.14782023258896),
         (dict(atmtype=AtmType.midLatitudeSummer), 45.69813369056101),
         (dict(atmtype=AtmType.tropical), 45.70706972843769),
         (dict(atmtype=AtmType.subarcticSummer), 45.694188468935124),
         (dict(atmtype=AtmType.midLatitudeWinter), 45.69641110432566),
         (dict(fcenter=350.0), 1046.3702374546874),
         (dict(nchan=128), 1.4276360828433052),
         (dict(resolution=0.000015), 45.68434620611521)
         ))
def test_get_wet_opacity(in_param: dict, expected: float):
    """
    Test get_wet_opacity.

    Args:
        in_param: A dictionary that specifies non-default parameters
            to initialize atmospheric model. The key is parameter
            name and value is corresponding parameter value. See
            parameters of atmutil.init_at for available parameters.
        expected: Expected sum of wet opacity.
    """
    myat = casa_tools.atmosphere
    in_atmparam = __update_atmparam(in_param)
    init_at(myat, **in_atmparam)
    wet_arr = get_wet_opacity(myat)
    assert np.allclose(np.sum(wet_arr), expected, rtol=1.e-5, atol=0.0)


@pytest.mark.parametrize("in_param, expected",
                         (((1.0, 90.0), 0.9813874324999965),
                          ((1.0, 30.0), 0.9631266292255092),
                          ((1.5, 90.0), 0.9779208925243648),
                          ))
def test_test(in_param: tuple[float, float], expected: float):
    """
    Test method, test.

    Args:
        in_param: A tuple of (pwv, elevation) to be used to
                  invoke method, test.
        expected: Expected mean of transmission.
    """
    transmission = _test(in_param[0], in_param[1])
    assert np.allclose(np.mean(transmission), expected, rtol=1.e-5, atol=0.0)


@pytest.mark.skip(reason='need_vis')
@pytest.mark.parametrize("spwid, expected",
                         ((15, (114.68215, 128, 0.015625)),
                          (17, (100.95000, 4080, -0.000488281))
                          ))
def test_get_spw_spec(spwid: int, expected: tuple[float, int, float]):
    """
    Test get_spw_spec.

    Arg:
        spwid: A spwctral window ID to get spw specification.
        expected: An expected spw specification in a tuple of
            (the center frequency, nchan, resolution).
    """
    fcenter, nchan, resolution = get_spw_spec(vis, spwid)
    assert np.allclose(fcenter, expected[0], rtol=1.e-8, atol=0.0)
    assert nchan == expected[1]
    assert np.allclose(resolution, expected[2], rtol=1.e-5, atol=0.0)


@pytest.mark.skip(reason='need_vis')
@pytest.mark.parametrize("antid, expected",
                         ((0, 51.137000119425466),
                          (1, 51.13678069960953),
                          (2, 51.13635643503322)
                          ))
def test_get_median_elevation(antid: int, expected: float):
    """
    Test get_median_elevation.

    Args:
        antid: Antenna ID to calculate median elevation.
        expected: An expected median elevation.
    """
    elevation = get_median_elevation(vis, antid)
    assert np.allclose(elevation, expected, rtol=1.e-5, atol=0.0)


@pytest.mark.skip(reason='need_vis')
@pytest.mark.parametrize("antid, spwid, expected",
                         ((0, 15, 0.8427800044848566),
                          (1, 17, 0.9685033492155325)
                          ))
def test_get_transmission(antid: int, spwid: int, expected: float):
    """
    Test get_transmission.

    Args:
        antid: An Antenna ID to execute.
        spwid: A spectral window ID to execute.
        expected: An expected mean transmission.
    """
    _, transmission = get_transmission(vis, antid, spwid)
    assert np.allclose(np.mean(transmission), expected)
