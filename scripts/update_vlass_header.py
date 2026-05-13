"""update_vlass_header.py - Add fits header keywords to the VLASS images

Background:
The VLASS header keywords introduced in PIPE-2461 and PIPE-3040 are only present in data processed with the updated pipeline. 
Data produced with earlier pipeline versions (prior to 6.7.1) do not include these keywords. This script provides a standalone 
method to populate the missing header keywords in such datasets using information from archived files.

Requirements:
    - astropy

Install with:
    pip install astropy

Usage:
    python update_vlass_header.py <products_dir>
"""

import argparse
import ast
import logging
import os
import re
import sys

from astropy.io import fits
import numpy as np


# logger
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
LOG = logging.getLogger(os.path.basename(__file__))


def get_vlass_image_type(filename: str, append_tt: bool = True) -> str:
    """
        Determine the VLASS image type based on specific substrings in the filename.
    """
    filename = os.path.basename(filename).lower()
    base = (
        "ALPHAERR" if ".alpha.error" in filename else
        "ALPHA" if ".alpha" in filename else
        "RMS" if ".rms" in filename else
        "COM" if ".com" in filename else
        "INTENSITY_PBCOR" if "image.pbcor." in filename else
        "UNKNOWN"
    )
    if base == "UNKNOWN" or not append_tt:
        return base

    tt = ("_TT0" if "tt0" in filename else "_TT1" if "tt1" in filename else "")
    return base + tt


def get_vlass_epoch_tile_version(filename: str) -> tuple[str, str, str]:
    """Determine the VLASS epoch, tile name and version in the filename."""

    epoch_match = re.search(r"VLASS(\d+\.\d+)", filename)
    tilename_match = re.search(r"\.(T\d+t\d+)\.", filename)
    version_match = re.search(r"\.v(\d+)(?:\.|$)", filename)
    if epoch_match:
        epoch = epoch_match.group(1)
    else:
        LOG.warning(f"Unable to get epoch given the filename {filename}, setting epoch to ''")
        epoch = ''
    if tilename_match:
        tile = tilename_match.group(1)
    else:
        LOG.warning(f"Unable to get tile name given the filename {filename}, setting tile name to ''")
        tile = ''
    if version_match:
        version = version_match.group(1)
    else:
        LOG.warning(f"Unable to get version number given the filename {filename}, setting version number to ''")
        version = ''

    return epoch, tile, version


def get_vlass_images(products_dir: str) -> tuple[list, list, list, list]:
    """
    Retrieve a list of VLASS fits files from the specified products directory.

    Args:
        products_dir (str): Path to the products directory containing the VLASS images.
    Returns:
        tuple[list, list, list, list]: A tuple containing lists of PB-corrected, ALPHA, COM, and RMS FITS images.
    """
    pbcor_images = []
    alpha_images = []
    com_images = []
    rms_images = []
    for file in os.listdir(products_dir):
        if not file.endswith(".fits"):
            continue
        image_type = get_vlass_image_type(file, append_tt=False)
        if image_type == "INTENSITY_PBCOR":
            rms_image_name = os.path.join(products_dir, file.replace(".subim", ".rms.subim"))
            if os.path.exists(rms_image_name):
                pbcor_images.append(os.path.join(products_dir, file))
                rms_images.append(rms_image_name)
            else:
                LOG.warning(f"RMS image corresponding to {file} is missing.")
        elif image_type == "ALPHA" or image_type == "ALPHAERR":
            alpha_images.append(os.path.join(products_dir, file))
        elif image_type == "COM":
            com_images.append(os.path.join(products_dir, file))
        else:
            LOG.debug(f"Skipping file '{file}' of type '{image_type}'.")

    return pbcor_images, alpha_images, com_images, rms_images


def get_image_stats(pbcor_image: str) -> dict:
    """
    Extract peak and median values from VLASS images.

    Args:
        pbcor_image (str): Path to the PB-corrected FITS image.
    Returns:
       dict: {'PEAK': float | None, 'MEDIAN': float | None}
    """
    # assumption: the naming convention is always consistent 
    rms_image = pbcor_image.replace(".subim", ".rms.subim")

    if not os.path.exists(rms_image):
        LOG.error(f"RMS file '{rms_image}' corresponding to '{pbcor_image}' is missing.")
        return {"PEAK": None, "MEDIAN": None}

    def compute_stats(image_name, function):
        with fits.open(image_name) as hdul:
            # Assumption: the image data is always multidimensional
            data = hdul[0].data
            if data is None:
                val = None
            else:
                val = function(data[0])
        return val

    peak_val = compute_stats(pbcor_image, np.nanmax)
    median_val = compute_stats(rms_image, np.nanmedian)

    return {"PEAK": peak_val, "MEDIAN": median_val}


