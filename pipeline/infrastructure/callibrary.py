# Do not evaluate type annotations at definition time.
from __future__ import annotations

import collections
import copy
import datetime
import functools
import itertools
import operator
import os
import uuid
import weakref
from typing import TYPE_CHECKING

import cachetools
import intervaltree

from casatasks.private.callibrary import applycaltocallib

from . import casa_tools, launcher, logging, utils

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from pipeline.domain import Field, MeasurementSet, SpectralWindow

LOG = logging.get_logger(__name__)

CalToArgs = collections.namedtuple('CalToArgs', ['vis', 'spw', 'field', 'intent', 'antenna'])

# struct used to link calapplication to the task and inputs that created it
CalAppOrigin = collections.namedtuple('CalAppOrigin', ['task', 'inputs'])

# observations before this date are considered Cycle 0 observations
CYCLE_0_END_DATE = datetime.datetime(2013, 1, 21, tzinfo=datetime.timezone.utc)


class CalApplication:
    """
    CalApplication maps calibration tables and their application arguments to
    a target data selection, encapsulated as CalFrom and CalTo objects
    respectively.

    Attributes:
        calto: The CalTo representing the data selection to which the
            calibration should apply.
        calfrom: The CalFrom representing the calibration and application
            parameters.
        origin: The CalAppOrigin marking how this calibration was created.
    """
    def __init__(self, calto: CalTo | list[CalTo], calfrom: CalFrom | list[CalFrom],
                 origin: CalAppOrigin | list[CalAppOrigin] | None = None) -> None:
        """
        Initialize a CalApplication object.

        Args:
            calto: CalTo object, or list thereof, representing the data
                selection(s) to which the calibration should apply.
            calfrom: CalFrom object, or list thereof, representing the
                calibration and application parameters.
            origin: CalOrigin object, or list thereof, marking how this
                calibration was created.
        """
        self.calto = calto

        if not isinstance(calfrom, list):
            calfrom = [calfrom]
        self.calfrom = calfrom

        if not isinstance(origin, list):
            origin = [origin]
        self.origin = origin

    @staticmethod
    def from_export(s: str) -> CalApplication:
        """
        Unmarshal a CalApplication from a string.

        Args:
            s: String representation of a CalApplication as a CASA applycal call.

        Returns:
            CalApplication object generated from given string.
        """
        d = eval(s.replace('applycal(', 'dict('))
        calto = CalTo(vis=d['vis'], field=d['field'], spw=d['spw'],
                      antenna=d['antenna'], intent=d['intent'])

        # wrap these values in a list if they are single valued,
        # eg. 'm31' -> ['m31']
        for key in ('gainfield', 'gaintable', 'interp'):
            if isinstance(d[key], str):
                d[key] = [d[key]]
        for key in ('calwt',):
            if isinstance(d[key], bool):
                d[key] = [d[key]]

        # do the same for spwmap. A bit more complicated, as a single valued
        # spwmap is a list of integers, or may not have any values at all.
        try:
            if not isinstance(d['spwmap'][0], list):
                d['spwmap'] = [d['spwmap']]
        except IndexError:
            d['spwmap'] = [d['spwmap']]

        zipped = list(zip(d['gaintable'], d['gainfield'], d['interp'], d['spwmap'], d['calwt']))

        calfroms = []
        for (gaintable, gainfield, interp, spwmap, calwt) in zipped:
            if os.path.exists(gaintable):
                with casa_tools.TableReader(gaintable) as caltable:
                    viscal = caltable.getkeyword('VisCal')

            else:
                LOG.warning('Could not access {}. Using heuristics to determine caltable type'
                            ''.format(os.path.basename(gaintable)))
                if 'tsys' in gaintable:
                    viscal = 'B TSYS'
                elif 'bcal' in gaintable:
                    viscal = 'B JONES'
                elif 'gpcal' in gaintable:
                    viscal = 'G JONES'
                elif 'gcal' in gaintable:
                    viscal = 'G JONES'
                elif 'gacal' in gaintable:
                    viscal = 'G JONES'
                else:
                    raise ValueError(gaintable)

            caltype = CalFrom.get_caltype_for_viscal(viscal)
            calfrom = CalFrom(gaintable, gainfield=gainfield, interp=interp,
                              spwmap=spwmap, calwt=calwt, caltype=caltype)
            LOG.trace('Marking caltable \'%s\' as caltype \'%s\''
                      '' % (gaintable, calfrom.caltype))

            calfroms.append(calfrom)

        return CalApplication(calto, calfroms)

    def as_applycal(self) -> str:
        """
        Get a representation of this object as a CASA applycal call.

        Returns:
            String representation of CalApplication as a CASA applycal call.
        """
        args = {
            'vis': self.vis,
            'field': self.field,
            'intent': self.intent,
            'spw': self.spw,
            'antenna': self.antenna,
            'gaintable': self.gaintable,
            'gainfield': self.gainfield,
            'spwmap': self.spwmap,
            'interp': self.interp,
            'calwt': self.calwt
        }

        for key in ('gaintable', 'gainfield', 'spwmap', 'interp', 'calwt'):
            if isinstance(args[key], str):
                args[key] = '\'%s\'' % args[key]

        return ('applycal(vis=\'{vis}\', field=\'{field}\', '
                'intent=\'{intent}\', spw=\'{spw}\', antenna=\'{antenna}\', '
                'gaintable={gaintable}, gainfield={gainfield}, '
                'spwmap={spwmap}, interp={interp}, calwt={calwt})'
                ''.format(**args))

    @property
    def antenna(self) -> str:
        """
        The antennas to which the calibrations apply.

        Returns:
            String representing the (comma-separated) antennas to which the
            calibrations apply.
        """
        return self.calto.antenna

    @property
    def calwt(self) -> bool | list[bool]:
        """
        The calwt parameter to be used when applying these calibrations.

        Returns:
            Boolean representing what to use for calwt for this calibration.
            If there are multiple CalFrom objects to apply, this returns a list
            of booleans, one per CalFrom.
        """
        l = [cf.calwt for cf in self.calfrom]
        return l[0] if len(l) == 1 else l

    def exists(self) -> bool:
        """
        Test whether all calibration tables referred to by this application exist.

        Returns:
            True if all calibration tables exist in the file system.
        """
        for cf in self.calfrom:
            if not os.path.exists(cf.gaintable):
                return False
        return True

    @property
    def field(self) -> str:
        """
        The field(s) to which the calibrations apply.

        Returns:
            String representing the field(s) (comma-separated) to apply the
            calibrations to.
        """
        return self.calto.field

    @property
    def gainfield(self) -> str | list[str]:
        """
        The gainfield parameters to be used when applying these calibrations.

        Returns:
            Value for the gainfield parameter to be used when applying these
            calibrations; returns a scalar string if representing 1 calibration,
            otherwise a list of strings.
        """
        l = [cf.gainfield for cf in self.calfrom]
        return l[0] if len(l) == 1 else l

    @property
    def gaintable(self) -> str | list[str]:
        """
        The gaintable parameters to be used when applying these calibrations.

        Returns:
            Value for the gaintable parameter to be used when applying these
            calibrations; returns a scalar string if representing 1 calibration,
            otherwise a list of strings.
        """
        l = [cf.gaintable for cf in self.calfrom]
        return l[0] if len(l) == 1 else l

    @property
    def intent(self) -> str:
        """
        The observing intent(s) to which the calibrations apply.

        Returns:
            String representing the intent(s) (comma-separated) to apply the
            calibrations to.
        """
        return self.calto.intent

    @property
    def interp(self) -> str | list[str]:
        """
        The interp parameters to be used when applying these calibrations.

        Returns:
            Value for the interp parameter to be used when applying these
            calibrations; returns a scalar string if representing 1 calibration,
            otherwise a list of strings.
        """
        l = [cf.interp for cf in self.calfrom]
        return l[0] if len(l) == 1 else l

    @property
    def spw(self) -> str:
        """
        Spectral window(s) to which the calibrations apply.

        Returns:
            String representing the spectral window id(s) (comma-separated) to
            apply the calibrations to.
        """
        return self.calto.spw

    @property
    def spwmap(self) -> str | list[str]:
        """
        The spwmap parameters to be used when applying these calibrations.

        Returns:
            Value for the spwmap parameter to be used when applying these
            calibrations; returns a scalar string if representing 1 calibration,
            otherwise a list of strings.
        """
        # convert tuples back into lists for the CASA argument
        l = [list(cf.spwmap) for cf in self.calfrom]
        return l[0] if len(l) == 1 else l

    @property
    def vis(self) -> str:
        """
        Name of the measurement set to which the calibrations apply.

        Returns:
            The name of the measurement set to which the calibrations apply.
        """
        return self.calto.vis

    def __str__(self) -> str:
        return self.as_applycal()

    def __repr__(self) -> str:
        return 'CalApplication(%s, %s)' % (self.calto, self.calfrom)


