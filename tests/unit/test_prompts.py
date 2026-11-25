import re

from config import ADS_DIR
from engine.knowledge import reference_text, taxonomy
from engine.prompts import PROMPT_VERSION, system_prompt, user_prompt


def test_prompt_is_grounded_in_reference_and_lists_all_15_codes():
    sp = system_prompt()
    assert reference_text().strip()[:200] in sp
    assert len(taxonomy()) == 15
    for code in taxonomy():
        assert code in sp


def test_prompt_version_is_set():
    assert re.fullmatch(r"v\d+(\.\d+)?", PROMPT_VERSION)


def test_no_ad_specific_logic_in_prompt():
    """Guards against tuning to the sample ads: no ad IDs and no distinctive ad phrases."""
    sp = system_prompt()
    assert not re.search(r"AD-\d\d", sp)
    # ("$299/month" is excluded: FCB's own reference.md uses it as an example.)
    for phrase in ["4.25%", "Free Checking", "First County Rewards", "3.99%", "6.125%", "$300"]:
        assert phrase not in sp


def test_user_prompt_carries_metadata_and_content():
    up = user_prompt("Earn 4.25%!", "mailer", "deposit")
    assert "Channel: mailer" in up and "Product: deposit" in up and "Earn 4.25%!" in up


def test_sample_ads_exist():
    assert len(list(ADS_DIR.glob("AD-*.md"))) == 12
