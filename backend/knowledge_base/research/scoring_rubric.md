# Tech research source scoring rubric

Used by `score_source()` in `tech_research.py`. Scores 0–100; threshold 55 for heuristic memory curation.

## Positive signals (+)

| Signal | Points | Examples |
|--------|--------|----------|
| production_pain | +25 | production, scale, latency, reliability, failure, 生产, 分布式, 容错 |
| authority | +15 | engineering blog from Meta/Uber/Google-scale companies |
| interview_signal | +10 | system design, 架构, interview questions tied to production |

## Negative signals (−)

| Signal | Points | Examples |
|--------|--------|----------|
| generic_tutorial | −20 | hello world, beginner, 入门, tutorial without production context |

## Source types

- **paper**: arXiv / research — valuable if mentions production deployment or real workloads
- **blog**: company engineering blogs preferred over personal tutorials
- **github**: stars + recent commits + README mentioning production use cases
- **interview**: real interview writeups with system design depth

## Heuristic memory

Sources with score ≥ 55 are persisted as `heuristic` memories for reuse across sessions.
