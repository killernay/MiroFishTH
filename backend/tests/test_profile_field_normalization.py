import csv
import json

from app.utils.locale import set_locale
from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
    _coerce_to_str,
    _coerce_to_str_list,
)


def test_text_coercion_handles_none_nested_objects_and_lists():
    assert _coerce_to_str(None) == ""
    assert _coerce_to_str({"text": {"value": "中文"}}) == "中文"
    assert _coerce_to_str([None, {"description": "alpha"}, ["beta"]]) == "alpha, beta"
    assert _coerce_to_str({"unexpected": None}) == '{"unexpected": null}'


def test_list_coercion_flattens_nested_values_and_drops_missing_items():
    assert _coerce_to_str_list(
        ["AI", ["policy", None], {"name": "society"}, 4]
    ) == ["AI", "policy", "society", "4"]
    assert _coerce_to_str_list(None) == []


def test_profile_construction_is_the_single_normalization_boundary():
    profile = OasisAgentProfile(
        user_id=1,
        user_name="agent",
        name="Agent Name",
        bio=None,
        persona={"text": {"value": "详细人设"}},
        gender=["female"],
        mbti={"value": "INTJ"},
        country={"name": "中国"},
        profession={"description": "研究员"},
        interested_topics=["AI", ["政策", None], {"name": "社会"}],
    )

    assert profile.bio == "Agent Name"
    assert profile.persona == "详细人设"
    assert profile.gender == "female"
    assert profile.mbti == "INTJ"
    assert profile.country == "中国"
    assert profile.profession == "研究员"
    assert profile.interested_topics == ["AI", "政策", "社会"]
    assert "None" not in json.dumps(profile.to_dict(), ensure_ascii=False)


def test_normalized_profile_serializes_to_twitter_and_reddit(tmp_path):
    profile = OasisAgentProfile(
        user_id=1,
        user_name="agent",
        name="Agent Name",
        bio={"summary": "公开简介"},
        persona=["详细", "人设"],
        mbti={"text": "ENFP"},
        interested_topics=["AI", ["政策"]],
    )
    generator = object.__new__(OasisProfileGenerator)
    twitter_path = tmp_path / "twitter_profiles.csv"
    reddit_path = tmp_path / "reddit_profiles.json"

    generator._save_twitter_csv([profile], str(twitter_path))
    generator._save_reddit_json([profile], str(reddit_path))

    with twitter_path.open(encoding="utf-8") as handle:
        twitter = next(csv.DictReader(handle))
    reddit = json.loads(reddit_path.read_text(encoding="utf-8"))[0]

    assert twitter["description"] == "公开简介"
    assert twitter["user_char"] == "公开简介 详细, 人设"
    assert reddit["bio"] == "公开简介"
    assert reddit["persona"] == "详细, 人设"
    assert reddit["mbti"] == "ENFP"
    assert reddit["interested_topics"] == ["AI", "政策"]


def test_rule_based_fallback_does_not_publish_raw_entity_summary():
    set_locale("en")
    generator = object.__new__(OasisProfileGenerator)
    source_summary = "Unlabelled source evidence: 这是原始摘要"

    profile = generator._generate_profile_rule_based(
        "Example Entity", "unknown", source_summary, {}
    )

    assert source_summary not in profile["bio"]
    assert source_summary not in profile["persona"]
    assert "source evidence" not in profile["bio"].lower()
    assert "source evidence" not in profile["persona"].lower()


def test_profile_fallbacks_are_localized_without_entity_summary():
    generator = object.__new__(OasisProfileGenerator)
    source_summary = "Raw source summary"

    set_locale("en")
    assert source_summary not in generator._fallback_bio()
    assert source_summary not in generator._fallback_persona()

    set_locale("th")
    assert "การสนทนา" in generator._fallback_bio()
    assert "การสนทนา" in generator._fallback_persona()


def test_console_profile_output_uses_locale_labels_and_redacts_han(capsys):
    set_locale("en")
    generator = object.__new__(OasisProfileGenerator)
    profile = OasisAgentProfile(
        user_id=1,
        user_name="teacher_927",
        name="Teacher",
        bio="Social discussion participant.",
        persona="This account participates in social discussions.",
        country="中国",
        interested_topics=["教育"],
    )

    generator._print_generated_profile("Teacher", "Person", profile)
    output = capsys.readouterr().out

    assert "[Bio]" in output
    assert "[Detailed persona]" in output
    assert "[Basic attributes]" in output
    assert "【基本属性】" not in output
    assert "中国" not in output
    assert "[source text]" in output
