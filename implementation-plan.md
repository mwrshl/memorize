# Implementation Plan for Algorithm Improvements

## Phase 1: Daily Review Limits
- [x] Add configuration parameter for max daily reviews
- [ ] Query existing review data to count today's completed reviews
- [ ] Modify review selection to respect daily limit
- [ ] Add visual indicator of remaining daily reviews

## Phase 2: Active vs Spaced Categories
- [ ] Add "status" field to verse metadata (active/spaced/new)
- [ ] Update database schema to store status
- [ ] Modify ReviewScore to prioritize active verses
- [ ] Add command to manually change verse status

## Phase 3: Ease Gauging
- [ ] Instrument audio recording to measure total speaking time
- [ ] Add detection for gaps between words
- [ ] Track consecutive successful repetitions
- [ ] Create composite ease score from these metrics
- [ ] Store ease metrics with review results

## Phase 4: Level-based Progression
- [ ] Implement audio mode levels (1-5)
- [ ] Add level field to verse metadata
- [ ] Create progression rules between levels
- [ ] Modify prompt selection based on level
- [ ] Add level-specific UI feedback

## Phase 5: Projection and Growth Control
- [ ] Add 7-day review history analysis
- [ ] Implement projection algorithm for daily averages
- [ ] Add logic to control growth of active set
- [ ] Create dashboard showing projection stats
- [ ] Add automatic demotion of difficult verses

## Phase 6: LLM Command Integration
- [ ] Add command parsing infrastructure
- [ ] Implement review completion commands
- [ ] Add previous review amendment functionality
- [ ] Create session status reporting
- [ ] Add session exit with summary