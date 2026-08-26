import os

import numpy as np

import scipy.interpolate as interpolate

import pipeline.hsd.heuristics.SDcalatmcorr as sdatm
import pipeline.infrastructure.casa_tools as casa_tools


test_data = casa_tools.utils.resolve("pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23/uid___A002_X85c183_X36f_SPW15_23.ms")


def get_reference_tau() -> dict:
    """Read tau stored in ASDM_CALATMOSPHERE table of the test data.

    Returns:
        tau and associated frequency arrays for each baseband.
    """
    basebands = [1, 2, 3, 4]
    calatm_table = os.path.join(test_data, "ASDM_CALATMOSPHERE")
    tau_ref = {}
    with casa_tools.TableReader(calatm_table) as tb:
        for bb in basebands:
            sel = tb.query(f'basebandName=="BB_{bb}" && syscalType=="TEMPERATURE_SCALE"')
            fullfreq = sel.getcell('frequencySpectrum', 0)
            tau = sel.getcell('tauSpectrum', 0)[0]
            if len(fullfreq) > 1 and fullfreq[0] > fullfreq[-1]:
                tau_ref[f"BB_{bb}"] = (fullfreq[::-1], tau[::-1])
            else:
                tau_ref[f"BB_{bb}"] = (fullfreq, tau)
    return tau_ref


def get_spw_setup() -> dict:
    """Construct spw_setup dictionary for test data.

    Returns:
        spw setup dictionary.
    """
    spw_ids = [17, 19, 21, 23]
    spw_table = os.path.join(test_data, "SPECTRAL_WINDOW")
    with casa_tools.TableReader(spw_table) as tb:
        chan_freqs = {
            spw_id: tb.getcell("CHAN_FREQ", spw_id) for spw_id in spw_ids
        }
        bb_names = {
            spw_id: f"BB_{tb.getcell("BBC_NO", spw_id)}" for spw_id in spw_ids
        }

    spw_setup = {
        spw_id: {
            "chanfreqs": chan_freqs[spw_id],
            "BBname": bb_names[spw_id],
            "nchan": len(chan_freqs[spw_id])
        }
        for spw_id in spw_ids
    }
    spw_setup["spwlist"] = spw_ids

    return spw_setup


def get_tau(*args, **kwargs) -> np.ndarray:
    """Call appropriate function to get tau.

    Returns:
        tau (optical depth)
    """
    if hasattr(sdatm, "getTau"):
        tau = sdatm.getTau(*args, **kwargs)
    else:
        tau = sdatm.getCalAtmData(*args, **kwargs)[-2]
    return tau


def test_getTau_full():
    """Test getTau for spws that cover entire range of baseband."""
    tau_base = get_reference_tau()

    spw_setup = get_spw_setup()

    tau = get_tau(test_data, spw_setup["spwlist"], spw_setup)
    for spw_id in spw_setup["spwlist"]:
        base_freq, base_tau = tau_base[spw_setup[spw_id]["BBname"]]
        interpolator = interpolate.CubicSpline(base_freq, base_tau)
        tau_ref = interpolator(spw_setup[spw_id]["chanfreqs"])
        assert np.all(tau[spw_id] >= 0)
        assert np.allclose(tau[spw_id], tau_ref, rtol=1e-5, atol=1e-8)


def test_getTau_partial():
    """Test getTau for spw that only covers a part of baseband.

    Test cases for the spw covering lower frequency end of the LSB spw.

    Channel range is adjusted to trigger a bug reported to PIPE-3226.
    Intention is not to overlap the frequency range of spw
    with the baseband frequency range selected for interpolation
    in the original logic. While spw 17 is FDM window with 1024 channels,
    tau was measured using TDM setup with 128 channels for the same
    frequency coverage. To avoid the overlap, nchan for partial spw
    setup is set to 100 which corresponds to ~10 channels in TDM window.
    Schematic diagram of channel selection designed for this test
    is shown below. "=" indicates selected channels.

    freq (LSB): low                                         high
      spw chan: 100        0
                 |=========|---------------------------------|
      tau chan: 128           100                            0
                 |-------------|=============================|
    If the bug emerges, resulting tau will be negative.
    """
    tau_base = get_reference_tau()

    spw_setup = get_spw_setup()

    # LSB: spw 17
    nchan_partial = 100
    lsb_split_setup = {
        17: {
            "chanfreqs": spw_setup[17]["chanfreqs"][-nchan_partial:],
            "BBname": spw_setup[17]["BBname"],
            "nchan": nchan_partial
        },
    }
    lsb_split_setup["spwlist"] = [17]
    tau = get_tau(test_data, lsb_split_setup["spwlist"], lsb_split_setup)
    for spw_id in lsb_split_setup["spwlist"]:
        base_freq, base_tau = tau_base[spw_setup[17]["BBname"]]
        interpolator = interpolate.CubicSpline(base_freq, base_tau, bc_type='not-a-knot')
        tau_ref = interpolator(lsb_split_setup[spw_id]["chanfreqs"])
        assert np.all(tau[spw_id] >= 0)
        assert np.allclose(tau[spw_id], tau_ref, rtol=1e-5, atol=1e-8)
