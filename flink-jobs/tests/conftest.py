import pathlib
import sys

# Make the flink-jobs package importable as top-level modules (windows, sinks).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
