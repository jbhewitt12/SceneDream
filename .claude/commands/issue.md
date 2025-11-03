# /issue command

You are tasked with creating a well-researched, implementable issue file in the `/issues` folder. Your plan must be grounded in a deep understanding of the existing codebase.

## CRITICAL FIRST STEP: Codebase Exploration

Before creating any plan, you MUST thoroughly explore and understand the relevant parts of the codebase:

### Required Exploration Commands:
1. **Project overview**: Read CLAUDE.md, README.md, and package.json/pyproject.toml
2. **Architecture discovery**:
   - `Grep -n "class.*Service" backend/app/services/` - Find all service classes
   - `Grep -n "def.*route" backend/app/api/` - Find API endpoints
   - `Glob "**/*_test.py"` - Find test patterns
   - `Glob "**/models.py"` - Find data models
3. **Pattern identification**:
   - Read at least 2 similar features completely before planning
   - Document the patterns found (e.g., service → repository → model flow)

### Detailed Exploration Steps:
1. **Read CLAUDE.md** to understand the project structure, conventions, and architecture
2. **Explore relevant existing code**:
   - Use Grep to search for related functionality, patterns, or similar features
   - Use Glob to find relevant files by extension or naming pattern
   - Read key files to understand:
     - Current architecture and design patterns
     - Database models and relationships
     - API structure and endpoints
     - Service layer organization
     - Frontend component patterns
     - Testing approaches
3. **Identify dependencies and integration points**:
   - What existing code will the new feature interact with?
   - What services, models, or components need to be modified?
   - Are there existing patterns or utilities that should be reused?
4. **Consider technical constraints**:
   - Check package.json/pyproject.toml for available libraries
   - Understand the deployment environment
   - Review any relevant configuration files

## CRITICAL GUIDELINES

- There is no test database or testnet.
- NEVER add any steps that involve manually testing the frontend.
- Don't include code blocks in the issue file.

## Creating the Issue Plan

Only after thoroughly understanding the codebase, follow these steps:

1. **Analyze the request in context**: Break down the user's request into a comprehensive plan that fits naturally with the existing architecture.

2. **Determine the next issue number**: 
   - Search the `/issues` folder for existing markdown files
   - Look for files that start with a number (e.g., "001-", "02-", "123-")
   - Find the highest number and increment it by 1
   - If no numbered files exist, start with "001"

3. **Create the issue file** with this naming convention: `{number}-{kebab-case-title}.md`
   - Use zero-padded numbers (001, 002, etc.)
   - Convert the title to kebab-case (lowercase, hyphens instead of spaces)
   - Example: "001-automatic-share-selling-system.md"

4. **Structure the issue file** with the following sections:

