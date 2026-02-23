"""This file contains slow regression-specific pytest configuration settings."""

import os

import pytest


@pytest.fixture(autouse=True, scope="module")
def data_directory() -> str:
    if hasattr(pytest, 'pytestconfig'):
        big_data_dir = pytest.pytestconfig.getoption('--data-directory')
    else:
        big_data_dir = "/lustre/cv/projects/pipeline-test-data/regression-test-data/"

    if not os.path.exists(big_data_dir):
        print(f"Warning! The large dataset directory {big_data_dir} does not exist, so any long-running tests will fail.")
    else:
        print(f"Using: {big_data_dir} for data directory")
    return big_data_dir
