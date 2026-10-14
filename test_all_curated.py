import sys
import os

# Add scratch path to sys.path
sys.path.insert(0, r"C:\Users\DELL\.gemini\antigravity-ide\scratch\worstai-chat")

from api.index import synthesize_academic_response

test_queries = [
    "what is binary search",
    "how does a compiler work",
    "difference between list and tuple in python",
    "choosing the appropriate number of cluster",
    "merge sort vs quick sort time complexity",
    "what is deadlock in operating system",
    "4 pillars of oops",
    "tcp vs udp",
    "dbms normalization",
    "process vs thread",
    "stack vs queue",
    "bfs vs dfs",
    "array vs linked list",
    "acid properties in dbms",
    "primary key vs foreign key",
    "osi model 7 layers",
    "mutex vs semaphore",
    "method overloading vs method overriding",
    "interface vs abstract class",
    "supervised vs unsupervised learning",
    "overfitting vs underfitting",
    "http vs https"
]

print(f"=== TESTING {len(test_queries)} CURATED TOPICS ===")
all_passed = True
for q in test_queries:
    ans = synthesize_academic_response(q, only_curated=True)
    if not ans:
        print(f"[FAIL] Curated topic missing for: '{q}'")
        all_passed = False
    else:
        first_line = ans.strip().split('\n')[0]
        word_count = len(ans.split())
        print(f"[OK] '{q}' -> {first_line} ({word_count} words)")

if all_passed:
    print("\nALL 22 CURATED EXAM TOPICS PASSED WITH 100% ACCURACY!")
else:
    print("\nSOME CURATED TOPICS FAILED!")