```markdown
# {Title}

## Overview
{Brief description of what needs to be implemented}

## Problem Statement
{Clear description of the problem this solves, including:
- Current limitations or pain points
- User impact
- Business value of solving this}

## Proposed Solution
{High-level approach to solving the problem, including:
- Architectural approach
- Key components involved
- Integration with existing systems}

## Codebase Research Summary
{Document your findings from the exploration phase:
- Relevant existing patterns found
- Files and components that will be affected
- Similar features that can serve as reference
- Potential risks or conflicts identified}

## Context for Future Claude Instances
**Important**: Each Claude instance working on this should:
1. Read this entire issue file first
2. Check for any updates/notes from previous phases
3. Review git history for recent related changes
4. Look for TODO/FIXME comments in affected files

**Key Decisions Made**:
- {Document any architectural choices}
- {Note any deviations from standard patterns and why}
- {List any assumptions about the system}

## Pre-Implementation Checklist for Each Phase
Before starting implementation:
- [ ] Verify all dependencies from previous phases
- [ ] Read the latest version of files you'll modify

## Implementation Phases

### Phase Structure

Each phase should include:
- **Phase Name**: Descriptive name and brief description
- **Goal**: Clear statement of what this phase achieves
- **Dependencies**: Prerequisites from previous phases or existing system
- **Time Estimate**: Realistic estimate (typically 30 min - 2 hours per phase)
- **Success Metrics**: Checklist of measurable outcomes
- **Tasks**: Specific, actionable items with file paths and references

### Guidelines for Phases:
1. **Keep phases focused**: Each phase should be completable by one Claude instance
2. **Build incrementally**: Start with core functionality, then add features
3. **Include testing**: Every phase should have associated tests
4. **Be specific**: Use exact file paths, class names, and method names
5. **Reference patterns**: Point to existing code that follows similar patterns

## System Integration Points
Document all external systems/services this feature touches:
- **Database Tables**: {list tables that will be read/written}
- **External APIs**: {list any external services called}
- **Message Queues**: {any async communication}
- **WebSockets**: {real-time connections affected}
- **Cron Jobs**: {scheduled tasks impacted}
- **Cache Layers**: {what needs cache invalidation}

## Technical Considerations
- **Performance**: {Impact on system performance, scaling considerations}
- **Security**: {Authentication, authorization, data protection needs}
- **Database**: {Schema changes, migrations, query optimization}
- **API Design**: {Endpoint structure, request/response formats}
- **Error Handling**: {Failure scenarios and recovery strategies}
- **Monitoring**: {Logging, metrics, alerts needed}

## Testing Strategy
1. **Unit Tests**: {Specific components to test - focus on core functionality}
2. **Integration Tests**: {1-2 key service interactions to verify}
3. **Manual Verification**: {Quick workflow to validate - should take <5 minutes}
4. **Optional Performance Check**: {Only if performance is a key concern}

## Acceptance Criteria
- [ ] All automated tests pass
- [ ] Code follows project conventions (as per CLAUDE.md)
- [ ] Linting passes (`uv run ruff check app`)
- [ ] Feature works as described in the problem statement
- [ ] Error cases are handled gracefully
- [ ] Performance meets requirements
- [ ] Documentation is updated

## Quick Reference Commands
- **Run backend locally**: `cd backend && uvicorn app.main:app --reload`
- **Run tests**: `cd backend && pytest tests/`
- **Lint check**: `cd backend && uv run ruff check app`
- **Type check**: `cd backend && uv run mypy app`
- **Database migration**: `cd backend && alembic upgrade head`
- **View logs**: `docker compose logs -f backend`
- **Check database**: `docker compose exec db psql -U postgres`
- **API testing**: `curl http://localhost:8000/api/health`

## Inter-Instance Communication
### Notes from Previous Claude Instances
<!-- Each instance should add notes here about important discoveries, gotchas, or decisions -->

### Phase Completion Notes Structure:
Each phase should document:
- Completion status
- Date completed
- Key findings or learnings
- Any deviations from the original plan and rationale
- Warnings or gotchas for future work
```

5. **Provide specific, actionable tasks**: 
   - Each checklist item should be concrete and achievable
   - Include file paths when creating or modifying files
   - Reference existing patterns to follow
   - Break large tasks into smaller subtasks
   - Include test writing as explicit tasks
   - Avoid vague tasks like "implement the system"
   
   Good examples:
   - "Create PositionAutoSeller service in backend/app/services/polymarket/position_auto_seller.py following the pattern in polymarket_trader.py"
   - "Add WebSocket handler for position updates in backend/app/services/twitter_websocket/handlers.py implementing the AbstractHandler interface"
   - "Create migration for new 'position_alerts' table with columns: id, position_id, alert_type, threshold, created_at"
   
   Bad examples:
   - "Implement automatic selling functionality"
   - "Add database support"
   - "Create tests"

6. **Quality Checklist** - Ensure your plan:
   - [ ] Is based on thorough codebase exploration
   - [ ] Follows existing architectural patterns
   - [ ] Includes specific file paths and function names
   - [ ] Has clear dependencies between phases
   - [ ] Includes comprehensive testing at each phase
   - [ ] Addresses error handling and edge cases
   - [ ] Considers performance implications
   - [ ] Has realistic time estimates
   - [ ] Identifies and mitigates risks

7. **Common Pitfalls to Avoid**:
   - Don't create new patterns when existing ones work
   - Don't skip the codebase exploration phase
   - Don't create monolithic phases - keep them focused
   - Don't forget about database migrations if schema changes
   - Don't ignore the existing testing infrastructure
   - Don't assume libraries are available without checking

## Notes
   - Ensure each Phase is achievable by a single Claude Code instance.

Now, please create an issue file for the following request: {prompt}