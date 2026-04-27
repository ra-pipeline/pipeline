
"""This module contains unit tests for the daskhelpers module.

The tests cover the following functionalities:

- Parallel processing with Dask using delayed
- Parallel map operation with Dask bag
- Parallel task performance measurement

They use pytest fixtures to create a Dask client and a temporary directory
containing sample data. The tests are skipped if the 'dask' package is not
installed.

To run these tests, use the following command:

```bash
pytest -vs pipeline/infrastructure/daskhelpers_test.py
casa_python -m pytest -vs pipeline/infrastructure/daskhelpers_test.py
```
"""

from __future__ import annotations

import importlib
import os
import shutil
import time
from typing import TYPE_CHECKING

import numpy as np
import pytest

from pipeline.infrastructure.daskhelpers import start_daskcluster, stop_daskcluster

# Define a decorator to check for the package
skip_if_no_dask = pytest.mark.skipif(importlib.util.find_spec('dask') is None, reason='dask not installed')

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    from dask.distributed import Client
    from numpy import generic, floating
    from numpy.typing import NDArray


@pytest.fixture(scope='module')
def dask_client() -> Generator[Client, None, None]:
    """Create and return a Dask client as a fixture.

    Yields:
        Client: A Dask client instance.
    """
    client = start_daskcluster()
    print(f'Dashboard link: {client.dashboard_link}')
    yield client
    # Teardown
    stop_daskcluster()
    print('Dask client closed')


@pytest.fixture(scope='module')
def sample_data_dir() -> Generator[str, None, None]:
    """Create a temporary directory for sample data.

    Yields:
        str: Path to the temporary data directory.
    """
    # Create directory
    data_dir = 'test_dask_data'
    os.makedirs(data_dir, exist_ok=True)

    # Generate data files
    for i in range(5):
        data = np.random.random(500000)
        np.save(f'{data_dir}/array_{i}.npy', data)

    yield data_dir

    # Cleanup
    shutil.rmtree(data_dir)
    print(f'Removed test data directory: {data_dir}')


@skip_if_no_dask
def test_parallel_processing(dask_client: Client, sample_data_dir: str) -> None:
    """Test parallel processing with Dask using delayed.

    Args:
        dask_client: The Dask client fixture.
        sample_data_dir: The path to the sample data directory.
    """
    import dask

    @dask.delayed
    def load_array(filename: str) -> NDArray[generic]:
        """Load a numpy array from file.

        Args:
            filename: The path to the numpy array file.

        Returns:
            The loaded numpy array.
        """
        return np.load(filename)

    @dask.delayed
    def process_array(array: NDArray[floating]) -> dict[str, float]:
        """Process an array with a CPU-intensive operation.

        Args:
            array: The numpy array to process.

        Returns:
            A dictionary containing statistics of the processed array.
        """
        # Simulate CPU-intensive work
        result = np.sin(array) * np.cos(array) * np.sqrt(np.abs(array))
        return {
            'mean': float(np.mean(result)),
            'std': float(np.std(result)),
            'min': float(np.min(result)),
            'max': float(np.max(result)),
        }

    # Create computation graph
    computation_tasks: list[dict[str, float]] = []
    for i in range(5):
        filename = f'{sample_data_dir}/array_{i}.npy'
        array = load_array(filename)
        stats = process_array(array)
        computation_tasks.append(stats)

    # Execute all tasks in parallel
    results: list[dict[str, float]] = dask.compute(*computation_tasks)

    # Verify results
    assert len(results) == 5
    for result in results:
        assert isinstance(result, dict)
        assert 'mean' in result
        assert 'std' in result
        assert 'min' in result
        assert 'max' in result
        # Values should be within expected ranges for sin*cos*sqrt operations
        assert -0.5 <= result['mean'] <= 0.5
        assert result['min'] >= -0.5
        assert result['max'] <= 0.5


@skip_if_no_dask
def test_parallel_map(dask_client: Client, sample_data_dir: str) -> None:
    """Test parallel map operation with Dask bag.

    Args:
        dask_client: The Dask client fixture.
        sample_data_dir: The path to the sample data directory.
    """
    import dask.bag as db

    # List all numpy files
    files: list[str] = [f'{sample_data_dir}/array_{i}.npy' for i in range(5)]

    # Create a bag from the file list
    file_bag = db.from_sequence(files)

    # Define operations
    def calculate_stats(filename: str) -> dict[str, Any]:
        """Load a file and calculate statistics.

        Args:
            filename: The path to the file.

        Returns:
            A dictionary containing file statistics.
        """
        arr = np.load(filename)
        transformed = np.exp(-arr) * np.cos(arr)
        return {
            'file': os.path.basename(filename),
            'mean': float(np.mean(transformed)),
            'sum': float(np.sum(transformed)),
            'count': len(arr),
        }

    # Apply the function to each file in parallel
    result_bag = file_bag.map(calculate_stats)
    results: list[dict[str, Any]] = result_bag.compute()

    # Verify results
    assert len(results) == 5
    for result in results:
        assert 'file' in result
        assert 'mean' in result
        assert 'sum' in result
        assert 'count' in result
        assert result['count'] == 500000


@skip_if_no_dask
def test_parallel_task_performance(dask_client: Client, sample_data_dir: str) -> None:
    """Test and measure performance of parallel vs sequential execution.

    This test compares the performance of parallel and sequential execution of a
    CPU-intensive task.  It measures the execution time for both and prints
    the speedup.  Note that the speedup is not asserted because it depends on
    hardware and system load.

    Args:
        dask_client: The Dask client fixture.
        sample_data_dir: The path to the sample data directory.
    """
    import dask

    # Define a CPU-intensive task
    def intensive_task(seed: int) -> float:
        """CPU-intensive calculation.

        Args:
            seed: Seed for random number generation.

        Returns:
            The mean of the calculation results.
        """
        np.random.seed(seed)
        x = np.random.random(1000000)
        for _ in range(5):
            x = np.sin(x) + np.cos(x**2) + np.sqrt(np.abs(x))
        return np.mean(x)

    # Sequential execution
    start_time = time.time()
    sequential_results: list[float] = [intensive_task(i) for i in range(10)]
    sequential_time = time.time() - start_time

    # Parallel execution with Dask
    start_time = time.time()
    delayed_tasks = [dask.delayed(intensive_task)(i) for i in range(10)]
    parallel_results: list[float] = dask.compute(*delayed_tasks)
    parallel_time = time.time() - start_time

    # Verify results match
    for seq, par in zip(sequential_results, parallel_results):
        assert abs(seq - par) < 1e-10

    # Check performance improvement
    # Note: This may not always pass on single-core systems or very loaded systems
    print(f'Sequential time: {sequential_time:.2f}s')
    print(f'Parallel time: {parallel_time:.2f}s')
    print(f'Speedup: {sequential_time / parallel_time:.2f}x')

    # We don't assert on speedup as it depends on hardware
    # but we can check that the parallel version works
    assert len(parallel_results) == 10
