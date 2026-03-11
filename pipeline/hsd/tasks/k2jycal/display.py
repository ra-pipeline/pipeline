"""Plotting class for k2jycal stage."""
import collections
import decimal
import os

from typing import Any, Dict, Generator, List, Sequence, Tuple, Union

import numpy as np
import itertools
     
from matplotlib.figure import Figure
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

import pipeline.infrastructure.renderer.logger as logger
import pipeline.infrastructure.logging as logging

from ..common.display import DPISummary
from pipeline.domain.spectralwindow import SpectralWindow
from pipeline.domain.measures import FrequencyUnits

LOG = logging.get_logger(__name__)

class K2JyBoxScatterDisplay(object):
    """A display class to generate a mixed box and scatter plot of Jy/K factors across all SPWs."""
    
    def __init__(
        self,
        stage_dir: str, 
        valid_factors: Dict[Any, Any], 
        ms_labels: List[str], 
        spws: Dict[Any, Any] = None
    ) -> None:
        """Initialize K2JyBoxScatterDisplay instance.

        Args:
            stage_dir: Stage directory to which plots are exported
            valid_factors:  A dictionary where each key is an SPW ID and each value is another dictionary 
                            containing:
                                - "spw_obj": The spectral window object.
                                - "all_factors": Jy/K factors for all MS associated with this SPW (for boxplots).
                                - "ms_dict": Mapping of MS labels to Jy/K factors.
                                - "outliers": List of (MS label, factor) tuples for outliers.
            ms_labels: A list of MS labels corresponding to the valid_factors dataset.
            spws: A dictionary mapping SPW IDs to their metadata. 
                  If not provided, it is inferred from `valid_factors`.
        """
        self.stage_dir = stage_dir
        self.valid_factors = valid_factors
        self.ms_labels = ms_labels
        if spws is not None:   
            self.spws = spws
        else:
            # Infer spw objects from valid_factors
            self.spws = {spw_id: valid_factors[spw_id]["spw_obj"] for spw_id in valid_factors}
        
    def plot(self) -> List[logger.Plot]:
        """Generate plot.

        Returns:
            List of plots.
        """
        return list(self._plot())
    
    def _create_plot(self, plotfile: str, x_axis: str, y_axis: str) -> logger.Plot:
        """Create Plot instance from plotfile.

        Args:
            plotfile: Name of the plot file
            x_axis: X-axis label
            y_axis: Y-axis label

        Returns:
            Plot instance
        """
        parameters = {}
        # Collect SPW IDs and Receiver bands
        parameters['spws'] = list(self.spws.keys())
        parameters['receivers'] = list(set([spw.band for spw in self.spws.values()]))
        plot_obj = logger.Plot(plotfile,
                            x_axis=x_axis,
                            y_axis=y_axis,
                            parameters=parameters)
        return plot_obj
    
    def _plot(self) -> Generator[logger.Plot, None, None]:
        """
        Create a plot with:
            - Primary x-axis: Centre Frequency (GHz)
            - Secondary x-axis: SPW IDs
            
        Yields:
            Plot instance

        Plot style depends on the number of measurement sets (MS):
            - If MS count is below a threshold, a scatter plot is used (each MS’s data from ms_dict).
            - Otherwise, a boxplot is drawn (using all_factors) with manually overlaid outlier points.
        """
        MS_THRESHOLD = 5       # Use scatter plot if MS count is less than this threshold
        ALPHA = 1.0            # Weight for blending uniform spacing with normalized frequency differences
        LEGEND_LIMIT = 3         # If number of MS > LEGEND_LIMIT, shorten labels and add extra right-space.

        # helper: shorten label if needed
        # e.g. process_label("uid___A002_X1234_X56.ms") will return "X56"
        def process_label(labels_list, label) -> str:
            return label.split('_')[-1].split('.')[0] if len(labels_list) > LEGEND_LIMIT else label

        # Extract and sort SPWs by centre frequency
        spw_freq_pairs = []
        for spw_id in list(self.valid_factors.keys()):
            spw_obj = self.valid_factors[spw_id]["spw_obj"]
            f = float(spw_obj.centre_frequency.to_units(FrequencyUnits.GIGAHERTZ))
            spw_freq_pairs.append((spw_id, round(f, 1)))
        spw_freq_pairs.sort(key=lambda pair: pair[1])
        if spw_freq_pairs:
            spw_ids, frequencies = zip(*spw_freq_pairs)
            spw_ids = list(spw_ids)
            frequencies = list(frequencies)
        else:
            spw_ids, frequencies = [], []
        positions = self.__compute_x_positions(frequencies, ALPHA)
        
        xlabel_bottom = 'Frequency (GHz)'
        ylabel = 'Jy/K factor'
        
        fig = Figure(figsize=(8, 6))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)
        ax.set_xlabel(xlabel_bottom, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title('Jy/K Factors across Frequencies', fontsize=11, fontweight='bold')

        ms_count = len(self.ms_labels)
        ms_styles = {
            ms: (marker, color)
            for ms, marker, color in zip(self.ms_labels, itertools.cycle('osDv^<>'),
                                        itertools.cycle(colormaps.get_cmap('tab10').colors))
        }

        # CASE 1: Scatter Plot for MS count < MS_THRESHOLD
        if ms_count < MS_THRESHOLD:
            for ms in self.ms_labels:
                marker, color = ms_styles[ms]
                for i, spw_id in enumerate(spw_ids):
                    ms_data = self.valid_factors[spw_id]["ms_dict"].get(ms, [])
                    if ms_data:
                        y_vals = [d[0] for d in ms_data]
                        x_vals = [positions[i]] * len(y_vals)
                        ax.scatter(x_vals, y_vals, marker=marker, color=color, alpha=1.0,
                                label=process_label(self.ms_labels, ms) if i == 0 else "")
            if ms_count <= 20:
                # Expand x-axis to add space for legend if needed.
                lims = ax.get_xlim()
                extra = (max(positions) - min(positions)) / (len(spw_ids)/2) if spw_ids else 0
                if ms_count > LEGEND_LIMIT:
                    ax.set_xlim((lims[0], lims[1] + extra))
                ax.legend(title='MS', loc='best')

     # CASE 2: Boxplot for MS count >= MS_THRESHOLD
        else:
            # Build boxplot data from all_factors for each SPW.
            box_data = [self.valid_factors[spw_id]["all_factors"] for spw_id in spw_ids]
            bp = ax.boxplot(box_data, positions=positions, patch_artist=True, showfliers=False)
            for box in bp['boxes']:
                box.set_facecolor('orange')
                box.set_alpha(0.7)
                
            # Scatter outliers manually
            handles = {}
            for i, spw_id in enumerate(spw_ids):
                outliers = self.valid_factors[spw_id]["outliers"]
                for ms, factor in outliers:
                    marker, color = ms_styles[ms]
                    scatter = ax.scatter(positions[i], factor, marker=marker, color=color,
                                            edgecolor="black", zorder=3, label=ms)
                    if ms not in handles:
                        handles[ms] = scatter

                if handles and len(handles) <= 20:
                    # Expand x-axis if needed.
                    if (len(handles) > LEGEND_LIMIT):
                        lims = ax.get_xlim()
                        extra = (max(positions) - min(positions)) / (len(spw_ids)/2) if spw_ids else 0
                        keys = [process_label(handles.keys(), key) for key in handles.keys()]
                        ax.set_xlim((lims[0], lims[1] + extra))
                    else:
                        keys = handles.keys()

                    ax.legend(list(handles.values()), keys,
                            title="MS with outliers", loc="best")

        # Adjust y-limits if needed.
        y_min, y_max = ax.get_ylim()
        if (y_max - y_min) < 0.5:
            ax.set_ylim(y_min - 0.25, y_max + 0.25)

        ax_top = ax.twiny()
        ax_top.set_xlim(ax.get_xlim())
        ax_top.set_xticks(positions)
        ax_top.set_xticklabels(spw_ids)
        ax_top.set_xlabel('SPW ID', fontsize=11)
        ax.set_xticks(positions)
        ax.set_xticklabels(frequencies) # for the main x-axis, display the original frequency values.
        ax.grid(True)

        plotfile = os.path.join(self.stage_dir, 'k2jy_factors_across_frequencies.png')
        canvas.print_figure(plotfile, format='png', dpi=DPISummary)
        plot = self._create_plot(plotfile, xlabel_bottom, ylabel)
        yield plot
        
    @staticmethod    
    def __compute_x_positions(frequencies: List[float], alpha: float) -> np.ndarray:
        """
        The x-positions for SPWs plotting are computed as a blend between uniform spacing (by index) and
        normalized frequency differences:
            x = i + alpha * ((f - f_min) / (f_max - f_min))
        ensuring that SPWs very close in frequency are evenly spaced while distant ones remain separated.

        Args:
            frequencies: List of centre frequencies (in GHz) for the SPWs.
            alpha: Weight for the normalized frequency term.

        Returns:
            Numpy array of x-positions.
        """
        N = len(frequencies)
        if N == 0:
            return np.array([])
        f_min, f_max = min(frequencies), max(frequencies)
        if f_max - f_min > 0:
            return np.array([i + alpha * ((f - f_min) / (f_max - f_min)) for i, f in enumerate(frequencies)])
        return np.arange(N, dtype=float)