class CalTo:
    """
    CalTo represents a target data selection to which a calibration can be
    applied.
    """
    __slots__ = ('_antenna', '_intent', '_field', '_spw', '_vis')

    def __getstate__(self) -> tuple[str, str, str, str, str]:
        """Define what to pickle as a class instance."""
        return self._antenna, self._intent, self._field, self._spw, self._vis

    def __setstate__(self, state: tuple[str, str, str, str, str]) -> None:
        """Define how to unpickle a class instance."""
        self._antenna, self._intent, self._field, self._spw, self._vis = state

    @staticmethod
    def from_caltoargs(cta: CalToArgs) -> CalTo:
        """
        Returns a CalTo object for given arguments ``cta``.

        Args:
            cta: CalToArgs object representing the arguments for the new CalTo object.

        Returns:
            CalTo object initialized with given arguments ``cta``.
        """
        def join(s: set[str]) -> str:
            return ','.join((str(o) for o in s))
        return CalTo(vis=join(cta.vis), field=join(cta.field), spw=join(cta.spw), antenna=join(cta.antenna),
                     intent=join(cta.intent))

    def __init__(self, vis: str | None = None, field: str = '', spw: str = '', antenna: str = '', intent: str = '')\
            -> None:
        """
        Initialize a CalTo object.

        Args:
            vis: Name of the measurement set to which the calibrations apply.
            field: The field(s) to which the calibrations apply.
            spw: The spectral window(s) to which the calibrations apply.
            antenna: The antennas to which the calibrations apply.
            intent: The observing intent(s) to which the calibrations apply.
        """
        self.vis = vis
        self.field = field
        self.spw = spw
        self.antenna = antenna
        self.intent = intent

    @property
    def antenna(self) -> str:
        """Return the antennas to which the calibrations apply."""
        return self._antenna

    @antenna.setter
    def antenna(self, value: int | str | None) -> None:
        """
        Set the antennas to which the calibrations apply to given value.

        Args:
            value: Antenna ID (integer) or a string of comma-separated antenna
                IDs to which the calibrations apply. If None, this is set to an
                empty string. Contiguous ID ranges are represented as a CASA
                range, e.g. 1~5.
        """
        if value is None:
            value = ''
        self._antenna = utils.find_ranges(str(value))

    @property
    def field(self):
        """Return the field(s) to which the calibrations apply."""
        return self._field

    @field.setter
    def field(self, value: str | None) -> None:
        """
        Set the field(s) to which the calibrations apply to given value.

        Args:
            value: String of comma-separated fields to which the calibrations
                apply. If None, this is set to an empty string.
        """
        if value is None:
            value = ''
        self._field = str(value)

    @property
    def intent(self) -> str:
        """Return the observing intent(s) to which the calibrations apply."""
        return self._intent

    @intent.setter
    def intent(self, value: str | None) -> None:
        """
        Set the observing intent(s) to which the calibrations apply to given
        value.

        Args:
            value: String of comma-separated intents to which the calibrations
                apply. If None, this is set to an empty string.
        """
        if value is None:
            value = ''
        self._intent = str(value)

    @property
    def spw(self) -> str:
        """Return the spectral window(s) to which the calibrations apply."""
        return self._spw

    @spw.setter
    def spw(self, value: int | str | None) -> None:
        """
        Set the spectral window(s) to which the calibrations apply.

        Args:
            value: Spectral window ID (integer) or a string of comma-separated
            spectral window IDs to which the calibrations apply. If None, this
            is set to an empty string. Contiguous ID ranges are represented as a
            CASA range, e.g. 1~5.
        """
        if value is None:
            value = ''
        self._spw = utils.find_ranges(str(value))

    @property
    def vis(self) -> str:
        """Return the name of the measurement set to which the calibrations apply."""
        return self._vis

    @vis.setter
    def vis(self, value: str | None = None) -> None:
        """
        Set the name of the measurement set to which the calibrations apply.

        Args:
            value: Name of the measurement set to which the calibrations apply.
        """
        self._vis = str(value)

    def __repr__(self) -> str:
        return ('CalTo(vis=\'%s\', field=\'%s\', spw=\'%s\', antenna=\'%s\','
                'intent=\'%s\')' % (self.vis, self.field, self.spw, self.antenna,
                                    self.intent))


class CalFrom:
    """
    CalFrom represents a calibration table and the CASA arguments that should
    be used when applying that calibration table.

    Attributes:
        CALTYPES: an enumeration of calibration table types identified by this code.
        CALTYPE_TO_VISCAL: mapping of calibration type to caltable identifier as
            store in the table header.
        VISCAL: mapping of calibration table header information to a description
            of that table type.
    """
    CALTYPES = {
        'unknown': 0,
        'gaincal': 1,
        'bandpass': 2,
        'tsys': 3,
        'wvr': 4,
        'polarization': 5,
        'antpos': 6,
        'gc': 7,
        'opac': 8,
        'rq': 9,
        'swpow': 10,
        'finalcal': 11,
        'uvcont': 12,
        'amp': 13,
        'ps': 14,
        'otfraster': 15,
        'tecim': 16,
        'kcross': 17,
        'otf': 18,
    }

    CALTYPE_TO_VISCAL = {
        'gaincal': ('G JONES', 'GSPLINE', 'T JONES'),
        'bandpass': ('B JONES', 'BPOLY'),
        'tsys': ('B TSYS',),
        'antpos': ('KANTPOS JONES',),
        'uvcont': ('A MUELLER',),
        # 'amp': ('G JONES',),
        'ps': ('SDSKY_PS',),
        'otfraster': ('SDSKY_RASTER',),
        'otf': ('SDSKY_OTF',),
    }

    VISCAL = {
        'P JONES': 'P Jones (parallactic angle phase)',
        'T JONES': 'T Jones (polarization-independent troposphere)',
        'TF JONES': 'Tf Jones (frequency-dependent atmospheric complex gain)',
        'G JONES': 'G Jones (electronic Gain)',
        'B JONES': 'B Jones (bandpass)',
        'DGEN JONES': 'Dgen Jones (instrumental polarization)',
        'DFGEN JONES': 'Dfgen Jones (frequency-dependent instrumental polarization)',
        'D JONES': 'D Jones (instrumental polarization)',
        'DF JONES': 'Df Jones (frequency-dependent instrumental polarization)',
        'J JONES': 'J Jones (generic polarized gain)',
        'M MUELLER': 'M Mueller (baseline-based)',
        'MF MUELLER': 'Mf Mueller (closure bandpass)',
        'TOPAC': 'TOpac (Opacity corrections in amplitude)',
        'TFOPAC': 'TfOpac (frequency-dependent opacity)',
        'X MUELLER': 'X Mueller (baseline-based)',
        'X JONES': 'X Jones (antenna-based)',
        'XF JONES': 'Xf Jones (antenna-based)',
        'GLINXPH JONES': 'GlinXph Jones (X-Y phase)',
        'B TSYS': 'B TSYS (freq-dep Tsys)',
        'BPOLY': 'B Jones Poly (bandpass)',
        'GSPLINE': 'G Jones SPLINE (elec. gain)',
        'KANTPOS JONES': 'KAntPos Jones (antenna position errors)',
        'A MUELLER': 'A Mueller (baseline-based)',
    }

    # Hundreds of thousands of CalFroms can be created and stored in a context.
    # To save memory, CalFrom uses a Flyweight pattern, caching objects in
    # _CalFromPool and returning a shared immutable instance for CalFroms
    # constructed with the same arguments.
    _CalFromPool = weakref.WeakValueDictionary()

    @staticmethod
    def _calc_hash(gaintable: str, gainfield: str, interp: str, spwmap: tuple, calwt: bool) -> int:
        """
        Generate a hash code unique to the given arguments.

        Args:
            gaintable: Filename of calibration table.
            gainfield: Field(s) to select from calibration table to use.
            interp: Value to use for interp when applying these calibrations.
            spwmap: Value to use for spwmap when applying these calibrations.
            calwt: Value to use for calwt when applying these calibrations.

        Returns:
            Integer representing hash code for given arguments.
        """
        result = 17
        result = 37 * result + hash(gaintable)
        result = 37 * result + hash(gainfield)
        result = 37 * result + hash(interp)
        result = 37 * result + hash(spwmap)
        result = 37 * result + hash(calwt)
        return result

    def __new__(cls, gaintable: str | None = None, gainfield: str = '', interp: str = 'linear,linear',
                spwmap: list | tuple | None = None, caltype: str = 'unknown', calwt: bool = True) -> CalFrom:
        """
        Return a new instance of the CalFrom class.

        This override is to implement the Flyweight Pattern for the CalFrom
        class, to save memory given that hundreds of the same CalFrom objects
        could be created and stored in the context.

        Upon creating a new instance of CalFrom, the combination of input
        arguments are first hashed. If this is the first occurence of this hash,
        then the corresponding CalFrom object is created and a reference to this
        object is stored in the module-level _CalFromPool, as well as returned.
        If the hash of the input arguments already exists in the _CalFromPool,
        then a reference to the corresponding (previously created) CalFrom is
        returned instead.

        In this implementation, the entire state of the CalFrom object is
        immutable, and any required modification to a CalFrom should be achieved
        through creating a new CalFrom.

        Args:
            gaintable: Filename of calibration table.
            gainfield: Field(s) to select from calibration table to use.
            interp: Value to use for interp when applying these calibrations.
            spwmap: Value to use for spwmap when applying these calibrations.
            caltype: String declaring type of calibration table, e.g. 'tsys'.
            calwt: Value to use for calwt when applying these calibrations.

        Returns:
            A new instance of the CalFrom class.

        Raises:
            ValueError if gaintable is None, gainfield is not a string,
            interp is not a string, or spwmap is not a list, tuple, or None.
        """
        if spwmap is None:
            spwmap = []

        if gaintable is None:
            raise ValueError('gaintable must be specified. Got None')

        if not isinstance(gainfield, str):
            raise ValueError('gainfield must be a string. Got %s' % str(gainfield))

        if not isinstance(interp, str):
            raise ValueError('interp must be a string. Got %s' % str(interp))

        if isinstance(spwmap, tuple):
            spwmap = [spw for spw in spwmap]

        if not isinstance(spwmap, list):
            raise ValueError('spwmap must be a list. Got %s' % str(spwmap))
        # Flyweight instances should be immutable, so convert spwmap to a
        # tuple. This also makes spwmap hashable for our hash function.
        spwmap = tuple([o for o in spwmap])

        caltype = caltype.lower()
        assert caltype in CalFrom.CALTYPES

        arg_hash = CalFrom._calc_hash(gaintable, gainfield, interp, spwmap,
                                      calwt)

        obj = CalFrom._CalFromPool.get(arg_hash, None)
        if not obj:
            LOG.trace('Creating new CalFrom(gaintable=\'%s\', '
                      'gainfield=\'%s\', interp=\'%s\', spwmap=%s, '
                      'caltype=\'%s\', calwt=%s)' %
                      (gaintable, gainfield, interp, spwmap, caltype, calwt))
            obj = object.__new__(cls)
            obj.__gaintable = gaintable
            obj.__gainfield = gainfield
            obj.__interp = interp
            obj.__spwmap = spwmap
            obj.__caltype = caltype
            obj.__calwt = calwt

            LOG.debug('Adding new CalFrom to pool: %s' % obj)
            CalFrom._CalFromPool[arg_hash] = obj
            LOG.trace('New pool contents: %s' % list(CalFrom._CalFromPool.items()))
        else:
            LOG.trace('Reusing existing CalFrom(gaintable=\'%s\', '
                      'gainfield=\'%s\', interp=\'%s\', spwmap=\'%s\', '
                      'caltype=\'%s\', calwt=%s)' %
                      (gaintable, gainfield, interp, spwmap, caltype, calwt))

        return obj

    __slots__ = ('__caltype', '__calwt', '__gainfield', '__gaintable',
                 '__interp', '__spwmap', '__weakref__')

    def __getstate__(self) -> tuple[str, bool, str, str, str, tuple]:
        """Define what to pickle as a class instance."""
        return (self.__caltype, self.__calwt, self.__gainfield,
                self.__gaintable, self.__interp, self.__spwmap)

    def __setstate__(self, state: tuple[str, bool, str, str, str, tuple]):
        """Define how to unpickle a class instance."""
        # a misguided attempt to clear stale CalFroms when loading from a
        # pickle. I don't think this should be done here.
        #         # prevent exception with pickle format #1 by calling hash on properties
        #         # rather than the object
        #         (_, calwt, gainfield, gaintable, interp, spwmap) = state
        #         old_hash = CalFrom._calc_hash(gaintable, gainfield, interp, spwmap, calwt)
        #         if old_hash in CalFrom._CalFromPool:
        #             del CalFrom._CalFromPool[old_hash]

        (self.__caltype, self.__calwt, self.__gainfield, self.__gaintable,
         self.__interp, self.__spwmap) = state

    def __getnewargs__(self) -> tuple[str, str, str, tuple, str, bool]:
        """Define the tuple of input arguments to pass to __new__ during unpickling."""
        return (self.gaintable, self.gainfield, self.interp, self.spwmap,
                self.caltype, self.calwt)

    def __init__(self, *args, **kw) -> None:
        """Initialize a CalFrom instance."""
        pass

    @property
    def caltype(self) -> str:
        """Return the type of calibration table."""
        return self.__caltype

    @property
    def calwt(self) -> bool:
        """Return the value to use for calwt when applying these calibrations."""
        return self.__calwt

    @property
    def gainfield(self) -> str:
        """Return which field(s) in the calibration table to apply."""
        return self.__gainfield

    @property
    def gaintable(self) -> str:
        """Return the filename of the calibration table."""
        return self.__gaintable

    @staticmethod
    def get_caltype_for_viscal(viscal: str) -> str:
        """Return the calibration table type for given VISCAL identifier.

        VISCAL identifiers are the caltable identifier as stored in the table
        header.

        Args:
            viscal: VISCAL table identifier to convert to calibration table type.

        Returns:
            Type of calibration table.
        """
        s = viscal.upper()
        for caltype, viscals in CalFrom.CALTYPE_TO_VISCAL.items():
            if s in viscals:
                return caltype
        return 'unknown'

    @property
    def interp(self) -> str:
        """Value to use for interp when applying these calibrations."""
        return self.__interp

    @property
    def spwmap(self) -> tuple:
        """Value to use for spwmap when applying these calibrations."""
        return self.__spwmap

    def __hash__(self) -> int:
        return CalFrom._calc_hash(self.gaintable, self.gainfield, self.interp,
                                  self.spwmap, self.calwt)

    def __repr__(self) -> str:
        return ('CalFrom(\'%s\', gainfield=\'%s\', interp=\'%s\', spwmap=%s, '
                'caltype=\'%s\', calwt=%s)' %
                (self.gaintable, self.gainfield, self.interp, self.spwmap,
                 self.caltype, self.calwt))


