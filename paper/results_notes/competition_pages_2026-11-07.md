# ARC Prize 2026 - ARC-AGI-3: the competition's own pages, verbatim
Fetched 2026-11-07 01:58 CST through Kaggle's MCP (list_competition_pages, competition arc-prize-2026-arc-agi-3), by
CL1, for citation in the long paper (§5, §8). Page names are Kaggle's. Rules page omitted except §2.5.

## abstract
Build systems that learn and adapt to novel, human-solvable tasks they’ve never seen before and advance AI’s ability to learn new skills efficiently.

## Description
Real intelligence isn’t about memorizing answers - it’s knowing what to do when the problem changes. Today’s AI systems excel at what they were trained to do, but often fall short when something unfamiliar comes along. Most benchmarks reward pattern recognition, not genuine problem-solving.

ARC Prize Foundation focuses on true generalization: whether a system can quickly learn new skills in unfamiliar situations. Instead of rewarding pattern recognition on known tasks, it evaluates how well systems can adapt to new problems they’ve never encountered before. The ARC-AGI-3 evaluation environment is designed so systems can't just memorize solutions. Tasks take place in hidden, interactive environments that require exploration and multi-step reasoning.

In this competition, you’ll build AI systems that adapt on the fly to new tasks in the ARC environment, and develop approaches that learn quickly, generalize well, and solve problems never seen before.

Your solution could help move AI closer to systems that learn the way people do: flexible, efficient, and able to handle new challenges.

The real test of intelligence begins when the problem changes.

## Evaluation
Scores for individual game range from 0 to 100%. A score of 100% represents an agent matching human-level performance, meaning it beat every game while matching the number of actions humans took. While an agent could theoretically exceed 100% by using fewer moves, scores are capped at 100%. The final score averages individual game scores across levels. Read more at the ARC-AGI-3 Scoring Methodology page (https://docs.arcprize.org/methodology).

Submission files are automatically calculated. As long as the agent takes action on _any_ of the games, a submission file for all of the games is created.

## data-description (opening and Scoring)
ARC-AGI-3 is an **Interactive Reasoning Benchmark** designed to measure an AI agent's ability to generalize in novel, unseen environments. Unlike traditional static benchmarks used to evaluate LLMs and reasoning systems, ARC-AGI-3 evaluates frontier AI agent systems on exploration, memory, goal acquisition, and alignment.

> **Note:** Competition evaluation uses a **separate, private set of 110 games** that your agent has never seen. Half of these are used for the Public Leaderboard score, and the other half for the Private Leaderboard score.

AI agents are scored on **two criteria**:
1. **Completion** — How many levels did the agent complete in each game?
2. **Efficiency** — How many actions did the agent take to complete each level, compared to a human baseline?

- For each level completed, the agent's action count is compared to a human baseline (first-time test-testers).
- **Per-level score** = `min(human_actions / agent_actions, 1.0)`, then **squared** (a raw score of 0.5 becomes 0.25).
- **Per-game score** = Weighted average of level scores (weighted by level index, 1-indexed).
- **Total score** = Average of all individual game scores.

## Code Requirements
Submissions to this competition must be made through Notebooks. In order for the "Submit" button to be active after a commit, the following conditions must be met:
- CPU Notebook <= 9 hours run-time
- GPU Notebook <= 9 hours run-time
- Internet access disabled
- Freely & publicly available external data is allowed, including pre-trained models
- Submission file will be automatically generated.

## Upgraded accelerators
We're excited to announce that we've added RTX 6000 machines to the ARC-AGI-3 hardware pool! See this page (https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines#g4-machine-types) for more on these machines. Kaggle uses machine type `g4-standard-48`.
- ARC-AGI-3 3 Only - RTX are only available for notebooks attached to this competition, use of RTX for any other activity could result in moderation action (e.g. site suspension or account ban).
- No Internet - To help ensure these machines are reserved for competition use, all RTX sessions must have internet disabled.

## Rules §2.5 WINNER LICENSE (a)
1. **Open Source:** You hereby license and will license your winning Submission and the source code used to generate the Submission under CC-BY 4.0, an Open Source Initiative-approved license that in no event limits commercial use of such code or model containing or depending on such code.
a. Submissions are required to have open source system, open source model, and open source weights/parameters, as defined in the checklist (https://opensource.org/ai/checklist) from the Open Source AI definition (https://opensource.org/ai/open-source-ai-definition) by the Open Source Initiative.

## Timeline (relevant lines)
* **November 2, 2026** - Final Submission Deadline.
* **December 4, 2026** - Winners announcement.
