"""Unit tests for the retrieval-backed chat service."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services import chat_service


class SendPromptToLlmTests(unittest.TestCase):
    def test_requires_job_ids_before_loading_models(self):
        with patch("services.chat_service.get_embedding_model") as get_embeddings:
            result = chat_service.send_prompt_to_llm("Compare these roles", [])

        self.assertEqual(result, (False, "No jobs were provided for retrieval"))
        get_embeddings.assert_not_called()

    @patch("services.chat_service.invoke_chat_model", return_value=(True, "Role A is the closer match."))
    @patch("services.chat_service.get_embedding_model", return_value="embedding-model")
    @patch("services.chat_service.PgVectorJobRetriever")
    def test_retrieves_job_context_and_includes_resume(
        self,
        retriever_class,
        get_embeddings,
        invoke_chat_model,
    ):
        retriever = retriever_class.return_value
        retriever.invoke.return_value = [
            SimpleNamespace(
                metadata={"title": "Engineer", "company": "Example Co", "job_id": "job-1"},
                page_content="The role requires Python and distributed systems.",
            )
        ]
        progress = []

        result = chat_service.send_prompt_to_llm(
            "Which role fits my background?",
            ["job-1"],
            resume_summary="Resume skills: Python and backend services.",
            on_progress=progress.append,
        )

        self.assertEqual(result, (True, "Role A is the closer match."))
        retriever_class.assert_called_once_with(
            job_ids=["job-1"],
            embeddings="embedding-model",
            top_k=10,
            min_similarity=0.7,
        )
        retriever.invoke.assert_called_once_with("Which role fits my background?")
        model_name, instructions, prompt = invoke_chat_model.call_args.args
        self.assertEqual(model_name, chat_service.config.llm_model_chat)
        self.assertIn("Resume skills: Python and backend services.", instructions)
        self.assertIn("Engineer | Company: Example Co | Job ID: job-1", prompt)
        self.assertIn("The role requires Python and distributed systems.", prompt)
        self.assertIn("Which role fits my background?", prompt)
        self.assertGreaterEqual(len(progress), 3)
        get_embeddings.assert_called_once_with()

    @patch("services.chat_service.invoke_chat_model", return_value=(False, "provider unavailable"))
    @patch("services.chat_service.get_embedding_model", return_value="embedding-model")
    @patch("services.chat_service.PgVectorJobRetriever")
    def test_returns_model_failure_to_caller(
        self,
        retriever_class,
        _get_embeddings,
        _invoke_chat_model,
    ):
        retriever_class.return_value.invoke.return_value = []

        result = chat_service.send_prompt_to_llm("Compare these roles", ["job-1"])

        self.assertEqual(result, (False, "provider unavailable"))


if __name__ == "__main__":
    unittest.main()
