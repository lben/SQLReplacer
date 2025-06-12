import pandas as pd
from haystack import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from sentence_transformers import SentenceTransformer

MODEL_DIR = "./models/all-MiniLM-L6-v2"       # local path after unzip
st_model = SentenceTransformer(MODEL_DIR, device="cpu")  # CPU-only

# Haystack pieces
doc_embedder = SentenceTransformersDocumentEmbedder(model=st_model)
query_embedder = SentenceTransformersTextEmbedder(model=st_model)
store = InMemoryDocumentStore()
retriever = InMemoryEmbeddingRetriever(document_store=store, embedder=query_embedder)  #  [oai_citation:2‡docs.haystack.deepset.ai](https://docs.haystack.deepset.ai/reference/retrievers-api?utm_source=chatgpt.com)

def embed_and_write(df, desc="description", side="left"):
    docs = [Document(content=r[desc], meta={f"{side}_row": i})
            for i, r in df.iterrows()]
    store.write_documents(docs)
    # create embeddings once ⇒ stored with the docs
    doc_embedder.run(documents=docs)
    store.update_embeddings(doc_embedder)

def embedding_semantic_join(df_left, df_right, desc="description", top_k=1):
    embed_and_write(df_left, desc, "left")

    matches = []
    for j, row in df_right.iterrows():
        hits = retriever.retrieve(query=row[desc], top_k=top_k)
        best = hits[0]
        matches.append({
            "right_row": j,
            "left_row": best.meta["left_row"],
            "cos_sim": best.score,          # cosine similarity in [0, 1]
        })

    map_df = pd.DataFrame(matches).set_index("right_row")
    joined = df_right.join(map_df).merge(df_left,
                                         left_on="left_row",
                                         right_index=True,
                                         suffixes=("", "_left"))
    return joined