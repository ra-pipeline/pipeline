import psutil
import functools
import os
import time
import csv


def human_bytes(num):
    """Convert bytes into a human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} PB"


def profile_io(output_file="pipeline_io_log.csv"):
    """
    Decorator to measure I/O bytes and runtime of a function
    and log the information to a CSV file.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            proc = psutil.Process(os.getpid())
            io_start = proc.io_counters()
            t0 = time.time()

            result = func(*args, **kwargs)

            t1 = time.time()
            io_end = proc.io_counters()

            # Calculate deltas
            bytes_read = io_end.read_bytes - io_start.read_bytes
            bytes_written = io_end.write_bytes - io_start.write_bytes
            elapsed_time = t1 - t0

            # Human readable
            hr_read = human_bytes(bytes_read)
            hr_write = human_bytes(bytes_written)

            # Throughput (avoid division by zero)
            read_rate = bytes_read / elapsed_time / (1024*1024) if elapsed_time > 0 else 0
            write_rate = bytes_written / elapsed_time / (1024*1024) if elapsed_time > 0 else 0

            # Append info to CSV
            file_exists = os.path.isfile(output_file)
            with open(output_file, mode="a", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Method", "Bytes Read", "Bytes Written", "Time Elapsed (s)", "Read MB/s", "Write MB/s",])
                writer.writerow([func.__name__, hr_read, hr_write, f"{elapsed_time:.2f}", f"{read_rate:.2f}", f"{write_rate:.2f}"])

            return result
        return wrapper
    return decorator
