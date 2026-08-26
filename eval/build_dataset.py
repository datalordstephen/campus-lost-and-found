"""Assemble the retrieval test set from COCO val2017.

Why COCO rather than photos we collect ourselves: the captions are written by
people who never saw this system, so the queries are not tuned to it. Writing
our own descriptions of our own photos would measure how well we describe
things, not how well the retrieval works.

Each sampled image contributes two independent human captions:

  caption A -> the *lost report*   (the query, for both CLIP and the baseline)
  caption B -> the *found listing* (the text the TF-IDF baseline searches)

That is what makes the comparison fair. CLIP matches caption A against the
photograph; TF-IDF matches caption A against caption B. Both are answering
"which handed-in item is this?", from the evidence each method can actually use.

    uv run python eval/build_dataset.py --n 200
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"
IMAGES = DATA / "images"
MANIFEST = DATA / "testset.json"

# COCO categories that plausibly turn up in a campus lost-and-found box.
# Vehicles, animals, furniture and food are excluded — nobody hands in a bus.
LOSABLE = {
    "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis",
    "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
}


def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        sys.exit(f"Missing {path}. Run the annotation download first (see README).")
    return json.loads(path.read_text())


def fetch(url: str, attempts: int = 4) -> bytes:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 * 2**attempt)
    raise RuntimeError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=200, help="how many pairs to sample")
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()

    instances = load("instances_val2017.json")
    captions = load("captions_val2017.json")

    id_to_name = {c["id"]: c["name"] for c in instances["categories"]}
    losable_ids = {cid for cid, name in id_to_name.items() if name in LOSABLE}

    # Area of each annotation per image, so we can insist the losable object is
    # the *subject* of the photo rather than a bottle on a distant table.
    area_by_image: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for ann in instances["annotations"]:
        if not ann.get("iscrowd"):
            area_by_image[ann["image_id"]][ann["category_id"]] += ann["area"]

    captions_by_image: dict[int, list[str]] = defaultdict(list)
    for ann in captions["annotations"]:
        captions_by_image[ann["image_id"]].append(" ".join(ann["caption"].split()))

    images = {img["id"]: img for img in instances["images"]}

    eligible = []
    for image_id, areas in area_by_image.items():
        if len(captions_by_image.get(image_id, [])) < 2:
            continue
        total = sum(areas.values())
        if total <= 0:
            continue
        best_cid = max(areas, key=areas.get)
        if best_cid not in losable_ids:
            continue
        # The losable object must dominate the annotated content, and occupy a
        # reasonable share of the frame.
        share_of_objects = areas[best_cid] / total
        frame = images[image_id]["width"] * images[image_id]["height"]
        share_of_frame = areas[best_cid] / frame
        if share_of_objects < 0.5 or share_of_frame < 0.05:
            continue
        eligible.append((image_id, id_to_name[best_cid]))

    print(f"{len(eligible)} eligible images across {len({c for _, c in eligible})} categories")

    rng = random.Random(args.seed)
    rng.shuffle(eligible)

    # Cap any one category so the set is not 80% teddy bears.
    per_category_cap = max(3, args.n // 8)
    taken: dict[str, int] = defaultdict(int)
    chosen = []
    for image_id, category in eligible:
        if taken[category] >= per_category_cap:
            continue
        chosen.append((image_id, category))
        taken[category] += 1
        if len(chosen) == args.n:
            break

    if len(chosen) < args.n:
        print(f"warning: only {len(chosen)} pairs available under the per-category cap")

    IMAGES.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (image_id, category) in enumerate(chosen, start=1):
        destination = IMAGES / f"{image_id:012d}.jpg"
        if not destination.exists():
            try:
                destination.write_bytes(fetch(images[image_id]["coco_url"]))
            except Exception as exc:  # noqa: BLE001
                print(f"  skipped {image_id}: {exc}")
                continue
        caps = captions_by_image[image_id]
        records.append({
            "image_id": image_id,
            "category": category,
            "image_path": str(destination),
            "query": caps[0],          # the lost report
            "listing": caps[1],        # the finder's own words, for the baseline
            "all_captions": caps,
        })
        if index % 25 == 0:
            print(f"  {index}/{len(chosen)}")

    MANIFEST.write_text(json.dumps(records, indent=2))
    spread = defaultdict(int)
    for r in records:
        spread[r["category"]] += 1
    print(f"\n{len(records)} pairs -> {MANIFEST}")
    print("categories:", dict(sorted(spread.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
