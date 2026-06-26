"""Nigeria states + LGAs — canonical server copy used to validate the report
`region` field and to roll reports up by state.

Data lives in ``nigeria_states.json`` (generated from mobile/lib/nigeria.dart so
the picker and the validator can't drift). Region is stored as "LGA, State".
"""
import json
from functools import lru_cache
from pathlib import Path

_JSON = Path(__file__).with_name("nigeria_states.json")


@lru_cache(maxsize=1)
def states():
    """{state: [lga, ...]} loaded once."""
    return json.loads(_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def valid_regions():
    """Set of every accepted "LGA, State" string."""
    return {f"{lga}, {st}" for st, lgas in states().items() for lga in lgas}


def region_state(region):
    """State portion of a "LGA, State" region, or "" if unparseable."""
    return region.rsplit(", ", 1)[-1] if ", " in region else ""
