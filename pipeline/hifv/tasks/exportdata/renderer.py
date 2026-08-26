"""
Renderer for VLA ExportData task.
"""
import os

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.utils as utils

LOG = logging.get_logger(__name__)


class T2_4MDetailsVLAExportDataRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='exportdata.mako', description='Prepare pipeline data products for export',
                 always_rerender=False):
        super().__init__(uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, results):
        """Update mako context with merged table rows for image tables."""

        # Process each result to create merged table rows
        for r in results:
            calimages = r.calimages[0] if getattr(r, 'calimages', None) else []
            targetimages = r.targetimages[0] if getattr(r, 'targetimages', None) else []

            # Process calibrator images
            r.calimages_merged = self._merge_image_table(calimages, 'fitsfiles')
            r.calimages_aux_merged = self._merge_image_table(calimages, 'auxfitsfiles')

            # Process target images
            r.targetimages_merged = self._merge_image_table(targetimages, 'fitsfiles')
            r.targetimages_aux_merged = self._merge_image_table(targetimages, 'auxfitsfiles')

    def _merge_image_table(self, image_list, fitsfiles_key):
        """Convert image data to merged table rows using merge_td_columns.

        Args:
            image_list: List of image dictionaries containing sourcename, sourcetype, spwlist, and fitsfiles
            fitsfiles_key: Key to access fitsfiles list ('fitsfiles' or 'auxfitsfiles')

        Returns:
            List of tuples containing merged HTML <td> elements
        """
        rows = []
        for image in image_list:
            for fitsfile in image.get(fitsfiles_key, []):
                rows.append((
                    utils.wrap_long_str(image.get('sourcename', ''), newline='<br>'),
                    image.get('sourcetype', ''),
                    image.get('spwlist', ''),
                    os.path.basename(fitsfile),
                ))

        # Apply merge_td_columns to merge identical values in first 3 columns
        if rows:
            return utils.merge_td_columns(rows, num_to_merge=3)
        return []