class CalToIdAdapter:
    """
    CalToIdAdapter is an adapter class for CalTo that return some of its
    attributes as lists of IDs/names, instead of as the CASA-style string argument.
    """
    def __init__(self, context: launcher.Context, calto: CalTo) -> None:
        """Initialize a CalToIdAdapter instance."""
        self._context = context
        self._calto = calto

    @property
    def antenna(self) -> list[int]:
        """Return IDs of antennas to which the calibrations apply as a list of integers."""
        return [a.id for a in self.ms.get_antenna(self._calto.antenna)]

    @property
    def field(self) -> list[int] | list[str]:
        """Return fields to which the calibrations apply as a list of names or integer IDs."""
        fields = [f for f in self.ms.get_fields(task_arg=self._calto.field)]
        # if the field names are unique, we can return field names. Otherwise,
        # we fall back to field IDs.
        all_field_names = [f.name for f in self.ms.get_fields()]
        ### Activate the following line for NRO ###
        #         return [f.id for f in fields]
        if len(set(all_field_names)) == len(all_field_names):
            return [f.name for f in fields]
        else:
            return [f.id for f in fields]

    @property
    def intent(self) -> str:
        """Return the intents to which the calibrations apply."""
        return self._calto.intent

    def get_field_intents(self, field_id: int | str, spw_id: int | str) -> set[str]:
        """Return set of intents that are common to CalTo, given field(s), and
        given spectral window(s)."""
        field = self._get_field(field_id)
        field_intents = field.intents

        spw = self._get_spw(spw_id)
        spw_intents = spw.intents

        user_intents = frozenset(self._calto.intent.split(','))
        if self._calto.intent == '':
            user_intents = field.intents

        return user_intents & field_intents & spw_intents

    @property
    def ms(self) -> MeasurementSet:
        """Return the MeasurementSet object (from context) that the CalTo applies to."""
        return self._context.observing_run.get_ms(self._calto.vis)

    @property
    def spw(self) -> list[int | str]:
        """Return spectral windows IDs to which the calibrations apply."""
        return [spw.id for spw in self.ms.get_spectral_windows(
            self._calto.spw, science_windows_only=False)]

    def _get_field(self, field_id: int | str) -> Field:
        """Return the Field object (from context/MS) for given field ID/name."""
        fields = self.ms.get_fields(task_arg=field_id)
        if len(fields) != 1:
            msg = 'Illegal field ID \'%s\' for vis \'%s\'' % (field_id,
                                                              self._calto.vis)
            LOG.error(msg)
            raise ValueError(msg)
        return fields[0]

    def _get_spw(self, spw_id: int | str) -> SpectralWindow:
        """Return the SpectralWindow object (from context/MS) for given ID."""
        spws = self.ms.get_spectral_windows(spw_id,
                                            science_windows_only=False)
        if len(spws) != 1:
            msg = 'Illegal spw ID \'%s\' for vis \'%s\'' % (spw_id,
                                                            self._calto.vis)
            LOG.error(msg)
            raise ValueError(msg)
        return spws[0]

    def __repr__(self) -> str:
        return ('CalToIdAdapter(ms=\'%s\', field=\'%s\', intent=\'%s\', '
                'spw=%s, antenna=%s)' % (self.ms.name, self.field,
                                         self.intent, self.spw, self.antenna))


def unit(x):
    return x


def contiguous_sequences(l: Iterable) -> Generator[list[int], None, None]:
    """
    Generate contiguous sequences of numbers from a list.

    This function takes a list of integers (or values that can be converted to
    integers), sorts them, and yields contiguous sequences of these integers.

    A contiguous sequence is defined as a sequence of numbers where each number
    is exactly one greater than the previous number.

    Args:
        l: A list of integers or values that can be converted to integers.

    Yields:
        List containing sequence of continguous integers.

    Example:
    >>> list(contiguous_sequences([3, 1, 4, 2, 6, 5, 8]))
    [[1, 2, 3, 4, 5, 6], [8]]
    """
    s = sorted([int(d) for d in l])

    for _, g in itertools.groupby(enumerate(s), lambda i_x: i_x[0] - i_x[1]):
        rng = list(map(operator.itemgetter(1), g))
        yield rng


# intervals are not inclusive of the upper bound, hence the +1 on the right bound
sequence_to_range = lambda l: (l[0], l[-1] + 1)


def sequence_to_casa_range(seq):
    def as_casa_range(seq):
        size = len(seq)
        if size == 0:
            return ''
        elif size == 1:
            return '{}'.format(seq[0])
        else:
            return '{}~{}'.format(seq[0], seq[-1])

    return (as_casa_range(seq) for seq in contiguous_sequences(seq))


class CalToIntervalAdapter:
    def __init__(self, context, calto):
        self._context = context
        self._calto = calto

        ms = context.observing_run.get_ms(calto.vis)
        self.ms = ms

        antenna_ids = (a.id for a in ms.get_antenna(calto.antenna))
        self.antenna = [sequence_to_range(seq) for seq in contiguous_sequences(antenna_ids)]

        field_ids = (f.id for f in ms.get_fields(task_arg=calto.field))
        self.field = [sequence_to_range(seq) for seq in contiguous_sequences(field_ids)]

        spw_ids = (spw.id for spw in ms.get_spectral_windows(self._calto.spw, science_windows_only=False))
        self.spw = [sequence_to_range(seq) for seq in contiguous_sequences(spw_ids)]

        id_to_intent = get_intent_id_map(ms)
        intent_to_id = {v: i for i, v in id_to_intent.items()}

        if self._calto.intent == '':
            self.intent = [(0, len(intent_to_id))]
        else:
            str_intents = self._calto.intent.split(',')
            # the conditional check for intent is required as task parameters may
            # specify an intent that is not in the MS, such as CHECK.
            intent_ids = (intent_to_id[intent] for intent in str_intents
                          if intent in intent_to_id)
            self.intent = [sequence_to_range(seq) for seq in contiguous_sequences(intent_ids)]

    def __str__(self) -> str:
        return ('CalToIntervalAdapter(ms={!r}, field={!r}, intent={!r}, spw={!r}, antenna={!r})'.format(
            os.path.basename(self._calto.vis), self.field, self.intent, self.spw, self.antenna))

    def __repr__(self) -> str:
        return 'CalToIntervalAdapter({!s}, {!s})'.format(self._context, self._calto)


def create_data_reducer(join: Callable) -> Callable:
    """
    Return a function that creates a new TimestampedData object containing the
    result of executing the given operation on two TimestampedData objects.

    The use case for this function is actually quite simple: perform an
    operation on two TimestampedData objects (add, subtract, etc.) and put the
    result in a new TimestampedData object.

    The resulting TimestampedData object has a creation time equal to that of
    the oldest input object.

    Args:
        join: The function to call on the two input objects.

    Returns:
        Function that creates a TimestampedData object containing result of
        executing given join operation on two TimestampedData objects, with
        creation time equal to that of the oldest input object.
    """
    def m(td1: TimestampedData, td2: TimestampedData, join: Callable = join) -> TimestampedData:
        oldest = min(td1, td2)
        newest = max(td1, td2)
        return TimestampedData(oldest.time, join(oldest, newest))

    return m


def merge_lists(join_fn=operator.add):
    """
    Return a function that merge two lists by calling the input operation
    on the two input arguments.

    :param join_fn:
    :return:
    """

    def m(oldest, newest):
        return join_fn(oldest.data, newest.data)

    return m


def merge_intervaltrees(on_intersect):
    """
    Return a function that merges two IntervalTrees, executing a function
    on the intersecting Interval ranges in the resulting merged IntervalTree.

    :param on_intersect: the function to call on overlapping Intervals
    :return: function
    """

    def m(oldest, newest):
        union = oldest.data | newest.data
        union.split_overlaps()
        union.merge_equals(data_reducer=on_intersect)
        return union

    return m


def ranges(lst):
    pos = (j - i for i, j in enumerate(lst))
    t = 0
    for i, els in itertools.groupby(pos):
        l = len(list(els))
        el = lst[t]
        t += l
        yield (el, el + l)


def safe_join(vals, separator=','):
    return separator.join((str(o) for o in vals))


