from __future__ import annotations

import math
import typing

import numpy as np

from pipeline.domain.measures import FrequencyUnits
import pipeline.infrastructure.casa_tools as casa_tools
import pipeline.infrastructure.logging as logging

if typing.TYPE_CHECKING:
    from pipeline.domain.observingrun import ObservingRun
    from pipeline.domain.measurement_set import MeasurementSet


LOG = logging.get_logger(__name__)

me = casa_tools.measures
qa = casa_tools.quanta


def configure_frequency(
    observing_run: ObservingRun,
    ms_list: list[MeasurementSet],
    is_single_dish: bool
) -> dict[tuple[str, int], dict[str, int | dict[str, float | str]]]:
    # get list of virtual spw ids
    ref_ms = ms_list[0]
    sci_spw_virtual_ids = [
        observing_run.real2virtual_spw_id(spw_id=spw.id, target_ms=ref_ms)
        for spw in ref_ms.get_spectral_windows(science_windows_only=True)
    ]

    # get list of target sources
    target_sources = np.unique(
        [list(map(lambda x: x.source.name, ms.get_fields(intent="TARGET")))
         for ms in ms_list]
    )

    # output dictionary
    # key: (source_name, vspw_id)
    # value: {"start": start_freq, "width": width, "nchan": nchan}
    transform_config = {}
    for source_name in target_sources:
        # collect MS that contains the source specified as source_name
        target_ms_list = []
        for ms_obj in ms_list:
            target_sources = [s.name for s in ms_obj.sources if s.name == source_name]
            if len(target_sources) > 0:
                target_ms_list.append(ms_obj)

        LOG.info(f"Source {source_name}: {len(target_ms_list)} MSs selected \n {[ms.basename for ms in target_ms_list]}")

        for vspw_id in sci_spw_virtual_ids:
            is_lsb = None
            nchan = None
            chan_width = None
            max_lsrk_freq = None
            min_lsrk_freq = None
            for ms_obj in target_ms_list:
                spw_id = observing_run.real2virtual_spw_id(spw_id=vspw_id, target_ms=ms_obj)
                spw = ms_obj.spectral_windows[spw_id]
                max_topo_freq = float(spw.max_frequency.convert_to(FrequencyUnits.HERTZ).value)
                min_topo_freq = float(spw.min_frequency.convert_to(FrequencyUnits.HERTZ).value)
                if is_lsb is None:
                    is_lsb = int(spw.sideband) < 0
                if nchan is None:
                    nchan = spw.num_channels
                if chan_width is None:
                    chan_width = (max_topo_freq - min_topo_freq) / nchan

                # frame conversion to LSRK
                target_source = [s for s in ms_obj.sources if s.name == source_name][0]
                if target_source.is_eph_obj:
                    print("Ephemeris source is not supported yet")
                    continue

                # frame conversion to LSRK
                me.done()
                # clear_time_cache()
                me.doframe(me.observatory(ref_ms.antenna_array.name))
                me.doframe(target_source.direction)
                if is_single_dish:
                    with casa_tools.MSReader(ms_obj.name) as _ms:
                        _ms.msselect({
                            "scanintent": "OBSERVE_TARGET#ON_SOURCE",
                            "spw": str(spw_id),
                            "field": ",".join(map(lambda x: str(x.id), target_source.fields))
                        })
                        start_time = np.min(_ms.getdata(["time"])["time"])
                else:
                    start_time = np.unique([f.time for f in target_source.fields])[0]
                LOG.info(f"    DEBUG: {ms_obj.basename} {target_source.name} start_time {start_time} sec")
                me.doframe(me.epoch(rf="UTC", v0=qa.quantity(start_time, "s")))
                _max_freq = me.measure(v=me.frequency(rf="TOPO", v0=qa.quantity(max_topo_freq, "Hz")), rf="LSRK")["m0"]["value"]
                _min_freq = me.measure(v=me.frequency(rf="TOPO", v0=qa.quantity(min_topo_freq, "Hz")), rf="LSRK")["m0"]["value"]
                LOG.info(f"    DEBUG: {ms_obj.basename} {target_source.name} TOPO max {max_topo_freq}, LSRK max {_max_freq}, TOPO min {min_topo_freq}, LSRK min {_min_freq}")

                # retrieve overlapping frequency region
                if max_lsrk_freq is None or _max_freq < max_lsrk_freq:
                    max_lsrk_freq = _max_freq
                if min_lsrk_freq is None or _min_freq > min_lsrk_freq:
                    min_lsrk_freq = _min_freq

            LOG.info(f"Source {source_name}, vspw_id {vspw_id}: is_lsb {is_lsb}, nchan {nchan}, min_lsrk_freq {min_lsrk_freq}, max_lsrk_freq {max_lsrk_freq}")

            if is_lsb:
                width = chan_width * -1.0
                start_freq = max_lsrk_freq
            else:
                width = chan_width
                start_freq = min_lsrk_freq

            start_freq += width * 0.01  # shift 1% of width
            start_freq += width / 2  # channel edge -> channel center

            # store the configuration
            key = (source_name, vspw_id)
            transform_config[key] = {
                "start": qa.quantity(start_freq, "Hz"),
                "width": qa.quantity(width, "Hz"),
                "nchan": nchan
            }

    return transform_config
