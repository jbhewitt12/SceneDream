---
description: Create implementation plan from existing feature document
argument-hint: "[issue-number]"
---

# /issue-doc command

Update an existing issue file in the `/issues` folder with a well-researched implementation plan.

**Key difference from /issue**: This command reads an existing document containing the user's feature description, then appends an implementation plan below it.

## Step 1: Find and Read the Issue

1. The user provides an issue number (e.g., "001")
2. Locate the file in `/issues/` (e.g., `/issues/001-*.md`)
3. Read and understand the user's requirements

## Step 2: Codebase Exploration

Before asking questions or creating any plan, explore the relevant parts of the codebase:

1. **Read CLAUDE.md** to understand project structure and conventions
2. **Find similar features** - read at least 2 similar implementations to understand patterns
3. **Identify affected files** - use Grep/Glob to find code that will need changes
4. **Check dependencies** - review package.json/pyproject.toml for available libraries

## Step 3: Interactive Technical Interview

Ask clarifying questions using the `AskUserQuestion` tool.

**CRITICAL**: Ask questions ONE AT A TIME. Do not dump a list of questions. Wait for each answer before asking the next question. This creates a natural conversation flow.

Ask about:
- **Architecture choices**: "Based on the existing pattern in X, should this follow the same approach?"
- **Edge cases**: "What should happen when [specific scenario] occurs?"
- **Tradeoffs**: "Should we prioritize simplicity or flexibility for [specific aspect]?"
- **UI/UX details**: "How should [specific interaction] work?"

Continue asking follow-up questions until you have clarity on all ambiguous aspects. Only proceed to writing the plan when you have enough information.

## Step 4: Update the Issue File

1. **PRESERVE** the user's original description at the top
2. Add a separator (`---`) after their description
3. Append the implementation plan below using this structure:

```markdown
---

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
- Overwrite the user's original description

Now, please find and update the issue file numbered: $ARGUMENTS