def merge_contiguous_intervals(tree: intervaltree.IntervalTree) -> intervaltree.IntervalTree:
    """
    Merge contiguous Intervals with the same value into one Interval.

    Args:
        tree: An IntervalTree.

    Returns:
        A new IntervalTree with merged Intervals.
    """
    merged_tree = intervaltree.IntervalTree()

    # sort the tree by the list values. This is a prerequisite of using the
    # itertools.groupby function
    data = sorted(tree, key=tsd_accessor)

    # create groups of Intervals that have the same list values. These are the
    # Intervals we can merge.
    for l, g in itertools.groupby(data, tsd_accessor):
        # create a tree for these Intervals with the same list values
        candidate_tree = intervaltree.IntervalTree(g)
        # expand the Interval ranges to a list of integers (e.g. 1,3,6,7,8),
        # then find the contiguous ranges
        sequence = list(itertools.chain(*[range(i.begin, i.end) for i in sorted(candidate_tree)]))
        for begin, end in ranges(sequence):
            vals = sorted(candidate_tree[begin:end], key=tsd_accessor)
            # create a new Interval for the contiguous range but using an
            # existing value, thus reusing the timestamp
            merged_tree.add(intervaltree.Interval(begin, end, vals[0].data))

    return merged_tree


# function to access the value of a TimestampedData inside an Interval
tsd_accessor = operator.attrgetter('data.data')


def defrag_interval_tree(tree):
    """
    Condense an IntervalTree by consolidating fragmented entries with the same
    value into contiguous Intervals.

    :param tree:
    :return:
    """
    # if the intervals in this tree do not contain IntervalTrees, we're at the final
    # branch - the branch with the list of CalApplications. The intervals in this
    # branch can be merged
    leaf_values = [tsd_accessor(interval) for interval in tree]
    if not all((isinstance(v, intervaltree.IntervalTree) for v in leaf_values)):
        return merge_contiguous_intervals(tree)

    # otherwise call recursively
    merged_tree = intervaltree.IntervalTree()
    for interval in tree:
        new_leaf = intervaltree.Interval(interval.begin,
                                         interval.end,
                                         defrag_interval_tree(tsd_accessor(interval)))
        merged_tree.add(new_leaf)

    return merged_tree


# this chain of functions defines how to add overlapping Intervals when adding
# IntervalTrees
intent_add: Callable = create_data_reducer(join=merge_lists(join_fn=operator.add))
field_add: Callable = create_data_reducer(join=merge_intervaltrees(intent_add))
spw_add: Callable = create_data_reducer(join=merge_intervaltrees(field_add))
ant_add: Callable = create_data_reducer(join=merge_intervaltrees(spw_add))

# this chain of functions defines how to subtract overlapping Intervals when
# subtracting IntervalTrees
intent_sub: Callable = create_data_reducer(join=merge_lists(join_fn=lambda x, y: [item for item in x if item not in y]))
field_sub: Callable = create_data_reducer(join=merge_intervaltrees(intent_sub))
spw_sub: Callable = create_data_reducer(join=merge_intervaltrees(field_sub))
ant_sub: Callable = create_data_reducer(join=merge_intervaltrees(spw_sub))


def interval_to_set(interval: intervaltree.Interval) -> set[int]:
    """
    Get all the indices covered by an Interval.

    Args:
        interval: Interval to retrieve indices for.

    Returns:
        Set of indices covered by given Interval.
    """
    return set(range(interval.begin, interval.end))


def get_id_to_intent_fn(id_to_intent: dict[str, dict[int, str]]) -> Callable:
    """
    Return a function that can convert intent IDs to a string intent.

    Takes a dict of dicts, first key mapping measurement set name and second
    key mapping numeric intent ID to string intent for that MS, e.g.

    {'a.ms': {0: 'PHASE', 1: 'BANDPASS'}

    Args:
        id_to_intent: Dictionary mapping vis to a dictionary of intent ID: string intent.

    Returns:
        Function that converts given intent IDs for given MS to set of intents.
    """
    def f(vis, intent_ids):
        assert vis in id_to_intent

        mapping = id_to_intent[vis]

        # if the intent range spans all intents for this measurement set,
        # transform it back to '' to indicate all intents
        if all((i in intent_ids for i in mapping)):
            return set('')

        return set((mapping[i] for i in intent_ids))

    return f


def get_id_to_field_fn(ms_to_id_to_field):
    """
    Return a function that can convert field IDs to a field name.

    Takes a dict of dicts, first key mapping measurement set name and second
    key mapping numeric field ID to field name, eg.

    {'a.ms': {0: 'field 1', 1: 'field 2'}

    :param ms_to_id_to_field: dict of vis : field ID : field name
    :return: set of field names (or field IDs if names are not unique)
    """
    id_to_identifier = {}
    for ms_name, id_to_field in ms_to_id_to_field.items():
        counter = collections.Counter()
        counter.update(list(id_to_field.values()))

        # construct an id:name mapping using the ID for non-unique field names
        d = {field_id: field_name if counter[field_name] == 1 else field_id
             for field_id, field_name in id_to_field.items()}
        id_to_identifier[ms_name] = d

    def f(vis, field_ids):
        assert vis in id_to_identifier

        field_id_to_field_name = id_to_identifier[vis]

        # if the field range spans all fields for this measurement set,
        # transform it back to '' to indicate all fields
        if all(i in field_ids for i in field_id_to_field_name):
            return set('')

        return set(field_id_to_field_name[i] for i in field_ids)

    return f


def expand_interval(interval, calto_args, calto_fn):
    """
    Convert an Interval into the equivalent list of (CalTo, [CalFrom..])
    2-tuples.

    This function is the partner function to expand_intervaltree. See the
    documention for expand_intervaltree for more details on the argument
    format for this function.

    :param interval: the Interval to convert
    :param calto_args: the list of (argument name, conversion function) 2-tuples
     for the remaining dimensions
    :param calto_fn: the partial CalToArgs application
    :return:  a list of (CalTo, [CalFrom..]) tuples
    """
    data = tsd_accessor(interval)
    numeric_ids = interval_to_set(interval)

    arg_name, conversion_fn = calto_args[0]
    processed = conversion_fn(numeric_ids)
    kwargs = {arg_name: processed}

    calto_fn = functools.partial(calto_fn, **kwargs)

    if isinstance(data, intervaltree.IntervalTree):
        return expand_intervaltree(data, calto_args[1:], calto_fn)
    else:
        # the return type is an iterable of 2-tuples
        return ((calto_fn(), data),)


def expand_intervaltree(tree, convert_fns, calto_fn):
    """
    Convert an IntervalTree into the equivalent list of (CalTo, [CalFrom..])
    2-tuples.

    The second argument for this function is a list of 2-tuples of (CalToArgs
    constructor argument for this dimension, value conversion function for
    this dimension). The conversion function takes in a set of integer indexes
    and converts it to a suitable (probably more human-readable value) for that
    dimension, e.g. a conversion from field ID to field name. So, for a
    dimension that supplies the 'antenna' argument to CalToArgs and should
    prefix 'DV' to each antenna index, the tuple for that dimension could be
    ('antenna', lambda id: {'DV%s' % i for i in field_ids}).

    The third argument is the partially-applied CalToArgs constructor. A
    CalToArgs needs a number of arguments (vis, field, spw, etc.), each of
    which corresponds to a dimension of the IntervalTree and which must be
    supplied at CalToArgs creation time. To achieve this while iterating
    through the dimensions (when the constructor arguments are not fully
    known), object creation is delayed by performing just a partial
    application, adding the keyword for the current dimension to the partial
    application. At the final leaf node, when all constructor arguments have
    been partially applied, we can call the partial function and get the
    CalToArgs.

    :param tree: the IntervalTree to convert
    :param convert_fns: the list of (argument name, conversion function) 2-tuples
     for the remaining dimensions
    :param calto_fn: the partial CalToArgs application
    :return: a list of (CalTo, [CalFrom..]) tuples
    """
    return (x
            for interval in tree
            for x in expand_interval(interval, convert_fns, calto_fn))


def expand_calstate_to_calapps(calstate: IntervalCalState) -> list[tuple[CalTo, list[CalFrom]]]:
    """
    Convert an IntervalCalState into a list of (CalTo, [CalFrom..]) tuples.

    Args:
        calstate: The IntervalCalState to convert.

    Returns:
        A list of 2-tuples, first element a Calto, second element a list
        of CalFroms.
    """
    # get functions to map from integer IDs to field and intent for this MS
    id_to_field_fn = get_id_to_field_fn(calstate.id_to_field)
    id_to_intent_fn = get_id_to_intent_fn(calstate.id_to_intent)

    calapps: list[tuple[CalTo, list[CalFrom]]] = []

    for vis in calstate:
        # Set the vis argument for the CalToArgs constructor through partial
        # application. The subsequent calls will set the other arguments for
        # CalToArgs (field, intent, spw, etc.)
        caltoarg_fn = functools.partial(CalToArgs, vis={vis})

        # partially apply vis so that callees can call id-to-X functions
        # directly rather than having to push the vis arg through the layers
        intent_fn = functools.partial(id_to_intent_fn, vis)
        field_fn = functools.partial(id_to_field_fn, vis)

        # maps dimension order to the CalToArgs argument and value processing
        # function for that dimension. We have to process values at this point
        # while vis is still atomic, as once it's a set for the CalTo (as it
        # justly needs to be to handle sessions) we can't determine vis to
        # perform the mapping.
        caltoarg_dimension = (('antenna', unit),
                              ('spw', unit),
                              ('field', field_fn),
                              ('intent', intent_fn))

        vis_tree = calstate[vis]
        vis_calapps = expand_intervaltree(vis_tree, caltoarg_dimension, caltoarg_fn)
        calapps.extend(vis_calapps)

    return calapps


