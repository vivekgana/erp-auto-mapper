"""Tests for Knowledge Assistant vector index document builder."""

from erp_auto_mapper.ka.vector_index import build_docs


def test_build_docs_returns_all_types():
    docs = build_docs()
    types = {d["doc_type"] for d in docs}
    assert types == {"cdm_field", "alias", "entity_hint"}


def test_build_docs_cdm_field_count():
    docs = build_docs()
    cdm_docs = [d for d in docs if d["doc_type"] == "cdm_field"]
    assert len(cdm_docs) >= 80


def test_build_docs_alias_count():
    docs = build_docs()
    alias_docs = [d for d in docs if d["doc_type"] == "alias"]
    assert len(alias_docs) >= 100


def test_build_docs_entity_hint_count():
    docs = build_docs()
    hint_docs = [d for d in docs if d["doc_type"] == "entity_hint"]
    assert len(hint_docs) >= 20


def test_build_docs_unique_ids():
    docs = build_docs()
    ids = [d["doc_id"] for d in docs]
    assert len(ids) == len(set(ids))


def test_build_docs_non_empty_text():
    docs = build_docs()
    for doc in docs:
        assert doc["text"], f"Empty text for doc_id={doc['doc_id']}"


def test_build_docs_valid_payload_json():
    import json
    docs = build_docs()
    for doc in docs:
        payload = json.loads(doc["payload_json"])
        assert isinstance(payload, dict)


def test_build_docs_cdm_field_has_entity_and_field():
    docs = build_docs()
    for doc in docs:
        if doc["doc_type"] == "cdm_field":
            assert doc["entity_name"], f"Missing entity_name: {doc['doc_id']}"
            assert doc["field_name"], f"Missing field_name: {doc['doc_id']}"
