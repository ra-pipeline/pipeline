import numpy


class Polarization(object):
    """A logical representation of a polarization.

    Integer correlation Stokes types are translated to their corresponding
    string representation using a local definition of the Stokes enumeration
    that is copied from the Stokes class enumeration in CASA.

    Attributes:
        id: Numerical identifier of the polarization.
        num_corr: Number of correlations associated with this polarization.
        corr_type: Integer representation of Stokes type for each correlation
            associated with this polarization.
        corr_product: Pairs of polarization types, corresponding to the two
            receptors in the correlation, for each correlation associated with
            this polarization.
        corr_type_string: String representation of Stokes type for each
            correlation associated with this polarization.
    """
    def __init__(self, pol_id: int, num_corr: int, corr_type: numpy.ndarray, corr_product: numpy.ndarray) -> None:
        """
        Initialize a Polarization object.

        Args:
            pol_id: Numerical identifier of the polarization.
            num_corr: Number of correlations associated with this polarization.
            corr_type: Stokes types for each correlation associated with this polarization.
            corr_product: Pairs of polarization types for each correlation
                associated with this polarization.
        """
        # prefer standard Python integers to numpy integers
        self.id = int(pol_id)
        self.num_corr = int(num_corr)
        self.corr_type = corr_type
        self.corr_product = corr_product

        # Copied from C++ casa::Stokes class
        _stokes_enum = ['Undefined', 'I', 'Q', 'U', 'V', 'RR', 'RL', 'LR', 'LL', 'XX', 'XY', 'YX', 'YY', 'RX', 'RY',
                        'LX', 'LY', 'XR', 'XL', 'YR', 'YL', 'PP', 'PQ', 'QP', 'QQ', 'RCircular', 'LCircular', 'Linear',
                        'Ptotal', 'Plinear', 'PFtotal', 'PFlinear', 'Pangle']
        self.corr_type_string = [_stokes_enum[c] for c in corr_type]

    def __str__(self) -> str:
        return 'Polarization({!r}, {!r})'.format(self.id, self.corr_type_string)

    def __repr__(self) -> str:
        return ('Polarization({!r}, {!r}, {!r}, {!r})'
                ''.format(self.id, self.num_corr, self.corr_type, self.corr_product))
