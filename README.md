# ngram_GenAI
# Virtual environment setup
It is recommended to run this project through a Python virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```
# Dependency installation
Next, install the required dependencies within your virtural environment.
```bash
pip install javalang gitpython pandas requests
```
# Running data extraction
To execute data extraction and splitting:
```bash
python3 Data_Extraction.py
```
# Running train/validation/test

To train, validate, and test data:
```bash
python3 ngram.py
```
# Ouput locations
Results from the created test set were pusehd to the repository,
# Hyper-parameters tuned
Each training dataset was run with n values of 3, 5 and 7. Laplace smoothing (𝛼 = 1) was applied to each dataset.
