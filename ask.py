"""
ask.py — talk to Landed from the terminal.

One-off:      python ask.py "what's my response rate, referral vs cold?"
Interactive:  python ask.py          (then type questions; 'q' to quit)
"""

import os
import sys

from dotenv import load_dotenv

from landed import llm
from landed.agent import ask
from landed.db import build


def answer(question: str, con, client):
    result = ask(question, con, client)
    for i, q in enumerate(result["sql"], 1):
        print(f"\n--- SQL {i} ---\n{q.strip()}")
    print(f"\n=== Answer ===\n{result['answer']}\n")


def main():
    load_dotenv()
    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(here, "real_data") \
        if os.path.isdir(os.path.join(here, "real_data")) \
        else os.path.join(here, "sample_data")
    print(f"[landed] data: {os.path.basename(data_dir)}  |  "
          f"provider: {os.getenv('LANDED_LLM_PROVIDER', 'anthropic')}")

    con = build(data_dir)
    client = llm.from_env()

    question = " ".join(sys.argv[1:]).strip()
    if question:
        answer(question, con, client)
        return

    print("Ask me about your pipeline ('q' to quit):")
    while True:
        q = input("\nyou> ").strip()
        if q.lower() in ("q", "quit", "exit"):
            break
        if q:
            answer(q, con, client)


if __name__ == "__main__":
    main()