def get_image_stats_batch(pbcor_images: list, imaging_mode: list) -> dict:
    """
    Extract peak and median values from a batch of VLASS images.

    Args:
        pbcor_images (list): List of paths to FITS images.
        imaging_mode (list): List of imaging modes.
    Returns:
       dict: {basename: {'PEAK': float | None, 'MEDIAN': float | None}}
    """
    stokes_v_images = []
    image_stats = {}
    for pbcor_image in pbcor_images:
        LOG.info(f"Computing stats for '{pbcor_image}'...")
        # Assumption: the naming convention is always consistent.
        if '.IQU.' in pbcor_image or '.IQUV.' in pbcor_image:
            basename = os.path.basename(pbcor_image).split(".image.")[0]
            image_stats[basename] = get_image_stats(pbcor_image)
        elif '.V.' in pbcor_image:
            basename = os.path.basename(pbcor_image).split(".image.")[0]
            stokes_v_images.append((pbcor_image, basename))
        elif 'VLASS-SE-CUBE' not in imaging_mode:
            basename = os.path.basename(pbcor_image)
            match = re.search(r'(.*\.tt\d)', basename)
            if match:
                key = match.group(1)
                image_stats[key] = get_image_stats(pbcor_image)
        else:
            continue

    for pbcor_image, basename in stokes_v_images:
        iqu_key = basename.replace(".V.", ".IQU.")

        if iqu_key in image_stats:
            image_stats[basename] = image_stats[iqu_key]
        else:
            LOG.warning(f"No IQU stats found for '{pbcor_image}', skipping")
            continue

    return image_stats


def get_spw(filename: str) -> str:
    """Extract spectral window information from the filename."""
    spw_match = re.search(r"\.spw(\d+(?:,\d+)*)\.", filename)
    if spw_match:
        return spw_match.group(1)
    else:
        return ''


def get_vlass_metadata(imagename: str, stats: dict, parameters: dict) -> dict:
    """Builds vlass header keywords and values to be written to the FITS header
    Args:
        imagename (str): Name of the VLASS image for which to build metadata.
        stats (dict): Dictionary containing 'PEAK' and 'MEDIAN' values.
        parameters (dict): Dictionary containing imaging parameters.
    Returns:
        dict: Dictionary containing the VLASS header keywords and values.
    """

    vlass_metadata = {}
    epoch, tile, version = get_vlass_epoch_tile_version(imagename)
    spw = get_spw(imagename)
    if 'VLASS-SE-CUBE' in parameters.get('imaging_mode', []):
        vlass_im_mode = 'VLASS-SE-CUBE'
    elif 'VLASS-SE-CONT' in parameters.get('imaging_mode', []):
        vlass_im_mode = 'VLASS-SE-CONT'
    else:
        vlass_im_mode = 'VLASS-QL'
    if vlass_im_mode == 'VLASS-SE-CUBE':
        bandwidth = 2000000000
    else:
        bandwidth = 128000000
    im_type = get_vlass_image_type(imagename)
    if 'COM' in im_type:
        im_type = im_type.replace("COM", "INTENSITY_PBCOR")
    vlass_metadata['VLASSITY'] = im_type
    vlass_metadata['VLASSPT'] = vlass_im_mode
    vlass_metadata['VLASSTN'] = tile
    vlass_metadata['VLASSPC'] = parameters.get('phasecenter', '')
    vlass_metadata['VLASSEP'] = epoch
    vlass_metadata['VLASSVR'] = version
    vlass_metadata['VLASSPL'] = ''
    vlass_metadata['VLASSRJ'] = ''
    vlass_metadata['VLASSSPW'] = spw
    vlass_metadata['VLASSRMS'] = stats.get('MEDIAN', '')
    vlass_metadata['VLASSPK'] = stats.get('PEAK', '')
    vlass_metadata['VLASSBWN'] = bandwidth
    vlass_metadata['VLASSWP'] = ''

    return vlass_metadata


