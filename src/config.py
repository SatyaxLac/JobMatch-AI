# config.py

llm_model_summarization = "gpt-6-luna"
llm_model_chat = "gpt-6.2-sol"
local_embed_model = "BAAI/bge-m3"
embedding_dimensions = 1024
embedding_chunk_size = 4000  # tokens, leaving headroom under BGE-M3's 8192-token limit
embedding_chunk_overlap = 200
summarization_max_characters = 40000

# dark / light / road / satellite / dark_no_labels / light_no_labels

map_style_jobs = "light"
map_style_location = "light"
