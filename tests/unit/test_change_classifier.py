"""Unit tests for the deterministic complexity classifier (WP03).

Tests cover:
- Individual scoring functions (scope, coupling, churn, ambiguity, risk)
- Threshold boundary tests at 3/4 split and 6/7 split
- Determinism: repeated runs produce identical results
- Classification and packaging mode selection
- Continue/stop gating behavior
- Score invariants (total == sum of factors, recommend_specify iff high)
"""

from __future__ import annotations

import pytest

from specify_cli.core.change_classifier import (
    COMPLEX_MAX,
    SIMPLE_MAX,
    TOTAL_MAX,
    ComplexityClassification,
    PackagingMode,
    ReviewAttention,
    classify_change_request,
    _classify,
    _score_ambiguity,
    _score_coupling,
    _score_dependency_churn,
    _score_integration_risk,
    _score_scope_breadth,
    _select_packaging_mode,
)


# ============================================================================
# Scope Breadth Scoring
# ============================================================================


class TestScopeBreadth:
    """Test _score_scope_breadth (0-3)."""

    def test_simple_single_target(self):
        """A request mentioning one file should score 0."""
        assert _score_scope_breadth("fix the typo in utils.py") == 0

    def test_two_targets_scores_one(self):
        """Mentioning two distinct targets should score 1."""
        score = _score_scope_breadth("update function parse_config and class Validator in config.py")
        assert score >= 1

    def test_many_targets_scores_two(self):
        """Many distinct targets should score 2."""
        score = _score_scope_breadth(
            "update function parse_config in config.py, class Validator in validator.py, "
            "method run_tests in runner.py, and module helpers in utils.py"
        )
        assert score >= 2

    def test_cross_cutting_scores_three(self):
        """Cross-cutting language should score 3."""
        assert _score_scope_breadth("refactor all modules in the project") == 3
        assert _score_scope_breadth("change every endpoint to use the new format") == 3

    def test_across_codebase_scores_three(self):
        """'Across the codebase' should score 3."""
        assert _score_scope_breadth("apply the new naming convention across the codebase") == 3

    def test_architectural_scores_three(self):
        """Architectural changes should score 3."""
        assert _score_scope_breadth("architectural refactoring of the data layer") == 3

    def test_max_value(self):
        """Score should never exceed 3."""
        score = _score_scope_breadth(
            "refactor all modules across the entire codebase and every component"
        )
        assert score <= 3


# ============================================================================
# Coupling Scoring
# ============================================================================


class TestCoupling:
    """Test _score_coupling (0-2)."""

    def test_isolated_change_scores_zero(self):
        """No coupling indicators should score 0."""
        assert _score_coupling("add a comment to the README") == 0

    def test_interface_mention_scores_one(self):
        """Mentioning an interface should score 1."""
        assert _score_coupling("update the interface for the plugin system") == 1

    def test_shared_state_scores_one(self):
        """Shared state references should score 1."""
        assert _score_coupling("change the shared config module") == 1

    def test_api_contract_scores_two(self):
        """API contract changes should score 2."""
        assert _score_coupling("update the api contract for the v2 endpoint") == 2

    def test_database_schema_scores_two(self):
        """Database schema changes should score 2."""
        assert _score_coupling("modify the database schema for users table") == 2

    def test_breaking_change_scores_two(self):
        """Breaking changes should score 2."""
        assert _score_coupling("this is a breaking change to the auth module") == 2

    def test_max_value(self):
        """Score should never exceed 2."""
        score = _score_coupling(
            "breaking change to the api contract and database schema"
        )
        assert score <= 2


# ============================================================================
# Dependency Churn Scoring
# ============================================================================


class TestDependencyChurn:
    """Test _score_dependency_churn (0-2)."""

    def test_no_dependency_change_scores_zero(self):
        """No dependency language should score 0."""
        assert _score_dependency_churn("fix the login button color") == 0

    def test_add_package_scores_one(self):
        """Adding a package should score 1."""
        assert _score_dependency_churn("add package requests to the project") == 1

    def test_pip_mention_scores_one(self):
        """Mentioning pip should score 1."""
        assert _score_dependency_churn("install via pip the new formatter") == 1

    def test_replace_framework_scores_two(self):
        """Replacing a framework should score 2."""
        assert _score_dependency_churn("replace framework Flask with FastAPI") == 2

    def test_switch_from_to_scores_two(self):
        """'Switch from X to Y' should score 2."""
        assert _score_dependency_churn("switch from SQLite to PostgreSQL") == 2

    def test_migrate_from_to_scores_two(self):
        """'Migrate from X to Y' should score 2."""
        assert _score_dependency_churn("migrate from unittest to pytest") == 2

    def test_max_value(self):
        """Score should never exceed 2."""
        score = _score_dependency_churn(
            "replace framework Django with FastAPI and switch from MySQL to PostgreSQL"
        )
        assert score <= 2


