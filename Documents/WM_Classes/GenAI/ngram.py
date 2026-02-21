from collections import Counter
import math
import json

def buildVocab(filename, min_count = 1):
    counter = Counter()

    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            tokens = line.strip().split()
            counter.update(tokens)

    vocab = {tok for tok, c in counter.items() if c >= min_count}
    vocab.add("<UNK>")

    return vocab

def ngrams(filename, vocab, n):
    ngram_counts = Counter()
    context_counts = Counter()

    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            tokens = [
                token if token in vocab else "<UNK>" # mapped as unknown if not in vocab
                for token in line.strip().split()
                ]
            
            if len(tokens) < n:
                continue
            
            for i in range(len(tokens) - n + 1):
                ngram_counts[tuple(tokens[i:i+n])] += 1

                context = tuple(tokens[i:i+n])[:-1] # find context window
                context_counts[context] += 1

    return ngram_counts, context_counts

def train_model(train_file, n):
    vocab = buildVocab(train_file)
    ngram_counts, context_counts = ngrams(train_file, vocab, n)
    probs = laplaceSmoothing(ngram_counts, context_counts, vocab)

    return vocab, ngram_counts, context_counts, probs


'''def laplaceSmoothing(ngram_counts, context_counts, vocab, alpha=1.0):
    vocab_size = len(vocab)
    smoothed_probs = {}

    for context in context_counts:
        for word in vocab:
            ngram = context + (word,)
            count = ngram_counts.get(ngram, 0)
            denominator = context_counts[context] + alpha * vocab_size
            smoothed_probs[ngram] = (count + alpha) / denominator

    return smoothed_probs'''

def laplaceSmoothing(ngram_counts, context_counts, vocab, alpha=1.0): # TODO: switch for nltk package

    vocab_size = len(vocab)
    smoothed_probs = {}

    for ngram, count in ngram_counts.items():
        context = ngram[:-1]
        denominator = context_counts[context] + alpha * vocab_size
        smoothed_probs[ngram] = (count + alpha) / denominator

    return smoothed_probs

def perplexity(val_file, probs, vocab, n, context_counts):
    log_sum = 0
    token_count = 0

    with open(val_file, 'r', encoding='utf-8') as file:
        for line in file:
            tokens = [t if t in vocab else "<UNK>" for t in line.strip().split()]

            if len(tokens) < n:
                continue

            for i in range(len(tokens) - n + 1):
                context = tuple(tokens[i:i+n-1])
                word = tokens[i+n-1]
                ngram = context + (word,)

                # --- FIX FOR UNSEEN CONTEXTS ---
                if context not in context_counts:
                    val_prob = 1 / len(vocab)
                else:
                    # If context exists but ngram unseen, fall back to uniform
                    val_prob = probs.get(ngram, 1 / len(vocab))

                log_sum += math.log(val_prob, 2)
                token_count += 1

    entropy = -log_sum / token_count
    return 2 ** entropy


def validateModels(n, train_files, val_file):
    models = []

    for i in n:
        print("TRAINING WITH ", i, " GRAMS")
        for file in train_files:
           vocab, ngram_counts, context_counts, probs = train_model(file, i) 
           val_perplexity = perplexity(val_file, probs, vocab, i, context_counts)
           models.append((i, file, val_perplexity, probs, vocab)) # save models w vocab, ngrams, and context as tuples
           print("Training results for", file, ": ", val_perplexity)
    best_model = min(models, key=lambda x: x[2]) # find model with smallest perplexity

    return best_model

def testModels(test_file, probs, vocab, n, context_next_probs, output_file):

    log_sum = 0
    token_count = 0

    results = {
        "testSet": test_file,
        "perplexity": None,   # will compute using ground-truth tokens
        "data": []
    }

    with open(test_file, 'r', encoding='utf-8') as file:
        for idx, line in enumerate(file):
            tokens = [t if t in vocab else "<UNK>" for t in line.strip().split()]

            if len(tokens) < n:
                continue

            entry = {
                "index": f"ID{idx+1}",
                "tokenizedCode": line.strip(),
                "contextWindow": n,
                "predictions": []
            }

            for i in range(len(tokens) - n + 1):
                context = tuple(tokens[i:i+n-1])
                ground_truth = tokens[i+n-1]

                # compute probability of ground-truth token for perplexity
                gt_prob = probs.get(context + (ground_truth,), 1 / len(vocab))
                log_sum += math.log(gt_prob, 2)
                token_count += 1

                # predict the token with highest probability
                best_token, best_prob = max(context_next_probs.get(context, [(ground_truth, 1e-12)]), key=lambda x: x[1]
)

                entry["predictions"].append({
                    "context": list(context),
                    "predToken": best_token,
                    "predProbability": round(best_prob, 6),
                    "groundTruth": ground_truth
                })

            results["data"].append(entry)

    # overall perplexity using ground-truth probabilities
    entropy = -log_sum / token_count if token_count > 0 else 0
    results["perplexity"] = 2 ** entropy

    with open(output_file, "w", encoding="utf-8") as out:
        json.dump(results, out, indent=4)

    return results

def main():
    train_files = ["train_T1.txt", "train_T2.txt", "train_T3.txt"]
    val_file = "val.txt"
    test_given = "test_given.txt"
    test_created = "test_created.txt"

    n = [3, 5, 7]
    best_n, best_file, best_perplexity, best_probs, best_vocab = validateModels(n, train_files, val_file)

    context_next_probs = {}
    for ngram, prob in best_probs.items():
        context = ngram[:-1]
        word = ngram[-1]
        if context not in context_next_probs:
            context_next_probs[context] = []
        context_next_probs[context].append((word, prob))
    print("\nBest Model:: n=", best_n, "file: ", best_file, "perplexity: ", best_perplexity)
    testModels(test_created, best_probs, best_vocab, best_n, context_next_probs, "results-yyyyyy.json")
    testModels(test_given, best_probs, best_vocab, best_n, context_next_probs, "results-xxxxxx.json")


if __name__ == "__main__":
    main()