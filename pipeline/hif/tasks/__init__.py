from .antpos import Antpos
from .applycal import IFApplycal, HpcIFApplycal
from .bandpass import BandpassMode, ChannelBandpass, PhcorBandpass
from .correctedampflag import Correctedampflag
from .checkproductsize import CheckProductSize
from .findcont import FindCont
from .fluxscale import Fluxscale
from .gaincal import GaincalMode, GTypeGaincal, GSplineGaincal, KTypeGaincal
from .lowgainflag import Lowgainflag
from .makeimages import MakeImages
from .makeimlist import MakeImList
from .mstransform import Mstransform
from .rawflagchans import Rawflagchans
from .refant import RefAnt, HpcRefAnt
from .setmodel import Setjy
from .setmodel import SetModels
from .tclean import Tclean
from .uvcontsub import UVcontFit, UVcontSub
from .polarization import Polarization
from .editimlist import Editimlist
from .transformimagedata import Transformimagedata
from .makermsimages import Makermsimages
from .makecutoutimages import Makecutoutimages
from .analyzealpha import Analyzealpha
from .selfcal import Selfcal

# set default tasks for tasks with several implementations to our desired
# specific implementation
Bandpass = PhcorBandpass
Gaincal = GaincalMode
