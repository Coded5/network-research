"""Private subprocess entry point; the parent owns both temporary files."""

import pickle
import sys
from pathlib import Path

from propagation_lab.engine import run
from propagation_lab.scenario import Scenario

if __name__ == "__main__":
    source, target = map(Path, sys.argv[1:3])
    scenario = Scenario.model_validate_json(source.read_text(encoding="utf-8"))
    result = run(scenario, compare="--compare" in sys.argv[3:])
    target.write_bytes(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL))
