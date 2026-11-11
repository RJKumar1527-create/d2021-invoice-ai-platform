import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


KNOWLEDGE_BASE_PATH = Path(
    "knowledge_base/business_rules.json"
)

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"


def load_business_rules():
    """Load sanitized business rules."""
    if not KNOWLEDGE_BASE_PATH.exists():
        return []

    with open(
        KNOWLEDGE_BASE_PATH,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def create_rule_document(rule):
    """Build the text embedded for one rule."""
    return "\n".join(
        [
            f"Rule ID: {rule.get('rule_id', '')}",
            f"Category: {rule.get('category', '')}",
            f"Title: {rule.get('title', '')}",
            f"Rule: {rule.get('rule_text', '')}",
            (
                "Recommended action: "
                f"{rule.get('recommended_action', '')}"
            ),
            f"Source: {rule.get('source', '')}",
        ]
    )


def normalize_vector(vector):
    """Normalize a vector for cosine similarity."""
    array = np.asarray(
        vector,
        dtype=np.float32,
    )

    norm = np.linalg.norm(array)

    if norm == 0:
        return array

    return array / norm


def knowledge_base_hash(rules):
    """Create a hash to detect knowledge-base changes."""
    serialized_rules = json.dumps(
        rules,
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        serialized_rules.encode("utf-8")
    ).hexdigest()


def get_gemini_settings():
    """Read Gemini configuration from Streamlit secrets."""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]

        model_name = st.secrets.get(
            "GEMINI_EMBEDDING_MODEL",
            DEFAULT_EMBEDDING_MODEL,
        )

        return api_key, model_name

    except (KeyError, FileNotFoundError):
        return None, DEFAULT_EMBEDDING_MODEL


def get_embedding_client(api_key):
    """Create a Gemini API client."""
    return genai.Client(api_key=api_key)


def extract_embedding_values(response):
    """Extract vectors from Gemini embedding response."""
    if not response.embeddings:
        raise ValueError(
            "Gemini returned no embeddings."
        )

    vectors = []

    for embedding in response.embeddings:
        values = getattr(
            embedding,
            "values",
            None,
        )

        if values is None:
            raise ValueError(
                "Gemini embedding response has no values."
            )

        vectors.append(
            normalize_vector(values)
        )

    return vectors


def embed_documents(
    client,
    model_name,
    documents,
):
    """Generate Gemini document embeddings in batches."""
    vectors = []
    batch_size = 50

    for start in range(
        0,
        len(documents),
        batch_size,
    ):
        batch = documents[
            start:start + batch_size
        ]

        response = client.models.embed_content(
            model=model_name,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            ),
        )

        vectors.extend(
            extract_embedding_values(response)
        )

    return np.vstack(vectors)


def embed_query(
    client,
    model_name,
    query,
):
    """Generate a Gemini retrieval-query embedding."""
    response = client.models.embed_content(
        model=model_name,
        contents=[query],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768,
        ),
    )

    vectors = extract_embedding_values(
        response
    )

    return vectors[0]


def get_or_create_rule_embeddings(
    rules,
    client,
    model_name,
):
    """
    Create rule embeddings once per Streamlit session.

    Embeddings are regenerated only when the rule knowledge base
    or embedding model changes.
    """
    current_hash = knowledge_base_hash(rules)

    cached_hash = st.session_state.get(
        "rule_embedding_hash"
    )

    cached_model = st.session_state.get(
        "rule_embedding_model"
    )

    cached_vectors = st.session_state.get(
        "rule_embedding_vectors"
    )

    if (
        cached_hash == current_hash
        and cached_model == model_name
        and cached_vectors is not None
    ):
        return cached_vectors

    documents = [
        create_rule_document(rule)
        for rule in rules
    ]

    vectors = embed_documents(
        client,
        model_name,
        documents,
    )

    st.session_state.rule_embedding_hash = (
        current_hash
    )

    st.session_state.rule_embedding_model = (
        model_name
    )

    st.session_state.rule_embedding_vectors = (
        vectors
    )

    return vectors


def retrieve_with_gemini(
    query,
    rules,
    client,
    model_name,
    top_k=3,
):
    """Retrieve rules using Gemini semantic embeddings."""
    rule_vectors = get_or_create_rule_embeddings(
        rules,
        client,
        model_name,
    )

    query_vector = embed_query(
        client,
        model_name,
        query,
    )

    scores = np.dot(
        rule_vectors,
        query_vector,
    )

    ranked_indices = np.argsort(
        scores
    )[::-1]

    results = []

    for index in ranked_indices[:top_k]:
        result = dict(rules[index])

        result["relevance_score"] = round(
            max(float(scores[index]), 0.0)
            * 100,
            2,
        )

        result["retrieval_method"] = (
            "Gemini Vector Embeddings"
        )

        results.append(result)

    return results


