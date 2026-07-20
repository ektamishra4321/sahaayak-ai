"""Add Amazon India Late Dispatch policy doc to the corpus and re-ingest.
Put this file inside the sahaayak-ai folder, then run:  python fix_amazon_corpus.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS_AMAZON = os.path.join(ROOT, "corpus", "amazon")

DOC_PATH = os.path.join(CORPUS_AMAZON, "late-dispatch-shipping-performance.md")

DOC = """# Amazon India Shipping Performance & Late Dispatch Policy (researched draft)
source_url: https://sellercentral.amazon.in/help/hub/reference/G200205250

## What is Late Dispatch Rate (LDR)
Late Dispatch Rate (LDR) ek shipping performance metric hai jo seller-fulfilled
orders pe apply hota hai. LDR = un orders ka percentage jinka ship-confirm
expected ship date ke BAAD hua, divided by total orders, ek fixed time window
(7-day aur 30-day) mein. Amazon expect karta hai ki sellers LDR ko 4% se neeche
rakhein. FBA orders is metric mein count nahi hote kyunki unki shipping Amazon
handle karta hai.

## Late dispatch hone pe kya hota hai
Agar order expected ship date tak confirm nahi hua, to woh late dispatch count
hota hai. High LDR (4% se upar) ke consequences ho sakte hain: Account Health
rating pe negative impact, buyer ko late delivery ka risk (jo negative feedback
aur A-to-z Guarantee claims badhata hai), aur repeated ya severe cases mein
seller-fulfilled listings ka deactivation. Amazon pehle Account Health page pe
warning dikhata hai; seller ko performance improve karne ka mauka milta hai.

## Late dispatch se kaise bachein
Practical steps: (1) Handling time realistic set karo — agar 1 day mein pack
nahi kar sakte to 2-day handling time rakho. (2) Order ship karne ke turant
baad ship-confirm karo, warehouse se nikalne ka wait mat karo agar carrier
pickup confirm hai. (3) Holidays aur high-volume periods (sale events) se
pehle handling time temporarily badha do ya vacation mode use karo. (4)
Account Health dashboard weekly check karo — LDR wahan 7-day aur 30-day
window mein dikhta hai.

## Appeal aur reinstatement
Agar listings deactivate ho jayein high LDR ki wajah se, seller ko Plan of
Action (POA) submit karna hota hai Account Health page se. POA mein teen
cheezein chahiye: root cause (late dispatch kyun hua), corrective action
(abhi kya fix kiya), aur preventive steps (dobara na ho iske liye kya
process change kiya). Generic POA reject ho jaate hain — specific process
changes likhna zaroori hai.
"""


def main() -> None:
    # 1. Sanity check: are we inside the repo?
    if not os.path.isdir(os.path.join(ROOT, "rag")):
        print("ERROR: rag/ folder not found. Put this script inside the sahaayak-ai folder and run again.")
        sys.exit(1)

    # 2. Check config supports 'amazon' marketplace
    sys.path.insert(0, ROOT)
    try:
        import config
        markets = list(getattr(config, "SUPPORTED_MARKETPLACES", []))
        if "amazon" not in markets:
            print(f"WARNING: 'amazon' is not in config.SUPPORTED_MARKETPLACES (currently: {markets}).")
            print("Add 'amazon' to that list in config.py, then re-run this script.")
            sys.exit(1)
        print(f"OK: config supports marketplaces {markets}")
    except Exception as e:
        print(f"WARNING: could not verify config ({e}). Continuing anyway.")

    # 3. Write the doc
    os.makedirs(CORPUS_AMAZON, exist_ok=True)
    with open(DOC_PATH, "w", encoding="utf-8") as f:
        f.write(DOC)
    print(f"Wrote: {os.path.relpath(DOC_PATH, ROOT)}")

    # 4. Re-ingest
    print("Running ingestion...")
    result = subprocess.run([sys.executable, "-m", "rag.ingest"], cwd=ROOT)
    if result.returncode != 0:
        print("ERROR: ingestion failed. Scroll up for the error message.")
        sys.exit(1)

    print()
    print("DONE. Amazon late-dispatch doc ingested.")
    print("Next: restart the app locally and re-ask:")
    print('  "Amazon India pe late dispatch penalty kya hai?"')


if __name__ == "__main__":
    main()