def update_fits_header(imagename: str, vlass_metadata: dict, dry_run: bool = False) -> None:
    """
    Update the FITS header of a VLASS image by adding VLASS header keywords.

    Args:
        imagename (str): Name of the FITS image to be updated.
        vlass_metadata (dict): Dictionary containing VLASS header keywords and values.
        dry_run (bool): If True, preview header updates without modifying FITS files.
    Returns:
        None
    """
    lower_imagename = imagename.lower()
    tt_type = "TT0" if "tt0" in lower_imagename else "TT1" if "tt1" in lower_imagename else None
    header_comments = {
        "VLASSITY": "VLASS image type",
        "VLASSPT": "VLASS product type",
        "VLASSTN": "VLASS tile name",
        "VLASSPC": "VLASS phasecenter",
        "VLASSEP": "VLASS epoch",
        "VLASSVR": "VLASS version number",
        "VLASSPL": "VLASS Stokes/polarization parameter",
        "VLASSRJ": "Rejected plane relevant for VLASS CC processing",
        "VLASSSPW": "Spectral windows used for image",
        "VLASSBWN": "Nominal bandwidth",
        "VLASSRMS": None,
        "VLASSPK": None,
        "VLASSWP": "Number of w-projection planes"
    }
    if tt_type == "TT0" or 'alpha' in lower_imagename:
        header_comments["VLASSRMS"] = (
            "Median rms calculated from RMS_TT0 (Stokes I) image"
        )
        header_comments["VLASSPK"] = (
            "Peak flux density of INTENSITY_PBCOR_TT0 (Stokes I) image"
        )
    elif tt_type == "TT1":
        header_comments["VLASSRMS"] = (
            "Median rms calculated from RMS_TT1 (Stokes I) image"
        )
        header_comments["VLASSPK"] = (
            "Peak flux density of INTENSITY_PBCOR_TT1 (Stokes I) image"
        )
    else:
        header_comments["VLASSRMS"] = "Median RMS calculated from RMS image"
        header_comments["VLASSPK"] = "Peak flux density of INTENSITY_PBCOR image"
    try:

        LOG.info(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Updating header for '{imagename}'..."
        )

        if dry_run:
            for key in vlass_metadata:
                LOG.info(
                    f"[DRY RUN] Would set "
                    f"{key} = {vlass_metadata[key]!r} "
                    f"/ {header_comments.get(key, '')}"
                )
            return

        with fits.open(imagename, mode='update') as hdul:
            header = hdul[0].header
            for key in vlass_metadata:
                LOG.debug(f"Setting header keyword '{key}' to '{vlass_metadata[key]} with comment '{header_comments.get(key, '')}'")
                header[key] = (vlass_metadata[key], header_comments.get(key, ""))

        LOG.debug(f"Updated header for {imagename}")
    except Exception as e:
        LOG.error(f"Failed to update header for '{imagename}': {e}")


def parseParameterFiles(products_dir: str) -> dict:
    """
    Parse parameter files in products_dir and return a dictionary of parameters.

    Args:
        products_dir (str): Path to the directory containing parameter files.
    Returns:
        dict: Dictionary containing parameter names and values.
    """
    parameters = {}
    imaging_modes = []
    # In case of CCIP imaging, there can be multiple parameter files, so iterating through all of the files
    # to get imaging_mode. Assuming, phasecenter will be the same across all the parameter files.
    for file in os.listdir(products_dir):
        if file.endswith(".list"):
            parameter_file = os.path.join(products_dir, file)
            try:
                with open(parameter_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            value = ast.literal_eval(value.strip())  # Safely evaluate the value
                            key = key.strip().lower()
                            if key == "imaging_mode":
                                imaging_modes.append(value)
                            elif key in ("spw", "phasecenter"):
                                parameters[key] = value
            except Exception as e:
                LOG.error(f"Failed to parse parameter file '{parameter_file}': {e}")

    if imaging_modes:
        parameters["imaging_mode"] = imaging_modes

    return parameters


def process(products_dir: str, dry_run: bool = False) -> None:
    """
    Update the FITS header of VLASS images in the specified products directory by adding missing keywords.

    Args:
        products_dir (str): Path to the products directory containing the VLASS images.
        dry_run (bool): If True, preview header updates without modifying FITS files.
    Returns:
        None
    """
    LOG.info(f"Processing VLASS images in '{products_dir}'...")
    if not os.path.exists(products_dir):
        LOG.error(f"Products directory '{products_dir}' does not exist.")
        return
    LOG.debug("Retrieving VLASS FITS images...")
    # get list of images
    pbcor_images, alpha_images, com_images, rms_images = get_vlass_images(products_dir)

    # parse parameter file/s to read phasecenter, imaging mode and spw
    parameters = parseParameterFiles(products_dir)

    # compute median rms and peak for pbcor images

    image_stats = get_image_stats_batch(pbcor_images, parameters.get('imaging_mode', []))

    for image in pbcor_images + alpha_images + com_images + rms_images:
        if 'VLASS-SE-CUBE' not in parameters.get('imaging_mode', []):
            match = re.search(r'(.*\.tt\d)', os.path.basename(image))
            if match:
                basename = match.group(1)
            else:
                basename = os.path.basename(image)
                if '.alpha.' in basename.lower():
                    basename = os.path.basename(image).split(".alpha.")[0]
                    basename = f'{basename}.image.pbcor.tt0'
        else:
            basename = os.path.basename(image).split(".image.")[0]
        if basename in image_stats:
            vlass_metadata = get_vlass_metadata(image, image_stats[basename], parameters)
            update_fits_header(image, vlass_metadata, dry_run=dry_run)
        else:
            LOG.warning(f"No stats found for '{image}', skipping header update.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add fits header keywords to the VLASS images")
    parser.add_argument(
        "products_dir",
        metavar='PRODUCTS_DIR',
        help="Path to the products directory containing the VLASS images",
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='Enable debug-level logging.',
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview header updates without modifying FITS files.',
    )

    args = parser.parse_args()

    if args.debug:
        LOG.setLevel(logging.DEBUG)

    process(args.products_dir, dry_run=args.dry_run)
