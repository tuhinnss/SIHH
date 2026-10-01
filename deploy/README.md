---
title: Kalamkaar
emoji: 📐
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Indian Standards recommender for procurement specs
---

# Kalamkaar

Recommends applicable Indian Standards for procurement specifications and checks tender PDFs
(Tender Linter). Built for Smart India Hackathon 2026, problem SIH26108, by team "Ding Ding".

* **Search** — describe what is being procured (English, Hindi or Hinglish) and get the applicable
  standards with a ready-to-paste clause.
* **Tender Check** — upload a tender PDF; each line item gets recommendations and flags
  (superseded standard, older edition, missing certification, brand names).
* **Standard** — allied standards and supersession as a graph.

The catalogue is an older public archive snapshot: verify every standard on BIS "Know Your Standards"
before use. This Space holds only metadata, short scope extracts and reference links; the standard
texts are copyright of the Bureau of Indian Standards and are not included.

The first search after the Space wakes up can take up to a minute while the search model loads.