# ============================================================================
# Ambiguity Scoring
# ============================================================================


class TestAmbiguityScore:
    """Test _score_ambiguity (0-2) - residual uncertainty after fail-fast."""

    def test_clear_request_scores_zero(self):
        """A clear, specific request should score 0."""
        assert _score_ambiguity("add a retry mechanism to the HTTP client in client.py") == 0

    def test_hedging_language_scores_one(self):
        """Hedging language should score 1."""
        assert _score_ambiguity("maybe add some caching or something") == 1
        assert _score_ambiguity("I think we should probably update the tests") == 1

    def test_vague_improvement_scores_two(self):
        """Vague improvement language should score 2."""
        assert _score_ambiguity("improve the performance of the code") == 2
        assert _score_ambiguity("clean up the module") == 2

    def test_make_it_better_scores_two(self):
        """'Make it better' type requests should score 2."""
        assert _score_ambiguity("make it faster and cleaner") == 2

    def test_targeted_optimize_scores_zero(self):
        """Optimize with specific target should score lower."""
        # "optimize the query in search_handler" has a specific target
        score = _score_ambiguity("optimize the query function for the search index")
        assert score <= 1

    def test_max_value(self):
        """Score should never exceed 2."""
        score = _score_ambiguity("maybe improve the code quality somehow or something")
        assert score <= 2


# ============================================================================
# Integration Risk Scoring
# ============================================================================


class TestIntegrationRisk:
    """Test _score_integration_risk (0-1)."""

    def test_localized_change_scores_zero(self):
        """A localized code change should score 0."""
        assert _score_integration_risk("rename the variable from x to count") == 0

    def test_ci_cd_scores_one(self):
        """CI/CD changes should score 1."""
        assert _score_integration_risk("update the CI/CD pipeline configuration") == 1

    def test_deployment_scores_one(self):
        """Deployment changes should score 1."""
        assert _score_integration_risk("modify the deployment script for production") == 1

    def test_docker_scores_one(self):
        """Docker changes should score 1."""
        assert _score_integration_risk("update the Dockerfile for the new base image") == 1

    def test_kubernetes_scores_one(self):
        """Kubernetes changes should score 1."""
        assert _score_integration_risk("change the kubernetes manifest") == 1

    def test_environment_config_scores_one(self):
        """Environment config changes should score 1."""
        assert _score_integration_risk("add new environment variable for API key") == 1

    def test_external_api_scores_one(self):
        """External service changes should score 1."""
        assert _score_integration_risk("integrate with the external api for payments") == 1

    def test_max_value(self):
        """Score should never exceed 1."""
        score = _score_integration_risk(
            "update Docker, Kubernetes, CI/CD pipeline, and deploy to production"
        )
        assert score <= 1


# ============================================================================
# Classification Thresholds
# ============================================================================


class TestClassificationThresholds:
    """Test deterministic threshold boundaries."""

    def test_simple_max_boundary(self):
        """Score of 3 should classify as simple."""
        assert _classify(3) == ComplexityClassification.SIMPLE

    def test_complex_min_boundary(self):
        """Score of 4 should classify as complex (3/4 split)."""
        assert _classify(4) == ComplexityClassification.COMPLEX

    def test_complex_max_boundary(self):
        """Score of 6 should classify as complex."""
        assert _classify(6) == ComplexityClassification.COMPLEX

    def test_high_min_boundary(self):
        """Score of 7 should classify as high (6/7 split)."""
        assert _classify(7) == ComplexityClassification.HIGH

    def test_zero_is_simple(self):
        """Score of 0 should classify as simple."""
        assert _classify(0) == ComplexityClassification.SIMPLE

    def test_max_is_high(self):
        """Maximum possible score should classify as high."""
        assert _classify(TOTAL_MAX) == ComplexityClassification.HIGH

    @pytest.mark.parametrize("score", range(0, SIMPLE_MAX + 1))
    def test_all_simple_scores(self, score: int):
        """All scores 0-3 should be simple."""
        assert _classify(score) == ComplexityClassification.SIMPLE

    @pytest.mark.parametrize("score", range(SIMPLE_MAX + 1, COMPLEX_MAX + 1))
    def test_all_complex_scores(self, score: int):
        """All scores 4-6 should be complex."""
        assert _classify(score) == ComplexityClassification.COMPLEX

    @pytest.mark.parametrize("score", range(COMPLEX_MAX + 1, TOTAL_MAX + 1))
    def test_all_high_scores(self, score: int):
        """All scores 7-10 should be high."""
        assert _classify(score) == ComplexityClassification.HIGH