def consolidate_calibrations(all_my_calapps):
    """
    Consolidate a list of (CalTo, [CalFrom..]) 2-tuples into a smaller set of
    equivalent applications by consolidating their data selection arguments.

    This function works by merging the data selections of CalTo objects that
    have the same calibration application, as determined by the values and
    data selection present in the CalFroms.

    :param calapps: an iterable of (CalTo, [CalFrom..]) 2-tuples
    :return: a list of (CalTo, [CalFrom..]) tuples
    """
    # When faced with a large number of EBs, trying to merge calibrations
    # across all MSes results in a huge number of iterations - most of them
    # pointless as the caltables only apply to one MS. So, partition the
    # calapps, grouping them by MS, and merge within these partitions and not
    # across them.
    vis_to_calapps = collections.defaultdict(list)
    for calto, calfroms in all_my_calapps:
        if len(calto.vis) > 1:
            msg = 'Cannot handle calibrations that apply to multiple MSes'
            raise ValueError(msg)
        vis = tuple(calto.vis)[0]
        vis_to_calapps[vis].append((calto, calfroms))

    all_accepted = {}
    for vis, calapps_for_vis in vis_to_calapps.items():
        LOG.info('Consolidating calibrations for {}'.format(os.path.basename(vis)))

        # dict mapping an object hash to the object itself:
        #     hash([CalFrom, ...]): [CalFrom, ...]
        hash_to_calfroms = {}
        # dict mapping from object hash to corresponding list of CalToArgs
        hash_to_calto_args = collections.defaultdict(list)

        # create our maps of hashes, which we need to test for overlapping data
        # selections
        for calto_args, calfroms in calapps_for_vis:
            if not calfroms:
                continue

            # create a tuple, as lists are not hashable
            hashable_calfroms = tuple(hash(cf) for cf in calfroms)
            hash_to_calto_args[hashable_calfroms].append(calto_args)

            if hashable_calfroms not in hash_to_calfroms:
                hash_to_calfroms[hashable_calfroms] = calfroms

        # dict that maps holds accepted data selections and their CalFroms
        accepted = {}
        for hashable_calfroms, calto_args in hash_to_calto_args.items():
            # assemble the other data selections (the other CalToArgs) which we
            # will use to search for conflicting data selections
            other_data_selections = []
            for v in [v for k, v in hash_to_calto_args.items() if k != hashable_calfroms]:
                other_data_selections.extend(v)

            for to_merge in calto_args:
                if hashable_calfroms not in accepted:
                    # first time round for this calibration application, therefore it can always be added
                    # as there will be nothing to merge
                    accepted[hashable_calfroms] = [(copy.deepcopy(to_merge), hash_to_calfroms[hashable_calfroms])]
                    continue

                for idx, (existing_calto, calfroms) in enumerate(accepted[hashable_calfroms]):
                    if not calfroms:
                        continue

                    proposed_calto = CalToArgs(*copy.deepcopy(existing_calto))

                    for proposed_values, to_merge_values in zip(proposed_calto, to_merge):
                        proposed_values.update(to_merge_values)

                    # if the merged data selection does not conflict with any of
                    # the explicitly registered data selections that require a
                    # different calibration application, then it is safe to add
                    # the merged data selection and discard the unmerged data
                    # selection
                    if not any((data_selection_contains(proposed_calto, other) for other in other_data_selections)):
                        if LOG.isEnabledFor(logging.TRACE):
                            LOG.trace('No conflicting data selection detected')
                            LOG.trace('Accepting merged data selection: {!s}'.format(proposed_calto))
                            LOG.trace('Discarding unmerged data selection: {!s}'.format(to_merge))
                        accepted[hashable_calfroms][idx] = (proposed_calto, hash_to_calfroms[hashable_calfroms])
                        break

                else:
                    # we get here if all of the proposed merged data selections
                    # conflict with the data selection in hand. In this case, it
                    # should be added as it stands, completely unaltered.
                    if LOG.isEnabledFor(logging.TRACE):
                        LOG.trace('Merged data selection conflicts with other registrations')
                        LOG.trace('Abandoning proposed data selection: {!s}'.format(proposed_calto))
                        LOG.trace('Appending new unmerged data selection: {!s}'.format(to_merge))
                    unmergeable = (to_merge, hash_to_calfroms[hashable_calfroms])
                    accepted[hashable_calfroms].append(unmergeable)

            all_accepted.update(accepted)

    # dict values are lists, which we need to flatten into a single list
    result = []
    for l in all_accepted.values():
        result.extend(l)
    return result


def data_selection_contains(proposed: CalToArgs, calto_args: CalToArgs) -> bool:
    """
    Return True if one data selection is contained within another.

    Args:
        proposed: Data selection 1 as CalToArgs tuple.
        calto_args: Data selection 2 as CalToArgs tuple.

    Returns:
        True if data selection 2 is contained within data selection 1.
    """
    return all([not proposed.vis.isdisjoint(calto_args.vis),
                not proposed.antenna.isdisjoint(calto_args.antenna),
                not proposed.field.isdisjoint(calto_args.field),
                not proposed.spw.isdisjoint(calto_args.spw),
                not proposed.intent.isdisjoint(calto_args.intent)])


def expand_calstate(calstate: IntervalCalState) -> list[tuple[CalToArgs, list[CalFrom]]]:
    """
    Convert an IntervalCalState into the equivalent consolidated list of
    (CalToArgs, [CalFrom..]) 2-tuples.

    This function is the top-level entry point for converting a calibration
    state to 2-tuples. It consolidates data selections and converts numeric
    data selection IDs to friendly equivalents through downstream processing,

    Args:
        calstate: The IntervalCalState to convert.

    Returns:
        A list of (CalToArgs, [CalFrom..]) tuples.
    """
    # step 1: convert to [(CalTo, [CalFrom..]), ..]
    unmerged = expand_calstate_to_calapps(calstate)

    # step 2: consolidate entries with identical calibrations
    consolidated = consolidate_calibrations(unmerged)

    # step 3: take the list of (CalToArgs, [CalFrom]) tuples, taking any
    # CalToArgs whose vis property targets multiple MSes and dividing them
    # into n entries each targeting a single MS. This keeps the export data
    # format more readable as each entry targets a single measurement set.
    per_ms = [(CalToArgs({vis}, *cta[1:]), calfroms)
              for cta, calfroms in consolidated for vis in cta.vis]

    # step 4: convert integer ranges in data selection to friendlier CASA range
    # syntax, e.g.  [1,2,3,4,6,8] => ['1~4','6','8']
    casa_format = [(CalToArgs(vis=calto_args.vis,
                              antenna=sequence_to_casa_range(calto_args.antenna),
                              spw=sequence_to_casa_range(calto_args.spw),
                              field=calto_args.field,
                              intent=calto_args.intent), calfroms)
                   for calto_args, calfroms in per_ms]

    # step 5: convert each iterable argument to a comma-separated string
    return [(CalToArgs(*[safe_join(arg) for arg in calto_args]), calfroms)
            for calto_args, calfroms in casa_format]


def get_min_max(l, keyfunc=None):
    if keyfunc:
        l = list(map(keyfunc, l))
    # this function is used to specify Interval ranges, which are not
    # inclusive of the upper bound - hence the +1.
    return min(l), max(l) + 1


def create_interval_tree(a):
    """
    Create an IntervalTree containing a set of Intervals.

    The input argument used to create the Intervals is an iterable of
    3-tuples, each 3-tuple defined as:

    (interval start, interval end, function giving value for that interval).

    :param a: the iterable of argument tuples
    :return: IntervalTree
    """
    intervals = (intervaltree.Interval(begin, end, data_fn())
                 for begin, end, data_fn in a)
    return intervaltree.IntervalTree(intervals)


def create_interval_tree_nd(intervals, value_fn):
    """
    Create a multidimensional IntervalTree. Each Interval within the
    IntervalTree points to the next dimension, with the final Interval
    containing the value given by calling value_fn.

    :param intervals: a list of Interval lists, with range of the final
    (deepest) first, ending with the range of the root dimension
    :param value_fn: function that returns value for the final dimension
    :return: an IntervalTree
    """
    # wrapper to create TimestampedData objects with a fixed timestamp of now
    tsd_now = functools.partial(TimestampedData, datetime.datetime.now(datetime.timezone.utc))

    # Intervals have to point to the next dimension, so we must create the
    # dimensions in reverse order, starting with the deepest dimension.
    final_tree = create_interval_tree([(begin, end, lambda: tsd_now(value_fn()))
                                       for begin, end in intervals[0]])
    root = final_tree

    # the parent dimensions just link to their child dimensions, similar to a
    # linked list
    for current_dim_intervals in intervals[1:]:
        dim_args = [(begin, end, lambda: tsd_now(root))
                    for begin, end in current_dim_intervals]
        root = create_interval_tree(dim_args)

    return root


def create_interval_tree_for_ms(ms: MeasurementSet) -> intervaltree.IntervalTree:
    """
    Create a new IntervalTree fitted to the dimensions of a measurement set.

    This function creates a new IntervalTree with the size of the antenna,
    spw, field and intent dimensions fitted to envelop of the input measurement
    set.

    Args:
        ms: MeasurementSet to create new IntervalTree for.

    Returns:
        An IntervalTree fitted to the dimensions of given measurement set.
    """
    id_getter = operator.attrgetter('id')
    tree_intervals = [
        [(0, len(ms.intents))],
        [get_min_max(ms.fields, keyfunc=id_getter)],
        [get_min_max(ms.spectral_windows, keyfunc=id_getter)],
        [get_min_max(ms.antennas, keyfunc=id_getter)]
    ]

    return create_interval_tree_nd(tree_intervals, list)


def trim(tree, ranges):
    """
    Return an IntervalTree trimmed to the specified ranges.

    Ranges are specified as tuples of (begin, end).

    :param tree: the IntervalTree to trim
    :param ranges: a list of range tuples
    :return: the trimmed IntervalTree
    """
    insertions = set()

    for begin, end in ranges:
        # locate Intervals overlapping the range, not just those completely
        # contained within the range
        overlapping = tree.overlap(begin, end)

        # truncate the Intervals to the range boundaries
        truncated = {intervaltree.Interval(max(iv.begin, begin),
                                           min(iv.end, end),
                                           iv.data)
                     for iv in overlapping}
        insertions.update(truncated)

    return intervaltree.IntervalTree(insertions)


def trim_nd(tree, selection):
    """
    Return an IntervalTree with each dimension trimmed to the specified
    set of ranges.

    The data selection for each dimension is specified as a sequence of
    (begin, end) tuples; the data selection for the tree as a whole is a
    sequence of these dimension sequences. For example, the data selection

        [ [(1, 3)], [(0, 5), (7, 8)] ]

    would select 1-3 from the first dimension and 0-5, and 7 from the
    second dimension.

    :param tree: the IntervalTree to trim
    :param selection: the sequence of data selections for each dimension
    :return:
    """
    # print('tree={}\nselection={}'.format(tree, selection))
    root = trim(tree, selection[0])

    if len(selection) > 1:
        # TimestampedData objects are immutable namedtuples, so to change the
        # data they point to we must replace the whole Interval. These
        # replacement Intervals are identical to those they replace except for
        # the TimestampedData.data property, which is trimmed to the next set
        # of dimensions
        replacements = {
            intervaltree.Interval(iv.begin,
                                  iv.end,
                                  TimestampedData(iv.data.time,
                                                  trim_nd(tsd_accessor(iv), selection[1:])))
            for iv in root
        }
        # now remove the untrimmed Intervals and replace them with our trimmed
        # versions
        root.clear()
        root.update(replacements)

    return root


def get_intent_id_map(ms: MeasurementSet) -> dict[int, str]:
    """
    Get the mapping of intent ID to string intent for a measurement set.

    Args:
        ms: The measurement set to analyse.

    Returns:
        A dict of intent ID: intent.
    """
    # intents are sorted to ensure consistent ordering
    return dict(enumerate(sorted(ms.intents)))