def retrieve_with_tfidf(
    query,
    rules,
    top_k=3,
):
    """Fallback retrieval when Gemini is unavailable."""
    documents = [
        create_rule_document(rule)
        for rule in rules
    ]

    corpus = documents + [query]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
    )

    vectors = vectorizer.fit_transform(
        corpus
    )

    scores = cosine_similarity(
        vectors[-1],
        vectors[:-1],
    ).flatten()

    ranked_indices = np.argsort(
        scores
    )[::-1]

    results = []

    for index in ranked_indices[:top_k]:
        result = dict(rules[index])

        result["relevance_score"] = round(
            float(scores[index]) * 100,
            2,
        )

        result["retrieval_method"] = (
            "TF-IDF Fallback"
        )

        results.append(result)

    return results


def retrieve_rules(
    query,
    rules,
    client,
    model_name,
    top_k,
):
    """
    Use Gemini embeddings first.

    Automatically fall back to TF-IDF if the API is unavailable.
    """
    if not query.strip():
        return [], "No query", None

    if client is None:
        fallback_results = retrieve_with_tfidf(
            query,
            rules,
            top_k,
        )

        return (
            fallback_results,
            "TF-IDF Fallback",
            "Gemini API key is unavailable.",
        )

    try:
        results = retrieve_with_gemini(
            query,
            rules,
            client,
            model_name,
            top_k,
        )

        return (
            results,
            "Gemini Vector Embeddings",
            None,
        )

    except Exception as error:
        fallback_results = retrieve_with_tfidf(
            query,
            rules,
            top_k,
        )

        return (
            fallback_results,
            "TF-IDF Fallback",
            str(error),
        )


def build_safe_invoice_alias(
    risk_df,
    selected_invoice,
):
    """Create a non-sensitive invoice alias."""
    invoice_numbers = (
        risk_df["Invoice Number"]
        .astype(str)
        .tolist()
    )

    try:
        position = (
            invoice_numbers.index(
                str(selected_invoice)
            )
            + 1
        )
    except ValueError:
        position = 1

    return f"INV-{position:05d}"


def build_sanitized_query(
    risk_row,
    safe_invoice_alias,
):
    """
    Build retrieval evidence without sending original invoice,
    MPAN, customer, site or address identifiers.
    """
    risk_level = str(
        risk_row.get("Risk Level", "")
    )

    model_result = str(
        risk_row.get("Model Result", "")
    )

    unusual_features = str(
        risk_row.get(
            "Unusual Features",
            "",
        )
    )

    validation_score = float(
        risk_row.get(
            "Validation Score",
            0,
        )
        or 0
    )

    reconciliation_score = float(
        risk_row.get(
            "Reconciliation Score",
            0,
        )
        or 0
    )

    anomaly_score = float(
        risk_row.get(
            "Anomaly Score",
            0,
        )
        or 0
    )

    parts = [
        f"Sanitized invoice: {safe_invoice_alias}",
        f"Risk level: {risk_level}",
        f"Model result: {model_result}",
        f"Anomaly score: {anomaly_score:.2f}",
        f"Unusual features: {unusual_features}",
    ]

    if validation_score > 0:
        parts.append(
            "The invoice has validation failures or warnings."
        )
    else:
        parts.append(
            "The invoice passed critical validation."
        )

    if reconciliation_score > 0:
        parts.append(
            "The BCD and CCD values have a reconciliation "
            "difference."
        )
    else:
        parts.append(
            "The BCD net matches the sum of CCD charges."
        )

    parts.append(
        "Retrieve rules relevant to investigation, anomaly "
        "interpretation, charge review and human review."
    )

    return "\n".join(parts)


st.title("D2021 Invoice Validation Platform")
st.subheader(
    "Step 7: Gemini Vector Rule Retrieval"
)

risk_results = st.session_state.get(
    "risk_results"
)

if risk_results is None:
    st.warning(
        "Risk scoring has not been completed."
    )
    st.info(
        "Complete Step 6: Risk Scoring first."
    )
    st.stop()


rules = load_business_rules()

if not rules:
    st.error(
        "The business-rule knowledge base could not be loaded."
    )
    st.code(
        "knowledge_base/business_rules.json"
    )
    st.stop()


api_key, model_name = get_gemini_settings()

gemini_client = (
    get_embedding_client(api_key)
    if api_key
    else None
)

risk_df = pd.DataFrame(risk_results)


if gemini_client:
    st.success(
        "Gemini embedding service is configured. "
        "Semantic vector retrieval is enabled."
    )