# ============================================================================
# Packaging Mode Selection
# ============================================================================


class TestPackagingMode:
    """Test deterministic packaging mode selection."""

    def test_simple_always_single_wp(self):
        """Simple classification always uses single_wp."""
        assert _select_packaging_mode(ComplexityClassification.SIMPLE, 0, 0) == PackagingMode.SINGLE_WP
        assert _select_packaging_mode(ComplexityClassification.SIMPLE, 2, 3) == PackagingMode.SINGLE_WP

    def test_complex_high_coupling_orchestration(self):
        """Complex with high coupling should use orchestration."""
        assert _select_packaging_mode(ComplexityClassification.COMPLEX, 2, 0) == PackagingMode.ORCHESTRATION

    def test_complex_broad_scope_targeted_multi(self):
        """Complex with broad scope but low coupling should use targeted_multi."""
        assert _select_packaging_mode(ComplexityClassification.COMPLEX, 0, 2) == PackagingMode.TARGETED_MULTI
        assert _select_packaging_mode(ComplexityClassification.COMPLEX, 1, 3) == PackagingMode.TARGETED_MULTI

    def test_complex_low_both_single_wp(self):
        """Complex with low coupling and narrow scope should use single_wp."""
        assert _select_packaging_mode(ComplexityClassification.COMPLEX, 0, 1) == PackagingMode.SINGLE_WP
        assert _select_packaging_mode(ComplexityClassification.COMPLEX, 1, 0) == PackagingMode.SINGLE_WP

    def test_high_follows_same_rules(self):
        """High classification follows same packaging rules as complex."""
        assert _select_packaging_mode(ComplexityClassification.HIGH, 2, 0) == PackagingMode.ORCHESTRATION
        assert _select_packaging_mode(ComplexityClassification.HIGH, 0, 3) == PackagingMode.TARGETED_MULTI
        assert _select_packaging_mode(ComplexityClassification.HIGH, 0, 0) == PackagingMode.SINGLE_WP


# ============================================================================
# Score Invariants
# ============================================================================


class TestScoreInvariants:
    """Test invariants that must hold for all inputs."""

    SAMPLE_REQUESTS = [
        "fix typo in README",
        "add a caching layer to the API",
        "replace framework Flask with FastAPI and switch from SQLite to PostgreSQL",
        "refactor all modules across the entire codebase",
        "improve the performance of the code",
        "update the CI/CD pipeline and deploy to kubernetes",
        "maybe add some caching or something to the database schema",
        "use SQLAlchemy instead of raw SQL in the models",
        "add package requests and update the external api for payments",
        "clean up the module and update the interface for the plugin system",
    ]

    @pytest.mark.parametrize("request_text", SAMPLE_REQUESTS)
    def test_total_equals_sum_of_factors(self, request_text: str):
        """total_score must equal the sum of all five factors."""
        score = classify_change_request(request_text)
        expected = (
            score.scope_breadth_score
            + score.coupling_score
            + score.dependency_churn_score
            + score.ambiguity_score
            + score.integration_risk_score
        )
        assert score.total_score == expected, (
            f"Total {score.total_score} != sum {expected} for: {request_text}"
        )

    @pytest.mark.parametrize("request_text", SAMPLE_REQUESTS)
    def test_recommend_specify_iff_high(self, request_text: str):
        """recommend_specify must be True iff classification is high."""
        score = classify_change_request(request_text)
        assert score.recommend_specify == (
            score.classification == ComplexityClassification.HIGH
        ), f"recommend_specify mismatch for: {request_text}"

    @pytest.mark.parametrize("request_text", SAMPLE_REQUESTS)
    def test_total_within_range(self, request_text: str):
        """Total score must be in [0, TOTAL_MAX]."""
        score = classify_change_request(request_text)
        assert 0 <= score.total_score <= TOTAL_MAX

    @pytest.mark.parametrize("request_text", SAMPLE_REQUESTS)
    def test_factor_within_ranges(self, request_text: str):
        """Each factor must be within its documented range."""
        score = classify_change_request(request_text)
        assert 0 <= score.scope_breadth_score <= 3
        assert 0 <= score.coupling_score <= 2
        assert 0 <= score.dependency_churn_score <= 2
        assert 0 <= score.ambiguity_score <= 2
        assert 0 <= score.integration_risk_score <= 1