class IntervalCalState:
    """
    IntervalCalState is a data structure used to map calibrations for all data
    registered with the pipeline.

    It is implemented as a multi-dimensional array indexed by data selection
    parameters (ms, spw, field, intent, antenna), with the end value being a
    list of CalFroms, representing the calibrations to be applied to that data
    selection.
    """

    def __init__(self):
        """Initialize an IntervalCalState object."""
        self.data = {}
        self.id_to_intent = {}
        self.id_to_field = {}
        self.shape = {}

    @staticmethod
    def from_calapplication(context, calto, calfroms):
        if not isinstance(calfroms, list):
            calfroms = [calfroms]

        adapted = CalToIntervalAdapter(context, calto)

        selection_intervals = [
            adapted.intent,
            adapted.field,
            adapted.spw,
            adapted.antenna
        ]
        selection = create_interval_tree_nd(selection_intervals, lambda: calfroms)

        calstate = IntervalCalState.create_from_context(context)
        ms = context.observing_run.get_ms(calto.vis)
        calstate.data[ms.name] = selection

        calstate.data[ms.name] = trim_to_valid_data_selection(calstate, ms.name)[ms.name]

        return calstate

    @staticmethod
    def create_from_context(context: launcher.Context) -> IntervalCalState:
        """
        Return a new IntervalCalState based on given Pipeline context.

        This method initialises a new IntervalCalState instance and then updates
        its key attributes by generating "ID to intent" and "ID to field"
        mapping dictionaries, generating interval trees with correct dimensions,
        and computing the shape, for all measurement sets that are registered in
        the given context.

        Args:
            context: The Pipeline context.

        Returns:
            IntervalCalState based on given Pipeline context.
        """
        if LOG.isEnabledFor(logging.TRACE):
            LOG.trace('Creating new CalLibrary from context')

        # holds a mapping of numeric intent ID to string intent for each ms.
        id_to_intent = {ms.name: get_intent_id_map(ms)
                        for ms in context.observing_run.measurement_sets}

        # holds a mapping of numeric ID to field name for each ms.
        id_to_field = {ms.name: {field.id: field.name for field in ms.fields}
                       for ms in context.observing_run.measurement_sets}

        calstate = IntervalCalState()
        calstate.id_to_intent.update(id_to_intent)
        calstate.id_to_field.update(id_to_field)

        interval_trees = {ms.name: create_interval_tree_for_ms(ms)
                          for ms in context.observing_run.measurement_sets}
        calstate.data.update(interval_trees)

        # the shape is never modified and hence can be shared between calstates
        for ms in context.observing_run.measurement_sets:
            calstate.shape[ms.name] = get_calstate_shape(ms)

        calstate.data = trim_to_valid_data_selection(calstate)

        return calstate

    def clear(self):
        for calstate in self.data.values():
            calstate.clear()
        # do NOT clear the id mapping dicts as without access to the context
        # we have no way to repopulate them.
        # self.id_to_intent.clear()
        # self.id_to_field.clear()

    def trimmed(self, context, calto):
        """
        Return a copy of this IntervalCalState trimmed to the specified CalTo data selection.
        :param calto:
        :param selection_intervals:
        :return:
        """
        # wrap the text-only CalTo in a CalToIntervalAdapter, which will parse
        # the CalTo properties and give us the appropriate subtable IDs to
        # iterate over
        adapted = CalToIntervalAdapter(context, calto)

        # get the data selection as numeric IDs
        selection_intervals = [
            adapted.antenna,
            adapted.spw,
            adapted.field,
            adapted.intent
        ]

        # get a copy of this calstate trimmed to the CalTo data selection
        vis = adapted.ms.name

        # if the data has not been registered with the CalLibrary, create a
        # new and empty calibration application and register it, thereby
        # creating all the IntervalTrees necessary for the MS.
        if vis not in self.data:
            ms = context.observing_run.get_ms(vis)
            calto = CalTo(vis=ms.name)
            to_add = IntervalCalState.from_calapplication(context, calto, [])
            self.__iadd__(to_add)

        copied = copy.deepcopy(self.data[vis])
        trimmed = trim_nd(copied, selection_intervals)

        calstate = IntervalCalState()
        calstate.data[vis] = trimmed
        calstate.id_to_intent[vis] = self.id_to_intent[vis]
        calstate.id_to_field[vis] = self.id_to_field[vis]
        calstate.shape = self.shape

        return calstate

    def get_caltable(self, caltypes=None) -> set[str]:
        """
        Get the names of all caltables registered with this CalState.

        If an optional caltypes argument is given, only caltables of the
        requested type will be returned.

        :param caltypes: Caltypes should be one or/a list of table
        types known in CalFrom.CALTYPES.

        :rtype: set of strings
        """
        if caltypes is None:
            caltypes = list(CalFrom.CALTYPES.keys())

        if isinstance(caltypes, str):
            caltypes = (caltypes,)

        for c in caltypes:
            assert c in CalFrom.CALTYPES

        return {calfrom.gaintable for calfroms in self.merged().values()
                for calfrom in calfroms
                if calfrom.caltype in caltypes}

    def merged(self, hide_empty=False):
        calapps = expand_calstate(self)

        if hide_empty:
            calapps = [ca for ca in calapps if len(ca[1]) > 0]

        # TODO dict is unnecessary. refactor all usages of this class to use
        # the tuple
        return dict(calapps)

    def export_to_casa_callibrary(self, ms, callibfile):
        calapps = (CalApplication(calto, calfroms)
                   for calto, calfroms in self.merged(hide_empty=True).items())
        append = False
        for calapp in calapps:
            casa_intents = utils.to_CASA_intent(ms, calapp.intent)
            applycaltocallib(callibfile, append=append, field=calapp.field, intent=casa_intents, spw=calapp.spw,
                             gaintable=calapp.gaintable, gainfield=calapp.gainfield, interp=calapp.interp,
                             spwmap=calapp.spwmap, calwt=calapp.calwt)
            append = True

    def as_applycal(self) -> str:
        """Return the CalState as a string representation of the corresponding applycal commands."""
        calapps = (CalApplication(calto, calfroms)
                   for calto, calfroms in self.merged(hide_empty=True).items())

        return '\n'.join([str(c) for c in calapps])

    def __str__(self) -> str:
        return self.as_applycal()

    def _combine(self, other: IntervalCalState, combine_fn: Callable) -> IntervalCalState:
        """
        Get the union of this object combined with another IntervalCalState,
        applying a function to any Intervals that overlap.

        Args:
            other: The other IntervalCalState.
            combine_fn: The combining function to apply to overlapping intervals.

        Returns:
            New IntervalCalState object representing union of this
            IntervalCalState and given ``other`` IntervalCalState.
        """
        calstate = IntervalCalState()

        # ensure that the other calstate is not considered equal to this
        # calstate, even if they the values they hold are identical. This step
        # is required so that all entries are added to in the union
        # (my_root | other_root) operation, and ensures that arithmetic like
        # 'calstate_x - calstate_x = 0' holds true.
        marker = uuid.uuid4()
        other_marked = set_calstate_marker(other, marker)

        # copy the ID mapping and shape data across.
        calstate.id_to_intent = self.id_to_intent
        calstate.id_to_field = self.id_to_field
        calstate.shape = self.shape

        for vis, my_root in self.data.items():
            if LOG.isEnabledFor(logging.TRACE):
                LOG.trace('Combining callibrary entries for {}'.format(os.path.basename(vis)))
            # adopt IntervalTrees present in just this object
            if vis not in other_marked.data:
                # TODO think: does this need to be a deep copy?
                calstate.data[vis] = copy.deepcopy(self.data[vis])
                continue

            # get the union of IntervalTrees for MSes present in both objects
            other_root = other_marked.data[vis]
            union = my_root | other_root
            union.split_overlaps()
            union.merge_equals(data_reducer=combine_fn)

            calstate.data[vis] = union

        calstate.data = trim_to_valid_data_selection(calstate)

        # Unmark the result calstate, thus eliminating any residual uuids
        unmarked = set_calstate_marker(calstate, None)

        return unmarked

    def __add__(self, other: IntervalCalState) -> IntervalCalState:
        """Defines how to add this IntervalCalState to given ``other`` IntervalCalState."""
        # Create new IntervalCalState by combining this IntervalCalState with
        # given "other" IntervalCalState, while applying the "antenna addition"
        # function chain to overlapping intervals.
        calstate = self._combine(other, ant_add)

        # also adopt IntervalTrees only present in the other object
        for vis, other_root in other.data.items():
            if vis not in self.data:
                calstate[vis] = other_root
                calstate.id_to_intent[vis] = other.id_to_intent[vis]
                calstate.id_to_field[vis] = other.id_to_field[vis]
                calstate.shape[vis] = other.shape[vis]

        return calstate

    def __iadd__(self, other):
        sum_state = self + other

        # adopt all properties from the added states
        self.data = sum_state.data
        self.id_to_field = sum_state.id_to_field
        self.id_to_intent = sum_state.id_to_intent
        self.shape = sum_state.shape

        return self

    def __sub__(self, other):
        return self._combine(other, ant_sub)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]

    def __contains__(self, item):
        return item in self.data

    def __iter__(self):
        return iter(self.data)


def fix_cycle0_data_selection(context: launcher.Context, calstate: IntervalCalState) -> IntervalCalState:
    # shortcut to minimise processing for data from Cycle 1 onwards.
    if any(utils.get_epoch_as_datetime(ms.start_time) <= CYCLE_0_END_DATE
           for ms in context.observing_run.measurement_sets):
        return calstate

    final_calstate = IntervalCalState.create_from_context(context)

    # We can't trust Cycle 0 data intents. If this is Cycle 0 data we need
    # to resolve the intents to fields and add them to the CalTo data
    # selection to ensure that the correct data is selected.
    for calto, calfroms in calstate.merged().items():
        vis = calto.vis
        ms = context.observing_run.get_ms(vis)
        if utils.get_epoch_as_datetime(ms.start_time) > CYCLE_0_END_DATE:
            final_calstate += IntervalCalState.from_calapplication(context, calto, calfroms)
            continue

        if calto.intent != '':
            fields_with_intent = ms.get_fields(task_arg=calto.field, intent=calto.intent)
            field_names = {f.name for f in fields_with_intent}

            if len(field_names) == len(fields_with_intent):
                new_field_arg = ','.join(field_names)
            else:
                new_field_arg = ','.join([str(field.id) for field in fields_with_intent])

            if new_field_arg != calto.field:
                LOG.info('Rewriting data selection to work around mislabeled Cycle 0 data intents. '
                         'Old field selection: %r; new field selection: %r', calto.field, new_field_arg)
                calto = CalTo(vis=calto.vis, field=new_field_arg, spw=calto.spw, antenna=calto.antenna,
                              intent=calto.intent)

        to_add = IntervalCalState.from_calapplication(context, calto, calfroms)
        final_calstate += to_add

    return final_calstate