else:
    st.warning(
        "Gemini API key was not found. "
        "TF-IDF fallback retrieval is active."
    )


st.caption(
    "Only sanitized risk evidence and sanitized business rules "
    "are sent to Gemini. Original D2021 records and identifiers "
    "are not transmitted."
)


metric1, metric2, metric3 = st.columns(3)

metric1.metric(
    "Knowledge-Base Rules",
    len(rules),
)

metric2.metric(
    "Rule Categories",
    len(
        {
            rule.get("category")
            for rule in rules
        }
    ),
)

metric3.metric(
    "Invoices Available",
    len(risk_df),
)


st.markdown("---")
st.subheader("Invoice Rule Retrieval")

invoice_options = (
    risk_df.sort_values(
        "Final Risk Score",
        ascending=False,
    )["Invoice Number"]
    .astype(str)
    .tolist()
)

selected_invoice = st.selectbox(
    "Select an invoice",
    invoice_options,
)

selected_row = risk_df[
    risk_df["Invoice Number"].astype(str)
    == selected_invoice
].iloc[0]

safe_invoice_alias = build_safe_invoice_alias(
    risk_df,
    selected_invoice,
)


detail1, detail2, detail3, detail4 = st.columns(4)

detail1.metric(
    "Safe Invoice Alias",
    safe_invoice_alias,
)

detail2.metric(
    "Risk Level",
    selected_row["Risk Level"],
)

detail3.metric(
    "Final Risk Score",
    f"{float(selected_row['Final Risk Score']):.2f}",
)

detail4.metric(
    "Anomaly Score",
    f"{float(selected_row['Anomaly Score']):.2f}",
)


automatic_query = build_sanitized_query(
    selected_row,
    safe_invoice_alias,
)

retrieval_query = st.text_area(
    "Sanitized retrieval query",
    value=automatic_query,
    height=190,
)

top_k = st.slider(
    "Number of rules to retrieve",
    min_value=1,
    max_value=5,
    value=3,
)


if st.button(
    "Run Semantic Retrieval",
    type="primary",
    use_container_width=True,
):
    with st.spinner(
        "Generating embeddings and retrieving rules..."
    ):
        (
            retrieved_rules,
            retrieval_method,
            retrieval_error,
        ) = retrieve_rules(
            retrieval_query,
            rules,
            gemini_client,
            model_name,
            top_k,
        )

    st.session_state.current_retrieved_rules = (
        retrieved_rules
    )

    st.session_state.current_retrieval_method = (
        retrieval_method
    )

    st.session_state.current_retrieval_error = (
        retrieval_error
    )


retrieved_rules = st.session_state.get(
    "current_retrieved_rules",
    [],
)

retrieval_method = st.session_state.get(
    "current_retrieval_method",
    "Not executed",
)

retrieval_error = st.session_state.get(
    "current_retrieval_error",
)


if retrieved_rules:
    st.markdown("---")
    st.subheader("Retrieved Business Rules")

    st.write(
        f"**Retrieval method:** {retrieval_method}"
    )

    st.write(
        f"**Embedding model:** {model_name}"
    )

    if retrieval_error:
        st.warning(
            "Gemini retrieval was unavailable, so TF-IDF "
            f"fallback was used. Details: {retrieval_error}"
        )

    for position, rule in enumerate(
        retrieved_rules,
        start=1,
    ):
        with st.container(border=True):
            st.markdown(
                f"### {position}. {rule['title']}"
            )

            column1, column2, column3 = st.columns(3)

            column1.write(
                f"**Rule ID:** {rule['rule_id']}"
            )

            column2.write(
                f"**Category:** {rule['category']}"
            )

            column3.write(
                "**Similarity:** "
                f"{rule['relevance_score']:.2f}%"
            )

            st.write("**Rule**")
            st.write(rule["rule_text"])

            st.write("**Recommended action**")
            st.write(
                rule["recommended_action"]
            )

            st.caption(
                f"Source: {rule['source']}"
            )

    retrieval_record = {
        "safe_invoice_alias": safe_invoice_alias,
        "original_invoice_number": selected_invoice,
        "sanitized_query": retrieval_query,
        "retrieval_method": retrieval_method,
        "embedding_model": model_name,
        "retrieved_rules": retrieved_rules,
    }

    if (
        "rag_retrieval_results"
        not in st.session_state
    ):
        st.session_state.rag_retrieval_results = {}

    st.session_state.rag_retrieval_results[
        selected_invoice
    ] = retrieval_record

    st.success(
        "Semantic retrieval results have been stored "
        "for Step 8: Grounded AI Explanation."
    )