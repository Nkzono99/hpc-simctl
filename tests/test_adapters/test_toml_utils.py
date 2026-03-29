"""Tests for shared TOML configuration utilities."""

from __future__ import annotations

from simctl.adapters._utils.toml_utils import apply_dotted_overrides, deep_merge


class TestDeepMerge:
    def test_simple_merge(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        base = {"sim": {"dt": 1e-8, "steps": 100}}
        override = {"sim": {"dt": 2e-8}}
        result = deep_merge(base, override)
        assert result["sim"]["dt"] == 2e-8
        assert result["sim"]["steps"] == 100

    def test_list_replaced(self) -> None:
        base = {"tags": [1, 2, 3]}
        override = {"tags": [4, 5]}
        result = deep_merge(base, override)
        assert result["tags"] == [4, 5]

    def test_does_not_mutate_inputs(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        result = deep_merge(base, override)
        assert "y" not in base["a"]
        assert result["a"] == {"x": 1, "y": 2}


class TestApplyDottedOverrides:
    def test_simple_key(self) -> None:
        config = {"dt": 1e-8}
        result = apply_dotted_overrides(config, {"dt": 2e-8})
        assert result["dt"] == 2e-8

    def test_nested_key(self) -> None:
        config = {"sim": {"dt": 1e-8, "steps": 100}}
        result = apply_dotted_overrides(config, {"sim.dt": 2e-8})
        assert result["sim"]["dt"] == 2e-8
        assert result["sim"]["steps"] == 100

    def test_deep_nested_key(self) -> None:
        config = {"a": {"b": {"c": 1}}}
        result = apply_dotted_overrides(config, {"a.b.c": 99})
        assert result["a"]["b"]["c"] == 99

    def test_creates_intermediate_dicts(self) -> None:
        config: dict = {}
        result = apply_dotted_overrides(config, {"a.b.c": 42})
        assert result["a"]["b"]["c"] == 42

    def test_list_index_access(self) -> None:
        config = {"species": [{"wp": 1.0}, {"wp": 2.0}]}
        result = apply_dotted_overrides(config, {"species.0.wp": 3.0})
        assert result["species"][0]["wp"] == 3.0
        assert result["species"][1]["wp"] == 2.0

    def test_list_index_second_element(self) -> None:
        config = {"species": [{"wp": 1.0}, {"wp": 2.0}]}
        result = apply_dotted_overrides(config, {"species.1.wp": 9.0})
        assert result["species"][0]["wp"] == 1.0
        assert result["species"][1]["wp"] == 9.0

    def test_does_not_mutate_input(self) -> None:
        config = {"sim": {"dt": 1e-8}}
        result = apply_dotted_overrides(config, {"sim.dt": 2e-8})
        assert config["sim"]["dt"] == 1e-8
        assert result["sim"]["dt"] == 2e-8

    def test_multiple_overrides(self) -> None:
        config = {"tmgrid": {"nx": 100, "ny": 1, "nz": 200}, "jobcon": {"nstep": 1000}}
        result = apply_dotted_overrides(
            config, {"tmgrid.nx": 512, "jobcon.nstep": 5000}
        )
        assert result["tmgrid"]["nx"] == 512
        assert result["tmgrid"]["ny"] == 1
        assert result["jobcon"]["nstep"] == 5000