class IntervalCalLibrary:
    """
    IntervalCalLibrary is the root object for the pipeline calibration state.

    This implementation of the CalLibrary is based on the interval tree data
    structure.
    """
    def __init__(self, context: launcher.Context) -> None:
        """Initialize an IntervalCalLibrary instance."""
        self._context = context
        self._active = IntervalCalState.create_from_context(context)
        self._applied = IntervalCalState.create_from_context(context)

    def clear(self) -> None:
        """Clear all active and applied calibrations."""
        self._active.clear()
        self._applied.clear()

    def _calc_filename(self, filename: str | None = None) -> str:
        """
        Return output filename for this IntervalCalLibrary.

        If given filename is not None or an empty string, then given filename is
        returned. Otherwise, a new filename is defined based on the context
        name.

        Args:
            filename: Proposed output filename (optional).

        Returns:
            Output filename to use.
        """
        if filename in ('', None):
            filename = os.path.join(self._context.output_dir,
                                    self._context.name + '.calstate')
        return filename

    def _export(self, calstate: IntervalCalState, filename: str | None = None) -> None:
        """
        Export input calibration state to a file.

        Args:
            calstate: Calibration state to export to a file.
            filename: Name for saved calibration state file.
        """
        filename = self._calc_filename(filename)

        calapps = [CalApplication(k, v) for k, v in calstate.merged().items()]

        with open(filename, 'w') as export_file:
            for ca in calapps:
                export_file.write(ca.as_applycal())
                export_file.write('\n')

    def add(self, calto, calfroms):
        to_add = IntervalCalState.from_calapplication(self._context, calto, calfroms)
        self._active += to_add

        if LOG.isEnabledFor(logging.TRACE):
            LOG.trace('Calstate after _add:\n%s', self._active.as_applycal())

    @property
    def active(self) -> IntervalCalState:
        """
        CalState holding CalApplications to be (pre-)applied to the MS.
        """
        return self._active

    @property
    def applied(self) -> IntervalCalState:
        """
        CalState holding CalApplications that have been applied to the MS via
        the pipeline applycal task.
        """
        return self._applied

    def export(self, filename: str | None = None) -> None:
        """
        Export the pre-apply calibration state to disk.

        The pre-apply calibrations held in the 'active' CalState will be
        written to disk as a set of equivalent applycal calls.

        Args:
            filename: Name for saved calibration state file.
        """
        filename = self._calc_filename(filename)
        LOG.info('Exporting current calibration state to %s', filename)
        self._export(self._active, filename)

    def export_applied(self, filename: str | None = None) -> None:
        """
        Export the applied calibration state to disk.

        The calibrations held in the 'applied' CalState will be written to
        disk as a set of equivalent applycal calls.

        Args:
            filename: Name for saved calibration state file.
        """
        filename = self._calc_filename(filename)
        LOG.info('Exporting applied calibration state to %s', filename)
        self._export(self._applied, filename)

    def get_calstate(self, calto, ignore: list | None = None) -> IntervalCalState:
        """
        Get the active calibration state for a target data selection.

        Args:
            calto: The data selection to retrieve active calibration state for.
            ignore: CalFrom properties to ignore.

        Returns:
            New IntervalCalState object representing active calibration state
            for a target data selection.
        """
        if ignore is None:
            ignore = []

        trimmed = self.active.trimmed(self._context, calto)

        # TODO replace with something like defrag_tree implementation
        for tree in trimmed.data.values():
            for antenna_interval in tree:
                spw_tree = tsd_accessor(antenna_interval)
                for spw_interval in spw_tree:
                    field_tree = tsd_accessor(spw_interval)
                    for field_interval in field_tree:
                        intent_tree = tsd_accessor(field_interval)
                        for intent_interval in intent_tree:
                            old_vals = tsd_accessor(intent_interval)
                            old_vals[:] = [self._copy_calfrom(cf, ignore)
                                           for cf in old_vals]

        return trimmed

    def _copy_calfrom(self, to_copy, ignore=None):
        if ignore is None:
            ignore = []

        calfrom_properties = ['caltype', 'calwt', 'gainfield', 'gaintable',
                              'interp', 'spwmap']

        copied = {k: getattr(to_copy, k) for k in calfrom_properties
                  if k not in ignore}

        return CalFrom(**copied)

    def import_state(self, filename=None, append=False):
        filename = self._calc_filename(filename)

        LOG.info('Importing calibration state from %s' % filename)
        calapps = []
        with open(filename, 'r') as import_file:
            for line in [l for l in import_file if l.startswith('applycal(')]:
                calapp = CalApplication.from_export(line)
                calapps.append(calapp)

        if not append:
            for _, calstate in self._active.data.items():
                calstate.clear()

        for calapp in calapps:
            LOG.debug('Adding %s', calapp)
            self.add(calapp.calto, calapp.calfrom)

        LOG.info('Calibration state after import:\n%s', self.active.as_applycal())

    def mark_as_applied(self, calto, calfrom):
        application = IntervalCalState.from_calapplication(self._context, calto, calfrom)
        self._active -= application
        self._applied += application

        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug('New calibration state:\n%s', self.active.as_applycal())
            LOG.debug('Applied calibration state:\n%s', self.applied.as_applycal())

    def unregister_calibrations(self, predicate_fn: Callable[[CalToArgs, CalFrom], bool]) -> None:
        """
        Delete active calibrations that match the input predicate function.

        Context
        =======

        Previously, calibration had to be removed by calling private callibrary
        functions, e.g.,

            calto = callibrary.CalTo(self.inputs.vis)
            calfrom = callibrary.CalFrom(gaintable=ktypecaltable, interp='', calwt=False)
            context.callibrary._remove(calto, calfrom, context.callibrary._active)

        This function makes calibration removal a first-class public function
        of the callibrary, and requires less knowledge of the calibration to remove.

        Example usage
        =============

        The predicate function passed in by the caller defines which
        calibrations should be unregistered. For example, Tsys caltable
        removal can be achieved with the code below.

            def match_tsys(calto, calfrom):
                return calfrom.type == 'tsys'
            callibrary.unregister_calibrations(match_tsys)

        The pipeline inserts the task name into the caltable filename,
        which can be used to unregister caltables generated by that task. For
        example,

            def match_task_caltable(calto, calfrom):
                return 'hifa_bandpass' in calfrom.gaintable
            context.callibrary.unregister_calibrations(match_task_caltable)

        If you wanted to match calwt, interp, vis, etc. then that could be
        done in the matcher function too, but if it's not necessary to
        identify the caltable then it doesn't need to be tested in the
        predicate function.
        """
        to_remove = get_matching_calstate(self._context, self.active, predicate_fn)
        self._active -= to_remove


# Set the pipeline calibration state and library to the Interval Tree based
# implementation.
CalState = IntervalCalState
CalLibrary = IntervalCalLibrary

# Note: the current Interval Tree based implementation of the callibrary
# was introduced in March 2016 (commit 71b6e5bd67d240e2e27fe1a973715cf3aec4b0ab)
# and has been in use since the Cycle 4 Pipeline release, October 2016,
# (CASA 4.7.0 + Pipeline-Cycle4-R2-B, r38377).
#
# The original Pipeline callibrary was a dictionary-based implementation of the
# calibration state (DictCalState) and corresponding library (DictCalLibrary),
# that supported the same interface as the interval-tree based implementation.
# The dictionary-based implementation has been unused since the Cycle 4 Pipeline
# release in 2016, and was removed in December 2024 (as part of infrastructure
# work done in PIPE-2160) in commit: 81b674d10b9aa4b6ed9df8550af18ec86e2f26ce


class TimestampedData(collections.namedtuple('TimestampedDataBase', ['time', 'data', 'marker'])):
    __slots__ = ()  # Saves memory, avoiding the need to create __dict__ for each interval

    def __new__(cls, time, data, marker=None):
        return super(TimestampedData, cls).__new__(cls, time, data, marker)

    def cmp(self, other):
        """
        Tells whether other sorts before, after or equal to this
        Interval.

        Sorting is by time then by data fields.

        If data fields are not both sortable types, data fields are
        compared alphabetically by type name.
        :param other: Interval
        :return: -1, 0, 1
        :rtype: int
        """
        if self.time != other.time:
            return -1 if self.time < other.time else 1
        try:
            if self.data == other.data:
                return 0
            return -1 if self.data < other.data else 1
        except TypeError:
            s = type(self.data).__name__
            o = type(other.data).__name__
            if s == o:
                return 0
            return -1 if s < o else 1

    def __lt__(self, other):
        """
        Less than operator. Parrots __cmp__()
        :param other: Interval or point
        :return: True or False
        :rtype: bool
        """
        return self.cmp(other) < 0

    def __gt__(self, other):
        """
        Greater than operator. Parrots __cmp__()
        :param other: Interval or point
        :return: True or False
        :rtype: bool
        """
        return self.cmp(other) > 0

    def __repr__(self):
        """
        Return executable string representation of this Interval."""
        if self.marker is None:
            return 'TSD({0}, {1})'.format(self.time, repr(self.data))
        return 'TSD({0}, {1}, {2})'.format(self.time, repr(self.data), self.marker)

    def __str__(self) -> str:
        """Return string representation of this Interval."""
        return 'TSD({0})'.format(repr(self.data))

    def __eq__(self, other: TimestampedData) -> bool:
        """
        Whether the begins equal, the ends equal, and the data fields
        equal. Compare range_matches().

        Args:
            other: TimestampedData to test equality for.

        Returns:
            True or False.
        """
        if not isinstance(other, TimestampedData):
            return False
        return self.time == other.time and \
               self.data == other.data and \
               self.marker == other.marker


def trim_to_valid_data_selection(calstate: IntervalCalState, vis: str | None = None) \
        -> dict[str, intervaltree.IntervalTree]:
    """
    Trim an IntervalCalState to the shape of valid (present) data selections.

    This is achieved by trimming Intervals for each dimension (antenna, spw,
    field, intent) to exclude ranges for which no data is present.

    See CAS-9415: CalLibrary needs a way to filter out calibration
    applications for missing data selections

    Args:
        calstate: The calstate to shape.
        vis: Name of the calstate to shape. If not defined, shape all.

    Returns:
        A dictionary mapping name of MS to its trimmed IntervalTree.
    """
    if vis is None:
        vislist = list(calstate.data.keys())
    else:
        vislist = [vis] if isinstance(vis, str) else vis

    results = {}
    for vis in vislist:
        antenna_tree = calstate.data[vis]

        new_root = intervaltree.IntervalTree()
        for antenna_tuple in calstate.shape[vis]:
            for antenna_ranges, spw_tuple in antenna_tuple:
                for spw_ranges, field_tuple in spw_tuple:
                    for field_ranges, intent_ranges in field_tuple:
                        tree_intervals = (antenna_ranges, spw_ranges, field_ranges, intent_ranges)
                        # print('Shaping to {!r}'.format(tree_intervals))
                        new_root |= trim_nd(antenna_tree, tree_intervals)

        results[vis] = new_root

    return results


