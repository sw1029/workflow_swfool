# Dependency Name Mapping

Use this reference when a package distribution name differs from its import name. The scanner supports `--dep distribution=import_name`.

Common mappings:

- `beautifulsoup4=bs4`
- `opencv-python=cv2`
- `opencv-contrib-python=cv2`
- `pillow=PIL`
- `pyyaml=yaml`
- `scikit-learn=sklearn`
- `python-dateutil=dateutil`
- `google-cloud-storage=google.cloud.storage`
- `google-auth=google.auth`
- `protobuf=google.protobuf`
- `sentence-transformers=sentence_transformers`
- `huggingface-hub=huggingface_hub`
- `faiss-cpu=faiss`
- `faiss-gpu=faiss`
- `pytorch-lightning=pytorch_lightning`
- `transformers=transformers`
- `torch=torch`
- `tensorflow=tensorflow`
- `fastapi=fastapi`
- `uvicorn=uvicorn`

When uncertain, test both the distribution and the likely import module. Report ambiguity instead of claiming the dependency is missing.
