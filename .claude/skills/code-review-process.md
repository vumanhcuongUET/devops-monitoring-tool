---
name: code-review-process
description: Code review process for AI Assistant - review, document to memory, then implement
whenToUse: |
  Use this skill when working on code review tasks for the AI Assistant module.
  This ensures every task is properly reviewed and documented before implementation.
---

# Code Review Process for AI Assistant

## Overview

This skill enforces a structured review process for all AI Assistant code review tasks.

## Process Steps

### 1. Review Task Requirements
Before implementing any task:
- Read the task description from the plan
- Identify files that will be modified
- Consider architectural implications
- Check for dependencies on other tasks

### 2. Document to Memory
Before any code changes:
- Update `/home/vmcuong/.claude/projects/-home-vmcuong-Downloads-devops-monitoring-tool/memory/ai-assistant-code-review-2026-08-23.md`
- Record: task number, description, planned approach
- Update the task status

### 3. Implement
Only after memory is updated:
- Make code changes
- Follow existing code patterns
- Add appropriate comments and documentation

### 4. Update Memory
After implementation:
- Update memory with completion status
- List files modified
- Note any issues found or deviations from plan

### 5. Proceed to Next Task
Only after memory update is complete.

## Error Handling

### On Model Limit
When encountering model rate limits:
- Automatically retry with exponential backoff
- Preserve context across retries
- Resume from last successful operation

### On Token Exhaustion
When approaching token limit:
- Stop current task gracefully
- Update memory with partial progress
- Save checkpoint of work completed
- Note: "Resume from here on next run"

## Current Task List Reference

See plan at: `/home/vmcuong/.claude/plans/serene-stargazing-corbato.md`

| # | Task | Status |
|---|------|--------|
| 1 | Document backend import pattern with ADR | ✅ Complete |
| 2 | Implement Redis distributed cache | Pending |
| 3 | Implement distributed single-flight with Redis | Pending |
| 4 | Add retry logic with exponential backoff | Pending |
| 5 | Create v1 deprecation plan and migration guide | Pending |
| 6 | Apply consistent input validation | Pending |
| 7 | Implement persistent audit logging | Pending |
| 8 | Create security documentation and test suite | Pending |

## Memory File Location

`/home/vmcuong/.claude/projects/-home-vmcuong-Downloads-devops-monitoring-tool/memory/ai-assistant-code-review-2026-08-23.md`

## ADR Reference

Backend integration pattern documented at:
`docs/adr/001-backend-integration-via-sys-path.md`
