---
description: Create a well-researched implementation plan
argument-hint: "[feature description]"
---

# /issue command

Create a well-researched, implementable issue file in the `/issues` folder. Your plan must be grounded in a deep understanding of the existing codebase.

## Step 1: Codebase Exploration

Before asking questions or creating any plan, explore the relevant parts of the codebase:

1. **Read CLAUDE.md** to understand project structure and conventions
2. **Find similar features** - read at least 2 similar implementations to understand patterns
3. **Identify affected files** - use Grep/Glob to find code that will need changes
4. **Check dependencies** - review package.json/pyproject.toml for available libraries

## Step 2: Interactive Technical Interview

After exploring the codebase, ask clarifying questions using the `AskUserQuestion` tool.

**CRITICAL**: Ask questions ONE AT A TIME. Do not dump a list of questions. Wait for each answer before asking the next question. This creates a natural conversation flow.

Ask about:
- **Architecture choices**: "Based on the existing pattern in X, should this follow the same approach?"
- **Edge cases**: "What should happen when [specific scenario] occurs?"
- **Tradeoffs**: "Should we prioritize simplicity or flexibility for [specific aspect]?"
- **UI/UX details**: "How should [specific interaction] work?"

Continue asking follow-up questions until you have clarity on all ambiguous aspects. Only proceed to writing the issue file when you have enough information.

## Step 3: Create the Issue File

1. **Find the next issue number**: Check `/issues` folder, find highest number, increment by 1
2. **Create file**: `issues/{number}-{kebab-case-title}.md`

Use this template:

```markdown
# {Title}

## Overview
{Brief description of what needs to be implemented}

## Problem Statement
{Current limitations, user impact, business value}

## Proposed Solution
{High-level approach, key components, integration points}

## Codebase Research Summary
{Patterns found, files affected, similar features as reference}

## Key Decisions
{Document architectural choices and tradeoffs discussed with the user}

## Implementation Plan

### Phase 1: {Name}
**Goal**: {What this phase achieves}

**Tasks**:
- {Specific task with file path}
- {Another specific task}

**Verification**:
- [ ] {How to verify this phase is complete}

### Phase 2: {Name}
...

## Files to Modify
| File | Action |
|------|--------|
| `path/to/file.py` | Create/Modify |

## Testing Strategy
- **Unit Tests**: {Specific components to test}
- **Manual Verification**: {Quick check to validate}

## Acceptance Criteria
- [ ] All tests pass
- [ ] Linting passes
- [ ] Feature works as described
```

## Guidelines

**Do**:
- Use specific file paths, class names, and method names
- Reference existing patterns to follow
- Break large tasks into smaller subtasks
- Keep phases focused and achievable

**Don't**:
- Include code blocks in the issue file
- Add steps for manual frontend testing
- Create vague tasks like "implement the system"
- Skip the codebase exploration

**Good task examples**:
- "Create ImageProvider ABC in backend/app/services/image_generation/base_provider.py"
- "Add get_distinct_providers() method to GeneratedImageRepository"
- "Update generated-images.tsx to add provider filter dropdown"

**Bad task examples**:
- "Implement the provider system"
- "Add database support"
- "Create tests"

Now, please create an issue file for: $ARGUMENTS