def _merge_intervals(unmerged: dict) -> tuple:
    """
    Merge adjacent Intervals (represented by the keys within the input dict)
    that have identical values and output an IntervalTree-friendly tuple of
    constructor arguments.

    For example, a dict containing

        {1: A, 2: B, 3:A, 4:A}

    would be converted to

        ((((1, 2), (3, 5)), 'A'), (((2, 3),), 'B'))

    Args:
        unmerged: A dict mapping IDs to values.

    Returns:
        Tuple of constructor arguments ready for create_interval_tree_nd.
    """
    reversed = collections.defaultdict(set)
    for k, v in unmerged.items():
        reversed[v].add(k)
    return tuple(sorted((tuple(sequence_to_range(seq) for seq in contiguous_sequences(v)), k)
                        for k, v in reversed.items()))


def _print_dimensions(calstate: IntervalCalState) -> None:
    """
    Debugging function used to print the dimensions of an IntervalCalState.

    Args:
        calstate: The calstate to inspect.
    """
    for vis, antenna_tree in calstate.data.items():
        for antenna_interval in antenna_tree.items():
            antenna_ranges = (antenna_interval.begin, antenna_interval.end)
            for spw_interval in antenna_interval.data.data:
                spw_ranges = (spw_interval.begin, spw_interval.end)
                for field_interval in spw_interval.data.data:
                    field_ranges = (field_interval.begin, field_interval.end)
                    for intent_interval in field_interval.data.data:
                        intent_ranges = (intent_interval.begin, intent_interval.end)
                        tree_intervals = (os.path.basename(vis), antenna_ranges, spw_ranges, field_ranges, intent_ranges)
                        print('{!r}'.format(tree_intervals))


def get_calto_from_inputs(inputs):
    """
    Get a CalTo data selection object based on the state of an Inputs object
    """
    return CalTo(vis=inputs.vis, field=inputs.field, spw=inputs.spw, intent=inputs.intent, antenna=inputs.antenna)


def set_calstate_marker(calstate, marker):
    """
    Return a copy of a calstate, modified so that TimeStampedData objects in
    the final leaf node are annotated with the given marker object.

    Technical details:

    CalFroms are flyweight objects, so two identical CalFroms have the same
    hash. Identical hashes stop the IntervalTree union function from working
    as expected: IntervalTrees are based on sets, and as such adding two
    lists of CalFrom with identical hashes results in just one CalFrom list in
    the final IntervalTree, when we actually *wanted* the duplicate to be
    added.

    This function is used to ensure that CalState arithmetic works as
    expected. By changing the TimeStampedData marker and thus making the
    hashes different, 'identical' calibrations can indeed be duplicated in the
    IntervalTree union operation, and subsequently operated on in a
    merge_equals step.

    Args:
        calstate: The calstate to modify.
        marker: The object to annotate calstates with.

    Returns:
        New IntervalCalState representing the annotated calibration state.
    """
    calstate_copy = copy.deepcopy(calstate)

    for vis, antenna_tree in calstate_copy.data.items():
        for antenna_interval in antenna_tree.items():
            for spw_interval in antenna_interval.data.data:
                for field_interval in spw_interval.data.data:

                    to_remove = [i for i in field_interval.data.data]
                    to_add = []

                    intent_intervaltree = field_interval.data.data
                    for intent_interval in intent_intervaltree:
                        old_tsd = intent_interval.data
                        new_tsd = TimestampedData(time=old_tsd.time, data=old_tsd.data, marker=marker)
                        to_add.append(intervaltree.Interval(intent_interval.begin, intent_interval.end, new_tsd))

                    for interval in to_remove:
                        intent_intervaltree.remove(interval)
                    for interval in to_add:
                        intent_intervaltree.add(interval)

    return calstate_copy


def _copy_calfrom(calfrom: CalFrom, **overrides) -> CalFrom:
    """
    Copy a CalFrom, overwriting any CalFrom properties with the specified
    override values.

    For instance, to create a copy of a CalFrom with calwt set to True:

    modified = _copy_calfrom(calfrom, calwt=True)

    Args:
        calapp: CalFrom to copy.
        overrides: Keyword/value pairs of CalFrom properties to override.

    Returns:
        CalFrom instance with keywords overridden as per given arguments.
    """
    new_kwargs = dict(gaintable=calfrom.gaintable, gainfield=calfrom.gainfield, interp=calfrom.interp,
                      spwmap=list(calfrom.spwmap), caltype=calfrom.caltype, calwt=calfrom.calwt)
    new_kwargs.update(overrides)
    return CalFrom(**new_kwargs)


def _copy_calto(calto: CalTo, **overrides) -> CalTo:
    """
    Copy a CalTo, overwriting any CalFrom properties with the specified
    override values.

    For instance, to create a copy of a CalTo with spw set to 9:

    modified = _copy_calto(calto, spw=9)

    Args:
        calapp: CalTo to copy.
        overrides: Keyword/value pairs of CalTo properties to override

    Returns:
        CalTo instance with keywords overridden as per given arguments.
    """
    new_kwargs = dict(vis=calto.vis, field=calto.field, spw=calto.spw, antenna=calto.antenna, intent=calto.intent)
    new_kwargs.update(overrides)
    return CalTo(**new_kwargs)


def copy_calapplication(calapp: CalApplication, origin: CalAppOrigin | None = None, **overrides) -> CalApplication:
    """
    Copy a CalApplication, overwriting any CalTo or CalFrom values with the
    given override values.

    For instance, to create a copy of a CalApplication with the CalFrom.calwt
    set to True and the CalTo.spw set to 9:

    modified = copy_calapplication(calapp, calwt=True, spw=9)

    Args:
        calapp: The CalApplication to copy.
        origin: Origin to set, or None to copy the origin from calapp.
        overrides: Keyword/value pairs of CalTo/CalFrom attributes to override.

    Returns:
        New CalApplication instance with origin and keywords overridden as per
        given arguments.
    """
    if origin is None:
        origin = calapp.origin

    calto_kw = ['vis', 'field', 'spw', 'antenna', 'intent']
    calto_overrides = {k: v for k, v in overrides.items() if k in calto_kw}
    calto = _copy_calto(calapp.calto, **calto_overrides)

    calfrom_kw = ['gaintable', 'gainfield', 'interp', 'spwmap', 'caltype', 'calwt']
    calfrom_overrides = {k: v for k, v in overrides.items() if k in calfrom_kw}
    calfrom = [_copy_calfrom(calfrom, **calfrom_overrides) for calfrom in calapp.calfrom]

    return CalApplication(calto, calfrom, origin=origin)


@cachetools.cached(cachetools.LRUCache(50), key=operator.attrgetter('name'))
def get_calstate_shape(ms: MeasurementSet):
    """
    Get an IntervalTree shaped to the dimensions of the given measurement set.

    This function calculates the size of each metadata dimension (spw; intent;
    field; antenna), creating and returning an IntervalTree shaped to match.
    The output of this function is used to trim a calibration applied globally
    in one or more dimensions to a valid data selection.

    Output from this function is cached as it can take several seconds to
    calculate the result, which is done repeatedly when importing a calstate
    containing many entries.

    Note: this assumes that shape of an MS never changes, which should be
    true; the number of spws, fields, ants, etc. never changes.

    Args:
        ms: The MeasurementSet to analyse.

    Returns:
        IntervalTree shaped to match valid data dimensions.
    """
    LOG.debug('Calculating callibrary shape for {}'.format(ms.basename))

    # holds a mapping of numeric intent ID to string intent
    id_to_intent = get_intent_id_map(ms)
    # create map of observing intent to intent ID by inverting existing map
    intent_to_id = {v: k for k, v in id_to_intent.items()}

    # create interval tree. root branch is antenna
    antenna_tree = create_interval_tree_for_ms(ms)

    spw_shape = {}
    for spw in ms.spectral_windows:
        intents_for_field = {}
        for field in ms.fields:
            if spw in field.valid_spws:
                # construct the list of observed intent IDs for this field
                #
                # we can't rely on field.intents as this property
                # aggregates all intents across all spws, which may
                # differ across spws when there are multiple tunings
                #
                # DON'T DO THIS!
                # observed_intent_ids = (intent_to_id[i] for i in field.intents)
                scans_for_field_and_spw = ms.get_scans(spw=spw.id, field=field.id)
                observed_intent_ids = [intent_to_id[i]
                                       for scan in scans_for_field_and_spw
                                       for i in scan.intents]

                # SD scans can have subscans, where each subscan observes a
                # different field with different intent, e.g., TARGET alternating
                # with REFERENCE. Non-SD data should have a single target per
                # scan, so the following code should be a no-op.
                subscan_fields = {scan_field for scan in scans_for_field_and_spw for scan_field in scan.fields}
                if len(subscan_fields) > 1:
                    # unfortunately, we have to fall back to the field.intents
                    # method. Expect this to break for multituning SD EBs.
                    observed_intent_ids = (intent_to_id[i] for i in field.intents)

                # convert the intent IDs to an IntervalTree-friendly range
                # and record it against the field ID
                intents_for_field[field.id] = tuple(
                    sequence_to_range(seq) for seq in contiguous_sequences(observed_intent_ids)
                )
        # merge adjacent field intervals that have identical values
        spw_shape[spw.id] = _merge_intervals(intents_for_field)
    # merge adjacent spw intervals that have identical values
    spw_shape = _merge_intervals(spw_shape)

    # assume that spws are observed by all antennas. Note the trailing comma to make it a tuple!
    # the inner tuple is needed to convert the generator comprehension to objects
    antenna_shape = (tuple((((interval.begin, interval.end),), spw_shape) for interval in antenna_tree),)

    return antenna_shape


def get_matching_calstate(context: launcher.Context, calstate: IntervalCalState,
                          predicate_fn: Callable[[CalToArgs, CalFrom], bool]) -> IntervalCalState:
    """
    Return an IntervalCalState contain calibrations in the input 
    IntervalCalState that match the predicate function.

    The use case for this function is to identify calibrations matching a
    pattern so that those calibrations can be deleted or modified. For
    instance, matching registered bandpass caltables so they can be removed
    from the active CalState.

    Args:
        context: Pipeline context (required to create IntervalCalState).
        calstate: Calibration state to inspect.
        predicate_fn: Matching function that returns True when the selection
            is to be added to the output IntervalCalState.

    Returns:
        IntervalCalState containing the calibrations from the input
        IntervalCalState that match the given predicate function.
    """
    expanded = expand_calstate_to_calapps(calstate)

    matching = [IntervalCalState.from_calapplication(context, CalTo.from_caltoargs(caltoargs), calfrom)
                for (caltoargs, calfroms) in expanded
                for calfrom in calfroms
                if predicate_fn(caltoargs, calfrom)]

    consolidated = functools.reduce(operator.add, matching, IntervalCalState.create_from_context(context))

    return consolidated
