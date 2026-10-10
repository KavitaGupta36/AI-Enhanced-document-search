import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


def test_irrelevant_query_discards_low_similarity_vector_match(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "DOCUMENTS",
        [{"id": "doc-1", "source": "policy.txt", "content": "Employee leave policy explains vacation time."}],
    )
    monkeypatch.setattr(
        main,
        "search_postgres",
        lambda *_args: [
            {
                "id": 1,
                "source": "policy.txt",
                "score": 0.22,
                "snippet": "Employee leave policy explains vacation time.",
            }
        ],
    )

    assert main.rank_documents("what are quantum mechanics principles") == []


def test_empty_results_return_no_match_without_calling_model(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("The language model should not run without retrieved sources.")

    monkeypatch.setattr(main, "get_openai_client", fail_if_called)

    answer = main.create_llm_answer("quantum mechanics", [])

    assert "could not find" in answer.lower()