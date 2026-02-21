import os
import glob
import subprocess
import json
import random
import shutil
from pathlib import Path
import requests

import pandas as pd
import javalang
from javalang.tokenizer import tokenize

# Configuration
CLONE_DIR = "/Users/abigailschwall/Documents/WM_Classes/GenAI/java_repos"
OUTPUT_DIR = "/Users/abigailschwall/Documents/WM_Classes/GenAI"

CLASSES_PER_REPO = 20   # Java files to sample per repo
MIN_TOKENS = 10         # Minimum tokens per method
MAX_TOKENS = 500       # Maximum tokens per method

VAL_SIZE = 1000
TEST_SIZE = 1000

# for reproducability
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Create directories
os.makedirs(CLONE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Setup complete!")
print(f"Clone directory: {CLONE_DIR}")
print(f"Output directory: {OUTPUT_DIR}")


def fetch_top_java_repos(num_repos=700, per_page=100):
    """
    Fetch top-starred Java repositories from GitHub API.
    Skips forked repos to avoid duplicate code.
    """
    repos = []
    page = 1

    while len(repos) < num_repos:
        url = "https://api.github.com/search/repositories"
        params = {
            "q": "language:java stars:>1000 size:>1000 pushed:>2025-02-01",
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page
        }

        response = requests.get(url, params=params)

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break

        data = response.json()
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            if item.get("fork", False):
                continue

            repos.append({
                "full_name": item["full_name"],
                "clone_url": item["clone_url"],
                "stars": item["stargazers_count"],
                "size": item["size"],
                "push_date": item["pushed_at"],
                "description": item.get("description", "")
            })

        page += 1

        if len(repos) >= num_repos:
            break

    return repos[:num_repos]


def clone_repo(clone_url, dest_dir):
    """
    Shallow clone a repository.
    Returns True if successful, False otherwise.
    """
    try:
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)

        cmd = ["git", "clone", "--depth", "1", "--quiet", clone_url, dest_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  Timeout cloning {clone_url}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def find_java_files(repo_path):
    """
    Find all .java files in a repository.
    Excludes test files and common non-source directories.
    """
    java_files = []
    exclude_patterns = ["test", "tests", "example", "examples", "sample", "demo", "generated"]

    for root, dirs, files in os.walk(repo_path):
        root_lower = root.lower()
        if any(pattern in root_lower for pattern in exclude_patterns):
            continue

        for file in files:
            if file.endswith(".java"):
                java_files.append(os.path.join(root, file))

    return java_files


def select_java_files(java_files, max_files):
    """
    Randomly select up to max_files from the list.
    """
    if len(java_files) <= max_files:
        return java_files
    return random.sample(java_files, max_files)


def read_file_content(file_path):
    """Read file content with multiple encoding fallbacks."""
    encodings = ['utf-8', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    return None


def extract_method_source(source_code, method_node, lines):
    """Extract the source code of a method by counting braces."""
    try:
        start_line = method_node.position.line - 1

        brace_count = 0
        started = False
        end_line = start_line

        for i in range(start_line, len(lines)):
            line = lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1

            if started and brace_count == 0:
                end_line = i
                break

        method_lines = lines[start_line:end_line + 1]
        return '\n'.join(method_lines)

    except Exception:
        return None


def extract_methods_from_file(file_path, repo_name):
    """Parse a Java file and extract all methods."""
    methods = []

    source_code = read_file_content(file_path)
    if source_code is None:
        return methods

    lines = source_code.split('\n')

    try:
        tree = javalang.parse.parse(source_code)

        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            method_source = extract_method_source(source_code, node, lines)

            if method_source:
                methods.append({
                    "repo": repo_name,
                    "file": os.path.basename(file_path),
                    "method_name": node.name,
                    "source": method_source
                })

    except javalang.parser.JavaSyntaxError:
        pass
    except Exception:
        pass

    return methods

def contains_non_ascii(text):
    """Check if text contains non-ASCII characters."""
    try:
        text.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True


def count_tokens(source_code):
    """Count the number of Java tokens in source code."""
    try:
        tokens = list(tokenize(source_code))
        return len(tokens)
    except:
        return 0
    
# TODO: Write your filtering functions here

# check if method starts with get or set

def is_get(method_name):
    return method_name.startswith("get") # TODO : maybe delete these methods?
    
def is_set(method_name):
    return method_name.startswith("set")

def tokenize_method(source_code):
    """Tokenize Java source code into space-separated tokens."""
    try:
        tokens = list(tokenize(source_code))
        token_values = [token.value for token in tokens]
        return ' '.join(token_values)
    except:
        return None

def is_clean_method(tokenized_code):
    """Check if method is clean (single method, complete)."""
    method_keywords = tokenized_code.count("public ") + tokenized_code.count("private ") + tokenized_code.count("protected ")
    if method_keywords > 1:
        return False
    if not tokenized_code.endswith("}"):
        return False
    return True

def main():
    # Fetch repositories
    repo_data = fetch_top_java_repos(num_repos=700)
    df_repos = pd.DataFrame(repo_data)
    
    # Split repos by rank (GitHub API order)
    TR1_REPOS = set(df_repos.iloc[0:300]["full_name"])
    VAL_REPOS = set(df_repos.iloc[300:400]["full_name"])
    TEST_REPOS = set(df_repos.iloc[400:700]["full_name"])

    # Clone repositories
    cloned_repos = []
    failed_repos = []

    print(f"Cloning {len(df_repos)} repositories...\n")

    for idx, row in df_repos.iterrows():
        repo_name = row["full_name"]
        clone_url = row["clone_url"]

        safe_name = repo_name.replace("/", "_")
        dest_dir = os.path.join(CLONE_DIR, safe_name)

        print(f"[{idx+1}/{len(df_repos)}] Cloning {repo_name}...", end=" ")

        success = clone_repo(clone_url, dest_dir)

        if success:
            cloned_repos.append({
                "repo_name": repo_name,
                "local_path": dest_dir,
                "stars": row["stars"]
            })
            print("done")
        else:
            failed_repos.append(repo_name)
            print("failed")

    print(f"\n\nSummary:")
    print(f"  Successfully cloned: {len(cloned_repos)}")
    print(f"  Failed: {len(failed_repos)}")

    # Find and select Java files from each repo
    repo_java_files = {}
    all_selected_files = []

    print(f"Finding Java files (selecting up to {CLASSES_PER_REPO} per repo)...\n")

    for repo_info in cloned_repos:
        repo_name = repo_info["repo_name"]
        repo_path = repo_info["local_path"]

        java_files = find_java_files(repo_path)

        if not java_files:
            print(f"  {repo_name}: No Java files found")
            continue

        selected = select_java_files(java_files, max_files=CLASSES_PER_REPO)

        repo_java_files[repo_name] = {
            "total_files": len(java_files),
            "selected_files": [os.path.relpath(f, repo_path) for f in selected],
            "remaining_files": len(java_files) - len(selected)
        }

        all_selected_files.extend([(repo_name, f) for f in selected])
        print(f"  {repo_name}: {len(selected)}/{len(java_files)} files selected")

    print(f"\nTotal Java files selected: {len(all_selected_files)}")


    # Extract methods from all selected files
    all_methods = []

    print(f"Extracting methods from {len(all_selected_files)} files...\n")

    for i, (repo_name, file_path) in enumerate(all_selected_files):
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(all_selected_files)} files...")

        methods = extract_methods_from_file(file_path, repo_name)
        all_methods.extend(methods)

    print(f"\nTotal methods extracted: {len(all_methods)}")

    # Apply filters
    filtered_methods = []

    stats = {
        "total": len(all_methods),
        "non_ascii_dropped": 0,
        "too_short_dropped": 0,
        "too_long_dropped": 0,
        "get_set_dropped": 0,
        "kept": 0
    }

    print(f"Filtering {len(all_methods)} methods...\n")

    for method in all_methods:
        source = method["source"]

        if contains_non_ascii(source):
            stats["non_ascii_dropped"] += 1
            continue

        token_count = count_tokens(source)
        if token_count < MIN_TOKENS:
            stats["too_short_dropped"] += 1
            continue

        # TODO: Apply your filters here
        if token_count > MAX_TOKENS:
            stats["too_long_dropped"] += 1
            continue

        if is_get(method["method_name"]):
            stats["get_set_dropped"] += 1
            continue

        if is_set(method["method_name"]):
            stats["get_set_dropped"] += 1
            continue

        method["token_count"] = token_count
        filtered_methods.append(method)
        stats["kept"] += 1

    print(f"Filtering Results:")
    print(f"  Total methods:        {stats['total']}")
    print(f"  Dropped (non-ASCII):  {stats['non_ascii_dropped']}")
    print(f"  Dropped (< {MIN_TOKENS} tokens): {stats['too_short_dropped']}")
    print(f"  Dropped (> {MAX_TOKENS} tokens): {stats['too_long_dropped']}")
    print(f"  Dropped (get or set method): {stats['get_set_dropped']}")
    print(f"  -------------------------")
    print(f"  Methods kept:         {stats['kept']}")

    # Tokenize all methods
    tokenized_methods = []

    print(f"Tokenizing {len(filtered_methods)} methods...\n")

    for method in filtered_methods:
        tokenized = tokenize_method(method["source"])

        if tokenized:
            tokenized_methods.append({
                "repo": method["repo"],
                "file": method["file"],
                "method_name": method["method_name"],
                "tokenized_code": tokenized,
                "token_count": method["token_count"]
            })

    print(f"Successfully tokenized: {len(tokenized_methods)} methods")

    # Show example
    print(f"\nExample tokenized method:")
    if tokenized_methods:
        example = tokenized_methods[0]
        print(f"  Repo: {example['repo']}")
        print(f"  File: {example['file']}")
        print(f"  Method: {example['method_name']}")
        print(f"  Tokens ({example['token_count']}):")
        print(f"  {example['tokenized_code'][:200]}..." if len(example['tokenized_code']) > 200 else f"  {example['tokenized_code']}")

    # Clean
    print(f"Before cleaning: {len(tokenized_methods)}")
    tokenized_methods = [m for m in tokenized_methods if is_clean_method(m['tokenized_code'])]
    print(f"After cleaning: {len(tokenized_methods)}")

    # Deduplicate
    seen = set()
    unique_methods = []
    for m in tokenized_methods:
        if m['tokenized_code'] not in seen:
            seen.add(m['tokenized_code'])
            unique_methods.append(m)

    print(f"After dedup: {len(unique_methods)}")
    tokenized_methods = unique_methods

    '''# Shuffle and split
    random.seed(42)
    random.shuffle(tokenized_methods)

    val_size = VAL_SIZE
    test_size = TEST_SIZE
    train_size = len(tokenized_methods) - val_size - test_size

    train_data = tokenized_methods[:train_size]
    val_data = tokenized_methods[train_size:train_size + val_size]
    test_data = tokenized_methods[train_size + val_size:train_size + val_size + test_size]'''

    train_data, val_data = [], []
    test_data = []

    for m in tokenized_methods:
        repo = m["repo"]

        if repo in TR1_REPOS:
            train_data.append(m)
        elif repo in VAL_REPOS:
            val_data.append(m)
        elif repo in TEST_REPOS:
            test_data.append(m)

    print(f"\nDataset Split:")
    print(f"  Training:   {len(train_data)} methods")
    print(f"  Validation: {len(val_data)} methods")
    print(f"  Test:       {len(test_data)} methods")

    # Shuffle once for reproducibility
    random.shuffle(train_data)
    random.shuffle(val_data)
    random.shuffle(test_data)

    # Validation and test sets (~1000 each)
    val_data = val_data[:VAL_SIZE]
    test_data = test_data[:TEST_SIZE]   # choose one test split as self-created test

    # Cap training sizes
    T1 = train_data[:15000]
    T2 = train_data[:25000]
    T3 = train_data[:35000]

    print(f"\nFinal Dataset Sizes (CAPPED):")
    print(f"  T1 (<=15k): {len(T1)}")
    print(f"  T2 (<=25k): {len(T2)}")
    print(f"  T3 (<=35k): {len(T3)}")
    print(f"  Validation: {len(val_data)}")
    print(f"  Test:       {len(test_data)}")

    #Save data sets to text file
    def save_txt(data, filename):
        with open(filename, "w", encoding="utf-8", errors="replace") as f:
            for m in data:
                f.write(m["tokenized_code"] + "\n")
        return filename

    print("\nSaving datasets...")

    t1_path = save_txt(T1, "train_T1.txt")
    t2_path = save_txt(T2, "train_T2.txt")
    t3_path = save_txt(T3, "train_T3.txt")
    val_path = save_txt(val_data, "val.txt")
    test_path = save_txt(test_data, "test_created.txt")

    print("Saved:")
    print(f"  {t1_path}")
    print(f"  {t2_path}")
    print(f"  {t3_path}")
    print(f"  {val_path}")
    print(f"  {test_path}")

if __name__ == "__main__":
    main()