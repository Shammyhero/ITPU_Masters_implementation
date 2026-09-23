"""The live-source case study (plan A11, Fig 4.11): a real feed, a real pipeline.

    record.py   records a GBFS feed into a SQLite history (the system of record, as
                observed) and runs real caching pipelines beside it (what an agent
                would be served)

The data and its velocity are real; the pipeline's design is ours (brief
correction 12). Questions are asked afterwards, over the recording, so every
model sees the same stations at the same moments (invariant 2).
"""