# ============================================================================
# Determinism (Repeated Runs)
# ============================================================================


class TestDeterminism:
    """Verify that repeated runs produce identical results."""

    REQUESTS = [
        "fix the login button",
        "replace the ORM from SQLAlchemy to Tortoise and migrate the database schema",
        "clean up the project",
        "update all modules across the codebase with the new API contract",
        "add a caching layer to function get_user in service.py",
    ]

    @pytest.mark.parametrize("request_text", REQUESTS)
    def test_repeated_run_determinism(self, request_text: str):
        """Running the classifier 10 times on the same input must produce identical results."""
        first = classify_change_request(request_text)
        for _ in range(9):
            result = classify_change_request(request_text)
            assert result.total_score == first.total_score
            assert result.classification == first.classification
            assert result.scope_breadth_score == first.scope_breadth_score
            assert result.coupling_score == first.coupling_score
            assert result.dependency_churn_score == first.dependency_churn_score
            assert result.ambiguity_score == first.ambiguity_score
            assert result.integration_risk_score == first.integration_risk_score
            assert result.recommend_specify == first.recommend_specify
            assert result.proposed_mode == first.proposed_mode


# ============================================================================
# Review Attention
# ============================================================================


class TestReviewAttention:
    """Test FR-011 elevated review attention behavior."""

    def test_normal_review_by_default(self):
        """Without continue flag, review attention should be normal."""
        score = classify_change_request("fix typo in README")
        assert score.review_attention == ReviewAttention.NORMAL

    def test_elevated_when_continuing_past_high(self):
        """When continuing past high warning, review attention should be elevated."""
        # Use a request that scores high
        request = (
            "replace framework Flask with FastAPI, switch from SQLite to PostgreSQL, "
            "update the api contract and deploy to kubernetes, "
            "refactor all modules across the entire codebase"
        )
        score = classify_change_request(request, continued_after_warning=True)
        if score.classification == ComplexityClassification.HIGH:
            assert score.review_attention == ReviewAttention.ELEVATED

    def test_normal_even_with_continue_when_not_high(self):
        """continue flag has no effect when classification is not high."""
        score = classify_change_request("fix typo in README", continued_after_warning=True)
        assert score.review_attention == ReviewAttention.NORMAL


# ============================================================================
# to_dict Serialization
# ============================================================================


class TestToDict:
    """Test ComplexityScore.to_dict() serialization."""

    def test_to_dict_has_all_fields(self):
        """to_dict should contain all required camelCase fields."""
        score = classify_change_request("add a caching layer")
        d = score.to_dict()
        assert "scopeBreadthScore" in d
        assert "couplingScore" in d
        assert "dependencyChurnScore" in d
        assert "ambiguityScore" in d
        assert "integrationRiskScore" in d
        assert "totalScore" in d
        assert "classification" in d
        assert "recommendSpecify" in d
        assert "proposedMode" in d
        assert "reviewAttention" in d

    def test_to_dict_values_are_serializable(self):
        """All values should be JSON-serializable types."""
        import json

        score = classify_change_request("add a caching layer")
        d = score.to_dict()
        # Should not raise
        serialized = json.dumps(d)
        assert isinstance(serialized, str)


# ============================================================================
# End-to-End Classification
# ============================================================================


class TestEndToEndClassification:
    """Test full classify_change_request with realistic inputs."""

    def test_simple_request(self):
        """A simple, targeted request should classify as simple."""
        score = classify_change_request("fix the typo in README.md")
        assert score.classification == ComplexityClassification.SIMPLE
        assert score.total_score <= SIMPLE_MAX

    def test_complex_request(self):
        """A moderately complex request should classify as complex."""
        score = classify_change_request(
            "add package requests and update the shared config module "
            "and the interface for the plugin system, "
            "then modify function validate_input in validator.py"
        )
        assert score.total_score >= SIMPLE_MAX + 1

    def test_high_complexity_request(self):
        """A highly complex request should classify as high."""
        score = classify_change_request(
            "replace framework Django with FastAPI, migrate from PostgreSQL to MongoDB, "
            "update the api contract for all endpoints, modify the deployment pipeline "
            "and kubernetes manifests, refactor all modules across the codebase"
        )
        assert score.classification == ComplexityClassification.HIGH
        assert score.recommend_specify is True

    def test_empty_request(self):
        """An empty request should still produce a valid score."""
        score = classify_change_request("")
        assert score.total_score == 0
        assert score.classification == ComplexityClassification.SIMPLE
